"""매장 상권 맥락(SGIS) — 매장 주소로 동네 인구·상권 특성을 조회해 인사이트에 근거를 더한다.

집계 데이터는 '언제 붐볐나'(숫자)만 준다. 여기서는 통계청 SGIS 오픈API로 매장이 속한
행정동의 '어떤 동네인가'(연령 구성·직장인구/거주인구·아파트 비율 등)를 가져와,
Gemini가 "왜 이런 손님이 오는지"를 지어내지 않고 실제 통계로 추정하게 돕는다.

키(consumer_key/secret)가 없거나 SGIS 호출이 실패하면 프로필은 None이 되고,
인사이트는 상권 근거 없이 시간대만으로 추정한다(기능은 계속 동작).
"""

import logging
from typing import Any, Callable

import httpx

from .config import Settings

logger = logging.getLogger(__name__)

SGIS_BASE = "https://sgisapi.kostat.go.kr/OpenAPI3"

# 데모 매장 주소. 집계 API에 매장 주소가 없어 여기서 관리한다.
# 실제 운영에선 매장 마스터 데이터/집계 API가 주소를 주도록 바꾼다.
STORE_ADDRESSES: dict[str, str] = {
    "store-001": "광주광역시 동구 동계천로 162",
    "store-002": "광주광역시 광산구 임방울대로 338",
}

# SGIS 거주인구 요약의 연령 비율 필드 → 사람이 읽는 라벨.
_AGE_FIELDS: list[tuple[str, str]] = [
    ("teenage_less_than_per", "10대미만"),
    ("teenage_per", "10대"),
    ("twenty_per", "20대"),
    ("thirty_per", "30대"),
    ("forty_per", "40대"),
    ("fifty_per", "50대"),
    ("sixty_per", "60대"),
    ("seventy_more_than_per", "70대이상"),
]


class SgisClient:
    """SGIS 오픈API 최소 래퍼. 토큰을 받아 주소→행정동, 인구·상권 요약을 조회한다."""

    def __init__(self, consumer_key: str, consumer_secret: str, timeout: float = 10.0) -> None:
        self._key = consumer_key
        self._secret = consumer_secret
        self._timeout = timeout
        self._token: str | None = None

    def _call(self, path: str, **params: Any) -> dict[str, Any]:
        r = httpx.get(
            f"{SGIS_BASE}/{path}",
            params=params,
            timeout=self._timeout,
            follow_redirects=True,  # SGIS가 mods.go.kr로 리다이렉트한다
        )
        return r.json()

    def _ensure_token(self) -> None:
        if self._token:
            return
        d = self._call(
            "auth/authentication.json",
            consumer_key=self._key,
            consumer_secret=self._secret,
        )
        self._token = d["result"]["accessToken"]

    def region_profile(self, address: str) -> dict[str, Any] | None:
        """주소 → 그 동네의 인구/상권 요약 딕셔너리. 못 구하면 None."""
        self._ensure_token()
        geo = self._call("addr/geocode.json", accessToken=self._token, address=address, resultcount=1)
        rows = geo.get("result", {}).get("resultdata") or []
        if not rows:
            return None
        row = rows[0]
        adm_cd = row.get("adm_cd")
        if not adm_cd or adm_cd == "null":
            small = self._call(
                "personal/findcodeinsmallarea.json",
                accessToken=self._token,
                x_coor=row.get("x"),
                y_coor=row.get("y"),
            )
            adm_cd = small.get("result", {}).get("emdong_cd")
        if not adm_cd:
            return None
        ppl_list = self._call("startupbiz/pplsummary.json", accessToken=self._token, adm_cd=adm_cd).get("result") or []
        region_list = self._call("startupbiz/regiontotal.json", accessToken=self._token, adm_cd=adm_cd).get("result") or []
        ppl = ppl_list[0] if ppl_list else {}
        # regiontotal은 [시도, 해당 동]을 준다. adm_cd가 일치하는 동을 고른다.
        region = next((x for x in region_list if x.get("adm_cd") == adm_cd), region_list[-1] if region_list else {})
        return {"dong": ppl.get("adm_nm") or row.get("adm_nm"), "ppl": ppl, "region": region}


def build_sgis_client(settings: Settings) -> SgisClient | None:
    """설정에 SGIS 키가 있으면 클라이언트를, 없으면 None을 준다."""
    if not settings.sgis_consumer_key or not settings.sgis_consumer_secret:
        return None
    return SgisClient(settings.sgis_consumer_key, settings.sgis_consumer_secret)


def format_profile(data: dict[str, Any]) -> str:
    """SGIS 요약 딕셔너리를 프롬프트에 넣을 한 줄 상권 프로필로 만든다."""
    ppl = data.get("ppl", {})
    region = data.get("region", {})
    ages = [(label, ppl.get(field)) for field, label in _AGE_FIELDS if ppl.get(field)]
    top_ages = sorted(ages, key=lambda x: float(x[1]), reverse=True)[:3]
    age_str = ", ".join(f"{label} {v}%" for label, v in top_ages) or "정보 없음"
    dong = data.get("dong", "")
    return (
        f"{dong} 상권 통계 — 연령 상위: {age_str}; "
        f"상대지수(1~9, 높을수록 그 특성 강함): "
        f"직장인구 {region.get('job_ppltn_per')}, 거주인구 {region.get('resid_ppltn_per')}, "
        f"아파트 {region.get('apart_per')}, 1인가구 {region.get('one_person_family_per')}, "
        f"20대 {region.get('twenty_ppltn_per')}"
    )


class StoreContextProvider:
    """매장별 상권 프로필 문자열을 제공한다(캐시). 실패/미설정 시 None."""

    def __init__(
        self,
        client: SgisClient | None = None,
        addresses: dict[str, str] | None = None,
    ) -> None:
        self._client = client
        self._addresses = addresses if addresses is not None else STORE_ADDRESSES
        self._cache: dict[str, str | None] = {}

    def profile_text(self, store_id: str) -> str | None:
        if self._client is None:
            return None
        if store_id in self._cache:
            return self._cache[store_id]
        text: str | None = None
        address = self._addresses.get(store_id)
        if address:
            try:
                data = self._client.region_profile(address)
                if data:
                    text = format_profile(data)
            except Exception:
                # 상권 조회 실패는 인사이트를 막지 않는다. 시간대만으로 추정하면 된다.
                logger.warning("SGIS 상권 조회 실패 store=%s", store_id, exc_info=True)
        self._cache[store_id] = text
        return text

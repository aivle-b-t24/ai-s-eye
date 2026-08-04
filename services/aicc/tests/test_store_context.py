"""매장 상권 맥락(StoreContextProvider) 테스트 — 실제 SGIS 없이 가짜 클라이언트로."""

from typing import Any

from aicc.store_context import StoreContextProvider, format_profile

SAMPLE = {
    "dong": "동명동",
    "ppl": {"twenty_per": "27.08", "forty_per": "9.09", "fifty_per": "12.82"},
    "region": {
        "job_ppltn_per": "6", "resid_ppltn_per": "4", "apart_per": "1",
        "one_person_family_per": "8", "twenty_ppltn_per": "6",
    },
}


class FakeClient:
    def __init__(self, data: Any) -> None:
        self._data = data
        self.calls = 0

    def region_profile(self, address: str) -> Any:
        self.calls += 1
        return self._data


def test_format_profile_has_age_and_index() -> None:
    text = format_profile(SAMPLE)
    assert "동명동" in text
    assert "20대 27.08%" in text  # 연령 상위
    assert "직장인구 6" in text  # 상대지수


def test_profile_text_uses_client() -> None:
    p = StoreContextProvider(FakeClient(SAMPLE), {"store-001": "광주 동명동"})
    assert "동명동" in (p.profile_text("store-001") or "")


def test_no_client_returns_none() -> None:
    assert StoreContextProvider(None).profile_text("store-001") is None


def test_unknown_store_returns_none() -> None:
    p = StoreContextProvider(FakeClient(SAMPLE), {"store-001": "주소"})
    assert p.profile_text("store-999") is None


def test_result_is_cached() -> None:
    c = FakeClient(SAMPLE)
    p = StoreContextProvider(c, {"store-001": "주소"})
    p.profile_text("store-001")
    p.profile_text("store-001")
    assert c.calls == 1  # 두 번 물어도 SGIS는 한 번만


def test_client_error_returns_none() -> None:
    class Boom:
        def region_profile(self, address: str) -> Any:
            raise RuntimeError("SGIS 다운")

    p = StoreContextProvider(Boom(), {"store-001": "주소"})
    assert p.profile_text("store-001") is None  # 실패해도 안 죽고 None

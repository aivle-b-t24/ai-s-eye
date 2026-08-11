"""집계 결과 → Gemini 분석 → 슈퍼바이저용 인사이트.

이슈 #53: #52 집계 API 응답(GET /api/stores/summary)을 입력으로 받아,
매장별 특이사항·근거·권장사항과 두 매장 비교를 Gemini로 생성한다.

핵심 규칙:
- 집계에 있는 숫자만 근거로 삼고, 없는 사실은 지어내지 않는다.
- 시간은 한국시간(KST)으로 환산해 판단한다(집계는 UTC로 온다).
- expected_insights(정답)는 입력에 넣지 않는다. 결과 확인용일 뿐이다.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import get_settings
from .store_context import StoreContextProvider, build_sgis_client

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


class InsightsUnavailableError(RuntimeError):
    """Gemini를 쓸 수 없을 때."""


SYSTEM_PROMPT = """너는 프랜차이즈 본사의 운영 분석가다.

규칙:
- 아래 '집계 데이터'에 있는 숫자만 근거로 분석한다. 데이터에 없는 사실·수치는 절대 지어내지 않는다.
- 매장을 문장에서 부를 때는 store_id(예: store-001) 또는 상권 정보에 나온 '동 이름'(예: 동명동)만 쓴다.
  '강남점'·'홍대점'처럼 주어지지 않은 지점명은 절대 지어내지 않는다.
- 동 이름은 그 매장의 '상권' 줄에 적힌 이름을 글자 그대로만 쓴다. 다른 동네 이름(예: 신림동)으로 바꾸거나
  추측하지 않는다. 상권 줄이 없으면 동 이름을 아예 쓰지 않고 store_id로만 부른다.
- 모든 시간은 한국시간(KST) 기준이다.
- 각 매장에서 가장 두드러진 특이사항 하나를 찾는다. 점심(11~14시) 인원·대기 급증은 congestion,
  오후(14~17시) 방문·주문 증가는 afternoon_demand, 영상 이상은 video_issue로 분류한다.
- 근거(evidence)에는 판단에 쓴 실제 숫자(피크 인원·대기, 피크 시각, 주문 수 등)만 담는다.
  상권 정보·동 이름·설명 같은 텍스트는 evidence에 넣지 않는다(상권은 probable_cause에서만 다룬다).
- 주문 데이터 출처가 synthetic_order_simulator이면 합성 데모 수치로 취급하고 실제 POS 실적이라고 표현하지 않는다.
- '데이터 없음'으로 표시된 항목은 운영 이상으로 해석하지 않는다. 데이터가 있는 항목만 분석한다.
- 선택 매장이 2곳 이상이면 차이를 비교하고, 1곳이면 해당 매장의 종합 의견을 comparison에 담는다.
  운영자가 참고할 권장사항을 매장별·비교별로 만든다.
- 반드시 아래 JSON 형식만 출력한다. 다른 말은 하지 않는다.

분석 품질 규칙:
- 너는 10년차 프랜차이즈 운영 컨설턴트다. 숫자 뒤의 '왜'와 '그래서 무엇을'까지 짚는다.
- 심각도(severity)는 피크 대기 인원 기준으로 정한다: 8명 이상=high, 4~7명=medium, 3명 이하=low.
  단 영상 이상(video_issue)은 이상 건수와 상태를 보고 판단한다.
- summary에는 반드시 실제 숫자(피크 인원·대기, 시각)를 넣는다. "많았다"처럼 두루뭉술한 표현은 금지한다.
- 평균과 피크를 비교해 평소 대비 얼마나 몰렸는지 짚되, 배수(N배) 표현은 평균이 3명 이상일 때만 쓴다.
  평균이 3명 미만이면 배수 대신 "평소 거의 없다가 6명으로 몰렸다"처럼 실제 숫자로 설명한다.
- recommendation은 '언제, 무엇을' 하라는 구체적 행동으로 쓴다.
- 예시) 나쁨: "인원이 많았습니다" / 좋음: "점심 피크(12시) 대기 9명으로 평균(3명)의 3배였습니다"

추정 원인(probable_cause) 규칙 — 이 특이사항이 왜 생겼는지에 대한 '가설'을 쓴다:
- 근거는 '시간대'·집계 숫자, 그리고 매장에 '상권' 정보가 주어지면 그 상권 통계(SGIS 인구·상권 지수)다.
  상권 통계가 있으면 그 연령 구성·직장인구/거주인구·아파트 비율을 근거로 "어떤 손님이 왜 오는지"를 추정한다.
- 상권 통계에 없는 구체 사실(특정 회사명·건물명 등)은 지어내지 않는다. 통계로 뒷받침되는 범위에서만 추정한다.
- 반드시 "추정"이라는 단어를 넣고, "~로 추정됩니다 / ~일 가능성이 있습니다" 같은 가설 어투로만 쓴다.
- 시간대 의미 + 상권을 함께 본다: 점심(11~14시)/오후(14~17시)/저녁(17시~) 급증에, 상권의 연령·직장/거주 특성을 더한다.
  상권 통계가 없으면 시간대만으로 추정한다. 특이 시간대가 아니면 무리해서 이유를 만들지 않는다.
- 예시) 좋음: "동명동은 20대·직장인구 비중이 높은 도심 상권으로, 점심(12시) 급증은 인근 직장인 점심 수요일 가능성이 있습니다(추정)."
        나쁨: "옆 건물 대기업 직원들이 옵니다."(상권 통계에 없는 특정 사실 → 지어냄, 금지)

출력 JSON 형식:
{
  "insights": [
    {
      "store_id": "store-001",
      "insight_type": "congestion | afternoon_demand | video_issue",
      "severity": "high | medium | low | info",
      "summary": "한국어 한두 문장",
      "probable_cause": "왜 그런지에 대한 추정(가설). 시간대·숫자 근거로만, '추정' 표기 필수",
      "evidence": { "근거 필드": 숫자 },
      "recommendation": "한국어 권장사항"
    }
  ],
  "comparison": {
    "summary": "두 매장 차이 한국어 요약",
    "recommendation": "비교 기반 권장사항"
  }
}"""


def _to_kst(iso: Any) -> str:
    """UTC ISO 시각을 한국시간 문자열로. 형식이 이상하면 원본 그대로 돌려준다."""
    if not isinstance(iso, str):
        return str(iso)
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")


def build_client() -> Any | None:
    """Vertex(사내 크레딧) 또는 API 키로 Gemini 클라이언트를 만든다. agent.py와 같은 방식."""
    try:
        from google import genai
    except ImportError:
        return None
    settings = get_settings()
    if settings.use_vertex:
        try:
            return genai.Client(
                vertexai=True,
                project=settings.vertex_project,
                location=settings.vertex_location,
            )
        except Exception:
            # 연결 실패해도 호출한 쪽이 오류 응답으로 처리한다. 원인은 로그로 남긴다.
            logger.warning("Vertex Gemini 클라이언트 생성 실패", exc_info=True)
            return None
    if not settings.gemini_api_key:
        return None
    return genai.Client(api_key=settings.gemini_api_key)


def _summary_section(value: Any) -> dict[str, Any]:
    """null 또는 잘못된 형식의 집계 섹션을 빈 딕셔너리로 정규화한다."""
    return value if isinstance(value, dict) else {}


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _has_order_data(orders: dict[str, Any]) -> bool:
    status_counts = _summary_section(orders.get("latest_status_counts"))
    return any(
        (
            _positive_number(orders.get("total_order_count")),
            _positive_number(orders.get("order_event_count")),
            bool(orders.get("data_sources")),
            bool(orders.get("top_menu_items")),
            any(_positive_number(count) for count in status_counts.values()),
        )
    )


def _has_analysis_data(store: Any) -> bool:
    """매장에 AI가 분석할 수 있는 집계 섹션이 하나라도 있는지 확인한다."""
    if not isinstance(store, dict):
        return False
    traffic = _summary_section(store.get("traffic_summary"))
    orders = _summary_section(store.get("order_summary"))
    video = _summary_section(store.get("video_summary"))
    return bool(traffic) or _has_order_data(orders) or bool(video)


def build_prompt(summary: Any, profiles: dict[str, str] | None = None) -> str:
    """집계 데이터를 사람이 읽는 숫자 목록으로 바꿔 프롬프트를 만든다.

    profiles로 매장별 상권 프로필(SGIS)을 주면 각 매장 아래에 함께 넣는다.
    시각은 KST로 환산한다. expected_insights 같은 정답 필드는 넣지 않는다
    (애초에 집계 데이터에 없다).
    """
    profiles = profiles or {}
    lines: list[str] = ["집계 데이터 (기간별, 시간은 KST):"]
    for store in summary.get("stores", []):
        if not isinstance(store, dict):
            continue
        sid = store.get("store_id")
        t = _summary_section(store.get("traffic_summary"))
        o = _summary_section(store.get("order_summary"))
        v = _summary_section(store.get("video_summary"))
        lines.append(f"\n[{sid}]")
        if t:
            lines.append(
                f"  인원: 평균 {t.get('average_visible_person_count')}, "
                f"피크 {t.get('peak_visible_person_count')} "
                f"({_to_kst(t.get('peak_visible_person_count_at'))})"
            )
            lines.append(
                f"  대기: 평균 {t.get('average_queue_count_estimate')}, "
                f"피크 {t.get('peak_queue_count_estimate')} "
                f"({_to_kst(t.get('peak_queue_count_estimate_at'))})"
            )
        else:
            lines.append("  인원·대기: 데이터 없음")

        if _has_order_data(o):
            lines.append(
                f"  주문: 총 {o.get('total_order_count')}건, 상태 {o.get('latest_status_counts')}"
            )
            raw_data_sources = o.get("data_sources")
            data_sources = raw_data_sources if isinstance(raw_data_sources, list) else []
            if data_sources:
                lines.append(f"  주문 데이터 출처: {', '.join(map(str, data_sources))}")
            raw_top_menu_items = o.get("top_menu_items")
            top_menu_items = raw_top_menu_items if isinstance(raw_top_menu_items, list) else []
            tops = ", ".join(
                f"{m.get('name')}x{m.get('quantity')}"
                for m in top_menu_items[:5]
                if isinstance(m, dict)
            )
            if tops:
                lines.append(f"  인기메뉴: {tops}")
        else:
            lines.append("  주문: 데이터 없음")

        if v:
            lines.append(
                f"  영상: {v.get('latest_quality_status')}, 이상 {v.get('quality_issue_count')}건"
            )
        else:
            lines.append("  영상: 데이터 없음")
        prof = profiles.get(sid)
        if prof:
            lines.append(f"  상권: {prof}")
    return "\n".join(lines)


# 관리자가 JSON 대신 바로 읽는 문장(display_text)에 쓰는 표시용 라벨.
INSIGHT_TYPE_LABEL = {
    "congestion": "혼잡",
    "afternoon_demand": "오후 수요 증가",
    "video_issue": "영상 이상",
}
SEVERITY_LABEL = {"high": "높음", "medium": "보통", "low": "낮음", "info": "참고"}
SEVERITY_EMOJI = {"high": "🔴", "medium": "🟠", "low": "🟡", "info": "ℹ️"}


def _insight_display_text(insight: dict[str, Any], store_name: str | None = None) -> str:
    """인사이트 하나를 관리자가 바로 읽는 한 문단으로 만든다."""
    store = store_name or insight.get("store_id", "")
    itype = insight.get("insight_type")
    type_label = INSIGHT_TYPE_LABEL.get(itype, itype or "특이사항")
    sev = insight.get("severity")
    sev_label = SEVERITY_LABEL.get(sev, sev or "")
    emoji = SEVERITY_EMOJI.get(sev, "📊")

    header = f"{emoji} {store} — {type_label}"
    if sev_label:
        header += f" ({sev_label})"
    # summary(무슨 일) → probable_cause(왜, 추정) → recommendation(그래서 무엇을) 순으로 읽히게 잇는다.
    body = " ".join(
        part
        for part in (
            insight.get("summary"),
            insight.get("probable_cause"),
            insight.get("recommendation"),
        )
        if part
    )
    return f"{header}\n{body}" if body else header


def attach_display_text(
    result: dict[str, Any],
    store_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """인사이트/비교 각 항목에 사람이 읽는 display_text를 붙인다.

    store_names로 store_id -> 매장명을 주면 이름을 쓰고, 없으면 store_id를 쓴다.
    기존 필드는 그대로 두고 새 필드만 추가하므로 대시보드가 쓰는 형식은 안 깨진다.
    """
    names = store_names or {}
    for insight in result.get("insights", []):
        if isinstance(insight, dict):
            insight["display_text"] = _insight_display_text(
                insight, names.get(insight.get("store_id"))
            )
    comparison = result.get("comparison")
    if isinstance(comparison, dict):
        body = " ".join(
            part
            for part in (comparison.get("summary"), comparison.get("recommendation"))
            if part
        )
        comparison["display_text"] = f"📊 매장 비교\n{body}" if body else "📊 매장 비교"
    return result


def _severity_for_peak_wait(peak_wait: float) -> str:
    if peak_wait >= 8:
        return "high"
    if peak_wait >= 4:
        return "medium"
    if peak_wait > 0:
        return "low"
    return "info"


def _number(value: Any, default: float = 0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def build_rule_based_insights(summary: Any) -> dict[str, Any]:
    """Gemini 장애 시 집계에 있는 수치만 사용해 최소 운영 분석을 만든다.

    원인을 생성하지 않고 관측 사실과 추가 확인 항목만 제시한다. 따라서 429 같은
    외부 모델 장애가 발생해도 본사 화면이 빈 오류로 끝나지 않는다.
    """
    if not isinstance(summary, dict) or not isinstance(summary.get("stores"), list):
        raise InsightsUnavailableError("집계 응답 형식이 올바르지 않습니다(stores 목록 없음).")

    stores = [store for store in summary["stores"] if _has_analysis_data(store)]
    if not stores:
        raise InsightsUnavailableError(
            "선택한 기간에 분석할 매장 데이터가 없습니다. 다른 기간을 선택해 주세요."
        )

    insights: list[dict[str, Any]] = []
    queue_comparison: list[tuple[str, float]] = []
    for store in stores:
        sid = str(store.get("store_id") or "unknown-store")
        traffic = _summary_section(store.get("traffic_summary"))
        orders = _summary_section(store.get("order_summary"))
        video = _summary_section(store.get("video_summary"))
        issue_count = int(_number(video.get("quality_issue_count")))

        if issue_count > 0 or (
            video and video.get("latest_quality_status") not in {None, "normal"}
        ):
            insights.append(
                {
                    "store_id": sid,
                    "insight_type": "video_issue",
                    "severity": "medium",
                    "summary": (
                        f"선택 기간에 영상 품질 이상 {issue_count}건이 집계됐으며 "
                        f"최신 상태는 {video.get('latest_quality_status')}입니다."
                    ),
                    "probable_cause": (
                        "집계 수치만으로 영상 이상 원인을 특정할 수 없습니다(추정 제한)."
                    ),
                    "evidence": {
                        "quality_issue_count": issue_count,
                        "latest_quality_status": video.get("latest_quality_status"),
                    },
                    "recommendation": "해당 시각의 원본 영상과 카메라 연결 상태를 확인하세요.",
                }
            )
            continue

        if traffic:
            average_wait = _number(traffic.get("average_queue_count_estimate"))
            peak_wait = _number(traffic.get("peak_queue_count_estimate"))
            peak_at = traffic.get("peak_queue_count_estimate_at")
            queue_comparison.append((sid, peak_wait))
            insight_type = "congestion" if peak_wait >= 4 else "operating_status"
            insights.append(
                {
                    "store_id": sid,
                    "insight_type": insight_type,
                    "severity": _severity_for_peak_wait(peak_wait),
                    "summary": (
                        f"최대 대기 인원은 {peak_wait:g}명"
                        f"({_to_kst(peak_at)})이며 평균은 {average_wait:g}명입니다."
                    ),
                    "probable_cause": (
                        "현재 집계만으로 원인을 특정할 수 없으며 피크 전후 추이와 "
                        "반복 여부를 추가 확인해야 합니다(추정 제한)."
                    ),
                    "evidence": {
                        "average_queue_count_estimate": average_wait,
                        "peak_queue_count_estimate": peak_wait,
                        "peak_queue_count_estimate_at": peak_at,
                    },
                    "recommendation": (
                        "피크 전후 시간대의 주문·인원 추이를 확인한 뒤 인력 조정 여부를 "
                        "What-if 시뮬레이션으로 검토하세요."
                    ),
                }
            )
            continue

        total_orders = int(_number(orders.get("total_order_count")))
        insights.append(
            {
                "store_id": sid,
                "insight_type": "order_activity",
                "severity": "info",
                "summary": f"선택 기간에 주문 {total_orders}건이 집계됐습니다.",
                "probable_cause": (
                    "인원·대기 데이터가 없어 주문량 변화의 원인을 특정할 수 없습니다(추정 제한)."
                ),
                "evidence": {"total_order_count": total_orders},
                "recommendation": "시간대별 주문 추이와 Vision 데이터가 함께 수집되는지 확인하세요.",
            }
        )

    if len(queue_comparison) >= 2:
        queue_text = ", ".join(
            f"{store_id} {peak_wait:g}명" for store_id, peak_wait in queue_comparison
        )
        comparison_summary = f"선택 매장의 최대 대기는 {queue_text}으로 집계됐습니다."
        comparison_recommendation = (
            "동일한 수집 기간과 데이터량인지 확인한 뒤 피크가 반복되는 매장을 우선 검토하세요."
        )
    else:
        comparison_summary = "선택 매장의 집계 수치를 규칙 기반으로 확인했습니다."
        comparison_recommendation = (
            "AI 생성 분석이 복구되면 상권 맥락을 포함한 추가 진단을 다시 실행할 수 있습니다."
        )

    return attach_display_text(
        {
            "insights": insights,
            "comparison": {
                "summary": comparison_summary,
                "recommendation": comparison_recommendation,
            },
        }
    )


def generate_insights(
    summary: Any,
    client: Any | None = None,
    context_provider: StoreContextProvider | None = None,
) -> dict[str, Any]:
    """집계 데이터를 Gemini로 분석해 인사이트를 돌려준다.

    context_provider가 있으면(또는 SGIS 키가 설정돼 있으면) 매장별 상권 프로필을 함께 넣어
    추정 원인을 상권 통계로 뒷받침한다. 상권을 못 구하면 시간대만으로 추정한다.
    반환: {"insights": [...], "comparison": {...}}. 각 항목에 사람이 읽는 display_text 포함.
    집계 형식이 이상하거나 Gemini를 못 쓰면 InsightsUnavailableError를 던진다.
    """
    # 집계 응답이 예상 형식(딕셔너리 + stores 리스트)인지 먼저 확인한다.
    # 공통 API가 오류를 200으로 주거나 형식을 바꿔도 500으로 터지지 않게 막는다.
    if not isinstance(summary, dict) or not isinstance(summary.get("stores"), list):
        raise InsightsUnavailableError("집계 응답 형식이 올바르지 않습니다(stores 목록 없음).")

    # 데이터가 아예 없으면(예: 선택 기간에 집계된 매장 0개) Gemini를 부르지 않는다.
    # 빈 입력으로 부르면 모델이 매장·수치·상권을 통째로 지어내므로, 명확히 '데이터 없음'을 알린다.
    if not summary.get("stores"):
        raise InsightsUnavailableError(
            "선택한 기간에 분석할 매장 데이터가 없습니다. 다른 기간(최근 7일·30일)을 선택해 주세요."
        )

    # 신규 계정처럼 매장 행만 있고 세 집계가 모두 null인 항목은 Gemini 입력에서 제외한다.
    # 일부 섹션만 있는 매장은 남겨서, 존재하는 운영 데이터만으로 분석할 수 있게 한다.
    analyzable_stores = [store for store in summary["stores"] if _has_analysis_data(store)]
    if not analyzable_stores:
        raise InsightsUnavailableError(
            "선택한 기간에 분석할 매장 데이터가 없습니다. 다른 기간(최근 7일·30일)을 선택해 주세요."
        )
    analysis_summary = {**summary, "stores": analyzable_stores}

    client = client if client is not None else build_client()
    if client is None:
        raise InsightsUnavailableError("Gemini 클라이언트를 만들지 못했습니다.")

    from google.genai import types

    # 매장별 상권 프로필(SGIS). 실패/미설정이면 빈 dict → 상권 없이 진행.
    provider = context_provider or StoreContextProvider(build_sgis_client(get_settings()))
    profiles: dict[str, str] = {}
    for store in analyzable_stores:
        sid = store.get("store_id")
        if sid:
            text = provider.profile_text(sid)
            if text:
                profiles[sid] = text

    prompt = build_prompt(analysis_summary, profiles)
    try:
        response = client.models.generate_content(
            model=get_settings().gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,  # 분석은 창의성보다 일관성이 중요해 낮게 둔다
            ),
        )
    except Exception as exc:
        raise InsightsUnavailableError(f"{type(exc).__name__}: {exc}") from exc

    text = (response.text or "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InsightsUnavailableError(f"Gemini 응답이 JSON이 아닙니다: {text[:100]}") from exc
    if not isinstance(data, dict) or "insights" not in data:
        raise InsightsUnavailableError("Gemini 응답에 insights가 없습니다.")
    return attach_display_text(data)

"""집계 결과 → Gemini 분석 → 슈퍼바이저용 인사이트.

이슈 #53: #52 집계 API 응답(GET /api/stores/summary)을 입력으로 받아,
매장별 특이사항·근거·권장사항과 두 매장 비교를 Gemini로 생성한다.

핵심 규칙:
- 집계에 있는 숫자만 근거로 삼고, 없는 사실은 지어내지 않는다.
- 시간은 한국시간(KST)으로 환산해 판단한다(집계는 UTC로 온다).
- expected_insights(정답)는 입력에 넣지 않는다. 결과 확인용일 뿐이다.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import get_settings


KST = timezone(timedelta(hours=9))


class InsightsUnavailableError(RuntimeError):
    """Gemini를 쓸 수 없을 때."""


SYSTEM_PROMPT = """너는 프랜차이즈 본사의 운영 분석가다.

규칙:
- 아래 '집계 데이터'에 있는 숫자만 근거로 분석한다. 데이터에 없는 사실·수치는 절대 지어내지 않는다.
- 모든 시간은 한국시간(KST) 기준이다.
- 각 매장에서 가장 두드러진 특이사항 하나를 찾는다. 점심(11~14시) 인원·대기 급증은 congestion,
  오후(14~17시) 방문·주문 증가는 afternoon_demand, 영상 이상은 video_issue로 분류한다.
- 근거(evidence)에는 판단에 쓴 실제 숫자(피크 인원·대기, 피크 시각, 주문 수 등)를 담는다.
- 두 매장의 차이를 비교하고, 운영자가 참고할 권장사항을 매장별·비교별로 만든다.
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

출력 JSON 형식:
{
  "insights": [
    {
      "store_id": "store-001",
      "insight_type": "congestion | afternoon_demand | video_issue",
      "severity": "high | medium | low | info",
      "summary": "한국어 한두 문장",
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
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


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
            return None
    if not settings.gemini_api_key:
        return None
    return genai.Client(api_key=settings.gemini_api_key)


def build_prompt(summary: Any) -> str:
    """집계 데이터를 사람이 읽는 숫자 목록으로 바꿔 프롬프트를 만든다.

    시각은 KST로 환산한다. expected_insights 같은 정답 필드는 넣지 않는다
    (애초에 집계 데이터에 없다).
    """
    lines: list[str] = ["집계 데이터 (기간별, 시간은 KST):"]
    for store in summary.get("stores", []):
        sid = store.get("store_id")
        t = store.get("traffic_summary", {})
        o = store.get("order_summary", {})
        v = store.get("video_summary", {})
        lines.append(f"\n[{sid}]")
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
        lines.append(
            f"  주문: 총 {o.get('total_order_count')}건, 상태 {o.get('latest_status_counts')}"
        )
        tops = ", ".join(
            f"{m.get('name')}x{m.get('quantity')}" for m in o.get("top_menu_items", [])[:5]
        )
        if tops:
            lines.append(f"  인기메뉴: {tops}")
        lines.append(
            f"  영상: {v.get('latest_quality_status')}, 이상 {v.get('quality_issue_count')}건"
        )
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
    body = " ".join(
        part for part in (insight.get("summary"), insight.get("recommendation")) if part
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


def generate_insights(summary: Any, client: Any | None = None) -> dict[str, Any]:
    """집계 데이터를 Gemini로 분석해 인사이트를 돌려준다.

    반환: {"insights": [...], "comparison": {...}}. 각 항목에 사람이 읽는 display_text 포함.
    집계 형식이 이상하거나 Gemini를 못 쓰면 InsightsUnavailableError를 던진다.
    """
    # 집계 응답이 예상 형식(딕셔너리 + stores 리스트)인지 먼저 확인한다.
    # 공통 API가 오류를 200으로 주거나 형식을 바꿔도 500으로 터지지 않게 막는다.
    if not isinstance(summary, dict) or not isinstance(summary.get("stores"), list):
        raise InsightsUnavailableError("집계 응답 형식이 올바르지 않습니다(stores 목록 없음).")

    client = client if client is not None else build_client()
    if client is None:
        raise InsightsUnavailableError("Gemini 클라이언트를 만들지 못했습니다.")

    from google.genai import types

    prompt = build_prompt(summary)
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

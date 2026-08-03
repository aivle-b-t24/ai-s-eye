from typing import Any

from aicc.franchise_insights import attach_display_text


def sample_result() -> dict[str, Any]:
    return {
        "insights": [
            {
                "store_id": "store-001",
                "insight_type": "congestion",
                "severity": "high",
                "summary": "점심에 인원과 대기가 급증했습니다.",
                "probable_cause": "인근 직장인의 점심 수요일 가능성이 있습니다(추정).",
                "evidence": {"peak_visible_person_count": 28},
                "recommendation": "점심 전 인력을 늘리세요.",
            },
            {
                "store_id": "store-002",
                "insight_type": "afternoon_demand",
                "severity": "medium",
                "summary": "오후에 방문이 늘었습니다.",
                "recommendation": "베이커리를 보충하세요.",
            },
        ],
        "comparison": {"summary": "001 점심, 002 오후.", "recommendation": "매장별 운영."},
    }


def test_display_text_added_to_each_insight() -> None:
    result = attach_display_text(sample_result())
    for ins in result["insights"]:
        assert ins.get("display_text")  # 비어있지 않다


def test_display_text_is_readable() -> None:
    result = attach_display_text(sample_result())
    dt = result["insights"][0]["display_text"]
    assert "혼잡" in dt  # congestion -> 한국어 라벨
    assert "높음" in dt  # high -> 한국어
    assert "점심에 인원과 대기가 급증했습니다." in dt  # summary 포함
    assert "인력을 늘리세요" in dt  # recommendation 포함


def test_probable_cause_in_display_text() -> None:
    """추정 원인(왜)이 display_text에 들어간다."""
    result = attach_display_text(sample_result())
    dt = result["insights"][0]["display_text"]
    assert "추정" in dt  # 가설 표기가 보인다
    assert "직장인의 점심 수요" in dt  # probable_cause 내용 포함


def test_store_name_used_when_provided() -> None:
    result = attach_display_text(sample_result(), store_names={"store-001": "동명점"})
    assert "동명점" in result["insights"][0]["display_text"]


def test_store_id_used_when_no_name() -> None:
    result = attach_display_text(sample_result())
    assert "store-001" in result["insights"][0]["display_text"]


def test_comparison_gets_display_text() -> None:
    result = attach_display_text(sample_result())
    assert "매장 비교" in result["comparison"]["display_text"]


def test_original_fields_preserved() -> None:
    """기존 필드(대시보드가 쓰는)는 그대로 있어야 한다."""
    result = attach_display_text(sample_result())
    ins = result["insights"][0]
    assert ins["store_id"] == "store-001"
    assert ins["insight_type"] == "congestion"
    assert ins["evidence"] == {"peak_visible_person_count": 28}


def test_handles_missing_fields() -> None:
    """일부 필드가 없어도 터지지 않는다."""
    result = attach_display_text({"insights": [{"store_id": "store-009"}], "comparison": {}})
    assert result["insights"][0]["display_text"]  # store_id만 있어도 문장 나옴

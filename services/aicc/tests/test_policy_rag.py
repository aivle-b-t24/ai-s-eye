"""정책 RAG(PolicyRetriever) 테스트 — 실제 Vertex 없이 가짜 임베딩으로 검증한다."""

from typing import Any

from aicc.policy_rag import PolicyRetriever

# 키워드별로 정해둔 벡터. 같은 키워드끼리 코사인 유사도가 1이 되게 한다.
_KEYWORD_VECTORS = {
    "주차": [1.0, 0.0, 0.0],
    "와이파이": [0.0, 1.0, 0.0],
    "반려동물": [0.0, 0.0, 1.0],
}


def fake_embed(texts: list[str]) -> list[list[float]]:
    """텍스트에 든 키워드로 벡터를 정한다. 실제 임베딩 대역."""
    vectors: list[list[float]] = []
    for text in texts:
        vec = [0.1, 0.1, 0.1]
        for keyword, kv in _KEYWORD_VECTORS.items():
            if keyword in text:
                vec = kv
                break
        vectors.append(vec)
    return vectors


def policies() -> list[dict[str, Any]]:
    return [
        {"policy_id": "p1", "title": "주차", "content": "주차 불가, 공영주차장 이용"},
        {"policy_id": "p2", "title": "와이파이", "content": "주문 고객에게 제공"},
        {"policy_id": "p3", "title": "반려동물 출입", "content": "안내견만 가능"},
        {"policy_id": "p4", "title": "흡연", "content": "전 구역 금연"},
    ]


def test_retrieve_keeps_only_clearly_relevant() -> None:
    """단일 주제 질문이면 최고 점수와 margin 이상 벌어진 정책은 걸러 낸다."""
    r = PolicyRetriever(embed=fake_embed, top_k=2)
    result = r.retrieve(policies(), "주차 되나요?", "store-001")
    # 주차만 뚜렷이 관련(코사인 1.0), 나머지는 훨씬 낮아 margin 밖 → 주차 1개만
    assert [p["title"] for p in result] == ["주차"]


def test_retrieve_keeps_multiple_when_scores_close() -> None:
    """점수가 margin 이내로 가까우면(여러 주제/유사 정책) top_k까지 남긴다."""
    same = lambda texts: [[1.0, 0.0, 0.0] for _ in texts]  # 전부 동점(코사인 1.0)
    r = PolicyRetriever(embed=same, top_k=2)
    result = r.retrieve(policies(), "주차랑 와이파이 돼?", "store-001")
    assert len(result) == 2  # 동점이라 top_k(2)까지 유지


def test_retrieve_returns_all_when_no_embedder() -> None:
    r = PolicyRetriever(embed=None, top_k=2)
    result = r.retrieve(policies(), "주차 되나요?", "store-001")
    assert len(result) == 4  # 임베딩 없으면 전체 반환


def test_retrieve_returns_all_when_no_query() -> None:
    r = PolicyRetriever(embed=fake_embed, top_k=2)
    assert len(r.retrieve(policies(), None)) == 4
    assert len(r.retrieve(policies(), "   ")) == 4  # 공백만도 전체


def test_retrieve_returns_all_when_few_policies() -> None:
    r = PolicyRetriever(embed=fake_embed, top_k=5)
    result = r.retrieve(policies(), "주차 되나요?")
    assert len(result) == 4  # 정책이 top_k 이하이면 그대로


def test_retrieve_falls_back_on_embed_error() -> None:
    def boom(_: list[str]) -> list[list[float]]:
        raise RuntimeError("임베딩 실패")

    r = PolicyRetriever(embed=boom, top_k=2)
    result = r.retrieve(policies(), "주차 되나요?", "store-001")
    assert len(result) == 4  # 실패해도 전체 반환(챗봇 안 죽음)


def test_policy_vectors_are_cached() -> None:
    """같은 매장·같은 정책이면 정책은 다시 임베딩하지 않는다(질문만 매번 임베딩)."""
    calls: list[int] = []

    def counting_embed(texts: list[str]) -> list[list[float]]:
        calls.append(len(texts))
        return fake_embed(texts)

    r = PolicyRetriever(embed=counting_embed, top_k=2)
    r.retrieve(policies(), "주차 되나요?", "store-001")
    r.retrieve(policies(), "와이파이 있어요?", "store-001")
    # 정책 임베딩(4개짜리 호출)은 딱 1번, 질문 임베딩(1개짜리)은 2번이어야 한다.
    batch_calls = [n for n in calls if n == len(policies())]
    assert len(batch_calls) == 1

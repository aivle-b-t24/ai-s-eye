"""정책 RAG(검색 증강) — 질문과 관련된 정책만 골라준다.

챗봇이 정책 질문을 받으면, 매장 정책 전체(수십 개)를 Gemini에 통째로 넘기지 않고
질문과 의미가 가까운 상위 몇 개만 골라 넘긴다. 그래야 "정책 다 알려줘"에 전부 나열하지 않고,
관련된 답만 정확히 준다.

동작:
- 정책 텍스트(제목+내용)와 질문을 각각 벡터로 바꾼다(Vertex 임베딩).
- 코사인 유사도가 높은 상위 top_k개를 고른다.
- 임베딩을 못 쓰거나 정책이 top_k 이하이면, 그냥 전체를 그대로 돌려준다(안전망).
"""

import logging
import math
from typing import Any, Callable

from .config import Settings

logger = logging.getLogger(__name__)

# 질문·정책을 벡터로 바꾸는 함수 타입. 문자열 목록 → 벡터(실수 목록) 목록.
Embedder = Callable[[list[str]], list[list[float]]]


def build_embedder(settings: Settings) -> Embedder | None:
    """Vertex 임베딩으로 텍스트를 벡터로 바꾸는 함수를 만든다. 못 만들면 None.

    None이면 RAG는 자동으로 '전체 반환'으로 물러난다(챗봇은 계속 동작).
    """
    try:
        from google import genai
    except ImportError:
        return None
    if not settings.use_vertex:
        # 임베딩은 Vertex 경로만 지원한다. API 키 모드에선 RAG 없이 전체 반환.
        return None

    model = settings.embedding_model
    # 클라이언트는 실제로 임베딩할 때 한 번만 만든다(지연 생성). 그래야 도구를 만들기만 하고
    # 정책 질문이 안 들어오면(예: 테스트, 다른 질문) Vertex에 아예 연결하지 않는다.
    box: dict[str, Any] = {}

    def embed(texts: list[str]) -> list[list[float]]:
        client = box.get("client")
        if client is None:
            client = genai.Client(
                vertexai=True,
                project=settings.vertex_project,
                location=settings.vertex_location,
            )
            box["client"] = client
        resp = client.models.embed_content(model=model, contents=texts)
        return [e.values for e in resp.embeddings]

    return embed


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class PolicyRetriever:
    """정책을 임베딩해 질문과 관련된 것만 골라준다.

    임베딩이 없거나(embed=None) 오류가 나면 전체 정책을 그대로 돌려준다. 즉 RAG가
    실패해도 챗봇은 멈추지 않고, 최악의 경우 기존처럼 전체를 넘길 뿐이다.
    """

    def __init__(
        self,
        embed: Embedder | None = None,
        top_k: int = 3,
        margin: float = 0.05,
    ) -> None:
        self._embed = embed
        self._top_k = top_k
        # 최고 점수와의 차이가 margin 이내인 정책만 남긴다. 질문과 딱 하나 관련되면
        # 1개만, 여러 주제(예: "주차랑 와이파이")면 비슷한 점수라 여러 개가 남는다.
        self._margin = margin
        # 정책 벡터 캐시: store_id -> (정책 텍스트 튜플, 벡터 목록).
        # 정책 내용이 그대로면 다시 임베딩하지 않는다(매 질문마다 재계산 방지).
        self._cache: dict[str, tuple[tuple[str, ...], list[list[float]]]] = {}

    def retrieve(
        self,
        policies: list[dict[str, Any]],
        query: str | None,
        store_id: str = "",
    ) -> list[dict[str, Any]]:
        """policies 중 query와 관련된 상위 top_k개를 돌려준다.

        query가 없거나 임베딩을 못 쓰거나 정책이 top_k 이하이면 전체를 그대로 돌려준다.
        """
        if (
            self._embed is None
            or not query
            or not query.strip()
            or len(policies) <= self._top_k
        ):
            return policies
        try:
            texts = tuple(
                f"{p.get('title', '')}: {p.get('content', '')}" for p in policies
            )
            policy_vectors = self._policy_vectors(store_id, texts)
            query_vector = self._embed([query])[0]
            scores = [_cosine(query_vector, v) for v in policy_vectors]
            order = sorted(range(len(policies)), key=lambda i: scores[i], reverse=True)
            best = scores[order[0]]
            # 상위 top_k 중, 최고 점수와 margin 이내인 것만 남긴다(관련 낮은 건 버림).
            kept = [i for i in order[: self._top_k] if scores[i] >= best - self._margin]
            logger.info(
                "정책 RAG '%s': %s",
                query,
                [(policies[i].get("title"), round(scores[i], 3)) for i in order[: self._top_k]],
            )
            return [policies[i] for i in kept]
        except Exception:
            # 검색 실패는 대화를 끊을 이유가 안 된다. 전체를 그대로 넘긴다.
            logger.warning("정책 RAG 검색 실패, 전체 정책 반환", exc_info=True)
            return policies

    def _policy_vectors(
        self,
        store_id: str,
        texts: tuple[str, ...],
    ) -> list[list[float]]:
        cached = self._cache.get(store_id)
        if cached is not None and cached[0] == texts:
            return cached[1]
        vectors = self._embed(list(texts))  # type: ignore[misc]
        self._cache[store_id] = (texts, vectors)
        return vectors

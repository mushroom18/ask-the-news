from __future__ import annotations

from ask_the_news.config import RERANKER_MODEL
from ask_the_news.models import RetrievedChunk


class CrossEncoderReranker:
    """Lazy-loaded wrapper around a sentence-transformers CrossEncoder.

    Bi-encoder retrieval (pgvector cosine) returns a candidate pool. The
    cross-encoder re-scores each (query, chunk) pair by feeding both through
    a single transformer with full cross-attention. This catches the kind of
    ranking error vector cosine makes — correct article retrieved but ranked
    2nd or 3rd because cosine can't tell the difference between two similar-
    but-not-equal phrasings.

    Default model: BAAI/bge-reranker-v2-m3 (2024, multilingual, ~568MB).
    Override with RERANKER_MODEL env var.
    """

    def __init__(self, model_name: str = RERANKER_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self,
        query_text: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        model = self._ensure_model()
        pairs = [(query_text, item.chunk.text) for item in candidates]
        scores = model.predict(pairs)

        # Pair up, sort by cross-encoder score desc, take top_k, renumber ranks.
        ordered = sorted(
            zip(candidates, scores),
            key=lambda pair: -float(pair[1]),
        )[:top_k]

        return [
            RetrievedChunk(chunk=item.chunk, score=float(score), rank=new_rank)
            for new_rank, (item, score) in enumerate(ordered, start=1)
        ]


_default_reranker: CrossEncoderReranker | None = None


def default_reranker() -> CrossEncoderReranker:
    global _default_reranker
    if _default_reranker is None:
        _default_reranker = CrossEncoderReranker()
    return _default_reranker

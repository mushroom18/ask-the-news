from __future__ import annotations

from sentence_transformers import SentenceTransformer

from ask_the_news.config import EMBEDDING_MODEL


class EmbeddingModel:
    def __init__(self, model_name: str = EMBEDDING_MODEL) -> None:
        self.model = SentenceTransformer(model_name)

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    def encode_query(self, text: str) -> list[float]:
        return self.encode_texts([text])[0]

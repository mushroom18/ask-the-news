from __future__ import annotations

from ask_the_news.config import EMBEDDING_MODEL


class EmbeddingModel:
    def __init__(self, model_name: str = EMBEDDING_MODEL) -> None:
        self.model_name = model_name
        self.model = None

    def _ensure_model(self):
        if self.model is None:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(self.model_name)
        return self.model

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_model()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    def encode_query(self, text: str) -> list[float]:
        return self.encode_texts([text])[0]

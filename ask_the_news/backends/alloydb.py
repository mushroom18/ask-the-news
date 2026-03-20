from __future__ import annotations

from ask_the_news.backends.base import ArticleRepository, RetrievalBackend
from ask_the_news.models import Article, QAContext, QueryBundle, TimelineContext


class AlloyDBArticleRepository(ArticleRepository):
    def __init__(self, dsn: str = "") -> None:
        self.dsn = dsn

    def featured_articles(self, limit: int = 24) -> list[Article]:
        raise NotImplementedError("AlloyDBArticleRepository is not implemented yet.")

    def get_article(self, article_id: str) -> Article | None:
        raise NotImplementedError("AlloyDBArticleRepository is not implemented yet.")

    def list_articles_by_ids(self, article_ids: list[str]) -> list[Article]:
        raise NotImplementedError("AlloyDBArticleRepository is not implemented yet.")

    def index_ready(self) -> bool:
        return False


class AlloyDBRetrievalBackend(RetrievalBackend):
    def __init__(self, dsn: str = "") -> None:
        self.dsn = dsn

    def build_qa_context(self, query: QueryBundle, top_k: int) -> QAContext:
        raise NotImplementedError("AlloyDBRetrievalBackend is not implemented yet.")

    def build_timeline_context(self, query: QueryBundle, top_k: int) -> TimelineContext:
        raise NotImplementedError("AlloyDBRetrievalBackend is not implemented yet.")

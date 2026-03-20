from __future__ import annotations

from typing import Protocol

from ask_the_news.models import Article, QAContext, QueryBundle, TimelineContext


class ArticleRepository(Protocol):
    def featured_articles(self, limit: int = 24) -> list[Article]:
        ...

    def get_article(self, article_id: str) -> Article | None:
        ...

    def list_articles_by_ids(self, article_ids: list[str]) -> list[Article]:
        ...

    def index_ready(self) -> bool:
        ...


class RetrievalBackend(Protocol):
    def build_qa_context(self, query: QueryBundle, top_k: int) -> QAContext:
        ...

    def build_timeline_context(self, query: QueryBundle, top_k: int) -> TimelineContext:
        ...

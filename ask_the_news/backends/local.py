from __future__ import annotations

from pathlib import Path

from ask_the_news.backends.base import ArticleRepository, RetrievalBackend
from ask_the_news.config import SQLITE_DB_PATH, VECTOR_INDEX_IDS_PATH, VECTOR_INDEX_PATH
from ask_the_news.ingestion import load_articles
from ask_the_news.models import Article, QAContext, QueryBundle, TimelineContext
from ask_the_news.retrieval import LocalVectorRetriever
from ask_the_news.storage import SQLiteStorage


class LocalArticleRepository(ArticleRepository):
    def __init__(self, storage: SQLiteStorage | None = None) -> None:
        self.storage = storage or SQLiteStorage()

    def featured_articles(self, limit: int = 24) -> list[Article]:
        if Path(SQLITE_DB_PATH).exists():
            articles = self.storage.list_articles(limit=limit)
            if articles:
                return articles
        return load_articles()[:limit]

    def get_article(self, article_id: str) -> Article | None:
        if not article_id:
            return None
        if Path(SQLITE_DB_PATH).exists():
            article = self.storage.get_article(article_id)
            if article is not None:
                return article
        for article in load_articles():
            if article.article_id == article_id:
                return article
        return None

    def list_articles_by_ids(self, article_ids: list[str]) -> list[Article]:
        if not article_ids:
            return []
        if Path(SQLITE_DB_PATH).exists():
            return self.storage.list_articles_by_ids(article_ids)
        local_map = {article.article_id: article for article in load_articles()}
        return [local_map[article_id] for article_id in article_ids if article_id in local_map]

    def index_ready(self) -> bool:
        return Path(VECTOR_INDEX_PATH).exists() and Path(VECTOR_INDEX_IDS_PATH).exists()


class LocalRetrievalBackend(RetrievalBackend):
    def __init__(self, storage: SQLiteStorage | None = None, retriever: LocalVectorRetriever | None = None) -> None:
        self.storage = storage or SQLiteStorage()
        self.retriever = retriever or LocalVectorRetriever(storage=self.storage)

    def build_qa_context(self, query: QueryBundle, top_k: int) -> QAContext:
        return self.retriever.build_qa_context(query, top_k=top_k)

    def build_timeline_context(self, query: QueryBundle, top_k: int) -> TimelineContext:
        return self.retriever.build_timeline_context(query, top_k=top_k)

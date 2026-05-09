from __future__ import annotations

from dataclasses import asdict
from textwrap import shorten

from ask_the_news import db
from ask_the_news.backends.base import ArticleRepository, RetrievalBackend
from ask_the_news.backends.local import LocalArticleRepository, LocalRetrievalBackend
from ask_the_news.config import RETRIEVAL_TOP_K
from ask_the_news.llm import answer_question, generate_timeline
from ask_the_news.models import Article
from ask_the_news.query_router import build_query_bundle, guardrail_query


def default_backends() -> tuple[ArticleRepository, RetrievalBackend]:
    if db.is_configured():
        from ask_the_news.backends.postgres import PostgresArticleRepository, PostgresRetrievalBackend

        repository = PostgresArticleRepository()
        return repository, PostgresRetrievalBackend(repository=repository)
    return LocalArticleRepository(), LocalRetrievalBackend()


class NewsService:
    def __init__(
        self,
        repository: ArticleRepository | None = None,
        retriever: RetrievalBackend | None = None,
    ) -> None:
        default_repository, default_retriever = default_backends()
        self.repository = repository or default_repository
        self.retriever = retriever or default_retriever

    def featured_articles(self, limit: int = 24) -> list[Article]:
        return self.repository.featured_articles(limit=limit)

    def get_article(self, article_id: str) -> Article | None:
        return self.repository.get_article(article_id)

    def example_questions(self, article: Article | None) -> list[str]:
        if article is None:
            return [
                "Summarize the most important development.",
                "What happened before this?",
                "Who are the main actors involved?",
                "Build a timeline of related events.",
            ]

        subject = shorten(article.title, width=72, placeholder="...")
        return [
            f"Summarize the key development in {subject}.",
            "What happened before this?",
            "Who are the main people or organizations involved?",
            f"Build a timeline of related events behind {subject}.",
        ]

    def index_ready(self) -> bool:
        return self.repository.index_ready()

    def answer(self, question: str, current_article_id: str = "", top_k: int = RETRIEVAL_TOP_K) -> dict:
        article = self.get_article(current_article_id)
        guardrail = guardrail_query(question, current_article=article)
        if not guardrail.should_retrieve:
            return {
                "ok": False,
                "blocked": True,
                "message": guardrail.user_message,
                "query_mode": "blocked",
                "route_reason": guardrail.reason,
                "citations": [],
            }

        if not self.index_ready():
            return {
                "ok": False,
                "blocked": False,
                "message": "The active retrieval backend is not ready.",
                "query_mode": "error",
                "route_reason": "The active retrieval backend could not confirm index readiness.",
                "citations": [],
            }

        bundle = build_query_bundle(question, current_article=article)
        context = self.retriever.build_qa_context(bundle, top_k=top_k)
        answer = answer_question(context)
        return {
            "ok": True,
            "blocked": False,
            "message": answer,
            "query_mode": bundle.mode,
            "route_reason": bundle.route_reason,
            "citations": [asdict(citation) for citation in context.citations],
        }

    def timeline(self, question: str, current_article_id: str = "") -> dict:
        article = self.get_article(current_article_id)
        if article is None:
            return {
                "ok": False,
                "message": "Select a featured story before building a timeline.",
                "query_mode": "error",
                "route_reason": "No current article was provided.",
                "items": [],
            }

        if not self.index_ready():
            return {
                "ok": False,
                "message": "The active retrieval backend is not ready.",
                "query_mode": "error",
                "route_reason": "The active retrieval backend could not confirm index readiness.",
                "items": [],
            }

        timeline_query = question.strip() or f"Build a timeline of related events behind {article.title}."
        bundle = build_query_bundle(timeline_query, current_article=article)
        context = self.retriever.build_timeline_context(bundle, top_k=max(RETRIEVAL_TOP_K, 10))
        items = generate_timeline(context)
        return {
            "ok": True,
            "message": "",
            "query_mode": bundle.mode,
            "route_reason": bundle.route_reason,
            "items": [asdict(item) for item in items],
        }

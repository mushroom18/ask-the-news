from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from ask_the_news.service import NewsService


app = FastAPI(title="Ask the News API")
service = NewsService()


class QueryRequest(BaseModel):
    question: str = Field(default="")
    current_article_id: str = Field(default="")
    top_k: int = Field(default=8, ge=1, le=50)


class TimelineRequest(BaseModel):
    question: str = Field(default="")
    current_article_id: str = Field(default="")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "index_ready": service.index_ready()}


@app.get("/featured")
def featured(limit: int = 24) -> dict[str, Any]:
    articles = [article.__dict__ for article in service.featured_articles(limit=limit)]
    return {"articles": articles}


@app.get("/article/{article_id}")
def article(article_id: str) -> dict[str, Any]:
    item = service.get_article(article_id)
    return {"article": item.__dict__ if item else None}


@app.post("/query")
def query(payload: QueryRequest) -> dict[str, Any]:
    return service.answer(payload.question, current_article_id=payload.current_article_id, top_k=payload.top_k)


@app.post("/timeline")
def timeline(payload: TimelineRequest) -> dict[str, Any]:
    return service.timeline(payload.question, current_article_id=payload.current_article_id)

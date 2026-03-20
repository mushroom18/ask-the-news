from __future__ import annotations

import json
from textwrap import shorten

from openai import OpenAI

from ask_the_news.config import (
    OPENAI_API_KEY,
    OPENAI_MAX_OUTPUT_TOKENS,
    OPENAI_REASONING_EFFORT,
    QA_MODEL,
    TIMELINE_MODEL,
)
from ask_the_news.models import QAContext, TimelineContext, TimelineItem


def extractive_answer(context: QAContext) -> str:
    if not context.retrieved_chunks:
        return "I could not find a strong match in the current knowledge base."

    snippets: list[str] = []
    seen_articles: set[str] = set()
    for item in context.retrieved_chunks:
        if item.chunk.article_id in seen_articles:
            continue
        seen_articles.add(item.chunk.article_id)
        snippet = shorten(item.chunk.text.replace("\n", " "), width=320, placeholder="...")
        snippets.append(snippet)
        if len(snippets) == 3:
            break

    if not snippets:
        return "I found source articles, but the retrieved passages were too weak to summarize."

    answer = snippets[0]
    if len(snippets) > 1:
        answer += f"\n\nRelated coverage also notes: {snippets[1]}"
    if len(snippets) > 2:
        answer += f"\n\nAnother relevant report adds: {snippets[2]}"
    return answer


def fallback_timeline(context: TimelineContext) -> list[TimelineItem]:
    return context.items


def _client() -> OpenAI | None:
    if not OPENAI_API_KEY:
        return None
    return OpenAI(api_key=OPENAI_API_KEY)


def _qa_context_text(context: QAContext) -> str:
    parts = [
        f"User question: {context.query.user_query}",
        f"Retrieval mode: {context.query.mode}",
    ]
    if context.query.current_article_title:
        parts.extend(
            [
                f"Current article title: {context.query.current_article_title}",
                f"Current article description: {context.query.current_article_description}",
                f"Current article section: {context.query.current_article_section}",
            ]
        )

    for index, item in enumerate(context.retrieved_chunks[:6], start=1):
        parts.append(
            "\n".join(
                [
                    f"Source {index} title: {item.chunk.title}",
                    f"Source {index} date: {item.chunk.published_at}",
                    f"Source {index} section: {item.chunk.section}",
                    f"Source {index} excerpt: {item.chunk.text}",
                ]
            )
        )
    return "\n\n".join(part for part in parts if part.strip())


def answer_question(context: QAContext) -> str:
    client = _client()
    if client is None:
        return extractive_answer(context)

    try:
        response = client.responses.create(
            model=QA_MODEL,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Answer the user's question using only the supplied news excerpts. "
                                "Be concise, factual, and explicit when the context is incomplete. "
                                "Do not invent facts or citations."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _qa_context_text(context),
                        }
                    ],
                },
            ],
            reasoning={"effort": OPENAI_REASONING_EFFORT},
            max_output_tokens=OPENAI_MAX_OUTPUT_TOKENS,
        )
        text = (response.output_text or "").strip()
        return text or extractive_answer(context)
    except Exception:
        return extractive_answer(context)


def _timeline_context_text(context: TimelineContext) -> str:
    parts = [
        f"Timeline request: {context.query.user_query}",
        f"Retrieval mode: {context.query.mode}",
    ]
    if context.query.current_article_title:
        parts.append(f"Current article title: {context.query.current_article_title}")
    for item in context.items[:8]:
        parts.append(
            "\n".join(
                [
                    f"Article ID: {item.article_id}",
                    f"Date: {item.published_at}",
                    f"Title: {item.title}",
                    f"Existing summary: {item.summary}",
                ]
            )
        )
    return "\n\n".join(parts)


def generate_timeline(context: TimelineContext) -> list[TimelineItem]:
    client = _client()
    if client is None or not context.items:
        return fallback_timeline(context)

    try:
        response = client.responses.create(
            model=TIMELINE_MODEL,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Rewrite the retrieved timeline into concise event summaries. "
                                "Use only the supplied articles. Keep chronology intact."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _timeline_context_text(context),
                        }
                    ],
                },
            ],
            reasoning={"effort": OPENAI_REASONING_EFFORT},
            max_output_tokens=OPENAI_MAX_OUTPUT_TOKENS,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "timeline_response",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "article_id": {"type": "string"},
                                        "summary": {"type": "string"},
                                    },
                                    "required": ["article_id", "summary"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["items"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        payload = json.loads(response.output_text)
        summary_by_id = {
            item["article_id"]: item["summary"].strip()
            for item in payload.get("items", [])
            if item.get("article_id") and item.get("summary")
        }
        if not summary_by_id:
            return fallback_timeline(context)

        updated_items: list[TimelineItem] = []
        for item in context.items:
            summary = summary_by_id.get(item.article_id, item.summary)
            updated_items.append(
                TimelineItem(
                    article_id=item.article_id,
                    published_at=item.published_at,
                    title=item.title,
                    url=item.url,
                    source=item.source,
                    summary=summary,
                )
            )
        return updated_items
    except Exception:
        return fallback_timeline(context)

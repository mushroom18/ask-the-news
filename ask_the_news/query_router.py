from __future__ import annotations

import json
import re

from openai import OpenAI

from ask_the_news.config import OPENAI_API_KEY, QUERY_ROUTER_MODEL
from ask_the_news.models import Article, QueryBundle, QueryGuardrailResult, QueryRoute


FALLBACK_CONTEXT_WORDS = {
    "this",
    "that",
    "it",
    "they",
    "them",
    "he",
    "she",
    "his",
    "her",
    "their",
    "these",
    "those",
}

INCOMPLETE_QUERY_PATTERNS = [
    re.compile(r"^\s*what happened before this\??\s*$", re.I),
    re.compile(r"^\s*why did this happen\??\s*$", re.I),
    re.compile(r"^\s*what is the timeline\??\s*$", re.I),
    re.compile(r"^\s*what happened next\??\s*$", re.I),
    re.compile(r"^\s*what does this mean\??\s*$", re.I),
]


def heuristic_route(user_query: str) -> QueryRoute:
    words = {word.strip(".,?!:;()[]{}\"'").lower() for word in user_query.split()}
    if words & FALLBACK_CONTEXT_WORDS:
        return QueryRoute(mode="contextual", reason="Fallback heuristic detected context-dependent wording.")
    return QueryRoute(mode="global", reason="Fallback heuristic detected a standalone query.")


def parse_router_payload(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def route_query(user_query: str, current_article: Article | None = None) -> QueryRoute:
    if current_article is None:
        return QueryRoute(mode="global", reason="No current article context is available.")

    if not OPENAI_API_KEY:
        return heuristic_route(user_query)

    client = OpenAI(api_key=OPENAI_API_KEY)
    article_title = current_article.title
    article_description = current_article.description
    article_section = current_article.section

    prompt = [
        {
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Classify whether the user's question depends on the currently displayed article context. "
                        "Return JSON only."
                    ),
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        f"Current article title: {article_title}\n"
                        f"Current article description: {article_description}\n"
                        f"Current article section: {article_section}\n"
                        f"User question: {user_query}"
                    ),
                }
            ],
        },
    ]
    try:
        response = client.responses.create(
            model=QUERY_ROUTER_MODEL,
            input=prompt,
            max_output_tokens=120,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "query_route",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "mode": {
                                "type": "string",
                                "enum": ["contextual", "global"],
                            },
                            "reason": {
                                "type": "string",
                            },
                        },
                        "required": ["mode", "reason"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        payload = parse_router_payload(response.output_text)
        mode = payload.get("mode", "global")
        if mode not in {"contextual", "global"}:
            mode = "global"
        return QueryRoute(mode=mode, reason=str(payload.get("reason", "")))
    except Exception:
        return heuristic_route(user_query)


def build_query_bundle(user_query: str, current_article: Article | None = None) -> QueryBundle:
    route = route_query(user_query, current_article=current_article)
    return QueryBundle(
        user_query=user_query,
        mode=route.mode,
        current_article_id=current_article.article_id if current_article else "",
        current_article_title=current_article.title if current_article else "",
        current_article_description=current_article.description if current_article else "",
        current_article_section=current_article.section if current_article else "",
        route_reason=route.reason,
    )


def guardrail_query(user_query: str, current_article: Article | None = None) -> QueryGuardrailResult:
    if current_article is not None:
        return QueryGuardrailResult(should_retrieve=True)

    normalized = " ".join(user_query.split()).strip()
    if not normalized:
        return QueryGuardrailResult(
            should_retrieve=False,
            reason="The query is empty.",
            user_message="Please enter a question before searching.",
        )

    if any(pattern.match(normalized) for pattern in INCOMPLETE_QUERY_PATTERNS):
        return QueryGuardrailResult(
            should_retrieve=False,
            reason="The query depends on missing context.",
            user_message="This question needs a current article or a more specific topic. Select a story or rewrite the question.",
        )

    words = {word.strip(".,?!:;()[]{}\"'").lower() for word in normalized.split()}
    if words & FALLBACK_CONTEXT_WORDS and len(words) <= 6:
        return QueryGuardrailResult(
            should_retrieve=False,
            reason="The query is too context-dependent without a current article.",
            user_message="This question depends on missing context. Select a story or ask a more specific question.",
        )

    return QueryGuardrailResult(should_retrieve=True)

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai import OpenAI

from ask_the_news.config import OPENAI_API_KEY, OPENAI_MAX_OUTPUT_TOKENS, OPENAI_REASONING_EFFORT, RETRIEVAL_TOP_K
from ask_the_news.llm import answer_question, generate_timeline
from ask_the_news.query_router import build_query_bundle, guardrail_query
from ask_the_news.retrieval import LocalVectorRetriever
from ask_the_news.storage import SQLiteStorage


DEFAULT_JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-5-mini")


def load_cases(path: Path) -> list[dict]:
    cases: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def retrieved_article_ids_from_context(context) -> list[str]:
    article_ids: list[str] = []
    seen: set[str] = set()
    for item in getattr(context, "retrieved_chunks", []):
        article_id = item.chunk.article_id
        if article_id in seen:
            continue
        seen.add(article_id)
        article_ids.append(article_id)
    if article_ids:
        return article_ids

    for article in getattr(context, "related_articles", []):
        if article.article_id in seen:
            continue
        seen.add(article.article_id)
        article_ids.append(article.article_id)
    return article_ids


def citation_article_ids(context) -> list[str]:
    seen: set[str] = set()
    article_ids: list[str] = []
    for citation in getattr(context, "citations", []):
        if citation.article_id in seen:
            continue
        seen.add(citation.article_id)
        article_ids.append(citation.article_id)
    return article_ids


def run_case(case: dict, retriever: LocalVectorRetriever, storage: SQLiteStorage, top_k: int) -> dict:
    current_article_id = case.get("current_article_id", "").strip()
    current_article = storage.get_article(current_article_id) if current_article_id else None
    question = case["question"]
    guardrail = guardrail_query(question, current_article=current_article)

    result = {
        "id": case["id"],
        "task_type": case["task_type"],
        "question": question,
        "current_article_id": current_article_id,
        "expected_article_ids": case.get("expected_article_ids", []),
        "expected_answer_points": case.get("expected_answer_points", []),
        "expected_timeline_article_ids": case.get("expected_timeline_article_ids", []),
        "expected_timeline_points": case.get("expected_timeline_points", []),
        "guardrail_blocked": not guardrail.should_retrieve,
        "guardrail_reason": guardrail.reason,
        "guardrail_message": guardrail.user_message,
    }

    if not guardrail.should_retrieve:
        result.update(
            {
                "query_mode": "blocked",
                "route_reason": "",
                "retrieved_article_ids": [],
                "citation_article_ids": [],
                "answer": "",
                "timeline_items": [],
            }
        )
        return result

    bundle = build_query_bundle(question, current_article=current_article)
    result["query_mode"] = bundle.mode
    result["route_reason"] = bundle.route_reason

    if case["task_type"] == "timeline":
        context = retriever.build_timeline_context(bundle, top_k=top_k)
        timeline_items = generate_timeline(context)
        result["retrieved_article_ids"] = retrieved_article_ids_from_context(context)
        result["citation_article_ids"] = []
        result["answer"] = ""
        result["timeline_items"] = [
            {
                "article_id": item.article_id,
                "published_at": item.published_at,
                "title": item.title,
                "url": item.url,
                "summary": item.summary,
            }
            for item in timeline_items
        ]
        result["retrieved_chunks"] = []
        return result

    context = retriever.build_qa_context(bundle, top_k=top_k)
    result["retrieved_article_ids"] = retrieved_article_ids_from_context(context)
    result["citation_article_ids"] = citation_article_ids(context)
    result["answer"] = answer_question(context)
    result["timeline_items"] = []
    result["retrieved_chunks"] = [
        {
            "rank": item.rank,
            "score": item.score,
            "article_id": item.chunk.article_id,
            "chunk_index": item.chunk.chunk_index,
            "title": item.chunk.title,
            "published_at": item.chunk.published_at,
            "text": item.chunk.text,
        }
        for item in context.retrieved_chunks
    ]
    return result


def judge_case(result: dict, judge_model: str) -> dict:
    if result.get("guardrail_blocked"):
        return {
            "retrieval_relevance": None,
            "answer_groundedness": None,
            "answer_usefulness": None,
            "citation_support": None,
            "timeline_quality": None,
            "verdict": "skipped",
            "reasoning": "The case was blocked by the query guardrail before retrieval.",
        }

    if not OPENAI_API_KEY:
        return {
            "retrieval_relevance": None,
            "answer_groundedness": None,
            "answer_usefulness": None,
            "citation_support": None,
            "timeline_quality": None,
            "verdict": "skipped",
            "reasoning": "OPENAI_API_KEY is not configured.",
        }

    client = OpenAI(api_key=OPENAI_API_KEY)
    payload = {
        "task_type": result["task_type"],
        "question": result["question"],
        "query_mode": result.get("query_mode", ""),
        "expected_article_ids": result.get("expected_article_ids", []),
        "expected_answer_points": result.get("expected_answer_points", []),
        "expected_timeline_article_ids": result.get("expected_timeline_article_ids", []),
        "expected_timeline_points": result.get("expected_timeline_points", []),
        "retrieved_article_ids": result.get("retrieved_article_ids", []),
        "citation_article_ids": result.get("citation_article_ids", []),
        "retrieved_chunks": result.get("retrieved_chunks", []),
        "answer": result.get("answer", ""),
        "timeline_items": result.get("timeline_items", []),
    }

    response = client.responses.create(
        model=judge_model,
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are grading a news RAG system. Score each dimension from 0 to 2. "
                            "Use 0 for poor, 1 for partial, 2 for strong. "
                            "For non-applicable dimensions, return null. "
                            "Judge groundedness strictly against the retrieved context."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(payload, ensure_ascii=False),
                    }
                ],
            },
        ],
        reasoning={"effort": OPENAI_REASONING_EFFORT},
        max_output_tokens=min(900, OPENAI_MAX_OUTPUT_TOKENS),
        text={
            "format": {
                "type": "json_schema",
                "name": "rag_judge",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "retrieval_relevance": {"type": ["integer", "null"], "minimum": 0, "maximum": 2},
                        "answer_groundedness": {"type": ["integer", "null"], "minimum": 0, "maximum": 2},
                        "answer_usefulness": {"type": ["integer", "null"], "minimum": 0, "maximum": 2},
                        "citation_support": {"type": ["integer", "null"], "minimum": 0, "maximum": 2},
                        "timeline_quality": {"type": ["integer", "null"], "minimum": 0, "maximum": 2},
                        "verdict": {"type": "string"},
                        "reasoning": {"type": "string"},
                    },
                    "required": [
                        "retrieval_relevance",
                        "answer_groundedness",
                        "answer_usefulness",
                        "citation_support",
                        "timeline_quality",
                        "verdict",
                        "reasoning",
                    ],
                    "additionalProperties": False,
                },
            }
        },
    )
    return json.loads(response.output_text)


def summarize_scores(results: list[dict]) -> dict:
    score_keys = [
        "retrieval_relevance",
        "answer_groundedness",
        "answer_usefulness",
        "citation_support",
        "timeline_quality",
    ]
    summary: dict[str, float | int | None] = {"case_count": len(results)}
    for key in score_keys:
        values = [item["judge"][key] for item in results if item.get("judge") and item["judge"][key] is not None]
        summary[f"avg_{key}"] = round(mean(values), 3) if values else None
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM-as-a-Judge evaluation for Ask the News.")
    parser.add_argument("--cases", default="evaluation/cases_template.jsonl")
    parser.add_argument("--output", default="evaluation/results.jsonl")
    parser.add_argument("--top-k", type=int, default=RETRIEVAL_TOP_K)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    args = parser.parse_args()

    cases_path = Path(args.cases)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    storage = SQLiteStorage()
    retriever = LocalVectorRetriever(storage=storage)

    cases = load_cases(cases_path)
    results: list[dict] = []
    with output_path.open("w", encoding="utf-8") as handle:
        for case in cases:
            result = run_case(case, retriever=retriever, storage=storage, top_k=args.top_k)
            result["judge"] = judge_case(result, judge_model=args.judge_model)
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            results.append(result)

    print(json.dumps(summarize_scores(results), indent=2))


if __name__ == "__main__":
    main()

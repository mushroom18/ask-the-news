from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_results(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def hit_at_k(retrieved: list[str], expected: set[str], k: int) -> int:
    if not expected:
        return 0
    return int(any(article_id in expected for article_id in retrieved[:k]))


def reciprocal_rank(retrieved: list[str], expected: set[str]) -> float:
    if not expected:
        return 0.0
    for index, article_id in enumerate(retrieved, start=1):
        if article_id in expected:
            return 1.0 / index
    return 0.0


def precision_at_k(retrieved: list[str], expected: set[str], k: int) -> float:
    if not expected:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    return sum(1 for article_id in top if article_id in expected) / len(top)


def timeline_coverage(retrieved: list[str], expected: set[str]) -> float:
    if not expected:
        return 0.0
    overlap = sum(1 for article_id in expected if article_id in retrieved)
    return overlap / len(expected)


def summarize(results: list[dict]) -> dict:
    qa_rows = [row for row in results if row.get("task_type") == "qa" and not row.get("guardrail_blocked")]
    timeline_rows = [row for row in results if row.get("task_type") == "timeline" and not row.get("guardrail_blocked")]

    hit3_values = []
    hit5_values = []
    mrr_values = []
    precision5_values = []
    timeline_coverage_values = []

    for row in qa_rows:
        expected = set(row.get("expected_article_ids", []))
        retrieved = row.get("retrieved_article_ids", [])
        if not expected:
            continue
        hit3_values.append(hit_at_k(retrieved, expected, 3))
        hit5_values.append(hit_at_k(retrieved, expected, 5))
        mrr_values.append(reciprocal_rank(retrieved, expected))
        precision5_values.append(precision_at_k(retrieved, expected, 5))

    for row in timeline_rows:
        expected = set(row.get("expected_timeline_article_ids", []))
        retrieved = [item["article_id"] for item in row.get("timeline_items", [])]
        if not expected:
            continue
        timeline_coverage_values.append(timeline_coverage(retrieved, expected))

    return {
        "qa_case_count": len(qa_rows),
        "timeline_case_count": len(timeline_rows),
        "hit_at_3": round(mean(hit3_values), 3) if hit3_values else None,
        "hit_at_5": round(mean(hit5_values), 3) if hit5_values else None,
        "mrr": round(mean(mrr_values), 3) if mrr_values else None,
        "precision_at_5": round(mean(precision5_values), 3) if precision5_values else None,
        "timeline_coverage": round(mean(timeline_coverage_values), 3) if timeline_coverage_values else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute hard retrieval metrics from evaluation results.")
    parser.add_argument("--results", default="evaluation/results.jsonl")
    args = parser.parse_args()
    results = load_results(Path(args.results))
    print(json.dumps(summarize(results), indent=2))


if __name__ == "__main__":
    main()

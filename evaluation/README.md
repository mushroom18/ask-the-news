# Evaluation

This folder contains the RAG evaluation workflow for Ask the News.

## Files

- `cases_template.jsonl`
  - template for manually curated evaluation cases
- `judge.py`
  - runs retrieval + generation and scores outputs with an LLM judge
- `metrics.py`
  - computes hard retrieval metrics from judge output

## Case schema

Each line in the cases file must be a JSON object.

Common fields:

- `id`
- `task_type`
  - `qa` or `timeline`
- `question`
- `current_article_id`
  - optional, may be empty
- `expected_article_ids`
  - gold article ids for retrieval
- `expected_answer_points`
  - short bullet-style facts expected in a good answer
- `expected_timeline_article_ids`
  - gold article ids for timeline tasks
- `expected_timeline_points`
  - key timeline points in plain text

## Run the judge

```bash
python3 evaluation/judge.py --cases evaluation/cases_template.jsonl --output evaluation/results.jsonl
```

You can also run:

```bash
python3 -m evaluation.judge --cases evaluation/cases_template.jsonl --output evaluation/results.jsonl
```

Optional arguments:

- `--top-k`
- `--judge-model`

## Compute hard metrics

```bash
python3 evaluation/metrics.py --results evaluation/results.jsonl
```

Or:

```bash
python3 -m evaluation.metrics --results evaluation/results.jsonl
```

## Suggested targets

- `hit@3 >= 0.70`
- `hit@5 >= 0.85`
- `mrr >= 0.65`
- `precision@5 >= 0.60`
- `judge_answer_groundedness >= 1.7 / 2`
- `judge_answer_usefulness >= 1.6 / 2`
- `judge_citation_support >= 1.7 / 2`
- `judge_timeline_quality >= 1.5 / 2`

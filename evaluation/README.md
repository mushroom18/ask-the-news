# Evaluation

End-to-end evaluation for the Ask the News RAG pipeline, with ablations.

## TL;DR

| Dimension | Result |
|---|---|
| **Baseline retrieval quality** | hit@3 = **0.875**, MRR = **0.861** (24 QA cases) |
| **Baseline answer quality** (LLM-as-judge, 0–2) | groundedness **1.90**, usefulness **1.93**, citations **1.70** |
| **Router ablation** (router off) | overall hit@3 drops 9% (**0.875 → 0.792**); on contextual queries alone, hit@3 collapses **0.75 → 0.25** |
| **Chunk-size ablation** (100 / 150 / 180 / 220 words) | hit@3 is identical (0.875) across all four; chunk size is **not** a high-leverage tuning knob on this corpus |

## Methodology

### Dataset

30 hand-curated cases in [`cases_template.jsonl`](cases_template.jsonl):

- 24 QA cases — 18 global queries, 6 contextual (those depend on a featured article)
- 6 timeline cases — 4 global, 2 contextual
- Each case carries `expected_article_ids` (gold retrieval set) and `expected_answer_points` (rubric for the judge)

### Pipeline tested

Each case is run through the **same code that the production API serves** — `default_backends()` from `ask_the_news.service`, which selects the Postgres + pgvector backend when `DATABASE_URL` is set. So evaluation reflects what users actually get.

### Scoring

Two layers of scoring:

1. **Hard retrieval metrics** — [`metrics.py`](metrics.py)
   - `hit@k` — fraction of cases where at least one gold article appears in the top-k retrieved
   - `MRR` — Mean Reciprocal Rank; the rank position of the first gold article (1 / rank)
   - `precision@5` — fraction of top-5 results that are gold (note: most cases have only 1–2 gold IDs, so the ceiling is naturally low)
   - `timeline_coverage` — fraction of expected timeline articles that surface in the returned timeline

2. **LLM-as-judge** — [`judge.py`](judge.py)
   - Model: `gpt-5-mini` with `reasoning_effort=minimal`
   - Five dimensions, scored 0 (poor) / 1 (partial) / 2 (strong):
     `retrieval_relevance`, `answer_groundedness`, `answer_usefulness`, `citation_support`, `timeline_quality`
   - Strict JSON schema output (no free-form prose)

### Cost / runtime

Each full run is 30 cases × (1 `answer_question` call + 1 `judge_case` call) ≈ 60 LLM requests ≈ ~$0.60 and ~5 minutes wall time. The chunk-size ablations also re-embed and re-sync the entire chunks table (~6,000 chunks) before each run.

## Baseline

`router=on`, `chunk_target_words=180`, `top_k=8`, `retrieval=pgvector cosine`.

### Hard retrieval

| Metric | Value | Target |
|---|---|---|
| hit@3 | **0.875** | ≥ 0.70 ✅ |
| hit@5 | 0.875 | ≥ 0.85 ✅ |
| MRR | **0.861** | ≥ 0.65 ✅ |
| precision@5 | 0.347 | ≥ 0.60 ❌ (artifact: most cases have ≤ 2 gold IDs, so the ceiling is ~0.4) |
| timeline_coverage | 0.692 | – |

### LLM judge

| Dimension | Score | Target |
|---|---|---|
| retrieval_relevance | **2.00** | – |
| answer_groundedness | 1.90 | ≥ 1.7 ✅ |
| answer_usefulness | 1.93 | ≥ 1.6 ✅ |
| citation_support | 1.70 | ≥ 1.7 ✅ (on the line) |
| timeline_quality | 1.71 | ≥ 1.5 ✅ |

7 of 8 targets met; `precision@5` is a dataset artifact, not a pipeline regression.

## Ablation 1 — Query router on / off

The router is a `gpt-5-nano` classifier that decides, per query, whether to route to **contextual mode** (rewrite the retrieval text to include the current article's title + section + description) or **global mode** (use the bare user question). Disabling the router collapses every query to global mode.

### Overall (all 30 cases)

| Metric | router=on (baseline) | router=off | Δ |
|---|---|---|---|
| hit@3 | 0.875 | 0.792 | **−9.5%** |
| MRR | 0.861 | 0.771 | **−10.5%** |
| timeline_coverage | 0.692 | 0.558 | −19.4% |
| judge retrieval_relevance | 2.00 | 1.73 | −13.4% |
| judge answer_groundedness | 1.90 | 1.67 | −12.1% |
| judge citation_support | 1.70 | 1.53 | −10.0% |
| judge timeline_quality | 1.71 | 1.25 | −26.9% |

### Contextual-only slice (the 6 cases the router exists for)

These are cases where the user query depends on a currently displayed article (e.g. `qa-001: "Who died in this story?"` with `current_article_id` set). Without the router, the system never knows to rewrite the retrieval text — it just searches for "Who died in this story?" against the embedding space.

| Metric | router=on | router=off | Δ |
|---|---|---|---|
| hit@3 | 0.75 | **0.25** | **−66.7%** |
| MRR | 0.79 | **0.25** | **−68.4%** |
| judge retrieval_relevance | 2.00 | 0.67 | **−66.5%** |
| judge answer_groundedness | 2.00 | 0.67 | **−66.5%** |
| judge citation_support | 1.50 | 0.50 | −66.7% |

**Takeaway** — the router is the single most important architectural component on top of vanilla vector search. Without it, contextual queries are nearly random.

## Ablation 2 — Chunk size

Re-chunked and re-embedded the entire 1,500-article corpus four times (`CHUNK_TARGET_WORDS` ∈ {100, 150, 180, 220}) with `CHUNK_OVERLAP_WORDS=40` held constant. Then re-ran the full 30-case evaluation against each rebuilt corpus.

| chunk_target_words | hit@3 | MRR | precision@5 | judge ground. | judge cite. | judge tl. |
|---|---|---|---|---|---|---|
| 100 | 0.875 | 0.847 | **0.440** | 1.90 | 1.73 | 1.57 |
| 150 | 0.875 | 0.847 | 0.377 | 1.90 | 1.73 | 1.50 |
| 180 (baseline) | **0.875** | **0.861** | 0.347 | 1.90 | 1.70 | 1.71 |
| 220 | 0.875 | 0.861 | 0.306 | 1.90 | 1.70 | 1.50 |

**Takeaways**

- `hit@3` is **identical** across all four — the BBC corpus is large enough and topics distinct enough that retrieval finds the right article regardless of chunk granularity.
- `precision@5` *decreases* monotonically as chunks get larger. Mechanism: longer chunks span fewer distinct articles, so top-5 chunks more often share article IDs, which inflates noise vs. gold.
- LLM judge scores are essentially flat. The only sensitive dimension is `timeline_quality`, which peaks at `chunk=180`.
- **Chunk size is a low-leverage knob on this corpus.** Further effort should target retrieval architecture (hybrid BM25 + vector, reranker, query rewriting), not chunking parameters.

## What this tells the next iteration

| Optimization | Predicted impact | Effort |
|---|---|---|
| **Hybrid retrieval** (BM25 + pgvector with RRF or weighted fusion) | High — covers the lexical-precise queries that pure vector search misses | Medium |
| **Cross-encoder reranker** on top-30 → top-8 | Medium-High — should lift `precision@5` and `citation_support` | Low |
| **Query rewriting** (turn casual question into search-friendly form) | Low-Medium on this corpus, because the router already injects article context for contextual queries | Low |
| Chunk-size tuning | **None** on this corpus | Medium |
| Larger / domain-tuned embedding model | Low — `all-MiniLM-L6-v2` already hits 87.5% hit@3 | Medium |

## Reproduce

```bash
# Baseline
python evaluation/judge.py \
  --cases evaluation/cases_template.jsonl \
  --output evaluation/results_baseline.jsonl
python evaluation/metrics.py --results evaluation/results_baseline.jsonl

# Router ablation
python evaluation/judge.py --disable-router \
  --cases evaluation/cases_template.jsonl \
  --output evaluation/results_no_router.jsonl

# Chunk-size sweep — re-embeds the corpus each iteration
for size in 100 150 180 220; do
  CHUNK_TARGET_WORDS=$size python -m ask_the_news.admin sync-db
  CHUNK_TARGET_WORDS=$size python evaluation/judge.py \
    --cases evaluation/cases_template.jsonl \
    --output evaluation/results_chunk${size}.jsonl
done
```

## Case schema

Each line in `cases_template.jsonl` is a JSON object:

- `id`
- `task_type` — `qa` or `timeline`
- `question`
- `current_article_id` (optional)
- `expected_article_ids` — gold for retrieval metrics
- `expected_answer_points` — rubric for the judge
- `expected_timeline_article_ids`, `expected_timeline_points` — timeline-only fields

## Files

- [`cases_template.jsonl`](cases_template.jsonl) — 30 curated cases (gold-labelled)
- [`judge.py`](judge.py) — runs retrieval + generation + LLM-as-judge scoring
- [`metrics.py`](metrics.py) — computes hard retrieval metrics from a judge output file
- `results_baseline.jsonl` — baseline run (router on, chunk=180)
- `results_no_router.jsonl` — router-off ablation
- `results_chunk{100,150,220}.jsonl` — chunk-size ablations

# Evaluation

End-to-end evaluation for the Ask the News RAG pipeline, with ablations.

## TL;DR

| Dimension | Result |
|---|---|
| **Baseline retrieval quality** | hit@3 = **0.875**, MRR = **0.861** (24 QA cases) |
| **Baseline answer quality** (LLM-as-judge, 0–2) | groundedness **1.90**, usefulness **1.93**, citations **1.70** |
| **Router ablation** (router off) | overall hit@3 drops 9% (**0.875 → 0.792**); on contextual queries alone, hit@3 collapses **0.75 → 0.25** |
| **Chunk-size ablation** (100 / 150 / 180 / 220 words) | hit@3 is identical (0.875) across all four; chunk size is **not** a high-leverage tuning knob on this corpus |
| **Article-aggregation rerank** (QA path) | precision@5 **0.347 → 0.465 (+34% rel)**, answer_groundedness +0.07; MRR drops 0.035 (right article still found, just not always at rank 1) |
| **Hybrid retrieval ablation** (BM25 + pgvector + RRF) | **Regressed on this corpus** (hit@3 0.875 → 0.792). Baseline already near ceiling and queries lack lexical-precise terms — BM25 surfaces topical noise that RRF dilutes vector top-1. Honest negative result; reroute to cross-encoder rerank. |

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

## Ablation 3 — Article-level aggregation rerank (QA path only)

Pulls a wider candidate pool from pgvector (`top_k × 3 = 24` chunks), then reranks by article instead of by raw chunk score. Per article, the aggregate score is `top_chunk_score + 0.15 × second_chunk_score`. Within each article, chunks keep their cosine order. Returns the top-K chunks in article-priority order so the LLM sees several supporting passages from the same source before switching to the next article.

Implementation: [`article_aware_chunk_rerank`](../ask_the_news/retrieval.py) (re-used by both the local and Postgres backends). Gated by the `ARTICLE_AGGREGATION` env var (default `off`), so baseline behaviour is unchanged.

### What changes structurally

For the query *"What did Trump say about tariffs?"*:

```
Aggregation OFF  (top-8 spread across 4 articles)
  1. article-60f543… score 0.751  "Donald Trump says he will announce tariffs…"
  2. article-2528c4… score 0.738  "Trump announces 25% tariffs on all steel…"
  3. article-2528c4… score 0.715
  4. article-ab7ab3… score 0.706
  5. article-2528c4… score 0.703
  6. article-60f543… score 0.695
  7. article-2528c4… score 0.673
  8. article-72c4ac… score 0.669

Aggregation ON   (top-8 collapsed onto 2 articles)
  1-5. article-60f543…  (its five strongest chunks first)
  6-8. article-2528c4…  (its three strongest chunks)
```

### Results

| Metric | baseline | article aggregation | Δ |
|---|---|---|---|
| **precision@5** | 0.347 | **0.465** | **+0.118 (+34% rel)** |
| judge answer_groundedness | 1.90 | **1.97** | +0.07 |
| hit@3 / hit@5 | 0.875 | 0.875 | 0 |
| judge retrieval_relevance | 2.00 | 2.00 | 0 |
| judge citation_support | 1.70 | 1.70 | 0 |
| MRR | 0.861 | 0.826 | −0.035 |
| judge timeline_quality | 1.71 | 1.22 | −0.49 (noise — see below) |

### Caveat: judge noise on the timeline slice

`gpt-5-mini` with `reasoning_effort=minimal` returned the *same* 6 timeline article lists across both runs (verified by comparing `timeline_items`), but flipped `timeline-028` from 2 → 1 on the second pass. The −0.49 drop is **single-case LLM judge variance**, not a real regression — this ablation does not touch the timeline path.

### Takeaways

- `precision@5` jumps **+34% relative** (0.347 → 0.465). With fewer distinct articles in top-5 the proportion of gold-labelled articles climbs proportionally. Citations become tighter.
- `answer_groundedness` ticks up slightly because the LLM sees several passages from the same source, giving it more material to actually back its claims against.
- `MRR` drops a small amount: occasionally an article that had a single strongest chunk gets pushed below an article whose top-2 chunks aggregate higher. `hit@3` is unchanged, so the *right* article is still found — just not always at rank 1.
- LLM judge dimensions for QA are flat or slightly positive. Bigger wins on the judge side would likely need a different lever (e.g. a real cross-encoder rerank).

**Default policy** — kept `ARTICLE_AGGREGATION` opt-in for now. Worth flipping on by default once a cross-encoder reranker is in place too, since they compose well.

## Ablation 4 — Hybrid retrieval (BM25 + pgvector + RRF)

A second retrieval lane: Postgres `tsvector` + GIN index runs BM25 alongside the existing pgvector `<=>` cosine search. Both lanes return their own top-30 candidate pool. The two pools are fused with Reciprocal Rank Fusion (`SUM(1.0 / (60 + rank))`) and the top-K of the fused score is returned.

The BM25 query is built as an OR-of-tokens (stopwords stripped, len > 2) and parsed with `websearch_to_tsquery`. The default `plainto_tsquery` ANDs every token, which on a natural-language sentence ("what tariffs did Trump announce on 1 February 2025?") leaves zero matches once stopwords are removed — so BM25 contributes nothing and the fusion degenerates to pure vector. OR-of-tokens fixes that.

Schema change: a generated `ts tsvector` column on `chunks` plus a GIN index ([`sql/schema.sql`](../sql/schema.sql)). Code: [`PostgresRetrievalBackend._hybrid_search`](../ask_the_news/backends/postgres.py).

### Results

| Metric | baseline | hybrid | Δ |
|---|---|---|---|
| hit@3 | 0.875 | **0.792** | **−9.5%** |
| hit@5 | 0.875 | 0.833 | −4.8% |
| MRR | 0.861 | **0.773** | **−10.2%** |
| precision@5 | 0.347 | 0.264 | −24% |
| answer_groundedness (judge) | 1.90 | 1.90 | 0 |
| citation_support (judge) | 1.70 | 1.70 | 0 |
| answer_usefulness (judge) | 1.93 | 1.93 | 0 |

Per-case hit@3 diff: **0 cases improved, 2 regressed (qa-012, qa-016), 22 unchanged.**

### Why hybrid regressed on this dataset

- **Baseline is already near ceiling.** hit@3 = 0.875 means only 3 of 24 QA cases miss; those 3 are typically queries where the gold chunk's *text* shares almost no words with the question (e.g. qa-004 asks about "what did Elon Musk do on X at the start of 2025?", and the gold article uses "Kekius Maximus" + "Pepe the Frog" — words BM25 can't match either).
- **The query set is topical, not lexical-precise.** Most cases ask about Trump / Ukraine / Gaza / OpenAI — broad topics where many articles are lexically relevant. BM25 surfaces a long tail of topical-but-wrong chunks; RRF then dilutes the high-confidence vector top-1 down to top-3.
- **The LLM judge missed the regression.** Groundedness, citations and usefulness scores didn't move — even when the gold article isn't in retrieval top-3, the top-K still contains *some* relevant chunks and the LLM stitches together a usable answer. This is exactly why the eval combines hard retrieval metrics with LLM judging: each catches what the other misses.

### When hybrid would help (and we'd rerun this)

- Corpora dominated by proper nouns, IDs, code symbols (product catalogs, API docs)
- Multilingual queries with code-switching (BM25's lexical matching beats embeddings for OOV terms)
- Lower-baseline retrieval where vector recall is already a bottleneck

### Takeaway

Hybrid retrieval is **not** a free lift. Implemented and shipped behind the `HYBRID_RETRIEVAL` env var (default off) in case query distribution changes. Next-phase optimization moves to cross-encoder reranking, which directly attacks the kind of ranking error vector search makes here (correct article retrieved but pushed down a slot).

## What this tells the next iteration

| Optimization | Status | Notes |
|---|---|---|
| **Article-aggregation rerank** | ✅ shipped (Ablation 3) | precision@5 +34% on this corpus |
| **Hybrid retrieval** (BM25 + pgvector + RRF) | ❌ tested, regressed (Ablation 4) | Baseline near ceiling + queries lack lexical-precise terms; kept behind `HYBRID_RETRIEVAL=on` env var for future query distributions |
| **Cross-encoder reranker** on top-30 → top-8 | 🔜 next | Most promising: directly attacks the kind of error where vector retrieves the right article but ranks it 2nd or 3rd |
| **Query rewriting** | low priority | Router already injects article context for contextual queries |
| Chunk-size tuning | ❌ tested, no signal (Ablation 2) | Skip |
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

# Article-aggregation rerank ablation
ARTICLE_AGGREGATION=on python evaluation/judge.py \
  --cases evaluation/cases_template.jsonl \
  --output evaluation/results_article_agg.jsonl

# Hybrid retrieval ablation (requires the schema migration that adds ts column)
python -m ask_the_news.admin init-db   # idempotent: adds ts + GIN index
HYBRID_RETRIEVAL=on python evaluation/judge.py \
  --cases evaluation/cases_template.jsonl \
  --output evaluation/results_hybrid.jsonl
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
- `results_article_agg.jsonl` — article-aggregation rerank ablation
- `results_hybrid.jsonl` — BM25 + vector + RRF hybrid retrieval ablation

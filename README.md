---
title: Ask the News API
emoji: 📰
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# Ask the News

A production-shaped Retrieval-Augmented Generation (RAG) project over BBC News.
Read a featured story, ask grounded questions about it, and surface a horizontal
timeline of related coverage.

- Live frontend — https://ask-the-news-eta.vercel.app
- Backend API — https://mushroom18-ask-the-news.hf.space (FastAPI on HF Space Docker)
- Evaluation report — [`evaluation/README.md`](evaluation/README.md)

**Stack**: Next.js 16 · React 19 · Tailwind v4 · FastAPI · Postgres + pgvector
(Neon) · sentence-transformers · OpenAI Responses API · Docker on HF Space.
End-to-end deploys on free tiers — $0/mo to keep the live demo running.

## Why this project is interesting

- **Two-layer RAG data model.** `articles` (display, citations, timeline nodes)
  and `chunks` (retrieval units with `embedding vector(384)`) are first-class
  Postgres tables. A single SQL query joins them and runs cosine similarity
  via pgvector in one round trip.
- **Context router as a deliberate architectural piece.** A cheap `gpt-5-nano`
  classifier routes every question to *contextual* (rewrite the retrieval
  text with the current article's metadata) or *global* (use the bare
  question). Ablation: removing the router collapses hit@3 from **75% → 25%**
  on contextual queries.
- **Horizontal timeline with bucket-aware reranking.** Top-K chunks aggregate
  to articles, ISO-week buckets cap how many adjacent stories one news cycle
  can contribute, then `gpt-5-mini` rewrites each summary with strict JSON
  schema output.
- **Benchmarked.** 30 hand-curated cases × hard retrieval metrics
  (hit@k, MRR) × 5 dimensions of `gpt-5-mini` LLM-as-judge. Baseline numbers
  and two ablations live in [`evaluation/README.md`](evaluation/README.md).
- **Graceful fallbacks all the way down.** Router, QA, and timeline each fall
  back to a deterministic path when OpenAI is unavailable; the runtime
  backend falls back from Postgres to local SQLite + `.npy` when
  `DATABASE_URL` is unset; the frontend can short-circuit to in-process
  service calls when the API is unreachable.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Next.js 16 + Tailwind v4 on Vercel                      │
│    carousel · article reader · chat · timeline           │
└──────────────────────────────┬───────────────────────────┘
                               │ HTTPS / fetch
┌──────────────────────────────┴───────────────────────────┐
│  FastAPI on Hugging Face Space  (sdk: docker, port 7860) │
│    /featured  /article/{id}  /query  /timeline           │
│    sentence-transformers (CPU) · OpenAI Responses API    │
└──────────────────────────────┬───────────────────────────┘
                               │ psycopg + pgvector
┌──────────────────────────────┴───────────────────────────┐
│  Neon (serverless Postgres)                              │
│    articles · chunks(vector(384)) · ingestion_runs       │
└──────────────────────────────────────────────────────────┘
```

## Evaluation summary

Tested on 30 hand-curated cases (24 QA + 6 timeline), each carrying gold
`expected_article_ids` and rubric-style `expected_answer_points`. Scored with
hard retrieval metrics and `gpt-5-mini` LLM-as-judge (0–2 scale per dimension).

| Metric | Baseline | README target |
|---|---|---|
| hit@3 | **0.875** | ≥ 0.70 |
| hit@5 | 0.875 | ≥ 0.85 |
| MRR | **0.861** | ≥ 0.65 |
| Judge — answer groundedness | 1.90 / 2.00 | ≥ 1.7 |
| Judge — answer usefulness | 1.93 / 2.00 | ≥ 1.6 |
| Judge — citation support | 1.70 / 2.00 | ≥ 1.7 |
| Judge — timeline quality | 1.71 / 2.00 | ≥ 1.5 |

**Ablations**

- **Router off** — overall hit@3 drops 9.5%. On the 6-case contextual slice
  it drops **66.7%** (0.75 → 0.25). The router is the single highest-leverage
  component above vanilla vector search.
- **Chunk-size sweep** (`CHUNK_TARGET_WORDS ∈ {100, 150, 180, 220}`) — hit@3
  is **identical** across all four. Chunking is not a leverage point on this
  corpus; the next iteration should invest in hybrid retrieval and reranking
  instead.
- **Article-aggregation rerank** on the QA path — pulls a 3× candidate pool
  from pgvector, then reranks by article-level aggregate score
  (`top_chunk + 0.15 × second_chunk`). precision@5 lifts
  **0.347 → 0.465 (+34% relative)** and `answer_groundedness` ticks up to
  1.97 / 2.00. Gated by `ARTICLE_AGGREGATION=on` env var; opt-in until a
  cross-encoder reranker is added.

Full report (methodology, per-dimension tables, reproduce script):
[`evaluation/README.md`](evaluation/README.md).

## How it works

### Ingestion (offline)

1. Stream monthly subsets of
   [`RealTimeData/bbc_news_alltime`](https://huggingface.co/datasets/RealTimeData/bbc_news_alltime)
   into `data/sample_articles.json`. Article IDs are SHA-1 of the URL, so they
   are stable across backends.
2. **Paragraph-first chunking** ([`ingestion.py`](ask_the_news/ingestion.py)):
   respect existing paragraph boundaries first; split long paragraphs by
   sentence; merge under-sized paragraphs with neighbours; apply a small
   sentence-level overlap between adjacent chunks for context continuity.
3. Each chunk gets an enriched `embedding_text` —
   `Title / Section / Date / Description / Chunk body` — and is embedded with
   `sentence-transformers/all-MiniLM-L6-v2` (384-dim, L2-normalized).
4. Upsert articles + replace-all chunks per article in a single transaction
   ([`backends/postgres.py`](ask_the_news/backends/postgres.py)).

### Query (online)

1. **Guardrail** ([`query_router.py`](ask_the_news/query_router.py)) rejects
   empty queries and obviously context-dependent ones
   (`"what happened before this?"`) when no article is in focus.
2. **Router** (`gpt-5-nano`) classifies *contextual* vs *global*. Falls back
   to a keyword heuristic when OpenAI is unavailable.
3. **Retrieval**:
   ```sql
   SELECT chunk_id, article_id, ..., 1 - (embedding <=> $query) AS score
     FROM chunks
   ORDER BY embedding <=> $query
    LIMIT :top_k;
   ```
4. **Answering** (`gpt-5-mini`): strict instruction to use only the supplied
   excerpts; falls back to extractive snippet stitching if the API errors.
5. **Timeline**: top-K chunks → aggregate to articles → rank by best chunk
   score → bucket by ISO-week (or month) with a `MAX_PER_BUCKET` cap →
   `gpt-5-mini` rewrites each summary, JSON-schema constrained.

## Tech stack and rationale

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 16 + React 19 + Tailwind v4 | App Router server components for SSR; Vercel hobby tier free |
| Backend | FastAPI on uvicorn | Async, Pydantic types, free OpenAPI docs at `/docs` |
| Embeddings | `all-MiniLM-L6-v2` (384-d) | Hits ~85% of larger models' MTEB scores at a fraction of cost, runs on CPU |
| Vector store | Postgres 17 + pgvector | Relational + vector in one place; one SQL round trip per query |
| LLMs | `gpt-5-nano` (router) · `gpt-5-mini` (QA, timeline) | Cheap router separates from expensive answerer; both have deterministic fallbacks |
| Hosting | Vercel (frontend) · HF Space Docker (API) · Neon (DB) | $0/mo total for the live demo |

## Quick start (local dev)

```bash
# 0. Python env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 1. Configure (.env at repo root)
#    DATABASE_URL=postgresql://...?sslmode=require
#    OPENAI_API_KEY=sk-...
#    HF_DATASET_SUBSETS=2025-01,2025-02
#    MAX_ARTICLES=200

# 2. Pull a sample from the HF dataset
python -m ask_the_news.ingestion import-sample --limit 200

# 3. Bootstrap Postgres (creates pgvector + tables) and load data
python -m ask_the_news.admin init-db
python -m ask_the_news.admin sync-db

# 4. Run the API
uvicorn ask_the_news.api:app --reload --port 7860

# 5. Run the frontend (separate terminal, Node 20+)
cd frontend
npm install
echo 'NEXT_PUBLIC_API_BASE_URL=http://localhost:7860' > .env.local
npm run dev
# Open http://localhost:3000
```

If `DATABASE_URL` is unset, the project falls back to a local SQLite +
`.npy` backend ([`backends/local.py`](ask_the_news/backends/local.py)) so you
can iterate offline.

## API

Production base URL: `https://mushroom18-ask-the-news.hf.space`.

| Endpoint | Description |
|---|---|
| `GET /health` | `{status, index_ready}` |
| `GET /featured?limit=24` | latest articles for the carousel |
| `GET /article/{article_id}` | full article; used when clicking a timeline card |
| `POST /query` | `{question, current_article_id, top_k}` → `{message, citations, query_mode, ...}` |
| `POST /timeline` | `{question, current_article_id}` → `{items: TimelineItem[], ...}` |

Interactive schema at `/docs` (FastAPI auto-generated).

## Deployment

### Backend — HF Space (sdk: docker)

[`Dockerfile`](Dockerfile) prefetches the embedding model at build time so the
first user request doesn't pay the cold-start cost. Push to the `hf` remote
triggers a rebuild. Required Space secrets:

| Secret | What |
|---|---|
| `DATABASE_URL` | Postgres connection string (Neon or otherwise; `?sslmode=require`) |
| `OPENAI_API_KEY` | Drives the router, QA, and timeline calls |
| `CORS_ALLOW_ORIGINS` | Comma-separated allowed origins for the frontend |

### Frontend — Vercel

Root Directory: `frontend`. Env var `NEXT_PUBLIC_API_BASE_URL` points at the
HF Space URL. [`frontend/vercel.json`](frontend/vercel.json) pins
`framework: "nextjs"` so monorepo auto-detection doesn't fall back to
"Other" and break the `app/` router.

## Project layout

```
ask_the_news/
  admin.py            CLI: init-db, sync-db
  api.py              FastAPI app (CORS + 5 routes)
  backends/
    base.py           ArticleRepository / RetrievalBackend protocols
    local.py          SQLite + .npy backend (offline dev)
    postgres.py       pgvector backend (production)
  config.py           env var loading
  db.py               psycopg connection + schema bootstrap
  embeddings.py       sentence-transformers wrapper
  ingestion.py        HF dataset stream + paragraph-first chunking + CLI
  llm.py              gpt-5-mini QA + timeline, with extractive fallbacks
  models.py           dataclasses (Article, Chunk, QueryBundle, ...)
  query_router.py     gpt-5-nano router + heuristic fallback + guardrail
  retrieval.py        local brute-force vector search (used by local.py)
  service.py          NewsService: end-to-end orchestrator
  storage.py          SQLite storage helpers

frontend/             Next.js 16 app (App Router)
  app/page.tsx
  components/
    app-shell.tsx     selectedId state, lazy-fetch on click
    article-view.tsx  reader with "Continue reading" collapse
    carousel.tsx      featured strip
    chat-panel.tsx    chatbot + suggestion chips + unified input
    news-card.tsx     shared card (carousel + timeline)
    timeline.tsx      horizontal axis with alternating cards
  lib/
    api.ts            typed fetchers
    use-horizontal-wheel.ts   vertical wheel → horizontal scroll
  vercel.json         pins framework = nextjs

evaluation/
  README.md           full report (baseline + 2 ablations)
  cases_template.jsonl  30 hand-curated cases
  judge.py            run cases + LLM-as-judge
  metrics.py          hard retrieval metrics
  results_*.jsonl     reproducible run artifacts

sql/schema.sql        Postgres tables + pgvector extension
Dockerfile            HF Space (sdk: docker)
```

## Environment variables

Local development uses `.env` (gitignored). Production secrets go to HF Space +
Vercel.

### Required

- `DATABASE_URL` — Postgres connection string; if unset, the project falls
  back to the local SQLite + `.npy` backend
- `OPENAI_API_KEY` — router + QA + timeline LLM calls
- `HF_DATASET_SUBSETS` — comma-separated month tags (`2025-01,2025-02,...`),
  needed only during ingestion

### Tunable

```bash
MAX_ARTICLES=1500
CHUNK_TARGET_WORDS=180
CHUNK_OVERLAP_WORDS=40
CHUNK_MIN_WORDS=60
CHUNK_SPLIT_THRESHOLD=188
CHUNK_MAX_WORDS=220
RETRIEVAL_TOP_K=8
TIMELINE_RECALL_K=30
TIMELINE_MAX_ARTICLES=12
TIMELINE_MAX_PER_BUCKET=2
TIMELINE_BUCKET_GRANULARITY=week        # or "month"
QUERY_ROUTER_MODEL=gpt-5-nano
QA_MODEL=gpt-5-mini
TIMELINE_MODEL=gpt-5-mini
OPENAI_MAX_OUTPUT_TOKENS=700
OPENAI_REASONING_EFFORT=minimal
CORS_ALLOW_ORIGINS=http://localhost:3000,https://your-frontend.vercel.app
```

## Roadmap

- [ ] **Hybrid retrieval** — combine BM25 (`tsvector` GIN index) with pgvector
  using Reciprocal Rank Fusion; expected to lift lexical-precise queries
- [ ] **Cross-encoder reranker** on top-30 → top-8 to lift `citation_support`
  and `precision@5`
- [ ] **Auto-ingestion** — GitHub Actions cron pulls new monthly subsets and
  upserts to Postgres
- [ ] **Tests + CI** — unit tests for chunking edge cases, retrieval ranking,
  guardrail; GitHub Actions on every PR

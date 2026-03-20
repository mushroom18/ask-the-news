---
title: Ask the News
emoji: 📰
colorFrom: blue
colorTo: indigo
sdk: gradio
python_version: "3.10"
sdk_version: "5.22.0"
---

# Ask the News

The project has been reset to a clean starting point.

Current scope:

1. define the BBC article schema
2. implement paragraph-aware chunking
3. build a local RAG stack with QA and timeline pipelines
4. expose the backend over HTTP for deployment

## Data model

The project now uses a two-layer RAG data model:

### Article layer

The `Article` model is the canonical record for:

- featured story display
- article metadata filtering
- citations
- timeline nodes

Fields:

- `article_id`
- `title`
- `published_at`
- `authors`
- `description`
- `section`
- `content`
- `url`
- `top_image`
- `source`

### Chunk layer

The `Chunk` model is the retrieval unit for embedding search.

Fields:

- `chunk_id`
- `article_id`
- `title`
- `published_at`
- `description`
- `section`
- `url`
- `chunk_index`
- `text`
- `embedding_text`

`embedding_text` is intentionally different from `text`.
It is the enriched input used later for embeddings:

```text
Title
Section
Published date
Description
Chunk text
```

Design rules for `embedding_text`:

- include only retrieval-relevant fields
- skip empty fields
- keep a stable labeled format
- do not include `url` or `top_image`
- keep the original chunk body as the final and most important field

### Retrieval and generation models

The project also defines foundation models for later stages:

- `QueryBundle`
- `RetrievedChunk`
- `Citation`
- `TimelineItem`
- `QAContext`
- `TimelineContext`

These are not fully wired into retrieval yet, but they define the target contract for the QA pipeline and timeline pipeline.

## Current project structure

```text
ask_the_news/
  __init__.py
  app_logic.py
  api.py
  config.py
  embeddings.py
  ingestion.py
  llm.py
  models.py
  query_router.py
  retrieval.py
  service.py
  storage.py
app.py
data/sample_articles.json
requirements.txt
```

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Import a small BBC sample

First, point the project at one or more monthly subsets from the Hugging Face dataset:

```bash
export HF_DATASET_REPO=RealTimeData/bbc_news_alltime
export HF_DATASET_SUBSETS=2025-01,2025-02
export MAX_ARTICLES=30
```

Then import a small local sample:

```bash
python3 -m ask_the_news.ingestion import-sample --limit 30
```

This writes article records into `data/sample_articles.json`.
When multiple monthly subsets are configured, the importer now distributes the total article limit evenly across months instead of filling earlier months first.

## Preview chunking behavior

After importing the sample, inspect the paragraph-aware chunking output:

```bash
python3 -m ask_the_news.ingestion preview-chunks --limit 3
```

This prints, for a few sample articles:

- article title
- published date
- section
- number of generated chunks
- the first few chunk snippets and word counts

## SQLite storage v1

The project now has a minimal local storage layer for `articles` and `chunks`.

Write the current sample into SQLite:

```bash
python3 -m ask_the_news.ingestion sync-sqlite
```

This creates `data/news.db` and stores:

- `articles`
- `chunks`

## Retrieval v1

The first retrieval layer is designed as:

- SQLite for `articles` and `chunks`
- a local vector index for chunk embeddings
- query routing to choose `contextual` or `global`
- a query guardrail to block incomplete context-dependent questions

Planned modules:

- `query_router.py`
- `embeddings.py`
- `retrieval.py`

Build the local vector index:

```bash
python3 -m ask_the_news.retrieval build-index
```

Run a retrieval preview:

```bash
python3 -m ask_the_news.retrieval search "What happened before this?" --top-k 5
```

## Generation layer v1

The project now supports an OpenAI-backed generation layer with a cheap routing model and a stronger answer model:

- `QUERY_ROUTER_MODEL=gpt-5-nano`
- `QA_MODEL=gpt-5-mini`
- `TIMELINE_MODEL=gpt-5-mini`

If an OpenAI call fails, the app falls back to the current extractive answer and timeline output.

## Local backend and UI

The project now has a shared service layer and a FastAPI backend:

- `ask_the_news/service.py`
- `ask_the_news/api.py`
- `ask_the_news/backends/`

Run the backend locally:

```bash
uvicorn ask_the_news.api:app --reload
```

Run the Gradio UI:

```bash
python3 app.py
```

If `API_BASE_URL` is configured, the UI calls the HTTP backend.
If `API_BASE_URL` is empty, the UI falls back to local in-process service calls.

The backend now supports a pluggable backend mode:

- `BACKEND_MODE=local`
- `BACKEND_MODE=alloydb`

The AlloyDB backend is currently a stub. The abstraction is in place so the next step can focus on implementing the remote repository and retriever without rewriting the UI or API.

## Environment variables

```bash
export HF_DATASET_REPO=RealTimeData/bbc_news_alltime
export HF_DATASET_SUBSETS=2025-01,2025-02
export MAX_ARTICLES=50
export CHUNK_TARGET_WORDS=150
export CHUNK_OVERLAP_WORDS=40
export CHUNK_PREVIEW_LIMIT=3
export EMBEDDING_PREVIEW_CHARS=280
export CHUNK_MIN_WORDS=60
export CHUNK_SPLIT_THRESHOLD=188
export CHUNK_MAX_WORDS=220
export SQLITE_DB_PATH=data/news.db
export QUERY_ROUTER_MODEL=gpt-5-nano
export QA_MODEL=gpt-5-mini
export TIMELINE_MODEL=gpt-5-mini
export OPENAI_MAX_OUTPUT_TOKENS=700
export OPENAI_REASONING_EFFORT=minimal
export TIMELINE_RECALL_K=30
export TIMELINE_MAX_ARTICLES=12
export TIMELINE_MAX_PER_BUCKET=2
export TIMELINE_BUCKET_GRANULARITY=week
export API_BASE_URL=http://127.0.0.1:8000
export BACKEND_MODE=local
export ALLOYDB_DSN=
export ALLOYDB_INSTANCE_URI=
export ALLOYDB_DB=
export ALLOYDB_USER=
export ALLOYDB_PASSWORD=
export ALLOYDB_IP_TYPE=
export EMBEDDING_DIMENSION=384
```

For broader timeline coverage, use consecutive monthly subsets, for example:

```bash
export HF_DATASET_SUBSETS=2024-07,2024-08,2024-09,2024-10,2024-11,2024-12,2025-01,2025-02
export MAX_ARTICLES=1200
```

## Deployment direction

Recommended production split:

1. Hugging Face Space
   - hosts the Gradio UI
   - uses `API_BASE_URL` to call the backend over HTTPS

2. GCP backend
   - runs `ask_the_news.api:app`
   - owns retrieval, timeline generation, and LLM calls
   - connects to the long-term remote database and vector store

This avoids putting database credentials inside the Hugging Face Space and keeps the retrieval backend replaceable.

## AlloyDB schema v1

The first remote schema is defined in [sql/alloydb_schema.sql](/Users/yushu/projects/ask_the_news/sql/alloydb_schema.sql).

It uses three tables:

1. `articles`
   - canonical article records for featured stories, citations, and timeline rendering

2. `chunks`
   - chunk-level retrieval units with `embedding_text` and an `embedding` vector column

3. `ingestion_runs`
   - operational metadata for ingestion tracking

Design goals:

- support tens of thousands of articles and many more chunks
- keep article-level and chunk-level responsibilities separate
- allow later hybrid retrieval with metadata filters and text search
- delay vector ANN index tuning until the embedding pipeline is stable

The schema intentionally avoids event/entity tables for now.
Those can be added later without changing the core article/chunk contract.

## AlloyDB usage

The project now includes:

- `ask_the_news/alloydb.py`
- `ask_the_news/backends/alloydb.py`
- `ask_the_news/admin.py`

Initialize the remote schema:

```bash
python3 -m ask_the_news.admin init-alloydb
```

Sync the current local sample and chunks into AlloyDB:

```bash
python3 -m ask_the_news.admin sync-alloydb
```

Then switch the backend:

```bash
export BACKEND_MODE=alloydb
uvicorn ask_the_news.api:app --reload
python3 app.py
```

Important:

- the schema initializer replaces `VECTOR_DIMENSION` with `EMBEDDING_DIMENSION`
- the AlloyDB backend currently uses exact vector search through PostgreSQL/pgvector
- ANN index tuning and production-grade AlloyDB optimization still come later

## Deployment

### Cloud Run backend

The repository now includes [Dockerfile.backend](/Users/yushu/projects/ask_the_news/Dockerfile.backend) for the FastAPI backend.

If you prefer a container-first workflow:

```bash
gcloud builds submit --config deploy/cloudbuild.backend.yaml
gcloud run deploy ask-the-news-api \
  --image gcr.io/PROJECT_ID/ask-the-news-api \
  --region australia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars-file deploy/cloudrun.env.example.yaml
```

### Hugging Face Space

The root `README.md` now contains the YAML front matter needed for a Gradio Space.

For the Space:

1. push this repository to a Gradio Space
2. set `API_BASE_URL` in Space Secrets to your Cloud Run HTTPS URL
3. set `BACKEND_MODE=local` or leave it unset in the Space, because the Space should call the remote API, not connect to AlloyDB directly

The Space only needs the frontend path. The backend stays on GCP.

## What remains

1. validate the imported BBC sample fields against the dataset schema
2. tune paragraph-aware chunking after previewing real articles
3. build the first retrieval layer on top of SQLite article/chunk storage
4. build hybrid retrieval
5. add separate QA and timeline pipelines

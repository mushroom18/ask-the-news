-- Ask the News: Postgres + pgvector schema
-- Embedding dimension matches sentence-transformers/all-MiniLM-L6-v2 (384).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS articles (
    article_id   TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    published_at TEXT NOT NULL,
    authors_json TEXT NOT NULL DEFAULT '[]',
    description  TEXT NOT NULL DEFAULT '',
    section      TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL DEFAULT '',
    url          TEXT NOT NULL,
    top_image    TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL DEFAULT 'BBC News',
    content_hash TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_section      ON articles(section);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id       TEXT PRIMARY KEY,
    article_id     TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
    chunk_index    INTEGER NOT NULL,
    title          TEXT NOT NULL,
    published_at   TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    section        TEXT NOT NULL DEFAULT '',
    url            TEXT NOT NULL,
    text           TEXT NOT NULL,
    embedding_text TEXT NOT NULL,
    embedding      vector(384) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_article_id  ON chunks(article_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_index ON chunks(chunk_index);

-- Full-text search column for hybrid (BM25 + vector) retrieval.
-- ts is a STORED generated column so writes pay the cost once; the GIN
-- index makes `chunks WHERE ts @@ plainto_tsquery(...)` fast.
ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS ts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', text)) STORED;
CREATE INDEX IF NOT EXISTS idx_chunks_ts ON chunks USING GIN (ts);

-- ANN index deferred until the corpus stabilises; exact search is fine for the
-- current scale (tens of thousands of chunks). Enable when needed:
--   CREATE INDEX idx_chunks_embedding_hnsw
--     ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id                 SERIAL PRIMARY KEY,
    started_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at       TIMESTAMPTZ,
    articles_total     INTEGER NOT NULL DEFAULT 0,
    articles_inserted  INTEGER NOT NULL DEFAULT 0,
    articles_updated   INTEGER NOT NULL DEFAULT 0,
    chunks_total       INTEGER NOT NULL DEFAULT 0,
    notes              TEXT
);

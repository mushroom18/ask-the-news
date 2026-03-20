-- Ask the News: AlloyDB schema v1
--
-- This schema is designed for:
-- - tens of thousands of articles
-- - article-level UI, citations, and timeline rendering
-- - chunk-level vector retrieval for RAG
--
-- Notes:
-- - Replace VECTOR_DIMENSION with the final embedding dimension you choose.
-- - Apply AlloyDB AI vector indexing after the embedding pipeline is stable.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS articles (
    article_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'BBC News',
    title TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    authors_json TEXT NOT NULL DEFAULT '[]',
    section TEXT,
    description TEXT,
    content TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    top_image TEXT,
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding_text TEXT NOT NULL,
    token_count INTEGER,
    embedding VECTOR(VECTOR_DIMENSION),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (article_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id UUID PRIMARY KEY,
    source_name TEXT NOT NULL,
    subset_range TEXT,
    article_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_articles_published_at_desc
    ON articles (published_at DESC);

CREATE INDEX IF NOT EXISTS idx_articles_section_published_at_desc
    ON articles (section, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_articles_source_published_at_desc
    ON articles (source, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_chunks_article_id_chunk_index
    ON chunks (article_id, chunk_index);

-- Optional text-search starting point for later hybrid retrieval:
-- ALTER TABLE articles
-- ADD COLUMN search_document tsvector
-- GENERATED ALWAYS AS (
--     to_tsvector(
--         'english',
--         coalesce(title, '') || ' ' ||
--         coalesce(description, '') || ' ' ||
--         coalesce(content, '')
--     )
-- ) STORED;
--
-- CREATE INDEX idx_articles_search_document
--     ON articles
--     USING GIN (search_document);

-- Add a vector index later, after choosing recall/latency tradeoffs:
-- CREATE INDEX idx_chunks_embedding_scann
--     ON chunks
--     USING scann (embedding cosine)
--     WITH (num_leaves = 1000);

COMMIT;

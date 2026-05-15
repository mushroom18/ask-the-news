from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date

import numpy as np
from pgvector.psycopg import register_vector

from ask_the_news.backends.base import ArticleRepository, RetrievalBackend
from ask_the_news.config import (
    ARTICLE_AGGREGATION,
    ARTICLE_AGGREGATION_POOL_MULT,
    HYBRID_BM25_POOL,
    HYBRID_RETRIEVAL,
    HYBRID_RRF_K,
    HYBRID_VECTOR_POOL,
    RETRIEVAL_TOP_K,
    TIMELINE_BUCKET_GRANULARITY,
    TIMELINE_MAX_ARTICLES,
    TIMELINE_MAX_PER_BUCKET,
    TIMELINE_RECALL_K,
)
from ask_the_news.db import connect
from ask_the_news.embeddings import EmbeddingModel
from ask_the_news.models import (
    Article,
    Chunk,
    Citation,
    QAContext,
    QueryBundle,
    RetrievedChunk,
    TimelineContext,
    TimelineItem,
)
from ask_the_news.retrieval import article_aware_chunk_rerank


def _article_from_row(row: dict) -> Article:
    return Article(
        article_id=row["article_id"],
        title=row["title"],
        published_at=row["published_at"],
        authors=json.loads(row["authors_json"] or "[]"),
        description=row["description"],
        section=row["section"],
        content=row["content"],
        url=row["url"],
        top_image=row["top_image"],
        source=row["source"],
    )


def _chunk_from_row(row: dict) -> Chunk:
    return Chunk(
        chunk_id=row["chunk_id"],
        article_id=row["article_id"],
        title=row["title"],
        published_at=row["published_at"],
        description=row["description"],
        section=row["section"],
        url=row["url"],
        chunk_index=row["chunk_index"],
        text=row["text"],
        embedding_text=row["embedding_text"],
    )


_BM25_STOPWORDS = {
    "the", "and", "but", "with", "that", "this", "what", "when", "where",
    "who", "why", "how", "for", "from", "was", "were", "are", "did", "does",
    "has", "have", "had", "you", "your", "they", "them", "their", "she",
    "him", "his", "her", "its", "our", "any", "all", "some", "than",
}


def _build_bm25_or_query(query_text: str) -> str:
    """Turn a natural-language question into an OR-of-tokens query string
    suitable for `websearch_to_tsquery`. Drops stopwords and tokens shorter
    than 3 chars; returns "" if nothing useful is left, in which case the
    BM25 leg of the fusion contributes no candidates."""
    import re

    words = re.findall(r"[A-Za-z][A-Za-z']*", query_text.lower())
    keep = [w for w in words if len(w) > 2 and w not in _BM25_STOPWORDS]
    if not keep:
        return ""
    return " OR ".join(keep)


def _content_hash(article: Article) -> str:
    payload = "\n".join(
        [
            article.title,
            article.description,
            article.section,
            article.content,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PostgresArticleRepository(ArticleRepository):
    def featured_articles(self, limit: int = 24) -> list[Article]:
        with connect() as conn, conn.cursor(row_factory=psycopg_dict_row()) as cur:
            cur.execute(
                """
                SELECT article_id, title, published_at, authors_json, description,
                       section, content, url, top_image, source
                  FROM articles
                 ORDER BY published_at DESC, title ASC
                 LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [_article_from_row(row) for row in rows]

    def get_article(self, article_id: str) -> Article | None:
        if not article_id:
            return None
        with connect() as conn, conn.cursor(row_factory=psycopg_dict_row()) as cur:
            cur.execute(
                """
                SELECT article_id, title, published_at, authors_json, description,
                       section, content, url, top_image, source
                  FROM articles
                 WHERE article_id = %s
                """,
                (article_id,),
            )
            row = cur.fetchone()
        return _article_from_row(row) if row else None

    def list_articles_by_ids(self, article_ids: list[str]) -> list[Article]:
        if not article_ids:
            return []
        with connect() as conn, conn.cursor(row_factory=psycopg_dict_row()) as cur:
            cur.execute(
                """
                SELECT article_id, title, published_at, authors_json, description,
                       section, content, url, top_image, source
                  FROM articles
                 WHERE article_id = ANY(%s)
                """,
                (article_ids,),
            )
            rows = cur.fetchall()
        return [_article_from_row(row) for row in rows]

    def index_ready(self) -> bool:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM chunks LIMIT 1)")
            return bool(cur.fetchone()[0])

    def sync_articles_and_chunks(
        self,
        articles: list[Article],
        chunks: list[Chunk],
        embedder: EmbeddingModel,
    ) -> tuple[int, int]:
        if not articles:
            return 0, 0

        embedding_texts = [chunk.embedding_text for chunk in chunks]
        embeddings = embedder.encode_texts(embedding_texts) if embedding_texts else []
        embedding_vectors = [np.asarray(vec, dtype=np.float32) for vec in embeddings]

        chunks_by_article: dict[str, list[tuple[Chunk, np.ndarray]]] = defaultdict(list)
        for chunk, vector in zip(chunks, embedding_vectors):
            chunks_by_article[chunk.article_id].append((chunk, vector))

        articles_written = 0
        chunks_written = 0

        with connect() as conn, conn.cursor() as cur:
            for article in articles:
                cur.execute(
                    """
                    INSERT INTO articles (
                        article_id, title, published_at, authors_json, description,
                        section, content, url, top_image, source, content_hash, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                    ON CONFLICT (article_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        published_at = EXCLUDED.published_at,
                        authors_json = EXCLUDED.authors_json,
                        description = EXCLUDED.description,
                        section = EXCLUDED.section,
                        content = EXCLUDED.content,
                        url = EXCLUDED.url,
                        top_image = EXCLUDED.top_image,
                        source = EXCLUDED.source,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = NOW()
                    """,
                    (
                        article.article_id,
                        article.title,
                        article.published_at,
                        json.dumps(article.authors),
                        article.description,
                        article.section,
                        article.content,
                        article.url,
                        article.top_image,
                        article.source,
                        _content_hash(article),
                    ),
                )
                articles_written += 1

                cur.execute("DELETE FROM chunks WHERE article_id = %s", (article.article_id,))
                article_chunks = chunks_by_article.get(article.article_id, [])
                if not article_chunks:
                    continue
                cur.executemany(
                    """
                    INSERT INTO chunks (
                        chunk_id, article_id, chunk_index, title, published_at,
                        description, section, url, text, embedding_text, embedding
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    [
                        (
                            chunk.chunk_id,
                            chunk.article_id,
                            chunk.chunk_index,
                            chunk.title,
                            chunk.published_at,
                            chunk.description,
                            chunk.section,
                            chunk.url,
                            chunk.text,
                            chunk.embedding_text,
                            vector,
                        )
                        for chunk, vector in article_chunks
                    ],
                )
                chunks_written += len(article_chunks)

            conn.commit()

        return articles_written, chunks_written


class PostgresRetrievalBackend(RetrievalBackend):
    def __init__(
        self,
        repository: PostgresArticleRepository | None = None,
        embedder: EmbeddingModel | None = None,
    ) -> None:
        self.repository = repository or PostgresArticleRepository()
        self.embedder = embedder or EmbeddingModel()

    def _search(self, query: QueryBundle, top_k: int) -> list[RetrievedChunk]:
        if HYBRID_RETRIEVAL:
            return self._hybrid_search(query, top_k)
        return self._vector_search(query, top_k)

    def _vector_search(self, query: QueryBundle, top_k: int) -> list[RetrievedChunk]:
        query_vector = np.asarray(self.embedder.encode_query(query.retrieval_text()), dtype=np.float32)
        with connect() as conn, conn.cursor(row_factory=psycopg_dict_row()) as cur:
            cur.execute(
                """
                SELECT chunk_id, article_id, chunk_index, title, published_at,
                       description, section, url, text, embedding_text,
                       1 - (embedding <=> %s) AS score
                  FROM chunks
                 ORDER BY embedding <=> %s
                 LIMIT %s
                """,
                (query_vector, query_vector, top_k),
            )
            rows = cur.fetchall()

        results: list[RetrievedChunk] = []
        for rank, row in enumerate(rows, start=1):
            results.append(
                RetrievedChunk(
                    chunk=_chunk_from_row(row),
                    score=float(row["score"]),
                    rank=rank,
                )
            )
        return results

    def _hybrid_search(self, query: QueryBundle, top_k: int) -> list[RetrievedChunk]:
        """Hybrid retrieval: BM25 (Postgres tsvector) + pgvector cosine, fused via RRF.

        Reciprocal Rank Fusion: each candidate's final score is the sum of
        `1 / (k + rank)` across both lists. Candidates that rank well in
        either list survive; those that rank well in both rank highest.
        BM25 catches lexical-precise queries (proper nouns, dates) that
        pure vector search can miss; vector covers semantic paraphrases
        that bag-of-words misses.

        Note on the BM25 query: we build an OR-of-terms expression and parse
        it with `websearch_to_tsquery`. `plainto_tsquery` defaults to ANDing
        every token, which on natural-language questions ("what did X do on
        Y at start of 2025?") leaves zero matches once stopwords are stripped.
        """
        query_text = query.retrieval_text()
        query_vector = np.asarray(self.embedder.encode_query(query_text), dtype=np.float32)
        bm25_text = _build_bm25_or_query(query_text)
        sql = """
            WITH
              bm25 AS (
                SELECT chunk_id,
                       ROW_NUMBER() OVER (ORDER BY ts_rank_cd(ts, q) DESC) AS r
                  FROM chunks, websearch_to_tsquery('english', %s) AS q
                 WHERE %s <> '' AND ts @@ q
                 ORDER BY ts_rank_cd(ts, q) DESC
                 LIMIT %s
              ),
              vec AS (
                SELECT chunk_id, ROW_NUMBER() OVER () AS r FROM (
                  SELECT chunk_id FROM chunks
                   ORDER BY embedding <=> %s
                   LIMIT %s
                ) sub
              ),
              fused AS (
                SELECT chunk_id, SUM(1.0 / (%s::float + r)) AS rrf_score
                  FROM (SELECT chunk_id, r FROM bm25
                        UNION ALL
                        SELECT chunk_id, r FROM vec) u
                 GROUP BY chunk_id
              )
            SELECT c.chunk_id, c.article_id, c.chunk_index, c.title, c.published_at,
                   c.description, c.section, c.url, c.text, c.embedding_text,
                   f.rrf_score AS score
              FROM fused f
              JOIN chunks c ON c.chunk_id = f.chunk_id
             ORDER BY f.rrf_score DESC
             LIMIT %s
        """
        with connect() as conn, conn.cursor(row_factory=psycopg_dict_row()) as cur:
            cur.execute(
                sql,
                (
                    bm25_text,
                    bm25_text,
                    HYBRID_BM25_POOL,
                    query_vector,
                    HYBRID_VECTOR_POOL,
                    HYBRID_RRF_K,
                    top_k,
                ),
            )
            rows = cur.fetchall()

        results: list[RetrievedChunk] = []
        for rank, row in enumerate(rows, start=1):
            results.append(
                RetrievedChunk(
                    chunk=_chunk_from_row(row),
                    score=float(row["score"]),
                    rank=rank,
                )
            )
        return results

    def build_qa_context(self, query: QueryBundle, top_k: int = RETRIEVAL_TOP_K) -> QAContext:
        if ARTICLE_AGGREGATION:
            pool = self._search(query, top_k=top_k * ARTICLE_AGGREGATION_POOL_MULT)
            retrieved_chunks = article_aware_chunk_rerank(pool, top_k=top_k)
        else:
            retrieved_chunks = self._search(query, top_k=top_k)
        citations = self._citations(retrieved_chunks)
        return QAContext(query=query, retrieved_chunks=retrieved_chunks, citations=citations)

    def build_timeline_context(self, query: QueryBundle, top_k: int = RETRIEVAL_TOP_K) -> TimelineContext:
        retrieved_chunks = self._search(query, top_k=max(top_k, TIMELINE_RECALL_K))
        related_articles, items = self._timeline_candidates(retrieved_chunks)
        return TimelineContext(query=query, related_articles=related_articles, items=items)

    def _citations(self, retrieved_chunks: list[RetrievedChunk]) -> list[Citation]:
        article_ids: list[str] = []
        snippet_by_article: dict[str, str] = {}
        for item in retrieved_chunks:
            if item.chunk.article_id not in snippet_by_article:
                article_ids.append(item.chunk.article_id)
                snippet_by_article[item.chunk.article_id] = item.chunk.text[:240]

        articles = self.repository.list_articles_by_ids(article_ids)
        order = {article_id: idx for idx, article_id in enumerate(article_ids)}
        articles.sort(key=lambda article: order.get(article.article_id, 10**9))
        return [
            Citation(
                article_id=article.article_id,
                title=article.title,
                published_at=article.published_at,
                url=article.url,
                source=article.source,
                snippet=snippet_by_article.get(article.article_id, ""),
            )
            for article in articles
        ]

    def _timeline_candidates(
        self,
        retrieved_chunks: list[RetrievedChunk],
    ) -> tuple[list[Article], list[TimelineItem]]:
        if not retrieved_chunks:
            return [], []

        article_groups: dict[str, list[RetrievedChunk]] = defaultdict(list)
        for item in retrieved_chunks:
            article_groups[item.chunk.article_id].append(item)

        articles = self.repository.list_articles_by_ids(list(article_groups))
        articles_by_id = {article.article_id: article for article in articles}

        ranked_articles: list[dict] = []
        for article_id, matches in article_groups.items():
            article = articles_by_id.get(article_id)
            if article is None:
                continue
            ordered = sorted(matches, key=lambda item: item.score, reverse=True)
            top_scores = [item.score for item in ordered[:2]]
            score = top_scores[0] + (0.15 * top_scores[1] if len(top_scores) > 1 else 0)
            ranked_articles.append(
                {
                    "article": article,
                    "score": score,
                    "representative_text": ordered[0].chunk.text,
                }
            )

        ranked_articles.sort(
            key=lambda r: (-r["score"], r["article"].published_at, r["article"].title)
        )

        bucket_counts: dict[str, int] = defaultdict(int)
        selected: list[dict] = []
        for record in ranked_articles:
            bucket = _timeline_bucket(record["article"].published_at)
            if bucket_counts[bucket] >= TIMELINE_MAX_PER_BUCKET:
                continue
            selected.append(record)
            bucket_counts[bucket] += 1
            if len(selected) >= TIMELINE_MAX_ARTICLES:
                break

        if len(selected) < min(TIMELINE_MAX_ARTICLES, len(ranked_articles)):
            chosen_ids = {r["article"].article_id for r in selected}
            for record in ranked_articles:
                if record["article"].article_id in chosen_ids:
                    continue
                selected.append(record)
                if len(selected) >= TIMELINE_MAX_ARTICLES:
                    break

        selected.sort(
            key=lambda r: (r["article"].published_at, -r["score"], r["article"].title)
        )

        related_articles = [r["article"] for r in selected]
        items = [
            TimelineItem(
                article_id=r["article"].article_id,
                published_at=r["article"].published_at,
                title=r["article"].title,
                url=r["article"].url,
                source=r["article"].source,
                summary=(r["article"].description or r["representative_text"])[:240],
            )
            for r in selected
        ]
        return related_articles, items


def _timeline_bucket(published_at: str) -> str:
    try:
        parsed = date.fromisoformat(published_at[:10])
    except ValueError:
        return published_at[:7] or "unknown"
    if TIMELINE_BUCKET_GRANULARITY == "month":
        return f"{parsed.year:04d}-{parsed.month:02d}"
    iso_year, iso_week, _ = parsed.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def psycopg_dict_row():
    from psycopg.rows import dict_row

    return dict_row

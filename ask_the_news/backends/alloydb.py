from __future__ import annotations

import json
from pathlib import Path

from ask_the_news.alloydb import AlloyDBConnectionManager, execute_sql_script, fetch_all, vector_literal
from ask_the_news.backends.base import ArticleRepository, RetrievalBackend
from ask_the_news.config import EMBEDDING_DIMENSION, RETRIEVAL_TOP_K, TIMELINE_RECALL_K
from ask_the_news.embeddings import EmbeddingModel
from ask_the_news.models import Article, Chunk, Citation, QAContext, QueryBundle, RetrievedChunk, TimelineContext
from ask_the_news.retrieval import build_timeline_candidates, citations_from_chunks


class AlloyDBArticleRepository(ArticleRepository):
    def __init__(self, manager: AlloyDBConnectionManager | None = None, dsn: str = "") -> None:
        self.dsn = dsn
        self.manager = manager or AlloyDBConnectionManager()

    def init_schema(self, schema_path: Path) -> None:
        execute_sql_script(
            self.manager,
            schema_path,
            replacements={"VECTOR_DIMENSION": str(EMBEDDING_DIMENSION)},
        )

    def featured_articles(self, limit: int = 24) -> list[Article]:
        with self.manager.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT article_id, source, title, published_at, authors_json, section,
                       description, content, url, top_image
                FROM articles
                ORDER BY published_at DESC, title ASC
                LIMIT %s
                """,
                (limit,),
            )
            rows = fetch_all(cursor)
            cursor.close()
        return [article_from_row(row) for row in rows]

    def get_article(self, article_id: str) -> Article | None:
        if not article_id:
            return None
        with self.manager.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT article_id, source, title, published_at, authors_json, section,
                       description, content, url, top_image
                FROM articles
                WHERE article_id = %s
                """,
                (article_id,),
            )
            rows = fetch_all(cursor)
            cursor.close()
        if not rows:
            return None
        return article_from_row(rows[0])

    def list_articles_by_ids(self, article_ids: list[str]) -> list[Article]:
        if not article_ids:
            return []
        placeholders = ", ".join(["%s"] * len(article_ids))
        with self.manager.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT article_id, source, title, published_at, authors_json, section,
                       description, content, url, top_image
                FROM articles
                WHERE article_id IN ({placeholders})
                """,
                tuple(article_ids),
            )
            rows = fetch_all(cursor)
            cursor.close()
        order = {article_id: index for index, article_id in enumerate(article_ids)}
        articles = [article_from_row(row) for row in rows]
        return sorted(articles, key=lambda article: order.get(article.article_id, 10**9))

    def index_ready(self) -> bool:
        try:
            with self.manager.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM chunks WHERE embedding IS NOT NULL LIMIT 1")
                ready = cursor.fetchone() is not None
                cursor.close()
            return ready
        except Exception:
            return False

    def upsert_articles(self, articles: list[Article]) -> None:
        if not articles:
            return
        with self.manager.connect() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(
                    """
                    INSERT INTO articles (
                        article_id, source, title, published_at, authors_json, section,
                        description, content, url, top_image, content_hash
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                    ON CONFLICT (article_id) DO UPDATE SET
                        source = EXCLUDED.source,
                        title = EXCLUDED.title,
                        published_at = EXCLUDED.published_at,
                        authors_json = EXCLUDED.authors_json,
                        section = EXCLUDED.section,
                        description = EXCLUDED.description,
                        content = EXCLUDED.content,
                        url = EXCLUDED.url,
                        top_image = EXCLUDED.top_image,
                        updated_at = now()
                    """,
                    [
                        (
                            article.article_id,
                            article.source,
                            article.title,
                            article.published_at,
                            json.dumps(article.authors),
                            article.section,
                            article.description,
                            article.content,
                            article.url,
                            article.top_image,
                        )
                        for article in articles
                    ],
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

    def replace_chunks_for_article(self, article_id: str, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        with self.manager.connect() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM chunks WHERE article_id = %s", (article_id,))
                if chunks:
                    cursor.executemany(
                        """
                        INSERT INTO chunks (
                            chunk_id, article_id, chunk_index, chunk_text, embedding_text,
                            token_count, embedding
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                        """,
                        [
                            (
                                chunk.chunk_id,
                                chunk.article_id,
                                chunk.chunk_index,
                                chunk.text,
                                chunk.embedding_text,
                                len(chunk.embedding_text.split()),
                                vector_literal(embedding),
                            )
                            for chunk, embedding in zip(chunks, embeddings, strict=False)
                        ],
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

    def sync_articles_and_chunks(self, articles: list[Article], chunks: list[Chunk], embedder: EmbeddingModel | None = None) -> tuple[int, int]:
        if not articles:
            return 0, 0
        embedder = embedder or EmbeddingModel()
        self.upsert_articles(articles)

        grouped: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            grouped.setdefault(chunk.article_id, []).append(chunk)

        total_chunks = 0
        for article in articles:
            article_chunks = grouped.get(article.article_id, [])
            embeddings = embedder.encode_texts([chunk.embedding_text for chunk in article_chunks]) if article_chunks else []
            self.replace_chunks_for_article(article.article_id, article_chunks, embeddings)
            total_chunks += len(article_chunks)
        return len(articles), total_chunks


class AlloyDBRetrievalBackend(RetrievalBackend):
    def __init__(
        self,
        repository: AlloyDBArticleRepository | None = None,
        manager: AlloyDBConnectionManager | None = None,
        embedder: EmbeddingModel | None = None,
        dsn: str = "",
    ) -> None:
        self.dsn = dsn
        self.manager = manager or AlloyDBConnectionManager()
        self.repository = repository or AlloyDBArticleRepository(manager=self.manager)
        self.embedder = embedder or EmbeddingModel()

    def search(self, query: QueryBundle, top_k: int = RETRIEVAL_TOP_K) -> list[RetrievedChunk]:
        query_vector = self.embedder.encode_query(query.retrieval_text())
        vector = vector_literal(query_vector)
        with self.manager.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    c.chunk_id,
                    c.article_id,
                    c.chunk_index,
                    c.chunk_text,
                    c.embedding_text,
                    a.title,
                    a.published_at,
                    a.description,
                    a.section,
                    a.url,
                    (1 - (c.embedding <=> %s::vector)) AS score
                FROM chunks c
                JOIN articles a ON a.article_id = c.article_id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (vector, vector, top_k),
            )
            rows = fetch_all(cursor)
            cursor.close()

        results: list[RetrievedChunk] = []
        for rank, row in enumerate(rows, start=1):
            chunk = Chunk(
                chunk_id=row["chunk_id"],
                article_id=row["article_id"],
                title=row["title"],
                published_at=str(row["published_at"])[:10],
                description=row["description"] or "",
                section=row["section"] or "",
                url=row["url"] or "",
                chunk_index=row["chunk_index"],
                text=row["chunk_text"],
                embedding_text=row["embedding_text"],
            )
            results.append(RetrievedChunk(chunk=chunk, score=float(row["score"]), rank=rank))
        return results

    def build_qa_context(self, query: QueryBundle, top_k: int) -> QAContext:
        retrieved_chunks = self.search(query, top_k=top_k)
        citations = citations_from_chunks(retrieved_chunks, self.repository)
        return QAContext(query=query, retrieved_chunks=retrieved_chunks, citations=citations)

    def build_timeline_context(self, query: QueryBundle, top_k: int) -> TimelineContext:
        retrieved_chunks = self.search(query, top_k=max(top_k, TIMELINE_RECALL_K))
        related_articles, items = build_timeline_candidates(retrieved_chunks, self.repository)
        return TimelineContext(query=query, related_articles=related_articles, items=items)


def article_from_row(row: dict) -> Article:
    return Article(
        article_id=row["article_id"],
        title=row["title"],
        published_at=str(row["published_at"])[:10],
        authors=json.loads(row["authors_json"] or "[]"),
        description=row.get("description") or "",
        section=row.get("section") or "",
        content=row.get("content") or "",
        url=row.get("url") or "",
        top_image=row.get("top_image") or "",
        source=row.get("source") or "BBC News",
    )

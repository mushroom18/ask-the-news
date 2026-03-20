from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ask_the_news.config import SQLITE_DB_PATH
from ask_the_news.models import Article, Chunk


class SQLiteStorage:
    def __init__(self, db_path: Path = SQLITE_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    article_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    authors_json TEXT NOT NULL,
                    description TEXT NOT NULL,
                    section TEXT NOT NULL,
                    content TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    top_image TEXT NOT NULL,
                    source TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    article_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    description TEXT NOT NULL,
                    section TEXT NOT NULL,
                    url TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding_text TEXT NOT NULL,
                    FOREIGN KEY(article_id) REFERENCES articles(article_id)
                );

                CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
                CREATE INDEX IF NOT EXISTS idx_articles_section ON articles(section);
                CREATE INDEX IF NOT EXISTS idx_chunks_article_id ON chunks(article_id);
                CREATE INDEX IF NOT EXISTS idx_chunks_chunk_index ON chunks(chunk_index);
                """
            )

    def upsert_articles(self, articles: list[Article]) -> None:
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO articles (
                    article_id, title, published_at, authors_json, description,
                    section, content, url, top_image, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    title = excluded.title,
                    published_at = excluded.published_at,
                    authors_json = excluded.authors_json,
                    description = excluded.description,
                    section = excluded.section,
                    content = excluded.content,
                    url = excluded.url,
                    top_image = excluded.top_image,
                    source = excluded.source;
                """,
                [
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
                    )
                    for article in articles
                ],
            )

    def replace_chunks_for_article(self, article_id: str, chunks: list[Chunk]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM chunks WHERE article_id = ?", (article_id,))
            conn.executemany(
                """
                INSERT INTO chunks (
                    chunk_id, article_id, chunk_index, title, published_at,
                    description, section, url, text, embedding_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    )
                    for chunk in chunks
                ],
            )

    def sync_articles_and_chunks(self, articles: list[Article], chunks: list[Chunk]) -> None:
        self.init_schema()
        self.upsert_articles(articles)
        grouped: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            grouped.setdefault(chunk.article_id, []).append(chunk)
        for article in articles:
            self.replace_chunks_for_article(article.article_id, grouped.get(article.article_id, []))

    def list_articles(self, limit: int = 20) -> list[Article]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT article_id, title, published_at, authors_json, description,
                       section, content, url, top_image, source
                FROM articles
                ORDER BY published_at DESC, title ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            Article(
                article_id=row["article_id"],
                title=row["title"],
                published_at=row["published_at"],
                authors=json.loads(row["authors_json"]),
                description=row["description"],
                section=row["section"],
                content=row["content"],
                url=row["url"],
                top_image=row["top_image"],
                source=row["source"],
            )
            for row in rows
        ]

    def get_article(self, article_id: str) -> Article | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT article_id, title, published_at, authors_json, description,
                       section, content, url, top_image, source
                FROM articles
                WHERE article_id = ?
                """,
                (article_id,),
            ).fetchone()
        if row is None:
            return None
        return Article(
            article_id=row["article_id"],
            title=row["title"],
            published_at=row["published_at"],
            authors=json.loads(row["authors_json"]),
            description=row["description"],
            section=row["section"],
            content=row["content"],
            url=row["url"],
            top_image=row["top_image"],
            source=row["source"],
        )

    def get_chunks_for_article(self, article_id: str) -> list[Chunk]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT chunk_id, article_id, title, published_at, description,
                       section, url, chunk_index, text, embedding_text
                FROM chunks
                WHERE article_id = ?
                ORDER BY chunk_index ASC
                """,
                (article_id,),
            ).fetchall()
        return [
            Chunk(
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
            for row in rows
        ]

    def list_chunks(self) -> list[Chunk]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT chunk_id, article_id, title, published_at, description,
                       section, url, chunk_index, text, embedding_text
                FROM chunks
                ORDER BY article_id ASC, chunk_index ASC
                """
            ).fetchall()
        return [
            Chunk(
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
            for row in rows
        ]

    def list_chunks_by_ids(self, chunk_ids: list[str]) -> list[Chunk]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chunk_id, article_id, title, published_at, description,
                       section, url, chunk_index, text, embedding_text
                FROM chunks
                WHERE chunk_id IN ({placeholders})
                """,
                chunk_ids,
            ).fetchall()
        return [
            Chunk(
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
            for row in rows
        ]

    def list_articles_by_ids(self, article_ids: list[str]) -> list[Article]:
        if not article_ids:
            return []
        placeholders = ",".join("?" for _ in article_ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT article_id, title, published_at, authors_json, description,
                       section, content, url, top_image, source
                FROM articles
                WHERE article_id IN ({placeholders})
                """,
                article_ids,
            ).fetchall()
        return [
            Article(
                article_id=row["article_id"],
                title=row["title"],
                published_at=row["published_at"],
                authors=json.loads(row["authors_json"]),
                description=row["description"],
                section=row["section"],
                content=row["content"],
                url=row["url"],
                top_image=row["top_image"],
                source=row["source"],
            )
            for row in rows
        ]

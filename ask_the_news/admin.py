from __future__ import annotations

import argparse

from ask_the_news import db
from ask_the_news.backends.postgres import PostgresArticleRepository
from ask_the_news.config import BASE_DIR
from ask_the_news.embeddings import EmbeddingModel
from ask_the_news.ingestion import build_chunks, load_articles


def init_db() -> None:
    schema_path = BASE_DIR / "sql" / "schema.sql"
    db.init_schema(schema_path)
    print(f"Initialized Postgres schema from {schema_path}")


def sync_db() -> None:
    articles = load_articles()
    if not articles:
        print("No local articles found. Run `python -m ask_the_news.ingestion import-sample` first.")
        return
    chunks = build_chunks(articles)
    repository = PostgresArticleRepository()
    article_count, chunk_count = repository.sync_articles_and_chunks(
        articles, chunks, embedder=EmbeddingModel()
    )
    print(f"Synced {article_count} articles and {chunk_count} chunks into Postgres.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Administrative helpers for the Postgres backend.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize the Postgres schema (creates pgvector extension and tables).")
    subparsers.add_parser("sync-db", help="Sync local sample articles and chunks into Postgres.")

    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
        return

    if args.command == "sync-db":
        sync_db()


if __name__ == "__main__":
    main()

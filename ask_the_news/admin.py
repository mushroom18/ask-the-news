from __future__ import annotations

import argparse
from pathlib import Path

from ask_the_news.alloydb import AlloyDBConnectionManager
from ask_the_news.backends.alloydb import AlloyDBArticleRepository
from ask_the_news.config import BASE_DIR
from ask_the_news.embeddings import EmbeddingModel
from ask_the_news.ingestion import build_chunks, load_articles


def init_alloydb_schema() -> None:
    repository = AlloyDBArticleRepository(manager=AlloyDBConnectionManager())
    schema_path = BASE_DIR / "sql" / "alloydb_schema.sql"
    repository.init_schema(schema_path)
    print(f"Initialized AlloyDB schema from {schema_path}")


def sync_alloydb() -> None:
    articles = load_articles()
    chunks = build_chunks(articles)
    repository = AlloyDBArticleRepository(manager=AlloyDBConnectionManager())
    article_count, chunk_count = repository.sync_articles_and_chunks(articles, chunks, embedder=EmbeddingModel())
    print(f"Synced {article_count} articles and {chunk_count} chunks into AlloyDB.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Administrative helpers for Ask the News backends.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-alloydb", help="Initialize the AlloyDB schema.")
    subparsers.add_parser("sync-alloydb", help="Sync local sample articles and chunks into AlloyDB.")

    args = parser.parse_args()

    if args.command == "init-alloydb":
        init_alloydb_schema()
        return

    if args.command == "sync-alloydb":
        sync_alloydb()


if __name__ == "__main__":
    main()

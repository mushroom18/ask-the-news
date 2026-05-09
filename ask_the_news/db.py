from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector

from ask_the_news.config import DATABASE_URL


def is_configured() -> bool:
    return bool(DATABASE_URL)


@contextmanager
def _raw_connect() -> Iterator[psycopg.Connection]:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set; cannot open a Postgres connection.")
    with psycopg.connect(DATABASE_URL) as conn:
        yield conn


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with _raw_connect() as conn:
        register_vector(conn)
        yield conn


def init_schema(schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    with _raw_connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()

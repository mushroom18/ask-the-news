from __future__ import annotations

from pathlib import Path
from typing import Any

from ask_the_news.config import ALLOYDB_DB, ALLOYDB_INSTANCE_URI, ALLOYDB_IP_TYPE, ALLOYDB_PASSWORD, ALLOYDB_USER


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


class AlloyDBConnectionManager:
    def __init__(
        self,
        instance_uri: str = ALLOYDB_INSTANCE_URI,
        db: str = ALLOYDB_DB,
        user: str = ALLOYDB_USER,
        password: str = ALLOYDB_PASSWORD,
        ip_type: str = ALLOYDB_IP_TYPE,
    ) -> None:
        self.instance_uri = instance_uri
        self.db = db
        self.user = user
        self.password = password
        self.ip_type = ip_type
        self._connector = None

    def _ensure_connector(self):
        if self._connector is not None:
            return self._connector
        from google.cloud.alloydbconnector import Connector

        self._connector = Connector(refresh_strategy="background")
        return self._connector

    def _connector_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "user": self.user,
            "password": self.password,
            "db": self.db,
        }
        if self.ip_type:
            from google.cloud.alloydbconnector import IPTypes

            ip_map = {
                "public": IPTypes.PUBLIC,
                "psc": IPTypes.PSC,
                "private": IPTypes.PRIVATE,
            }
            if self.ip_type in ip_map:
                kwargs["ip_type"] = ip_map[self.ip_type]
        return kwargs

    def connect(self):
        connector = self._ensure_connector()
        return connector.connect(
            self.instance_uri,
            "pg8000",
            **self._connector_kwargs(),
        )

    def close(self) -> None:
        if self._connector is not None:
            self._connector.close()
            self._connector = None


def execute_sql_script(manager: AlloyDBConnectionManager, path: Path, replacements: dict[str, str] | None = None) -> None:
    sql = path.read_text(encoding="utf-8")
    for key, value in (replacements or {}).items():
        sql = sql.replace(key, value)

    statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
    with manager.connect() as conn:
        cursor = conn.cursor()
        try:
            for statement in statements:
                normalized = statement.strip().strip(";").upper()
                if normalized in {"BEGIN", "COMMIT"}:
                    continue
                try:
                    cursor.execute(statement)
                    conn.commit()
                except Exception as exc:
                    conn.rollback()
                    if is_vector_extension_permission_error(statement, exc):
                        if vector_extension_exists(cursor):
                            continue
                        raise RuntimeError(
                            "The database user cannot create the pgvector extension, and the extension is not "
                            "installed yet. Connect with an administrative user and run "
                            "`CREATE EXTENSION vector;` once, then rerun `python3 -m ask_the_news.admin init-alloydb`."
                        ) from exc
                    raise
        except Exception:
            raise
        finally:
            cursor.close()


def is_vector_extension_permission_error(statement: str, exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "create extension" in statement.lower()
        and "vector" in statement.lower()
        and "permission denied" in text
    )


def vector_extension_exists(cursor) -> bool:
    cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
    row = cursor.fetchone()
    return bool(row and row[0])


def fetch_all(cursor) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description or []]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]

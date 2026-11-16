"""Postgres access: a connection pool and three small helpers. Every statement runs in autocommit mode."""

from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import config

pool = ConnectionPool(
    config.DATABASE_URL,
    min_size=1,
    max_size=20,
    open=False,
    kwargs={"autocommit": True, "row_factory": dict_row},
)


def query(sql: str, params: Any = ()) -> list[dict[str, Any]]:
    """Runs a statement and returns its rows (empty list if it returns none)."""
    with pool.connection() as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchall() if cursor.description else []


def query_one(sql: str, params: Any = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Any = ()) -> int:
    """Runs a statement and returns how many rows it changed."""
    with pool.connection() as conn:
        return conn.execute(sql, params).rowcount


def init_schema() -> None:
    with pool.connection() as conn:
        conn.execute(Path(__file__).with_name("schema.sql").read_text())

"""PostgreSQL connection helpers using native SQL via psycopg2."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection

from src.app.core.config import Settings, get_settings
from src.app.core.exceptions import ConfigurationError, DatabaseError, SchemaMismatchError

# Expected tables in the normalized movies schema.
REQUIRED_TABLES = (
    "titles",
    "content_types",
    "ratings",
    "directors",
    "cast_members",
    "countries",
    "genres",
    "title_directors",
    "title_cast",
    "title_countries",
    "title_genres",
)

REQUIRED_TITLE_COLUMNS = (
    "show_id",
    "title",
    "type_id",
    "release_year",
    "rating_id",
    "date_added",
    "duration_value",
    "duration_unit",
    "description",
)


def _connect(settings: Settings) -> PgConnection:
    if not settings.db_password:
        raise ConfigurationError("DB_PASSWORD environment variable is required.")
    try:
        conn = psycopg2.connect(settings.dsn)
        conn.autocommit = True
        return conn
    except psycopg2.Error as exc:
        raise DatabaseError(f"Failed to connect to PostgreSQL: {exc}") from exc


def _fetch_all(
    settings: Settings,
    query: str,
    params: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    conn = _connect(settings)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params or ())
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    except psycopg2.Error as exc:
        raise DatabaseError(f"Query failed: {exc}") from exc
    finally:
        conn.close()


async def fetch_all(
    query: str,
    params: Sequence[Any] | None = None,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Execute a SELECT and return rows as dictionaries (non-blocking)."""
    cfg = settings or get_settings()
    return await asyncio.to_thread(_fetch_all, cfg, query, params)


def verify_schema(settings: Settings | None = None) -> None:
    """Ensure the configured schema and required tables/columns exist.

    Raises SchemaMismatchError when the database shape does not match
    what the API expects.
    """
    cfg = settings or get_settings()
    schema = cfg.db_schema

    missing_tables_sql = """
        SELECT required.table_name
        FROM unnest(%s::text[]) AS required(table_name)
        LEFT JOIN information_schema.tables t
          ON t.table_schema = %s
         AND t.table_name = required.table_name
        WHERE t.table_name IS NULL
        ORDER BY required.table_name
    """
    missing = _fetch_all(cfg, missing_tables_sql, (list(REQUIRED_TABLES), schema))
    if missing:
        names = ", ".join(row["table_name"] for row in missing)
        raise SchemaMismatchError(
            f"Schema '{schema}' is missing required table(s): {names}"
        )

    missing_cols_sql = """
        SELECT required.column_name
        FROM unnest(%s::text[]) AS required(column_name)
        LEFT JOIN information_schema.columns c
          ON c.table_schema = %s
         AND c.table_name = 'titles'
         AND c.column_name = required.column_name
        WHERE c.column_name IS NULL
        ORDER BY required.column_name
    """
    missing_cols = _fetch_all(
        cfg, missing_cols_sql, (list(REQUIRED_TITLE_COLUMNS), schema)
    )
    if missing_cols:
        names = ", ".join(row["column_name"] for row in missing_cols)
        raise SchemaMismatchError(
            f"Table '{schema}.titles' is missing required column(s): {names}"
        )

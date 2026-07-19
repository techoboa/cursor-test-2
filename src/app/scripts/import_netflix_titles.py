"""Ingest netflix_titles.csv into a normalized (3NF) PostgreSQL schema.

Usage:
    python import_netflix_titles.py

Connection parameters are read from environment variables (see below) so that
credentials never need to be hardcoded or committed:
    DB_HOST      (default: localhost)
    DB_PORT      (default: 5432)
    DB_NAME      (default: netflix)
    DB_SCHEMA    (default: movies)
    DB_USER      (default: postgres)
    DB_PASSWORD  (required)

Design:
    Dimension/lookup tables (content_types, ratings, countries, genres,
    directors, cast_members) are populated first from the full set of
    distinct values found in the CSV. Their generated ids are then used to
    populate the `titles` fact table and its many-to-many junction tables
    (title_directors, title_cast, title_countries, title_genres).

    The CSV is streamed row-by-row via csv.DictReader (never loaded fully
    into memory) and processed in two passes: pass 1 collects distinct
    dimension values, pass 2 builds and bulk-inserts fact/junction rows in
    chunks. The entire ingestion runs inside a single transaction that is
    rolled back on any failure.
"""

from __future__ import annotations

import csv
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import execute_values

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "netflix_titles.csv"
CHUNK_SIZE = 500

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "netflix")
DB_SCHEMA = os.environ.get("DB_SCHEMA", "movies")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

_DURATION_RE = re.compile(r"^\s*(\d+)\s*(min|season|seasons)\s*$", re.IGNORECASE)
_RATING_LIKE_DURATION_RE = re.compile(r"^\s*\d+\s*min\s*$", re.IGNORECASE)


def ensure_database() -> None:
    """Create the target database if it does not already exist."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname="postgres", user=DB_USER, password=DB_PASSWORD
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{DB_NAME}"')
    finally:
        conn.close()


def connect_target() -> PgConnection:
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )


def create_schema_and_tables(conn: PgConnection) -> None:
    s = DB_SCHEMA
    with conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{s}"')

        # Dimension/lookup tables (created first, deterministic order).
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".cast_members (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".content_types (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".countries (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".directors (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".genres (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".ratings (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL UNIQUE
            )
        """)

        # Fact table.
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".titles (
                show_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                type_id INTEGER NOT NULL REFERENCES "{s}".content_types(id),
                release_year INTEGER,
                rating_id INTEGER REFERENCES "{s}".ratings(id),
                date_added DATE,
                duration_value INTEGER,
                duration_unit TEXT,
                description TEXT
            )
        """)

        # Many-to-many junction tables.
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".title_cast (
                show_id TEXT REFERENCES "{s}".titles(show_id) ON DELETE CASCADE,
                cast_member_id INTEGER REFERENCES "{s}".cast_members(id),
                PRIMARY KEY (show_id, cast_member_id)
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".title_countries (
                show_id TEXT REFERENCES "{s}".titles(show_id) ON DELETE CASCADE,
                country_id INTEGER REFERENCES "{s}".countries(id),
                PRIMARY KEY (show_id, country_id)
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".title_directors (
                show_id TEXT REFERENCES "{s}".titles(show_id) ON DELETE CASCADE,
                director_id INTEGER REFERENCES "{s}".directors(id),
                PRIMARY KEY (show_id, director_id)
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{s}".title_genres (
                show_id TEXT REFERENCES "{s}".titles(show_id) ON DELETE CASCADE,
                genre_id INTEGER REFERENCES "{s}".genres(id),
                PRIMARY KEY (show_id, genre_id)
            )
        """)


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def split_multi(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def fix_rating_duration(rating: str | None, duration: str | None) -> tuple[str | None, str | None]:
    """Some source rows have the duration value shifted into the rating column."""
    if rating and _RATING_LIKE_DURATION_RE.match(rating) and not duration:
        return None, rating
    return rating, duration


def parse_date_added(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%B %d, %Y").date()
    except ValueError:
        return None


def parse_duration(value: str | None) -> tuple[int | None, str | None]:
    if not value:
        return None, None
    m = _DURATION_RE.match(value)
    if not m:
        return None, None
    amount, unit = m.groups()
    unit = "min" if unit.lower() == "min" else "season"
    return int(amount), unit


def parse_release_year(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def iter_rows():
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield row


def upsert_lookup_batch(cur, schema: str, table: str, column: str, values: set[str]) -> dict[str, int]:
    """Bulk upsert distinct values into a lookup table and return name -> id map."""
    if not values:
        return {}
    rows = [(v,) for v in sorted(values)]
    query = (
        f'INSERT INTO "{schema}".{table} ({column}) VALUES %s '
        f"ON CONFLICT ({column}) DO NOTHING"
    )
    execute_values(cur, query, rows)
    cur.execute(f'SELECT id, {column} FROM "{schema}".{table} WHERE {column} = ANY(%s)', (list(values),))
    return {name: id_ for id_, name in cur.fetchall()}


def run_import() -> None:
    if not DB_PASSWORD:
        raise SystemExit("DB_PASSWORD environment variable is required.")
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV file not found: {CSV_PATH}")

    print(f"Connecting to postgres://{DB_USER}:***@{DB_HOST}:{DB_PORT}/{DB_NAME} ...")
    ensure_database()
    conn = connect_target()
    print("Connection successful.")

    try:
        create_schema_and_tables(conn)

        # ---- Pass 1: collect distinct dimension values (streaming) ----
        types: set[str] = set()
        ratings: set[str] = set()
        countries: set[str] = set()
        genres: set[str] = set()
        directors: set[str] = set()
        cast_members: set[str] = set()

        row_count = 0
        for row in iter_rows():
            row_count += 1
            rating, _ = fix_rating_duration(clean(row.get("rating")), clean(row.get("duration")))
            types.add(clean(row.get("type")) or "Unknown")
            if rating:
                ratings.add(rating)
            countries.update(split_multi(row.get("country")))
            genres.update(split_multi(row.get("listed_in")))
            directors.update(split_multi(row.get("director")))
            cast_members.update(split_multi(row.get("cast")))

        with conn.cursor() as cur:
            type_ids = upsert_lookup_batch(cur, DB_SCHEMA, "content_types", "name", types)
            rating_ids = upsert_lookup_batch(cur, DB_SCHEMA, "ratings", "code", ratings)
            country_ids = upsert_lookup_batch(cur, DB_SCHEMA, "countries", "name", countries)
            genre_ids = upsert_lookup_batch(cur, DB_SCHEMA, "genres", "name", genres)
            director_ids = upsert_lookup_batch(cur, DB_SCHEMA, "directors", "name", directors)
            cast_ids = upsert_lookup_batch(cur, DB_SCHEMA, "cast_members", "name", cast_members)

        print(
            f"Dimensions loaded: {len(type_ids)} types, {len(rating_ids)} ratings, "
            f"{len(country_ids)} countries, {len(genre_ids)} genres, "
            f"{len(director_ids)} directors, {len(cast_ids)} cast members."
        )

        # ---- Pass 2: build fact + junction rows, insert in chunks ----
        title_rows: list[tuple] = []
        director_links: list[tuple] = []
        cast_links: list[tuple] = []
        country_links: list[tuple] = []
        genre_links: list[tuple] = []
        seen_show_ids: set[str] = set()

        def flush(cur) -> None:
            if title_rows:
                execute_values(
                    cur,
                    f'INSERT INTO "{DB_SCHEMA}".titles '
                    "(show_id, title, type_id, release_year, rating_id, date_added, "
                    "duration_value, duration_unit, description) VALUES %s "
                    "ON CONFLICT (show_id) DO NOTHING",
                    title_rows,
                )
                title_rows.clear()
            for table, column, links in (
                ("title_directors", "director_id", director_links),
                ("title_cast", "cast_member_id", cast_links),
                ("title_countries", "country_id", country_links),
                ("title_genres", "genre_id", genre_links),
            ):
                if links:
                    execute_values(
                        cur,
                        f'INSERT INTO "{DB_SCHEMA}".{table} (show_id, {column}) VALUES %s '
                        "ON CONFLICT DO NOTHING",
                        links,
                    )
                    links.clear()

        with conn.cursor() as cur:
            for row in iter_rows():
                show_id = clean(row.get("show_id"))
                if not show_id or show_id in seen_show_ids:
                    continue
                seen_show_ids.add(show_id)

                rating, duration = fix_rating_duration(
                    clean(row.get("rating")), clean(row.get("duration"))
                )
                duration_value, duration_unit = parse_duration(duration)
                type_name = clean(row.get("type")) or "Unknown"

                title_rows.append((
                    show_id,
                    clean(row.get("title")),
                    type_ids[type_name],
                    parse_release_year(row.get("release_year")),
                    rating_ids.get(rating) if rating else None,
                    parse_date_added(row.get("date_added")),
                    duration_value,
                    duration_unit,
                    clean(row.get("description")),
                ))

                for name in split_multi(row.get("director")):
                    director_links.append((show_id, director_ids[name]))
                for name in split_multi(row.get("cast")):
                    cast_links.append((show_id, cast_ids[name]))
                for name in split_multi(row.get("country")):
                    country_links.append((show_id, country_ids[name]))
                for name in split_multi(row.get("listed_in")):
                    genre_links.append((show_id, genre_ids[name]))

                if len(title_rows) >= CHUNK_SIZE:
                    flush(cur)

            flush(cur)

        conn.commit()
        print(f"Import complete. {len(seen_show_ids)} of {row_count} rows committed to schema '{DB_SCHEMA}'.")
    except Exception:
        conn.rollback()
        print("Import failed, transaction rolled back.", file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_import()

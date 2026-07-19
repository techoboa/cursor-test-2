"""Business logic for fetching movie titles from PostgreSQL."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.app.core.config import Settings, get_settings
from src.app.core.database import fetch_all
from src.app.core.exceptions import SchemaMismatchError
from src.app.schemas.titles import MovieTitle, MovieTitleListResponse

MOVIE_TYPE_NAME = "Movie"


def _movies_query(schema: str) -> str:
    # Native SQL — reconstructs full title details with related arrays.
    return f"""
        WITH directors_agg AS (
            SELECT td.show_id,
                   COALESCE(
                       array_agg(d.name ORDER BY d.name) FILTER (WHERE d.name IS NOT NULL),
                       ARRAY[]::text[]
                   ) AS directors
            FROM "{schema}".title_directors td
            JOIN "{schema}".directors d ON d.id = td.director_id
            GROUP BY td.show_id
        ),
        cast_agg AS (
            SELECT tc.show_id,
                   COALESCE(
                       array_agg(cm.name ORDER BY cm.name)
                           FILTER (WHERE cm.name IS NOT NULL),
                       ARRAY[]::text[]
                   ) AS cast_members
            FROM "{schema}".title_cast tc
            JOIN "{schema}".cast_members cm ON cm.id = tc.cast_member_id
            GROUP BY tc.show_id
        ),
        countries_agg AS (
            SELECT tco.show_id,
                   COALESCE(
                       array_agg(c.name ORDER BY c.name)
                           FILTER (WHERE c.name IS NOT NULL),
                       ARRAY[]::text[]
                   ) AS countries
            FROM "{schema}".title_countries tco
            JOIN "{schema}".countries c ON c.id = tco.country_id
            GROUP BY tco.show_id
        ),
        genres_agg AS (
            SELECT tg.show_id,
                   COALESCE(
                       array_agg(g.name ORDER BY g.name)
                           FILTER (WHERE g.name IS NOT NULL),
                       ARRAY[]::text[]
                   ) AS genres
            FROM "{schema}".title_genres tg
            JOIN "{schema}".genres g ON g.id = tg.genre_id
            GROUP BY tg.show_id
        )
        SELECT
            t.show_id,
            t.title,
            ct.name AS type,
            t.release_year,
            r.code AS rating,
            t.date_added,
            t.duration_value,
            t.duration_unit,
            t.description,
            COALESCE(da.directors, ARRAY[]::text[]) AS directors,
            COALESCE(ca.cast_members, ARRAY[]::text[]) AS cast,
            COALESCE(coa.countries, ARRAY[]::text[]) AS countries,
            COALESCE(ga.genres, ARRAY[]::text[]) AS genres
        FROM "{schema}".titles t
        JOIN "{schema}".content_types ct ON ct.id = t.type_id
        LEFT JOIN "{schema}".ratings r ON r.id = t.rating_id
        LEFT JOIN directors_agg da ON da.show_id = t.show_id
        LEFT JOIN cast_agg ca ON ca.show_id = t.show_id
        LEFT JOIN countries_agg coa ON coa.show_id = t.show_id
        LEFT JOIN genres_agg ga ON ga.show_id = t.show_id
        WHERE ct.name = %s
        ORDER BY t.show_id
    """


def _row_to_movie(row: dict[str, Any]) -> MovieTitle:
    """Validate a DB row against the response schema; error on mismatch."""
    payload = {
        "show_id": row.get("show_id"),
        "title": row.get("title"),
        "type": row.get("type"),
        "release_year": row.get("release_year"),
        "rating": row.get("rating"),
        "date_added": row.get("date_added"),
        "duration_value": row.get("duration_value"),
        "duration_unit": row.get("duration_unit"),
        "description": row.get("description"),
        "directors": list(row.get("directors") or []),
        "cast": list(row.get("cast") or []),
        "countries": list(row.get("countries") or []),
        "genres": list(row.get("genres") or []),
    }
    try:
        return MovieTitle.model_validate(payload)
    except ValidationError as exc:
        show_id = row.get("show_id", "<unknown>")
        raise SchemaMismatchError(
            f"Row for show_id={show_id} does not match MovieTitle schema: {exc}"
        ) from exc


async def get_all_movie_titles(
    settings: Settings | None = None,
) -> MovieTitleListResponse:
    """Return every movie title with full related details."""
    cfg = settings or get_settings()
    rows = await fetch_all(_movies_query(cfg.db_schema), (MOVIE_TYPE_NAME,), settings=cfg)

    titles: list[MovieTitle] = []
    for row in rows:
        titles.append(_row_to_movie(row))

    return MovieTitleListResponse(count=len(titles), titles=titles)

"""Unit tests for movie title schema validation."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from src.app.core.exceptions import SchemaMismatchError
from src.app.schemas.titles import MovieTitle, MovieTitleListResponse
from src.app.services.titles import _row_to_movie


def test_movie_title_schema_accepts_valid_row() -> None:
    movie = _row_to_movie(
        {
            "show_id": "s1",
            "title": "Example",
            "type": "Movie",
            "release_year": 2020,
            "rating": "PG-13",
            "date_added": date(2021, 1, 1),
            "duration_value": 90,
            "duration_unit": "min",
            "description": "A film.",
            "directors": ["Ada"],
            "cast": ["Bob"],
            "countries": ["United States"],
            "genres": ["Dramas"],
        }
    )
    assert movie.show_id == "s1"
    assert movie.directors == ["Ada"]


def test_movie_title_schema_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        MovieTitle.model_validate(
            {
                "show_id": "s1",
                "title": "Example",
                "type": "Movie",
                "unexpected": True,
            }
        )


def test_row_to_movie_errors_on_schema_mismatch() -> None:
    with pytest.raises(SchemaMismatchError):
        _row_to_movie(
            {
                "show_id": "s1",
                "title": "Example",
                "type": "Movie",
                "release_year": "not-an-int",
            }
        )


def test_list_response_envelope() -> None:
    payload = MovieTitleListResponse(
        count=1,
        titles=[
            MovieTitle(show_id="s1", title="Example", type="Movie"),
        ],
    )
    assert payload.count == 1
    assert payload.titles[0].title == "Example"

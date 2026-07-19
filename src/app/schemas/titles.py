"""Pydantic schemas for movie title API responses."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class MovieTitle(BaseModel):
    """Full detail for a single movie title from the normalized schema."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    show_id: str
    title: str
    type: str = Field(description="Content type; always 'Movie' for this endpoint.")
    release_year: int | None = None
    rating: str | None = None
    date_added: date | None = None
    duration_value: int | None = None
    duration_unit: str | None = None
    description: str | None = None
    directors: list[str] = Field(default_factory=list)
    cast: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)


class MovieTitleListResponse(BaseModel):
    """Envelope for the list-all-movies endpoint."""

    model_config = ConfigDict(extra="forbid")

    count: int
    titles: list[MovieTitle]

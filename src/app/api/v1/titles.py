"""Movie titles API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.app.core.config import Settings, get_settings
from src.app.core.rate_limit import limiter
from src.app.schemas.titles import MovieTitleListResponse
from src.app.services import titles as titles_service

router = APIRouter(prefix="/movies", tags=["movies"])


@router.get(
    "",
    response_model=MovieTitleListResponse,
    summary="List all movie titles with full details",
)
@limiter.limit(get_settings().rate_limit)
async def list_movie_titles(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> MovieTitleListResponse:
    """Return all movie titles from the database, including related entities."""
    return await titles_service.get_all_movie_titles(settings=settings)

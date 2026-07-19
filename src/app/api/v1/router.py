"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from src.app.api.v1 import titles

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(titles.router)

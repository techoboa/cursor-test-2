"""Shared rate limiter for the API."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from src.app.core.config import get_settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[get_settings().rate_limit],
)

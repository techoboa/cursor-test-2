"""Domain exceptions raised by the service layer."""

from __future__ import annotations


class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DatabaseError(AppError):
    """Raised when a database operation fails."""


class SchemaMismatchError(AppError):
    """Raised when DB rows or schema do not match the expected API contract."""


class ConfigurationError(AppError):
    """Raised when required configuration is missing or invalid."""

"""FastAPI application entrypoint.

Serves HTTPS with a self-signed certificate on port 8445 by default.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.app.api.v1.router import api_router
from src.app.core.config import get_settings
from src.app.core.database import verify_schema
from src.app.core.exceptions import AppError, ConfigurationError, DatabaseError, SchemaMismatchError
from src.app.core.rate_limit import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    try:
        verify_schema(settings)
        logger.info("Database schema '%s' verified.", settings.db_schema)
    except (ConfigurationError, DatabaseError, SchemaMismatchError) as exc:
        # Fail fast when the DB shape/config does not match the API contract.
        logger.error("Startup schema check failed: %s", exc.message)
        raise
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    application.add_middleware(SlowAPIMiddleware)

    @application.exception_handler(SchemaMismatchError)
    async def schema_mismatch_handler(
        _request: Request, exc: SchemaMismatchError
    ) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": exc.message})

    @application.exception_handler(DatabaseError)
    async def database_error_handler(
        _request: Request, exc: DatabaseError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": exc.message})

    @application.exception_handler(ConfigurationError)
    async def configuration_error_handler(
        _request: Request, exc: ConfigurationError
    ) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": exc.message})

    @application.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": exc.message})

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(api_router)
    return application


app = create_app()


def main() -> None:
    """Run the API over HTTPS on the configured port (default 8445)."""
    settings = get_settings()
    if not settings.ssl_certfile.exists() or not settings.ssl_keyfile.exists():
        raise SystemExit(
            f"SSL cert/key not found under {settings.ssl_certfile.parent}. "
            "Generate them with: python -m src.app.scripts.generate_certs"
        )

    uvicorn.run(
        "src.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        ssl_certfile=str(settings.ssl_certfile),
        ssl_keyfile=str(settings.ssl_keyfile),
        reload=False,
    )


if __name__ == "__main__":
    main()

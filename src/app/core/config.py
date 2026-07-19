"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

CERTS_DIR = Path(__file__).resolve().parents[1] / "certs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Netflix Titles API"
    api_host: str = "0.0.0.0"
    api_port: int = 8445

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "netflix"
    db_schema: str = "movies"
    db_user: str = "postgres"
    db_password: str = Field(default="", validation_alias="DB_PASSWORD")

    ssl_keyfile: Path = CERTS_DIR / "key.pem"
    ssl_certfile: Path = CERTS_DIR / "cert.pem"

    # Rate limiting: requests per window across the API.
    rate_limit: str = "60/minute"

    @property
    def dsn(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={self.db_user} password={self.db_password}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

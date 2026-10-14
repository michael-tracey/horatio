from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration, read from `HORATIO_*` environment variables."""

    model_config = SettingsConfigDict(env_prefix="HORATIO_", env_file=".env")

    # Matches compose.yaml at the repo root.
    database_url: str = "postgresql+psycopg://horatio:horatio@localhost:54329/horatio"


@lru_cache
def get_settings() -> Settings:
    return Settings()

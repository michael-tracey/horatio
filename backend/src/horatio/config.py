from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration, read from `HORATIO_*` environment variables."""

    model_config = SettingsConfigDict(env_prefix="HORATIO_", env_file=".env")

    # Matches compose.yaml at the repo root.
    database_url: str = "postgresql+psycopg://horatio:horatio@localhost:54329/horatio"

    # Sign-in sessions.
    session_cookie_name: str = "horatio_session"
    session_days: int = 30
    # Secure cookies are only sent over HTTPS. Turn off only for local HTTP development.
    cookie_secure: bool = True

    # The built frontend (frontend/dist). When set, the API serves it too.
    frontend_dist: str | None = None

    # Where people reach the app, for links in messages sent outside it.
    public_url: str = "http://localhost:5173"
    # How often the API sends deliveries waiting on connectors, in seconds; 0 stops it.
    delivery_interval: float = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()

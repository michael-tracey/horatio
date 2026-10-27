from datetime import datetime
from functools import lru_cache

from pydantic import field_validator
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
    # Where database backups are kept (horatio.backups): the nightly ones and those
    # the custodian makes. Unset, the custodian's Backups page says they are not set up.
    backup_dir: str | None = None
    # Where uploaded pictures are kept (horatio.pictures): characters' pictures and
    # clan logos. Unset, nothing can be uploaded and every picture is a placeholder.
    upload_dir: str | None = None
    # The build running, baked into the image by deploy/deploy.sh: the git commit
    # (with "-dirty" if uncommitted changes went in) and when it was built.
    commit: str | None = None
    built_at: datetime | None = None
    # Horatio's code, for linking a build to its commit.
    source_url: str = "https://github.com/michael-tracey/horatio"
    # Paradox's Dark Pack resources, imported by `python -m horatio.dark_pack`
    # (horatio.dark_pack). Never shipped with Horatio; unset, there are none.
    dark_pack_dir: str | None = None
    # How someone whose account is suspended can reach the custodian, such as an
    # email address or a web page (horatio.suspensions). Unset, they are told only
    # to contact the custodian.
    custodian_contact: str | None = None
    # How often the API sends deliveries waiting on connectors, in seconds; 0 stops it.
    delivery_interval: float = 15

    # The Horatio Discord app (horatio.connectors.discord): one bot that troupes
    # invite to their servers. All three are needed for the Discord connector.
    discord_client_id: str | None = None
    discord_client_secret: str | None = None
    discord_bot_token: str | None = None

    # Email (horatio.connectors.email): Horatio sends from its own address through
    # one SMTP service; troupes' storytellers get replies. Host and from-address
    # are needed for the email connector.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    # STARTTLS on a plain connection (port 587), or TLS from the start (port 465).
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    mail_from: str | None = None

    @field_validator("commit", "built_at", mode="before")
    @classmethod
    def unset_when_blank(cls, value: object) -> object:
        """A local image build leaves the build arguments empty: not set."""
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()

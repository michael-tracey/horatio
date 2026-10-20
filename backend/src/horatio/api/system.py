"""What is running, for the custodian: the build deployed, since when, and whether
the database is on the latest migration. Nobody else sees it, so the version is
not advertised to the world."""

from datetime import UTC, datetime
from pathlib import Path

from alembic.script import ScriptDirectory
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from horatio.auth.deps import CurrentUser, DbSession
from horatio.config import get_settings
from horatio.permissions import require_custodian

router = APIRouter(prefix="/system", tags=["system"])

# backend/migrations here, /app/migrations in the image.
MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
STARTED_AT = datetime.now(UTC)


class SystemOut(BaseModel):
    # The git commit the image was built from; None for a local or untagged build.
    commit: str | None
    # Where to read that commit's code.
    commit_url: str | None
    built_at: datetime | None
    started_at: datetime
    # The migration the database is on, and the newest this code has.
    database_revision: str | None
    code_revision: str | None
    database_version: str


def code_revision() -> str | None:
    if not MIGRATIONS.is_dir():
        return None
    return ScriptDirectory(str(MIGRATIONS)).get_current_head()


def database_revision(db: DbSession) -> str | None:
    try:
        with db.begin_nested():
            return db.scalar(text("select version_num from alembic_version"))
    except DBAPIError:
        return None


@router.get("")
def system(db: DbSession, user: CurrentUser) -> SystemOut:
    require_custodian(user)
    settings = get_settings()
    commit = settings.commit
    return SystemOut(
        commit=commit,
        commit_url=f"{settings.source_url.rstrip('/')}/commit/{commit.removesuffix('-dirty')}"
        if commit
        else None,
        built_at=settings.built_at,
        started_at=STARTED_AT,
        database_revision=database_revision(db),
        code_revision=code_revision(),
        database_version=str(db.scalar(text("show server_version"))),
    )

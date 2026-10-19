"""The custodian's database backups: list them, make one, download one."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from horatio import backups
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.config import get_settings
from horatio.permissions import require_custodian

router = APIRouter(prefix="/backups", tags=["backups"])


class BackupOut(BaseModel):
    name: str
    made_at: datetime
    # In bytes.
    size: int
    # Made from the app rather than by the nightly job.
    manual: bool


class BackupsOut(BaseModel):
    # False where backups are not set up (HORATIO_BACKUP_DIR), as in local development.
    available: bool
    backups: list[BackupOut]


def out(backup: backups.Backup) -> BackupOut:
    return BackupOut(
        name=backup.name, made_at=backup.made_at, size=backup.size, manual=backup.manual
    )


@router.get("")
def list_backups(user: CurrentUser) -> BackupsOut:
    require_custodian(user)
    directory = backups.backup_dir()
    if directory is None:
        return BackupsOut(available=False, backups=[])
    return BackupsOut(available=True, backups=[out(b) for b in backups.list_backups(directory)])


@router.post("", status_code=status.HTTP_201_CREATED)
def make_backup(db: DbSession, user: CurrentUser) -> BackupOut:
    require_custodian(user)
    directory = backups.backup_dir()
    if directory is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Backups are not set up here.")
    try:
        made = backups.make(directory, get_settings().database_url)
    except backups.BackupError as error:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(error)) from None
    record(db, user, "backup.made", name=made.name)
    db.commit()
    return out(made)


@router.get("/{name}", response_class=FileResponse)
def download_backup(name: str, db: DbSession, user: CurrentUser) -> FileResponse:
    """The backup's file. It holds everything, password hashes included, so each
    download is logged."""
    require_custodian(user)
    directory = backups.backup_dir()
    path = backups.find(directory, name) if directory else None
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such backup.")
    record(db, user, "backup.downloaded", name=name)
    db.commit()
    return FileResponse(path, media_type="application/gzip", filename=name)

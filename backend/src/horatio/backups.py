"""Database backups the custodian makes and downloads (issue #50).

A backup is the whole database as plain SQL from `pg_dump`, gzipped: the same as
the host's nightly backup (deploy/backup.sh.j2) makes, kept beside them in
`HORATIO_BACKUP_DIR`, so one set of restore steps (deploy/README.md) serves both.
The nightly ones are named `horatio-<UTC time>.sql.gz`; those made here end in
`-manual`. The host keeps a week of either.
"""

import gzip
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import make_url

from horatio.config import get_settings

# Swapped for a stand-in by the tests.
PG_DUMP = "pg_dump"
NAME = re.compile(r"horatio-(?P<at>\d{8}T\d{6}Z)(?P<manual>-manual)?\.sql\.gz")


class BackupError(Exception):
    """A backup could not be made; the message says why, for the custodian."""


@dataclass(frozen=True)
class Backup:
    name: str
    made_at: datetime
    size: int
    # Made from the app rather than by the nightly job.
    manual: bool


def backup_dir() -> Path | None:
    """Where backups are kept, or None where they are not set up (local development)."""
    setting = get_settings().backup_dir
    return Path(setting) if setting else None


def _backup(path: Path) -> Backup | None:
    match = NAME.fullmatch(path.name)
    if match is None or not path.is_file():
        return None
    return Backup(
        name=path.name,
        made_at=datetime.strptime(match["at"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC),
        size=path.stat().st_size,
        manual=match["manual"] is not None,
    )


def list_backups(directory: Path) -> list[Backup]:
    """Every backup kept, newest first."""
    found = (_backup(p) for p in directory.iterdir())
    return sorted((b for b in found if b), key=lambda b: b.made_at, reverse=True)


def find(directory: Path, name: str) -> Path | None:
    """A kept backup's file. Only names a backup could have are looked up, so a
    name can never reach outside the directory."""
    if NAME.fullmatch(name) is None:
        return None
    path = directory / name
    return path if path.is_file() else None


def make(directory: Path, database_url: str) -> Backup:
    """Dump the database into a new backup. It appears only once complete: a failed
    dump leaves nothing behind."""
    name = f"horatio-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-manual.sql.gz"
    if (directory / name).exists():
        raise BackupError("A backup was made a moment ago; wait a second and try again.")
    url = make_url(database_url)
    command = [PG_DUMP, "--no-owner", f"--dbname={url.database}"]
    if url.host:
        command.append(f"--host={url.host}")
    if url.port:
        command.append(f"--port={url.port}")
    if url.username:
        command.append(f"--username={url.username}")
    # The password goes in the environment, never on the command line.
    env = {**os.environ, "PGPASSWORD": url.password or ""}

    partial = directory / f".{name}.partial"
    try:
        with tempfile.TemporaryFile() as errors, gzip.open(partial, "wb") as out:
            try:
                dump = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, env=env)
            except FileNotFoundError:
                raise BackupError("pg_dump is not installed where Horatio runs.") from None
            assert dump.stdout is not None
            with dump:
                shutil.copyfileobj(dump.stdout, out)
            if dump.returncode != 0:
                errors.seek(0)
                said = errors.read().decode(errors="replace").strip().splitlines()
                raise BackupError(f"pg_dump failed: {said[-1] if said else dump.returncode}")
        partial.rename(directory / name)
    finally:
        partial.unlink(missing_ok=True)
    made = _backup(directory / name)
    assert made is not None
    return made

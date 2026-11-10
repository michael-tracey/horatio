"""Fetching resources from elsewhere onto the server (Custodian › Tools, #534):
Paradox's Dark Pack kit (horatio.dark_pack) and the VTES symbols from KRCG
(horatio.vtes_symbols). Both are the operator's to fetch under the Dark Pack
Agreement, so Horatio never ships them.

Downloads are https only, with a User-Agent naming Horatio, timeouts and a size
cap, and go to a file on the server's permanent storage rather than into memory.

**Each tool fetches only from its own hosts** (its `Source`): the address the
custodian gives, and every address it redirects to, must be https, on the default
port, and on the tool's list. A literal IP address or `localhost` is never fetched
from, even if a list were to name one. So the server can't be pointed at itself,
the cloud's metadata service or anything else on its network.

**A fetch runs in the background**, in a thread of the API process, as the Yorick
import does: the kit is about 450 MB. How far it has got, and why the last one
failed, are kept in memory, as the API runs as one process; a restart forgets
them, and the next fetch sweeps up any files a stopped one left.
"""

import ipaddress
import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from horatio import audit
from horatio.config import get_settings
from horatio.db import get_sessionmaker
from horatio.models import User

log = logging.getLogger(__name__)

# Tests swap these for a fake server and a clock that does not wait.
transport: httpx.BaseTransport | None = None
sleep: Callable[[float], None] = time.sleep
CHUNK = 1024 * 1024


class Failed(Exception):
    """Why a fetch or an import could not be done, in words for the custodian."""


class Busy(Exception):
    """A fetch or an import is under way already."""


def user_agent() -> str:
    return f"Horatio ({get_settings().source_url})"


@dataclass(frozen=True)
class Source:
    """Where a tool fetches from: its name for the custodian, and the hosts it may
    fetch from, each a host name or `*.` and a domain for any one name under it."""

    name: str
    hosts: tuple[str, ...]

    def allows(self, host: str) -> bool:
        host = host.lower()
        if not host or _ip_or_local(host):
            return False
        for allowed in self.hosts:
            if allowed.startswith("*."):
                first, _, rest = host.partition(".")
                if first and rest == allowed[2:]:
                    return True
            elif host == allowed:
                return True
        return False


# A host that ends in a number is an IPv4 address to a browser and to the resolver,
# however it is written (2130706433, 0x7f.1, 127.1).
_NUMBER = re.compile(r"(0x[0-9a-f]*|[0-9]+)", re.IGNORECASE)


def _ip_or_local(host: str) -> bool:
    host = host.rstrip(".")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        return True
    return (
        bool(_NUMBER.fullmatch(host.rpartition(".")[2]))
        or host == "localhost"
        or host.endswith(".localhost")
    )


def _refuse(url: httpx.URL, source: Source) -> str | None:
    """Why Horatio won't fetch `url` for `source`, if it won't."""
    if url.scheme != "https":
        return "isn't https"
    if url.port not in (None, 443) or not source.allows(url.host):
        return f"isn't {source.name}"
    return None


def check_address(address: str, source: Source) -> str:
    """The address, trimmed, if it is one Horatio will fetch from for `source`:
    https, and on its list."""
    address = address.strip()
    try:
        url = httpx.URL(address)
    except httpx.InvalidURL:
        url = None
    if url is None or url.scheme != "https" or not url.host:
        raise Failed("Only https addresses can be fetched from.")
    if _refuse(url, source):
        raise Failed(f"Horatio fetches these only from {source.name}.")
    return address


def client(source: Source) -> httpx.Client:
    def checked(request: httpx.Request) -> None:
        # Every request, the first and each redirect, before it is sent.
        why = _refuse(request.url, source)
        if why:
            raise Failed(f"The address sent Horatio on to {request.url}, which {why}.")

    return httpx.Client(
        transport=transport,
        follow_redirects=True,
        max_redirects=10,
        timeout=httpx.Timeout(60, connect=20),
        headers={"User-Agent": user_agent()},
        event_hooks={"request": [checked]},
    )


def _answered(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise Failed(
            f"{response.url} answered {response.status_code} {response.reason_phrase}".rstrip()
            + "."
        )


def download(
    http: httpx.Client,
    url: str,
    to: Path,
    *,
    cap: int,
    deadline: float,
    step: Callable[[int, int | None], None] = lambda done, total: None,
) -> int:
    """Stream `url` into the file `to`, at most `cap` bytes, by the `deadline`
    (time.monotonic()). How many bytes it was."""
    try:
        with http.stream("GET", url) as response:
            _answered(response)
            length = response.headers.get("content-length")
            total = int(length) if length and length.isdigit() else None
            if total is not None and total > cap:
                raise Failed(
                    f"That file is {megabytes(total)}, more than the {megabytes(cap)} allowed."
                )
            done = 0
            step(done, total)
            with to.open("wb") as out:
                for chunk in response.iter_bytes(CHUNK):
                    done += len(chunk)
                    if done > cap:
                        raise Failed(f"That file is more than the {megabytes(cap)} allowed.")
                    if time.monotonic() > deadline:
                        raise Failed("The download took too long, and was stopped.")
                    out.write(chunk)
                    step(done, total)
            return done
    except httpx.TooManyRedirects as error:
        raise Failed(f"{url} redirected too many times.") from error
    except httpx.TimeoutException as error:
        raise Failed(f"{url} took too long to answer.") from error
    except httpx.TransportError as error:
        raise Failed(f"Could not reach {url}: {error}") from error


def get(http: httpx.Client, url: str, *, cap: int) -> bytes:
    """A small file, whole: at most `cap` bytes."""
    try:
        with http.stream("GET", url) as response:
            _answered(response)
            data = bytearray()
            for chunk in response.iter_bytes(CHUNK):
                data += chunk
                if len(data) > cap:
                    raise Failed(f"{url} is more than the {megabytes(cap)} allowed.")
            return bytes(data)
    except httpx.TooManyRedirects as error:
        raise Failed(f"{url} redirected too many times.") from error
    except httpx.TimeoutException as error:
        raise Failed(f"{url} took too long to answer.") from error
    except httpx.TransportError as error:
        raise Failed(f"Could not reach {url}: {error}") from error


def megabytes(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:,.0f} MB"
    return f"{size / 1024:,.0f} KB" if size >= 1024 else f"{size:,} bytes"


def sweep(root: Path, prefixes: tuple[str, ...]) -> None:
    """Delete what a stopped fetch or import left in `root`: its folders whose names
    start with one of `prefixes`."""
    if not root.is_dir():
        return
    for path in root.iterdir():
        if path.name.startswith(prefixes):
            shutil.rmtree(path, ignore_errors=True)


def writable(root: Path) -> bool:
    """Whether Horatio can write into `root`, or make it: not where it is mounted
    read-only, as the Dark Pack folder was before #534."""
    found = root
    while not found.exists() and found.parent != found:
        found = found.parent
    return os.access(found, os.W_OK | os.X_OK)


# --- running a fetch ------------------------------------------------------------------------------


def open_session() -> Session:
    """A session of the job's own; tests replace this."""
    return get_sessionmaker()()


def launch(work: Callable[[], None]) -> None:
    """Run the job in the background; tests replace this to run it straight away."""
    threading.Thread(target=work, name="fetch", daemon=True).start()


def record(user_id: uuid.UUID, action: str, **data: Any) -> None:
    """An audit log entry, from a job."""
    with open_session() as db:
        audit.record(db, db.get(User, user_id), action, **data)
        db.commit()


def message(error: BaseException) -> str:
    """What went wrong, for the custodian."""
    if isinstance(error, Failed):
        return str(error)
    if isinstance(error, OSError):
        return f"The files could not be written on the server: {error.strerror or error}."
    return f"Something went wrong ({type(error).__name__}); the server's log has the details."


@dataclass
class Progress:
    # What the job is doing: "Downloading", "Importing"...
    stage: str
    by: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    done: int = 0
    total: int | None = None


class Job:
    """One tool's fetch: at most one at a time, its progress, and why the last
    one failed."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.lock = threading.Lock()
        self.progress: Progress | None = None
        self.error: str | None = None
        self.error_at: datetime | None = None

    def state(self) -> tuple[Progress | None, str | None, datetime | None]:
        with self.lock:
            now = None if self.progress is None else Progress(**vars(self.progress))
            return now, self.error, self.error_at

    def claim(self, by: str, stage: str) -> None:
        """Mark the job as started, or raise Busy."""
        with self.lock:
            if self.progress is not None:
                raise Busy
            self.progress = Progress(stage, by)
            self.error = self.error_at = None

    def release(self, error: BaseException | None = None) -> None:
        with self.lock:
            self.progress = None
            if error is not None:
                self.error = message(error)
                self.error_at = datetime.now(UTC)

    def step(self, stage: str, done: int = 0, total: int | None = None) -> None:
        with self.lock:
            if self.progress is not None:
                self.progress.stage, self.progress.done, self.progress.total = stage, done, total

    def start(self, by: str, stage: str, work: Callable[[], None]) -> None:
        """Run `work` in the background as this job."""
        self.claim(by, stage)

        def run() -> None:
            try:
                work()
            except Exception as error:
                if not isinstance(error, Failed):
                    log.exception("%s", self.name)
                self.release(error)
            else:
                self.release()

        try:
            launch(run)
        except BaseException:
            self.release()
            raise

    def run_now(self, by: str, stage: str, work: Callable[[], None]) -> None:
        """Run `work` straight away as this job (an upload): what it raises goes back
        to whoever asked, not into the job's last error."""
        self.claim(by, stage)
        try:
            work()
        finally:
            self.release()

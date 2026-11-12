"""Letting a browser keep a big answer that seldom changes (issue #643): the rules
catalogue, the rules browser and the equipment rules. Each is sent with an ETag worked
out from what it is read from, and `Cache-Control: private, no-cache`: the browser
keeps it and asks every time, and an answer it has already is 304 Not Modified, with
no body. Working out the ETag takes one query (the rules' version), not the answer.

The ETag is weak (W/"..."): nginx gzips JSON (deploy/nginx-horatio.conf.j2), and
weakens a strong ETag as it does, so the browser asks back with W/"..." either way.
The gzipped answer and the plain one are the same JSON, which is what a weak ETag says."""

import hashlib
import uuid
from functools import cache

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from horatio.config import get_settings
from horatio.models import Troupe
from horatio.rules.store import rules_version

CACHE_CONTROL = "private, no-cache"


@cache
def build() -> str:
    """The code answering: a new build may answer the same rules differently. A build
    that doesn't say its commit (a local one) is new each time it starts."""
    settings = get_settings()
    if settings.commit is None:
        return uuid.uuid4().hex
    return f"{settings.commit}@{settings.built_at}"


def etag(*parts: str) -> str:
    """A weak ETag for an answer made by this build from `parts`."""
    digest = hashlib.blake2b("\0".join((build(), *parts)).encode(), digest_size=16)
    return f'W/"{digest.hexdigest()}"'


def matches(if_none_match: str | None, tag: str) -> bool:
    """Whether If-None-Match names `tag`, compared weakly (RFC 9110 13.1.2): W/"x"
    and "x" are the same, as nginx may have weakened the one the browser was sent."""
    if not if_none_match:
        return False
    if if_none_match.strip() == "*":
        return True
    opaque = tag.removeprefix("W/")
    return any(t.strip().removeprefix("W/") == opaque for t in if_none_match.split(","))


def revalidate(request: Request, response: Response, *parts: str) -> None:
    """Send the answer with the ETag of `parts`, everything it depends on; or, if the
    browser has it already, 304 Not Modified instead. Only after every check of who
    may see it: a 304 says the answer is the same, not that the asker may have it."""
    tag = etag(*parts)
    headers = {"ETag": tag, "Cache-Control": CACHE_CONTROL}
    if matches(request.headers.get("If-None-Match"), tag):
        raise HTTPException(status.HTTP_304_NOT_MODIFIED, headers=headers)
    response.headers.update(headers)


def rules_tag(db: Session, splat: str, troupe_id: uuid.UUID | None) -> str:
    """The version of the rules a character of `splat` plays by in `troupe_id`
    (horatio.rules.store.rules_version): the book's and the troupe's, which change with
    its house rules, written rules and its own row, its allowed sects among them. Read
    before the answer is, so a change in between leaves the ETag older than the
    answer, and the next request gets the answer again. 404 for no such troupe or splat."""
    try:
        return rules_version(db, splat, troupe_id)
    except NoResultFound:
        if troupe_id is not None and db.get(Troupe, troupe_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.") from None
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No rules for {splat!r}.") from None

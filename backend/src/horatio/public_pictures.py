"""Pictures Horatio sends to Discord as a message's sender (#883, #884): a news
agency's portrait, and a character's picture. Discord fetches a sender's picture
from an address, without signing in, while every other picture in Horatio is shown
only to those who may see it. So each picture Horatio sends gets an address of its
own that anyone may open, and that nobody can guess or make up: it carries a
signature of what it shows, made with the Discord app's secret (a key taken from
`HORATIO_DISCORD_CLIENT_SECRET`, used for nothing else).

An address opens one picture, a square WebP of 128 px, and only while it is still
its owner's: a new picture has a new id, and the old address stops working. Nothing
lists these addresses; only the messages Horatio sends carry them.
"""

import hashlib
import hmac
import uuid
from pathlib import Path
from typing import Literal, get_args

from sqlalchemy.orm import Session

from horatio import pictures
from horatio.config import get_settings
from horatio.models import Character, NewsAgency

Kind = Literal["agency", "character"]
KINDS: tuple[str, ...] = get_args(Kind)
# The size Discord is given: it shows a sender's picture at 40 px, 80 at most.
FILE = "128.webp"


def key() -> bytes | None:
    secret = get_settings().discord_client_secret
    if not secret:
        return None
    return hashlib.sha256(b"horatio public pictures\0" + secret.encode()).digest()


def signature(kind: str, owner_id: uuid.UUID, picture_id: uuid.UUID) -> str | None:
    found = key()
    if found is None:
        return None
    message = f"{kind}/{owner_id}/{picture_id}".encode()
    return hmac.new(found, message, hashlib.sha256).hexdigest()[:32]


def avatar_url(kind: Kind, owner_id: uuid.UUID, picture_id: uuid.UUID) -> str:
    """An absolute, unguessable URL Discord can fetch without signing in (signed, e.g. an
    HMAC of kind/owner/picture with the app's secret), serving a square webp of the picture."""
    signed = signature(kind, owner_id, picture_id)
    if signed is None:
        raise RuntimeError("Discord isn't set up on this server: no address can be signed.")
    site = get_settings().public_url.rstrip("/")
    return f"{site}/api/public-pictures/{kind}/{owner_id}/{picture_id}/{signed}.webp"


def picture_file(
    db: Session, kind: str, owner_id: uuid.UUID, picture_id: uuid.UUID, signed: str
) -> Path | None:
    """The file an address shows, or None: for any other kind, a wrong signature, or
    a picture that is no longer its owner's."""
    expected = signature(kind, owner_id, picture_id)
    root = pictures.upload_dir()
    if kind not in KINDS or expected is None or root is None:
        return None
    if not hmac.compare_digest(expected, signed):
        return None
    if kind == "agency":
        agency = db.get(NewsAgency, owner_id)
        if agency is None or agency.portrait_id != picture_id:
            return None
        return pictures.agency_portrait_file(root, agency.troupe_id, picture_id, FILE)
    character = db.get(Character, owner_id)
    if character is None or character.picture_id != picture_id:
        return None
    return pictures.picture_file(root, character.id, picture_id, FILE)

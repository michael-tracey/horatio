"""What a troupe calls the clan stored as "Assamite" (issue #430).

The 2013 books call the clan the Assamites; later World of Darkness books call it
the Banu Haqim. Each troupe chooses which name Horatio shows (`Troupe.assamite_name`),
Banu Haqim by default, and a character outside any troupe gets the default.

Only what is shown changes. "Assamite" stays the key in the rules data, in clan
conditions and requirements, rarity and status rules, and the traits saved on
sheets. The frontend renames what it shows with the same rules
(frontend/src/clanNames.ts); this module renames the text Horatio writes to
send, such as notifications, as the troupe calls the clan when it is sent.
"""

import re
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import Character, Troupe

ASSAMITE = "Assamite"
BANU_HAQIM = "Banu Haqim"
NAMES = (BANU_HAQIM, ASSAMITE)
DEFAULT = BANU_HAQIM

# Banu Haqim is the same in the plural, and takes "a", not "an".
_ARTICLE = re.compile(r"\b([Aa])n Assamite\b")
_NAME = re.compile(r"\bAssamites?\b")


def shown(text: str, name: str) -> str:
    """`text`, which names the clan as the rules store it, as a troupe calling it
    `name` reads it: "Assamite: Vizier" is "Banu Haqim: Vizier", "Kiss of the Asp
    (Assamite)" is "Kiss of the Asp (Banu Haqim)", "the Assamites" are "the Banu
    Haqim" and "an Assamite" is "a Banu Haqim"."""
    if name != BANU_HAQIM or ASSAMITE not in text:
        return text
    return _NAME.sub(BANU_HAQIM, _ARTICLE.sub(rf"\1 {BANU_HAQIM}", text))


def troupe_name(troupe: Troupe | None) -> str:
    """What `troupe` calls the clan; the default for no troupe."""
    return troupe.assamite_name if troupe is not None else DEFAULT


def for_characters(db: Session, characters: Iterable[Character]) -> dict[uuid.UUID, str]:
    """What each character's sheet calls the clan: as the troupe whose rules it plays by
    does (its home, the troupe an NPC belongs to, or the one it is built for); the
    default for a character outside any troupe."""
    troupe_of = {
        c.id: c.home_troupe_id or c.owner_troupe_id or c.building_troupe_id for c in characters
    }
    ids = {t for t in troupe_of.values() if t is not None}
    query = select(Troupe.id, Troupe.assamite_name).where(Troupe.id.in_(ids))
    called: dict[uuid.UUID, str] = {t: name for t, name in db.execute(query)}
    return {c: called.get(t, DEFAULT) if t else DEFAULT for c, t in troupe_of.items()}

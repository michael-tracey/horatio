"""A troupe's abbreviation (#1153): the short name it goes by where its full name won't
fit, such as the pill on a search hit from another troupe.

Its lead storyteller can set one: 1 to 10 letters, digits, hyphens, underscores or full
stops, no two troupes the same, whatever the case (`troupes.abbreviation`, unique on
`lower(abbreviation)`). Until one is set, it is made from the name, never stored: the
first letter of each word, upper case but for the small words after the first ("Court of
Ashes" is "CoA", "Land of the Sky" "LotS"). A made one that would be the same as another
troupe's, set or made, gives way to the full name, until its staff set one.

`effective` is the one place that decides what each troupe goes by; everything that
shows an abbreviation asks it.
"""

import re
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Troupe, User

LONGEST = 10
# Words kept lower case in a made abbreviation, unless they come first.
SMALL_WORDS = frozenset({"of", "the", "and", "a", "an", "in", "on", "at", "to", "for"})
# What a set one may be: letters, digits, "-", "_" and ".", no spaces.
ALLOWED = re.compile(rf"[\w.\-]{{1,{LONGEST}}}")
# A word of a name: letters and digits, with any apostrophes inside it ("Prince's").
WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")

INVALID = (
    f"An abbreviation is 1 to {LONGEST} letters, digits, hyphens, underscores or full stops,"
    " with no spaces."
)


def initials(name: str) -> str:
    """The abbreviation made from a name: each word's first letter, upper case but for
    the small words after the first. "" for a name with no letters or digits."""
    made = []
    for n, word in enumerate(WORD.findall(name)):
        first = word[0]
        made.append(first.lower() if n and word.lower() in SMALL_WORDS else first.upper())
    return "".join(made)


@dataclass(frozen=True)
class Named:
    id: uuid.UUID
    name: str
    abbreviation: str | None
    archived: bool = False


@dataclass(frozen=True)
class GoesBy:
    # What the troupe goes by now: the abbreviation set, else `default`.
    abbreviation: str
    # What it goes by with none set: the one made from its name, unless that clashes or
    # there is none to make, and then its name.
    default: str


def choose(troupes: Iterable[Named]) -> dict[uuid.UUID, GoesBy]:
    """What each troupe goes by: its own abbreviation; else the one made from its name,
    unless another troupe has set it or would make it too (any case), or there is none to
    make; else its full name. An archived troupe's made one stands in nobody's way, as
    nobody but the custodian sees it."""
    found = list(troupes)
    made = {t.id: initials(t.name) for t in found}
    set_ones = Counter(t.abbreviation.lower() for t in found if t.abbreviation)
    # The made ones in use, which another troupe's would clash with.
    made_ones = Counter(made[t.id].lower() for t in found if not t.abbreviation and not t.archived)
    chosen: dict[uuid.UUID, GoesBy] = {}
    for t in found:
        own = made[t.id]
        key = own.lower()
        # Leaving out its own: the one it set, or the made one it goes by.
        set_by_others = set_ones[key] - (1 if (t.abbreviation or "").lower() == key else 0)
        made_by_others = made_ones[key] - (0 if t.abbreviation or t.archived else 1)
        default = t.name if not own or set_by_others or made_by_others else own
        chosen[t.id] = GoesBy(t.abbreviation or default, default)
    return chosen


def effective(db: Session) -> dict[uuid.UUID, GoesBy]:
    """What every troupe goes by, asked of the database once: a made abbreviation depends
    on every other troupe's."""
    rows = db.execute(
        select(Troupe.id, Troupe.name, Troupe.abbreviation, Troupe.archived_at.is_not(None))
    ).all()
    return choose(Named(*row) for row in rows)


def of(db: Session, troupe: Troupe) -> str:
    """What one troupe goes by."""
    return effective(db)[troupe.id].abbreviation


def checked(value: str) -> str | None:
    """An abbreviation as given, trimmed; None for none ("" clears it). 422 for one it
    can't be."""
    value = value.strip()
    if not value:
        return None
    if not ALLOWED.fullmatch(value):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, INVALID)
    return value


def holder(db: Session, value: str, besides: uuid.UUID) -> Troupe | None:
    """Another troupe that has set this abbreviation, in any case."""
    return db.scalar(
        select(Troupe).where(func.lower(Troupe.abbreviation) == value.lower(), Troupe.id != besides)
    )


def clash(db: Session, value: str, troupe: Troupe) -> str | None:
    """Why the troupe can't take this abbreviation, or None."""
    other = holder(db, value, troupe.id)
    if other is None:
        return None
    return f"{other.name} goes by {other.abbreviation} already: choose another abbreviation."


def set_abbreviation(db: Session, user: User, troupe: Troupe, value: str | None) -> None:
    """Set the troupe's abbreviation, or with None or "", clear it and go by the one made
    from its name. 409 if another troupe has it. The caller checks who may."""
    value = checked(value or "")
    if value == troupe.abbreviation:
        return
    if value is not None:
        problem = clash(db, value, troupe)
        if problem:
            raise HTTPException(status.HTTP_409_CONFLICT, problem)
    troupe.abbreviation = value
    db.flush()
    if value is None:
        audit.record(
            db,
            user,
            "troupe.abbreviation_cleared",
            troupe_id=troupe.id,
            abbreviation=of(db, troupe),
        )
    else:
        audit.record(db, user, "troupe.abbreviation_set", troupe_id=troupe.id, abbreviation=value)

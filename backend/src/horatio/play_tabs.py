"""Which of the Play View's tabs a troupe's players see (issue #673).

A troupe keeps the tabs it has switched off (`Troupe.play_tabs_off`), so every tab
is on by default, a new one included. With every tab off the troupe doesn't use the
Play View at all: there is no Play for its characters, NPCs and visitors' own Play
Views aside, and none of its scenes run. It uses Horatio only to keep sheets.

Whose setting applies is the character's: its home troupe's, or while it has none
the troupe it is built for; an NPC's, its troupe's. A visitor keeps its home
troupe's tabs at another troupe's game. On an NPC, staff always see every tab, while
its troupe uses the Play View at all: the setting is about what players see.
"""

import uuid
from collections.abc import Iterable
from typing import Literal, get_args

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, Troupe, User

# The Play View's tabs, as the frontend's TABS names them (pages/play/PlayPage.tsx),
# in their order there. A tab added there is added here.
PlayTab = Literal["sheet", "tracker", "pools", "status", "equipment"]
PLAY_TABS: tuple[PlayTab, ...] = get_args(PlayTab)

# Why a character with no Play View isn't run in a scene.
NO_PLAY_VIEW = "Its troupe doesn't use the Play View."

NAMES: dict[PlayTab, str] = {
    "sheet": "Sheet",
    "tracker": "Tracker",
    "pools": "Pools",
    "status": "Status",
    "equipment": "Equipment",
}
assert set(NAMES) == set(PLAY_TABS)


def tabs_on(off: Iterable[str]) -> list[PlayTab]:
    """The tabs a troupe that has switched `off` off shows, in order."""
    gone = set(off)
    return [t for t in PLAY_TABS if t not in gone]


def tabs_off(off: Iterable[str]) -> list[PlayTab]:
    """Those of `off` that are tabs, in order."""
    gone = set(off)
    return [t for t in PLAY_TABS if t in gone]


def uses_play_view(troupe: Troupe | None) -> bool:
    """Whether a troupe has any tab on; no troupe has them all."""
    return troupe is None or bool(tabs_on(troupe.play_tabs_off))


def troupe_id_of(character: Character) -> uuid.UUID | None:
    """The troupe whose setting a character's Play View follows."""
    if character.kind == "npc":
        return character.owner_troupe_id
    return character.home_troupe_id or character.building_troupe_id


def character_tabs(db: Session, character: Character) -> list[PlayTab]:
    """The tabs the character's Play View has: none when its troupe doesn't use the
    Play View, every one on an NPC, else those its troupe has on."""
    troupe_id = troupe_id_of(character)
    troupe = db.get(Troupe, troupe_id) if troupe_id else None
    if troupe is None:
        return list(PLAY_TABS)
    on = tabs_on(troupe.play_tabs_off)
    if character.kind == "npc" and on:
        return list(PLAY_TABS)
    return on


def without_play_view(db: Session, characters: Iterable[Character]) -> set[uuid.UUID]:
    """Those of the characters whose troupe doesn't use the Play View, asked of the
    database once."""
    found = {c.id: troupe_id_of(c) for c in characters}
    troupes = {t for t in found.values() if t is not None}
    if not troupes:
        return set()
    off = {
        troupe_id
        for troupe_id, tabs in db.execute(
            select(Troupe.id, Troupe.play_tabs_off).where(Troupe.id.in_(troupes))
        )
        if not tabs_on(tabs)
    }
    return {character_id for character_id, troupe_id in found.items() if troupe_id in off}


def plays(db: Session, character: Character) -> bool:
    """Whether the character has a Play View: its troupe uses one."""
    return not without_play_view(db, [character])


def words(off: Iterable[str]) -> str:
    """The troupe log's account of the setting: "all tabs", "Sheet and Tracker" or
    "none (the Play View is off)"."""
    on = tabs_on(off)
    if len(on) == len(PLAY_TABS):
        return "all tabs"
    if not on:
        return "no tabs, so the Play View is off"
    named = [NAMES[t] for t in on]
    return named[0] if len(named) == 1 else f"{', '.join(named[:-1])} and {named[-1]}"


def set_tabs_off(db: Session, user: User, troupe: Troupe, off: Iterable[PlayTab]) -> None:
    """Switch the troupe's Play View tabs, logged if it changes anything."""
    chosen = tabs_off(off)
    if chosen == tabs_off(troupe.play_tabs_off):
        return
    troupe.play_tabs_off = list(chosen)
    audit.record(db, user, "troupe.play_tabs", troupe_id=troupe.id, tabs=words(chosen))

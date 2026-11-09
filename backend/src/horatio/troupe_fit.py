"""The custodian fits the creation picks of one troupe's NPCs at once (issue #533), from
Custodian › Tools, where before it meant running `python -m horatio.npc_picks` on the
server for every troupe.

It fits the troupe's NPCs whose picks are fitted (horatio.npc_picks.fitted) and
leaves the rest as they are, saying why: one built in the wizard has the picks
placed there, a Stock NPC has no sheet, and a character already given to a player
has picks and XP of its own. Picks staff placed or took off by hand are kept, as
every refit keeps them, so fitting again changes nothing. The preview fits in a
savepoint and rolls it back, so it changes nothing either.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, npc_picks, npcs
from horatio.models import AuditEvent, Character, CharacterTrait, Troupe, User
from horatio.sheets import conflict, lock_character


@dataclass(frozen=True)
class Fitted:
    id: uuid.UUID
    name: str
    # What its sheet is worth in XP at the troupe's prices, before and after fitting.
    xp_now: int
    xp_after: int
    # Whether fitting moved any of its picks.
    changed: bool


@dataclass(frozen=True)
class Skipped:
    id: uuid.UUID
    name: str
    why: str


@dataclass(frozen=True)
class TroupeFit:
    fitted: list[Fitted]
    skipped: list[Skipped]

    @property
    def changed(self) -> int:
        return sum(f.changed for f in self.fitted)


def picks_of(db: Session, npc: Character) -> set[tuple[object, ...]]:
    """Its picks, and the places its merits give (horatio.npc_picks)."""
    return {
        (t.id, t.creation_pick, t.free_rating, t.pick_by, t.grant_place, t.place_by)
        for t in db.scalars(select(CharacterTrait).where(CharacterTrait.character_id == npc.id))
    }


def why_not(npc: Character) -> str:
    if npc.npc_form == "stock":
        return "A Stock NPC: it has no sheet to fit picks to."
    if npc.creation_completed_at is None:
        return "Still being built in the wizard."
    return "Built in the wizard: its picks are the ones placed there."


def given(db: Session, troupe: Troupe) -> list[Skipped]:
    """The troupe's NPCs given to players since, which are PCs now."""
    found = db.execute(
        select(Character, User.handle)
        .join(AuditEvent, AuditEvent.character_id == Character.id)
        .join(User, User.id == Character.player_id)
        .where(
            AuditEvent.troupe_id == troupe.id,
            AuditEvent.action.in_(("npc.given", "npc.claimed")),
            Character.kind == "pc",
        )
        .distinct()
    )
    return [
        Skipped(
            character.id,
            character.name,
            f"Given to @{handle}: its picks and XP are its own now.",
        )
        for character, handle in found
    ]


def fit_troupe(db: Session, troupe: Troupe, *, apply: bool) -> TroupeFit:
    """Fit the troupe's NPCs' picks, or with `apply` false only say what fitting would
    do, changing nothing."""
    if troupe.archived_at is not None:
        raise conflict(f"{troupe.name} is archived: reopen it to fit its NPCs' picks.")
    found = db.scalars(
        select(Character)
        .where(Character.kind == "npc", Character.owner_troupe_id == troupe.id)
        .order_by(Character.name, Character.id)
    ).all()
    fitted: list[Fitted] = []
    skipped: list[Skipped] = []
    savepoint = None if apply else db.begin_nested()
    for npc in found:
        if not npc_picks.fitted(npc):
            skipped.append(Skipped(npc.id, npc.name, why_not(npc)))
            continue
        if apply:
            npc = lock_character(db, npc.id)
        xp_now = npcs.tally(db, npc)[0]
        before = picks_of(db, npc)
        npc_picks.fit(db, npc)
        fitted.append(
            Fitted(
                npc.id,
                npc.name,
                xp_now,
                npcs.tally(db, npc)[0],
                picks_of(db, npc) != before,
            )
        )
    if savepoint is not None:
        savepoint.rollback()
    skipped.extend(given(db, troupe))
    return TroupeFit(fitted, sorted(skipped, key=lambda s: (s.name, s.id)))


def fit(db: Session, custodian: User, troupe: Troupe) -> TroupeFit:
    """Fit the troupe's NPCs' picks, with one entry in its log for the lot."""
    done = fit_troupe(db, troupe, apply=True)
    audit.record(
        db,
        custodian,
        "npc.troupe_picks_fitted",
        troupe_id=troupe.id,
        count=len(done.fitted),
        changed=done.changed,
    )
    return done

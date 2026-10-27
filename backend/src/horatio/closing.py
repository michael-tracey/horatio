"""Archiving a troupe, settling what it leaves behind, and reopening it (#276).

Archiving closes a troupe to all use but the custodian's, and keeps its history
(CONTEXT.md: Archived Troupe). Before that, it settles what the troupe was
holding, so nothing is left waiting on staff who can no longer act:

- each Play View game under way, for its own characters and NPCs, ends and is kept;
- an open downtime cycle ends without being answered or delivered;
- every player character leaves it: a visit ends, and a character whose home it
  was has no home troupe, so its player can ask another troupe to accept it. Its
  accepted sheet, XP and history stay; its titles there end; its status stays, as
  status is the sect's, not the troupe's;
- its NPCs stay with it, as they are its own.

Each player affected is told, and so are its staff. Characters are never retired
by it: their players decide what comes next.

Troupes archived before this settled nothing; the custodian settles one with
`settle`. Reopening a troupe brings none of its characters back.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, notifications, play, reconciliation
from horatio.models import (
    AuditEvent,
    Character,
    CycleParticipant,
    DowntimeCycle,
    Troupe,
    TroupeMembership,
    TroupeStaff,
    User,
)
from horatio.sheets import conflict, lock_character


@dataclass(frozen=True)
class Affected:
    """What archiving the troupe settles, or would."""

    # Player characters whose home troupe it is, and those visiting it.
    home: list[Character]
    visiting: list[Character]
    # Its NPCs, which stay with it.
    npcs: list[Character]
    # Its open downtime cycle, if any (a troupe has at most one).
    cycles: list[DowntimeCycle]
    # Its own characters and NPCs with a Play View game under way.
    games: list[Character]

    @property
    def characters(self) -> int:
        return len(self.home) + len(self.visiting)


def affected(db: Session, troupe: Troupe) -> Affected:
    members = list(
        db.scalars(
            select(Character)
            .join(TroupeMembership, TroupeMembership.character_id == Character.id)
            .where(TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None))
            .order_by(Character.name)
        )
    )
    pcs = [c for c in members if c.kind == "pc"]
    home = [c for c in pcs if c.home_troupe_id == troupe.id]
    npcs = [c for c in members if c.kind == "npc"]
    cycles = list(
        db.scalars(
            select(DowntimeCycle).where(
                DowntimeCycle.troupe_id == troupe.id, DowntimeCycle.status == "open"
            )
        )
    )
    games = []
    for character in [*home, *npcs]:
        game = play.current_game(db, character)
        if game is not None and play.game_events(db, game):
            games.append(character)
    return Affected(
        home=home,
        visiting=[c for c in pcs if c.home_troupe_id != troupe.id],
        npcs=npcs,
        cycles=cycles,
        games=games,
    )


def staff_ids(db: Session, troupe: Troupe) -> list[uuid.UUID]:
    """The troupe's lead storyteller and the rest of its staff."""
    staff = db.scalars(select(TroupeStaff.user_id).where(TroupeStaff.troupe_id == troupe.id))
    return list(dict.fromkeys([troupe.lead_user_id, *staff]))


def settle(db: Session, actor: User, troupe: Troupe, reason: str) -> Affected:
    """Settle what the troupe holds, as archiving it does: see the module's notes.
    Returns what was settled."""
    found = affected(db, troupe)
    for character in found.games:
        play.reset(db, lock_character(db, character.id), actor, troupe_id=troupe.id)

    taking_part: set[uuid.UUID] = set()
    for cycle in found.cycles:
        cycle.status = "closed"
        cycle.closed_at = datetime.now(UTC)
        taking_part |= set(
            db.scalars(
                select(CycleParticipant.character_id).where(
                    CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None)
                )
            )
        )
        audit.record(
            db,
            actor,
            "downtime.cycle_ended",
            troupe_id=troupe.id,
            cycle_id=cycle.id,
            name=cycle.name,
            reason=reason,
        )

    for character in [*found.home, *found.visiting]:
        home = character.home_troupe_id == troupe.id
        membership = reconciliation.current_membership(db, character, troupe)
        assert membership is not None
        reconciliation.end_membership(
            db, actor, lock_character(db, character.id), troupe, membership
        )
        audit.record(
            db,
            actor,
            "troupe.settled",
            troupe_id=troupe.id,
            character_id=character.id,
            kind="home" if home else "visit",
            troupe=troupe.name,
            reason=reason,
        )
        if home:
            summary = (
                f"{troupe.name} is archived ({reason}): {character.name} has no home troupe now,"
                " and can ask another troupe to accept it"
            )
            if character.id in taking_part:
                summary += f". Its downtime for {found.cycles[0].name} will not be answered"
        else:
            summary = f"{troupe.name} is archived ({reason}): {character.name} no longer visits it"
        notifications.notify(
            db,
            [character.player_id],
            "troupe.archived",
            summary,
            f"/characters/{character.id}",
            troupe_id=troupe.id,
            character_id=character.id,
        )
    db.flush()
    return found


def archive(db: Session, actor: User, troupe: Troupe, reason: str) -> Affected:
    """Settle the troupe and archive it, telling its staff."""
    if troupe.archived_at is not None:
        raise conflict("This troupe is archived already.")
    # Archived first, so those it lets go leave it after (see `at_archiving`).
    troupe.archived_at = datetime.now(UTC)
    found = settle(db, actor, troupe, reason)
    audit.record(
        db,
        actor,
        "troupe.archived",
        troupe_id=troupe.id,
        reason=reason,
        home=len(found.home),
        visiting=len(found.visiting),
        cycles=len(found.cycles),
        games=len(found.games),
    )
    summary = f"{actor.display_name} archived {troupe.name} ({reason})"
    if found.home:
        summary += f": {plural(len(found.home), 'character')} it was home to " + (
            "has no home troupe now" if len(found.home) == 1 else "have no home troupe now"
        )
    notifications.notify(
        db,
        [s for s in staff_ids(db, troupe) if s != actor.id],
        "troupe.archived",
        summary,
        "/troupes",
        troupe_id=troupe.id,
    )
    return found


def settle_archived(db: Session, actor: User, troupe: Troupe, reason: str) -> Affected:
    """Settle a troupe archived before archiving settled anything."""
    if troupe.archived_at is None:
        raise conflict("Only an archived troupe's characters are settled this way.")
    found = settle(db, actor, troupe, reason)
    if not (found.characters or found.cycles or found.games):
        raise conflict("Nothing is left to settle in this troupe.")
    audit.record(
        db,
        actor,
        "troupe.settled_later",
        troupe_id=troupe.id,
        reason=reason,
        home=len(found.home),
        visiting=len(found.visiting),
    )
    return found


def reopen(db: Session, actor: User, troupe: Troupe, reason: str) -> None:
    """Open an archived troupe again, with its staff, NPCs and history, but none of
    the player characters it let go: their players ask to come back if they wish."""
    if troupe.archived_at is None:
        raise conflict("This troupe is not archived.")
    let_go = [
        c
        for c in at_archiving(db, troupe)
        if c[0].kind == "pc" and c[1] and c[0].home_troupe_id is None and c[2]
    ]
    troupe.archived_at = None
    audit.record(db, actor, "troupe.reopened", troupe_id=troupe.id, reason=reason)
    notifications.notify(
        db,
        [s for s in staff_ids(db, troupe) if s != actor.id],
        "troupe.reopened",
        f"{troupe.name} is open again ({reason})",
        f"/troupes/{troupe.id}",
        troupe_id=troupe.id,
    )
    for character, _, _ in let_go:
        notifications.notify(
            db,
            [character.player_id],
            "troupe.reopened",
            f"{troupe.name} is open again ({reason}): {character.name} can ask it to be its"
            " home troupe once more",
            f"/characters/{character.id}",
            troupe_id=troupe.id,
            character_id=character.id,
        )


def at_archiving(db: Session, troupe: Troupe) -> list[tuple[Character, bool, bool]]:
    """The characters the archived troupe had when it was archived, by name: each
    with whether it was their home (or, for an NPC, theirs), and whether it has let
    them go since. Those still in it were in it then; those who left on or after
    the day it was archived left because of it."""
    assert troupe.archived_at is not None
    rows = db.execute(
        select(Character, TroupeMembership)
        .join(TroupeMembership, TroupeMembership.character_id == Character.id)
        .where(
            TroupeMembership.troupe_id == troupe.id,
            (TroupeMembership.left_at.is_(None)) | (TroupeMembership.left_at >= troupe.archived_at),
        )
        .order_by(Character.name)
    )
    # How each was let go, where archiving or the custodian settled it: the latest.
    settled = {
        e.character_id: e.data.get("kind") == "home"
        for e in db.scalars(
            select(AuditEvent)
            .where(AuditEvent.troupe_id == troupe.id, AuditEvent.action == "troupe.settled")
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    }
    found: dict[uuid.UUID, tuple[Character, bool, bool]] = {}
    for character, membership in rows:
        left = membership.left_at is not None
        if character.kind == "npc" or not left:
            home = character.kind == "npc" or character.home_troupe_id == troupe.id
        else:
            home = settled.get(character.id, membership.approved_version_id is not None)
        found[character.id] = (character, home, left)
    return list(found.values())


def archived_by(db: Session, troupe_ids: list[uuid.UUID]) -> dict[uuid.UUID, AuditEvent]:
    """The latest archiving of each troupe, from the audit log: who did it and why."""
    found: dict[uuid.UUID, AuditEvent] = {}
    for event in db.scalars(
        select(AuditEvent)
        .where(AuditEvent.troupe_id.in_(troupe_ids), AuditEvent.action == "troupe.archived")
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ):
        assert event.troupe_id is not None
        found[event.troupe_id] = event
    return found


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"

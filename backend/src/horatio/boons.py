"""Boons, and the troupe's boon ledger (#685; MET: VTM pp. 395-397).

A boon is a debt one character owes another, registered with the Harpy (p. 395):
trivial, minor, major, blood or life (pp. 396-397). Everything goes through the
ledger: a boon made off the record isn't tracked here, and isn't enforced.

A troupe keeps a ledger or doesn't (its Boons setting, off by default). Switched
off, nothing of it shows anywhere, not even in the log, but nothing is lost: it
all comes back when it is switched on again.

Either side of a boon is a character (a PC or an NPC, retired ones too) or, for an
NPC of another domain or a character from before Horatio, a name only. A party's
standing comes from Horatio: active, or retired, as Final Death, Off-field or
Inactive. A boon still standing that involves someone dead or off-field stays in
the ledger as "departed", out of the open boons.

Each boon keeps its own log (BoonEvent): its registering, every edit, trade,
passing on, settling, voiding and reopening, with who did it, when and a note.
An edit keeps what it changed, field by field, which only the troupe's
storytellers and assistant storytellers see (`sees_changes`); anyone else who may
see the boon (the Harpy, #688) sees that it was edited, when, and the note. A
trade, a passing on, a settling or a reopening says what it did to anyone who sees
the boon.
Each change also goes in the troupe's log, which is for its running staff; never
in a character's own, which its player reads.

This issue builds the ledger for staff. Players' intake and what they see (#686),
review (#687, horatio.boon_reviews), the Harpy (#688) and Lesser Harpies (#689)
come after; the `pending` state and `BoonEvent.as_character_id` are there for them.

Players (#686) report boons in the Play View's Boons tab, for the troupe whose
setting their Play View follows. What else they see there is the troupe's to say
(`PLAYERS_SEE`): the form alone, or also what their character owes, or also what it
is owed. With "owed", the troupe may let a boon's creditor's player mark it settled,
called in or forgiven. A player never sees a boon's log, its staff note, or who
registered it.
"""

import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.orm import Session

from horatio import audit, court_knows, notifications
from horatio.models import AuditEvent, Boon, BoonEvent, Character, Troupe, User
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.sheets import conflict, membership, unprocessable

# The five kinds, lightest first (pp. 396-397).
KINDS = {
    "trivial": "Trivial",
    "minor": "Minor",
    "major": "Major",
    "blood": "Blood",
    "life": "Life",
}
# How a boon is settled: repaid when called in, forgiven by its creditor, or
# formally ignored by its debtor, which costs them status for a major or greater
# boon (p. 397).
SETTLED = {"called_in": "called in", "forgiven": "forgiven", "ignored": "formally ignored"}
# A boon's state, as its log shows it.
STATES = {"pending": "Pending", "registered": "Standing", "settled": "Settled", "void": "Void"}
# A retired character's reason for leaving, as the ledger shows it.
STANDINGS = {
    "active": "Active",
    "final_death": "Final Death",
    "off_field": "Off-field",
    "inactive": "Inactive",
    "retired": "Retired",
}
# Gone from play: a boon still standing that involves one is "departed". An inactive
# character's player has stopped, which says nothing in game; a character retired
# before reasons were kept is counted as gone.
DEPARTED = ("final_death", "off_field", "retired")
# What a troupe's players see of its ledger in the Play View (#686), least first.
PLAYERS_SEE = {
    "intake": "the form to report a boon only",
    "owes": "the form, and the boons their characters owe",
    "owed": "the form, and the boons their characters owe and are owed",
}
# How a player may settle a boon owed to their character: formally ignoring one is
# its debtor's doing (p. 397).
PLAYER_SETTLES = ("called_in", "forgiven")
# Formally ignoring one of these costs its debtor status (p. 395; horatio.boonbreakers).
COSTS_STATUS = ("major", "blood", "life")
# The most boons one entry may make, and rows a quick entry may hold.
MOST_AT_ONCE = 20
MOST_ROWS = 100
LONGEST_NAME = 200
LONGEST_TEXT = 2000


@dataclass(frozen=True)
class Party:
    """One side of a boon: a character, or a name only."""

    character: Character | None
    name: str

    @property
    def shown(self) -> str:
        return self.character.name if self.character is not None else self.name


@dataclass(frozen=True)
class Terms:
    """What a boon says, besides who owes whom."""

    kind: str
    made_on: date
    reason: str = ""
    conditions: str = ""
    notify_on_trade: bool = False
    staff_note: str = ""


def tracked(troupe: Troupe) -> bool:
    return troupe.boons


def set_setting(db: Session, user: User, troupe: Troupe, on: bool) -> None:
    """Switch the troupe's boon ledger on or off. Off hides it everywhere; what was
    registered is kept, and comes back when it is on again."""
    if troupe.boons == on:
        return
    troupe.boons = on
    audit.record(db, user, "house.boons", troupe_id=troupe.id, setting="on" if on else "off")


def can_manage(db: Session, user: User, troupe: Troupe) -> bool:
    """The troupe's running staff, and the custodian: they keep its ledger."""
    if troupe.archived_at is not None and not user.is_custodian:
        return False
    return allows(
        troupe_role(db, user, troupe), TroupeAction.MANAGE_BOONS, is_custodian=user.is_custodian
    )


def sees_changes(db: Session, user: User, troupe: Troupe) -> bool:
    """Whether `user` sees what each edit changed: the troupe's storytellers and
    assistant storytellers only (and the custodian), never the Harpy or a player."""
    return allows(
        troupe_role(db, user, troupe), TroupeAction.MANAGE_BOONS, is_custodian=user.is_custodian
    )


def hidden_events() -> ColumnElement[bool]:
    """The log entries about boons in troupes whose ledger is off, which no log shows
    until it is on again (but the custodian's search of the whole audit log)."""
    return and_(
        AuditEvent.action.startswith("boon."),
        AuditEvent.troupe_id.in_(select(Troupe.id).where(Troupe.boons.is_(False))),
    )


# --- who is on each side ------------------------------------------------------------------


def standing(character: Character | None) -> str | None:
    """A character's standing, from Horatio: active, or why it retired. None for a
    name only, whose standing Horatio doesn't know."""
    if character is None:
        return None
    if character.status != "retired":
        return "active"
    return character.left_reason or "retired"


def departed(character: Character | None, court: Collection[uuid.UUID] | None = None) -> bool:
    """Gone from play: dead or off-field. With `court`, for those who learn of
    departures only as the court knows them (a Harpy, horatio.court_knows), as the
    troupe's Who's Who lists them."""
    if court is not None:
        return court_knows.departed(character, court)
    return standing(character) in DEPARTED


def in_troupe(db: Session, troupe: Troupe, character: Character) -> bool:
    """A character the troupe's ledger can name: one of its NPCs, or a character in
    the troupe, at home or visiting, retired or not."""
    if character.kind == "npc":
        return character.owner_troupe_id == troupe.id
    return membership(db, character, troupe.id) is not None


def party(
    db: Session, troupe: Troupe, character_id: uuid.UUID | None, name: str, side: str
) -> Party:
    """The debtor or the creditor as named: a character of the troupe's, or a name only."""
    name = name.strip()
    if (character_id is None) == (not name):
        raise unprocessable(f"Name the {side}: a character, or a name only.")
    if character_id is None:
        if len(name) > LONGEST_NAME:
            raise unprocessable(f"A name is at most {LONGEST_NAME} characters.")
        return Party(None, name)
    character = db.get(Character, character_id)
    if character is None or not in_troupe(db, troupe, character):
        raise unprocessable(f"The {side} isn't a character in this troupe.")
    return Party(character, "")


def parties(db: Session, boon: Boon) -> tuple[Party, Party]:
    """The boon's debtor and creditor."""
    debtor = db.get(Character, boon.debtor_id) if boon.debtor_id else None
    creditor = db.get(Character, boon.creditor_id) if boon.creditor_id else None
    return Party(debtor, boon.debtor_name), Party(creditor, boon.creditor_name)


def same_party(a: Party, b: Party) -> bool:
    if a.character is not None or b.character is not None:
        return (
            a.character is not None and b.character is not None and a.character.id == b.character.id
        )
    return a.name.casefold() == b.name.casefold()


def place(boon: Boon, side: str, who: Party) -> None:
    """Put `who` on the boon's `side`, debtor or creditor."""
    setattr(boon, f"{side}_id", who.character.id if who.character else None)
    setattr(boon, f"{side}_name", who.name)


# --- what a boon says ---------------------------------------------------------------------


def check_terms(terms: Terms) -> Terms:
    if terms.kind not in KINDS:
        raise unprocessable(f"A boon is one of {', '.join(KINDS)}.")
    for label, text in (
        ("reason", terms.reason),
        ("conditions", terms.conditions),
        ("staff note", terms.staff_note),
    ):
        if len(text) > LONGEST_TEXT:
            raise unprocessable(f"The {label} is at most {LONGEST_TEXT} characters.")
    return Terms(
        kind=terms.kind,
        made_on=terms.made_on,
        reason=terms.reason.strip(),
        conditions=terms.conditions.strip(),
        notify_on_trade=terms.notify_on_trade,
        staff_note=terms.staff_note.strip(),
    )


def a_boon(kind: str, count: int = 1) -> str:
    """ "a minor boon", "3 major boons": every kind starts with a consonant."""
    name = KINDS[kind].lower()
    return f"a {name} boon" if count == 1 else f"{count} {name} boons"


def when(day: date) -> str:
    return f"{day.day} {day:%b %Y}"


def shown(field: str, value: Any) -> str:
    """A field's value as a change shows it."""
    if field == "kind":
        return KINDS.get(value, str(value))
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, date):
        return value.isoformat()
    return "" if value is None else str(value)


# --- the log ------------------------------------------------------------------------------


def event(
    db: Session,
    user: User,
    boon: Boon,
    kind: str,
    note: str = "",
    changes: Mapping[str, tuple[str, str]] | None = None,
    as_character: Character | None = None,
) -> BoonEvent:
    """A line in the boon's own log: done as `as_character` for a player in the Play
    View (#686), or a Harpy (#688)."""
    line = BoonEvent(
        boon_id=boon.id,
        kind=kind,
        note=note,
        changes={k: list(v) for k, v in (changes or {}).items()},
        actor_id=user.id,
        as_character_id=as_character.id if as_character is not None else None,
    )
    db.add(line)
    return line


def log(db: Session, user: User, action: str, boon: Boon, **data: Any) -> None:
    """Into the troupe's log, for its running staff. Never a character's own log,
    which its player reads: a player sees only what the troupe lets them (#686)."""
    debtor, creditor = parties(db, boon)
    audit.record(
        db,
        user,
        action,
        troupe_id=boon.troupe_id,
        debtor=debtor.shown,
        creditor=creditor.shown,
        kind=KINDS[boon.kind].lower(),
        boon_id=boon.id,
        **data,
    )


def events_of(db: Session, boon: Boon) -> list[BoonEvent]:
    """Its log, oldest first."""
    return list(
        db.scalars(
            select(BoonEvent)
            .where(BoonEvent.boon_id == boon.id)
            .order_by(BoonEvent.created_at, BoonEvent.id)
        )
    )


# --- changes ------------------------------------------------------------------------------


def check_new(debtor: Party, creditor: Party, terms: Terms, count: int = 1) -> Terms:
    """What a new boon says, checked before anything is written."""
    if not 1 <= count <= MOST_AT_ONCE:
        raise unprocessable(f"Register 1 to {MOST_AT_ONCE} boons at once.")
    if same_party(debtor, creditor):
        raise unprocessable(f"{debtor.shown} can't owe a boon to themself.")
    return check_terms(terms)


def register(
    db: Session,
    user: User,
    troupe: Troupe,
    debtor: Party,
    creditor: Party,
    terms: Terms,
    count: int = 1,
    note: str = "",
    as_character: Character | None = None,
    pending: bool = False,
    game_id: uuid.UUID | None = None,
) -> list[Boon]:
    """Put `count` boons, alike, in the troupe's ledger: standing, or, `pending`,
    submitted to wait for review (horatio.boon_reviews, #687); registered at the
    troupe's game `game_id`, if staff say so (checked by the caller)."""
    terms = check_new(debtor, creditor, terms, count)
    made: list[Boon] = []
    for _ in range(count):
        boon = Boon(
            troupe_id=troupe.id,
            kind=terms.kind,
            made_on=terms.made_on,
            reason=terms.reason,
            conditions=terms.conditions,
            notify_on_trade=terms.notify_on_trade,
            staff_note=terms.staff_note,
            state="pending" if pending else "registered",
            submitted_by=user.id,
            game_id=game_id,
        )
        place(boon, "debtor", debtor)
        place(boon, "creditor", creditor)
        db.add(boon)
        db.flush()
        kind = "submitted" if pending else "registered"
        event(db, user, boon, kind, note.strip(), as_character=as_character)
        made.append(boon)
    log(
        db,
        user,
        "boon.submitted" if pending else "boon.registered",
        made[0],
        what=a_boon(terms.kind, count),
        reason=note.strip(),
    )
    return made


def need_note(note: str, doing: str) -> str:
    note = note.strip()
    if not note:
        raise unprocessable(f"Give a note for {doing}.")
    if len(note) > LONGEST_TEXT:
        raise unprocessable(f"A note is at most {LONGEST_TEXT} characters.")
    return note


def edit(
    db: Session,
    user: User,
    boon: Boon,
    note: str,
    *,
    debtor: Party | None = None,
    creditor: Party | None = None,
    terms: Mapping[str, Any] | None = None,
    as_character: Character | None = None,
) -> None:
    """Correct what the boon says, with a note. Its log keeps each field before and
    after, for the troupe's storytellers and assistant storytellers; done as
    `as_character` for a Harpy (#688)."""
    note = need_note(note, "the edit")
    was_debtor, was_creditor = parties(db, boon)
    now_debtor = debtor or was_debtor
    now_creditor = creditor or was_creditor
    if same_party(now_debtor, now_creditor):
        raise unprocessable(f"{now_debtor.shown} can't owe a boon to themself.")
    current = Terms(
        kind=boon.kind,
        made_on=boon.made_on,
        reason=boon.reason,
        conditions=boon.conditions,
        notify_on_trade=boon.notify_on_trade,
        staff_note=boon.staff_note,
    )
    wanted = check_terms(replace(current, **(terms or {})))
    changes: dict[str, tuple[str, str]] = {}
    for side, was, now in (
        ("debtor", was_debtor, now_debtor),
        ("creditor", was_creditor, now_creditor),
    ):
        if not same_party(was, now) or was.shown != now.shown:
            changes[side] = (was.shown, now.shown)
            place(boon, side, now)
    for field in ("kind", "made_on", "reason", "conditions", "notify_on_trade", "staff_note"):
        before, after = getattr(current, field), getattr(wanted, field)
        if before != after:
            changes[field] = (shown(field, before), shown(field, after))
            setattr(boon, field, after)
    if not changes:
        raise unprocessable("Nothing has changed.")
    db.flush()
    event(db, user, boon, "edited", note, changes, as_character)
    log(db, user, "boon.edited", boon, reason=note)


def must_stand(boon: Boon, doing: str) -> None:
    if boon.state != "registered":
        raise conflict(f"Only a boon that still stands can be {doing}.")


def trade(
    db: Session,
    user: User,
    boon: Boon,
    to: Party,
    note: str = "",
    as_character: Character | None = None,
) -> None:
    """Its creditor trades it to another, who holds it now; the boon keeps its
    history. If its conditions ask, its debtor's player is told."""
    must_stand(boon, "traded")
    debtor, creditor = parties(db, boon)
    if same_party(to, creditor):
        raise unprocessable(f"{creditor.shown} holds it already.")
    if same_party(to, debtor):
        raise unprocessable(f"{debtor.shown} can't hold a boon they owe.")
    place(boon, "creditor", to)
    db.flush()
    note = note.strip()
    event(db, user, boon, "traded", note, {"creditor": (creditor.shown, to.shown)}, as_character)
    log(db, user, "boon.traded", boon, before=creditor.shown, reason=note)
    owner = debtor.character
    if boon.notify_on_trade and owner is not None and owner.kind == "pc":
        notifications.notify(
            db,
            [owner.player_id],
            "boon.traded",
            f"{creditor.shown} traded {owner.name}'s {KINDS[boon.kind].lower()} boon"
            f" ({when(boon.made_on)}) to {to.shown}.",
            f"/characters/{owner.id}",
            troupe_id=boon.troupe_id,
            character_id=owner.id,
        )


def pass_on(
    db: Session,
    user: User,
    boon: Boon,
    side: str,
    to: Party,
    note: str = "",
    as_character: Character | None = None,
) -> None:
    """Move the debtor's or the creditor's side of a standing boon to another, such
    as a broodmate after a death."""
    if side not in ("debtor", "creditor"):
        raise unprocessable("Pass on the debtor's side or the creditor's.")
    must_stand(boon, "passed on")
    debtor, creditor = parties(db, boon)
    was, other = (debtor, creditor) if side == "debtor" else (creditor, debtor)
    if same_party(to, was):
        raise unprocessable(f"{was.shown} is the {side} already.")
    if same_party(to, other):
        raise unprocessable(f"{other.shown} can't owe a boon to themself.")
    place(boon, side, to)
    db.flush()
    note = note.strip()
    event(db, user, boon, "passed_on", note, {side: (was.shown, to.shown)}, as_character)
    log(db, user, "boon.passed_on", boon, side=side, before=was.shown, after=to.shown, reason=note)


def close(boon: Boon, state: str, note: str, how: str | None = None) -> None:
    boon.state = state
    boon.settled_how = how
    boon.closed_at = datetime.now(UTC)
    boon.closed_note = note


def settle(
    db: Session,
    user: User,
    boon: Boon,
    how: str,
    note: str = "",
    as_character: Character | None = None,
) -> None:
    """The boon is settled: called in, forgiven, or formally ignored (p. 397)."""
    if how not in SETTLED:
        raise unprocessable(f"A boon is settled as one of {', '.join(SETTLED)}.")
    must_stand(boon, "settled")
    note = note.strip()
    close(boon, "settled", note, how)
    boon.status_loss = "due" if how == "ignored" and boon.kind in COSTS_STATUS else None
    db.flush()
    event(
        db,
        user,
        boon,
        "settled",
        note,
        {"state": ("Standing", f"Settled: {SETTLED[how]}")},
        as_character,
    )
    log(db, user, "boon.settled", boon, how=SETTLED[how], reason=note)


def void(
    db: Session, user: User, boon: Boon, note: str, as_character: Character | None = None
) -> None:
    """The boon never stood, or no longer counts: entered by mistake, say."""
    note = need_note(note, "making it void")
    if boon.state == "void":
        raise conflict("That boon is void already.")
    was = STATES[boon.state]
    close(boon, "void", note)
    db.flush()
    event(db, user, boon, "voided", note, {"state": (was, "Void")}, as_character)
    log(db, user, "boon.voided", boon, reason=note)


def reopen(
    db: Session, user: User, boon: Boon, note: str, as_character: Character | None = None
) -> None:
    """A settled or void boon stands again: settled by mistake, say."""
    note = need_note(note, "reopening it")
    if boon.state not in ("settled", "void"):
        raise conflict("Only a settled or void boon can be reopened.")
    was = STATES[boon.state]
    boon.state = "registered"
    boon.settled_how = None
    boon.closed_at = None
    boon.closed_note = ""
    boon.status_loss = None
    db.flush()
    event(db, user, boon, "reopened", note, {"state": (was, "Standing")}, as_character)
    log(db, user, "boon.reopened", boon, reason=note)


# --- reading the ledger -------------------------------------------------------------------


VIEWS = ("open", "departed", "settled", "void", "pending", "all")


def in_view(
    boon: Boon,
    characters: Mapping[uuid.UUID, Character],
    view: str,
    court: Collection[uuid.UUID] | None = None,
) -> bool:
    """Whether the boon belongs in one of the ledger's views: open, standing with both
    parties still in play; departed, standing but involving someone dead or
    off-field; settled; void; pending; or all."""
    if view == "all":
        return True
    if boon.state != "registered":
        return boon.state == view
    gone = any(
        departed(characters.get(c), court)
        for c in (boon.debtor_id, boon.creditor_id)
        if c is not None
    )
    return view == ("departed" if gone else "open")


def counts(
    boons: Sequence[Boon],
    characters: Mapping[uuid.UUID, Character],
    court: Collection[uuid.UUID] | None = None,
) -> dict[str, int]:
    """How many boons are in each view."""
    return {v: sum(1 for b in boons if in_view(b, characters, v, court)) for v in VIEWS}


# --- players (#686) -----------------------------------------------------------------------


def set_players(db: Session, user: User, troupe: Troupe, see: str, settle: bool) -> None:
    """What the troupe's players see of its ledger in the Play View, and whether a
    creditor's player may mark a boon settled. Logged if it changes anything."""
    if see not in PLAYERS_SEE:
        raise unprocessable(f"Players see one of {', '.join(PLAYERS_SEE)}.")
    if (troupe.boon_players_see, troupe.boon_players_settle) == (see, settle):
        return
    troupe.boon_players_see = see
    troupe.boon_players_settle = settle
    audit.record(
        db,
        user,
        "house.boon_players",
        troupe_id=troupe.id,
        see=PLAYERS_SEE[see],
        settle="may" if settle else "may not",
    )


def players_settle(troupe: Troupe) -> bool:
    """Whether a creditor's player may mark a boon settled: only where they see it."""
    return troupe.boon_players_settle and troupe.boon_players_see == "owed"


def shown_to_player(troupe: Troupe, boon: Boon, character: Character) -> bool:
    """Whether the character's player sees the boon in the Play View: standing or
    settled (never pending or void), and on a side the troupe lets them see."""
    if boon.state not in ("registered", "settled"):
        return False
    if boon.debtor_id == character.id:
        return troupe.boon_players_see in ("owes", "owed")
    if boon.creditor_id == character.id:
        return troupe.boon_players_see == "owed"
    return False


def ledger_of(db: Session, character: Character) -> Troupe | None:
    """The troupe whose ledger the character's Play View shows: the one whose setting
    the Play View follows (a PC's home troupe, or the one it is built for; an NPC's
    own), while it keeps a ledger."""
    troupe_id = (
        character.owner_troupe_id
        if character.kind == "npc"
        else character.home_troupe_id or character.building_troupe_id
    )
    troupe = db.get(Troupe, troupe_id) if troupe_id else None
    return troupe if troupe is not None and tracked(troupe) else None

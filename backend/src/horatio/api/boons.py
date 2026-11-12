"""Boons (horatio.boons): the troupe's Boons setting; its boon ledger, for its running
staff, to register boons (several at once), edit, trade, pass on, settle, void and
reopen them, each with its own log; and a character's boon summary, for staff."""

import uuid
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from horatio import boons
from horatio.api.downtimes import staff_troupe
from horatio.api.influence_log import CharacterChoice
from horatio.api.troupes import TroupeOut, troupe_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Boon, BoonEvent, Character, Troupe, TroupeMembership, User
from horatio.permissions import TroupeAction, visible_character

router = APIRouter(tags=["boons"])

Kind = Literal["trivial", "minor", "major", "blood", "life"]
State = Literal["pending", "registered", "settled", "void"]
SettledHow = Literal["called_in", "forgiven", "ignored"]
View = Literal["open", "departed", "settled", "void", "pending", "all"]
Standing = Literal["active", "final_death", "off_field", "inactive", "retired"]
EventKind = Literal["registered", "edited", "traded", "passed_on", "settled", "voided", "reopened"]
Side = Literal["debtor", "creditor"]

Text = Field(default="", max_length=boons.LONGEST_TEXT)


class BoonLedgerIn(BaseModel):
    on: bool


class BoonPartyIn(BaseModel):
    """One side of a boon: a character in the troupe, or a name only."""

    character_id: uuid.UUID | None = None
    name: str = Field(default="", max_length=boons.LONGEST_NAME)


class NewBoonIn(BaseModel):
    debtor: BoonPartyIn
    creditor: BoonPartyIn
    kind: Kind
    # The in-game night it was made.
    made_on: date
    reason: str = Text
    conditions: str = Text
    notify_on_trade: bool = False
    staff_note: str = Text
    # How many alike: "1 of 3", "2 of 3"... entered once.
    count: int = Field(default=1, ge=1, le=boons.MOST_AT_ONCE)


class RegisterBoonsIn(BaseModel):
    """One boon, or a whole game's at once."""

    boons: list[NewBoonIn] = Field(min_length=1, max_length=boons.MOST_ROWS)
    # Why or where they come from, for each boon's log: "Elysium, 3 October".
    note: str = Text


class BoonEditIn(BaseModel):
    """What to correct; anything left out stays as it is. The note is required."""

    debtor: BoonPartyIn | None = None
    creditor: BoonPartyIn | None = None
    kind: Kind | None = None
    made_on: date | None = None
    reason: str | None = Field(default=None, max_length=boons.LONGEST_TEXT)
    conditions: str | None = Field(default=None, max_length=boons.LONGEST_TEXT)
    notify_on_trade: bool | None = None
    staff_note: str | None = Field(default=None, max_length=boons.LONGEST_TEXT)
    note: str = Field(max_length=boons.LONGEST_TEXT)


class BoonTradeIn(BaseModel):
    # Who holds it now.
    creditor: BoonPartyIn
    note: str = Text


class BoonPassOnIn(BaseModel):
    side: Side
    to: BoonPartyIn
    note: str = Text


class BoonSettleIn(BaseModel):
    how: SettledHow
    note: str = Text


class BoonNoteIn(BaseModel):
    note: str = Field(max_length=boons.LONGEST_TEXT)


class BoonPartyOut(BaseModel):
    # The character, or None for a name only.
    character_id: uuid.UUID | None
    name: str
    # pc | npc, or None for a name only.
    kind: str | None
    # From Horatio: active, or why it retired; None for a name only.
    standing: Standing | None


class BoonChangeOut(BaseModel):
    field: str
    before: str
    after: str


class BoonEventOut(BaseModel):
    id: uuid.UUID
    kind: EventKind
    note: str
    at: datetime
    by: str | None
    # The character it was done as (a Harpy, #688); None for staff.
    as_character: str | None
    # What it changed. For an edit, only the troupe's storytellers and assistant
    # storytellers get these; anyone else gets None, and sees only that it was edited.
    changes: list[BoonChangeOut] | None


class BoonOut(BaseModel):
    id: uuid.UUID
    debtor: BoonPartyOut
    creditor: BoonPartyOut
    kind: Kind
    made_on: date
    reason: str
    conditions: str
    notify_on_trade: bool
    state: State
    settled_how: SettledHow | None
    closed_at: datetime | None
    closed_note: str
    staff_note: str
    # Standing, but someone on it is dead or off-field.
    departed: bool
    submitted_by: str | None
    submitted_at: datetime
    # Its log, oldest first: only on a single boon, not in the ledger's list.
    events: list[BoonEventOut] | None = None


class TroupeBoonsOut(BaseModel):
    # The boons in the view asked for, newest first.
    boons: list[BoonOut]
    # How many boons are in each view, for its tabs.
    counts: dict[str, int]
    # Its characters, retired ones too, to name on either side.
    characters: list[CharacterChoice]


class BoonKindCount(BaseModel):
    kind: Kind
    count: int


class TroupeBoonSummaryOut(BaseModel):
    troupe_id: uuid.UUID
    troupe_name: str
    # The boons still standing it owes, and is owed, by kind, lightest first.
    owes: list[BoonKindCount]
    owed: list[BoonKindCount]


class CharacterBoonsOut(BaseModel):
    # One for each troupe keeping a ledger whose running staff the caller is.
    troupes: list[TroupeBoonSummaryOut]


# --- reading ------------------------------------------------------------------------------


def characters_of(db: DbSession, found: Iterable[Boon]) -> dict[uuid.UUID, Character]:
    ids = {c for b in found for c in (b.debtor_id, b.creditor_id) if c is not None}
    if not ids:
        return {}
    return {c.id: c for c in db.scalars(select(Character).where(Character.id.in_(ids)))}


def users_of(db: DbSession, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(wanted)))}


def party_out(character: Character | None, name: str) -> BoonPartyOut:
    if character is None:
        return BoonPartyOut(character_id=None, name=name, kind=None, standing=None)
    return BoonPartyOut(
        character_id=character.id,
        name=character.name,
        kind=character.kind,
        standing=boons.standing(character),  # type: ignore[arg-type]  # a known reason
    )


def boon_out(
    boon: Boon,
    characters: Mapping[uuid.UUID, Character],
    users: Mapping[uuid.UUID, str],
) -> BoonOut:
    debtor = characters.get(boon.debtor_id) if boon.debtor_id else None
    creditor = characters.get(boon.creditor_id) if boon.creditor_id else None
    return BoonOut(
        id=boon.id,
        debtor=party_out(debtor, boon.debtor_name),
        creditor=party_out(creditor, boon.creditor_name),
        kind=boon.kind,  # type: ignore[arg-type]  # checked by the database
        made_on=boon.made_on,
        reason=boon.reason,
        conditions=boon.conditions,
        notify_on_trade=boon.notify_on_trade,
        state=boon.state,  # type: ignore[arg-type]  # checked by the database
        settled_how=boon.settled_how,  # type: ignore[arg-type]  # checked by the database
        closed_at=boon.closed_at,
        closed_note=boon.closed_note,
        staff_note=boon.staff_note,
        departed=boon.state == "registered"
        and (boons.departed(debtor) or boons.departed(creditor)),
        submitted_by=users.get(boon.submitted_by) if boon.submitted_by else None,
        submitted_at=boon.created_at,
    )


def event_out(
    line: BoonEvent, users: Mapping[uuid.UUID, str], names: Mapping[uuid.UUID, str], diffs: bool
) -> BoonEventOut:
    shown = diffs or line.kind != "edited"
    return BoonEventOut(
        id=line.id,
        kind=line.kind,  # type: ignore[arg-type]  # checked by the database
        note=line.note,
        at=line.created_at,
        by=users.get(line.actor_id) if line.actor_id else None,
        as_character=names.get(line.as_character_id) if line.as_character_id else None,
        changes=[BoonChangeOut(field=f, before=b, after=a) for f, (b, a) in line.changes.items()]
        if shown
        else None,
    )


def full_out(db: DbSession, user: User, troupe: Troupe, boon: Boon) -> BoonOut:
    """The boon with its log, its changes shown as far as `user` may see them."""
    lines = boons.events_of(db, boon)
    users = users_of(db, [boon.submitted_by, *(e.actor_id for e in lines)])
    acting = {e.as_character_id for e in lines} - {None}
    names = (
        {c.id: c.name for c in db.scalars(select(Character).where(Character.id.in_(acting)))}
        if acting
        else {}
    )
    out = boon_out(boon, characters_of(db, [boon]), users)
    diffs = boons.sees_changes(db, user, troupe)
    out.events = [event_out(e, users, names, diffs) for e in lines]
    return out


def ledger_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> Troupe:
    """The troupe, for its running staff, while it keeps a ledger. Switched off, there
    is nothing to see."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_BOONS)
    if not boons.tracked(troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This troupe doesn't keep a boon ledger.")
    return troupe


def troupe_boon(db: DbSession, troupe: Troupe, boon_id: uuid.UUID) -> Boon:
    boon = db.get(Boon, boon_id)
    if boon is None or boon.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such boon.")
    return boon


def side(db: DbSession, troupe: Troupe, given: BoonPartyIn, which: str) -> boons.Party:
    return boons.party(db, troupe, given.character_id, given.name, which)


def choices(db: DbSession, troupe: Troupe) -> list[CharacterChoice]:
    """The troupe's characters, at home or visiting, and its NPCs: retired ones too,
    as a boon outlives its parties' play."""
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None)
    )
    found = db.scalars(
        select(Character)
        .where(or_(Character.id.in_(members), Character.owner_troupe_id == troupe.id))
        .order_by(Character.name)
    )
    return [CharacterChoice(id=c.id, name=c.name, kind=c.kind, in_troupe=True) for c in found]


# --- the setting --------------------------------------------------------------------------


@router.put("/troupes/{troupe_id}/boon-ledger")
def set_boon_ledger(
    troupe_id: uuid.UUID, body: BoonLedgerIn, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """Whether the troupe keeps a boon ledger. Off hides it everywhere; what was
    registered is kept, and comes back when it is switched on again."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    boons.set_setting(db, user, troupe, body.on)
    db.commit()
    return troupe_out(db, user, troupe)


# --- the ledger ---------------------------------------------------------------------------


@router.get("/troupes/{troupe_id}/boons")
def troupe_boons(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    view: View = "open",
    character_id: uuid.UUID | None = None,
    name: str = "",
    kind: Kind | None = None,
    made_from: date | None = None,
    made_to: date | None = None,
) -> TroupeBoonsOut:
    """The troupe's boons in one view of its ledger, newest first: open (standing,
    both parties in play), departed (standing, but someone on it is dead or
    off-field), settled, void, pending, or all. Narrowed to those a character or a
    name is on, of a kind, or made between two nights."""
    troupe = ledger_troupe(db, user, troupe_id)
    every = list(
        db.scalars(
            select(Boon)
            .where(Boon.troupe_id == troupe.id)
            .order_by(Boon.made_on.desc(), Boon.created_at.desc())
        )
    )
    characters = characters_of(db, every)
    wanted = name.strip().casefold()

    def matches(b: Boon) -> bool:
        if character_id is not None and character_id not in (b.debtor_id, b.creditor_id):
            return False
        if wanted and wanted not in (b.debtor_name.casefold(), b.creditor_name.casefold()):
            return False
        if kind is not None and b.kind != kind:
            return False
        if made_from is not None and b.made_on < made_from:
            return False
        return made_to is None or b.made_on <= made_to

    narrowed = [b for b in every if matches(b)]
    shown = [b for b in narrowed if boons.in_view(b, characters, view)]
    users = users_of(db, (b.submitted_by for b in shown))
    return TroupeBoonsOut(
        boons=[boon_out(b, characters, users) for b in shown],
        counts=boons.counts(narrowed, characters),
        characters=choices(db, troupe),
    )


@router.get("/troupes/{troupe_id}/boons/{boon_id}")
def one_boon(troupe_id: uuid.UUID, boon_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BoonOut:
    """A boon with its log."""
    troupe = ledger_troupe(db, user, troupe_id)
    return full_out(db, user, troupe, troupe_boon(db, troupe, boon_id))


@router.post("/troupes/{troupe_id}/boons", status_code=status.HTTP_201_CREATED)
def register(
    troupe_id: uuid.UUID, body: RegisterBoonsIn, db: DbSession, user: CurrentUser
) -> list[BoonOut]:
    """Register boons in the ledger: one, or a whole game's at once, each row as many
    times as its count. All or none: a row that can't be registered stops them all."""
    troupe = ledger_troupe(db, user, troupe_id)
    rows: list[tuple[boons.Party, boons.Party, boons.Terms, int]] = []
    # Every row is checked before any is written.
    for number, given in enumerate(body.boons, start=1):
        try:
            debtor = side(db, troupe, given.debtor, "debtor")
            creditor = side(db, troupe, given.creditor, "creditor")
            terms = boons.check_new(
                debtor,
                creditor,
                boons.Terms(
                    kind=given.kind,
                    made_on=given.made_on,
                    reason=given.reason,
                    conditions=given.conditions,
                    notify_on_trade=given.notify_on_trade,
                    staff_note=given.staff_note,
                ),
                given.count,
            )
        except HTTPException as error:
            if len(body.boons) > 1:
                error.detail = f"Row {number}: {error.detail}"
            raise
        rows.append((debtor, creditor, terms, given.count))
    made: list[Boon] = []
    for debtor, creditor, terms, count in rows:
        made += boons.register(db, user, troupe, debtor, creditor, terms, count, body.note)
    db.commit()
    characters = characters_of(db, made)
    users = users_of(db, [user.id])
    return [boon_out(b, characters, users) for b in made]


@router.patch("/troupes/{troupe_id}/boons/{boon_id}")
def edit(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonEditIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """Correct what a boon says, with a note. Its log keeps each field before and
    after, which only the troupe's storytellers and assistant storytellers see."""
    troupe = ledger_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    terms = body.model_dump(
        exclude_none=True,
        include={"kind", "made_on", "reason", "conditions", "notify_on_trade", "staff_note"},
    )
    boons.edit(
        db,
        user,
        boon,
        body.note,
        debtor=side(db, troupe, body.debtor, "debtor") if body.debtor else None,
        creditor=side(db, troupe, body.creditor, "creditor") if body.creditor else None,
        terms=terms,
    )
    db.commit()
    return full_out(db, user, troupe, boon)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/trade")
def trade(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonTradeIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """Its creditor traded it: another holds it now. If its conditions ask, its
    debtor's player is told."""
    troupe = ledger_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    boons.trade(db, user, boon, side(db, troupe, body.creditor, "creditor"), body.note)
    db.commit()
    return full_out(db, user, troupe, boon)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/pass-on")
def pass_on(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonPassOnIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """Move the debtor's or the creditor's side of a standing boon to another, such
    as a broodmate after a death."""
    troupe = ledger_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    boons.pass_on(db, user, boon, body.side, side(db, troupe, body.to, body.side), body.note)
    db.commit()
    return full_out(db, user, troupe, boon)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/settle")
def settle(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonSettleIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """The boon is settled: called in, forgiven, or formally ignored (p. 397)."""
    troupe = ledger_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    boons.settle(db, user, boon, body.how, body.note)
    db.commit()
    return full_out(db, user, troupe, boon)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/void")
def void(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonNoteIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """The boon never stood, or no longer counts, with a note: entered by mistake, say."""
    troupe = ledger_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    boons.void(db, user, boon, body.note)
    db.commit()
    return full_out(db, user, troupe, boon)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/reopen")
def reopen(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonNoteIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """A settled or void boon stands again, with a note."""
    troupe = ledger_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    boons.reopen(db, user, boon, body.note)
    db.commit()
    return full_out(db, user, troupe, boon)


# --- on the sheet -------------------------------------------------------------------------


def by_kind(found: Iterable[Boon]) -> list[BoonKindCount]:
    tally: dict[str, int] = {}
    for b in found:
        tally[b.kind] = tally.get(b.kind, 0) + 1
    return [BoonKindCount(kind=k, count=tally[k]) for k in boons.KINDS if k in tally]  # type: ignore[arg-type]


@router.get("/characters/{character_id}/boons")
def character_boons(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CharacterBoonsOut:
    """The boons still standing the character owes and is owed, by kind, in each
    troupe whose ledger the caller keeps: for the staff view of the sheet. Players
    see nothing here (what they may see comes with #686)."""
    character = visible_character(db, user, character_id)
    found = list(
        db.scalars(
            select(Boon).where(
                or_(Boon.debtor_id == character.id, Boon.creditor_id == character.id),
                Boon.state == "registered",
            )
        )
    )
    troupe_ids = {b.troupe_id for b in found}
    home = character.home_troupe_id or character.owner_troupe_id
    if home is not None:
        troupe_ids.add(home)
    summaries: list[TroupeBoonSummaryOut] = []
    for troupe in db.scalars(select(Troupe).where(Troupe.id.in_(troupe_ids)).order_by(Troupe.name)):
        if not (boons.tracked(troupe) and boons.can_manage(db, user, troupe)):
            continue
        mine = [b for b in found if b.troupe_id == troupe.id]
        summaries.append(
            TroupeBoonSummaryOut(
                troupe_id=troupe.id,
                troupe_name=troupe.name,
                owes=by_kind(b for b in mine if b.debtor_id == character.id),
                owed=by_kind(b for b in mine if b.creditor_id == character.id),
            )
        )
    return CharacterBoonsOut(troupes=summaries)


# --- the troupe's players (#686) ----------------------------------------------------------

PlayersSee = Literal["intake", "owes", "owed"]
Direction = Literal["owes", "owed"]
PlayerSettles = Literal["called_in", "forgiven"]


class BoonPlayersIn(BaseModel):
    # What players see in the Play View's Boons tab: the form only, also what their
    # characters owe, or also what they're owed.
    see: PlayersSee
    # A boon's creditor's player may mark it settled (only with "owed").
    settle: bool


@router.put("/troupes/{troupe_id}/boon-players")
def set_boon_players(
    troupe_id: uuid.UUID, body: BoonPlayersIn, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """What the troupe's players see of its boon ledger in the Play View, and whether a
    boon's creditor's player may mark it settled there."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    boons.set_players(db, user, troupe, body.see, body.settle)
    db.commit()
    return troupe_out(db, user, troupe)


class PlayBoonIn(BaseModel):
    """A boon a player reports for their character."""

    # The other side: a player character in the troupe, or a name only.
    other: BoonPartyIn
    # The character owes the other side, or is owed by it.
    direction: Direction
    kind: Kind
    # The in-game night it was made.
    made_on: date
    reason: str = Text
    conditions: str = Text
    notify_on_trade: bool = False
    # How many alike.
    count: int = Field(default=1, ge=1, le=boons.MOST_AT_ONCE)


class PlayBoonSettleIn(BaseModel):
    how: PlayerSettles
    note: str = Text


class PlayBoonOut(BaseModel):
    """A boon as its party's player sees it: never its log, staff note or who
    registered it."""

    id: uuid.UUID
    # The other side: a character, or a name only.
    other: str
    other_id: uuid.UUID | None
    kind: Kind
    made_on: date
    reason: str
    conditions: str
    notify_on_trade: bool
    state: Literal["registered", "settled"]
    settled_how: SettledHow | None
    settled_at: datetime | None
    settled_note: str
    # The caller may mark it settled here.
    can_settle: bool


class PlayBoonsOut(BaseModel):
    troupe_id: uuid.UUID
    troupe_name: str
    # What the troupe lets its players see.
    see: PlayersSee
    # The caller may report a boon for the character now: it's in play in the troupe.
    can_report: bool
    # What the character owes, and is owed, standing then settled, newest first; None
    # where the troupe doesn't show that side.
    owes: list[PlayBoonOut] | None
    owed: list[PlayBoonOut] | None
    # The troupe's player characters in play, to name the other side; anyone else is
    # named by name.
    characters: list[CharacterChoice]


def play_ledger(db: DbSession, user: User, character_id: uuid.UUID) -> tuple[Character, Troupe]:
    """The character and the troupe whose ledger its Play View shows, for its player
    or the troupe's running staff."""
    character = visible_character(db, user, character_id)
    troupe = boons.ledger_of(db, character)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Its troupe doesn't keep a boon ledger.")
    if character.player_id != user.id and not boons.can_manage(db, user, troupe):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only its player and its troupe's staff see its boons."
        )
    return character, troupe


def player_sees(troupe: Troupe, character: Character) -> str:
    """What is shown for the character: as its troupe lets players see, or, on an NPC
    its staff run, everything."""
    return "owed" if character.kind == "npc" else troupe.boon_players_see


def in_play(db: DbSession, troupe: Troupe, character: Character) -> bool:
    return (
        character.status != "retired"
        and troupe.archived_at is None
        and boons.in_troupe(db, troupe, character)
    )


def play_choices(db: DbSession, troupe: Troupe, character: Character) -> list[CharacterChoice]:
    """The troupe's player characters in play, at home or visiting, but this one."""
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None)
    )
    found = db.scalars(
        select(Character)
        .where(
            Character.id.in_(members),
            Character.kind == "pc",
            Character.status == "active",
            Character.id != character.id,
        )
        .order_by(Character.name)
    )
    return [CharacterChoice(id=c.id, name=c.name, kind=c.kind, in_troupe=True) for c in found]


def play_out(
    db: DbSession, user: User, troupe: Troupe, character: Character, sees: str
) -> PlayBoonsOut:
    found = [
        b
        for b in db.scalars(
            select(Boon)
            .where(
                Boon.troupe_id == troupe.id,
                or_(Boon.debtor_id == character.id, Boon.creditor_id == character.id),
            )
            .order_by(Boon.made_on.desc(), Boon.created_at.desc())
        )
        if b.state in ("registered", "settled")
    ]
    others = characters_of(db, found)
    playing = in_play(db, troupe, character)
    settles = playing and (character.kind == "npc" or boons.players_settle(troupe))

    def out(b: Boon, owes: bool) -> PlayBoonOut:
        other_id, other_name = (
            (b.creditor_id, b.creditor_name) if owes else (b.debtor_id, b.debtor_name)
        )
        other = others.get(other_id) if other_id else None
        return PlayBoonOut(
            id=b.id,
            other=other.name if other is not None else other_name,
            other_id=other_id,
            kind=b.kind,  # type: ignore[arg-type]  # checked by the database
            made_on=b.made_on,
            reason=b.reason,
            conditions=b.conditions,
            notify_on_trade=b.notify_on_trade,
            state=b.state,  # type: ignore[arg-type]  # registered or settled, as found
            settled_how=b.settled_how,  # type: ignore[arg-type]  # checked by the database
            settled_at=b.closed_at,
            settled_note=b.closed_note,
            can_settle=settles and not owes and b.state == "registered",
        )

    def side(owes: bool) -> list[PlayBoonOut]:
        mine = [b for b in found if (b.debtor_id if owes else b.creditor_id) == character.id]
        # Standing first, then settled, each newest first.
        mine.sort(key=lambda b: b.state != "registered")
        return [out(b, owes) for b in mine]

    return PlayBoonsOut(
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        see=troupe.boon_players_see,  # type: ignore[arg-type]  # checked by the database
        can_report=playing,
        owes=side(True) if sees in ("owes", "owed") else None,
        owed=side(False) if sees == "owed" else None,
        characters=play_choices(db, troupe, character) if playing else [],
    )


@router.get("/characters/{character_id}/play-boons")
def play_boons(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PlayBoonsOut:
    """The Play View's Boons tab: the form to report a boon, and what the troupe lets
    its players see of the character's boons. Staff on a PC see what its player does;
    on an NPC they run, everything."""
    character, troupe = play_ledger(db, user, character_id)
    return play_out(db, user, troupe, character, player_sees(troupe, character))


@router.post("/characters/{character_id}/play-boons", status_code=status.HTTP_201_CREATED)
def report_boon(
    character_id: uuid.UUID, body: PlayBoonIn, db: DbSession, user: CurrentUser
) -> PlayBoonsOut:
    """A player reports a boon for their character, which goes in the troupe's ledger
    as theirs, done as the character."""
    character, troupe = play_ledger(db, user, character_id)
    if not in_play(db, troupe, character):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{character.name} isn't in play in {troupe.name}."
        )
    me = boons.Party(character, "")
    other = side(db, troupe, body.other, "other side")
    if other.character is not None and other.character.kind == "npc":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Name an NPC by name: the Harpy or staff link it to the ledger.",
        )
    debtor, creditor = (me, other) if body.direction == "owes" else (other, me)
    terms = boons.Terms(
        kind=body.kind,
        made_on=body.made_on,
        reason=body.reason,
        conditions=body.conditions,
        notify_on_trade=body.notify_on_trade,
    )
    boons.register(
        db,
        user,
        troupe,
        debtor,
        creditor,
        terms,
        body.count,
        "Reported in the Play View.",
        as_character=character,
    )
    db.commit()
    return play_out(db, user, troupe, character, player_sees(troupe, character))


@router.post("/characters/{character_id}/play-boons/{boon_id}/settle")
def settle_owed(
    character_id: uuid.UUID,
    boon_id: uuid.UUID,
    body: PlayBoonSettleIn,
    db: DbSession,
    user: CurrentUser,
) -> PlayBoonsOut:
    """A boon owed to the character is settled, called in or forgiven, by its
    creditor's player, where the troupe lets them."""
    character, troupe = play_ledger(db, user, character_id)
    boon = troupe_boon(db, troupe, boon_id)
    if boon.creditor_id != character.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the player of the boon's creditor settles it here."
        )
    if not in_play(db, troupe, character):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{character.name} isn't in play in {troupe.name}."
        )
    if character.kind != "npc" and not boons.players_settle(troupe):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"{troupe.name}'s players don't mark boons settled."
        )
    boons.settle(db, user, boon, body.how, body.note, as_character=character)
    db.commit()
    return play_out(db, user, troupe, character, player_sees(troupe, character))

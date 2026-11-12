"""Boons (horatio.boons): the troupe's Boons setting; its boon ledger, for its running
staff, to register boons (several at once), edit, trade, pass on, settle, void and
reopen them, each with its own log; and a character's boon summary, for staff."""

import uuid
from collections.abc import Collection, Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select

from horatio import boon_harpy, boon_reviews, boon_status, boon_talons, boons, court_knows
from horatio.api.downtimes import staff_troupe
from horatio.api.influence_log import CharacterChoice
from horatio.api.troupes import TroupeOut, troupe_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.boon_harpy import Keeper
from horatio.models import (
    Boon,
    BoonEvent,
    BoonFlag,
    Character,
    ScheduledGame,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.permissions import TroupeAction, visible_character

router = APIRouter(tags=["boons"])

Kind = Literal["trivial", "minor", "major", "blood", "life"]
State = Literal["pending", "registered", "settled", "void"]
SettledHow = Literal["called_in", "forgiven", "ignored"]
View = Literal["open", "departed", "settled", "void", "pending", "all"]
Standing = Literal["active", "final_death", "off_field", "inactive", "retired"]
EventKind = Literal[
    "registered",
    "edited",
    "traded",
    "passed_on",
    "settled",
    "voided",
    "reopened",
    "submitted",
    "accepted",
    "rejected",
    "flagged",
    "flag_cleared",
    "linked",
]
FlagKind = Literal["unmatched", "duplicate", "hand"]
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
    # The troupe's game they were registered at, if any (#702): one of its games
    # already started.
    game_id: uuid.UUID | None = None


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


class BoonFlagOut(BaseModel):
    """A flag raised on a boon for review (horatio.boon_reviews, #687)."""

    id: uuid.UUID
    kind: FlagKind
    # For an unmatched name: the side it names.
    side: Side | None
    # What Horatio found.
    detail: str
    # Why it was flagged by hand.
    note: str
    # For a likely duplicate: the boon it looks like.
    other_boon_id: uuid.UUID | None
    raised_by: str | None
    raised_at: datetime


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
    # Standing, and its creditor holds Disgraced: it need not be repaid while they do
    # (p. 316, horatio.boon_status).
    creditor_disgraced: bool = False
    submitted_by: str | None
    submitted_at: datetime
    # Its log, oldest first: only on a single boon, not in the ledger's list.
    events: list[BoonEventOut] | None = None
    # Its flags still raised for review (#687): only on a single boon and in the
    # review queue, not in the ledger's list.
    flags: list[BoonFlagOut] | None = None


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


def party_out(
    character: Character | None, name: str, court: Collection[uuid.UUID] | None = None
) -> BoonPartyOut:
    """One side of a boon. With `court`, for a Harpy (#688), as the court knows it
    (horatio.court_knows, #749): gone only if the Who's Who lists it, and why only
    when that says something in game."""
    if character is None:
        return BoonPartyOut(character_id=None, name=name, kind=None, standing=None)
    found = boons.standing(character) if court is None else court_knows.standing(character, court)
    return BoonPartyOut(
        character_id=character.id,
        name=character.name,
        kind=character.kind,
        standing=found,  # type: ignore[arg-type]  # one of boons.STANDINGS
    )


def boon_out(
    boon: Boon,
    characters: Mapping[uuid.UUID, Character],
    users: Mapping[uuid.UUID, str],
    disgraced: Collection[uuid.UUID] = frozenset(),
    keeper: Keeper | None = None,
) -> BoonOut:
    """The boon as `keeper` sees it: staff (the default) see everything; a Harpy (#688)
    never its staff note, who entered it, or why a character on it retired, and who
    has left only as the court knows it (#749)."""
    harpy = keeper is not None and not keeper.staff
    court = keeper.court if keeper is not None and harpy else None
    debtor = characters.get(boon.debtor_id) if boon.debtor_id else None
    creditor = characters.get(boon.creditor_id) if boon.creditor_id else None
    return BoonOut(
        id=boon.id,
        debtor=party_out(debtor, boon.debtor_name, court),
        creditor=party_out(creditor, boon.creditor_name, court),
        kind=boon.kind,  # type: ignore[arg-type]  # checked by the database
        made_on=boon.made_on,
        reason=boon.reason,
        conditions=boon.conditions,
        notify_on_trade=boon.notify_on_trade,
        state=boon.state,  # type: ignore[arg-type]  # checked by the database
        settled_how=boon.settled_how,  # type: ignore[arg-type]  # checked by the database
        closed_at=boon.closed_at,
        closed_note=boon.closed_note,
        staff_note="" if harpy else boon.staff_note,
        departed=boon.state == "registered"
        and (boons.departed(debtor, court) or boons.departed(creditor, court)),
        creditor_disgraced=boon.state == "registered" and boon.creditor_id in disgraced,
        submitted_by=users.get(boon.submitted_by) if boon.submitted_by and not harpy else None,
        submitted_at=boon.created_at,
    )


def event_out(
    line: BoonEvent,
    users: Mapping[uuid.UUID, str],
    names: Mapping[uuid.UUID, str],
    diffs: bool,
    harpy: bool = False,
) -> BoonEventOut:
    """A line of the boon's log. Only those who see what edits changed get an edit's
    changes; a Harpy (#688) sees the character a line was done as, never who did it
    out of game."""
    shown = diffs or line.kind != "edited"
    return BoonEventOut(
        id=line.id,
        kind=line.kind,  # type: ignore[arg-type]  # checked by the database
        note=line.note,
        at=line.created_at,
        by=users.get(line.actor_id) if line.actor_id and not harpy else None,
        as_character=names.get(line.as_character_id) if line.as_character_id else None,
        changes=[BoonChangeOut(field=f, before=b, after=a) for f, (b, a) in line.changes.items()]
        if shown
        else None,
    )


def flag_out(f: BoonFlag, users: Mapping[uuid.UUID, str]) -> BoonFlagOut:
    return BoonFlagOut(
        id=f.id,
        kind=f.kind,  # type: ignore[arg-type]  # checked by the database
        side=f.side,  # type: ignore[arg-type]  # checked by the database
        detail=f.detail,
        note=f.note,
        other_boon_id=f.other_boon_id,
        raised_by=users.get(f.raised_by) if f.raised_by else None,
        raised_at=f.created_at,
    )


def full_out(
    db: DbSession, user: User, troupe: Troupe, boon: Boon, keeper: Keeper | None = None
) -> BoonOut:
    """The boon with its log and its flags, its changes shown as far as `user` may see
    them, as `keeper` sees it (staff by default)."""
    harpy = keeper is not None and not keeper.staff
    lines = boons.events_of(db, boon)
    flags = boon_reviews.raised(db, [boon.id])
    users = users_of(
        db, [boon.submitted_by, *(e.actor_id for e in lines), *(f.raised_by for f in flags)]
    )
    acting = {e.as_character_id for e in lines} - {None}
    names = (
        {c.id: c.name for c in db.scalars(select(Character).where(Character.id.in_(acting)))}
        if acting
        else {}
    )
    out = boon_out(
        boon, characters_of(db, [boon]), users, standing_disgraced(db, [boon]), keeper=keeper
    )
    diffs = boons.sees_changes(db, user, troupe)
    out.events = [event_out(e, users, names, diffs, harpy) for e in lines]
    out.flags = [flag_out(f, users) for f in flags]
    return out


def standing_disgraced(db: DbSession, found: Iterable[Boon]) -> set[uuid.UUID]:
    """The creditors of these boons still standing who hold Disgraced (p. 316)."""
    return boon_status.disgraced(db, (b.creditor_id for b in found if b.state == "registered"))


def ledger_troupe(
    db: DbSession, user: User, troupe_id: uuid.UUID, *needs: str
) -> tuple[Troupe, Keeper]:
    """The troupe, and who `user` works its ledger as (horatio.boon_harpy.keeper): its
    running staff, a Harpy as far as the troupe's setting lets them, or a Lesser Harpy
    as far as the Harpy let them (#689), for `need`, while it keeps a ledger. Switched
    off, there is nothing to see. Given several needs, any one of them will do; given
    none, seeing the ledger ("view")."""
    troupe = db.get(Troupe, troupe_id)
    keeper = None
    if troupe is not None:
        for need in needs or ("view",):
            keeper = boon_harpy.keeper(db, user, troupe, need)
            if keeper is not None:
                break
    if troupe is None or keeper is None:
        # Refused as staff's pages refuse anyone else.
        staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_BOONS)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    if not boons.tracked(troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This troupe doesn't keep a boon ledger.")
    return troupe, keeper


def troupe_boon(db: DbSession, troupe: Troupe, boon_id: uuid.UUID) -> Boon:
    boon = db.get(Boon, boon_id)
    if boon is None or boon.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such boon.")
    return boon


def side(
    db: DbSession, troupe: Troupe, given: BoonPartyIn, which: str, keeper: Keeper | None = None
) -> boons.Party:
    """The side as named. A Harpy (#688) names only the characters they may pick
    (`harpy_choices`); anyone else by name."""
    if (
        keeper is not None
        and not keeper.staff
        and given.character_id is not None
        and given.character_id not in {c.id for c in harpy_choices(db, troupe)}
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Name the {which} by name: staff link it to a character.",
        )
    return boons.party(db, troupe, given.character_id, given.name, which)


def no_staff_note(keeper: Keeper, note: str | None) -> None:
    """A boon's staff note is its storytellers' and assistant storytellers' alone."""
    if not keeper.staff and note:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the troupe's staff write a boon's staff note."
        )


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


def harpy_choices(db: DbSession, troupe: Troupe) -> list[CharacterChoice]:
    """The characters a Harpy (#688) may pick: the troupe's player characters, at home
    or visiting, retired ones too, and the NPCs its ledger already names. Any other NPC
    stays unknown to them: they name it by name, for staff to link."""
    named = (
        select(Boon.debtor_id)
        .where(Boon.troupe_id == troupe.id)
        .union(select(Boon.creditor_id).where(Boon.troupe_id == troupe.id))
    )
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None)
    )
    found = db.scalars(
        select(Character)
        .where(
            or_(
                and_(Character.id.in_(members), Character.kind == "pc"),
                and_(Character.owner_troupe_id == troupe.id, Character.id.in_(named)),
            )
        )
        .order_by(Character.name)
    )
    return [CharacterChoice(id=c.id, name=c.name, kind=c.kind, in_troupe=True) for c in found]


def choices_for(db: DbSession, troupe: Troupe, keeper: Keeper) -> list[CharacterChoice]:
    return choices(db, troupe) if keeper.staff else harpy_choices(db, troupe)


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


HarpyAccess = Literal["none", "submissions", "full"]


class BoonHarpyIn(BaseModel):
    # The Harpy's access to the ledger: none, the review queue, or the full ledger.
    access: HarpyAccess
    # Whether the Harpy with the full ledger also reads its standings and statistics
    # (#749); left out, unchanged.
    standings: bool | None = None


@router.put("/troupes/{troupe_id}/boon-harpy")
def set_boon_harpy(
    troupe_id: uuid.UUID, body: BoonHarpyIn, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """How far the troupe's Harpy reaches into its boon ledger (#688): not at all, the
    review queue and word of each boon players report, or the full ledger; and whether,
    with the full ledger, the Harpy also reads its standings and statistics (#749)."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    boon_harpy.set_access(db, user, troupe, body.access)
    if body.standings is not None:
        boon_harpy.set_standings(db, user, troupe, body.standings)
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
    troupe, keeper = ledger_troupe(db, user, troupe_id)
    court = keeper.court
    every = list(
        db.scalars(
            select(Boon)
            .where(Boon.troupe_id == troupe.id)
            .order_by(Boon.made_on.desc(), Boon.created_at.desc(), Boon.id.desc())
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
    shown = [b for b in narrowed if boons.in_view(b, characters, view, court)]
    users = users_of(db, (b.submitted_by for b in shown))
    disgraced = standing_disgraced(db, shown)
    return TroupeBoonsOut(
        boons=[boon_out(b, characters, users, disgraced, keeper=keeper) for b in shown],
        counts=boons.counts(narrowed, characters, court),
        characters=choices_for(db, troupe, keeper),
    )


@router.get("/troupes/{troupe_id}/boons/{boon_id}")
def one_boon(troupe_id: uuid.UUID, boon_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BoonOut:
    """A boon with its log. A Harpy given only the review queue (#688) opens only the
    boons in it; a Lesser Harpy (#689) any boon."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "view", "submissions")
    boon = troupe_boon(db, troupe, boon_id)
    queue_only = "view" not in keeper.can
    if queue_only and boon.id not in {b.id for b in boon_reviews.queue(db, troupe)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such boon.")
    return full_out(db, user, troupe, boon, keeper)


@router.post("/troupes/{troupe_id}/boons", status_code=status.HTTP_201_CREATED)
def register(
    troupe_id: uuid.UUID, body: RegisterBoonsIn, db: DbSession, user: CurrentUser
) -> list[BoonOut]:
    """Register boons in the ledger: one, or a whole game's at once, each row as many
    times as its count. All or none: a row that can't be registered stops them all. A
    Harpy (#688) registers them as their character, with no staff note."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "add")
    if body.game_id is not None:
        game = db.get(ScheduledGame, body.game_id)
        if game is None or game.troupe_id != troupe.id or game.starts_at > datetime.now(UTC):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose one of the troupe's past games."
            )
    rows: list[tuple[boons.Party, boons.Party, boons.Terms, int]] = []
    # Every row is checked before any is written.
    for number, given in enumerate(body.boons, start=1):
        try:
            no_staff_note(keeper, given.staff_note.strip())
            debtor = side(db, troupe, given.debtor, "debtor", keeper)
            creditor = side(db, troupe, given.creditor, "creditor", keeper)
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
        made += boons.register(
            db,
            user,
            troupe,
            debtor,
            creditor,
            terms,
            count,
            body.note,
            as_character=keeper.character,
            game_id=body.game_id,
        )
    boon_reviews.flag_new(db, troupe, made)
    db.commit()
    characters = characters_of(db, made)
    users = users_of(db, [user.id])
    disgraced = standing_disgraced(db, made)
    return [boon_out(b, characters, users, disgraced, keeper=keeper) for b in made]


@router.patch("/troupes/{troupe_id}/boons/{boon_id}")
def edit(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonEditIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """Correct what a boon says, with a note. Its log keeps each field before and
    after, which only the troupe's storytellers and assistant storytellers see. A Harpy
    (#688) edits as their character, and never the staff note."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "edit")
    boon = troupe_boon(db, troupe, boon_id)
    # A Harpy never sees the staff note, so sends none; one they send is refused.
    no_staff_note(keeper, (body.staff_note or "").strip())
    terms = body.model_dump(
        exclude_none=True,
        include={"kind", "made_on", "reason", "conditions", "notify_on_trade", "staff_note"},
    )
    boons.edit(
        db,
        user,
        boon,
        body.note,
        debtor=side(db, troupe, body.debtor, "debtor", keeper) if body.debtor else None,
        creditor=side(db, troupe, body.creditor, "creditor", keeper) if body.creditor else None,
        terms=terms if keeper.staff else {k: v for k, v in terms.items() if k != "staff_note"},
        as_character=keeper.character,
    )
    db.commit()
    return full_out(db, user, troupe, boon, keeper)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/trade")
def trade(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonTradeIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """Its creditor traded it: another holds it now. If its conditions ask, its
    debtor's player is told."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "edit")
    boon = troupe_boon(db, troupe, boon_id)
    to = side(db, troupe, body.creditor, "creditor", keeper)
    boons.trade(db, user, boon, to, body.note, keeper.character)
    db.commit()
    return full_out(db, user, troupe, boon, keeper)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/pass-on")
def pass_on(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonPassOnIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """Move the debtor's or the creditor's side of a standing boon to another, such
    as a broodmate after a death."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "edit")
    boon = troupe_boon(db, troupe, boon_id)
    to = side(db, troupe, body.to, body.side, keeper)
    boons.pass_on(db, user, boon, body.side, to, body.note, keeper.character)
    db.commit()
    return full_out(db, user, troupe, boon, keeper)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/settle")
def settle(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonSettleIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """The boon is settled: called in, forgiven, or formally ignored (p. 397)."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "edit")
    boon = troupe_boon(db, troupe, boon_id)
    boons.settle(db, user, boon, body.how, body.note, as_character=keeper.character)
    db.commit()
    return full_out(db, user, troupe, boon, keeper)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/void")
def void(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonNoteIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """The boon never stood, or no longer counts, with a note: entered by mistake, say."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "edit")
    boon = troupe_boon(db, troupe, boon_id)
    boons.void(db, user, boon, body.note, keeper.character)
    db.commit()
    return full_out(db, user, troupe, boon, keeper)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/reopen")
def reopen(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: BoonNoteIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """A settled or void boon stands again, with a note."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "edit")
    boon = troupe_boon(db, troupe, boon_id)
    boons.reopen(db, user, boon, body.note, keeper.character)
    db.commit()
    return full_out(db, user, troupe, boon, keeper)


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
    # Standing, and its creditor holds Disgraced: it need not be repaid while they do
    # (p. 316).
    creditor_disgraced: bool = False
    # The caller may mark it settled here.
    can_settle: bool


class PlayReportOut(BaseModel):
    """A boon the character's player reported that waits for review, or that wasn't
    accepted lately, with the reason (#687). Shown to its player whatever else the
    troupe lets them see: they reported it."""

    id: uuid.UUID
    # The character owes the other side, or is owed by it.
    direction: Direction
    other: str
    kind: Kind
    made_on: date
    reason: str
    state: Literal["pending", "rejected"]
    # Why it wasn't accepted, and when.
    rejected_because: str
    rejected_at: datetime | None


class HarpyLedgerOut(BaseModel):
    """A ledger the character keeps as its troupe's Harpy (#688), or as one of its
    Lesser Harpies (#689)."""

    troupe_id: uuid.UUID
    troupe_name: str
    # How far the troupe lets the Harpy reach: the review queue, or the full ledger.
    # A Lesser Harpy sees the full ledger, and does what the Harpy let them.
    access: Literal["submissions", "full"]
    # Boons waiting for review or flagged, where they may review them; else 0.
    to_review: int
    # "harpy", or "talon" for a Lesser Harpy.
    role: Literal["harpy", "talon"] = "harpy"
    # What the troupe calls one of its Lesser Harpies: "Lesser Harpy" or "Talon".
    talon_word: str = "Lesser Harpy"
    can_add: bool = True
    can_edit: bool = True
    can_review: bool = True
    can_audit: bool = True
    # The Harpy may give others access to the ledger now (#689).
    gives_access: bool = False
    # The troupe lets its Harpy, and the Lesser Harpies who see the ledger, read its
    # boon standings and statistics too (#749).
    sees_standings: bool = False


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
    # Its boons reported here that wait for review, or weren't accepted in the last
    # REJECTED_SHOWN days (#687).
    reports: list[PlayReportOut] = []
    # The ledgers its player keeps as the Harpy (#688), for the character's player.
    harpy: list[HarpyLedgerOut] = []


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


# How long a report that wasn't accepted stays in its reporter's Boons tab.
REJECTED_SHOWN = 30


def reports_of(db: DbSession, troupe: Troupe, character: Character) -> list[PlayReportOut]:
    """The boons reported as the character that wait for review, or weren't accepted
    lately, newest first."""
    reported = select(BoonEvent.boon_id).where(
        BoonEvent.kind.in_(("submitted", "registered")),
        BoonEvent.as_character_id == character.id,
    )
    found = list(
        db.scalars(
            select(Boon)
            .where(
                Boon.troupe_id == troupe.id,
                Boon.id.in_(reported),
                Boon.state.in_(("pending", "void")),
            )
            .order_by(Boon.created_at.desc(), Boon.id.desc())
        )
    )
    rejections = {
        e.boon_id: e
        for e in db.scalars(
            select(BoonEvent).where(
                BoonEvent.boon_id.in_([b.id for b in found]), BoonEvent.kind == "rejected"
            )
        )
    }
    since = datetime.now(UTC) - timedelta(days=REJECTED_SHOWN)
    others = characters_of(db, found)
    out: list[PlayReportOut] = []
    for b in found:
        rejected = rejections.get(b.id)
        if b.state == "void" and (rejected is None or rejected.created_at < since):
            continue
        owes = b.debtor_id == character.id
        other_id, other_name = (
            (b.creditor_id, b.creditor_name) if owes else (b.debtor_id, b.debtor_name)
        )
        other = others.get(other_id) if other_id else None
        out.append(
            PlayReportOut(
                id=b.id,
                direction="owes" if owes else "owed",
                other=other.name if other is not None else other_name,
                kind=b.kind,  # type: ignore[arg-type]  # checked by the database
                made_on=b.made_on,
                reason=b.reason,
                state="pending" if b.state == "pending" else "rejected",
                rejected_because=rejected.note if rejected is not None else "",
                rejected_at=rejected.created_at if rejected is not None else None,
            )
        )
    return out


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
            .order_by(Boon.made_on.desc(), Boon.created_at.desc(), Boon.id.desc())
        )
        if b.state in ("registered", "settled")
    ]
    others = characters_of(db, found)
    disgraced = standing_disgraced(db, found)
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
            creditor_disgraced=b.state == "registered" and b.creditor_id in disgraced,
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
        reports=reports_of(db, troupe, character),
        harpy=harpy_ledgers(db, user, character),
    )


def harpy_ledgers(db: DbSession, user: User, character: Character) -> list[HarpyLedgerOut]:
    """The ledgers the character's player keeps as it: as the troupe's Harpy (#688),
    or as one of its Lesser Harpies (#689)."""
    if character.player_id != user.id:
        return []
    found = [
        HarpyLedgerOut(
            troupe_id=t.id,
            troupe_name=t.name,
            access=t.boon_harpy,  # type: ignore[arg-type]  # not "none", as found
            to_review=len(boon_reviews.queue(db, t)),
            talon_word=boon_talons.ONE[t.boon_talon_word],
            can_add=t.boon_harpy == "full",
            can_edit=t.boon_harpy == "full",
            can_audit=t.boon_harpy == "full",
            gives_access=boon_talons.enabled(t),
            sees_standings=boon_harpy.reads_standings(t),
        )
        for t in boon_harpy.offices_of(db, character)
    ]
    harpy_of = {f.troupe_id for f in found}
    for t, talon in boon_talons.offices_of(db, character):
        if t.id in harpy_of:
            continue
        found.append(
            HarpyLedgerOut(
                troupe_id=t.id,
                troupe_name=t.name,
                access="full",
                to_review=len(boon_reviews.queue(db, t)) if talon.can_edit else 0,
                role="talon",
                talon_word=boon_talons.ONE[t.boon_talon_word],
                can_add=talon.can_add,
                can_edit=talon.can_edit,
                can_review=talon.can_edit,
                can_audit=talon.can_audit,
                sees_standings=boon_harpy.reads_standings(t),
            )
        )
    return sorted(found, key=lambda f: f.troupe_name)


@router.get("/characters/{character_id}/harpy-ledgers")
def character_harpy_ledgers(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[HarpyLedgerOut]:
    """The ledgers the character's player keeps as it, the troupe's Harpy (#688): for
    the Harpy's own page, linked from the Play View's Boons tab."""
    character = visible_character(db, user, character_id)
    return harpy_ledgers(db, user, character)


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
    as theirs, done as the character: standing, or waiting for review where the troupe
    holds reports for review (#687)."""
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
    made = boons.register(
        db,
        user,
        troupe,
        debtor,
        creditor,
        terms,
        body.count,
        "Reported in the Play View.",
        as_character=character,
        pending=boon_reviews.held(troupe),
    )
    boon_reviews.flag_new(db, troupe, made)
    boon_harpy.tell(db, troupe, made, character)
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

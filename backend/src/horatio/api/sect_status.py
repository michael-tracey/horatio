"""A character's sect status on its sheet (horatio.sect_status): what it derives
from titles, social age and merits, the fleeting and negative status it holds with
each one's patron, its bans and fleeting cap; and adding and removing held status
as the home troupe's Status on sheets setting allows."""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import sect_status, sheets
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe, User
from horatio.permissions import visible_character

router = APIRouter(prefix="/characters/{character_id}/status", tags=["status"])


class StatusAbout(BaseModel):
    """What a status does, as the rules say (horatio.rules.status)."""

    name: str
    type: str
    sect: str
    passive: str
    spent: str
    censure: str
    punishment: str
    duration: str
    page: str | None


class DerivedOut(BaseModel):
    name: str
    type: str
    # Where it comes from: a title ("Prince"), a social age ("Elder"), a faction
    # ("Loyalist"), or the merits that grant it.
    source: str
    kind: Literal["title", "social_age", "faction", "merit"]
    # A title's troupe, by name, where the character is in more than one.
    troupe_id: uuid.UUID | None
    troupe_name: str | None
    # A title's status that holds only sometimes: "while the Prince is absent".
    condition: str


class PatronOut(BaseModel):
    # The character picked, if it is still in Horatio; its name now, and the title it
    # held when it gave the status.
    id: uuid.UUID | None
    name: str
    title: str
    # Words of the giver's own.
    text: str
    # All of it in a line: "Elena Varga (Prince at the time); for defending Elysium".
    words: str


class EndingOut(BaseModel):
    # The rule: "2 games or 1 month, whichever is longer".
    text: str
    # It ends no sooner than this, and after this many more of the character's games.
    not_before: date | None
    games_left: int
    # It lasts while the character holds this status too.
    while_held: str | None
    # It ends with the game it was given at.
    this_game: bool


class HeldOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    patron: PatronOut
    # Where: the troupe or domain, as written.
    place: str
    given_on: date
    story: str
    ending: EndingOut | None
    # Whether the viewer can take it off.
    can_remove: bool


class SuppressionOut(BaseModel):
    """What suppresses the character's fleeting status (MET: VTM p. 314): staff, for
    the rest of a game or for defying a Commander; or holding Vulgar (no id)."""

    id: uuid.UUID | None
    kind: Literal["game", "commander", "vulgar"]
    # "for defying a Commander", "while it holds Vulgar".
    text: str
    reason: str
    ending: EndingOut | None


class BanOut(BaseModel):
    level: str
    applies_to: str
    page: str | None
    # As the sheet shows it; None where it cannot tell.
    by_sheet: bool | None
    # As staff marked it: True, it applies; False, exempt; None, as the sheet shows.
    marked: bool | None
    reason: str
    applies: bool


class StatusOut(BaseModel):
    sect: str | None
    # The sect's name for Accepted (Acknowledged, Initiated, Committed); None for a
    # character with no status, as its sect has no status rules or it has no sect.
    accepted: str | None
    # The home troupe, whose Status on sheets setting applies here: "players" keep
    # their own, or "staff" only.
    troupe_id: uuid.UUID | None
    troupe_name: str | None
    setting: str
    # Whether the viewer adds and removes held status, and as whom.
    acting: Literal["player", "staff"] | None
    # Whether the viewer is staff for the character: they resolve old status and
    # mark bans.
    staff: bool
    derived: list[DerivedOut]
    held: list[HeldOut]
    # Status traits on the sheet from before status was derived, that nothing gives
    # now: for staff to resolve.
    unresolved: list[str]
    bans: list[BanOut]
    fleeting: int
    fleeting_cap: int
    # Why the cap is not the usual: "a lesser ban: 3", "Tainted Embrace: 1 less".
    cap_why: list[str] = []
    # Accepted by no sect, it holds the fleeting status of this one through a merit
    # (Emissary to the Camarilla), named in `outsider_through`.
    outsider_sect: str | None = None
    outsider_through: str | None = None
    disgraced: bool
    # Its fleeting status suppressed: not carried into a game, and none gained.
    suppressed: list[SuppressionOut] = []
    # The status that can be added: fleeting and negative status of its sect and
    # the general status.
    addable: list[StatusAbout]
    # What each status shown does, by name.
    about: dict[str, StatusAbout]


class PatronChoiceOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    # The titles it holds in the home troupe, "Prince"; empty for none.
    title: str


class StatusIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # The patron: a character from the patron list, or words, or both.
    patron_id: uuid.UUID | None = None
    patron_text: str = Field(default="", max_length=500)
    # The troupe or domain; empty for the troupe it is added in.
    place: str = Field(default="", max_length=200)
    # When; empty for today.
    given_on: date | None = None
    story: str = Field(default="", max_length=2000)
    # Staff say why, for the character's log.
    reason: str = Field(default="", max_length=1000)
    # At the fleeting cap: the held status given up for this one.
    give_up: uuid.UUID | None = None
    # Staff give fleeting status to a Disgraced character anyway.
    override: bool = False


class StatusRemoveIn(BaseModel):
    reason: str = Field(default="", max_length=1000)


class SuppressIn(BaseModel):
    # For the rest of the game, or 2 games or a month for defying a Commander.
    kind: Literal["game", "commander"]
    reason: str = Field(max_length=1000)


class StatusResolveIn(BaseModel):
    name: str
    reason: str = Field(default="", max_length=1000)


class BanMarkIn(BaseModel):
    # The ban, by who it applies to, as the rules word it.
    ban: str
    # "applies", "exempt", or None to go back to what the sheet shows.
    mark: Literal["applies", "exempt"] | None
    reason: str = Field(default="", max_length=1000)


def about(status: sect_status.StatusData) -> StatusAbout:
    return StatusAbout(
        name=status.name,
        type=status.type,
        sect=status.sect,
        passive=status.passive,
        spent=status.spent,
        censure=status.censure,
        punishment=status.punishment,
        duration=status.duration.text if status.duration else "",
        page=status.page,
    )


def ending_out(ending: sect_status.Ending) -> EndingOut:
    return EndingOut(
        text=ending.text,
        not_before=ending.not_before,
        games_left=ending.games_left,
        while_held=ending.while_held,
        this_game=ending.this_game,
    )


def suppression_out(s: sect_status.Suppressed) -> SuppressionOut:
    return SuppressionOut(
        id=s.id,
        kind=s.kind,
        text=s.text,
        reason=s.reason,
        ending=ending_out(s.ending) if s.ending else None,
    )


def can_remove(
    db: DbSession,
    user: User,
    character: Character,
    acting: sect_status.Acting | None,
    held: sect_status.Held,
    patrons: dict[uuid.UUID, Character],
) -> bool:
    if held.type != "Negative":
        return acting is not None
    patron = patrons.get(held.patron.id) if held.patron.id else None
    return acting == "staff" or (patron is not None and sect_status.is_player(user, patron))


def status_out(db: DbSession, user: User, character: Character) -> StatusOut:
    found = sect_status.standing(db, character)
    home = sect_status.home_troupe(db, character)
    acting = sect_status.may_change(db, user, character, home)
    names = {
        t.id: t.name
        for t in db.query(Troupe).filter(
            Troupe.id.in_({d.troupe_id for d in found.derived} - {None})
        )
    }
    patrons = {
        c.id: c
        for c in db.query(Character).filter(
            Character.id.in_({h.patron.id for h in found.held} - {None})
        )
    }
    statuses = found.rules.statuses
    shown = {d.name for d in found.derived} | {h.name for h in found.held} | set(found.unresolved)
    addable = (
        [
            about(s)
            for s in sorted(statuses.values(), key=lambda s: (s.type, s.name))
            if s.type in sect_status.HELD_TYPES and found.own(s)
        ]
        if found.sect_data is not None
        else []
    )
    return StatusOut(
        sect=found.sect,
        accepted=found.accepted,
        troupe_id=home.id if home else None,
        troupe_name=home.name if home else None,
        setting=sect_status.setting_of(home),
        acting=acting if found.sect_data is not None else None,
        staff=sect_status.staff_in(db, user, character, home),
        derived=[
            DerivedOut(
                name=d.name,
                type=d.type,
                source=d.source,
                kind=d.kind,
                troupe_id=d.troupe_id,
                troupe_name=names.get(d.troupe_id) if d.troupe_id else None,
                condition=d.condition,
            )
            for d in found.derived
        ],
        held=[
            HeldOut(
                id=h.id,
                name=h.name,
                type=h.type,
                patron=PatronOut(
                    id=h.patron.id,
                    name=h.patron.name,
                    title=h.patron.title,
                    text=h.patron.text,
                    words=h.patron.words,
                ),
                place=h.place,
                given_on=h.given_on,
                story=h.story,
                ending=ending_out(h.ending) if h.ending else None,
                can_remove=can_remove(db, user, character, acting, h, patrons),
            )
            for h in found.held
        ],
        unresolved=found.unresolved,
        bans=[
            BanOut(
                level=b.level,
                applies_to=b.applies_to,
                page=b.page,
                by_sheet=b.by_sheet,
                marked=b.marked,
                reason=b.reason,
                applies=b.applies,
            )
            for b in found.bans
        ],
        fleeting=len(found.fleeting),
        fleeting_cap=found.fleeting_cap,
        cap_why=found.cap_why,
        outsider_sect=found.outsider.sect if found.outsider else None,
        outsider_through=found.outsider.name if found.outsider else None,
        disgraced=found.disgraced,
        suppressed=[suppression_out(s) for s in found.suppressing],
        addable=addable,
        about={name: about(statuses[name]) for name in sorted(shown) if name in statuses},
    )


def up_to_date(db: DbSession, user: User, character: Character) -> None:
    """Drop held status that has ended, and suppressions, before showing it."""
    found = sect_status.held(db, character)
    if any(
        s.ending and s.ending.over
        for s in [*found, *sect_status.suppressions(db, character, found)]
    ):
        sheets.lock_character(db, character.id)
        sect_status.expire(db, character, user)
        db.commit()


@router.get("")
def read_status(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> StatusOut:
    """The character's sect status: derived, held with its patrons, its bans and cap,
    and what the viewer can change."""
    character = visible_character(db, user, character_id)
    up_to_date(db, user, character)
    return status_out(db, user, character)


@router.get("/patrons")
def read_patrons(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[PatronChoiceOut]:
    """Who can be picked as the patron of status given to the character: its home
    troupe's PCs, and its NPCs holding a title there of the character's sect."""
    character = visible_character(db, user, character_id)
    return [
        PatronChoiceOut(id=c.id, name=c.name, kind=c.kind, title=c.title)
        for c in sect_status.patron_choices(db, character)
    ]


@router.post("")
def add_status(
    character_id: uuid.UUID, body: StatusIn, db: DbSession, user: CurrentUser
) -> StatusOut:
    """Give the character a fleeting or negative status, naming its patron. On the
    sheet, the home troupe's setting says who can."""
    visible_character(db, user, character_id)
    character = sheets.lock_character(db, character_id)
    sect_status.add(
        db,
        user,
        character,
        sect_status.home_troupe(db, character),
        name=body.name,
        patron_id=body.patron_id,
        patron_text=body.patron_text,
        place=body.place,
        given_on=body.given_on,
        story=body.story,
        reason=body.reason,
        give_up=body.give_up,
        override=body.override,
    )
    db.commit()
    return status_out(db, user, character)


@router.post("/{held_id}/remove")
def remove_status(
    character_id: uuid.UUID,
    held_id: uuid.UUID,
    body: StatusRemoveIn,
    db: DbSession,
    user: CurrentUser,
) -> StatusOut:
    """Take a held status off the character. A negative status comes off early only
    by the one who gave it, or staff."""
    visible_character(db, user, character_id)
    character = sheets.lock_character(db, character_id)
    sect_status.remove(
        db, user, character, sect_status.home_troupe(db, character), held_id, reason=body.reason
    )
    db.commit()
    return status_out(db, user, character)


@router.post("/resolve")
def resolve_status(
    character_id: uuid.UUID, body: StatusResolveIn, db: DbSession, user: CurrentUser
) -> StatusOut:
    """Staff take off a status trait the sheet held before status was derived, that
    nothing gives now."""
    visible_character(db, user, character_id)
    character = sheets.lock_character(db, character_id)
    sect_status.resolve(db, user, character, body.name, body.reason)
    db.commit()
    return status_out(db, user, character)


@router.put("/bans")
def mark_ban(
    character_id: uuid.UUID, body: BanMarkIn, db: DbSession, user: CurrentUser
) -> StatusOut:
    """Staff say a status ban applies to the character, or that it is exempt, with a
    reason; or go back to what the sheet shows."""
    visible_character(db, user, character_id)
    character = sheets.lock_character(db, character_id)
    applies = {"applies": True, "exempt": False, None: None}[body.mark]
    sect_status.mark_ban(db, user, character, body.ban, applies, body.reason)
    db.commit()
    return status_out(db, user, character)


@router.post("/suppress")
def suppress_status(
    character_id: uuid.UUID, body: SuppressIn, db: DbSession, user: CurrentUser
) -> StatusOut:
    """Staff suppress the character's fleeting status, unspent (MET: VTM p. 314): for
    the rest of the game, or for 2 games or a month for defying a Commander. It comes
    back on its own."""
    visible_character(db, user, character_id)
    character = sheets.lock_character(db, character_id)
    sect_status.suppress(db, user, character, body.kind, body.reason)
    db.commit()
    return status_out(db, user, character)


@router.post("/suppressions/{suppression_id}/lift")
def lift_suppression(
    character_id: uuid.UUID,
    suppression_id: uuid.UUID,
    body: StatusRemoveIn,
    db: DbSession,
    user: CurrentUser,
) -> StatusOut:
    """Staff give the character its suppressed fleeting status back early."""
    visible_character(db, user, character_id)
    character = sheets.lock_character(db, character_id)
    sect_status.lift(db, user, character, suppression_id, body.reason)
    db.commit()
    return status_out(db, user, character)

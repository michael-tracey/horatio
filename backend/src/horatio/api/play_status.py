"""The Play View's Status tab (horatio.play_status): what the character carries into
its game, spent or not, the choices it makes for the game, and its titles."""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from horatio import play_status, sect_status
from horatio.api.sect_status import (
    EndingOut,
    StatusAbout,
    SuppressionOut,
    about,
    ending_out,
    suppression_out,
)
from horatio.models import Character, PlayEvent, PlayGame


class SourceStatus(BaseModel):
    name: str
    # Status it gives only sometimes: "while the Prince is absent".
    condition: str


class AbidingSourceOut(BaseModel):
    """A source of abiding status the character can choose for the game: a title,
    its social age or its faction, and what it gives."""

    name: str
    kind: Literal["title", "social_age", "faction"]
    status: list[SourceStatus]


class ConditionOut(BaseModel):
    """Status the source's title gives only as chosen for the game: one of `options`
    ("choose", a Bishop's Blessed or Enforcer), or `options` while the holder of
    `absent_title` is away ("absent")."""

    title: str
    kind: Literal["choose", "absent"]
    options: list[str]
    absent_title: str | None
    chosen: str | None
    away: bool


class TitleHeldOut(BaseModel):
    name: str
    # What it gives, as the sheet words it: "Noble", "Authority (while the Prince is absent)".
    status: list[SourceStatus]
    # Given since the game began: it gives nothing until the next game.
    next_game: bool
    # The one of its titles here that gives status; the others give none.
    active: bool = False


class CarriedOut(BaseModel):
    # Its tracker in taps: "status:Authority" for the game, "held:<id>" for good.
    key: str
    name: str
    type: str
    # Where it comes from: a title, "Elder", the merits that grant it, or its patron.
    source: str
    about: StatusAbout | None
    # Negative status, and suppressed fleeting status, are never spent.
    spendable: bool
    spent: bool
    # The tap that spent it, which Undo takes back.
    spent_by: uuid.UUID | None
    # Held but suppressed: not carried into the game.
    suppressed: bool = False
    # A negative status's end.
    ending: EndingOut | None = None
    # A held status's where and when, and its story.
    place: str = ""
    given_on: date | None = None
    story: str = ""


class PlayStatusOut(BaseModel):
    """The character's sect status at its game (issue #253)."""

    sect: str | None
    # The sect's name for Accepted: Acknowledged, Initiated, Committed.
    accepted: str | None
    # The game's troupe: the character's home troupe.
    troupe_id: uuid.UUID | None
    troupe_name: str | None
    sources: list[AbidingSourceOut]
    # The source of abiding status in effect; None while it is to be chosen.
    source: str | None
    # The holder has chosen it: it is locked for the game, and only staff change it.
    source_chosen: bool
    # More than one source, and none chosen yet.
    choosing: bool
    conditions: list[ConditionOut]
    titles: list[TitleHeldOut]
    # Negative first, then abiding, innate and fleeting.
    carried: list[CarriedOut]
    fleeting_cap: int
    # Why the cap is not the usual: "Tainted Embrace: 1 less".
    cap_why: list[str] = []
    # Accepted by no sect, it holds this sect's fleeting status through a merit.
    outsider_sect: str | None = None
    outsider_through: str | None = None
    suppressed: list[SuppressionOut]


class StatusChoiceIn(BaseModel):
    """The character's choices for its game; what is left out stays as it is."""

    # The source of abiding status: a title, a social age ("Elder") or a faction.
    source: str | None = Field(default=None, max_length=200)
    # A title's status chosen from its choice: {"Bishop": "Blessed"}.
    chosen: dict[str, str] = {}
    # Titles whose holder is away (True), or, by staff, back after all (False).
    absent: dict[str, bool] = {}


def source_status(derived: Sequence[sect_status.Derived]) -> list[SourceStatus]:
    return [SourceStatus(name=d.name, condition=d.condition) for d in derived]


def play_status_out(
    db: Session, character: Character, game: PlayGame | None, events: Sequence[PlayEvent]
) -> PlayStatusOut | None:
    """The Status tab; None for a character with no status (its sect has no status
    rules, or it has no sect)."""
    at = play_status.at_game(db, character, game)
    found = at.found
    if found.sect_data is None:
        return None
    return PlayStatusOut(
        sect=found.sect,
        accepted=found.accepted,
        troupe_id=at.troupe.id if at.troupe else None,
        troupe_name=at.troupe.name if at.troupe else None,
        sources=[
            AbidingSourceOut(name=s.name, kind=s.kind, status=source_status(s.status))
            for s in at.sources
        ],
        source=at.source.name if at.source else None,
        source_chosen=at.choices.source is not None,
        choosing=at.choosing,
        conditions=[
            ConditionOut(
                title=c.title,
                kind=c.kind,
                options=list(c.options),
                absent_title=c.absent_title,
                chosen=c.chosen,
                away=c.away,
            )
            for c in at.conditions
        ],
        titles=[
            TitleHeldOut(
                name=t.name,
                status=source_status(sect_status.title_status(t.data, at.troupe.id))
                if t.data and t.gives and at.troupe
                else [],
                next_game=t.next_game,
                active=t.active,
            )
            for t in at.titles
        ],
        carried=[
            CarriedOut(
                key=e.key,
                name=e.name,
                type=e.type,
                source=e.source,
                about=about(e.status) if e.status else None,
                spendable=e.spendable,
                spent=e.spent,
                spent_by=e.spent_by,
                suppressed=e.suppressed,
                ending=ending_out(e.held.ending) if e.held and e.held.ending else None,
                place=e.held.place if e.held else "",
                given_on=e.held.given_on if e.held else None,
                story=e.held.story if e.held else "",
            )
            for e in play_status.entries(at, events)
        ],
        fleeting_cap=found.fleeting_cap,
        cap_why=found.cap_why,
        outsider_sect=found.outsider.sect if found.outsider else None,
        outsider_through=found.outsider.name if found.outsider else None,
        suppressed=[suppression_out(s) for s in found.suppressing],
    )

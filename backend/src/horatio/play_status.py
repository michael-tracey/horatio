"""Sect status at a game, on the Play View's Status tab (issue #253): what the
character carries into its game (horatio.sect_status.carried), the choices it makes
for the game, and spending it.

The game's troupe is the character's home troupe (an NPC's, the troupe that keeps
it), as for the influence a game spends (horatio.play_influence). Its titles there
give its abiding status.

**As the game begins** (its first tap or choice) the titles the character holds
there are kept with the game (`begin`): a title given during the game gives nothing
until the next one (MET: VTM p. 311). One taken during the game stops giving its
abiding status at once, spent or not, as `carried` works from the titles held now.

**Choices for the game**, kept on it (PlayGame.status):

- a character with more than one source of abiding status (titles, its social age)
  chooses one (p. 311); its innate status always applies;
- a title's choice of status, such as a Bishop's Blessed or Enforcer;
- the titles whose holders are away, such as the Prince, for a Seneschal's Authority.

Each is the holder's to make once, and is then locked for the game. Only staff
change it.

**Chosen at check-in** (issue #441), where the troupe's house rule says so
(Troupe.status_at_checkin): the source of abiding status is chosen as the character
checks in to a game (horatio.checkin), before it enters play, and is fixed for that
game (`fix_at_checkin`). Its only source is chosen for it. Staff checking a
character in by hand may leave a choice of several for them to make on its Play
View. Its player cannot choose or change it on the Play View; staff can, giving a
reason, which goes in the game's log as a note. A title's status for the night (a
Bishop's Enforcer) and a ruler away are still chosen on the Play View, and status
given at the game is held beside the source, never in its place. While its game is
on, the troupe's Who's Who and the others at the game show the source it carries
(`carried_tonight`). Absentee games start no night, so choose nothing.

**Spending** is always the holder's, whatever the troupe's Status on sheets setting:

- abiding and innate status is spent for the game: a tap on "status:<name>"
  (horatio.play), which the next game puts back;
- fleeting status is spent for good: a tap on "held:<id>" takes it off the character
  (sect_status.remove, how="spent"), keeping its record with the tap, so Undo gives
  it back;
- negative status is never spent.
"""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, sect_status, titles
from horatio.models import (
    Character,
    GameAttendance,
    HeldStatus,
    PlayEvent,
    PlayGame,
    ScheduledGame,
    Troupe,
    User,
)
from horatio.rules.status import StatusData, TitleData
from horatio.sheets import apply_grants, conflict, unprocessable

# A tap spending abiding or innate status, by name, for the game: "status:Authority".
STATUS = "status:"
# A tap spending a fleeting status for good, by its record: "held:<id>".
HELD = "held:"
# The note in a game's log of staff changing its source of abiding status, where the
# troupe fixes it at check-in.
SOURCE_NOTE = "status-source"


def status_key(name: str) -> str:
    return STATUS + name


def held_key(held_id: uuid.UUID) -> str:
    return f"{HELD}{held_id}"


def held_id(tracker: str) -> uuid.UUID | None:
    """The held status a tap names, or None for another tracker."""
    if not tracker.startswith(HELD):
        return None
    try:
        return uuid.UUID(tracker.removeprefix(HELD))
    except ValueError:
        return None


def is_status(tracker: str) -> bool:
    return (tracker.startswith(STATUS) and len(tracker) > len(STATUS)) or held_id(
        tracker
    ) is not None


# --- the game's choices ------------------------------------------------------------------------


@dataclass(frozen=True)
class Choices:
    """What PlayGame.status keeps: the source of abiding status chosen, each title's
    status chosen from its choice, the titles whose holders are away, and the titles
    held in the troupe as the game began (None before it has). `checked_in`: the
    scheduled game whose check-in fixed the source, where the troupe chooses it then;
    `to_choose`: it checked in with several sources and none chosen (by staff, by
    hand), for staff to choose."""

    source: str | None = None
    chosen: Mapping[str, str] = field(default_factory=dict[str, str])
    absent: tuple[str, ...] = ()
    begun_with: tuple[str, ...] | None = None
    checked_in: str | None = None
    to_choose: bool = False

    @staticmethod
    def of(game: PlayGame | None) -> "Choices":
        kept: dict[str, Any] = game.status if game is not None else {}
        begun = kept.get("titles")
        return Choices(
            source=kept.get("source"),
            chosen=dict(kept.get("chosen", {})),
            absent=tuple(kept.get("absent", [])),
            begun_with=tuple(begun) if begun is not None else None,
            checked_in=kept.get("checked_in"),
            to_choose=bool(kept.get("to_choose", False)),
        )

    def kept(self) -> dict[str, Any]:
        found: dict[str, Any] = {"chosen": dict(self.chosen), "absent": list(self.absent)}
        if self.source is not None:
            found["source"] = self.source
        if self.begun_with is not None:
            found["titles"] = list(self.begun_with)
        if self.checked_in is not None:
            found["checked_in"] = self.checked_in
        if self.to_choose:
            found["to_choose"] = True
        return found


# The troupe's setting, as its log says it.
CHECKIN_TEXT = {
    True: "chosen at check-in and fixed for the game",
    False: "chosen on the Play View, as the book has it",
}


def at_checkin(troupe: Troupe | None) -> bool:
    """The troupe's house rule: the source of abiding status is chosen at check-in."""
    return troupe is not None and troupe.status_at_checkin


def troupe_of(db: Session, character: Character) -> Troupe | None:
    """The troupe of the character's games: its home troupe, or an NPC's."""
    return sect_status.home_troupe(db, character)


def begin(db: Session, character: Character, game: PlayGame) -> None:
    """Keep the titles the character holds in the troupe as its game begins, once."""
    troupe = troupe_of(db, character)
    if game.ended_at is not None or troupe is None or "titles" in game.status:
        return
    game.status = {**game.status, "titles": titles.held(db, troupe.id, character.id)}


# --- what it carries ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Condition:
    """Status a title gives only as chosen for the game: one of `options` (`kind`
    "choose", a Bishop's Blessed or Enforcer); or `options` while the holder of
    `absent_title` is away ("absent", the Seneschal's Authority)."""

    title: str
    kind: Literal["choose", "absent"]
    options: tuple[str, ...]
    absent_title: str | None
    chosen: str | None
    away: bool


@dataclass(frozen=True)
class TitleHeld:
    """A title the character holds in the troupe, with the status it gives; one given
    since the game began gives nothing until the next."""

    name: str
    data: TitleData | None
    gives: bool
    next_game: bool
    # The one of its titles there that gives status (horatio.titles).
    active: bool = False


@dataclass
class AtGame:
    """The character's status at its game: its sources of abiding status, the one in
    effect (None while there is a choice to make), the choices for it, its titles in
    the troupe, and what it carries."""

    troupe: Troupe | None
    found: sect_status.Standing
    choices: Choices
    # The troupe chooses the source at check-in: its player cannot on the Play View.
    fixed: bool = False
    sources: list[sect_status.AbidingSource] = field(
        default_factory=list[sect_status.AbidingSource]
    )
    source: sect_status.AbidingSource | None = None
    conditions: list[Condition] = field(default_factory=list[Condition])
    titles: list[TitleHeld] = field(default_factory=list[TitleHeld])
    carried: list[sect_status.Carried] = field(default_factory=list[sect_status.Carried])

    @property
    def choosing(self) -> bool:
        """The character has more than one source and has not chosen."""
        return self.source is None and len(self.sources) > 1


def at_game(db: Session, character: Character, game: PlayGame | None) -> AtGame:
    found = sect_status.standing(db, character)
    troupe = troupe_of(db, character)
    choices = Choices.of(game)
    at = AtGame(troupe, found, choices, at_checkin(troupe))
    if troupe is None or found.sect_data is None:
        return at
    data = titles.title_data(db, troupe.id)
    begun = choices.begun_with
    active = titles.active_title(db, troupe.id, character.id)
    at.titles = [
        TitleHeld(
            name,
            data.get(name),
            name == active and sect_status.gives_status(data.get(name), found.sect),
            begun is not None and name not in begun,
            name == active,
        )
        for name in titles.held(db, troupe.id, character.id)
    ]
    at.sources = sect_status.abiding_sources(found, troupe.id, begun)
    if choices.source is not None:
        # One chosen and since lost gives nothing for the rest of the game.
        at.source = next((s for s in at.sources if s.name == choices.source), None)
    elif len(at.sources) == 1:
        at.source = at.sources[0]
    title = data.get(at.source.name) if at.source and at.source.kind == "title" else None
    if title is not None:
        if title.choose_one:
            at.conditions.append(
                Condition(
                    title.name,
                    "choose",
                    title.choose_one,
                    None,
                    choices.chosen.get(title.name),
                    False,
                )
            )
        for a in title.while_absent:
            at.conditions.append(
                Condition(title.name, "absent", a.status, a.title, None, a.title in choices.absent)
            )
    at.carried = sect_status.carried(
        db,
        character,
        troupe.id,
        abiding_source=at.source.name if at.source else None,
        chosen=choices.chosen,
        absent=choices.absent,
        begun_with=begun,
        or_first=False,
        found=found,
    )
    return at


@dataclass(frozen=True)
class Entry:
    """One status on the Status tab: carried into the game, or a fleeting status
    spent for good at it. `key` is its tracker in taps; `spent_by`, the tap that
    spent it (a device's id for it), for Undo."""

    key: str
    name: str
    type: str
    source: str
    status: StatusData | None
    spendable: bool
    spent_by: uuid.UUID | None = None
    held: sect_status.Held | None = None
    # Held but suppressed: not carried, and not to be spent.
    suppressed: bool = False

    @property
    def spent(self) -> bool:
        return self.spent_by is not None


TYPE_ORDER = {"Negative": 0, "Abiding": 1, "Innate": 2, "Fleeting": 3}


def spends(events: Iterable[PlayEvent]) -> dict[str, PlayEvent]:
    """The tap that spent each status at the game, by its tracker: the latest spend
    on it that did, neither undone nor given back."""
    undone = {e.undoes_id for e in events if e.kind == "undo"}
    found: dict[str, PlayEvent] = {}
    for e in sorted(events, key=lambda e: (e.happened_at, e.id)):
        if e.kind != "change" or e.id in undone or not is_status(e.tracker):
            continue
        if e.tracker.startswith(HELD) and e.held_status is None:
            # Spent on another device first: this one changed nothing.
            continue
        if e.amount < 0:
            found[e.tracker] = e
        else:
            found.pop(e.tracker, None)
    return found


def entries(at: AtGame, events: Iterable[PlayEvent]) -> list[Entry]:
    """What the Status tab lists, negative status first, then abiding, innate and
    fleeting: what the character carries, each spent or not; its fleeting status
    suppressed; and the fleeting status it spent for good at this game."""
    events = list(events)
    spent = spends(events)
    statuses = at.found.rules.statuses
    found: list[Entry] = []
    for c in at.carried:
        key = held_key(c.held.id) if c.type == "Fleeting" and c.held else status_key(c.name)
        by = spent.get(key)
        found.append(
            Entry(
                key=key,
                name=c.name,
                type=c.type,
                source=c.source,
                status=c.status,
                spendable=c.type != "Negative",
                spent_by=by.client_id if by and c.type != "Negative" else None,
                held=c.held,
            )
        )
    if at.found.suppressing:
        found += [
            Entry(
                key=held_key(h.id),
                name=h.name,
                type="Fleeting",
                source=h.patron.words,
                status=h.status,
                spendable=False,
                held=h,
                suppressed=True,
            )
            for h in at.found.fleeting
            if h.status and at.found.own(h.status)
        ][: at.found.fleeting_cap]
    for key, by in spent.items():
        record = by.held_status
        if not key.startswith(HELD) or record is None:
            continue
        patron = sect_status.Patron(
            uuid.UUID(record["patron_id"]) if record.get("patron_id") else None,
            record.get("patron_name", ""),
            record.get("patron_title", ""),
            record.get("patron_text", ""),
        )
        found.append(
            Entry(
                key=key,
                name=record["name"],
                type="Fleeting",
                source=patron.words,
                status=statuses.get(record["name"]),
                spendable=True,
                spent_by=by.client_id,
            )
        )
    return sorted(found, key=lambda e: TYPE_ORDER.get(e.type, 9))


# --- choosing ----------------------------------------------------------------------------------


def choice_text(choices: Choices, before: Choices) -> str:
    """The choices made, as the log says them."""
    said: list[str] = []
    if choices.source != before.source and choices.source:
        said.append(f"{choices.source} as its source of abiding status")
    for title, status in choices.chosen.items():
        if before.chosen.get(title) != status:
            said.append(f"{status}, as {title}")
    for away in set(choices.absent) - set(before.absent):
        said.append(f"the {away} absent")
    for back in set(before.absent) - set(choices.absent):
        said.append(f"the {back} present after all")
    return "; ".join(said)


def choose(
    db: Session,
    user: User,
    character: Character,
    game: PlayGame,
    *,
    staff: bool,
    source: str | None = None,
    chosen: Mapping[str, str] | None = None,
    absent: Mapping[str, bool] | None = None,
    reason: str = "",
) -> None:
    """Make the character's choices for the game: its source of abiding status, a
    title's status, a title's holder absent (or, by staff, back). The holder makes
    each once, and it is locked for the game; `staff` change any of them. Where the
    troupe chooses the source at check-in, only staff choose it here, and changing
    one already chosen takes a `reason`, noted in the game's log."""
    begin(db, character, game)
    at = at_game(db, character, game)
    if at.found.sect_data is None or at.troupe is None:
        raise conflict(f"{character.name} has no status to choose.")
    before = at.choices
    locked = "is chosen for this game; staff can change it."
    new_source = before.source
    reason = reason.strip()
    if source is not None and source != before.source:
        if not any(s.name == source for s in at.sources):
            raise unprocessable(f"{source} gives {character.name} no abiding status here.")
        if at.fixed and not staff:
            raise conflict(
                "Your source of abiding status is chosen as you check in, and fixed for the"
                " game; staff can change it."
            )
        if before.source is not None and not staff:
            raise conflict(f"Your source of abiding status {locked}")
        if at.fixed and before.source is not None and not reason:
            raise unprocessable("Give a reason for the change: it goes in the game's log.")
        new_source = source
    data = titles.title_data(db, at.troupe.id)
    held_now = [t.name for t in at.titles if not t.next_game]
    new_chosen = dict(before.chosen)
    for title, status in (chosen or {}).items():
        if new_chosen.get(title) == status:
            continue
        found = data.get(title)
        if title not in held_now or found is None or status not in found.choose_one:
            raise unprocessable(f"{status} is not a choice of a title {character.name} holds.")
        if title in new_chosen and not staff:
            raise conflict(f"Your {title}'s status {locked}")
        new_chosen[title] = status
    new_absent = list(before.absent)
    away_from = {a.title for t in held_now if (d := data.get(t)) for a in d.while_absent}
    for title, away in (absent or {}).items():
        if title not in away_from:
            raise unprocessable(
                f"No title {character.name} holds gives status while the {title} is absent."
            )
        if away and title not in new_absent:
            new_absent.append(title)
        elif not away and title in new_absent:
            if not staff:
                raise conflict(f"The {title}'s absence {locked}")
            new_absent.remove(title)
    source_changed = new_source != before.source
    after = Choices(
        new_source,
        new_chosen,
        tuple(new_absent),
        Choices.of(game).begun_with,
        checked_in=before.checked_in,
        to_choose=before.to_choose and new_source is None,
    )
    said = choice_text(after, before)
    if not said:
        return
    game.status = after.kept()
    if at.fixed and source_changed:
        note_source(db, user, game, before.source, new_source, reason)
    audit.record(
        db,
        user,
        "play.status_chosen",
        troupe_id=at.troupe.id,
        character_id=character.id,
        game=game.number,
        choice=f"{said} ({reason})" if reason and source_changed else said,
    )
    db.flush()


def note_source(
    db: Session, user: User, game: PlayGame, was: str | None, now: str | None, reason: str
) -> None:
    """Note staff choosing or changing the game's source of abiding status in its log."""
    text = f"From {was} to {now}" if was else f"{now}"
    db.add(
        PlayEvent(
            game_id=game.id,
            client_id=uuid.uuid4(),
            actor_id=user.id,
            happened_at=datetime.now(UTC),
            kind="note",
            tracker=SOURCE_NOTE,
            note=f"{text}: {reason}" if reason else text,
        )
    )


def fixed_for(choices: Choices, game: ScheduledGame) -> str | None:
    """The source fixed as the character checked in to `game`, if it did: checked out
    and in again, it keeps it."""
    return choices.source if choices.checked_in == str(game.id) else None


def fix_at_checkin(
    db: Session,
    user: User,
    character: Character,
    night: PlayGame,
    game: ScheduledGame,
    source: str | None,
    *,
    by_staff: bool,
) -> None:
    """As the character checks in to `game`, where its troupe chooses the source of
    abiding status then: fix it for the night. It is the one fixed at this game's
    check-in already, if any; else its only source; else `source`, which its player
    must give. Staff checking it in by hand may leave a choice of several to make on
    its Play View. A source chosen before check-in, or kept from an earlier game the
    night joined, gives way to the choice made now."""
    if not at_checkin(troupe_of(db, character)):
        return
    begin(db, character, night)
    at = at_game(db, character, night)
    if at.found.sect_data is None or at.troupe is None:
        return
    before = at.choices
    chosen = fixed_for(before, game)
    if chosen is None and len(at.sources) == 1:
        chosen = at.sources[0].name
    elif chosen is None and len(at.sources) > 1:
        if source is not None:
            if not any(s.name == source for s in at.sources):
                raise unprocessable(f"{source} gives {character.name} no abiding status here.")
            chosen = source
        elif not by_staff:
            raise unprocessable(
                f"Choose the one source of abiding status {character.name} carries tonight."
            )
    after = replace(
        before,
        source=chosen,
        checked_in=str(game.id),
        to_choose=chosen is None and len(at.sources) > 1,
    )
    night.status = after.kept()
    if chosen != before.source:
        audit.record(
            db,
            user,
            "play.status_chosen",
            troupe_id=at.troupe.id,
            character_id=character.id,
            game=night.number,
            choice=f"{chosen} as its source of abiding status, at check-in",
        )
    db.flush()


@dataclass(frozen=True)
class Tonight:
    """The source of abiding status a character checked in with, fixed for a game
    still on; None while staff are still to choose it."""

    source: str | None
    to_choose: bool


def carried_tonight(db: Session, character_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Tonight]:
    """The source each character carries into a game on now, where it was fixed as it
    checked in: from its night's choices, while that night and the scheduled game are
    both on. Those not checked in to one, or whose troupe does not fix it, are left
    out."""
    ids = list(character_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(GameAttendance.character_id, GameAttendance.game_id, PlayGame.status)
        .join(PlayGame, GameAttendance.play_game_id == PlayGame.id)
        .join(ScheduledGame, GameAttendance.game_id == ScheduledGame.id)
        .where(
            GameAttendance.character_id.in_(ids),
            GameAttendance.kind == "attended",
            PlayGame.ended_at.is_(None),
            ScheduledGame.ends_at > datetime.now(UTC),
        )
    )
    return {
        character_id: Tonight(kept.get("source"), bool(kept.get("to_choose")))
        for character_id, game_id, kept in rows
        if kept.get("checked_in") == str(game_id)
    }


# --- spending fleeting status for good ---------------------------------------------------------


def record_of(row: HeldStatus) -> dict[str, Any]:
    """A held status as a tap keeps it, to give it back on Undo."""
    return {
        "id": str(row.id),
        "name": row.name,
        "patron_id": str(row.patron_id) if row.patron_id else None,
        "patron_name": row.patron_name,
        "patron_title": row.patron_title,
        "patron_text": row.patron_text,
        "troupe_id": str(row.troupe_id) if row.troupe_id else None,
        "place": row.place,
        "given_on": row.given_on.isoformat(),
        "story": row.story,
        "added_by": str(row.added_by) if row.added_by else None,
        "game_id": str(row.game_id) if row.game_id else None,
        "created_at": row.created_at.isoformat(),
    }


def spend_held(
    db: Session, character: Character, actor: User, tracker: str, note: str
) -> dict[str, Any] | None:
    """Spend a fleeting status for good, from a tap: it leaves the sheet, and the log
    says so. Says its record, for Undo; None if it is gone already (spent on another
    device), and then the tap changes nothing."""
    found = held_id(tracker)
    row = db.get(HeldStatus, found) if found else None
    if row is None or row.character_id != character.id:
        return None
    kept = record_of(row)
    sect_status.remove(
        db, actor, character, troupe_of(db, character), row.id, reason=note, how="spent"
    )
    return kept


def give_back(db: Session, character: Character, actor: User, record: dict[str, Any]) -> None:
    """Undo spending a fleeting status: it is back on the sheet as it was, and the log
    says so."""
    held = uuid.UUID(record["id"])
    if db.get(HeldStatus, held) is not None:
        return

    def linked(key: str, model: type[Any]) -> uuid.UUID | None:
        value = record.get(key)
        return uuid.UUID(value) if value and db.get(model, uuid.UUID(value)) else None

    row = HeldStatus(
        id=held,
        character_id=character.id,
        name=record["name"],
        patron_id=linked("patron_id", Character),
        patron_name=record.get("patron_name", ""),
        patron_title=record.get("patron_title", ""),
        patron_text=record.get("patron_text", ""),
        troupe_id=linked("troupe_id", Troupe),
        place=record.get("place", ""),
        given_on=date.fromisoformat(record["given_on"]),
        story=record.get("story", ""),
        added_by=linked("added_by", User),
        game_id=linked("game_id", PlayGame),
        created_at=datetime.fromisoformat(record["created_at"]),
    )
    db.add(row)
    db.flush()
    troupe = troupe_of(db, character)
    audit.record(
        db,
        actor,
        "status.given_back",
        troupe_id=troupe.id if troupe else None,
        character_id=character.id,
        **sect_status.log_data(row, sect_status.patron_words(row)),
    )
    apply_grants(db, actor, character)

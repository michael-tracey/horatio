"""Sect status on the character (MET: VTM pp. 310-317). What each status does,
the bans, the caps and the status titles give are rules, in horatio.rules.status.

A character's status is of two kinds:

- **derived**, never typed in: abiding status from the active title it holds in
  each troupe (horatio.titles: of several, only the active one gives status, as a
  character carries one abiding source into a game, p. 313), the abiding status
  its sect gives its social age (horatio.social_age: a Camarilla elder's
  Confirmed, Established and Privileged), and innate status its merits grant
  (horatio.rules.grants), which stays a trait on the sheet as everything granted
  does;
- **held**: fleeting and negative status (HeldStatus), each with its patron, where
  and when it was given, and the story: what Leadership reveals (p. 310). Held
  status lives on the character, not a troupe, so it counts in every game of its
  sect.

Only an Accepted character has status: one with a sect that has status rules.
It holds only its own sect's status and the general status, and changing sect
clears what it holds.

**Who adds and removes held status** is the troupe's "Status on sheets" setting
(Troupe.status_by): its players, each on their own character, naming the patron;
or its running staff only. Running staff always can, giving a reason for the log.
The home troupe's setting applies on the sheet, the game's troupe's at a game.
A negative status is removed early only by the one who gave it (the patron's
player) or staff (p. 313).

**The caps** (pp. 312-313): at most 5 fleeting status, 3 under a lesser ban and 1
under a greater; one more asks which to give up, and that one is lost unspent. A
ban applies where the sheet shows it (a clan, a Path) or staff say so, unless they
make the character exempt. Merits and flaws move the cap, on top of any ban
(Reputation 1 more, Tainted Embrace 1 fewer), and the standing says why the cap
is what it is. A character holding Disgraced gains no fleeting status unless staff
override.

**An outsider** (horatio.rules.status.OutsiderData): a character no sect with
status rules has Accepted, holding Emissary to the Camarilla, holds up to one
fleeting Camarilla status (p. 404), and nothing else: no titles, social age or
bans count for it.

**Negative status ends** by its duration (horatio.rules.status.DurationData): after
`games` of the character's Play View games end, not counting the game it was given
at, and `months` calendar months, whichever is later. A stacking status (Warned)
adds the same again for each one held, and they all end together. `expire` drops
what is over, and logs it.

**A negative status that takes status away** (Bloodhunted, p. 389): given it, the
character loses the fleeting status it holds for good, and gains the negative status
it brings (Forsaken) unless it holds that already. While it lasts, its titles, social
age and merits give it none of the types taken away (they are shown as lost), and it
gains no fleeting status: its cap is 0.

**Suppressed** fleeting status (p. 314) is held but neither carried nor gained for a
while, and comes back on its own: while the character holds Vulgar (p. 403), or for
as long as staff say (StatusSuppression): the rest of a game, or 2 games or a month
for defying a Commander.

**Carried into a game** (`carried`): the abiding status of one source (a title, or
social age), all innate and negative status, and fleeting status up to the cap.

**The rules by sect** (`status_rules`), for a troupe's Rules tab: every status of
its sects and the general status, and what gives each there: its titles (the rule
sets' and its own), social ages, factions and merits.
"""

import uuid
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal, get_args

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from horatio import audit, social_age, titles
from horatio.models import (
    Character,
    CharacterTitle,
    HeldStatus,
    PlayEvent,
    PlayGame,
    StatusBanMark,
    StatusSuppression,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.renames import add_months
from horatio.rules.checks import matches
from horatio.rules.model import RuleSetData, SheetTrait
from horatio.rules.status import (
    GENERAL,
    STATUS_CATEGORY,
    DurationData,
    OutsiderData,
    SectData,
    StatusCapsData,
    StatusData,
    TitleData,
)
from horatio.rules.store import read_troupe_rules
from horatio.sheets import (
    apply_grants,
    chosen,
    conflict,
    membership,
    memberships,
    rules_for,
    sheet_effects,
    sheet_rows,
    unprocessable,
)

# Status on sheets: who adds and removes held status in a troupe.
Setting = Literal["players", "staff"]
SETTINGS: tuple[str, ...] = get_args(Setting)
SETTING_TEXT = {
    "players": "players keep their own status",
    "staff": "only staff add or remove status",
}
# Who is making a change: the character's player, or staff.
Acting = Literal["player", "staff"]
HELD_TYPES = ("Fleeting", "Negative")
# The patron of status a sheet held before Horatio kept who gave it.
BEFORE_HORATIO = "(before Horatio)"
# The status that stops a character gaining status (p. 316).
DISGRACED = "Disgraced"
# The status that suppresses its holder's fleeting status while it lasts (p. 403).
VULGAR = "Vulgar"
# How long staff suppress fleeting status for (p. 314).
Suppression = Literal["game", "commander"]
SUPPRESSIONS: dict[str, DurationData] = {
    "game": DurationData(text="For the rest of the game", this_game=True),
    "commander": DurationData(text="2 games or 1 month, whichever is longer", games=2, months=1),
}
SUPPRESSION_TEXT = {"game": "for the rest of the game", "commander": "for defying a Commander"}


# --- what a character has ----------------------------------------------------------------------


@dataclass(frozen=True)
class Patron:
    """Who gave a status: a character picked from the home troupe's, with its name
    (as it is now, if it is still there) and the title it held then; and, or
    instead, words of the giver's own."""

    id: uuid.UUID | None
    name: str
    title: str
    text: str

    @property
    def words(self) -> str:
        picked = f"{self.name} ({self.title} at the time)" if self.title else self.name
        return "; ".join(p for p in (picked, self.text) if p)


@dataclass(frozen=True)
class Ending:
    """When a held status ends: no sooner than `not_before` (its months), and after
    `games_left` more games; while the holder has `while_held` as well; or with the
    game it was given at. `over` once all of that has passed."""

    text: str
    not_before: date | None
    games_left: int
    while_held: str | None
    this_game: bool
    over: bool


@dataclass(frozen=True)
class Held:
    id: uuid.UUID
    name: str
    status: StatusData | None
    patron: Patron
    troupe_id: uuid.UUID | None
    place: str
    given_on: date
    story: str
    added_by: uuid.UUID | None
    added_at: datetime
    game_id: uuid.UUID | None
    ending: Ending | None

    @property
    def type(self) -> str:
        return self.status.type if self.status else ""


@dataclass(frozen=True)
class Derived:
    """Status that comes from something else on the character: a title ("Prince",
    in `troupe_id`), its social age ("Elder"), its faction ("Loyalist"), or the
    merits that grant it."""

    name: str
    type: str
    source: str
    kind: Literal["title", "social_age", "faction", "merit"]
    troupe_id: uuid.UUID | None = None
    # A title's status that holds only sometimes: "one of Blessed or Enforcer,
    # chosen each game", "while the Prince is absent".
    condition: str = ""


@dataclass(frozen=True)
class Suppressed:
    """The character's fleeting status suppressed: by staff (`id`), or while it holds
    Vulgar (`kind` "vulgar", no id)."""

    id: uuid.UUID | None
    kind: Literal["game", "commander", "vulgar"]
    reason: str
    ending: Ending | None

    @property
    def text(self) -> str:
        return "while it holds Vulgar" if self.kind == "vulgar" else SUPPRESSION_TEXT[self.kind]


@dataclass(frozen=True)
class Ban:
    """One of the sect's status bans, and whether it applies to the character: as the
    sheet shows (None where it cannot tell), or as staff marked it."""

    level: str
    applies_to: str
    page: str | None
    by_sheet: bool | None
    marked: bool | None
    reason: str

    @property
    def applies(self) -> bool:
        return self.marked if self.marked is not None else bool(self.by_sheet)


@dataclass
class Standing:
    """A character's status as its sheet shows it."""

    sect: str | None
    sect_data: SectData | None
    rules: RuleSetData
    derived: list[Derived] = field(default_factory=list[Derived])
    held: list[Held] = field(default_factory=list[Held])
    # Status traits on the sheet nothing gives: left by Horatio's move to derived
    # status, for staff to resolve.
    unresolved: list[str] = field(default_factory=list[str])
    bans: list[Ban] = field(default_factory=list[Ban])
    fleeting_cap: int = 0
    # Why the cap is not the usual 5: "a lesser ban: 3", "Tainted Embrace: 1 less".
    cap_why: list[str] = field(default_factory=list[str])
    # Holding a sect's fleeting status though no sect has Accepted it: sect_data is
    # that sect's (Emissary to the Camarilla).
    outsider: OutsiderData | None = None
    # What suppresses its fleeting status now.
    suppressed: list[Suppressed] = field(default_factory=list[Suppressed])
    # The held status that takes status away (Bloodhunted), and the derived status
    # its titles, social age and merits would give, lost while it is held.
    taken_by: str | None = None
    lost: list[Derived] = field(default_factory=list[Derived])

    @property
    def accepted(self) -> str | None:
        """The sect's name for Accepted: Acknowledged, Initiated, Committed. None
        for an outsider, whom the sect has not Accepted."""
        return self.sect_data.accepted if self.sect_data and not self.outsider else None

    @property
    def fleeting(self) -> list[Held]:
        return [h for h in self.held if h.type == "Fleeting"]

    @property
    def negative(self) -> list[Held]:
        return [h for h in self.held if h.type == "Negative"]

    @property
    def disgraced(self) -> bool:
        return any(h.name == DISGRACED for h in self.held)

    @property
    def suppressing(self) -> list[Suppressed]:
        """What suppresses its fleeting status now: not yet over."""
        return [s for s in self.suppressed if not (s.ending and s.ending.over)]

    def own(self, status: StatusData) -> bool:
        """Whether the status is the character's sect's or the general status; for
        an outsider, fleeting status of the sect it may hold."""
        if self.outsider is not None:
            return status.type == "Fleeting" and status.sect in (GENERAL, self.outsider.sect)
        return status.sect in (GENERAL, self.sect)


def sect_of(db: Session, character: Character) -> str | None:
    return chosen(db, character, "sect")


def home_troupe(db: Session, character: Character) -> Troupe | None:
    """The troupe whose setting applies on the sheet, and whose characters can be
    patrons: a PC's home troupe, or the troupe an NPC belongs to."""
    troupe_id = character.home_troupe_id or character.owner_troupe_id
    return db.get(Troupe, troupe_id) if troupe_id else None


def current_troupe_ids(db: Session, character: Character) -> list[uuid.UUID]:
    """The troupes the character holds titles in now: those it is in, home first."""
    ids = [m.troupe_id for m in memberships(db, character)]
    home = character.home_troupe_id or character.owner_troupe_id
    if home is not None:
        ids = [home, *(i for i in ids if i != home)]
    return ids


def active_titles(db: Session, character: Character) -> dict[uuid.UUID, str]:
    """The character's active title in each troupe it holds one in: of its titles
    there, the only one that gives it status (horatio.titles)."""
    return {
        troupe_id: name
        for troupe_id, name in db.execute(
            select(CharacterTitle.troupe_id, CharacterTitle.name).where(
                CharacterTitle.character_id == character.id, CharacterTitle.active
            )
        )
    }


def gives_status(title: TitleData | None, sect: str | None) -> bool:
    """A title gives status to a character of its sect, or to anyone if it has none."""
    return title is not None and title.gives_status and title.sect in (None, sect)


def title_status(title: TitleData, troupe_id: uuid.UUID) -> list[Derived]:
    def given(name: str, condition: str = "") -> Derived:
        return Derived(name, "Abiding", title.name, "title", troupe_id, condition)

    found = [given(s) for s in title.status]
    either = " or ".join(title.choose_one)
    found += [given(s, f"one of {either}, chosen each game") for s in title.choose_one]
    for absent in title.while_absent:
        found += [given(s, f"while the {absent.title} is absent") for s in absent.status]
    return found


# The abiding status a faction gives while its member holds no title of the sect,
# by sect and faction: a Loyalist is no clergy (MET: VTM pp. 439, 447). The status
# data (horatio.rules.status) says so only in words.
FACTION_STATUS = {("Sabbat", "Loyalist"): ("Loyalist",)}


def faction_status(rules: RuleSetData, sect: str | None, faction: str | None) -> list[Derived]:
    names = FACTION_STATUS.get((sect or "", faction or ""), ())
    return [Derived(s, "Abiding", faction or "", "faction") for s in names if s in rules.statuses]


def age_status(rules: RuleSetData, sect: str | None, age: str) -> list[Derived]:
    return [
        Derived(s, "Abiding", age, "social_age")
        for a in rules.status_rules.social_ages
        if a.sect == sect and a.age == age
        for s in a.status
    ]


def caps_of(rules: RuleSetData) -> StatusCapsData:
    return rules.status_rules.caps or StatusCapsData()


def games_ended_since(db: Session, row: HeldStatus | StatusSuppression) -> int:
    """The character's Play View games ended since the status was added, but for the
    game it was given at."""
    query = select(func.count()).where(
        PlayGame.character_id == row.character_id,
        PlayGame.ended_at.is_not(None),
        PlayGame.ended_at > row.created_at,
    )
    if row.game_id is not None:
        query = query.where(PlayGame.id != row.game_id)
    return db.scalar(query) or 0


def endings(
    db: Session, rows: Sequence[HeldStatus], statuses: Mapping[str, StatusData], today: date
) -> dict[uuid.UUID, Ending]:
    """When each held status with a duration ends. A stacking status's rows run one
    after another from the first, and end together."""
    by_name: dict[str, list[HeldStatus]] = defaultdict(list)
    for row in rows:
        by_name[row.name].append(row)
    found: dict[uuid.UUID, Ending] = {}
    # Each status lasting while another is held waits on that one's ending.
    waiting: list[tuple[HeldStatus, StatusData]] = []
    for name, chain in by_name.items():
        status = statuses.get(name)
        duration = status.duration if status else None
        if status is None or duration is None or duration.until_removed:
            continue
        chain.sort(key=lambda r: (r.created_at, r.id))
        groups = [chain] if duration.stacks else [[r] for r in chain]
        for group in groups:
            first, times = group[0], len(group)
            if duration.while_held is not None:
                waiting.append((first, status))
                continue
            ending = lasting(db, first, duration, today, times)
            for row in group:
                found[row.id] = ending
    for row, status in waiting:
        assert status.duration is not None
        duration = status.duration
        other = [
            r
            for r in by_name.get(duration.while_held or "", [])
            if not (r.id in found and found[r.id].over)
        ]
        not_before = add_months(row.given_on, duration.months) if duration.months else None
        left = max(0, (duration.games or 0) - games_ended_since(db, row))
        over = not other and left == 0 and (not_before is None or today >= not_before)
        found[row.id] = Ending(duration.text, not_before, left, duration.while_held, False, over)
    return found


def lasting(
    db: Session,
    first: HeldStatus | StatusSuppression,
    duration: DurationData,
    today: date,
    times: int = 1,
) -> Ending:
    """When something given at `first` ends that lasts `duration`, `times` over: with
    the game it was given at, or after its games and months."""
    if duration.this_game:
        if first.game_id is not None:
            ended = db.scalar(
                select(PlayGame.ended_at.is_not(None)).where(PlayGame.id == first.game_id)
            )
            played = 0 if ended else 1
        else:
            played = max(0, 1 - games_ended_since(db, first))
        return Ending(duration.text, None, played, None, True, played == 0)
    not_before = add_months(first.given_on, duration.months * times) if duration.months else None
    left = max(0, (duration.games or 0) * times - games_ended_since(db, first))
    over = left == 0 and (not_before is None or today >= not_before)
    return Ending(duration.text, not_before, left, None, False, over)


def held_rows(db: Session, character: Character) -> list[HeldStatus]:
    return list(
        db.scalars(
            select(HeldStatus)
            .where(HeldStatus.character_id == character.id)
            .order_by(HeldStatus.given_on, HeldStatus.created_at, HeldStatus.id)
        )
    )


def held(db: Session, character: Character, rules: RuleSetData | None = None) -> list[Held]:
    """The fleeting and negative status the character holds, each with its patron
    record and, for a status that ends, when it does."""
    rules = rules or rules_for(db, character).rule_set
    rows = held_rows(db, character)
    ends = endings(db, rows, rules.statuses, datetime.now(UTC).date())
    patrons = {
        c.id: c
        for c in db.scalars(
            select(Character).where(Character.id.in_({r.patron_id for r in rows} - {None}))
        )
    }
    found: list[Held] = []
    for row in rows:
        linked = patrons.get(row.patron_id) if row.patron_id else None
        found.append(
            Held(
                id=row.id,
                name=row.name,
                status=rules.statuses.get(row.name),
                patron=Patron(
                    id=row.patron_id,
                    name=linked.name if linked else row.patron_name,
                    title=row.patron_title,
                    text=row.patron_text,
                ),
                troupe_id=row.troupe_id,
                place=row.place,
                given_on=row.given_on,
                story=row.story,
                added_by=row.added_by,
                added_at=row.created_at,
                game_id=row.game_id,
                ending=ends.get(row.id),
            )
        )
    return found


def suppression_rows(db: Session, character: Character) -> list[StatusSuppression]:
    return list(
        db.scalars(
            select(StatusSuppression)
            .where(StatusSuppression.character_id == character.id)
            .order_by(StatusSuppression.created_at, StatusSuppression.id)
        )
    )


def suppressions(db: Session, character: Character, held: Sequence[Held]) -> list[Suppressed]:
    """What suppresses the character's fleeting status (p. 314), with when each ends:
    staff's, and Vulgar while it is held (p. 403). Those over are left in, to expire."""
    today = datetime.now(UTC).date()
    found = [
        Suppressed(r.id, r.kind, r.reason, lasting(db, r, SUPPRESSIONS[r.kind], today))  # pyright: ignore[reportArgumentType]
        for r in suppression_rows(db, character)
    ]
    found += [
        Suppressed(None, "vulgar", "", h.ending)
        for h in held
        if h.name == VULGAR and not (h.ending and h.ending.over)
    ]
    return found


def bans_of(
    db: Session, character: Character, sect: SectData | None, sheet: Sequence[SheetTrait]
) -> list[Ban]:
    if sect is None:
        return []
    marks = {
        m.ban: m
        for m in db.scalars(
            select(StatusBanMark).where(
                StatusBanMark.character_id == character.id, StatusBanMark.sect == sect.name
            )
        )
    }
    subject = SheetTrait(category="sect", name=sect.name, rating=None)
    found: list[Ban] = []
    for ban in sect.bans:
        mark = marks.get(ban.applies_to)
        found.append(
            Ban(
                level=ban.level,
                applies_to=ban.applies_to,
                page=ban.page,
                by_sheet=matches(ban.when, sheet, subject) if ban.when else None,
                marked=mark.applies if mark else None,
                reason=mark.reason if mark else "",
            )
        )
    return found


def less_or_more(amount: int) -> str:
    return f"{amount} more" if amount > 0 else f"{-amount} less"


def fleeting_cap(
    rules: RuleSetData,
    bans: Sequence[Ban],
    sheet: Sequence[SheetTrait] = (),
    outsider: OutsiderData | None = None,
) -> tuple[int, list[str]]:
    """The most fleeting status the character carries, and why it is not the usual:
    its bans, then the merits and flaws on its sheet that move it. Never below 0."""
    caps = caps_of(rules)
    levels = {b.level for b in bans if b.applies}
    if outsider is not None:
        cap, why = outsider.fleeting, [f"{outsider.name}: {outsider.fleeting}"]
    elif "greater" in levels:
        cap, why = caps.greater_ban, [f"a greater ban: {caps.greater_ban}"]
    elif "lesser" in levels:
        cap, why = caps.lesser_ban, [f"a lesser ban: {caps.lesser_ban}"]
    else:
        cap, why = caps.fleeting, []
    held = {(t.category, t.name) for t in sheet if t.rating is None or t.rating > 0}
    for change in rules.status_rules.cap_changes:
        if (change.category, change.name) in held:
            cap += change.fleeting
            why.append(f"{change.name}: {less_or_more(change.fleeting)}")
    return max(0, cap), why


def outsider_of(
    rules: RuleSetData, sect: str | None, sheet: Sequence[SheetTrait]
) -> OutsiderData | None:
    """What lets a character no sect with status rules has Accepted hold a sect's
    fleeting status, if its sheet holds it."""
    if sect is not None and sect in rules.status_rules.sects:
        return None
    held = {(t.category, t.name) for t in sheet if t.rating is None or t.rating > 0}
    return next(
        (
            o
            for o in rules.status_rules.outsiders
            if (o.category, o.name) in held and o.sect in rules.status_rules.sects
        ),
        None,
    )


def standing(db: Session, character: Character) -> Standing:
    """The character's status as its sheet shows it: what it holds, what comes from
    its titles in each of its troupes, its social age and its merits, and the bans
    and cap on its fleeting status."""
    rules = rules_for(db, character).rule_set
    rows = sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
    sect = next((r.definition.name for r in rows if r.category.key == "sect"), None)
    sect_data = rules.status_rules.sects.get(sect) if sect else None
    outsider = outsider_of(rules, sect, sheet)
    found = Standing(sect=sect, sect_data=sect_data, rules=rules)
    if outsider is not None:
        found.outsider = outsider
        found.sect_data = rules.status_rules.sects[outsider.sect]
    if sect_data is not None:
        holding = active_titles(db, character)
        for troupe_id in current_troupe_ids(db, character):
            name = holding.get(troupe_id)
            if name is None:
                continue
            title = titles.title_data(db, troupe_id).get(name)
            if title is not None and gives_status(title, sect):
                found.derived += title_status(title, troupe_id)
        # Ancilla and Elder, as titles, give nothing: social age gives their status.
        age = social_age.standings(db, [character.id])[character.id].age
        found.derived += age_status(rules, sect, age)
        if not any(d.kind == "title" for d in found.derived):
            faction = next((r.definition.name for r in rows if r.category.key == "faction"), None)
            found.derived += faction_status(rules, sect, faction)
    sources = sheet_effects(db, character).sources
    for row in rows:
        if row.category.key != STATUS_CATEGORY or not row.trait.rating:
            continue
        name = row.definition.name
        if row.trait.granted_rating:
            status = rules.statuses.get(name)
            givers = ", ".join(sources.get(row.key, [])) or "a merit"
            kind = status.type if status else "Innate"
            found.derived.append(Derived(name, kind, givers, "merit"))
        if (row.trait.rating or 0) > row.trait.granted_rating:
            found.unresolved.append(name)
    found.held = held(db, character, rules)
    found.suppressed = suppressions(db, character, found.held)
    found.bans = bans_of(db, character, sect_data, sheet)
    found.fleeting_cap, found.cap_why = fleeting_cap(rules, found.bans, sheet, outsider)
    taking = next((h for h in found.held if taking_away(found, h)), None)
    if taking is not None and taking.status is not None:
        taken = taking.status.takes_away
        found.taken_by = taking.name
        found.lost = [d for d in found.derived if d.type in taken]
        found.derived = [d for d in found.derived if d.type not in taken]
        if "Fleeting" in taken:
            found.fleeting_cap, found.cap_why = 0, [f"{taking.name}: none"]
    return found


def taking_away(found: Standing, h: Held) -> bool:
    """Whether a held status takes status away from the character now (Bloodhunted)."""
    return (
        h.status is not None
        and bool(h.status.takes_away)
        and found.own(h.status)
        and not (h.ending and h.ending.over)
    )


# --- what it carries into a game ---------------------------------------------------------------


@dataclass(frozen=True)
class Carried:
    """One status a character carries into a game, and where it comes from: a title,
    its social age, a merit, or (held) its patron."""

    name: str
    type: str
    source: str
    status: StatusData | None
    # A held status's record.
    held: Held | None = None


@dataclass(frozen=True)
class AbidingSource:
    """One source of abiding status in a troupe: a title, social age, or a faction."""

    name: str
    kind: Literal["title", "social_age", "faction"]
    status: tuple[Derived, ...]


def abiding_sources(
    found: Standing, troupe_id: uuid.UUID, begun_with: Collection[str] | None = None
) -> list[AbidingSource]:
    """The character's sources of abiding status at a game in `troupe_id`, in order:
    its titles there by name, then its social age, then its faction. Its titles in
    other troupes give nothing here; nor, with `begun_with` (the titles it held there
    as the game began), does a title given since, until the next game (p. 311)."""
    sources: dict[str, list[Derived]] = {}
    for d in found.derived:
        here = d.troupe_id == troupe_id and (begun_with is None or d.source in begun_with)
        if d.kind == "title" and here or d.kind in ("social_age", "faction"):
            sources.setdefault(d.source, []).append(d)
    order = {"title": 0, "social_age": 1, "faction": 2}
    named = sorted(sources, key=lambda n: (order[sources[n][0].kind], n))
    return [
        AbidingSource(name, sources[name][0].kind, tuple(sources[name]))  # pyright: ignore[reportArgumentType]
        for name in named
    ]


def carried(
    db: Session,
    character: Character,
    troupe_id: uuid.UUID,
    *,
    abiding_source: str | None = None,
    chosen: Mapping[str, str] | None = None,
    absent: Collection[str] = (),
    begun_with: Collection[str] | None = None,
    or_first: bool = True,
    found: Standing | None = None,
) -> list[Carried]:
    """The status the character carries into a game in `troupe_id` (p. 312): the
    abiding status of one source (`abiding_source`, a title or social age by name,
    or else, `or_first`, the first of `abiding_sources`), all its innate and negative
    status, and its fleeting status up to the cap, oldest first, unless it is
    suppressed. Of a title's conditional status it carries the one `chosen` for that
    title (a Bishop's Blessed or Enforcer), and what it gives while the holder of a
    title in `absent` is away. A title given since the game began (not in
    `begun_with`) gives nothing. Only status of its sect and the general status
    count; Accepted is not status. `found` is its standing, if already worked out."""
    found = found or standing(db, character)
    if found.sect_data is None:
        return []
    chosen = chosen or {}
    out: list[Carried] = []
    statuses = found.rules.statuses

    sources = abiding_sources(found, troupe_id, begun_with)
    first = next(iter(sources), None) if or_first else None
    source = next((s for s in sources if s.name == abiding_source), first)
    if source is not None:
        title = titles.title_data(db, troupe_id).get(source.name)
        if source.kind != "title":
            title = None
        for d in source.status:
            if title is not None and d.name not in title.status:
                in_choice = d.name in title.choose_one and chosen.get(title.name) == d.name
                while_absent = any(
                    d.name in a.status and a.title in absent for a in title.while_absent
                )
                if not (in_choice or while_absent):
                    continue
            if any(c.name == d.name for c in out):
                continue
            out.append(Carried(d.name, "Abiding", d.source, statuses.get(d.name)))
    for d in found.derived:
        if d.kind == "merit":
            out.append(Carried(d.name, "Innate", d.source, statuses.get(d.name)))
    live = [
        h
        for h in found.held
        if h.status and found.own(h.status) and not (h.ending and h.ending.over)
    ]
    for h in live:
        if h.type == "Negative":
            out.append(Carried(h.name, "Negative", h.patron.words, h.status, h))
    if not found.suppressing:
        for h in [h for h in live if h.type == "Fleeting"][: found.fleeting_cap]:
            out.append(Carried(h.name, "Fleeting", h.patron.words, h.status, h))
    return out


# --- naming the patron -------------------------------------------------------------------------


@dataclass(frozen=True)
class PatronChoice:
    id: uuid.UUID
    name: str
    kind: str
    # The titles it holds in the troupe, "Prince, Harpy"; empty for none.
    title: str


def patron_choices(db: Session, character: Character) -> list[PatronChoice]:
    """Who can be picked as the patron of status given to `character`: its home
    troupe's PCs, and that troupe's NPCs holding a title there of the character's
    sect, each with the titles it holds there. Never the character itself."""
    home = home_troupe(db, character)
    if home is None:
        return []
    sect = sect_of(db, character)
    held_there: dict[uuid.UUID, list[str]] = defaultdict(list)
    for who, name in db.execute(
        select(CharacterTitle.character_id, CharacterTitle.name)
        .where(CharacterTitle.troupe_id == home.id)
        .order_by(CharacterTitle.name)
    ):
        held_there[who].append(name)
    data = titles.title_data(db, home.id)
    found: list[PatronChoice] = []
    for c in db.scalars(
        select(Character)
        .where(
            Character.status == "active",
            Character.id != character.id,
            (Character.kind == "pc") & (Character.home_troupe_id == home.id)
            | (Character.kind == "npc") & (Character.owner_troupe_id == home.id),
        )
        .order_by(Character.name)
    ):
        names = held_there.get(c.id, [])
        of_sect = any((t := data.get(n)) is not None and t.sect == sect for n in names)
        if c.kind == "npc" and not (sect and of_sect):
            continue
        found.append(PatronChoice(c.id, c.name, c.kind, ", ".join(names)))
    return found


# --- who can change it -------------------------------------------------------------------------


def setting_of(troupe: Troupe | None) -> str:
    return troupe.status_by if troupe is not None else "players"


def staff_in(db: Session, user: User, character: Character, troupe: Troupe | None) -> bool:
    """The custodian, or the running staff of a troupe the character is in (or that
    keeps it, for an NPC)."""
    if user.is_custodian:
        return True
    if troupe is None or troupe.archived_at is not None:
        return False
    if character.owner_troupe_id != troupe.id and membership(db, character, troupe.id) is None:
        return False
    return allows(troupe_role(db, user, troupe), TroupeAction.CHANGE_STATUS)


def is_player(user: User, character: Character) -> bool:
    return character.kind == "pc" and character.player_id == user.id


def may_change(
    db: Session, user: User, character: Character, troupe: Troupe | None
) -> Acting | None:
    """Whether `user` adds and removes the character's held status where `troupe`'s
    setting applies (the home troupe on the sheet, a game's troupe at a game), and
    as whom: its player, where players keep their own, or staff."""
    if is_player(user, character) and setting_of(troupe) == "players":
        return "player"
    if staff_in(db, user, character, troupe):
        return "staff"
    return None


def require_change(db: Session, user: User, character: Character, troupe: Troupe | None) -> Acting:
    acting = may_change(db, user, character, troupe)
    if acting is None:
        if is_player(user, character):
            raise conflict("Only staff add or remove status in this troupe.")
        raise conflict("You cannot change this character's status.")
    return acting


def reason_needed(user: User, character: Character, acting: Acting, reason: str) -> str:
    """Staff changing a PC's status say why, for its log."""
    reason = reason.strip()
    as_staff = acting == "staff" and character.kind == "pc" and not is_player(user, character)
    if as_staff and not reason:
        raise unprocessable("Give a reason: it goes in the character's log.")
    return reason


def game_in_progress(db: Session, character: Character) -> uuid.UUID | None:
    """The character's Play View game, if it has begun: status added during it is
    given at it, and the game does not count toward the status's end."""
    game = db.scalar(
        select(PlayGame).where(PlayGame.character_id == character.id, PlayGame.ended_at.is_(None))
    )
    if game is None:
        return None
    tapped = db.scalar(select(PlayEvent.id).where(PlayEvent.game_id == game.id).limit(1))
    return game.id if tapped is not None else None


# --- changing it -------------------------------------------------------------------------------


def log_data(row: HeldStatus, patron: str) -> dict[str, str]:
    return {"status": row.name, "patron": patron}


def patron_words(row: HeldStatus) -> str:
    return Patron(row.patron_id, row.patron_name, row.patron_title, row.patron_text).words


def add(
    db: Session,
    user: User,
    character: Character,
    troupe: Troupe | None,
    *,
    name: str,
    patron_id: uuid.UUID | None = None,
    patron_text: str = "",
    place: str = "",
    given_on: date | None = None,
    story: str = "",
    reason: str = "",
    give_up: uuid.UUID | None = None,
    override: bool = False,
    game_id: uuid.UUID | None = None,
) -> HeldStatus:
    """Give the character a fleeting or negative status of its sect, named for its
    patron, as the troupe's setting allows. At the fleeting cap it gives up
    `give_up`, lost unspent. `game_id` is the game it is given at, if any; else the
    game the character is playing now, if it has begun."""
    acting = require_change(db, user, character, troupe)
    expire(db, character, user)
    found = standing(db, character)
    if found.sect_data is None:
        raise conflict(
            f"{character.name} has no status: only a character of the Camarilla, the Sabbat or"
            " the Anarchs, as its sect, holds it."
            if found.sect is None or found.sect not in found.rules.status_rules.sects
            else f"{character.name} has no status."
        )
    status = found.rules.statuses.get(name)
    if status is None or status.type not in HELD_TYPES:
        raise unprocessable(f"{name} is not fleeting or negative status.")
    if not found.own(status):
        raise unprocessable(
            f"{character.name} is Accepted by no sect, and through {found.outsider.name} holds"
            f" only fleeting {found.outsider.sect} status."
            if found.outsider is not None
            else f"{name} is {status.sect} status, and {character.name} is {found.sect}."
        )
    reason = reason_needed(user, character, acting, reason)

    patron_text = patron_text.strip()
    patron_name = patron_title = ""
    if patron_id is not None:
        choice = next((c for c in patron_choices(db, character) if c.id == patron_id), None)
        if choice is None:
            raise unprocessable("Pick the patron from the home troupe's characters, or name them.")
        patron_name, patron_title = choice.name, choice.title
    elif not patron_text:
        raise unprocessable("Name the patron: pick a character, say who, or both.")

    if status.type == "Fleeting" and found.disgraced and not (acting == "staff" and override):
        disgraced = found.rules.statuses.get(DISGRACED)
        page = f" (p. {disgraced.page})" if disgraced and disgraced.page else ""
        raise conflict(
            f"{character.name} holds Disgraced, and gains no status while it does{page}."
        )

    if status.type == "Fleeting" and found.suppressing and not (acting == "staff" and override):
        why = found.suppressing[0].text
        raise conflict(
            f"{character.name}'s fleeting status is suppressed {why}, and it gains none"
            " meanwhile (p. 314)."
        )

    giving_up: HeldStatus | None = None
    if give_up is not None:
        giving_up = db.get(HeldStatus, give_up)
        if giving_up is None or giving_up.character_id != character.id:
            raise unprocessable("Give up a status the character holds.")
    if status.type == "Fleeting":
        fleeting = [h for h in found.fleeting if not (giving_up and h.id == giving_up.id)]
        if giving_up is not None and giving_up.id not in {h.id for h in found.fleeting}:
            raise unprocessable("Give up one of the character's fleeting status.")
        if len(fleeting) >= found.fleeting_cap:
            caps = caps_of(found.rules)
            page = f" (p. {caps.page})" if caps.page else ""
            why = f" ({', '.join(found.cap_why)})" if found.cap_why else ""
            raise conflict(
                f"{character.name} can hold no fleeting status{why}."
                if found.fleeting_cap == 0
                else f"{character.name} can hold {found.fleeting_cap} fleeting status{page}{why}:"
                " choose one to give up for this one."
                if len(fleeting) == found.fleeting_cap
                else f"{character.name} holds {len(fleeting)} fleeting status, over its"
                f" {found.fleeting_cap}: remove some first."
            )

    home = troupe or home_troupe(db, character)
    row = HeldStatus(
        character_id=character.id,
        name=name,
        patron_id=patron_id,
        patron_name=patron_name,
        patron_title=patron_title,
        patron_text=patron_text,
        troupe_id=home.id if home else None,
        place=place.strip() or (home.name if home else ""),
        given_on=given_on or datetime.now(UTC).date(),
        story=story.strip(),
        added_by=user.id,
        game_id=game_id or game_in_progress(db, character),
    )
    db.add(row)
    db.flush()
    patron = Patron(patron_id, patron_name, patron_title, patron_text).words
    at_game = db.get(PlayGame, row.game_id) if row.game_id else None
    troupe_id = home.id if home else None
    if giving_up is not None:
        audit.record(
            db,
            user,
            "status.given_up",
            troupe_id=troupe_id,
            character_id=character.id,
            **log_data(giving_up, patron_words(giving_up)),
            instead=name,
        )
        db.delete(giving_up)
    audit.record(
        db,
        user,
        "status.added",
        troupe_id=troupe_id,
        character_id=character.id,
        **log_data(row, patron),
        type=status.type.lower(),
        override=override
        and (found.disgraced or bool(found.suppressing))
        and status.type == "Fleeting",
        reason=reason,
        **({"game": at_game.number} if at_game else {}),
    )
    if "Fleeting" in status.takes_away and found.fleeting:
        lose_fleeting(db, user, character, troupe_id, found.fleeting, name)
    holding = {h.name for h in found.held}
    for brought in status.brings:
        if brought in holding or brought not in found.rules.statuses:
            continue
        db.add(
            HeldStatus(
                character_id=character.id,
                name=brought,
                patron_id=row.patron_id,
                patron_name=row.patron_name,
                patron_title=row.patron_title,
                patron_text=row.patron_text,
                troupe_id=row.troupe_id,
                place=row.place,
                given_on=row.given_on,
                story=row.story,
                added_by=user.id,
                game_id=row.game_id,
            )
        )
        audit.record(
            db,
            user,
            "status.added",
            troupe_id=troupe_id,
            character_id=character.id,
            status=brought,
            patron=patron,
            type=found.rules.statuses[brought].type.lower(),
            reason=f"with {name}",
            **({"game": at_game.number} if at_game else {}),
        )
    db.flush()
    apply_grants(db, user, character)
    return row


def lose_fleeting(
    db: Session,
    user: User,
    character: Character,
    troupe_id: uuid.UUID | None,
    fleeting: Sequence[Held],
    by: str,
) -> None:
    """The character loses its fleeting status for good, as `by` (Bloodhunted) takes it
    away: not spent, and not coming back."""
    audit.record(
        db,
        user,
        "status.lost",
        troupe_id=troupe_id,
        character_id=character.id,
        statuses=", ".join(h.name for h in fleeting),
        by=by,
    )
    db.execute(delete(HeldStatus).where(HeldStatus.id.in_([h.id for h in fleeting])))


def remove(
    db: Session,
    user: User,
    character: Character,
    troupe: Troupe | None,
    held_id: uuid.UUID,
    *,
    reason: str = "",
    how: Literal["removed", "spent"] = "removed",
) -> None:
    """Take a held status off the character: removed, as the troupe's setting allows
    (a negative status only by the one who gave it, or staff); or `spent`, a fleeting
    status gone for good, which is always its holder's to do."""
    row = db.get(HeldStatus, held_id)
    if row is None or row.character_id != character.id:
        raise unprocessable("The character does not hold that status.")
    status = rules_for(db, character).rule_set.statuses.get(row.name)
    patron = db.get(Character, row.patron_id) if row.patron_id else None
    gave_it = patron is not None and is_player(user, patron)
    if how == "spent":
        if status is None or status.type != "Fleeting":
            raise unprocessable("Only fleeting status is spent for good.")
        acting: Acting = (
            "player" if is_player(user, character) else require_change(db, user, character, troupe)
        )
    elif gave_it and status is not None and status.type == "Negative":
        acting = "player"
    else:
        acting = require_change(db, user, character, troupe)
        if acting == "player" and status is not None and status.type == "Negative":
            raise conflict(f"Only the one who gave {row.name}, or staff, remove it before it ends.")
    # Spending is a move in the game, not a change to the sheet: it needs no reason.
    spending = how == "spent" or gave_it
    reason = reason.strip() if spending else reason_needed(user, character, acting, reason)
    home = troupe or home_troupe(db, character)
    audit.record(
        db,
        user,
        f"status.{how}",
        troupe_id=home.id if home else None,
        character_id=character.id,
        **log_data(row, patron_words(row)),
        reason=reason,
    )
    db.delete(row)
    db.flush()
    apply_grants(db, user, character)


def expire(db: Session, character: Character, user: User) -> list[str]:
    """Drop the character's held status that is over, logging each as ended by
    itself, and staff's suppressions of its fleeting status that are over. Says which
    status ended. `user` is whoever's request found it over."""
    found = held(db, character)
    over = [h for h in found if h.ending and h.ending.over]
    lifted = [s for s in suppressions(db, character, found) if s.id and s.ending and s.ending.over]
    home = home_troupe(db, character)
    for s in lifted:
        audit.record(
            db,
            None,
            "status.suppression_ended",
            troupe_id=home.id if home else None,
            character_id=character.id,
            why=s.text,
        )
    if lifted:
        db.execute(
            delete(StatusSuppression).where(StatusSuppression.id.in_([s.id for s in lifted]))
        )
        db.flush()
    if not over:
        return []
    for h in over:
        audit.record(
            db,
            None,
            "status.expired",
            troupe_id=home.id if home else None,
            character_id=character.id,
            status=h.name,
            patron=h.patron.words,
        )
    db.execute(delete(HeldStatus).where(HeldStatus.id.in_([h.id for h in over])))
    db.flush()
    apply_grants(db, user, character)
    return [h.name for h in over]


def clear(db: Session, user: User, character: Character, sect: str | None) -> None:
    """A character changing sect loses all the status it holds; the log says what."""
    rows = held_rows(db, character)
    if not rows:
        return
    home = home_troupe(db, character)
    audit.record(
        db,
        user,
        "status.cleared",
        troupe_id=home.id if home else None,
        character_id=character.id,
        statuses=", ".join(r.name for r in rows),
        sect=sect or "none",
    )
    db.execute(delete(HeldStatus).where(HeldStatus.character_id == character.id))
    db.flush()


def resolve(db: Session, user: User, character: Character, name: str, reason: str) -> None:
    """Staff take off a status trait the sheet held before status was derived, that
    no title, social age or merit now gives (`Standing.unresolved`). Any part a
    merit grants stays."""
    troupe = home_troupe(db, character)
    if not staff_in(db, user, character, troupe):
        raise conflict("Only staff resolve status left from before.")
    reason = reason_needed(user, character, "staff", reason)
    rows = [
        r
        for r in sheet_rows(db, character)
        if r.category.key == STATUS_CATEGORY
        and r.definition.name == name
        and (r.trait.rating or 0) > r.trait.granted_rating
    ]
    if not rows:
        raise unprocessable(f"{character.name} has no {name} to resolve.")
    for row in rows:
        if row.trait.granted_rating:
            row.trait.rating = row.trait.free_rating = row.trait.granted_rating
            row.trait.creation_pick = None
        else:
            db.delete(row.trait)
    audit.record(
        db,
        user,
        "status.resolved",
        troupe_id=troupe.id if troupe else None,
        character_id=character.id,
        status=name,
        reason=reason,
    )
    db.flush()


def mark_ban(
    db: Session, user: User, character: Character, ban: str, applies: bool | None, reason: str
) -> None:
    """Staff say a status ban of the character's sect applies to it, or that it is
    exempt, with their reason; or (None) go back to what the sheet shows."""
    troupe = home_troupe(db, character)
    if not staff_in(db, user, character, troupe):
        raise conflict("Only staff mark a status ban.")
    found = standing(db, character)
    if found.sect_data is None or not any(b.applies_to == ban for b in found.bans):
        raise unprocessable("That is not a status ban of the character's sect.")
    reason = reason.strip()
    if applies is not None and not reason:
        raise unprocessable("Give a reason: it goes in the character's log.")
    db.execute(
        delete(StatusBanMark).where(
            StatusBanMark.character_id == character.id,
            StatusBanMark.sect == found.sect_data.name,
            StatusBanMark.ban == ban,
        )
    )
    if applies is not None:
        db.add(
            StatusBanMark(
                character_id=character.id,
                sect=found.sect_data.name,
                ban=ban,
                applies=applies,
                reason=reason,
                marked_by=user.id,
            )
        )
    audit.record(
        db,
        user,
        "status.ban_marked",
        troupe_id=troupe.id if troupe else None,
        character_id=character.id,
        ban=ban,
        mark={True: "applies", False: "exempt", None: "as the sheet shows"}[applies],
        reason=reason,
    )
    db.flush()


def suppress(
    db: Session, user: User, character: Character, kind: Suppression, reason: str
) -> StatusSuppression:
    """Staff strip the character's fleeting status without its being spent (p. 314):
    it carries none into a game and gains none, for the rest of the game, or for 2
    games or a month for defying a Commander. Then it has it back on its own."""
    troupe = home_troupe(db, character)
    if not staff_in(db, user, character, troupe):
        raise conflict("Only staff suppress status.")
    reason = reason.strip()
    if not reason:
        raise unprocessable("Give a reason: it goes in the character's log.")
    row = StatusSuppression(
        character_id=character.id,
        kind=kind,
        reason=reason,
        given_on=datetime.now(UTC).date(),
        game_id=game_in_progress(db, character),
        added_by=user.id,
    )
    db.add(row)
    audit.record(
        db,
        user,
        "status.suppressed",
        troupe_id=troupe.id if troupe else None,
        character_id=character.id,
        why=SUPPRESSION_TEXT[kind],
        reason=reason,
    )
    db.flush()
    return row


def lift(
    db: Session, user: User, character: Character, suppression_id: uuid.UUID, reason: str
) -> None:
    """Staff give the character back its suppressed fleeting status early."""
    troupe = home_troupe(db, character)
    if not staff_in(db, user, character, troupe):
        raise conflict("Only staff lift a suppression.")
    row = db.get(StatusSuppression, suppression_id)
    if row is None or row.character_id != character.id:
        raise unprocessable("The character's status is not suppressed so.")
    audit.record(
        db,
        user,
        "status.suppression_lifted",
        troupe_id=troupe.id if troupe else None,
        character_id=character.id,
        why=SUPPRESSION_TEXT[row.kind],
        reason=reason.strip(),
    )
    db.delete(row)
    db.flush()


# --- the rules, by sect ------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusSource:
    """Where a status comes from in a troupe: a title it gives (`house`: the troupe's
    own), a social age, a faction, or a merit that grants it."""

    kind: Literal["title", "social_age", "faction", "merit"]
    name: str
    page: str | None = None
    # A title's other names: a Harpy is also a Master Harpy.
    aliases: tuple[str, ...] = ()
    # "while the Prince is absent", "one of Blessed or Enforcer, chosen each game".
    condition: str = ""
    house: bool = False


@dataclass(frozen=True)
class StatusRule:
    status: StatusData
    sources: tuple[StatusSource, ...]


@dataclass(frozen=True)
class SectRules:
    """A sect's status (General: the status every sect has), with its Accepted."""

    sect: str
    accepted: str | None
    page: str | None
    statuses: tuple[StatusRule, ...]


def status_rules(db: Session, troupe: Troupe) -> tuple[StatusCapsData, list[SectRules]]:
    """Every status of the sects the troupe takes, and the general status, by sect:
    what each does, and where it comes from here (its titles, the rule sets' and its
    own, social ages, factions and merits). Also the caps."""
    rules = read_troupe_rules(db, "vampire", troupe.id).rule_set
    data = titles.title_data(db, troupe.id)
    order = titles.court_order(db, troupe.id)
    house = {t.name for t in titles.house_titles(db, troupe.id)}
    found: dict[str, list[StatusSource]] = defaultdict(list)
    offices = sorted(
        (t for t in data.values() if t.alias_of is None and titles.offers(troupe, t)),
        key=lambda t: titles.court_key(order, t.name),
    )
    for title in offices:
        aliases = tuple(n for n, t in data.items() if t.alias_of == title.name)
        for given in title_status(title, troupe.id):
            found[given.name].append(
                StatusSource(
                    "title", title.name, title.page, aliases, given.condition, title.name in house
                )
            )
    sects = [GENERAL, *titles.troupe_sects(db, troupe)]
    for age in rules.status_rules.social_ages:
        if age.sect in sects:
            for name in age.status:
                found[name].append(StatusSource("social_age", age.age, age.page))
    for (sect, faction), names in FACTION_STATUS.items():
        if sect in sects:
            for name in names:
                found[name].append(StatusSource("faction", faction))
    for grant in rules.grants:
        if grant.target.get("category") == STATUS_CATEGORY and "name" in grant.target:
            found[grant.target["name"]].append(
                StatusSource("merit", grant.source.get("name", ""), grant.page)
            )
    kinds = {kind: i for i, kind in enumerate(("Accepted", "Abiding", "Innate", "Fleeting"))}
    by_sect: list[SectRules] = []
    for sect in sects:
        statuses = sorted(
            (s for s in rules.statuses.values() if s.sect == sect),
            key=lambda s: (kinds.get(s.type, len(kinds)), s.name),
        )
        if not statuses:
            continue
        sect_data = rules.status_rules.sects.get(sect)
        by_sect.append(
            SectRules(
                sect=sect,
                accepted=sect_data.accepted if sect_data else None,
                page=sect_data.page if sect_data else None,
                statuses=tuple(StatusRule(s, tuple(found.get(s.name, ()))) for s in statuses),
            )
        )
    return caps_of(rules), by_sect

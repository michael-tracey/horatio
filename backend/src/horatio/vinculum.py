"""The Vinculum and the Vaulderie (#666; MET: VTM pp. 433-435, and the Errata's p. 434).

Only for a troupe that allows the Sabbat (its allowed sects are any, or include the
Sabbat) and tracks blood bonds: with Blood bonds off, or in a Camarilla-only troupe,
none of it shows anywhere. Its log lines are "bond." ones, so they hide with the rest
of the troupe's bonds when the setting is off (horatio.bonds.hidden_events).

**The Vaulderie log.** Each Vaulderie is a night, who took part (characters, NPCs and
names only), who officiated, and any false Sabbat among them: one who drank but gave
no blood. The troupe's running staff record them. In the player modes a player can
report one their own character took part in; it waits for staff to approve, in either
mode, because it changes the other participants' ratings and blood bonds too.

**Ratings.** A Vinculum rating is never typed in: it comes from the Vaulderies two
shared, counting each night once however many they shared that night (p. 434). It
runs from each to the other, except that a false Sabbat gains a rating to the others
without them gaining one to the false Sabbat from that Vaulderie (the Errata's p.
434). As of a day, from the nights shared (`rating_of`):

- 1, after the first: permanent;
- 2, more than once in the past year;
- 3, more than 10 times in the past year;
- 4, about weekly for the past three months, never missing more than two weeks in a
  row: no gap between Vaulderies, nor at either end of the three months, over three
  weeks;
- 5, every few days for the past three months: no such gap over four days.

So a rating thins as the history does: a 2 returns to 1 after a year without
another. Staff can enter a background tie (p. 435's example): two who shared
Vaulderies before Horatio, at a rating on a night. It counts as the history that
would give that rating then (`tie_nights`), so it thins the same way.

**The blood bond.** The Errata's p. 434: anyone who takes part in a Vaulderie has all
their blood bonds lowered one step, at most once a night. Recording a Vaulderie (or
approving one reported) lowers each participant's bonds that this troupe keeps, as
thrall: a step down goes in the bond's log as a "vaulderie" line, and a bond of one
drink ends. The thrall took part, so their player sees the change at once. Removing a
Vaulderie afterwards doesn't raise them again; staff put a bond back by hand.

**Who sees it.** A Vinculum is mutual and known to both: each character's player sees
the ratings their character feels, and the troupe's running staff see them all. Nobody
else does.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from horatio import audit, bonds
from horatio.models import (
    BloodBond,
    BondEntry,
    Character,
    Troupe,
    User,
    Vaulderie,
    VaulderieParticipant,
    VinculumTie,
)
from horatio.sheets import conflict, unprocessable

PAGE = "p. 434"
SABBAT = "Sabbat"
RATINGS = range(1, 6)
# The most a Vaulderie may name, and a name or note may be.
LONGEST_NAME = bonds.LONGEST_NAME
MOST_PARTICIPANTS = 40
# The longest gap that still counts as about weekly (missing at most two weeks in a
# row), and as every few days.
WEEKLY_GAP = 21
FEW_DAYS_GAP = 4
SOURCES = bonds.SOURCES
PLAYER_SOURCES = bonds.PLAYER_SOURCES
# A Vaulderie that counts toward ratings.
COUNTS = "recorded"


def on(troupe: Troupe) -> bool:
    """The troupe tracks blood bonds and allows the Sabbat."""
    return bonds.tracked(troupe) and (not troupe.allowed_sects or SABBAT in troupe.allowed_sects)


# --- who --------------------------------------------------------------------------------


Key = tuple[str, str]


def key_of(character_id: uuid.UUID | None, name: str) -> Key:
    """Who someone is, for working out ratings: a character, or a name only, the same
    however its case is written."""
    if character_id is not None:
        return ("c", str(character_id))
    return ("n", name.strip().casefold())


@dataclass(frozen=True)
class Who:
    """A participant as staff or a player named them."""

    party: bonds.Party
    false_sabbat: bool = False

    @property
    def key(self) -> Key:
        c = self.party.character
        return key_of(c.id if c is not None else None, self.party.name)


def participant(
    db: Session, troupe: Troupe, character_id: uuid.UUID | None, name: str
) -> bonds.Party:
    """A participant as staff named them: a vampire of the troupe's, or a name only."""
    name = name.strip()
    if (character_id is None) == (not name):
        raise unprocessable("Name each participant: a character, or a name only.")
    if character_id is None:
        if len(name) > LONGEST_NAME:
            raise unprocessable(f"A name is at most {LONGEST_NAME} characters.")
        return bonds.Party(None, name)
    character = db.get(Character, character_id)
    if character is None or not bonds.in_troupe(db, troupe, character):
        raise unprocessable("A participant isn't a character in this troupe.")
    if not bonds.is_vampire(character):
        raise unprocessable(f"{character.name} isn't a vampire: only vampires take the Vaulderie.")
    return bonds.Party(character, "")


def officiant_party(
    db: Session, troupe: Troupe, character_id: uuid.UUID | None, name: str
) -> bonds.Party | None:
    if character_id is None and not name.strip():
        return None
    return participant(db, troupe, character_id, name)


def checked(people: Sequence[Who]) -> list[Who]:
    if len(people) < 2:
        raise unprocessable("A Vaulderie needs at least two participants.")
    if len(people) > MOST_PARTICIPANTS:
        raise unprocessable(f"A Vaulderie names at most {MOST_PARTICIPANTS} participants.")
    keys = [p.key for p in people]
    if len(set(keys)) != len(keys):
        raise unprocessable("Name each participant once.")
    if all(p.false_sabbat for p in people):
        raise unprocessable("Someone has to give blood: not everyone can be a false Sabbat.")
    return list(people)


# --- ratings ----------------------------------------------------------------------------


def months_before(day: date, months: int) -> date:
    return bonds.add_months(day, -months)


def steady(nights: Sequence[date], on_day: date, gap: int) -> bool:
    """Vaulderies at most `gap` days apart through the three months up to `on_day`,
    from the start of them to the day itself."""
    start = months_before(on_day, 3)
    within = sorted(n for n in nights if start <= n <= on_day)
    if not within:
        return False
    points = [start, *within, on_day]
    return all((b - a).days <= gap for a, b in zip(points, points[1:], strict=False))


def rating_of(nights: Iterable[date], on_day: date) -> int:
    """The Vinculum rating, 0 to 5, from the nights two shared a Vaulderie, as of a day
    (p. 434): the first answer that holds, from 5 down."""
    shared = sorted({n for n in nights if n <= on_day})
    if not shared:
        return 0
    if steady(shared, on_day, FEW_DAYS_GAP):
        return 5
    if steady(shared, on_day, WEEKLY_GAP):
        return 4
    year = [n for n in shared if n > months_before(on_day, 12)]
    if len(year) > 10:
        return 3
    if len(year) > 1:
        return 2
    return 1


def tie_nights(rating: int, night: date) -> list[date]:
    """The history that gives `rating` on `night`, for a background tie: it thins with
    time as real Vaulderies would."""

    def back(every: int, count: int) -> list[date]:
        return [night - timedelta(days=every * i) for i in range(count)]

    if rating >= 5:
        return back(3, 32)  # every three days, past three months
    if rating == 4:
        return back(7, 14)  # weekly, past three months
    if rating == 3:
        return back(22, 11)  # eleven, but never weekly enough for 4
    if rating == 2:
        return back(7, 2)
    return [night]


@dataclass
class History:
    """A troupe's Vinculum history: the nights each shared with each other, as felt by
    the first toward the second, and who each is."""

    nights: dict[tuple[Key, Key], set[date]]
    names: dict[Key, bonds.Party]

    def rating(self, felt_by: Key, toward: Key, on_day: date | None = None) -> int:
        return rating_of(self.nights.get((felt_by, toward), ()), on_day or bonds.today())

    def ratings(self, on_day: date | None = None) -> dict[tuple[Key, Key], int]:
        day = on_day or bonds.today()
        found = {pair: rating_of(n, day) for pair, n in self.nights.items()}
        return {pair: r for pair, r in found.items() if r > 0}


def party_of(db: Session, character_id: uuid.UUID | None, name: str) -> bonds.Party:
    character = db.get(Character, character_id) if character_id else None
    return bonds.Party(character, "" if character else name)


def counted(db: Session, troupe: Troupe) -> list[Vaulderie]:
    return list(
        db.scalars(
            select(Vaulderie)
            .where(Vaulderie.troupe_id == troupe.id, Vaulderie.status == COUNTS)
            .order_by(Vaulderie.night, Vaulderie.created_at, Vaulderie.id)
        )
    )


def participants_of(db: Session, vaulderie: Vaulderie) -> list[VaulderieParticipant]:
    return list(
        db.scalars(
            select(VaulderieParticipant)
            .where(VaulderieParticipant.vaulderie_id == vaulderie.id)
            .order_by(VaulderieParticipant.created_at, VaulderieParticipant.id)
        )
    )


def ties_of(db: Session, troupe: Troupe) -> list[VinculumTie]:
    return list(
        db.scalars(
            select(VinculumTie)
            .where(VinculumTie.troupe_id == troupe.id)
            .order_by(VinculumTie.night, VinculumTie.created_at, VinculumTie.id)
        )
    )


def history(db: Session, troupe: Troupe) -> History:
    """Every rating's history in the troupe, from its Vaulderies recorded and its
    background ties."""
    nights: dict[tuple[Key, Key], set[date]] = defaultdict(set)
    names: dict[Key, bonds.Party] = {}
    for vaulderie in counted(db, troupe):
        people = participants_of(db, vaulderie)
        for p in people:
            k = key_of(p.character_id, p.name)
            names.setdefault(k, party_of(db, p.character_id, p.name))
        for one in people:
            for other in people:
                if one is other or other.false_sabbat:
                    # Nothing toward someone who gave no blood (the Errata's p. 434).
                    continue
                pair = (key_of(one.character_id, one.name), key_of(other.character_id, other.name))
                nights[pair].add(vaulderie.night)
    for tie in ties_of(db, troupe):
        a, b = key_of(tie.one_id, tie.one_name), key_of(tie.other_id, tie.other_name)
        names.setdefault(a, party_of(db, tie.one_id, tie.one_name))
        names.setdefault(b, party_of(db, tie.other_id, tie.other_name))
        made = tie_nights(tie.rating, tie.night)
        nights[(a, b)].update(made)
        nights[(b, a)].update(made)
    return History(dict(nights), names)


# --- what a rating does ---------------------------------------------------------------


def effects_of(rating: int, toward: str) -> list[str]:
    """What the rating means at a game, toward `toward` (p. 434)."""
    if rating >= 5:
        return [
            f"Working against {toward} costs 2 Willpower a scene; attacking them, 2 Willpower"
            " a round.",
            f"You can't kill {toward} or knowingly let them be killed ({PAGE}).",
        ]
    if rating == 4:
        return [
            f"Working against {toward} costs 1 Willpower a scene; attacking them, 1 Willpower"
            " a round.",
            f"Killing {toward} or knowingly letting them die costs 1 Willpower ({PAGE}).",
        ]
    if rating == 3:
        return [
            f"Attacking {toward} costs 1 Willpower, then you may for the rest of the scene."
            f" Not in Ignoblis or training fights ({PAGE}).",
        ]
    if rating == 2:
        return [f"Killing {toward} costs 1 Willpower ({PAGE})."]
    return [f"Kinship with {toward}: no rules effect ({PAGE})."]


@dataclass(frozen=True)
class Felt:
    """A Vinculum the character feels, in a troupe, toward someone."""

    troupe: Troupe
    toward: bonds.Party
    rating: int


def can_see(db: Session, user: User, troupe: Troupe, character: Character) -> bool:
    return on(troupe) and (bonds.can_manage(db, user, troupe) or bonds.plays(user, character))


def felt_by(db: Session, user: User, character: Character) -> list[Felt]:
    """The Vinculum ratings `character` feels, in each troupe that keeps its Vaulderies,
    as `user` may know of them: its player's own, and every one for the troupe's running
    staff. Strongest first."""
    me = key_of(character.id, "")
    troupe_ids = set(
        db.scalars(
            select(Vaulderie.troupe_id)
            .join(VaulderieParticipant, VaulderieParticipant.vaulderie_id == Vaulderie.id)
            .where(VaulderieParticipant.character_id == character.id, Vaulderie.status == COUNTS)
        )
    ) | set(
        db.scalars(
            select(VinculumTie.troupe_id).where(
                or_(VinculumTie.one_id == character.id, VinculumTie.other_id == character.id)
            )
        )
    )
    found: list[Felt] = []
    for troupe in db.scalars(select(Troupe).where(Troupe.id.in_(troupe_ids)).order_by(Troupe.name)):
        if not can_see(db, user, troupe, character):
            continue
        known = history(db, troupe)
        for (one, other), rating in known.ratings().items():
            if one == me:
                found.append(Felt(troupe, known.names[other], rating))
    found.sort(key=lambda f: (-f.rating, f.toward.shown.casefold()))
    return found


class VinculumLine(BaseModel):
    """A Vinculum the character feels, for the Play View's Sheet tab (#666)."""

    toward: str
    rating: int
    # What it costs at a game, in words.
    effects: list[str]


def play_lines(felt: Sequence[Felt]) -> list[VinculumLine]:
    """The ratings with a rules effect, 2 and up, strongest first: a 1 is kinship only."""
    return [
        VinculumLine(
            toward=f.toward.shown, rating=f.rating, effects=effects_of(f.rating, f.toward.shown)
        )
        for f in felt
        if f.rating >= 2
    ]


# --- the log ----------------------------------------------------------------------------


def log(db: Session, user: User | None, action: str, troupe: Troupe, **data: str) -> None:
    """Into the troupe's log, which its running staff keep."""
    audit.record(db, user, action, troupe_id=troupe.id, character_id=None, **data)


def listed(people: Sequence[bonds.Party]) -> str:
    names = [p.shown for p in people]
    if len(names) <= 2:
        return " and ".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def keep(db: Session, vaulderie: Vaulderie, people: Sequence[Who]) -> None:
    for p in people:
        c = p.party.character
        db.add(
            VaulderieParticipant(
                vaulderie_id=vaulderie.id,
                character_id=c.id if c is not None else None,
                name="" if c is not None else p.party.name,
                false_sabbat=p.false_sabbat,
            )
        )
    db.flush()


def new_vaulderie(
    db: Session,
    user: User,
    troupe: Troupe,
    night: date,
    people: Sequence[Who],
    officiant: bonds.Party | None,
    source: str,
    note: str,
    status: str,
) -> Vaulderie:
    if not on(troupe):
        raise conflict("This troupe doesn't keep the Vinculum.")
    if source not in SOURCES:
        raise unprocessable(f"Where it was told is one of {', '.join(SOURCES)}.")
    bonds.check_night(night)
    people = checked(people)
    if len(note) > 2000:
        raise unprocessable("A note is at most 2000 characters.")
    vaulderie = Vaulderie(
        troupe_id=troupe.id,
        night=night,
        officiant_id=officiant.character.id if officiant and officiant.character else None,
        officiant_name=officiant.name if officiant and not officiant.character else "",
        source=source,
        note=note.strip(),
        status=status,
        recorded_by=user.id,
    )
    db.add(vaulderie)
    db.flush()
    keep(db, vaulderie, people)
    return vaulderie


def record(
    db: Session,
    user: User,
    troupe: Troupe,
    night: date,
    people: Sequence[Who],
    officiant: bonds.Party | None,
    source: str,
    note: str,
) -> Vaulderie:
    """Staff record a Vaulderie: it counts at once, and lowers its participants' blood
    bonds a step (the Errata's p. 434)."""
    vaulderie = new_vaulderie(db, user, troupe, night, people, officiant, source, note, COUNTS)
    log(
        db,
        user,
        "bond.vaulderie",
        troupe,
        night=bonds.when(night),
        who=listed([p.party for p in people]),
        source=SOURCES[source],
    )
    lower_bonds(db, user, troupe, vaulderie)
    return vaulderie


def lower_bonds(db: Session, user: User | None, troupe: Troupe, vaulderie: Vaulderie) -> None:
    """Each participant's blood bonds that the troupe keeps, as thrall, go down a step:
    once a night, however many Vaulderies they took part in (the Errata's p. 434). A
    bond of one drink ends."""
    now = datetime.now(UTC)
    for p in participants_of(db, vaulderie):
        if p.character_id is not None:
            mine = BloodBond.thrall_id == p.character_id
        else:
            mine = and_(
                BloodBond.thrall_id.is_(None),
                func.lower(BloodBond.thrall_name) == p.name.strip().lower(),
            )
        for bond in db.scalars(
            select(BloodBond)
            .where(BloodBond.troupe_id == troupe.id, mine, BloodBond.status.in_(bonds.OPEN))
            .order_by(BloodBond.created_at, BloodBond.id)
        ):
            entries = bonds.entries_of(db, bond)
            if any(e.kind == "vaulderie" and e.night == vaulderie.night for e in entries):
                continue
            at = bonds.level_of(entries)
            if at <= 1:
                bonds.end(
                    db,
                    user,
                    bond,
                    "ended",
                    f"Lowered to nothing by the Vaulderie on {bonds.when(vaulderie.night)}"
                    f" (the Errata's {PAGE}).",
                )
                # The thrall took part: their player knows at once.
                bond.thrall_told_at = now
                db.flush()
                bonds.staff_log(
                    db, user, "bond.vaulderie_ended", bond, night=bonds.when(vaulderie.night)
                )
                continue
            db.add(
                BondEntry(
                    bond_id=bond.id,
                    kind="vaulderie",
                    night=vaulderie.night,
                    source="staff",
                    level=at - 1,
                    note=f"Lowered a step by the Vaulderie (the Errata's {PAGE}).",
                    recorded_by=user.id if user else None,
                    thrall_told_at=now,
                )
            )
            db.flush()
            bonds.staff_log(
                db,
                user,
                "bond.vaulderie_lowered",
                bond,
                night=bonds.when(vaulderie.night),
                level=bonds.LEVELS[at - 1],
            )


def remove(db: Session, user: User, troupe: Troupe, vaulderie: Vaulderie, reason: str) -> None:
    """Staff take a recorded Vaulderie out, with the reason: it no longer counts toward
    ratings. The blood bonds it lowered stay lowered."""
    reason = reason.strip()
    if not reason:
        raise unprocessable("Give a reason for taking the Vaulderie out.")
    if vaulderie.status != COUNTS:
        raise conflict("Only a Vaulderie that counts can be taken out.")
    vaulderie.status = "removed"
    vaulderie.reason = reason
    vaulderie.decided_by = user.id
    vaulderie.decided_at = datetime.now(UTC)
    db.flush()
    log(
        db, user, "bond.vaulderie_removed", troupe, night=bonds.when(vaulderie.night), reason=reason
    )


# --- players' reports ------------------------------------------------------------------


def report_troupes(db: Session, user: User, character: Character) -> list[Troupe]:
    """The troupes its player can report the character's Vaulderies to: those it is in
    whose players report or record bonds, and which keep the Vinculum."""
    return [t for t in bonds.report_troupes(db, user, character) if on(t)]


def report(
    db: Session,
    user: User,
    troupe: Troupe,
    character: Character,
    night: date,
    people: Sequence[Who],
    officiant: bonds.Party | None,
    source: str,
    note: str,
) -> Vaulderie:
    """A player reports a Vaulderie their character took part in. It waits for the
    troupe's running staff in either player mode, as it changes the other participants'
    ratings and bonds too."""
    if source not in PLAYER_SOURCES:
        raise unprocessable("A Vaulderie happened at a game or in a downtime.")
    if not any(
        p.party.character is not None and p.party.character.id == character.id for p in people
    ):
        raise unprocessable(f"{character.name} has to be one of the participants.")
    bonds.check_player_night(night, *(p.party.character for p in people))
    vaulderie = new_vaulderie(db, user, troupe, night, people, officiant, source, note, "pending")
    audit.record(
        db,
        user,
        "bond.vaulderie_reported",
        troupe_id=troupe.id,
        character_id=character.id,
        character_name=character.name,
        night=bonds.when(night),
        who=listed([p.party for p in people]),
    )
    return vaulderie


def decide(
    db: Session, user: User, troupe: Troupe, vaulderie: Vaulderie, approve: bool, reason: str
) -> None:
    """Staff approve a Vaulderie a player reported, which then counts as if they had
    recorded it, or decline it with the reason."""
    if vaulderie.status != "pending":
        raise conflict("That Vaulderie isn't waiting for a decision.")
    reason = reason.strip()
    if not approve and not reason:
        raise unprocessable("Give the player a reason for declining it.")
    vaulderie.decided_by = user.id
    vaulderie.decided_at = datetime.now(UTC)
    night = bonds.when(vaulderie.night)
    if approve:
        vaulderie.status = COUNTS
        db.flush()
        log(db, user, "bond.vaulderie_approved", troupe, night=night)
        lower_bonds(db, user, troupe, vaulderie)
        return
    vaulderie.status = "declined"
    vaulderie.reason = reason
    db.flush()
    log(db, user, "bond.vaulderie_declined", troupe, night=night, reason=reason)


def withdraw(db: Session, user: User, troupe: Troupe, vaulderie: Vaulderie) -> None:
    if vaulderie.status != "pending" or vaulderie.recorded_by != user.id:
        raise conflict("Only a Vaulderie you reported, still waiting, can be withdrawn.")
    vaulderie.status = "withdrawn"
    db.flush()
    log(db, user, "bond.vaulderie_withdrawn", troupe, night=bonds.when(vaulderie.night))


def pending(db: Session, troupe: Troupe) -> list[Vaulderie]:
    return list(
        db.scalars(
            select(Vaulderie)
            .where(Vaulderie.troupe_id == troupe.id, Vaulderie.status == "pending")
            .order_by(Vaulderie.created_at, Vaulderie.id)
        )
    )


def reported_by(db: Session, user: User, character: Character) -> list[Vaulderie]:
    """The Vaulderies the user reported for the character that wait, or were declined in
    the last month."""
    month_ago = datetime.now(UTC) - timedelta(days=30)
    return list(
        db.scalars(
            select(Vaulderie)
            .join(VaulderieParticipant, VaulderieParticipant.vaulderie_id == Vaulderie.id)
            .where(
                Vaulderie.recorded_by == user.id,
                VaulderieParticipant.character_id == character.id,
                or_(
                    Vaulderie.status == "pending",
                    and_(Vaulderie.status == "declined", Vaulderie.decided_at >= month_ago),
                ),
            )
            .order_by(Vaulderie.created_at.desc(), Vaulderie.id.desc())
        )
    )


# --- background ties --------------------------------------------------------------------


def add_tie(
    db: Session,
    user: User,
    troupe: Troupe,
    one: bonds.Party,
    other: bonds.Party,
    rating: int,
    night: date,
    reason: str,
) -> VinculumTie:
    """Staff enter a background tie: two who shared Vaulderies before Horatio, at a
    rating on a night (p. 435's example)."""
    if not on(troupe):
        raise conflict("This troupe doesn't keep the Vinculum.")
    reason = reason.strip()
    if not reason:
        raise unprocessable("Give a reason for the background tie.")
    if rating not in RATINGS:
        raise unprocessable("A Vinculum rating is 1 to 5.")
    bonds.check_night(night)
    a = key_of(one.character.id if one.character else None, one.name)
    b = key_of(other.character.id if other.character else None, other.name)
    if a == b:
        raise unprocessable("A tie is between two different characters.")
    tie = VinculumTie(
        troupe_id=troupe.id,
        one_id=one.character.id if one.character else None,
        one_name="" if one.character else one.name,
        other_id=other.character.id if other.character else None,
        other_name="" if other.character else other.name,
        rating=rating,
        night=night,
        reason=reason,
        recorded_by=user.id,
    )
    db.add(tie)
    db.flush()
    log(
        db,
        user,
        "bond.vinculum_tie",
        troupe,
        one=one.shown,
        other=other.shown,
        rating=str(rating),
        night=bonds.when(night),
        reason=reason,
    )
    return tie


def remove_tie(db: Session, user: User, troupe: Troupe, tie: VinculumTie, reason: str) -> None:
    reason = reason.strip()
    if not reason:
        raise unprocessable("Give a reason for taking the tie out.")
    one = party_of(db, tie.one_id, tie.one_name)
    other = party_of(db, tie.other_id, tie.other_name)
    db.delete(tie)
    db.flush()
    log(
        db,
        user,
        "bond.vinculum_tie_removed",
        troupe,
        one=one.shown,
        other=other.shown,
        reason=reason,
    )

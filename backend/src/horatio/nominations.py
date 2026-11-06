"""Player Nominations (issue #470): in each downtime, players write short notes
praising others' roleplaying. The troupe's running staff read them, with their
authors, take out any that aren't kind, star the best and lightly edit them; once
the cycle is past Due (horatio.downtimes.past_due) a storyteller publishes them to
the troupe's players, shuffled and without names. Starred ones rotate in a footer on
the troupe's pages for good.

An optional troupe setting, off by default (`Troupe.player_nominations`): while it is
off, nothing of them shows anywhere.

A nomination belongs to its writer's part in the cycle (`CycleParticipant`). Staff
see only those in submitted downtimes, and only those are published. Its writer can
change it while their downtime can be changed, until it is published. One written
after the cycle's nominations were published waits for staff to publish more.

Who reads the published ones: the troupe's players (anyone with an active character
at home there) and its staff. A character's player also reads those linked to it, on
its page. Only running staff ever see an author, a removed one or a reason.
"""

import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, exists, false, or_, select
from sqlalchemy.orm import Session

from horatio import audit, downtimes, notifications, suspensions
from horatio.models import (
    Character,
    CycleParticipant,
    DowntimeCycle,
    Nomination,
    Submission,
    Troupe,
    TroupeMembership,
    TroupeStaff,
    User,
)
from horatio.permissions import troupe_role
from horatio.sheets import conflict, unprocessable

# The most a nomination may say: a line or two usually, a paragraph at most.
TEXT_MOST = 1000


def on(troupe: Troupe) -> bool:
    return troupe.player_nominations


def require_on(troupe: Troupe) -> None:
    if not on(troupe):
        raise conflict("This troupe doesn't use Player Nominations.")


def reviewed_here(troupe: Troupe) -> bool:
    """Whether the troupe's cycles have nominations or remembrances (horatio.remembrances)
    to review and publish: they share the cycle's tab and its Publish."""
    return troupe.player_nominations or troupe.remembrances


def require_reviewed(troupe: Troupe) -> None:
    if not reviewed_here(troupe):
        raise conflict("This troupe doesn't use Player Nominations or Remembrances.")


def kinds(troupe: Troupe) -> ColumnElement[bool]:
    """The entries the troupe's settings show: nominations, memories, both or neither."""
    shown: list[ColumnElement[bool]] = []
    if troupe.player_nominations:
        shown.append(Nomination.remembrance_id.is_(None))
    if troupe.remembrances:
        shown.append(Nomination.remembrance_id.is_not(None))
    return or_(*shown) if shown else false()


# --- who a nomination is about ------------------------------------------------------------


@dataclass(frozen=True)
class About:
    """Someone a nomination can be linked to: a character in the troupe, or one of
    its staff."""

    name: str
    character_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


def about_choices(db: Session, troupe: Troupe) -> list[About]:
    """The troupe's characters, at home or visiting and not retired, then its staff,
    each by name."""
    characters = db.scalars(
        select(Character)
        .join(TroupeMembership, TroupeMembership.character_id == Character.id)
        .where(
            TroupeMembership.troupe_id == troupe.id,
            TroupeMembership.left_at.is_(None),
            Character.kind == "pc",
            Character.status == "active",
        )
        .order_by(Character.name, Character.id)
    )
    staff_ids = [
        troupe.lead_user_id,
        *db.scalars(select(TroupeStaff.user_id).where(TroupeStaff.troupe_id == troupe.id)),
    ]
    staff = db.scalars(select(User).where(User.id.in_(staff_ids)).order_by(User.display_name))
    return [About(name=c.name, character_id=c.id) for c in characters] + [
        About(name=u.display_name, user_id=u.id) for u in staff
    ]


def check_about(
    db: Session, troupe: Troupe, character_id: uuid.UUID | None, user_id: uuid.UUID | None
) -> None:
    if character_id is None and user_id is None:
        return
    if character_id is not None and user_id is not None:
        raise unprocessable("A nomination is about one character or one member of staff.")
    choices = about_choices(db, troupe)
    if not any(a.character_id == character_id and a.user_id == user_id for a in choices):
        raise unprocessable("Link it to one of the troupe's characters or staff.")


def about_name(db: Session, nomination: Nomination) -> str | None:
    if nomination.about_character_id is not None:
        return db.get_one(Character, nomination.about_character_id).name
    if nomination.about_user_id is not None:
        return db.get_one(User, nomination.about_user_id).display_name
    return None


def checked_text(text: str) -> str:
    text = text.strip()
    if not text:
        raise unprocessable("Write what you'd like to say.")
    if len(text) > TEXT_MOST:
        raise unprocessable(f"A nomination can be at most {TEXT_MOST:,} characters.")
    return text


# --- writing them ---------------------------------------------------------------------------


def mine(db: Session, participant: CycleParticipant) -> list[Nomination]:
    """What the character has written in this cycle, oldest first."""
    return list(
        db.scalars(
            select(Nomination)
            .where(Nomination.participant_id == participant.id, Nomination.remembrance_id.is_(None))
            .order_by(Nomination.created_at, Nomination.id)
        )
    )


def writable(
    db: Session, character: Character, cycle: DowntimeCycle, participant: CycleParticipant
) -> Troupe:
    """The troupe, if the character's player may write or change nominations now: as
    long as they may change the downtime itself."""
    troupe = db.get_one(Troupe, cycle.troupe_id)
    require_on(troupe)
    downtimes.ensure_can_submit(db, cycle, participant)
    suspensions.refuse_character(db, character)
    return troupe


def write(
    db: Session,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    text: str,
    about_character_id: uuid.UUID | None = None,
    about_user_id: uuid.UUID | None = None,
) -> Nomination:
    troupe = writable(db, character, cycle, participant)
    check_about(db, troupe, about_character_id, about_user_id)
    nomination = Nomination(
        cycle_id=cycle.id,
        participant_id=participant.id,
        text=checked_text(text),
        about_character_id=about_character_id,
        about_user_id=about_user_id,
    )
    db.add(nomination)
    db.flush()
    return nomination


def own(participant: CycleParticipant, nomination: Nomination | None) -> Nomination:
    """One of the participant's own nominations, not yet published."""
    if (
        nomination is None
        or nomination.participant_id != participant.id
        or nomination.remembrance_id is not None
    ):
        raise unprocessable("That isn't one of this character's nominations.")
    if nomination.published_at is not None:
        raise conflict("It's published now: ask a storyteller if it needs changing.")
    return nomination


def change(
    db: Session,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    nomination: Nomination | None,
    text: str,
    about_character_id: uuid.UUID | None = None,
    about_user_id: uuid.UUID | None = None,
) -> Nomination:
    troupe = writable(db, character, cycle, participant)
    found = own(participant, nomination)
    check_about(db, troupe, about_character_id, about_user_id)
    text = checked_text(text)
    if text != found.text:
        # The writer's own words again: staff's edit no longer stands.
        found.text = text
        found.edited_at = None
        found.edited_by = None
    found.about_character_id = about_character_id
    found.about_user_id = about_user_id
    db.flush()
    return found


def delete(
    db: Session,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    nomination: Nomination | None,
) -> None:
    writable(db, character, cycle, participant)
    db.delete(own(participant, nomination))
    db.flush()


# --- reviewing them ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Written:
    """A nomination as staff review it, with who wrote it."""

    nomination: Nomination
    character: Character
    player: User


def submitted(cycle: DowntimeCycle) -> tuple[ColumnElement[bool], ...]:
    """Those of the cycle's nominations whose downtime is submitted, by a character
    still taking part."""
    return (
        Nomination.cycle_id == cycle.id,
        CycleParticipant.removed_at.is_(None),
        exists().where(
            Submission.participant_id == Nomination.participant_id,
            Submission.status == "submitted",
        ),
    )


def review(db: Session, cycle: DowntimeCycle) -> list[Written]:
    """Every nomination and memory staff can see in the cycle, as the troupe's settings
    show them: those in submitted downtimes, in the order they were written."""
    troupe = db.get_one(Troupe, cycle.troupe_id)
    rows = db.execute(
        select(Nomination, Character, User)
        .join(CycleParticipant, Nomination.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .join(User, Character.player_id == User.id)
        .where(*submitted(cycle), kinds(troupe))
        .order_by(Nomination.created_at, Nomination.id)
    )
    return [Written(n, c, u) for n, c, u in rows]


def in_cycle(db: Session, cycle: DowntimeCycle, nomination_id: uuid.UUID) -> Nomination:
    """One of the nominations or memories staff can see in the cycle."""
    troupe = db.get_one(Troupe, cycle.troupe_id)
    found = db.scalar(
        select(Nomination)
        .join(CycleParticipant, Nomination.participant_id == CycleParticipant.id)
        .where(Nomination.id == nomination_id, *submitted(cycle), kinds(troupe))
    )
    if found is None:
        raise unprocessable("No such nomination in this cycle.")
    return found


def excerpt(text: str, most: int = 80) -> str:
    """The start of a nomination, for the troupe's log."""
    line = " ".join(text.split())
    return line if len(line) <= most else f"{line[: most - 1].rstrip()}…"


def logged(
    db: Session, staff: User, action: str, cycle: DowntimeCycle, n: Nomination, **data: Any
) -> None:
    if n.remembrance_id is not None:
        # A memory, named by whom it remembers.
        from horatio.models import Remembrance

        remembrance = db.get_one(Remembrance, n.remembrance_id)
        data["remembered"] = db.get_one(Character, remembrance.character_id).name
    audit.record(
        db,
        staff,
        f"{'remembrance' if n.remembrance_id else 'nomination'}.{action}",
        troupe_id=cycle.troupe_id,
        cycle_id=cycle.id,
        cycle=cycle.name,
        text=excerpt(n.text),
        **data,
    )


def remove(db: Session, staff: User, cycle: DowntimeCycle, n: Nomination, reason: str) -> None:
    """Take it out of what is published, now or later, with a reason for staff only."""
    if n.removed_at is not None:
        raise conflict("It's removed already.")
    n.removed_at = downtimes.now()
    n.removed_by = staff.id
    n.removed_reason = reason.strip()
    logged(db, staff, "removed", cycle, n, reason=n.removed_reason)


def restore(db: Session, staff: User, cycle: DowntimeCycle, n: Nomination) -> None:
    if n.removed_at is None:
        raise conflict("It isn't removed.")
    n.removed_at = None
    n.removed_by = None
    n.removed_reason = ""
    logged(db, staff, "restored", cycle, n)


def star(db: Session, staff: User, cycle: DowntimeCycle, n: Nomination, starred: bool) -> None:
    """Star it, for the footer of the troupe's pages once published, or unstar it."""
    if n.remembrance_id is not None:
        raise conflict("Only Player Nominations are starred, not remembrances.")
    if starred == (n.starred_at is not None):
        return
    n.starred_at = downtimes.now() if starred else None
    n.starred_by = staff.id if starred else None
    logged(db, staff, "starred" if starred else "unstarred", cycle, n)


def edit(db: Session, staff: User, cycle: DowntimeCycle, n: Nomination, text: str) -> None:
    """A light edit, such as a typo or a real name taken out, marked as staff's."""
    text = checked_text(text)
    if text == n.text:
        return
    before = n.text
    n.text = text
    n.edited_at = downtimes.now()
    n.edited_by = staff.id
    logged(db, staff, "edited", cycle, n, before=excerpt(before))


# --- publishing them ----------------------------------------------------------------------------


def waiting(db: Session, cycle: DowntimeCycle) -> list[Nomination]:
    """Those staff can see that are not yet published, nor removed."""
    return [
        w.nomination
        for w in review(db, cycle)
        if w.nomination.published_at is None and w.nomination.removed_at is None
    ]


def home_players(db: Session, troupe: Troupe) -> list[uuid.UUID]:
    """The troupe's players: those with an active character at home there."""
    return list(
        db.scalars(
            select(Character.player_id)
            .where(
                Character.home_troupe_id == troupe.id,
                Character.kind == "pc",
                Character.status == "active",
            )
            .distinct()
        )
    )


def publish(db: Session, staff: User, cycle: DowntimeCycle) -> int:
    """Publish the cycle's nominations and memories (horatio.remembrances) not yet
    published, once it is past Due: the first time, telling the troupe's players;
    after, adding those written since. Each takes its place in its month's shuffled
    order now, and keeps it. Everyone named in a nomination is told, and so is each
    remembered character's player. Returns how many were published."""
    from horatio import remembrances

    troupe = db.get_one(Troupe, cycle.troupe_id)
    require_reviewed(troupe)
    if not downtimes.past_due(cycle):
        raise conflict("They can be published once the cycle is past Due.")
    seen = review(db, cycle)
    found = [
        w.nomination
        for w in seen
        if w.nomination.published_at is None and w.nomination.removed_at is None
    ]
    if not found:
        raise conflict("There is nothing waiting to be published.")
    # What was published before: so each kind's news goes out once.
    before = [w.nomination for w in seen if w.nomination.published_at is not None]
    nominated_before = any(n.remembrance_id is None for n in before)
    remembered_before = {n.remembrance_id for n in before if n.remembrance_id is not None}
    at = downtimes.now()
    first = cycle.nominations_published_at is None
    if first:
        cycle.nominations_published_at = at
    for n in found:
        n.published_at = at
        n.shuffle_key = random.random()
    db.flush()
    audit.record(
        db,
        staff,
        "nomination.published" if first else "nomination.published_more",
        troupe_id=troupe.id,
        cycle_id=cycle.id,
        cycle=cycle.name,
        count=len(found),
    )
    page = f"/troupes/{troupe.id}/nominations"
    nominated = [n for n in found if n.remembrance_id is None]
    if nominated and not nominated_before:
        notifications.notify(
            db,
            home_players(db, troupe),
            "nominations.published",
            f"{cycle.name}'s Player Nominations are up",
            page,
            troupe_id=troupe.id,
        )
    tell_those_named(db, troupe, cycle, nominated, page)
    remembrances.tell(db, troupe, cycle, found, remembered_before)
    return len(found)


def tell_those_named(
    db: Session, troupe: Troupe, cycle: DowntimeCycle, found: Sequence[Nomination], page: str
) -> None:
    """A line for the player of each character named in those just published, and
    for each member of staff named."""
    characters = {n.about_character_id for n in found} - {None}
    for character in db.scalars(
        select(Character).where(Character.id.in_(characters)).order_by(Character.name)
    ):
        notifications.notify(
            db,
            [character.player_id],
            "nominations.about",
            f"{character.name} is named in {cycle.name}'s Player Nominations",
            f"/characters/{character.id}",
            troupe_id=troupe.id,
            character_id=character.id,
        )
    users = list({n.about_user_id for n in found} - {None})
    if users:
        notifications.notify(
            db,
            [u for u in users if u is not None],
            "nominations.about",
            f"You're named in {cycle.name}'s Player Nominations",
            page,
            troupe_id=troupe.id,
        )


# --- reading them -------------------------------------------------------------------------------


def is_reader(db: Session, user: User, troupe: Troupe) -> bool:
    """One of the troupe's readers: its staff and its players, those with an active
    character at home there; and the custodian."""
    if user.is_custodian:
        return True
    if troupe.archived_at is not None:
        return False
    if troupe_role(db, user, troupe) is not None:
        return True
    return bool(
        db.scalar(
            select(
                exists().where(
                    Character.player_id == user.id,
                    Character.home_troupe_id == troupe.id,
                    Character.kind == "pc",
                    Character.status == "active",
                )
            )
        )
    )


def can_read(db: Session, user: User, troupe: Troupe) -> bool:
    """Whether the user reads the troupe's published months: one of its readers, while
    it uses Player Nominations or Remembrances. Never while both are off."""
    return reviewed_here(troupe) and is_reader(db, user, troupe)


def shown() -> tuple[ColumnElement[bool], ...]:
    """Published, and not removed since."""
    return (Nomination.published_at.is_not(None), Nomination.removed_at.is_(None))


@dataclass(frozen=True)
class Month:
    """A month published: its nominations, and the characters remembered in it with
    their memories, each in their shuffled order."""

    cycle: DowntimeCycle
    nominations: list[Nomination]
    remembered: list[tuple[Character, list[Nomination]]]


def published(db: Session, troupe: Troupe) -> list[Month]:
    """Each month published, newest first, with what the troupe's settings show of it:
    its nominations, and its remembrances by the character's name."""
    from horatio.models import Remembrance

    cycles = list(
        db.scalars(
            select(DowntimeCycle)
            .where(
                DowntimeCycle.troupe_id == troupe.id,
                DowntimeCycle.nominations_published_at.is_not(None),
            )
            .order_by(DowntimeCycle.nominations_published_at.desc())
        )
    )
    by_cycle: dict[uuid.UUID, list[Nomination]] = {c.id: [] for c in cycles}
    memories: dict[uuid.UUID, dict[uuid.UUID, list[Nomination]]] = {c.id: {} for c in cycles}
    for n in db.scalars(
        select(Nomination)
        .where(Nomination.cycle_id.in_(by_cycle), kinds(troupe), *shown())
        .order_by(Nomination.shuffle_key, Nomination.id)
    ):
        if n.remembrance_id is None:
            by_cycle[n.cycle_id].append(n)
        else:
            memories[n.cycle_id].setdefault(n.remembrance_id, []).append(n)
    remembered = {
        r.id: db.get_one(Character, r.character_id)
        for r in db.scalars(
            select(Remembrance).where(Remembrance.id.in_([i for m in memories.values() for i in m]))
        )
    }
    months: list[Month] = []
    for c in cycles:
        found = sorted(
            ((remembered[i], m) for i, m in memories[c.id].items()),
            key=lambda pair: (pair[0].name, str(pair[0].id)),
        )
        if by_cycle[c.id] or found:
            months.append(Month(c, by_cycle[c.id], found))
    return months


def about_character(db: Session, character: Character) -> list[tuple[DowntimeCycle, Nomination]]:
    """The published nominations linked to the character, newest month first, from
    troupes that use Player Nominations."""
    rows = db.execute(
        select(DowntimeCycle, Nomination)
        .join(Nomination, Nomination.cycle_id == DowntimeCycle.id)
        .join(Troupe, DowntimeCycle.troupe_id == Troupe.id)
        .where(
            Nomination.about_character_id == character.id,
            Nomination.remembrance_id.is_(None),
            Troupe.player_nominations,
            *shown(),
        )
        .order_by(DowntimeCycle.nominations_published_at.desc(), Nomination.shuffle_key)
    )
    return [(c, n) for c, n in rows]


def starred(db: Session, troupe: Troupe) -> list[tuple[DowntimeCycle, Nomination]]:
    """Every starred nomination of the troupe's, from every month, for the footer."""
    rows = db.execute(
        select(DowntimeCycle, Nomination)
        .join(Nomination, Nomination.cycle_id == DowntimeCycle.id)
        .where(
            DowntimeCycle.troupe_id == troupe.id,
            Nomination.starred_at.is_not(None),
            Nomination.remembrance_id.is_(None),
            *shown(),
        )
        .order_by(DowntimeCycle.nominations_published_at.desc(), Nomination.shuffle_key)
    )
    return [(c, n) for c, n in rows]

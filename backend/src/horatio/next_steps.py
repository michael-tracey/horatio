"""Next for this character (issue #1051): what a player's character waits on, from
every tab it is kept on, in one place: what needs the player, what waits on staff
(and since when), and what is coming up. Each step links to the page of the app
where it is done. Staff have Waiting on you (horatio.api.waiting); this is the
player's.

Each kind of step has its own small function, and reads what its own module keeps
(approvals, backstories, downtimes, boon reports, drinks to confirm, quest
requests, games, free changes) rather than working it out again. The Characters
page asks for every character at once, and every change in the app asks again, so
each function makes a query or two for all of them together, never one per
character (`Asked`).

Only an active PC has steps: an NPC needs no approval and takes no downtimes, and a
retired character takes no new actions.
"""

import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from horatio import backstories, bonds, downtimes, free_changes
from horatio.models import (
    Approval,
    Backstory,
    BondReport,
    Boon,
    BoonEvent,
    Character,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    QuestRequest,
    ScheduledGame,
    Submission,
    Troupe,
)

# Theirs to do; waiting on staff (or the Harpy); or coming up.
Who = Literal["player", "staff", "coming"]


@dataclass(frozen=True)
class Step:
    kind: str
    who: Who
    label: str
    # The page of the app where it is done.
    link: str
    # Since when it has waited on staff; for new results, when the newest came.
    since: datetime | None = None
    # When it is due, starts or ends.
    at: datetime | None = None


@dataclass(frozen=True)
class Pending:
    """An approval waiting on a troupe's staff."""

    character_id: uuid.UUID
    kind: str
    troupe_id: uuid.UUID
    created_at: datetime


@dataclass(frozen=True)
class Asked:
    """The characters asked about, and what every kind of step shares."""

    db: Session
    characters: list[Character]
    # The troupes each is at home in, built for, or asking to make home.
    troupes: dict[uuid.UUID, Troupe]
    # Its approvals waiting on staff, oldest first.
    pending: list[Pending]
    at: datetime
    # The troupe each asks to make its home, while its staff decide.
    asking: dict[uuid.UUID, uuid.UUID]

    @property
    def ids(self) -> list[uuid.UUID]:
        return [c.id for c in self.characters]

    def troupe(self, troupe_id: uuid.UUID | None) -> Troupe | None:
        return self.troupes.get(troupe_id) if troupe_id else None

    def reading(self, character: Character) -> Troupe | None:
        """The troupe reading its backstory (horatio.backstories.review_troupe): the
        one it asks to make home, or its home troupe."""
        return self.troupe(self.asking.get(character.id) or character.home_troupe_id)


Found = list[tuple[uuid.UUID, Step]]
Gather = Callable[[Asked], Found]


def now() -> datetime:
    return datetime.now(UTC)


def counted(n: int, one: str, many: str) -> str:
    return one if n == 1 else f"{n} {many}"


def link(character_id: uuid.UUID, tab: str = "") -> str:
    return f"/characters/{character_id}" + (f"/{tab}" if tab else "")


def creation(asked: Asked) -> Found:
    """A character not yet finished: its player finishes it in the wizard."""
    return [
        (
            c.id,
            Step("finish_creation", "player", "Finish character creation", link(c.id, "create")),
        )
        for c in asked.characters
        if c.creation_completed_at is None
    ]


def home_troupe(asked: Asked) -> Found:
    """A finished character with no home troupe, not asking one: its player asks one,
    the troupe it is built for if any, from its Troupes tab."""
    found: Found = []
    for c in asked.characters:
        if c.creation_completed_at is None or c.home_troupe_id or c.id in asked.asking:
            continue
        built_for = asked.troupe(c.building_troupe_id)
        if built_for is not None and built_for.archived_at is None:
            label = f"Ask {built_for.name} to be its home"
            to = link(c.id, f"troupes?home={built_for.id}")
        else:
            label, to = "Ask a troupe to be its home", link(c.id, "troupes")
        found.append((c.id, Step("ask_home", "player", label, to)))
    return found


# What each kind of approval waits for, in the player's words, for one and for
# several. `sheet_change` is kept only for history, so it is never pending.
APPROVAL_WORDS: dict[str, tuple[str, str]] = {
    "discipline": (
        "Discipline purchase awaiting approval",
        "discipline purchases awaiting approval",
    ),
    "review": ("Change held for review", "changes held for review"),
    "exception": ("Exception awaiting an answer", "exceptions awaiting an answer"),
    "merit_flaw": (
        "Merit or flaw change awaiting approval",
        "merit or flaw changes awaiting approval",
    ),
    "diablerie": ("Diablerie awaiting approval", "diableries awaiting approval"),
    "bond_drink": ("Reported drink awaiting approval", "reported drinks awaiting approval"),
}


def approvals(asked: Asked) -> Found:
    """Its approvals waiting on its home troupe's staff, one step for each kind, since
    the oldest. Asking to make a troupe its home links to its Troupes tab, where it
    can be withdrawn; the rest show on its sheet."""
    found: Found = []
    names = {t.id: t.name for t in asked.troupes.values()}
    grouped: dict[tuple[uuid.UUID, str], list[Pending]] = defaultdict(list)
    for p in asked.pending:
        grouped[(p.character_id, p.kind)].append(p)
    for (character_id, kind), waiting in grouped.items():
        first = waiting[0]
        if kind == "home_troupe_change":
            troupe = names.get(first.troupe_id, "the troupe")
            step = Step(
                "approval_home",
                "staff",
                f"Asked {troupe} to be its home",
                link(character_id, "troupes"),
                since=first.created_at,
            )
        elif kind in APPROVAL_WORDS:
            one, many = APPROVAL_WORDS[kind]
            step = Step(
                f"approval_{kind}",
                "staff",
                counted(len(waiting), one, many),
                link(character_id),
                since=first.created_at,
            )
        else:
            continue
        found.append((character_id, step))
    return found


def backstory(asked: Asked) -> Found:
    """Where its backstory stands with the troupe reading it (horatio.backstories):
    sent back for its player to revise; a draft not yet submitted; written and waiting
    for the storytellers since it changed, as their Backstories to read counts it
    (`backstories.waiting`); or not yet written while the troupe it asks, or is built
    for, needs it to accept the character."""
    found: Found = []
    kept = {
        b.character_id: b
        for b in asked.db.scalars(select(Backstory).where(Backstory.character_id.in_(asked.ids)))
    }
    for c in asked.characters:
        b = kept.get(c.id)
        troupe = asked.reading(c)
        written = b is not None and b.text.strip() != ""
        state = backstories.state_for(b, troupe)
        to = link(c.id, "backstory")
        if troupe is not None and state == "returned":
            label = f"Revise the backstory {troupe.name} sent back"
            found.append((c.id, Step("backstory_returned", "player", label, to)))
        elif backstories.has_draft(b):
            found.append(
                (c.id, Step("backstory_draft", "player", "Submit the backstory draft", to))
            )
        if (
            troupe is not None
            and written
            and state != "returned"
            and not backstories.approved_for(b, troupe)
        ):
            label = f"Backstory with {troupe.name}'s storytellers"
            since = b.changed_at if b is not None else None
            found.append((c.id, Step("backstory_reading", "staff", label, to, since=since)))
        # With no home troupe yet, the troupe it asks, or else the one it is built for. A
        # draft is on its way, and already said.
        needing = None if c.home_troupe_id else troupe or asked.troupe(c.building_troupe_id)
        if (
            needing is not None
            and needing.backstory_required
            and not written
            and not backstories.has_draft(b)
        ):
            label = f"Write the backstory {needing.name} needs"
            found.append((c.id, Step("backstory_write", "player", label, to)))
    return found


def downtime(asked: Asked) -> Found:
    """Its downtime to submit and the results delivered (horatio.downtimes.waiting);
    and a downtime submitted whose results have yet to come, waiting on staff since it
    was submitted. The results step names when the newest came, and the page judges
    whether its player has opened them, as the Results tab counts them."""
    found: Found = []
    waiting = downtimes.waiting(asked.db, asked.ids)
    for c in asked.characters:
        w = waiting.get(c.id)
        if w is None:
            continue
        if w.due is not None:
            step = Step("downtime_due", "player", "Downtime due", link(c.id, "downtime"), at=w.due)
            found.append((c.id, step))
        if w.delivered:
            step = Step(
                "results", "player", "New results", link(c.id, "results"), since=w.delivered[0]
            )
            found.append((c.id, step))
    delivered = exists().where(
        Delivery.submission_id == Submission.id,
        Delivery.channel == "horatio",
        Delivery.status == "sent",
        Delivery.test_mode.is_(False),
    )
    for character_id, cycle, submitted_at in asked.db.execute(
        select(CycleParticipant.character_id, DowntimeCycle.name, Submission.submitted_at)
        .join(DowntimeCycle, CycleParticipant.cycle_id == DowntimeCycle.id)
        .join(Submission, Submission.participant_id == CycleParticipant.id)
        .where(
            CycleParticipant.character_id.in_(asked.ids),
            CycleParticipant.removed_at.is_(None),
            DowntimeCycle.status.in_(("open", "closed")),
            Submission.status == "submitted",
            ~delivered,
        )
        .order_by(Submission.submitted_at, Submission.id)
    ):
        step = Step(
            "downtime_results",
            "staff",
            f"Results of {cycle}",
            link(character_id, "downtime"),
            since=submitted_at,
        )
        found.append((character_id, step))
    return found


def boon_reports(asked: Asked) -> Found:
    """Boons reported as the character in the Play View that wait for review, as its
    Boons tab lists them (horatio.api.boons.reports_of), while the troupe keeps its
    ledger."""
    by: dict[uuid.UUID, list[datetime]] = defaultdict(list)
    for character_id, _, made_at in asked.db.execute(
        select(BoonEvent.as_character_id, Boon.id, Boon.created_at)
        .join(Boon, BoonEvent.boon_id == Boon.id)
        .join(Troupe, Boon.troupe_id == Troupe.id)
        .where(
            BoonEvent.as_character_id.in_(asked.ids),
            BoonEvent.kind == "submitted",
            Boon.state == "pending",
            Troupe.boons.is_(True),
        )
        .distinct()
        .order_by(Boon.created_at, Boon.id)
    ):
        if character_id is not None:
            by[character_id].append(made_at)
    return [
        (
            character_id,
            Step(
                "boon_reports",
                "staff",
                counted(
                    len(made), "Boon report awaiting approval", "boon reports awaiting approval"
                ),
                f"/play/characters/{character_id}?tab=boons",
                since=made[0],
            ),
        )
        for character_id, made in by.items()
    ]


def drinks_to_confirm(asked: Asked) -> Found:
    """Drinks a regnant's player recorded with the character as thrall, waiting for its
    player to confirm or decline them, where the troupe has players record them
    (horatio.bonds). They show with its bonds, on its sheet."""
    by: dict[uuid.UUID, int] = defaultdict(int)
    for (character_id,) in asked.db.execute(
        select(BondReport.thrall_id)
        .join(Troupe, BondReport.troupe_id == Troupe.id)
        .where(
            BondReport.thrall_id.in_(asked.ids),
            BondReport.status == "pending",
            BondReport.waiting_on == "thrall",
            Troupe.blood_bonds == "players_manage",
        )
    ):
        if character_id is not None:
            by[character_id] += 1
    return [
        (
            character_id,
            Step(
                "drinks_to_confirm",
                "player",
                counted(n, "A drink to confirm or decline", "drinks to confirm or decline"),
                link(character_id),
            ),
        )
        for character_id, n in by.items()
    ]


def quest_requests(asked: Asked) -> Found:
    """Its quest requests not yet answered, while its troupe runs quests."""
    by: dict[uuid.UUID, list[datetime]] = defaultdict(list)
    for character_id, made_at in asked.db.execute(
        select(QuestRequest.character_id, QuestRequest.created_at)
        .join(Troupe, QuestRequest.troupe_id == Troupe.id)
        .where(
            QuestRequest.character_id.in_(asked.ids),
            QuestRequest.status.in_(("new", "working")),
            Troupe.quests_enabled.is_(True),
        )
        .order_by(QuestRequest.created_at, QuestRequest.id)
    ):
        by[character_id].append(made_at)
    return [
        (
            character_id,
            Step(
                "quest_requests",
                "staff",
                counted(
                    len(made),
                    "Quest request awaiting an answer",
                    "quest requests awaiting an answer",
                ),
                link(character_id, "quests"),
                since=made[0],
            ),
        )
        for character_id, made in by.items()
    ]


def next_game(asked: Asked) -> Found:
    """Its home troupe's next game, not yet over, on the troupe's About page."""
    homes = {c.home_troupe_id for c in asked.characters if c.home_troupe_id}
    if not homes:
        return []
    starts = {
        troupe_id: starts_at
        for troupe_id, starts_at in asked.db.execute(
            select(ScheduledGame.troupe_id, func.min(ScheduledGame.starts_at))
            .where(ScheduledGame.troupe_id.in_(homes), ScheduledGame.ends_at > asked.at)
            .group_by(ScheduledGame.troupe_id)
        )
    }
    return [
        (c.id, Step("next_game", "coming", "Next game", f"/troupes/{home}", at=starts[home]))
        for c in asked.characters
        if (home := c.home_troupe_id) and home in starts
    ]


def free_change_window(asked: Asked) -> Found:
    """Its free changes while they are open (horatio.free_changes): until a day, or
    for a number of games more."""
    found: Found = []
    for character_id, window in free_changes.windows(asked.db, asked.characters, asked.at).items():
        if window.kind == "date":
            step = Step(
                "free_changes", "coming", "Free changes", link(character_id), at=window.ends_at
            )
        else:
            n = window.games_left or 0
            label = f"Free changes for {n} more {'game' if n == 1 else 'games'}"
            step = Step("free_changes", "coming", label, link(character_id))
        found.append((character_id, step))
    return found


# Each kind of step, in the order they show within each of player, staff and coming.
STEPS: list[Gather] = [
    creation,
    backstory,
    home_troupe,
    downtime,
    drinks_to_confirm,
    approvals,
    boon_reports,
    quest_requests,
    next_game,
    free_change_window,
]

ORDER: dict[Who, int] = {"player": 0, "staff": 1, "coming": 2}


def next_steps(
    db: Session, characters: Sequence[Character], at: datetime | None = None
) -> dict[uuid.UUID, list[Step]]:
    """For each character, what is next for it: the player's steps first, then those
    waiting on staff, then what is coming up. A character with none is left out."""
    found = [c for c in characters if c.kind == "pc" and c.status == "active"]
    if not found:
        return {}
    pending = [
        Pending(character_id, kind, troupe_id, created_at)
        for character_id, kind, troupe_id, created_at in db.execute(
            select(Approval.character_id, Approval.kind, Approval.troupe_id, Approval.created_at)
            .where(
                Approval.character_id.in_([c.id for c in found]),
                Approval.status == "pending",
                ~bonds.hidden_approvals(),
            )
            .order_by(Approval.created_at, Approval.id)
        )
    ]
    asking = {p.character_id: p.troupe_id for p in pending if p.kind == "home_troupe_change"}
    troupe_ids = {
        t for c in found for t in (c.home_troupe_id, c.building_troupe_id, asking.get(c.id)) if t
    }
    troupes = (
        {t.id: t for t in db.scalars(select(Troupe).where(Troupe.id.in_(troupe_ids)))}
        if troupe_ids
        else {}
    )
    asked = Asked(db, found, troupes, pending, at or now(), asking)
    steps: dict[uuid.UUID, list[Step]] = defaultdict(list)
    for gather in STEPS:
        for character_id, step in gather(asked):
            steps[character_id].append(step)
    return {
        character_id: sorted(listed, key=lambda s: ORDER[s.who])
        for character_id, listed in steps.items()
    }

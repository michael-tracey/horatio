"""Feeding in downtimes: what each character must spend to come to the next
game at full Blood, how they meet it, and the storytellers' answer.

Each cycle carries a feeding difficulty for each clan, copied from the last
cycle (horatio.downtimes.create_cycle); storytellers and assistant
storytellers change a clan's number with a reason. A character's number is its
clan's, changed by its traits (horatio.rules.feeding) and by any adjustment
staff make for it this cycle.

The Feeding section of the form takes feeding actions, counted against the
character's general actions, and shares out its Herd: for its own feeding,
given to other characters taking part, saved for the game, or something else,
never more dots than it has. The tally is advisory; nothing is blocked.
Storytellers answer full Blood, half Blood, or something else; a full or half
answer goes to the player with how it was worked out. A half answer, once
delivered, starts the character's next Play View game at half Blood
(horatio.play).

A troupe may leave feeding out altogether (Troupe.feeding "off"): no Feeding section
on the form, no Feeding tab, nothing in the results or at the next game. Whatever was
recorded stays, and comes back when feeding is switched on again. With the optional
rule Blood Resonance on, the player names the humor they hunt for and the answer
gives the Resonance and any Dyscrasia (horatio.resonance).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, resonance
from horatio.models import (
    Character,
    CycleParticipant,
    DowntimeCycle,
    FeedingAdjustment,
    FeedingTerritory,
    PlayEvent,
    PlayGame,
    RuleSet,
    Submission,
    Troupe,
    User,
)
from horatio.rules import feeding as rules
from horatio.rules.splats import SPLATS
from horatio.rules.store import read_troupe_rules
from horatio.sheets import conflict, unprocessable

RESULTS = ("full", "half", "other")
RESULT_WORDS = {"full": "Full Blood next game.", "half": "Half Blood next game."}
SETTINGS = ("off", "book")
SETTING_TEXT = {
    "off": "Not tracked: no feeding in downtimes, results or at the next game",
    "book": "Tracked in downtimes, as the book has it",
}


# --- the troupe's setting ---------------------------------------------------------------


def tracked(troupe: Troupe | None) -> bool:
    """Whether Horatio handles feeding for the troupe's characters. A character with
    no home troupe goes by the book."""
    return troupe is None or troupe.feeding != "off"


def resonance_on(troupe: Troupe | None) -> bool:
    """Blood Resonance is played: switched on, with feeding tracked."""
    return troupe is not None and tracked(troupe) and troupe.feeding_resonance


def not_tracked() -> Exception:
    return conflict("This troupe doesn't track feeding. Its storytellers can switch it on.")


@dataclass(frozen=True)
class Shown:
    """What of feeding a troupe plays, and so what Horatio shows of it: feeding at all,
    and each optional rule."""

    tracked: bool = True
    resonance: bool = False
    territories: bool = False
    rack: bool = False


# Everything shown, whatever was recorded.
EVERYTHING = Shown(True, True, True, True)


def shown(troupe: Troupe | None) -> Shown:
    if not tracked(troupe):
        return Shown(tracked=False)
    if troupe is None:
        return Shown()
    return Shown(
        tracked=True,
        resonance=troupe.feeding_resonance,
        territories=troupe.feeding_territories,
        rack=troupe.feeding_resonance and troupe.feeding_rack,
    )


@dataclass(frozen=True)
class Setting:
    feeding: str
    resonance: bool = False
    territories: bool = False
    rack: bool = False


def set_setting(db: Session, staff: User, troupe: Troupe, setting: Setting) -> None:
    """Change how far Horatio handles the troupe's feeding. Nothing recorded is lost:
    switching feeding, or a rule, off only hides it."""
    if setting.feeding not in SETTINGS:
        raise unprocessable(f"Feeding is one of {', '.join(SETTINGS)}.")
    if setting.rack and not setting.resonance:
        raise unprocessable(
            "The Rack builds on Blood Resonance, as each vessel carries one: switch that on too."
        )
    now = Setting(
        troupe.feeding, troupe.feeding_resonance, troupe.feeding_territories, troupe.feeding_rack
    )
    if now == setting:
        return
    troupe.feeding = setting.feeding
    troupe.feeding_resonance = setting.resonance
    troupe.feeding_territories = setting.territories
    troupe.feeding_rack = setting.rack
    db.flush()
    rules_on = [
        name
        for name, on in (
            ("Blood Resonance", setting.resonance),
            ("feeding territories", setting.territories),
            ("the Rack", setting.rack),
        )
        if on
    ]
    audit.record(
        db,
        staff,
        "house.feeding",
        troupe_id=troupe.id,
        feeding="not tracked" if setting.feeding == "off" else "tracked as the book has it",
        rules=", ".join(rules_on) or "none",
    )


# --- the difficulty by clan -------------------------------------------------------------


def troupe_clans(db: Session, troupe: Troupe) -> list[str]:
    """Every clan in the troupe's rules, bloodlines counted with their clan."""
    clans: set[str] = set()
    for splat in db.scalars(select(RuleSet.splat)):
        traits = read_troupe_rules(db, splat, troupe.id).rule_set.traits
        clans |= {rules.clan_family(name) for category, name in traits if category == "clan"}
    return sorted(clans)


def clan_difficulty(cycle: DowntimeCycle, clan: str) -> tuple[int, str]:
    """The clan's feeding actions this cycle, and the storytellers' reason."""
    found = cycle.feeding_difficulty.get(clan)
    if found is None:
        return rules.DEFAULT_DIFFICULTY, ""
    return int(found["amount"]), str(found.get("reason", ""))


def set_difficulty(
    db: Session,
    staff: User,
    cycle: DowntimeCycle,
    troupe: Troupe,
    clan: str,
    amount: int,
    reason: str,
) -> None:
    if cycle.status == "complete":
        raise conflict("This cycle is complete.")
    if clan not in troupe_clans(db, troupe):
        raise unprocessable(f"No clan {clan!r} in this troupe's rules.")
    if amount < 0:
        raise unprocessable("A clan cannot need fewer than 0 feeding actions.")
    reason = reason.strip()
    cycle.feeding_difficulty = {
        **cycle.feeding_difficulty,
        clan: {"amount": amount, "reason": reason},
    }
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.feeding_difficulty_set",
        troupe_id=troupe.id,
        cycle_id=cycle.id,
        clan=clan,
        amount=amount,
        reason=reason or "no reason given",
    )


# --- a character's number ---------------------------------------------------------------


def participant_basis(
    db: Session, participant: CycleParticipant, character: Character, cycle: DowntimeCycle
) -> dict[str, Any]:
    """What the sheet said about feeding when the character joined the cycle, or
    for a participant from before feeding was tracked, what it says now. A
    character of a splat that does not feed has nothing to say."""
    if not SPLATS[character.splat].panels.feed:
        return {"clan": None, "modifiers": [], "herd": 0}
    if participant.feeding is not None:
        return participant.feeding
    from horatio.downtimes import allowance_sheet

    troupe_rules = read_troupe_rules(db, character.splat, cycle.troupe_id)
    return rules.basis(troupe_rules, allowance_sheet(db, character))


def adjustments(db: Session, participant: CycleParticipant) -> list[FeedingAdjustment]:
    return list(
        db.scalars(
            select(FeedingAdjustment)
            .where(FeedingAdjustment.participant_id == participant.id)
            .order_by(FeedingAdjustment.id)
        )
    )


def adjust(
    db: Session,
    staff: User,
    participant: CycleParticipant,
    troupe: Troupe,
    delta: int,
    reason: str,
) -> None:
    if delta == 0:
        raise unprocessable("An adjustment changes the number by at least 1.")
    db.add(
        FeedingAdjustment(
            participant_id=participant.id, delta=delta, reason=reason.strip(), adjusted_by=staff.id
        )
    )
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.feeding_adjusted",
        troupe_id=troupe.id,
        character_id=participant.character_id,
        cycle_id=participant.cycle_id,
        delta=delta,
        reason=reason.strip(),
    )


def need(
    db: Session, cycle: DowntimeCycle, participant: CycleParticipant, basis: dict[str, Any]
) -> rules.Need | None:
    """The character's feeding number and why; None for a character with no clan,
    which does not feed."""
    if basis.get("clan") is None:
        return None
    amount, reason = clan_difficulty(cycle, basis["clan"])
    return rules.need(
        amount, reason, basis, [(a.delta, a.reason) for a in adjustments(db, participant)]
    )


# --- the player's answer ----------------------------------------------------------------


@dataclass
class Gift:
    character_id: uuid.UUID
    amount: int


@dataclass
class Patrol:
    territory_id: uuid.UUID
    actions: int


@dataclass
class FeedingAnswer:
    """The Feeding section of one submission, as kept in `Submission.feeding`."""

    actions: int = 0
    where: str = ""
    herd_own: int = 0
    gifts: list[Gift] = field(default_factory=list[Gift])
    herd_saved: int = 0
    herd_other: int = 0
    herd_other_text: str = ""
    # With Blood Resonance: the humor the character hunts for, "" for any.
    resonance: str = ""
    # With feeding territories and book feeding: the territory it feeds in once, by id,
    # or "" for none; and downtime actions spent patrolling territories it holds.
    territory: str = ""
    patrols: list[Patrol] = field(default_factory=list[Patrol])
    # With the Rack: the simple challenge thrown for hunting outside it (win, tie or
    # lose), or "" before it hunts. Horatio sets it, never the player.
    hunt: str = ""

    @property
    def patrolling(self) -> int:
        return sum(p.actions for p in self.patrols)

    @property
    def herd_shared(self) -> int:
        return self.herd_own + sum(g.amount for g in self.gifts) + self.herd_saved + self.herd_other

    @property
    def empty(self) -> bool:
        return not (
            self.actions
            or self.where.strip()
            or self.herd_shared
            or self.resonance
            or self.territory
            or self.patrolling
        )

    def stored(self) -> dict[str, Any]:
        return {
            "actions": self.actions,
            "where": self.where.strip(),
            "herd_own": self.herd_own,
            "gifts": [
                {"character_id": str(g.character_id), "amount": g.amount}
                for g in self.gifts
                if g.amount
            ],
            "herd_saved": self.herd_saved,
            "herd_other": self.herd_other,
            "herd_other_text": self.herd_other_text.strip(),
            "resonance": self.resonance,
            "territory": self.territory,
            "patrols": [
                {"territory_id": str(p.territory_id), "actions": p.actions}
                for p in self.patrols
                if p.actions
            ],
            "hunt": self.hunt,
        }


def answer_of(submission: Submission | None) -> FeedingAnswer:
    raw = submission.feeding if submission is not None else {}
    return FeedingAnswer(
        actions=int(raw.get("actions", 0)),
        where=str(raw.get("where", "")),
        herd_own=int(raw.get("herd_own", 0)),
        gifts=[Gift(uuid.UUID(g["character_id"]), int(g["amount"])) for g in raw.get("gifts", [])],
        herd_saved=int(raw.get("herd_saved", 0)),
        herd_other=int(raw.get("herd_other", 0)),
        herd_other_text=str(raw.get("herd_other_text", "")),
        resonance=str(raw.get("resonance", "")),
        territory=str(raw.get("territory", "")),
        patrols=[
            Patrol(uuid.UUID(p["territory_id"]), int(p["actions"])) for p in raw.get("patrols", [])
        ],
        hunt=str(raw.get("hunt", "")),
    )


def recipients(db: Session, cycle: DowntimeCycle, giver: Character) -> list[tuple[uuid.UUID, str]]:
    """Who Herd can be given to: everyone else taking part in the cycle who feeds.
    No vampire is left out, Salubri included: a character may be under another
    identity. A ghoul drinks vitae, so it is."""
    feeders = [s for s, splat in SPLATS.items() if splat.panels.feed]
    rows = db.execute(
        select(Character.id, Character.name)
        .join(CycleParticipant, CycleParticipant.character_id == Character.id)
        .where(
            CycleParticipant.cycle_id == cycle.id,
            CycleParticipant.removed_at.is_(None),
            Character.id != giver.id,
            Character.splat.in_(feeders),
        )
        .order_by(Character.name)
    )
    return [(i, n) for i, n in rows]


def check_answer(
    db: Session,
    cycle: DowntimeCycle,
    character: Character,
    basis: dict[str, Any],
    answer: FeedingAnswer,
) -> None:
    """Refuse what cannot be: negative numbers, gifts to someone not taking part,
    or more Herd shared out than the character has."""
    numbers = [answer.actions, answer.herd_own, answer.herd_saved, answer.herd_other]
    if any(n < 0 for n in numbers) or any(g.amount < 0 for g in answer.gifts):
        raise unprocessable("Feeding numbers cannot be negative.")
    if answer.resonance and answer.resonance not in resonance.HUMORS:
        raise unprocessable(f"No humor {answer.resonance!r}.")
    if basis.get("clan") is None and not answer.empty:
        raise unprocessable("This character does not feed.")
    allowed = {i for i, _ in recipients(db, cycle, character)}
    given = [g.character_id for g in answer.gifts if g.amount]
    if any(i not in allowed for i in given):
        raise unprocessable("Herd can only be given to another character taking part.")
    if len(set(given)) != len(given):
        raise unprocessable("Give each character their Herd in one gift.")
    herd = int(basis.get("herd", 0))
    if answer.herd_shared > herd:
        raise unprocessable(
            f"That shares out {answer.herd_shared} dots of Herd; this character has {herd}."
        )
    if answer.territory or answer.patrols:
        from horatio import territories

        troupe = db.get_one(Troupe, cycle.troupe_id)
        if any(p.actions < 0 for p in answer.patrols):
            raise unprocessable("Feeding numbers cannot be negative.")
        if answer.territory:
            found = territories.territory_of(db, troupe, uuid.UUID(answer.territory))
            if found.archived_at is not None:
                raise unprocessable(f"{found.name} is no longer a feeding territory.")
        for patrol in answer.patrols:
            found = territories.territory_of(db, troupe, patrol.territory_id)
            if patrol.actions and not territories.holds(found, character.id):
                raise unprocessable(f"Only {found.name}'s holders patrol it.")


@dataclass
class Received:
    character_id: uuid.UUID
    character_name: str
    amount: int
    # The giver has submitted their downtime; until then the gift may change.
    submitted: bool


def received(db: Session, cycle: DowntimeCycle, character_id: uuid.UUID) -> list[Received]:
    """Herd other characters in the cycle have given this one."""
    rows = db.execute(
        select(Submission, Character)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None))
        .order_by(Character.name)
    )
    found: list[Received] = []
    for submission, giver in rows:
        for gift in answer_of(submission).gifts:
            if gift.character_id == character_id and gift.amount:
                found.append(
                    Received(giver.id, giver.name, gift.amount, submission.status == "submitted")
                )
    return found


def territory_fed(
    db: Session, answer: FeedingAnswer, character_id: uuid.UUID
) -> tuple[FeedingTerritory, bool] | None:
    """The territory the character feeds in with book feeding, and whether it is
    poaching there."""
    if not answer.territory:
        return None
    found = db.get(FeedingTerritory, uuid.UUID(answer.territory))
    if found is None:
        return None
    from horatio.territories import holds

    return found, not holds(found, character_id)


def tally(
    db: Session,
    cycle: DowntimeCycle,
    character: Character,
    feeding_need: rules.Need,
    submission: Submission | None,
    *,
    submitted_only: bool = False,
    with_territories: bool = False,
) -> rules.Tally:
    """The advisory count for the character. Staff count only gifts from
    downtimes that were submitted. With feeding territories, feeding in one stands in
    for a feeding action."""
    answer = answer_of(submission)
    gifts = [
        (r.character_name, r.amount)
        for r in received(db, cycle, character.id)
        if r.submitted or not submitted_only
    ]
    counted = rules.tally(feeding_need, answer.actions, answer.herd_own, gifts)
    fed = territory_fed(db, answer, character.id) if with_territories else None
    if fed is None:
        return counted
    territory, poaching = fed
    label = f"{'Poaching' if poaching else 'Feeding'} in {territory.name}"
    return rules.Tally(counted.needed, (*counted.parts, (label, 1)), counted.always_half)


def patrol_names(db: Session, answer: FeedingAnswer) -> dict[uuid.UUID, str]:
    ids = [p.territory_id for p in answer.patrols]
    if not ids:
        return {}
    rows = db.execute(
        select(FeedingTerritory.id, FeedingTerritory.name).where(FeedingTerritory.id.in_(ids))
    )
    return {i: n for i, n in rows}


def summary(
    db: Session,
    answer: FeedingAnswer,
    *,
    with_resonance: bool = False,
    show: Shown | None = None,
    participant: CycleParticipant | None = None,
) -> str:
    """The player's Feeding section in one line, for staff and for the results; with
    Blood Resonance, the humor hunted for too; with feeding territories, where it fed
    and patrolled; with the Rack, the vessel it took rather than its actions and Herd."""
    show = show or Shown(resonance=with_resonance)
    parts: list[str] = []
    if show.rack and participant is not None:
        from horatio import rack

        took = rack.taken_with_territory(db, participant)
        parts.append(rack.card_text(took.card, took.territory) if took else "no Feeding Card")
        if answer.where.strip():
            parts.append(answer.where.strip())
    else:
        names = dict(
            db.execute(
                select(Character.id, Character.name).where(
                    Character.id.in_([g.character_id for g in answer.gifts])
                )
            ).all()
        )
        parts = [f"{answer.actions} feeding action{'' if answer.actions == 1 else 's'}"]
        if answer.where.strip():
            parts[0] += f" ({answer.where.strip()})"
        herd: list[str] = []
        if answer.herd_own:
            herd.append(f"{answer.herd_own} for my feeding")
        herd += [
            f"{g.amount} to {names.get(g.character_id, '?')}" for g in answer.gifts if g.amount
        ]
        if answer.herd_saved:
            herd.append(f"{answer.herd_saved} saved for game")
        if answer.herd_other:
            other = f"{answer.herd_other} other"
            if answer.herd_other_text.strip():
                other += f" ({answer.herd_other_text.strip()})"
            herd.append(other)
        if herd:
            parts.append("Herd: " + ", ".join(herd))
        if show.territories and participant is not None:
            fed = territory_fed(db, answer, participant.character_id)
            if fed is not None:
                parts.append(f"{'poaching' if fed[1] else 'feeding'} in {fed[0].name}")
    if show.territories and answer.patrolling:
        territory = patrol_names(db, answer)
        for patrol in answer.patrols:
            if patrol.actions:
                actions = f"{patrol.actions} action{'' if patrol.actions == 1 else 's'}"
                parts.append(f"patrolling {territory.get(patrol.territory_id, '?')} ({actions})")
    if show.resonance and answer.resonance in resonance.HUMORS:
        parts.append(f"hunting {resonance.HUMORS[answer.resonance].name.lower()} blood")
    return " · ".join(parts)


# --- poaching and patrols ---------------------------------------------------------------


@dataclass
class PatrolBy:
    character_id: uuid.UUID
    character_name: str
    actions: int


def poached(
    db: Session, participant: CycleParticipant, answer: FeedingAnswer, show: Shown
) -> FeedingTerritory | None:
    """The territory the character poached in, if it did: one it fed in, or took a
    card from, that it does not hold."""
    if not show.territories:
        return None
    from horatio import territories

    if show.rack:
        from horatio import rack

        took = rack.taken_with_territory(db, participant)
        territory = took.territory if took else None
    else:
        fed = territory_fed(db, answer, participant.character_id)
        territory = fed[0] if fed else None
    if territory is None or territories.holds(territory, participant.character_id):
        return None
    return territory


def patrols_of(
    db: Session, cycle: DowntimeCycle, territory_id: uuid.UUID, but: uuid.UUID
) -> list[PatrolBy]:
    """Who patrolled the territory this cycle, with how many actions, from submitted
    downtimes: each action is a simple challenge against a poacher there."""
    rows = db.execute(
        select(Submission, Character)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(
            CycleParticipant.cycle_id == cycle.id,
            CycleParticipant.removed_at.is_(None),
            Submission.status == "submitted",
            Character.id != but,
        )
        .order_by(Character.name)
    )
    found: list[PatrolBy] = []
    for submission, character in rows:
        actions = sum(
            p.actions for p in answer_of(submission).patrols if p.territory_id == territory_id
        )
        if actions:
            found.append(PatrolBy(character.id, character.name, actions))
    return found


def catches_by(
    db: Session, cycle: DowntimeCycle, patroller: Character, show: Shown
) -> list[tuple[str, str]]:
    """The poachers the character's patrols caught this cycle, as (poacher, territory),
    from the answers staff gave them."""
    rows = db.execute(
        select(Submission, CycleParticipant, Character)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None))
        .order_by(Character.name)
    )
    found: list[tuple[str, str]] = []
    for submission, participant, character in rows:
        if str(patroller.id) not in submission.feeding_caught_by:
            continue
        territory = poached(db, participant, answer_of(submission), show)
        found.append((character.name, territory.name if territory else "a territory"))
    return found


# --- the storytellers' answer -----------------------------------------------------------


def write_answer(
    db: Session,
    staff: User,
    cycle: DowntimeCycle,
    troupe: Troupe,
    participant: CycleParticipant,
    character: Character,
    result: str | None,
    reply: str,
    humor: str | None = None,
    dyscrasia: str = "",
    caught_by: Sequence[uuid.UUID] = (),
) -> Submission:
    """Answer the character's feeding: full or half Blood next game, with the
    working kept as it stood, or something else in the reply's own words; with
    Blood Resonance, the Resonance it fed on and any Dyscrasia; with feeding
    territories, which patrols caught it poaching. No result takes the answer back."""
    from horatio.downtimes import submission_for

    if not tracked(troupe):
        raise not_tracked()
    if cycle.status == "complete":
        raise conflict("This cycle is complete.")
    submission = submission_for(db, participant)
    if submission is None or submission.status != "submitted":
        raise conflict("Only a submitted downtime's feeding can be answered.")
    if result is not None and result not in RESULTS:
        raise unprocessable(f"Answer one of {', '.join(RESULTS)}.")
    reply = reply.strip()
    if result == "other" and not reply:
        raise unprocessable("Say what happens instead.")
    if humor is not None and humor not in resonance.HUMORS:
        raise unprocessable(f"No humor {humor!r}.")
    if dyscrasia and (humor is None or resonance.dyscrasia(humor, dyscrasia) is None):
        raise unprocessable(f"No Dyscrasia {dyscrasia!r} for that Resonance.")
    show = shown(troupe)
    answer = answer_of(submission)
    if caught_by:
        territory = poached(db, participant, answer, show)
        patrollers = (
            {p.character_id for p in patrols_of(db, cycle, territory.id, character.id)}
            if territory is not None
            else set()
        )
        if not set(caught_by) <= patrollers:
            raise unprocessable("Only a character who patrolled where it poached can catch it.")
    basis = participant_basis(db, participant, character, cycle)
    feeding_need = need(db, cycle, participant, basis)
    if feeding_need is None:
        raise unprocessable("This character does not feed.")
    submission.feeding_result = result
    submission.feeding_reply = reply if result else ""
    submission.feeding_working = ""
    if result in ("full", "half") and show.rack:
        from horatio import rack

        took = rack.taken_with_territory(db, participant)
        submission.feeding_working = (
            f"took {rack.card_text(took.card, took.territory)}."
            if took
            else "took no Feeding Card."
        )
    elif result in ("full", "half"):
        counted = tally(
            db,
            cycle,
            character,
            feeding_need,
            submission,
            submitted_only=True,
            with_territories=show.territories,
        )
        submission.feeding_working = rules.working(feeding_need, counted)
    if result is None:
        submission.feeding_resonance, submission.feeding_dyscrasia = None, ""
        submission.feeding_caught_by = []
    else:
        # With a rule off, an answer leaves what it gave before, kept for when the rule
        # comes back.
        if show.resonance:
            submission.feeding_resonance, submission.feeding_dyscrasia = humor, dyscrasia
        if show.territories:
            submission.feeding_caught_by = [str(i) for i in dict.fromkeys(caught_by)]
    submission.feeding_answered_by = staff.id if result else None
    submission.feeding_answered_at = datetime.now(UTC) if result else None
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.feeding_answered",
        troupe_id=troupe.id,
        character_id=character.id,
        cycle_id=cycle.id,
        result=result or "none",
    )
    return submission


def territory_text(db: Session, submission: Submission, show: Shown) -> str:
    """With feeding territories, what came of poaching and patrolling: "You were caught
    poaching in the Docks by Agnes." "Patrolling the Docks, you caught Bram poaching.";
    "" when the character did neither."""
    if not show.territories:
        return ""
    participant = db.get_one(CycleParticipant, submission.participant_id)
    cycle = db.get_one(DowntimeCycle, participant.cycle_id)
    character = db.get_one(Character, participant.character_id)
    answer = answer_of(submission)
    lines: list[str] = []
    territory = poached(db, participant, answer, show)
    if territory is not None:
        catchers = [
            p.character_name
            for p in patrols_of(db, cycle, territory.id, character.id)
            if str(p.character_id) in submission.feeding_caught_by
        ]
        if catchers:
            lines.append(
                f"You were caught poaching in {territory.name} by {' and '.join(catchers)}."
            )
        else:
            lines.append(f"Poaching in {territory.name}, you went unnoticed.")
    if answer.patrolling:
        caught = catches_by(db, cycle, character, show)
        names = patrol_names(db, answer)
        for patrol in answer.patrols:
            name = names.get(patrol.territory_id, "your territory")
            here = [poacher for poacher, where in caught if where == name]
            lines.append(
                f"Patrolling {name}, you caught {' and '.join(here)} poaching."
                if here
                else f"Patrolling {name}, you caught no one."
            )
    return " ".join(lines)


def result_text(
    submission: Submission,
    *,
    with_resonance: bool = False,
    territory_words: str = "",
) -> str | None:
    """The Feeding part of the delivered results, or None if it is unanswered."""
    if submission.feeding_result is None:
        return None
    if submission.feeding_result == "other":
        text = f"*Result:* {submission.feeding_reply}"
    else:
        text = f"*Result:* **{RESULT_WORDS[submission.feeding_result]}**"
        if submission.feeding_reply:
            text += f" {submission.feeding_reply}"
    fed_on = resonance.answer_text(submission.feeding_resonance, submission.feeding_dyscrasia)
    if with_resonance and fed_on:
        text += f"\n\n{fed_on}"
    if territory_words:
        text += f"\n\n{territory_words}"
    if submission.feeding_working:
        # Its own paragraph, so Horatio shows it folded away.
        text += f"\n\n▸ How it was worked out: {submission.feeding_working}"
    return text


def compose(db: Session, submission: Submission, show: Shown) -> str | None:
    """The Feeding part of the results: None while it is unanswered, or when the
    troupe doesn't track feeding. `show` says which optional rules it shows."""
    if not show.tracked:
        return None
    found = result_text(
        submission,
        with_resonance=show.resonance,
        territory_words=territory_text(db, submission, show),
    )
    if found is None:
        return None
    answer = answer_of(submission)
    participant = db.get_one(CycleParticipant, submission.participant_id)
    words = summary(db, answer, show=show, participant=participant)
    lines = ["**Feeding**"]
    if words and (not answer.empty or show.rack):
        lines.append(f"*Your feeding:* {words}")
    return "\n".join(lines) + "\n" + found


def mark_half_blood(db: Session, character: Character, submission: Submission) -> None:
    """On delivery: a half answer starts the character's next Play View game at
    half Blood; any other answer, at the usual amount. A game already started
    but with nothing tapped yet is the next game."""
    if submission.feeding_result is None:
        return
    half = submission.feeding_result == "half"
    game = db.scalar(
        select(PlayGame).where(PlayGame.character_id == character.id, PlayGame.ended_at.is_(None))
    )
    untouched = (
        game is not None
        and db.scalar(select(PlayEvent.id).where(PlayEvent.game_id == game.id).limit(1)) is None
    )
    if game is not None and untouched:
        game.half_blood = half
        character.half_blood_next_game = False
    else:
        character.half_blood_next_game = half
    db.flush()

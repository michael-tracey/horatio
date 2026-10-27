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
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import (
    Character,
    CycleParticipant,
    DowntimeCycle,
    FeedingAdjustment,
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
class FeedingAnswer:
    """The Feeding section of one submission, as kept in `Submission.feeding`."""

    actions: int = 0
    where: str = ""
    herd_own: int = 0
    gifts: list[Gift] = field(default_factory=list[Gift])
    herd_saved: int = 0
    herd_other: int = 0
    herd_other_text: str = ""

    @property
    def herd_shared(self) -> int:
        return self.herd_own + sum(g.amount for g in self.gifts) + self.herd_saved + self.herd_other

    @property
    def empty(self) -> bool:
        return not (self.actions or self.where.strip() or self.herd_shared)

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


def tally(
    db: Session,
    cycle: DowntimeCycle,
    character: Character,
    feeding_need: rules.Need,
    submission: Submission | None,
    *,
    submitted_only: bool = False,
) -> rules.Tally:
    """The advisory count for the character. Staff count only gifts from
    downtimes that were submitted."""
    answer = answer_of(submission)
    gifts = [
        (r.character_name, r.amount)
        for r in received(db, cycle, character.id)
        if r.submitted or not submitted_only
    ]
    return rules.tally(feeding_need, answer.actions, answer.herd_own, gifts)


def summary(db: Session, answer: FeedingAnswer) -> str:
    """The player's Feeding section in one line, for staff and for the results."""
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
    herd += [f"{g.amount} to {names.get(g.character_id, '?')}" for g in answer.gifts if g.amount]
    if answer.herd_saved:
        herd.append(f"{answer.herd_saved} saved for game")
    if answer.herd_other:
        other = f"{answer.herd_other} other"
        if answer.herd_other_text.strip():
            other += f" ({answer.herd_other_text.strip()})"
        herd.append(other)
    if herd:
        parts.append("Herd: " + ", ".join(herd))
    return " · ".join(parts)


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
) -> Submission:
    """Answer the character's feeding: full or half Blood next game, with the
    working kept as it stood, or something else in the reply's own words. No
    result takes the answer back."""
    from horatio.downtimes import submission_for
    from horatio.responses import delivered

    if cycle.status == "complete":
        raise conflict("This cycle is complete.")
    submission = submission_for(db, participant)
    if submission is None or submission.status != "submitted":
        raise conflict("Only a submitted downtime's feeding can be answered.")
    if delivered(db, submission.id):
        raise conflict("These results have already been delivered.")
    if result is not None and result not in RESULTS:
        raise unprocessable(f"Answer one of {', '.join(RESULTS)}.")
    reply = reply.strip()
    if result == "other" and not reply:
        raise unprocessable("Say what happens instead.")
    basis = participant_basis(db, participant, character, cycle)
    feeding_need = need(db, cycle, participant, basis)
    if feeding_need is None:
        raise unprocessable("This character does not feed.")
    submission.feeding_result = result
    submission.feeding_reply = reply if result else ""
    submission.feeding_working = ""
    if result in ("full", "half"):
        counted = tally(db, cycle, character, feeding_need, submission, submitted_only=True)
        submission.feeding_working = rules.working(feeding_need, counted)
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


def result_text(submission: Submission) -> str | None:
    """The Feeding part of the delivered results, or None if it is unanswered."""
    if submission.feeding_result is None:
        return None
    if submission.feeding_result == "other":
        return f"*Result:* {submission.feeding_reply}"
    text = f"*Result:* **{RESULT_WORDS[submission.feeding_result]}**"
    if submission.feeding_reply:
        text += f" {submission.feeding_reply}"
    if submission.feeding_working:
        # Its own paragraph, so Horatio shows it folded away.
        text += f"\n\n▸ How it was worked out: {submission.feeding_working}"
    return text


def compose(db: Session, submission: Submission) -> str | None:
    found = result_text(submission)
    if found is None:
        return None
    answer = answer_of(submission)
    lines = ["**Feeding**"]
    if not answer.empty:
        lines.append(f"*Your feeding:* {summary(db, answer)}")
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

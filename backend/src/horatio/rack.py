"""Advanced Feeding, the Rack, an optional feeding rule (MET: VTM Vol. 2, pp. 298-303),
as a troupe plays it when it switches the rule on (Troupe.feeding_rack). It builds on
Blood Resonance (horatio.resonance), as each vessel carries one, so it needs that rule
on too.

Each vessel is a Feeding Card with a number, a Resonance, perhaps a Dyscrasia, and a
few words on who it is (pp. 299-300). The book lays the cards on a table at the game
and players take one as they arrive; it replaces spending downtime actions on feeding
(p. 298). Horatio runs feeding through downtimes, so the table is the cycle's:

- Staff lay out the Rack for the cycle: as many cards as they choose, with the book's
  suggestion worked out from those taking part and the mood of the domain (p. 306),
  dealt at random and then changed as they like. Each feeding territory gets as many
  cards of its own as its size (horatio.territories).
- Each character takes one card on the downtime form, first come, first served: from
  the Rack, from a territory it holds, or by poaching another's. A character with Herd
  is dealt one card of its own for each dot (p. 303).
- A character can hunt outside the Rack once a cycle ("Go Fish", p. 303): Horatio
  throws the simple challenge and deals it 3 cards on a win, 2 on a tie, 1 on a loss.
- A feeding restriction, such as Prey Exclusion or the Ventrue clan weakness, is a set
  of card numbers staff give the character, by their last digit: it may take only
  those, or never those (p. 301). Its Herd cards always suit it.
- Taking a card means the character fed; staff answer full Blood, as the book has it,
  with the card's Resonance and Dyscrasia, unless they say otherwise.
"""

import math
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, resonance, territories
from horatio.models import (
    Character,
    CycleParticipant,
    DowntimeCycle,
    FeedingCard,
    FeedingTerritory,
    Submission,
    Troupe,
    User,
)
from horatio.sheets import conflict, unprocessable

PAGES = "Vol. 2, pp. 298-303"
# The book's adjustments to the number of cards, in tenths (p. 306).
MASQUERADE = {"none": 0, "minor": -1, "notable": -2, "severe": -3}
MOOD = {"none": 0, "slightly": 1, "notably": 2, "very": 3}
# Cards dealt for hunting outside the Rack, by the simple challenge's result.
HUNT_CARDS = {"win": 3, "tie": 2, "lose": 1}
SOURCE_WORDS = {
    "rack": "the Rack",
    "territory": "a territory",
    "herd": "your Herd",
    "hunt": "hunting outside the Rack",
}


def on(troupe: Troupe | None) -> bool:
    """The Rack is played: switched on, with feeding tracked and Blood Resonance on."""
    from horatio.feeding import resonance_on

    return troupe is not None and resonance_on(troupe) and troupe.feeding_rack


def suggested(players: int, masquerade: str = "none", mood: str = "none") -> int:
    """The book's number of cards: one for each player and 2 more for every 5, changed
    by a tenth for each step of Masquerade trouble or festive mood, fractions rounded
    up (p. 306)."""
    base = math.ceil(players * 7 / 5)
    return max(0, math.ceil(base * (10 + MASQUERADE[masquerade] + MOOD[mood]) / 10))


# --- the cards ---------------------------------------------------------------------------


def cards(db: Session, cycle: DowntimeCycle) -> list[FeedingCard]:
    return list(
        db.scalars(
            select(FeedingCard)
            .where(FeedingCard.cycle_id == cycle.id)
            .order_by(FeedingCard.source, FeedingCard.number)
        )
    )


def random_card(
    cycle: DowntimeCycle, number: int, share: int, rng: random.Random, **where: Any
) -> FeedingCard:
    """A card of a random humor, carrying one of its Dyscrasias `share` times in 100."""
    humor = rng.choice(list(resonance.HUMORS.values()))
    dyscrasia = rng.choice(humor.dyscrasias).name if rng.randrange(100) < share else ""
    return FeedingCard(
        cycle_id=cycle.id, number=number, resonance=humor.key, dyscrasia=dyscrasia, **where
    )


def numbers(db: Session, cycle: DowntimeCycle, count: int, rng: random.Random) -> list[int]:
    """`count` card numbers not yet used in the cycle, from 1 to 100 while they last."""
    used = set(db.scalars(select(FeedingCard.number).where(FeedingCard.cycle_id == cycle.id)))
    free = [n for n in range(1, 101) if n not in used]
    rng.shuffle(free)
    top = max([100, *used])
    while len(free) < count:
        top += 1
        free.append(top)
    return free[:count]


def herd_of(db: Session, participant: CycleParticipant, cycle: DowntimeCycle) -> int:
    from horatio.feeding import participant_basis

    character = db.get_one(Character, participant.character_id)
    return int(participant_basis(db, participant, character, cycle).get("herd", 0))


def deal(
    db: Session,
    staff: User,
    cycle: DowntimeCycle,
    troupe: Troupe,
    count: int,
    share: int,
    rng: random.Random | None = None,
) -> None:
    """Lay `count` more cards on the cycle's Rack, a Dyscrasia on about `share` in 100.
    Each territory with no cards yet this cycle gets its size's worth, and each
    character taking part gets a card for each dot of its Herd it has not had yet."""
    rng = rng or random.Random()
    if cycle.status == "complete":
        raise conflict("This cycle is complete.")
    if count < 0 or not 0 <= share <= 100:
        raise unprocessable("Lay out 0 or more cards, with a Dyscrasia on 0 to 100 in 100.")
    existing = cards(db, cycle)
    wanted: list[dict[str, Any]] = [{"source": "rack"} for _ in range(count)]
    if territories.on(troupe):
        dealt = {c.territory_id for c in existing if c.territory_id is not None}
        for territory in territories.listed(db, troupe):
            if territory.id not in dealt:
                vessels = territories.SIZES[territory.size].vessels
                wanted += [{"source": "territory", "territory_id": territory.id}] * vessels
    participants = db.scalars(
        select(CycleParticipant).where(
            CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None)
        )
    )
    for participant in participants:
        had = sum(1 for c in existing if c.source == "herd" and c.dealt_to == participant.id)
        wanted += [{"source": "herd", "dealt_to": participant.id}] * max(
            0, herd_of(db, participant, cycle) - had
        )
    for number, where in zip(numbers(db, cycle, len(wanted), rng), wanted, strict=True):
        db.add(random_card(cycle, number, share, rng, **where))
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.rack_dealt",
        troupe_id=troupe.id,
        cycle_id=cycle.id,
        count=str(count),
        all=str(len(wanted)),
    )


def change_card(
    db: Session,
    cycle: DowntimeCycle,
    card: FeedingCard,
    humor: str,
    dyscrasia: str,
    descriptor: str,
) -> None:
    if cycle.status == "complete":
        raise conflict("This cycle is complete.")
    if humor not in resonance.HUMORS:
        raise unprocessable(f"No humor {humor!r}.")
    if dyscrasia and resonance.dyscrasia(humor, dyscrasia) is None:
        raise unprocessable(f"No Dyscrasia {dyscrasia!r} for that Resonance.")
    card.resonance, card.dyscrasia, card.descriptor = humor, dyscrasia, descriptor.strip()
    db.flush()


def remove_card(db: Session, cycle: DowntimeCycle, card: FeedingCard) -> None:
    if cycle.status == "complete":
        raise conflict("This cycle is complete.")
    if card.taken_by is not None:
        raise conflict("A character has taken that card; it can't be removed now.")
    db.delete(card)
    db.flush()


def card_of(db: Session, cycle: DowntimeCycle, card_id: uuid.UUID) -> FeedingCard:
    found = db.get(FeedingCard, card_id)
    if found is None or found.cycle_id != cycle.id:
        raise unprocessable("No such Feeding Card in this cycle.")
    return found


# --- taking one --------------------------------------------------------------------------


def taken(db: Session, participant: CycleParticipant) -> FeedingCard | None:
    return db.scalar(select(FeedingCard).where(FeedingCard.taken_by == participant.id))


def suits(character: Character, card: FeedingCard) -> bool:
    """Whether the character's feeding restriction lets it feed on the card. Its Herd's
    cards always do (p. 303)."""
    rule = character.feeding_numbers
    if not rule or card.source == "herd":
        return True
    ending = card.number % 10 in rule.get("endings", [])
    return ending if rule.get("mode") == "only" else not ending


def restriction_text(rule: dict[str, Any] | None) -> str:
    """ "Only cards ending in 5 or 9": a feeding restriction in words; "" for none."""
    if not rule or not rule.get("endings"):
        return ""
    endings = [str(e) for e in sorted(rule["endings"])]
    listed = endings[0] if len(endings) == 1 else f"{', '.join(endings[:-1])} or {endings[-1]}"
    return f"{'Only' if rule.get('mode') == 'only' else 'Never'} cards ending in {listed}"


def visible(db: Session, cycle: DowntimeCycle, participant: CycleParticipant) -> list[FeedingCard]:
    """The cards the character can see: those left on the Rack and in every territory,
    those dealt to it, and the one it took."""
    return [
        c
        for c in cards(db, cycle)
        if c.taken_by == participant.id
        or (c.taken_by is None and (c.dealt_to is None or c.dealt_to == participant.id))
    ]


def take(
    db: Session,
    cycle: DowntimeCycle,
    troupe: Troupe,
    participant: CycleParticipant,
    character: Character,
    submission: Submission | None,
    card_id: uuid.UUID | None,
) -> None:
    """Take a card, giving back any taken before; or give it back with no card."""
    from horatio.downtimes import ensure_can_submit

    ensure_can_submit(db, cycle, participant)
    if submission is not None and submission.feeding_result is not None:
        raise conflict("A storyteller has already answered your feeding; it can no longer change.")
    before = taken(db, participant)
    card = card_of(db, cycle, card_id) if card_id is not None else None
    if card is not None and card is not before:
        if card.taken_by is not None:
            raise conflict("Someone has taken that vessel already.")
        if card.dealt_to is not None and card.dealt_to != participant.id:
            raise unprocessable("That card was dealt to another character.")
        if card.source == "territory" and not territories.on(troupe):
            raise unprocessable("This troupe doesn't play feeding territories.")
        if not suits(character, card):
            raise unprocessable(
                f"{character.name} can't feed on that vessel: "
                f"{restriction_text(character.feeding_numbers).lower()}."
            )
    if before is not None and before is not card:
        before.taken_by, before.taken_at = None, None
        db.flush()
    if card is not None and card is not before:
        card.taken_by, card.taken_at = participant.id, datetime.now(UTC)
    db.flush()


def hunt(
    db: Session,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    submission: Submission,
    rng: random.Random | None = None,
) -> str:
    """Hunt outside the Rack, once a cycle: a simple challenge, and 3, 2 or 1 cards
    dealt to the character to choose from. Returns win, tie or lose."""
    from horatio.downtimes import ensure_can_submit

    rng = rng or random.Random()
    ensure_can_submit(db, cycle, participant)
    if submission.feeding.get("hunt"):
        raise conflict("This character has hunted outside the Rack this cycle already.")
    outcome = rng.choice(list(HUNT_CARDS))
    for number in numbers(db, cycle, HUNT_CARDS[outcome], rng):
        db.add(random_card(cycle, number, 50, rng, source="hunt", dealt_to=participant.id))
    submission.feeding = {**submission.feeding, "hunt": outcome}
    db.flush()
    return outcome


# --- in words ----------------------------------------------------------------------------


def card_text(card: FeedingCard, territory: FeedingTerritory | None = None) -> str:
    """ "Feeding Card 91, sanguine, Manic High (a jogger), from the Rack"."""
    humor = resonance.HUMORS[card.resonance].name.lower()
    text = f"Feeding Card {card.number}, {humor}, {card.dyscrasia or 'no Dyscrasia'}"
    if card.descriptor:
        text += f" ({card.descriptor})"
    where = territory.name if territory is not None else SOURCE_WORDS[card.source]
    return f"{text}, from {where}"


@dataclass
class Taken:
    card: FeedingCard
    territory: FeedingTerritory | None


def taken_with_territory(db: Session, participant: CycleParticipant) -> Taken | None:
    card = taken(db, participant)
    if card is None:
        return None
    territory = db.get(FeedingTerritory, card.territory_id) if card.territory_id else None
    return Taken(card, territory)

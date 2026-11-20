"""A character's plan (issue #1052): the traits its player means to buy with XP
later, in order, on the Experience tab.

Each line is priced by the cart itself (horatio.cart.apply_changes, on a dry run),
as if the lines before it had been bought, so a line costs here what it would cost
in the cart: in-clan or not, with the troupe's own prices and settings. It is
priced as if the character had the XP for every line, so it says what each costs,
not whether it can be paid yet; the running total against the XP unspent says
that, and the troupe's usual award for a game (`usual_award`) roughly how many
games away the rest is. Nothing is saved by pricing.

A plan is its player's own. The staff who see the sheet see it only while the
player shares it.
"""

import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import cart, checkin, game_xp, sheets, teaching
from horatio.auth.viewing import read_only
from horatio.models import Character, Troupe, User, XpEntry, XpPlan
from horatio.rules.status import STATUS_CATEGORY
from horatio.sheets import TraitKey, unprocessable

MAX_LINES = 50
# XP the character is lent while its plan is priced, so no line is refused for want
# of it: more than any plan could cost.
HEADROOM = 1_000_000
# Named as a line's teacher while it is priced, so a troupe's teacher rule
# (horatio.teaching) prices it rather than refusing it; the cart asks for the real one.
PRICING_TEACHER = "A teacher, chosen in the cart"


@dataclass(frozen=True)
class Line:
    """A trait to take to a rating."""

    category: str
    name: str
    detail: str
    rating: int

    @property
    def key(self) -> TraitKey:
        return (self.category, self.name, self.detail)

    def kept(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "detail": self.detail,
            "rating": self.rating,
        }


@dataclass(frozen=True)
class Priced:
    line: Line
    # The rating it raises from: held now, or as the lines before it leave it.
    from_rating: int
    # XP it costs (negative: gives back), as the cart prices it; None if that can't
    # be told, or the plan wasn't priced.
    cost: int | None = None
    # Why the cart would refuse it, even with the XP for it.
    refused: str | None = None
    # Already held at its rating or more: done.
    held: bool = False
    # Waits on the home troupe once bought, like a discipline dot.
    needs_approval: bool = False
    # A power a merit opens past a check: "Hard as Steel: 20 XP".
    because: str | None = None
    # A troupe's teacher rule asks a teacher for it, chosen in the cart.
    teacher: teaching.Need | None = None


@dataclass(frozen=True)
class Award:
    """The XP a game usually gives the character, and where that comes from, in words."""

    per_game: int
    source: str


def find(db: Session, character: Character) -> XpPlan | None:
    return db.scalar(select(XpPlan).where(XpPlan.character_id == character.id))


def lines_of(plan: XpPlan | None) -> list[Line]:
    return [
        Line(str(x["category"]), str(x["name"]), str(x.get("detail", "")), int(x["rating"]))
        for x in (plan.lines if plan is not None else [])
    ]


def checked_line(db: Session, character: Character, line: Line) -> Line:
    """The line with the trait's own name, or refused (422) if XP can't buy it."""
    definition, category = sheets.find_definition(db, character, line.category, line.name)
    if not category.rated or category.derived or category.key == STATUS_CATEGORY:
        raise unprocessable(f"{category.name} aren't bought with XP.")
    if category.max_rating is not None and line.rating > category.max_rating:
        raise unprocessable(f"{definition.name} goes no higher than {category.max_rating}.")
    return Line(category.key, definition.name, line.detail.strip(), line.rating)


def save(db: Session, character: Character, lines: list[Line], *, shared: bool) -> XpPlan:
    if character.kind != "pc":
        raise sheets.conflict("NPCs spend no experience.")
    if len(lines) > MAX_LINES:
        raise unprocessable(f"A plan holds at most {MAX_LINES} lines.")
    checked = [checked_line(db, character, line) for line in lines]
    plan = find(db, character)
    if plan is None:
        plan = XpPlan(character_id=character.id)
        db.add(plan)
    plan.lines = [line.kept() for line in checked]
    plan.shared = shared
    db.flush()
    return plan


def price(db: Session, character: Character, lines: list[Line]) -> list[Priced]:
    """Each line priced by the cart, in order, as if the ones before it were bought;
    unpriced if nothing may be written, such as for the custodian viewing as someone,
    as the cart prices by making the changes and taking them back."""
    held = {row.key: row.trait.rating or 0 for row in sheets.sheet_rows(db, character)}
    froms: list[int] = []
    for line in lines:
        froms.append(held.get(line.key, 0))
        held[line.key] = max(held.get(line.key, 0), line.rating)
    # Lines already held at their rating are done; the rest go to the cart.
    wanted = [i for i, line in enumerate(lines) if line.rating > froms[i]]
    priced = [
        Priced(line=line, from_rating=froms[i], held=line.rating <= froms[i])
        for i, line in enumerate(lines)
    ]
    if not wanted or read_only(db):
        return priced
    player = db.get_one(User, character.player_id)
    changes: list[cart.Change] = [
        cart.SetRating(
            lines[i].category,
            lines[i].name,
            lines[i].detail,
            lines[i].rating,
            teacher=PRICING_TEACHER,
        )
        for i in wanted
    ]
    savepoint = db.begin_nested()
    try:
        db.add(
            XpEntry(
                character_id=character.id,
                kind="award",
                amount=HEADROOM,
                reason="Lent while the plan is priced",
                entered_by=player.id,
            )
        )
        db.flush()
        outcomes = cart.apply_changes(db, player, character, changes)
    finally:
        savepoint.rollback()
        db.expire_all()
    for i, outcome in zip(wanted, outcomes, strict=True):
        priced[i] = Priced(
            line=lines[i],
            from_rating=froms[i],
            cost=outcome.cost,
            refused=outcome.refused,
            needs_approval=outcome.needs_approval,
            because=outcome.because,
            teacher=outcome.teacher,
        )
    return priced


def usual_award(db: Session, character: Character) -> Award | None:
    """What a game the character comes to usually gives it, by its home troupe's game
    XP (horatio.game_xp): the chart's figure for a game attended in the character's
    band of earned XP, or with no chart, the troupe's session XP; no more than the
    monthly cap, where the troupe caps awards at it. Adjustments staff tick, absentee
    games and downtime XP are left out. None without a home troupe, or for nothing."""
    if character.home_troupe_id is None:
        return None
    troupe = db.get_one(Troupe, character.home_troupe_id)
    found = game_xp.settings(troupe)
    if found.bands:
        band = game_xp.band_of(found, checkin.earned(db, [character.id])[character.id])
        if band is None:
            return None
        per_game, source = band[1].attended, f"the troupe's chart, {band[0]} band"
    else:
        per_game, source = troupe.session_xp, "the troupe's session XP"
    if found.cap == "cap":
        per_game = min(per_game, game_xp.monthly_limit(found))
    return Award(per_game, source) if per_game > 0 else None


def games_away(short: int, award: Award | None) -> int | None:
    """Roughly how many games until `short` XP more is had, at the usual award."""
    if short <= 0:
        return 0
    if award is None:
        return None
    return math.ceil(short / award.per_game)


def visible_to(character: Character, user: User, plan: XpPlan | None) -> bool:
    """Its player sees it; anyone else who sees the sheet, only while it is shared."""
    return is_players(character, user) or (plan is not None and plan.shared)


def is_players(character: Character, user: User) -> bool:
    return character.kind == "pc" and character.player_id == user.id

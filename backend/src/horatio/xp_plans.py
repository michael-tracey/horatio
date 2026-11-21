"""A character's plan (issue #1052): the traits its player means to buy with XP
later, in order, on the Experience tab.

Each line is priced by the cart itself (horatio.cart.apply_changes, on a dry run),
as if the lines before it had been bought, so a line costs here what it would cost
in the cart: in-clan or not, with the troupe's own prices and settings. What is in
the player's cart (kept in the browser, and sent with the request) is priced first,
as bought, so the plan's lines cost what they would after it (#1086). It is priced
as if the character had the XP for every line, so it says what each costs, not
whether it can be paid yet; the running total against the XP unspent says that,
and the XP a game usually brings (`usual_award`: the game's own, and its share of
the downtimes) roughly how many games away the rest is. Nothing is saved by pricing.

A plan is its player's own. The staff who see the sheet see it only while the
player shares it. A retired character's plan stays as it was, unpriced and unchanged.
"""

import math
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import cart, checkin, game_xp, sheets, teaching
from horatio.auth.viewing import read_only
from horatio.models import (
    Character,
    DowntimeCycle,
    ScheduledGame,
    Troupe,
    User,
    XpEntry,
    XpPlan,
)
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
    # Already held at its rating or more, once the cart is bought: done.
    held: bool = False
    # Held at its rating only once the cart is bought: the cart takes it there.
    in_cart: bool = False
    # The next step for its trait after the cart: no line before it raises the trait.
    next_step: bool = False
    # Waits on the home troupe once bought, like a discipline dot.
    needs_approval: bool = False
    # A power a merit opens past a check: "Hard as Steel: 20 XP".
    because: str | None = None
    # A troupe's teacher rule asks a teacher for it, chosen in the cart.
    teacher: teaching.Need | None = None


@dataclass(frozen=True)
class Pricing:
    lines: list[Priced]
    # What the cart's changes spend, bought before the plan.
    cart_cost: int = 0
    # Whether the lines are priced at all.
    priced: bool = True


@dataclass(frozen=True)
class Award:
    """The XP a game usually brings the character, and where that comes from, in words:
    the game's own award, and its share of the downtime XP between games."""

    per_game: int
    source: str
    # Downtime XP for each game, worked out from the troupe's cycles and games.
    downtime: Fraction = Fraction(0)
    downtime_source: str | None = None

    @property
    def total(self) -> Fraction:
        return self.per_game + self.downtime


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
    if character.status == "retired":
        raise sheets.conflict("This character is retired.")
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


def ratings(db: Session, character: Character) -> dict[TraitKey, int]:
    return {row.key: row.trait.rating or 0 for row in sheets.sheet_rows(db, character)}


def unpriced(lines: list[Line], held: dict[TraitKey, int]) -> list[Priced]:
    """Each line with the rating it raises from, as the lines before it leave it."""
    held = dict(held)
    priced: list[Priced] = []
    for line in lines:
        from_rating = held.get(line.key, 0)
        priced.append(
            Priced(
                line=line,
                from_rating=from_rating,
                held=line.rating <= from_rating,
                next_step=line.key not in {p.line.key for p in priced if not p.held},
            )
        )
        held[line.key] = max(from_rating, line.rating)
    return priced


def for_pricing(change: cart.Change) -> cart.Change:
    """A cart line as it is priced: one with no teacher yet named gets the stand-in."""
    if isinstance(change, cart.SetRating) and not change.teacher and change.teacher_id is None:
        return replace(change, teacher=PRICING_TEACHER)
    return change


def price(
    db: Session, character: Character, lines: list[Line], in_cart: list[cart.Change] | None = None
) -> Pricing:
    """Each line priced by the cart, in order, as if the cart's changes and the lines
    before it were bought; unpriced if nothing may be written, such as for the
    custodian viewing as someone, as the cart prices by making the changes and taking
    them back, or for a retired character, which buys nothing."""
    saved = ratings(db, character)
    if read_only(db) or character.status == "retired":
        return Pricing(unpriced(lines, saved), priced=False)
    if not in_cart and all(p.held for p in unpriced(lines, saved)):
        return Pricing(unpriced(lines, saved))
    player = db.get_one(User, character.player_id)
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
        cart_cost = 0
        after_cart = saved
        if in_cart:
            # What the cart's changes spend is what they take from the XP; a refused
            # one is taken back, and spends nothing.
            before = sheets.xp_balance(db, character)
            cart.apply_changes(db, player, character, [for_pricing(c) for c in in_cart])
            db.flush()
            cart_cost = before - sheets.xp_balance(db, character)
            after_cart = ratings(db, character)
        priced = unpriced(lines, after_cart)
        wanted = [i for i, p in enumerate(priced) if not p.held]
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
        outcomes = cart.apply_changes(db, player, character, changes) if changes else []
    finally:
        savepoint.rollback()
        db.expire_all()
    for i, outcome in zip(wanted, outcomes, strict=True):
        priced[i] = replace(
            priced[i],
            cost=outcome.cost,
            refused=outcome.refused,
            needs_approval=outcome.needs_approval,
            because=outcome.because,
            teacher=outcome.teacher,
        )
    for i, p in enumerate(priced):
        if p.held and saved.get(p.line.key, 0) < p.line.rating <= after_cart.get(p.line.key, 0):
            priced[i] = replace(p, in_cart=True)
    return Pricing(priced, cart_cost)


def usual_award(db: Session, character: Character) -> Award | None:
    """What a game the character comes to usually brings it, by its home troupe's game
    XP (horatio.game_xp): the chart's figure for a game attended in the character's
    band of earned XP, or with no chart, the troupe's session XP; and its share of the
    downtime XP (`downtime_share`). Where the troupe caps awards at the monthly limit,
    the downtime XP counts toward it, and the game's figure shrinks to fit. Adjustments
    staff tick and absentee games are left out. None without a home troupe, or for
    nothing."""
    if character.home_troupe_id is None:
        return None
    troupe = db.get_one(Troupe, character.home_troupe_id)
    found = game_xp.settings(troupe)
    per_game, source = 0, ""
    if found.bands:
        band = game_xp.band_of(found, checkin.earned(db, [character.id])[character.id])
        if band is not None:
            per_game, source = band[1].attended, f"the troupe's chart, {band[0]} band"
    else:
        per_game, source = troupe.session_xp, "the troupe's session XP"
    downtime, downtime_source = downtime_share(db, troupe)
    if found.cap == "cap":
        per_game = min(per_game, max(0, math.floor(game_xp.monthly_limit(found) - downtime)))
    award = Award(per_game, source, downtime, downtime_source)
    return award if award.total > 0 else None


def downtime_share(db: Session, troupe: Troupe) -> tuple[Fraction, str | None]:
    """The downtime XP a game's worth of time usually brings, and how that was told:
    the XP for completing every downtime cycle the troupe has opened, over every game
    it has held, however long ago (a chronicle can run for years). With no games held,
    there is nothing to tell by, so the troupe's downtime XP setting, counting a cycle
    for each game. It counts the downtime as submitted, as an active character's
    usually is. Two counts on indexed columns, however many years of games there are."""
    games = db.scalar(
        select(func.count())
        .select_from(ScheduledGame)
        .where(ScheduledGame.troupe_id == troupe.id, ScheduledGame.ends_at <= checkin.now())
    )
    if not games:
        if troupe.downtime_xp <= 0:
            return Fraction(0), None
        return (
            Fraction(troupe.downtime_xp),
            f"the troupe's {troupe.downtime_xp} XP a downtime, counting a cycle a game",
        )
    cycles, xp = db.execute(
        select(func.count(), func.coalesce(func.sum(DowntimeCycle.completion_xp), 0)).where(
            DowntimeCycle.troupe_id == troupe.id, DowntimeCycle.opened_at.is_not(None)
        )
    ).one()
    if not xp:
        return Fraction(0), None
    return (
        Fraction(int(xp), games),
        f"{xp} XP from {plural(cycles, 'downtime cycle')}"
        f" over the troupe's {plural(games, 'game')} so far",
    )


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def games_away(short: int, award: Award | None) -> int | None:
    """Roughly how many games until `short` XP more is had, at the usual award."""
    if short <= 0:
        return 0
    if award is None:
        return None
    return math.ceil(short / award.total)


def visible_to(character: Character, user: User, plan: XpPlan | None) -> bool:
    """Its player sees it; anyone else who sees the sheet, only while it is shared."""
    return is_players(character, user) or (plan is not None and plan.shared)


def is_players(character: Character, user: User) -> bool:
    return character.kind == "pc" and character.player_id == user.id

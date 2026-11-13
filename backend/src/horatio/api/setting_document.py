"""The parts of a troupe's Setting Style Document built from its own settings (issue
#771), never typed twice: its setting and factions, how rare it rates clans, its
changes to costs, and the mechanics particular to it, the New Character Incentive
among them (MET: VTM pp. 331-336, 349). Each is read from what the troupe already
holds, so the document changes as the troupe's settings do. The parts staff write
are in horatio.setting_style."""

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import game_xp, xp_range
from horatio.api.book_traits import book_traits_out
from horatio.api.house_rules import (
    checks_out,
    clan_rarity_out,
    other_settings,
    own_checks,
    splat_house_rules,
)
from horatio.models import HouseTrait, Troupe
from horatio.rules.splats import SPLATS

# How a check the troupe plays differently holds, in a player's words (as the House
# rules tab has them).
PLAYED = {
    "refuse": "not allowed",
    "complete": "needed to finish character creation",
    "review": "allowed, for the storytellers to review",
    "note": "allowed, noted for the storytellers",
    "off": "does not apply",
}


class RarityChangeOut(BaseModel):
    """A clan the troupe rates itself: its rarity here, the book's in the troupe's
    setting (None when each character goes by its own sect's), and why."""

    clan: str
    rarity: str
    book: str | None
    note: str


class IncentiveOut(BaseModel):
    """The New Character Incentive in figures (p. 349): the starting XP, the most XP a
    character could have earned here, a quarter of it, and the two together."""

    base: int
    earned: int
    bonus: int
    total: int


class GeneratedOut(BaseModel):
    # The sects whose characters may join; empty for any. With one, its setting is the
    # chronicle's for everyone (`setting`); with several, each character is built by its
    # own sect's, as the book's crossover rules have factions do (p. 334).
    sects: list[str]
    setting: str | None
    # The clans the troupe rates itself, by clan.
    clan_rarity: list[RarityChangeOut]
    # Its changes to costs: prices, its own merits and flaws, and book traits it bans.
    costs: list[str]
    # What a new character built for it starts with, and the incentive behind it if on.
    initial_xp: int
    incentive: IncentiveOut | None
    # A game XP chart that gives less as a character earns more: the book's graduated
    # cap (p. 349), or one like it.
    graduated: bool
    # Its other setting-specific mechanics, in plain words: starting points, game XP,
    # the checks that limit character creation and its other house rules.
    mechanics: list[str]


def splats_of(troupe: Troupe) -> list[str]:
    return ["vampire", *(s for s in troupe.allowed_splats if s != "vampire" and s in SPLATS)]


def with_book(text: str, book: str | None) -> str:
    return f"{text} (the book: {book[0].lower()}{book[1:]})" if book else text


def rarity_changes(db: Session, troupe: Troupe) -> list[RarityChangeOut]:
    if not troupe.clan_rarity:
        return []
    found = clan_rarity_out(db, troupe)
    return [
        RarityChangeOut(
            clan=row.clan,
            rarity=row.house,
            book=row.book.get(found.setting) if found.setting else None,
            note=row.note,
        )
        for row in found.clans
        if row.house is not None
    ]


def cost_lines(db: Session, troupe: Troupe) -> list[str]:
    splats = splats_of(troupe)
    lines: list[str] = []
    for splat in splats:
        rules = splat_house_rules(db, troupe.id, splat)
        prefix = f"{rules.label}: " if len(splats) > 1 else ""
        lines += [
            prefix + with_book(f"{c.subject}: {c.price_text}", c.book_text) for c in rules.costs
        ]
    own = db.scalars(
        select(HouseTrait)
        .where(
            HouseTrait.troupe_id == troupe.id,
            HouseTrait.archived_at.is_(None),
            HouseTrait.availability == "building",
        )
        .order_by(HouseTrait.category.desc(), HouseTrait.name)
    ).all()
    for h in own:
        noun = "flaw" if h.category == "flaws" else "merit"
        lines.append(f"{h.name}: a {h.points}-point {noun} of the troupe's own")
    for b in book_traits_out(db, troupe):
        if b.banned:
            why = f": {b.ban_reason}" if b.ban_reason else ""
            lines.append(f"{b.name} is not used here{why}")
        elif b.kind:
            lines.append(with_book(f"{b.name}: {b.kind} here", b.book_kind))
    return lines


def mechanic_lines(db: Session, troupe: Troupe) -> list[str]:
    splats = splats_of(troupe)
    lines: list[str] = []
    for splat in splats:
        rules = splat_house_rules(db, troupe.id, splat)
        prefix = f"{rules.label}: " if len(splats) > 1 else ""
        lines += [
            prefix + with_book(f"{s.category}: {s.text}", s.book_text) for s in rules.starting
        ]
    lines += [c.rule for c in own_checks(db, troupe)]
    lines += [
        f"{c.message or c.about}: {PLAYED.get(c.house, c.house)}"
        for c in checks_out(db, troupe.id)
        if c.house
    ]
    lines += [
        with_book(f"{s.name}: {s.text}", s.book_text)
        for s in other_settings(db, troupe, rarity=False)
    ]
    return lines


def generated_out(db: Session, troupe: Troupe) -> GeneratedOut:
    found = xp_range.figures(db, troupe)
    incentive = xp_range.incentive(found)
    bands = game_xp.settings(troupe).bands
    return GeneratedOut(
        sects=list(troupe.allowed_sects),
        setting=troupe.allowed_sects[0] if len(troupe.allowed_sects) == 1 else None,
        clan_rarity=rarity_changes(db, troupe),
        costs=cost_lines(db, troupe),
        initial_xp=xp_range.new_character_xp(troupe, found),
        incentive=IncentiveOut(
            base=incentive.base,
            earned=incentive.earned,
            bonus=incentive.bonus,
            total=incentive.total,
        )
        if troupe.new_character_incentive
        else None,
        graduated=len(bands) > 1 and bands[-1].attended < bands[0].attended,
        mechanics=mechanic_lines(db, troupe),
    )

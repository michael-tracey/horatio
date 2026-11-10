"""Merits that give free traits the player chooses (Ventrue Royalty and five more).

A merit with a `free_choices` grant (horatio.rules.grants) is held with the
player's choices on its row (`CharacterTrait.choices`). The grants then give
what they name, as any free dots (`sheets.apply_grants`), and take it back with
the merit.

The player chooses when the merit is taken and can change the choices freely
until a home troupe has accepted the character with the merit on its sheet.
After that a change goes through staff (an exception asked of them, or given).
A merit taken after acceptance can still be chosen for once, as it was never
part of what staff accepted; once chosen it is fixed too.

Walking Atrocity (Vol. 2, p. 205) gives its dots as Morality falls: one for each
dot below 5, placed in the attributes. Those are never locked whole: a dot that
comes later is placed then. Once a home troupe has accepted the character, a dot
placed stays where it is, unless Morality rises and one must be given up.

An NPC's staff choose for it, at any time (#577): what Piece That Remains,
Auspicious, Old Habits or Shadows of the Past gives is free on it as on a
player's character, and goes to its player with it. Where an NPC's creation
picks are fitted, the fitting places Ventrue Royalty's dots instead
(horatio.npc_picks).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import npc_picks, sheets
from horatio.models import Character, SheetVersion
from horatio.rules.checks import matches
from horatio.rules.grants import (
    GrantData,
    Option,
    check_picks,
    dots_to_place,
    holds_source,
    options,
)
from horatio.rules.model import FreeChoice, SheetTrait


@dataclass(frozen=True)
class Offer:
    """One free_choices grant of a held merit: what can be chosen and what was."""

    grant: GrantData
    options: list[Option]
    picks: list[FreeChoice]
    # Why the player can no longer change the picks; None while they can.
    locked: str | None
    # For dots that follow a trait (Walking Atrocity's, from Morality): how many the
    # sheet gives now. None for any other grant.
    dots: int | None = None

    @property
    def category(self) -> str:
        return self.grant.target["category"]

    @property
    def placed(self) -> int:
        return sum(p.amount for p in self.picks)

    @property
    def complete(self) -> bool:
        """Whether the player has chosen all the grant gives: every place filled,
        or every pick of a count, or every dot placed; for a budget of points, any."""
        shape = self.grant.picks or {}
        if self.dots is not None:
            return self.placed == self.dots
        if "places" in shape:
            return len(self.picks) == len(shape["places"])
        if "count" in shape:
            return len(self.picks) == shape["count"]
        return bool(self.picks)


def accepted_keys(db: Session, character: Character) -> set[sheets.TraitKey]:
    """The traits on the sheet any home troupe accepted."""
    found: set[sheets.TraitKey] = set()
    for snapshot in db.scalars(
        select(SheetVersion.snapshot).where(SheetVersion.character_id == character.id)
    ):
        found |= {(t["category"], t["name"], t["detail"]) for t in snapshot if t["rating"]}
    return found


def locked_reason(
    db: Session, character: Character, row: sheets.SheetRow, grant: GrantData
) -> str | None:
    if character.kind != "pc":
        # Staff choose what an NPC's merit gives (Piece That Remains' clan merit,
        # #577), except where its creation picks are fitted and the fitting places
        # the merit's dots (Ventrue Royalty's 4, 3 and 2, horatio.npc_picks).
        if "places" in (grant.picks or {}) and npc_picks.fitted(character):
            return f"{row.definition.name}'s free dots are placed with the NPC's creation picks."
        return None
    if "below" in (grant.picks or {}):
        # New dots come as Morality falls; moving the placed ones is judged on saving.
        return None
    if sheets.ever_accepted(db, character) and (
        row.trait.choices or row.key in accepted_keys(db, character)
    ):
        return (
            f"{row.definition.name}'s free traits can't change once a home troupe has "
            "accepted the character. Ask staff."
        )
    return None


def grants_of(
    row: sheets.SheetRow, sheet: Sequence[SheetTrait], grants: Sequence[GrantData]
) -> list[GrantData]:
    """The free_choices grants this held trait has."""
    trait = row.as_rules_trait()
    return [
        g
        for g in grants
        if g.kind == "free_choices"
        and holds_source(trait, g.source)
        and (g.when is None or matches(g.when, sheet, trait))
    ]


def held_offers(db: Session, character: Character) -> list[tuple[sheets.SheetRow, list[Offer]]]:
    """Each held trait that lets the player choose free traits, with what it offers."""
    rules = sheets.rules_for(db, character)
    sources = {
        (g.source["category"], g.source["name"])
        for g in rules.rule_set.grants
        if g.kind == "free_choices"
    }
    rows = sheets.sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
    found: list[tuple[sheets.SheetRow, list[Offer]]] = []
    for row in rows:
        if (row.category.key, row.definition.name) not in sources:
            continue
        grants = grants_of(row, sheet, rules.rule_set.grants)
        if not grants:
            continue
        mine = row.as_rules_trait().choices
        found.append(
            (
                row,
                [
                    Offer(
                        grant=g,
                        options=options(g, rules.rule_set, sheet),
                        picks=[c for c in mine if c.grant == g.key],
                        locked=locked_reason(db, character, row, g),
                        dots=dots_to_place(g, sheet),
                    )
                    for g in grants
                ],
            )
        )
    return found


def offers(db: Session, character: Character, key: sheets.TraitKey) -> list[Offer]:
    """What the held trait lets the player choose, and what they have."""
    return next((o for row, o in held_offers(db, character) if row.key == key), [])


def unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def set_choices(
    db: Session,
    character: Character,
    category: str,
    name: str,
    detail: str,
    picks: Sequence[FreeChoice],
) -> None:
    """Replace the free traits the player chose for a held merit. The caller makes
    the change inside `sheets.checked`, which gives them and judges the sheet."""
    sheets.ensure_unlocked(db, character)
    key = (category, name, detail)
    if not any(r.key == key for r in sheets.sheet_rows(db, character)):
        raise unprocessable(f"The character does not hold {name}.")
    found = offers(db, character, key)
    if not found:
        raise unprocessable(f"{name} gives no free traits to choose.")
    if (reason := next((o.locked for o in found if o.locked), None)) is not None:
        raise sheets.conflict(reason)
    rules = sheets.rules_for(db, character)
    sheet = [r.as_rules_trait() for r in sheets.sheet_rows(db, character)]
    # The biggest placed first, as they read: 4, 3, 2. Others keep their order.
    cleaned = sorted(
        (FreeChoice(p.grant, p.name, p.detail.strip(), p.amount) for p in picks),
        key=lambda p: -p.amount,
    )
    for offer in found:
        mine = [p for p in cleaned if p.grant == offer.grant.key]
        message = check_picks(offer.grant, mine, rules.rule_set, sheet)
        if message:
            raise unprocessable(message)
        if (
            offer.dots is not None
            and character.kind == "pc"
            and sheets.ever_accepted(db, character)
        ):
            moved = _moves_placed(offer, mine, name)
            if moved:
                raise sheets.conflict(moved)
        for pick in mine:
            _check_troupe_options(db, character, offer.category, pick)
    stray = {p.grant for p in cleaned} - {o.grant.key for o in found}
    if stray:
        raise unprocessable(f"{name} has no such choice.")
    held = next(r for r in sheets.sheet_rows(db, character) if r.key == key)
    held.trait.choices = [
        {"grant": p.grant, "name": p.name, "detail": p.detail, "amount": p.amount} for p in cleaned
    ]
    db.flush()


def _moves_placed(offer: Offer, picks: Sequence[FreeChoice], name: str) -> str | None:
    """Once a home troupe has accepted the character, Walking Atrocity's placed dots
    stay put: new ones can be placed, and the dots placed beyond what Morality now
    gives can be given up, but no more (Vol. 2, p. 205)."""
    assert offer.dots is not None
    was = {p.name: p.amount for p in offer.picks}
    now = {p.name: p.amount for p in picks}
    taken_off = sum(max(amount - now.get(n, 0), 0) for n, amount in was.items())
    if taken_off <= max(offer.placed - offer.dots, 0):
        return None
    return (
        f"{name}'s placed dots can't move once a home troupe has accepted the character. Ask staff."
    )


def _check_troupe_options(
    db: Session, character: Character, category_key: str, pick: FreeChoice
) -> None:
    """A troupe's own list of specialisations applies to the free ones too."""
    from horatio.specializations import check_choice  # imports this module's neighbours

    _, category = sheets.find_definition(db, character, category_key, pick.name)
    check_choice(db, character, category, pick.name, pick.detail)


def preview(db: Session, character: Character, category: str, name: str) -> list[Offer]:
    """What the merit would let the player choose if the character took it now:
    no choices made, none locked. For the Add panel on the sheet."""
    rules = sheets.rules_for(db, character)
    sheet = [r.as_rules_trait() for r in sheets.sheet_rows(db, character)]
    return [
        Offer(
            grant=g,
            options=options(g, rules.rule_set, sheet),
            picks=[],
            locked=None,
            dots=dots_to_place(g, sheet),
        )
        for g in rules.rule_set.grants
        if g.kind == "free_choices" and (g.source["category"], g.source["name"]) == (category, name)
    ]

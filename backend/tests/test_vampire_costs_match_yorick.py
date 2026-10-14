"""Horatio's Vampire rule set prices every case exactly as Yorick did.

The reference data was produced by running Yorick's own cost engine
(client/src/domain/rules/BNSMETV1_VampireCosts.ts) over a grid of characters
and traits; see tools/yorick_oracle/. Each row is one trait on one character.
"""

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.pricing import NotAllowed, PricingError, trait_cost

FIXTURE = Path(__file__).parent / "fixtures" / "yorick_vampire_costs.json.gz"

# Yorick made a trait unaffordable by charging 9999 or 99999 XP a dot.
# Horatio says `not_allowed` instead.
YORICK_SENTINEL_RATE = 9999

# Yorick's engine priced a "humanity" category that no Vampire sheet has;
# Horatio has only "paths".
NOT_HORATIO_CATEGORIES = {"humanity"}


def load_cases() -> list[dict[str, Any]]:
    with gzip.open(FIXTURE, "rt") as f:
        data = json.load(f)
    return [dict(zip(data["columns"], row, strict=True)) for row in data["cases"]]


CASES = [c for c in load_cases() if c["category"] not in NOT_HORATIO_CATEGORIES]
RULES = TroupeRules(load_rule_set(DATA_DIR / "bns_met_vampire.toml"))


def horatio_trait(case: dict[str, Any]) -> SheetTrait:
    # Yorick kept a detail in the name: "Thaumaturgy: Path of Blood".
    name, _, detail = case["name"].partition(": ")
    return SheetTrait(
        category=case["category"],
        name=name,
        detail=detail,
        rating=case["value"],
        free_rating=case["free_value"],
    )


def horatio_sheet(case: dict[str, Any], trait: SheetTrait) -> list[SheetTrait]:
    sheet = [SheetTrait(category="clan", name=case["clan"]), trait]
    sheet += [
        SheetTrait(category="extra_in_clan_disciplines", name=name, rating=0)
        for name in case["extra_in_clan"]
    ]
    if case["generation"] is not None:
        sheet.append(
            SheetTrait(category="backgrounds", name="Generation", rating=case["generation"])
        )
    return sheet


def yorick_says_not_allowed(case: dict[str, Any]) -> bool:
    paid_dots = case["value"] - case["free_value"]
    return (
        case["cost"] is not None
        and paid_dots > 0
        and abs(case["cost"]) // paid_dots >= YORICK_SENTINEL_RATE
    )


def test_the_reference_data_covers_every_category() -> None:
    rated = {k for k, c in RULES.rule_set.categories.items() if c.rated}
    assert {c["category"] for c in CASES} >= rated
    assert len(CASES) > 10_000


def test_every_case_matches_yorick() -> None:
    mismatches: list[str] = []
    for case in CASES:
        trait = horatio_trait(case)
        sheet = horatio_sheet(case, trait)
        try:
            outcome: object = trait_cost(RULES, sheet, trait).cost
        except NotAllowed:
            outcome = "not allowed"
        except PricingError:
            outcome = "refused"

        if case["cost"] is None:
            expected: object = "refused"
        elif yorick_says_not_allowed(case):
            expected = "not allowed"
        else:
            expected = case["cost"]

        if outcome != expected:
            mismatches.append(f"{case}: Horatio {outcome!r}, Yorick {expected!r}")

    assert not mismatches, f"{len(mismatches)} mismatches, first: " + "\n".join(mismatches[:10])


@pytest.mark.parametrize(
    ("category", "name", "clan", "generation", "rating", "expected"),
    [
        # Readable spot checks of what the grid covers.
        ("disciplines", "Celerity", "Brujah", 3, 2, 9),  # in-clan: 3 + 6
        ("disciplines", "Celerity", "Tremere", 3, 2, 12),  # out-of-clan, gen < 5: 4 + 8
        ("disciplines", "Celerity", "Tremere", 5, 2, 15),  # out-of-clan, gen >= 5: 5 + 10
        ("backgrounds", "Generation", "Brujah", 3, 3, 11),  # 1 + 4 + 6
        ("skills", "Example", "Brujah", 1, 3, 6),  # generation 1: 1 + 2 + 3
        ("skills", "Example", "Brujah", 2, 3, 12),  # otherwise: 2 + 4 + 6
    ],
)
def test_spot_checks(
    category: str, name: str, clan: str, generation: int, rating: int, expected: int
) -> None:
    trait = SheetTrait(category=category, name=name, rating=rating)
    sheet = [
        SheetTrait(category="clan", name=clan),
        SheetTrait(category="backgrounds", name="Generation", rating=generation),
        trait,
    ]
    if name == "Generation":
        sheet = [SheetTrait(category="clan", name=clan), trait]

    assert trait_cost(RULES, sheet, trait).cost == expected

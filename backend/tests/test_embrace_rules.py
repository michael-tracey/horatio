"""The sums a ghoul's Embrace works with (MET: VTM pp. 100–101, 263, 297–299), and how
XP debt is paid off line by line."""

import pytest

from horatio.embrace import GENERATIONS, generation_cost, generation_number, ordinal
from horatio.xp_debt import Paid, owed, running, short_of


@pytest.mark.parametrize(
    ("dots", "flaws", "number"),
    [
        (1, [], 11),
        (1, ["Lesser Generation 1"], 12),
        (1, ["Lesser Generation 2"], 13),
        (2, [], 9),
        (2, ["Lesser Generation 1"], 10),
        (3, [], 8),
        (4, [], 7),
        (5, [], 6),
        (0, [], None),
        (1, ["Thin Blooded"], None),
    ],
)
def test_a_vampires_generation_from_its_sheet(dots: int, flaws: list[str], number: int) -> None:
    assert generation_number(dots, flaws) == number


def test_each_generation_is_its_dots_and_flaw_back_again() -> None:
    for number, (dots, flaw) in GENERATIONS.items():
        assert generation_number(dots, [flaw] if flaw else []) == number


def test_generation_at_a_backgrounds_price() -> None:
    # 1 × the level as a Neonate; 2 × the level a dot at any other Generation (p. 298).
    assert [generation_cost(d) for d in (1, 2, 3, 4, 5)] == [1, 6, 12, 20, 30]


def test_ordinals() -> None:
    assert [ordinal(n) for n in (6, 11, 12, 13, 21, 22)] == [
        "6th",
        "11th",
        "12th",
        "13th",
        "21st",
        "22nd",
    ]


def test_earned_xp_pays_the_debt_first() -> None:
    # Vivian: 30 creation XP spent, 9 owed at the Embrace, then 4 and 6 earned.
    assert running([30, -30, -9, 4, 6]) == [
        Paid(0, 0),
        Paid(0, 0),
        Paid(0, 9),
        Paid(4, 5),
        Paid(5, 0),
    ]
    assert owed(-9) == 9
    assert owed(3) == 0


def test_why_a_purchase_is_refused() -> None:
    assert short_of(-9, 3).startswith("The character owes 9 XP of debt.")
    assert short_of(2, 3) == "That costs 3 XP, and the character has 2."

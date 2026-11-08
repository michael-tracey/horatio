"""XP earned, spent and lost, from a character's XP entries (#548)."""

from horatio.sheets import earned_and_spent

START = ("award", 30, None)


def test_a_refund_lowers_spent_and_leaves_earned() -> None:
    bought = [START, ("purchase", -6, None)]
    refunded = [*bought, ("purchase", 6, None)]
    rebought = [*refunded, ("purchase", -6, None)]

    assert earned_and_spent(bought) == (30, 6, 0)
    assert earned_and_spent(refunded) == (30, 0, 0)
    assert earned_and_spent(rebought) == (30, 6, 0)


def test_a_flaw_taken_is_spending_going_down() -> None:
    assert earned_and_spent([START, ("purchase", 3, None)]) == (30, -3, 0)
    # Taken back by a diablerie, its XP is spending again.
    assert earned_and_spent([START, ("purchase", 3, None), ("correction", -3, "purchase")]) == (
        30,
        0,
        0,
    )


def test_a_settlement_counts_toward_spent_either_way() -> None:
    assert earned_and_spent([START, ("purchase", -6, None), ("settlement", -2, None)]) == (
        30,
        8,
        0,
    )
    assert earned_and_spent([START, ("purchase", -6, None), ("settlement", 6, None)]) == (
        30,
        0,
        0,
    )


def test_a_fee_is_spent() -> None:
    assert earned_and_spent([START, ("fee", -2, None)]) == (30, 2, 0)


def test_what_was_given_counts_toward_earned_either_way() -> None:
    entries = [
        START,
        ("self_entered", 10, None),
        ("correction", -4, "self_entered"),
        ("award", 5, None),
        ("correction", 2, "award"),
        ("cap", -8, None),
    ]

    assert earned_and_spent(entries) == (35, 0, 0)


def test_reprices_and_debt_are_spent_and_lost_xp_is_apart() -> None:
    entries = [
        START,
        ("purchase", -10, None),
        ("reprice", -2, None),
        ("debt", -5, None),
        ("debt", 1, None),
        ("lost", -7, None),
    ]

    assert earned_and_spent(entries) == (30, 16, 7)

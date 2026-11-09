"""A trait's dots under the grants its sheet holds (horatio.sheets.regrant): free
dots come first, and dots bought sit above them."""

from horatio.sheets import Regranted, regrant


def test_a_new_grant_makes_dots_bought_inside_it_free() -> None:
    # Resources 2 bought, then Ventrue Royalty places 4 there.
    assert regrant(2, 0, 0, 0, 4) == Regranted(4, 4, 4, made_free=2)


def test_a_new_grant_keeps_dots_bought_above_it() -> None:
    # Resources 5 bought, then a grant makes it free up to 4: the fifth stays bought.
    assert regrant(5, 0, 0, 0, 4) == Regranted(5, 4, 4, made_free=4)


def test_a_dot_bought_above_a_grant_stays_bought() -> None:
    """Resources 5 over Ventrue Royalty's 4 (#575): nothing is refunded and the
    rating stays 5."""
    assert regrant(5, 4, 4, 0, 4) == Regranted(5, 4, 4, made_free=0)


def test_a_grant_that_grows_makes_the_dots_bought_it_reaches_free() -> None:
    # Free up to 2, with dots 3 and 4 bought; now free up to 4.
    assert regrant(4, 2, 2, 0, 4) == Regranted(4, 4, 4, made_free=2)


def test_a_grant_that_shrinks_keeps_the_dots_bought() -> None:
    # Free up to 4 with the fifth bought; now free up to 2: the bought dot is kept.
    assert regrant(5, 4, 4, 0, 2) == Regranted(3, 2, 2, made_free=0)


def test_a_lost_grant_takes_its_dots_and_leaves_those_bought() -> None:
    assert regrant(5, 4, 4, 0, 0) == Regranted(1, 0, 0, made_free=0)
    assert regrant(4, 4, 4, 0, 0) == Regranted(0, 0, 0, made_free=0)


def test_free_dots_of_its_own_count_toward_the_grant() -> None:
    # A creation pick made the first dot free and the second was bought; the grant
    # gives the rest up to 4.
    assert regrant(2, 1, 0, 0, 4) == Regranted(4, 4, 3, made_free=1)


def test_added_dots_go_on_top() -> None:
    # Rugged's health level: one more, nothing made free.
    assert regrant(3, 0, 0, 1, 0) == Regranted(4, 1, 1, made_free=0)
    assert regrant(4, 1, 1, 1, 0) == Regranted(4, 1, 1, made_free=0)

"""Mantle of Sutekh (Vol. 2 pp. 239-240, issue #854): Blood tithed through it is kept
even past the pool while it lasts; when it ends, the Blood over the pool goes
without being spent."""

from horatio import play, reference
from horatio.models import PlayEvent
from horatio.reference import Owner, Sheet, _switch

NAME = "Serpentis: Mantle of Sutekh"


def mantle() -> tuple[reference.Switch, list[reference.PowerUse]]:
    entry = reference.catalogue().others[("luminary_disciplines", NAME)]
    sheet = Sheet(disciplines={"Serpentis": 5})
    return _switch(Owner(entry, NAME, "Serpentis"), entry["active"], sheet), reference.uses(
        entry, sheet
    )


def limits(power: reference.Switch) -> play.Limits:
    return play.Limits(
        generation=0,
        blood=10,
        blood_per_turn=1,
        starting_blood=10,
        willpower=5,
        health=(("Healthy", 3), ("Injured", 3), ("Incapacitated", 3)),
        morality=5,
        morality_name="Humanity",
        switches=(power,),
    )


def tap(tracker: str, amount: int) -> PlayEvent:
    return PlayEvent(kind="change", tracker=tracker, amount=amount)


def test_the_tithe_is_marked_to_go_past_the_pool() -> None:
    power, found = mantle()
    assert power.blood_over
    assert "Blood past the pool until it ends" in reference._changes(power, [], [])
    [tithe] = found
    assert tithe.over and tithe.when == "Mantle of Sutekh"
    assert [(g.tracker, g.amount) for g in tithe.gains] == [("blood", 1)]


def test_blood_is_kept_past_the_pool_until_it_ends() -> None:
    power, _ = mantle()
    found = limits(power)
    state = found.start()
    assert state["blood"] == 10
    # Without the Mantle on, Blood stops at the pool.
    assert play.apply(state, found, tap("blood", 1)) == (10, 10)
    play.apply(state, found, tap("power:Mantle of Sutekh", 1))
    assert found.blood_top(state["on"]) is None
    assert play.apply(state, found, tap("blood", 1)) == (10, 11)
    assert play.apply(state, found, tap("blood", 2)) == (11, 13)
    # Spending over the pool spends what is held, as any Blood.
    assert play.apply(state, found, tap("blood", -1)) == (13, 12)
    # Its end takes the Blood over the pool, unspent.
    play.apply(state, found, tap("power:Mantle of Sutekh", -1))
    assert state["blood"] == 10
    assert found.blood_top(state["on"]) == 10


def test_replaying_the_taps_gives_the_same() -> None:
    power, _ = mantle()
    found = limits(power)
    events = [tap("power:Mantle of Sutekh", 1), tap("blood", 3), tap("blood", -1)]
    assert play.replay(found, events).state["blood"] == 12
    events.append(tap("power:Mantle of Sutekh", -1))
    assert play.replay(found, events).state["blood"] == 10

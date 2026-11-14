"""Health levels and attribute points given up while a power is on, by an amount
chosen at use (issue #824): the shape Bonecraft (#813) needs, dry-run here on data
of its own rather than the powers file's."""

from typing import Any

from horatio import play, reference
from horatio.models import PlayEvent
from horatio.reference import Owner, Sheet, _changes, _switch, option_switches

# Bonecraft as #813 will have it (core pp. 168-169, Vol. 2 Issue 1 p. 61), in the
# shape this ticket builds: amounts chosen each use, levels given up, Blood added.
BONECRAFT: dict[str, Any] = {
    "key": "Bonecraft",
    "page": 168,
    # Kept until undone in #813 (issue #822); a plain switch here, so taps turn it on.
    "normal_form_only": True,
    "picks": {
        "count": 1,
        "focus_count": {"Manipulation": 2},
        "options": [
            {
                "name": "Tough",
                "amount": {"least": 1, "most": 3, "label": "Physical given up"},
                "attributes": [{"attribute": "Physical", "amount": -1, "scale": True}],
                "health": [{"level": "Healthy", "boxes": 1, "scale": True}],
            },
            {"name": "Extra Limbs", "health": [{"level": "Healthy", "boxes": -2}]},
            {
                "name": "Second Stomach",
                "page": 61,
                "book": "Vol. 2 Issue 1",
                "normal_form_only": False,
                "amount": {"most": 3, "label": "levels given up"},
                "health": [{"level": "Healthy", "boxes": -1, "scale": True}],
                "blood": {"extra": 2, "scale": True},
            },
        ],
    },
}


def bonecraft(focuses: frozenset[str] = frozenset()) -> reference.Switch:
    sheet = Sheet(focuses=set(focuses), disciplines={"Vicissitude": 3})
    return _switch(Owner({"name": "Bonecraft"}, "Bonecraft", "Vicissitude 3"), BONECRAFT, sheet)


def limits(power: reference.Switch, *others: reference.Switch) -> play.Limits:
    options = power.picks.options if power.picks else []
    return play.Limits(
        generation=0,
        blood=10,
        blood_per_turn=1,
        starting_blood=10,
        willpower=5,
        health=(("Healthy", 3), ("Injured", 3), ("Incapacitated", 3)),
        morality=5,
        morality_name="Humanity",
        switches=(power, *option_switches(power), *others),
        options={power.key: tuple(play.PickOption(o.name, "", None) for o in options)},
    )


def tap(tracker: str, amount: int, damage: str | None = None) -> PlayEvent:
    return PlayEvent(kind="change", tracker=tracker, amount=amount, damage=damage)


def test_an_option_with_an_amount_is_one_option_for_each_amount() -> None:
    """Tough's 1 to 3 Physical given up for as many Healthy levels (core p. 168):
    "Tough: 2" gives -2 Physical and +2 Healthy; Second Stomach's levels given up add
    2 Blood each (Vol. 2 Issue 1 p. 61)."""
    power = bonecraft()
    assert power.picks is not None
    names = [o.name for o in power.picks.options]
    assert names == [
        "Tough: 1",
        "Tough: 2",
        "Tough: 3",
        "Extra Limbs",
        "Second Stomach: 1",
        "Second Stomach: 2",
        "Second Stomach: 3",
    ]
    tough = power.picks.options[1]
    assert (tough.base, tough.amount, tough.amount_label) == ("Tough", 2, "Physical given up")
    assert tough.key == "Bonecraft/Tough: 2"
    assert [(a.attribute, a.amount) for a in tough.attributes] == [("Physical", -2)]
    assert [(h.level, h.boxes) for h in tough.health] == [("Healthy", 2)]
    limbs = power.picks.options[3]
    assert (limbs.base, limbs.amount) == (None, None)
    stomach = power.picks.options[6]
    assert [(h.level, h.boxes) for h in stomach.health] == [("Healthy", -3)]
    assert stomach.blood_extra == 6
    assert stomach.page == "Vol. 2 Issue 1, p. 61"

    found = {s.key: s for s in option_switches(power)}
    assert _changes(found["Bonecraft/Tough: 2"], [], []) == ["-2 Physical", "+2 Healthy"]
    assert _changes(found["Bonecraft/Extra Limbs"], [], []) == ["-2 Healthy given up"]
    assert _changes(found["Bonecraft/Second Stomach: 3"], [], []) == [
        "-3 Healthy given up",
        "+6 most Blood",
    ]
    # Second Stomach stays in a form; the rest are the normal form's only.
    assert not found["Bonecraft/Second Stomach: 1"].normal_form_only
    assert found["Bonecraft/Tough: 1"].normal_form_only


def test_levels_given_up_come_off_the_sheets_own_and_back_when_it_ends() -> None:
    power = bonecraft()
    found = limits(power)
    assert len(found.boxes()) == 9
    on = ["Bonecraft", "Bonecraft/Extra Limbs"]
    boxes = found.boxes(on)
    assert len(boxes) == 7
    assert boxes[:1] == [None]  # Healthy: 3 less 2
    on = ["Bonecraft", "Bonecraft/Tough: 2"]
    assert len(found.boxes(on)) == 11
    assert found.boxes(on).count("Bonecraft/Tough: 2") == 2
    # Never fewer than none in a category: Second Stomach gives up all 3 Healthy.
    on = ["Bonecraft", "Bonecraft/Second Stomach: 3"]
    assert len(found.boxes(on)) == 6
    assert found.blood_most(on) == 16
    assert found.most("health", on) == 6


def test_picking_another_amount_replaces_the_first_and_damage_stays() -> None:
    """One choice of an option at a time; damage marked stays when levels are given
    up, and the levels come back when the power ends (core p. 169)."""
    found = limits(bonecraft())
    state = found.start()
    said: list[str] = []
    assert play.apply(state, found, tap("power:Bonecraft", 1), said) is not None
    play.apply(state, found, tap("health", 2, "normal"), said)
    play.apply(state, found, tap("pick:Bonecraft/Tough: 1", 1), said)
    assert state["picked"]["Bonecraft"] == ["Tough: 1"]
    said = []
    assert play.apply(state, found, tap("pick:Bonecraft/Tough: 3", 1), said) == (0, 1)
    assert state["picked"]["Bonecraft"] == ["Tough: 3"]
    assert "in place of Tough: 1" in said
    assert "Bonecraft/Tough: 1" not in state["on"]
    assert "Bonecraft/Tough: 3" in state["on"]
    assert found.most("health", state["on"]) == 12

    # Extra Limbs in Tough's place (one pick at a time): two Healthy given up.
    play.apply(state, found, tap("pick:Bonecraft/Extra Limbs", 1), [])
    assert state["picked"]["Bonecraft"] == ["Extra Limbs"]
    assert found.most("health", state["on"]) == 7
    assert state["health"] == ["normal", "normal"]
    play.apply(state, found, tap("power:Bonecraft", -1), [])
    assert found.most("health", state["on"]) == 9
    assert state["health"] == ["normal", "normal"]


def test_blood_past_a_given_up_option_goes_when_it_is_dropped() -> None:
    found = limits(bonecraft(frozenset({"Manipulation"})))
    state = found.start()
    play.apply(state, found, tap("power:Bonecraft", 1), [])
    play.apply(state, found, tap("pick:Bonecraft/Second Stomach: 2", 1), [])
    assert found.blood_most(state["on"]) == 14
    play.apply(state, found, tap("blood", 4), [])
    assert state["blood"] == 14
    # With the Manipulation focus, two options at once: Tough beside Second Stomach.
    play.apply(state, found, tap("pick:Bonecraft/Tough: 1", 1), [])
    assert state["picked"]["Bonecraft"] == ["Second Stomach: 2", "Tough: 1"]
    play.apply(state, found, tap("pick:Bonecraft/Second Stomach: 2", -1), [])
    assert state["blood"] == 10

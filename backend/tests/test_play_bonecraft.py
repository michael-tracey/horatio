"""Bonecraft on the Play View (issue #813, core pp. 168-169): each use picks a
modification, two with the Manipulation focus, on yourself or on another character
of the home troupe; Bonecraft Prodigy (Vol. 2 Issue 1 p. 61) and Virtuoso del
Corpo (Vol. 2 p. 248) add options; Tzimisce: Scar Tissue (Vol. 2 p. 278) rules the
beneficial ones out on the flawed character's own body; and with Ravenous
Conglomeration (Vol. 2 p. 249) it is kept with a form, as one of its two."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import play, reference
from horatio.models import PlayEffect
from horatio.reference import Sheet, option_switches, switch_for, work_out
from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_play import send, tap, view
from tests.test_api_play_powers import give, on
from tests.test_api_sheets import make_home_troupe_member

PRODIGY = ("techniques", "Bonecraft Prodigy")
VIRTUOSO = ("elder_disciplines", "Vicissitude: Virtuoso Del Corpo")
SCAR_TISSUE = ("flaws", "Tzimisce: Scar Tissue")
CORE = ["Extra Limbs", "Tough", "Transformed Biology", "Crippled", "Body Weaponry"]
PRODIGY_OPTIONS = ["Defensive Quills", "Deformed", "Elongated Gait", "Second Stomach"]


def bonecraft(*traits: tuple[str, str], focuses: frozenset[str] = frozenset()) -> Any:
    ratings = {("attributes", "Physical"): 5, **{t: 1 for t in traits}}
    sheet = Sheet(ratings=ratings, focuses=set(focuses), disciplines={"Vicissitude": 3})
    return {s.key: s for s in work_out(sheet, {}).switches}


def names(switch: reference.Switch) -> list[str]:
    assert switch.picks is not None
    return list(dict.fromkeys(o.base or o.name for o in switch.picks.options))


def test_bonecraft_is_kept_in_the_normal_form_and_offers_the_core_modifications() -> None:
    found = bonecraft()
    power = found["Bonecraft"]
    assert (power.kept, power.normal_form_only, power.counts_as_form) == (True, True, True)
    assert power.target == "any" and power.page == "p. 168"
    assert power.picks is not None and power.picks.count == 1
    assert names(power) == CORE
    targets = {o.base or o.name: o.target for o in power.picks.options}
    assert targets["Crippled"] == "other" and targets["Tough"] == "any"
    assert {o.name: o.page for o in power.picks.options}["Crippled"] == "p. 169"

    # Tough: 1 to 3 Physical given up for as many Healthy levels (core p. 168).
    tough = found["Bonecraft/Tough: 3"]
    assert [(a.attribute, a.amount) for a in tough.attributes] == [("Physical", -3)]
    assert [(h.level, h.boxes) for h in tough.health] == [("Healthy", 3)]
    assert [(h.level, h.boxes) for h in found["Bonecraft/Extra Limbs"].health] == [("Healthy", -2)]
    assert [(h.level, h.boxes) for h in found["Bonecraft/Body Weaponry"].health] == [
        ("Healthy", -1)
    ]


def test_the_manipulation_focus_gives_two_and_traits_add_their_options() -> None:
    power = bonecraft(PRODIGY, VIRTUOSO, focuses=frozenset({"Manipulation"}))["Bonecraft"]
    assert power.picks is not None and power.picks.count == 2
    assert names(power)[: len(CORE) + 4] == CORE + PRODIGY_OPTIONS
    assert names(power)[len(CORE) + 4 :] == [
        "Bauble",
        "Chiropteran Marauder",
        "Kraken's Kiss",
        "Living Weapon",
        "Simplified",
        "Skin Trap",
        "Skittering Legs",
    ]
    pages = {o.base or o.name: o.page for o in power.picks.options}
    assert pages["Second Stomach"] == "Vol. 2 Issue 1, p. 61"
    assert pages["Skin Trap"] == "Vol. 2, p. 248"


def test_second_stomach_adds_blood_and_stays_in_any_form() -> None:
    stomach = bonecraft(PRODIGY)["Bonecraft/Second Stomach: 2"]
    assert [(h.level, h.boxes) for h in stomach.health] == [("Healthy", -2)]
    assert stomach.blood_extra == 4
    assert not stomach.normal_form_only


def test_deformed_takes_up_to_three_social_and_none_at_all() -> None:
    found = bonecraft(PRODIGY)
    assert [(a.attribute, a.amount) for a in found["Bonecraft/Deformed: 3"].attributes] == [
        ("Social", -3)
    ]
    assert [a.amount for a in found["Bonecraft/Deformed: 0"].attributes] == [0]


def test_scar_tissue_leaves_the_beneficial_ones_for_others_only() -> None:
    power = bonecraft(PRODIGY, VIRTUOSO, SCAR_TISSUE)["Bonecraft"]
    assert power.picks is not None
    targets = {o.base or o.name: o.target for o in power.picks.options}
    # The flawed body can't take them, but the Tzimisce can still give them to others.
    assert targets["Tough"] == targets["Extra Limbs"] == targets["Second Stomach"] == "other"
    assert targets["Crippled"] == "other"
    # Living Weapon is the user's own body only, so it goes.
    assert "Living Weapon" not in targets


def test_another_body_takes_every_option_but_what_its_own_scars_rule_out() -> None:
    every = {s.key for s in switch_for("Bonecraft")}
    assert {"Bonecraft/Second Stomach: 1", "Bonecraft/Skin Trap", "Bonecraft/Crippled"} <= every
    scarred = Sheet(ratings={SCAR_TISSUE: 1})
    kept = {s.key for s in switch_for("Bonecraft", scarred)}
    assert "Bonecraft/Crippled" in kept and "Bonecraft/Deformed: 2" in kept
    assert "Bonecraft/Tough: 1" not in kept and "Bonecraft/Skin Trap" not in kept


def limits(power: reference.Switch, forms: int) -> play.Limits:
    form = reference.Switch(key="Horrid Form", name="Horrid Form", origin="", page="", form=True)
    return play.Limits(
        generation=0,
        blood=10,
        blood_per_turn=1,
        starting_blood=10,
        willpower=5,
        health=(("Healthy", 3), ("Injured", 3), ("Incapacitated", 3)),
        morality=5,
        morality_name="Humanity",
        switches=(power, *option_switches(power), form),
        forms=forms,
    )


def test_ravenous_conglomeration_keeps_it_with_a_form() -> None:
    power = bonecraft()["Bonecraft"]
    on = ["Bonecraft", "Bonecraft/Extra Limbs", "Horrid Form"]
    # Alone, a form pauses it (core pp. 168-169): the two levels come back.
    one = limits(power, forms=1)
    assert one.paused(on) == {"Bonecraft", "Bonecraft/Extra Limbs"}
    assert one.boxes(on).count(None) == 9
    # With Ravenous Conglomeration it is kept with the form, as one of its two
    # (Vol. 2 p. 249): its levels stay given up, and one form is left.
    two = limits(power, forms=2)
    assert two.paused(on) == set()
    assert two.boxes(on).count(None) == 7
    assert two.forms_now(on) == 1


# --- On the Play View ---------------------------------------------------------------


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def second(client_for: Callable[[], TestClient]) -> Person:
    return sign_up(client_for, "second")


@pytest.fixture
def ilsa(troupe: Troupe, session: Session) -> str:
    """A bonecrafter (Vicissitude 3, Bonecraft Prodigy), at home in the troupe."""
    character_id = new_character(troupe, troupe.player, "Ilsa")
    give(session, character_id, "disciplines", "Vicissitude", 3)
    give(session, character_id, *PRODIGY, 1)
    make_home_troupe_member(session, troupe, character_id)
    return character_id


@pytest.fixture
def oren(troupe: Troupe, second: Person, session: Session) -> str:
    """Another player's character, at home in the troupe."""
    character_id = new_character(troupe, second, "Oren")
    make_home_troupe_member(session, troupe, character_id)
    return character_id


def picked(state: dict[str, Any]) -> list[str]:
    """What is picked for Bonecraft on this Play View."""
    [power] = [p for p in state["powers"] if p["key"] == "Bonecraft"]
    return list(power["picked"]) if power["on"] else []


def crafted(oren: str, *options: str, at: int = 1) -> dict[str, Any]:
    return {
        **tap("blood", 0, at=at),
        "kind": "note",
        "tracker": "",
        "amount": 0,
        "note": "Bonecraft on Oren",
        "on_other": {
            "character_id": oren,
            "power": "Bonecraft",
            "switch": "Bonecraft",
            "use": None,
            "options": list(options),
        },
    }


def test_on_yourself_tough_gives_physical_for_healthy_levels(troupe: Troupe, ilsa: str) -> None:
    [power] = [p for p in view(troupe.player, ilsa)["powers"] if p["key"] == "Bonecraft"]
    # Crippled and Deformed are for others only (core p. 169, Vol. 2 Issue 1 p. 61).
    offered = [o["name"] for o in power["options"]]
    assert "Crippled" not in offered and not any(n.startswith("Deformed") for n in offered)
    assert "Tough: 2" in offered and "Second Stomach: 1" in offered

    state = send(
        troupe.player,
        ilsa,
        tap("power:Bonecraft", 1),
        tap("pick:Bonecraft/Tough: 2", 1, at=1),
    )
    assert picked(state) == ["Tough: 2"]

    # Crippled isn't picked on yourself, whatever the tap says.
    after = send(troupe.player, ilsa, tap("pick:Bonecraft/Crippled", 1, at=2))
    assert picked(after) == ["Tough: 2"]


def test_used_on_another_it_counts_on_their_play_view(
    troupe: Troupe, ilsa: str, oren: str, second: Person, session: Session
) -> None:
    state = send(troupe.player, ilsa, tap("blood", -1), crafted(oren, "Second Stomach: 2"))
    assert state["log"][0]["text"] == "Used Bonecraft: remade (Second Stomach: 2) on Oren"
    theirs = view(second, oren)
    assert "Bonecraft" in on(theirs) and picked(theirs) == ["Second Stomach: 2"]
    [effect] = theirs["effects"]
    assert effect["source_character_name"] == "Ilsa"

    # Crippled is for another: it goes on them too, in place of the last (one at a time).
    send(troupe.player, ilsa, crafted(oren, "Crippled", at=2))
    assert picked(view(second, oren)) == ["Crippled"]
    assert len(session.scalars(select(PlayEffect).where(PlayEffect.ended_at.is_(None))).all()) == 1


def test_scar_tissue_bars_beneficial_alterations_and_one_option_counts_once(
    troupe: Troupe, ilsa: str, oren: str, second: Person, session: Session
) -> None:
    give(session, oren, *SCAR_TISSUE, None)
    session.commit()
    state = send(troupe.player, ilsa, crafted(oren, "Tough: 2"))
    assert state["log"][0]["text"] == (
        "Couldn't use Bonecraft on Oren: Oren's body can't take Tough: 2."
    )
    # A harmful one still works on them.
    send(troupe.player, ilsa, crafted(oren, "Crippled", at=2))
    assert picked(view(second, oren)) == ["Crippled"]


def test_the_same_modification_cant_be_picked_twice(
    troupe: Troupe, ilsa: str, oren: str, session: Session
) -> None:
    give(session, ilsa, "focus_socials", "Manipulation", None)
    session.commit()
    state = send(troupe.player, ilsa, crafted(oren, "Tough: 1", "Tough: 2"))
    assert "same modification" in state["log"][0]["text"]
    assert session.scalars(select(PlayEffect)).all() == []

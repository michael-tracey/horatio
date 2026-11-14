"""Powers' charges, points and stacks on the Play View (issue #826): a tracker of
their own, "charge:<key>", built and spent by a power's uses, at none as each game
starts, and let go with a tap when the book says they fade."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import play, reference
from horatio.models import PlayEvent
from horatio.reference import CHARGE, Sheet, catalogue, counters_of, pools, work_out
from tests.api_helpers import Troupe, new_character
from tests.test_api_play import send, tap, texts, view
from tests.test_api_play_powers import give

KINETICISM = CHARGE + "Kineticism"


def kineticist(dots: int, *techniques: str) -> Sheet:
    return Sheet(
        ratings={
            ("attributes", "Physical"): 3,
            ("skills", "Brawl"): 2,
            **{("techniques", t): 1 for t in techniques},
        },
        disciplines={"Kineticism": dots, "Potence": 2, "Fortitude": 2},
        others=[("techniques", "Techniques", t) for t in techniques],
    )


BASES = {
    "Kinetic Wave": {"Kineticism", "Potence"},
    "Wall of Force": {"Kineticism", "Fortitude"},
    "Ensnaring Force": {"Kineticism", "Celerity"},
}


def counter(sheet: Sheet, key: str) -> reference.Counter:
    return next(c for c in counters_of(sheet, BASES) if c.key == CHARGE + key)


def limits(*charges: reference.Counter) -> play.Limits:
    return play.Limits(
        generation=0,
        blood=10,
        blood_per_turn=1,
        starting_blood=10,
        willpower=5,
        health=(("Healthy", 3), ("Injured", 3), ("Incapacitated", 3)),
        morality=5,
        morality_name="Humanity",
        charges=charges,
    )


def change(tracker: str, amount: int) -> PlayEvent:
    return PlayEvent(kind="change", tracker=tracker, amount=amount)


def test_kineticism_holds_a_charge_a_power_and_technique() -> None:
    """Vol. 2 p. 72: as many charges as Kineticism dots and Kineticism techniques."""
    assert counter(kineticist(1), "Kineticism").most == 1
    assert counter(kineticist(3, "Kinetic Wave", "Wall of Force"), "Kineticism").most == 5
    found = counter(kineticist(2), "Kineticism")
    assert (found.discipline, found.unit, found.units) == ("Kineticism", "charge", "charges")
    assert [(f.label, f.keep) for f in found.fades] == [
        ("Fight over", 0),
        ("Going into a fight", 1),
    ]


def test_a_counter_shows_only_for_a_character_that_has_its_power() -> None:
    """Reaper's Due's stack needs the path's third power; Rayzeel's Grace the elder
    power itself."""
    low = Sheet(disciplines={"Necromancy: Path of the Graveborn": 2})
    high = Sheet(disciplines={"Necromancy: Path of the Graveborn": 3})
    assert [c.key for c in counters_of(low, {})] == []
    assert [c.key for c in counters_of(high, {})] == [CHARGE + "Reaper's Due"]
    obeah = Sheet(
        ratings={("elder_disciplines", "Obeah: Rayzeel's Grace"): 1},
        disciplines={"Obeah": 5},
        others=[("elder_disciplines", "Elder Disciplines", "Obeah: Rayzeel's Grace")],
    )
    grace = next(c for c in counters_of(obeah, {}) if c.key == CHARGE + "Rayzeel's Grace")
    # Vol. 2 p. 219: one for each Obeah power, its elder power too.
    assert (grace.most, grace.other, grace.unit) == (6, "Obeah: Rayzeel's Grace", "Grace")
    assert [c.key for c in counters_of(Sheet(disciplines={"Obeah": 5}), {})] == []


def test_charges_start_at_none_and_stay_within_their_most() -> None:
    found = limits(counter(kineticist(2), "Kineticism"))
    state = found.start()
    assert state["uses"][KINETICISM] == 0
    assert play.apply(state, found, change(KINETICISM, 1)) == (0, 1)
    assert play.apply(state, found, change(KINETICISM, 3)) == (1, 2)
    assert play.apply(state, found, change(KINETICISM, -5)) == (2, 0)
    assert found.name(KINETICISM) == "Kineticism charges"
    assert play.known_tracker(KINETICISM)
    # A sheet without the counter has no such tracker: its taps change nothing.
    assert play.apply(limits().start(), limits(), change(KINETICISM, 1)) is None


def test_every_game_starts_the_charges_again() -> None:
    """Vol. 2 p. 72: charges don't outlast a fight; nothing carries them through Reset."""
    assert not play.carries(KINETICISM)


def test_reapers_due_counts_its_stack_against_the_mark() -> None:
    """Vol. 2 p. 118: +1 wild card against the mark for each Willpower they spend or
    lose near you, up to 5: a line under attacks while the mark is on, which the Play
    View counts from the stack."""
    sheet = Sheet(
        ratings={("attributes", "Physical"): 3, ("skills", "Brawl"): 2},
        disciplines={"Necromancy: Path of the Graveborn": 3},
    )
    worked = work_out(sheet, {})
    brawl = next(
        p
        for p in pools(sheet, worked.effects, worked.hurts, worked.switches)
        if p.key == "attack:Brawl"
    )
    mark = next(v for v in brawl.variants if v.switch == "Reaper's Due")
    assert mark.when.lower() == "against your mark"
    assert [t.model_dump() for t in mark.tracked] == [
        {"label": "Reaper's Due", "tracks": "charge:Reaper's Due"}
    ]
    assert counter(sheet, "Reaper's Due").most == 5


def test_uses_build_and_spend_charges() -> None:
    """Accumulate stores a charge, Vengeful Strike spends as many as the player says
    (Vol. 2 pp. 73, 75), Rayzeel's Grace fills its Grace (p. 219)."""
    book = catalogue()
    sheet = kineticist(5)
    accumulate = reference.uses(book.power("Kineticism", "Accumulate") or {}, sheet)
    assert [
        (u.label, u.charges and u.charges.gain, u.charges and u.charges.spend) for u in accumulate
    ] == [
        ("Store a charge", 1, 0),
        ("3 more steps", 0, 1),
    ]
    strike = reference.uses(book.power("Kineticism", "Vengeful Strike") or {}, sheet)
    assert strike[0].charges is not None and strike[0].charges.more
    # The exceptional success gains 1, or 2 with Intelligence.
    assert [u.charges.gain for u in strike[1:] if u.charges] == [1]
    smart = reference.uses(
        book.power("Kineticism", "Vengeful Strike") or {}, Sheet(focuses={"Intelligence"})
    )
    assert [u.charges.gain for u in smart[1:] if u.charges] == [2]
    grace = reference.uses(book.others[("elder_disciplines", "Obeah: Rayzeel's Grace")], Sheet())
    assert grace[0].charges is not None and grace[0].charges.fill
    assert grace[0].cost == reference.Cost(tracker="blood", amount=2)
    assert [u.target for u in grace] == ["self", "self", "self", "other"]


def test_every_counter_and_charge_use_hangs_together() -> None:
    """Each counter belongs to something the file has, says where it is from and how
    it fades; each use's counter is one of them."""
    book = catalogue()
    keys = {c["key"] for c in book.counters}
    assert keys >= {"Kineticism", "Rayzeel's Grace", "Reaper's Due", "Water Mastery"}
    for c in book.counters:
        assert c["name"] and c.get("page") and c.get("fades"), c["key"]
        if "discipline" in c:
            assert c["discipline"] in book.disciplines, c["key"]
            if "power" in c:
                assert book.power(c["discipline"], c["power"]) is not None, c["key"]
        else:
            assert any(name == c["other"] for _, name in book.others), c["key"]
        for f in c["fades"]:
            assert f["label"] and f.get("keep", 0) >= 0, c["key"]
            if "off" in f:
                assert f["off"] in book.switch_keys, c["key"]
    entries = [*(p for ps in book.powers.values() for p in ps), *book.others.values()]
    for e in entries:
        for u in e.get("use", []):
            if "charges" in u:
                assert u["charges"]["counter"] in keys, (e["name"], u["label"])
            if "on" in u:
                assert u["on"] in book.switch_keys, (e["name"], u["label"])


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def test_the_play_view_keeps_kineticism_charges(troupe: Troupe, session: Session) -> None:
    """A Kineticism 2 character's Play View has its charges, at none, most 2; taps
    store and spend them within that, the log names them, and Reset empties them."""
    character_id = new_character(troupe, troupe.player, "Kinetica")
    give(session, character_id, "disciplines", "Kineticism", 2)
    state = view(troupe.player, character_id)
    [charges] = state["charges"]
    assert (charges["key"], charges["value"], charges["most"]) == (KINETICISM, 0, 2)
    assert (charges["discipline"], charges["unit"]) == ("Kineticism", "charge")

    state = send(
        troupe.player,
        character_id,
        tap(KINETICISM, 1),
        tap(KINETICISM, 1, at=1),
        tap(KINETICISM, 1, at=2),
    )
    assert state["charges"][0]["value"] == 2
    assert texts(state)[0] == "Kineticism charges 2 → 2"
    state = send(troupe.player, character_id, tap(KINETICISM, -1, at=3))
    assert state["charges"][0]["value"] == 1

    state = troupe.player.client.post(f"/characters/{character_id}/play/reset", json={}).json()
    assert state["charges"][0]["value"] == 0

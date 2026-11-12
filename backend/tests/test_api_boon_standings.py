"""Boon standings through the API (#691): only the troupe's running staff read them,
only while it keeps a ledger; its staff set what each kind weighs; and a troupe's own
characters bring their clan and titles into the sums."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_boons import Ledger


def at_home(troupe: Troupe, player: Person, name: str, clan: str) -> str:
    """A Camarilla character of `clan`, accepted at home in `troupe`."""
    character_id = new_character(troupe, player, name, clan=clan)
    joined = player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "sect", "name": "Camarilla", "rating": None},
    )
    assert joined.status_code == 200, joined.text
    asked = player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert asked.status_code == 201, asked.text
    approved = troupe.lead.client.post(f"/approvals/{asked.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    return character_id


@pytest.fixture
def ledger(client_for: Callable[[], TestClient], session: Session) -> Ledger:
    return Ledger(Troupe(client_for, session))


def standings(ledger: Ledger, by: Person | None = None, **query: Any) -> Any:
    found = (by or ledger.troupe.storyteller).client.get(
        f"/troupes/{ledger.troupe.id}/boon-standings", params=query
    )
    assert found.status_code == 200, found.text
    return found.json()


def net_of(found: Any, name: str) -> float:
    return next(c["net"] for c in found["characters"] if c["who"]["name"] == name)


def test_only_running_staff_read_the_standings_and_only_while_the_ledger_is_on(
    ledger: Ledger,
) -> None:
    troupe = ledger.troupe
    path = f"/troupes/{troupe.id}/boon-standings"
    for person in (troupe.lead, troupe.storyteller, troupe.assistant):
        assert person.client.get(path).status_code == 200
    for person in (troupe.narrator, troupe.player):
        assert person.client.get(path).status_code == 403

    assert ledger.switch(False).status_code == 200

    assert troupe.storyteller.client.get(path).status_code == 404


def test_standings_show_each_party_s_net_by_the_default_weights(ledger: Ledger) -> None:
    ledger.one(ledger.agnes, ledger.bram, kind="major")
    ledger.one(ledger.bram, ledger.agnes)
    ledger.one({"name": "The Moon"}, ledger.agnes, kind="trivial")

    found = standings(ledger)

    assert net_of(found, "Bram") == 2.0
    assert net_of(found, "Agnes") == -1.5
    assert found["totals"]["open"] == 3
    assert found["totals"]["name_only"] == 1
    assert found["weights"] == {
        "trivial": 0.5,
        "minor": 1.0,
        "major": 3.0,
        "blood": 5.0,
        "life": 10.0,
        "defaults": True,
    }
    assert [(m["first"]["name"], m["owes"], m["back"]) for m in found["mutual"]] == [
        ("Agnes", 3.0, 1.0)
    ]


def test_staff_set_what_each_kind_weighs_and_the_sums_follow(ledger: Ledger) -> None:
    ledger.one(ledger.agnes, ledger.bram, kind="major")
    path = f"/troupes/{ledger.troupe.id}/boon-weights"
    weights = {"trivial": 0.5, "minor": 1, "major": 4, "blood": 5, "life": 10}

    refused = ledger.troupe.player.client.put(path, json=weights)
    zero = ledger.troupe.assistant.client.put(path, json={**weights, "minor": 0})
    changed = ledger.troupe.assistant.client.put(path, json=weights)

    assert refused.status_code == 403
    assert zero.status_code == 422
    assert changed.status_code == 200, changed.text
    assert changed.json()["major"] == 4.0
    assert changed.json()["defaults"] is False
    assert net_of(standings(ledger), "Bram") == 4.0
    assert any("Major 3 → 4" in m for m in ledger.messages())

    back = ledger.troupe.assistant.client.put(path, json={**weights, "major": 3})

    assert back.json()["defaults"] is True


def test_clans_and_the_court_come_from_the_troupe_s_own_characters(ledger: Ledger) -> None:
    troupe = ledger.troupe
    vera = at_home(troupe, troupe.player, "Vera", "Ventrue")
    hal = at_home(troupe, ledger.other, "Hal", "Toreador")
    given = troupe.assistant.client.put(
        f"/troupes/{troupe.id}/characters/{vera}/titles", json={"titles": ["Prince"]}
    )
    assert given.status_code == 200, given.text
    ledger.one(hal, vera, kind="major")

    found = standings(ledger)

    [prince] = found["court"]
    assert prince["title"] == "Prince"
    assert prince["standing"]["who"]["name"] == "Vera"
    assert [(t["who"]["name"], t["weight"]) for t in prince["owe_them"]] == [("Hal", 3.0)]
    clans = {g["label"]: g for g in found["clans"]}
    assert (clans["Ventrue"]["owed"], clans["Toreador"]["owes"]) == (3.0, 3.0)
    assert found["across_clans"]["pairs"] == [
        {"label": "Toreador ↔ Ventrue", "count": 1, "weight": 3.0}
    ]


def test_active_leaves_out_boons_with_someone_dead_and_everyone_keeps_them(
    ledger: Ledger,
) -> None:
    ledger.one(ledger.bram, ledger.agnes, kind="life")
    gone = ledger.other.client.post(
        f"/characters/{ledger.bram}/retire", json={"reason": "final_death", "listed": False}
    )
    assert gone.status_code < 300, gone.text

    active = standings(ledger)
    everyone = standings(ledger, scope="everyone")

    assert active["characters"] == []
    assert active["totals"]["departed"] == 1
    assert net_of(everyone, "Agnes") == 10.0


def test_the_weights_travel_with_the_troupe_s_settings(ledger: Ledger) -> None:
    path = f"/troupes/{ledger.troupe.id}/boon-weights"
    weights = {"trivial": 1, "minor": 2, "major": 3, "blood": 5, "life": 10}
    assert ledger.troupe.storyteller.client.put(path, json=weights).status_code == 200

    exported = ledger.troupe.lead.client.get(f"/troupes/{ledger.troupe.id}/settings-share")

    assert exported.status_code == 200, exported.text
    settings = [
        i
        for i in exported.json()["document"]["sections"]["at_game"]
        if i.get("key") == "boon_weights"
    ]
    assert settings == [
        {"type": "setting", "key": "boon_weights", "value": {"trivial": 1.0, "minor": 2.0}}
    ]

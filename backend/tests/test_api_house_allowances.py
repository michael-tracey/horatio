"""Troupes change downtime allowances: the base each character gets, and what
traits add or take away. A cycle keeps the allowances it was opened with."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_downtimes import member_character, my_downtime, new_cycle, open_cycle

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def allowances(troupe: Troupe, person: Person | None = None) -> dict[str, Any]:
    response = (person or troupe.storyteller).client.get(f"/troupes/{troupe.id}/allowances")
    assert response.status_code == 200, response.text
    return response.json()


def add(troupe: Troupe, person: Person | None = None, **rule: Any) -> Any:
    return (person or troupe.storyteller).client.post(f"/troupes/{troupe.id}/allowances", json=rule)


def general(troupe: Troupe, character_id: str) -> int:
    return my_downtime(troupe.player, character_id).json()["allowance"]["general"]


def test_the_rule_sets_allowances_in_plain_words(troupe: Troupe) -> None:
    listed = allowances(troupe, troupe.assistant)

    shown = {(r["who"], r["amount_text"]) for r in listed["rules"]}
    assert ("Everyone", "3 downtime actions") in shown
    assert ("Hunted", "−2 downtime actions") in shown
    assert ("Influences: The Elite", "+1 elite influence action per dot") in shown
    assert "general" in [k["key"] for k in listed["action_kinds"]]
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/allowances").status_code == 403


def test_a_new_cycle_uses_the_troupes_allowances(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")

    assert add(troupe, troupe.assistant, action_kind="general", amount=4).status_code == 403
    added = add(troupe, action_kind="general", amount=4)

    assert added.status_code == 201, added.text
    assert (added.json()["who"], added.json()["amount_text"]) == ("Everyone", "4 downtime actions")
    replaced = [r for r in allowances(troupe)["rules"] if r["replaced"]]
    assert [(r["who"], r["amount"]) for r in replaced] == [("Everyone", 3)]
    open_cycle(troupe, new_cycle(troupe))
    assert general(troupe, agnes) == 4
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller set the troupe's downtime actions for Everyone: 4 downtime actions." in log


def test_an_open_cycle_keeps_its_allowances(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))

    add(troupe, action_kind="general", amount=5)

    assert general(troupe, agnes) == 3


def test_traits_that_change_the_allowance(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    troupe.player.client.put(
        f"/characters/{agnes}/traits", json={"category": "flaws", "name": "Hunted", "rating": 4}
    )
    hunted = add(troupe, action_kind="general", category="flaws", trait="Hunted", amount=-1)
    resources = add(
        troupe, action_kind="general", category="backgrounds", trait="Resources", amount=1
    )
    troupe.player.client.put(
        f"/characters/{agnes}/traits",
        json={"category": "backgrounds", "name": "Resources", "rating": 1},
    )

    assert hunted.status_code == 201, hunted.text
    assert resources.status_code == 201, resources.text
    open_cycle(troupe, new_cycle(troupe))
    assert general(troupe, agnes) == 3  # 3 − 1 for Hunted + 1 for Resources


def test_changing_and_removing_a_rule(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    rule = add(troupe, action_kind="general", amount=4).json()
    url = f"/troupes/{troupe.id}/allowances/{rule['id']}"

    assert troupe.assistant.client.put(url, json={"amount": 6}).status_code == 403
    changed = troupe.storyteller.client.put(url, json={"amount": 6})
    assert changed.status_code == 200, changed.text
    assert changed.json()["amount_text"] == "6 downtime actions"

    assert troupe.storyteller.client.delete(url).status_code == 204
    assert troupe.storyteller.client.delete(url).status_code == 404
    open_cycle(troupe, new_cycle(troupe))
    assert general(troupe, agnes) == 3


def test_rules_that_could_not_apply_are_refused(troupe: Troupe) -> None:
    assert add(troupe, action_kind="feeding", amount=1).status_code == 422
    assert add(troupe, action_kind="general", category="flaws", amount=1).status_code == 422
    assert (
        add(troupe, action_kind="general", category="flaws", trait="Juggling", amount=1).status_code
        == 422
    )
    assert add(troupe, action_kind="general", amount=1, min_rating=0).status_code == 422
    assert add(troupe, action_kind="general", amount=2).status_code == 201
    assert add(troupe, action_kind="general", amount=2).status_code == 409

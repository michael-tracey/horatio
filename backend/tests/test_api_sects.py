"""Sects: a faction only for the Sabbat, and troupes that take only some sects."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def choose(person: Person, character_id: str, category: str, name: str) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": None},
    )


def chosen(person: Person, character_id: str) -> dict[str, str]:
    sheet = person.client.get(f"/characters/{character_id}/sheet").json()
    return {t["category"]: t["name"] for t in sheet["traits"] if t["rating"] is None}


def limit(troupe: Troupe, person: Person, sects: list[str]) -> Any:
    return person.client.patch(f"/troupes/{troupe.id}", json={"allowed_sects": sects})


# --- faction ----------------------------------------------------------------------------------


def test_only_the_sabbat_have_a_faction(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert choose(troupe.player, character_id, "faction", "Orthodox").status_code == 422
    choose(troupe.player, character_id, "sect", "Camarilla")
    assert choose(troupe.player, character_id, "faction", "Orthodox").status_code == 422

    choose(troupe.player, character_id, "sect", "Sabbat")
    assert choose(troupe.player, character_id, "faction", "Orthodox").status_code == 200
    assert chosen(troupe.player, character_id) == {"sect": "Sabbat", "faction": "Orthodox"}


def test_leaving_the_sabbat_drops_the_faction(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    choose(troupe.player, character_id, "sect", "Sabbat")
    choose(troupe.player, character_id, "faction", "Loyalist")

    choose(troupe.player, character_id, "sect", "Anarch")

    assert chosen(troupe.player, character_id) == {"sect": "Anarch"}


def test_npc_factions_follow_the_same_rule(troupe: Troupe) -> None:
    npc = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs", json={"name": "Bishop Moreau"}
    ).json()["id"]

    def rate(category: str, name: str) -> int:
        return troupe.storyteller.client.put(
            f"/characters/{npc}/npc/ratings",
            json={"category": category, "name": name, "rating": None},
        ).status_code

    assert rate("faction", "Ultra-Conservative") == 422
    assert (rate("sect", "Sabbat"), rate("faction", "Ultra-Conservative")) == (200, 200)
    rate("sect", "Inconnu")
    assert chosen(troupe.storyteller, npc) == {"sect": "Inconnu"}


def test_the_catalogue_says_faction_needs_the_sabbat(troupe: Troupe) -> None:
    categories = troupe.player.client.get("/rules/vampire").json()["categories"]

    faction = next(c for c in categories if c["key"] == "faction")
    assert faction["requires"] == {"category": "sect", "name": "Sabbat"}


# --- which sects a troupe takes ---------------------------------------------------------------


def test_storytellers_choose_which_sects_may_join(troupe: Troupe) -> None:
    assert limit(troupe, troupe.assistant, ["Camarilla"]).status_code == 403
    assert limit(troupe, troupe.storyteller, ["Atlantean"]).status_code == 422

    changed = limit(troupe, troupe.storyteller, ["Camarilla", "Anarch", "Camarilla"])

    assert changed.json()["allowed_sects"] == ["Anarch", "Camarilla"]
    assert troupe.player.client.get(f"/troupes/{troupe.id}").json()["allowed_sects"] == [
        "Anarch",
        "Camarilla",
    ]
    messages = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert messages[0] == "storyteller set which sects may join: Anarch, Camarilla."


def test_pcs_of_other_sects_cannot_join(troupe: Troupe) -> None:
    limit(troupe, troupe.lead, ["Camarilla"])
    sabbat = new_character(troupe, troupe.player, "Sabbat")
    choose(troupe.player, sabbat, "sect", "Sabbat")
    nobody = new_character(troupe, troupe.player, "Unsure")
    camarilla = new_character(troupe, troupe.player, "Camarilla")
    choose(troupe.player, camarilla, "sect", "Camarilla")

    def join(character_id: str) -> Any:
        return troupe.player.client.post(
            f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id}
        )

    refused = join(sabbat)
    assert refused.status_code == 409
    assert refused.json()["detail"].endswith("does not take Sabbat characters.")
    assert join(nobody).status_code == 409
    assert join(camarilla).status_code == 201
    home = troupe.player.client.post(
        f"/characters/{sabbat}/home-troupe", json={"troupe_id": troupe.id, "settlements": []}
    )
    assert home.status_code == 409


def test_any_sect_may_join_when_none_are_ticked(troupe: Troupe) -> None:
    limit(troupe, troupe.lead, ["Camarilla"])
    limit(troupe, troupe.lead, [])
    character_id = new_character(troupe, troupe.player)

    joined = troupe.player.client.post(
        f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id}
    )

    assert joined.status_code == 201


def test_npcs_are_not_limited_by_sect(troupe: Troupe) -> None:
    limit(troupe, troupe.lead, ["Camarilla"])

    made = troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Anarch"})

    assert made.status_code == 201

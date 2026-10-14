"""NPCs, which troupes make and keep, and titles, which troupes give."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import XpEntry
from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def make_npc(troupe: Troupe, name: str = "Prince Vasquez", wizard: bool = False) -> dict[str, Any]:
    response = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs", json={"name": name, "wizard": wizard}
    )
    assert response.status_code == 201, response.text
    return response.json()


def rate(person: Person, npc_id: str, category: str, name: str, rating: int | None) -> Any:
    return person.client.put(
        f"/characters/{npc_id}/npc/ratings",
        json={"category": category, "name": name, "rating": rating},
    )


def member(troupe: Troupe, name: str = "Agnes") -> str:
    character_id = new_character(troupe, troupe.player, name)
    troupe.player.client.post(f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id})
    return character_id


# --- NPCs ---------------------------------------------------------------------------------------


def test_running_staff_make_npcs_for_their_troupe(troupe: Troupe) -> None:
    for person in (troupe.narrator, troupe.player):
        assert (
            person.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "x"}).status_code == 403
        )

    npc = make_npc(troupe)

    assert (npc["kind"], npc["owner_troupe_id"], npc["creation_complete"]) == (
        "npc",
        troupe.id,
        True,
    )
    roster = troupe.assistant.client.get(f"/troupes/{troupe.id}/characters").json()
    assert [(r["character_name"], r["kind"], r["standing"], r["player_name"]) for r in roster] == [
        ("Prince Vasquez", "npc", "approved", "NPC")
    ]
    # Not in the maker's own vault.
    assert troupe.storyteller.client.get("/characters").json() == []


def test_setting_npc_ratings_directly_keeps_a_running_tally(
    troupe: Troupe, session: Session
) -> None:
    npc = make_npc(troupe)["id"]
    rate(troupe.storyteller, npc, "clan", "Brujah", None)
    rate(troupe.storyteller, npc, "attributes", "Physical", 6)
    rate(troupe.storyteller, npc, "skills", "Brawl", 3)

    tally = rate(troupe.assistant, npc, "disciplines", "Celerity", 2).json()

    # Physical 6 x 3, Brawl 1 + 2 + 3, in-clan Celerity 3 + 6; starting traits are free.
    assert tally["total"] == 18 + 6 + 9
    assert {(line["name"], line["cost"]) for line in tally["lines"]} >= {
        ("Physical", 18),
        ("Brawl", 6),
        ("Celerity", 9),
        ("Willpower", 0),
    }
    assert session.scalars(select(XpEntry)).all() == []
    # Lowering and removing are just as direct.
    assert rate(troupe.storyteller, npc, "skills", "Brawl", 0).json()["total"] == 18 + 9


def test_npc_ratings_are_still_checked_against_the_catalogue(troupe: Troupe) -> None:
    npc = make_npc(troupe)["id"]

    assert rate(troupe.storyteller, npc, "skills", "Juggling", 1).status_code == 422
    assert rate(troupe.storyteller, npc, "skills", "Brawl", 11).status_code == 422
    assert rate(troupe.storyteller, npc, "merits", "Acute Sense", 3).status_code == 422


def test_npcs_spend_no_xp_need_no_approval_and_stay_home(troupe: Troupe) -> None:
    npc = make_npc(troupe)["id"]
    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Elsewhere", "lead_email": troupe.storyteller.email}
    ).json()["id"]
    client = troupe.storyteller.client

    bought = client.put(
        f"/characters/{npc}/traits", json={"category": "skills", "name": "Brawl", "rating": 1}
    )
    assert bought.status_code == 409
    assert client.post(f"/characters/{npc}/approval", json={}).status_code == 409
    assert client.post(f"/characters/{npc}/troupes", json={"troupe_id": other}).status_code == 409
    assert client.delete(f"/characters/{npc}/troupes/{troupe.id}").status_code == 409


def test_narrators_and_players_never_see_npc_sheets(troupe: Troupe) -> None:
    npc = make_npc(troupe)["id"]

    assert troupe.assistant.client.get(f"/characters/{npc}/sheet").status_code == 200
    for person in (troupe.narrator, troupe.player):
        assert person.client.get(f"/characters/{npc}/sheet").status_code == 404
        assert rate(person, npc, "skills", "Brawl", 1).status_code == 404


def test_npcs_can_be_built_with_the_wizard(troupe: Troupe) -> None:
    npc = make_npc(troupe, wizard=True)

    assert npc["creation_complete"] is False
    picked = troupe.storyteller.client.put(
        f"/characters/{npc['id']}/creation/picks",
        json={"category": "attributes", "name": "Physical", "rating": 7},
    )
    assert picked.status_code == 200


def test_npcs_take_no_part_in_downtimes(troupe: Troupe) -> None:
    make_npc(troupe)
    now = datetime.now(UTC)
    cycle = troupe.lead.client.post(
        f"/troupes/{troupe.id}/cycles",
        json={
            "name": "November",
            "closes_at": (now + timedelta(days=7)).isoformat(),
            "grace_ends_at": (now + timedelta(days=9)).isoformat(),
        },
    ).json()

    troupe.lead.client.post(f"/cycles/{cycle['id']}/open")

    assert troupe.lead.client.get(f"/cycles/{cycle['id']}/participants").json() == []


def test_staff_delete_npcs_whenever_they_like(troupe: Troupe) -> None:
    npc = make_npc(troupe)["id"]

    assert troupe.narrator.client.delete(f"/characters/{npc}").status_code == 404
    assert troupe.assistant.client.delete(f"/characters/{npc}").status_code == 204

    assert troupe.assistant.client.get(f"/troupes/{troupe.id}/npcs").json() == []
    messages = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert messages[:2] == [
        "assistant deleted the NPC Prince Vasquez.",
        "storyteller made an NPC, Prince Vasquez.",
    ]


# --- titles ---------------------------------------------------------------------------------------


def test_a_troupes_titles_are_the_catalogues_plus_its_own(troupe: Troupe) -> None:
    path = f"/troupes/{troupe.id}/titles"

    added = troupe.assistant.client.post(path, json={"name": "Keeper of the Gate"})
    assert added.status_code == 201
    assert "Prince" in added.json()["catalogue"]
    assert added.json()["troupe"] == ["Keeper of the Gate"]
    assert troupe.assistant.client.post(path, json={"name": "Prince"}).status_code == 409
    assert troupe.narrator.client.get(path).status_code == 403

    removed = troupe.assistant.client.delete(f"{path}/Keeper of the Gate")
    assert removed.json()["troupe"] == []


def test_titles_are_given_in_one_troupe_and_mean_nothing_elsewhere(troupe: Troupe) -> None:
    character_id = member(troupe)
    path = f"/troupes/{troupe.id}/characters/{character_id}/titles"

    given = troupe.assistant.client.put(path, json={"titles": ["Primogen", "Harpy"]})

    assert given.json() == {"titles": ["Harpy", "Primogen"]}
    sheet = troupe.player.client.get(f"/characters/{character_id}/sheet").json()
    assert sheet["standings"][0]["titles"] == ["Harpy", "Primogen"]
    roster = troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()
    assert roster[0]["titles"] == ["Harpy", "Primogen"]
    printed = troupe.player.client.get(f"/characters/{character_id}/print").json()
    assert printed["titles"] == ["Harpy", "Primogen"]
    messages = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "assistant gave Agnes the title Primogen." in messages


def test_titles_must_exist_and_go_to_members(troupe: Troupe) -> None:
    character_id = member(troupe)
    outsider = new_character(troupe, troupe.player, "Outsider")

    unknown = troupe.assistant.client.put(
        f"/troupes/{troupe.id}/characters/{character_id}/titles", json={"titles": ["Emperor"]}
    )
    not_member = troupe.assistant.client.put(
        f"/troupes/{troupe.id}/characters/{outsider}/titles", json={"titles": ["Prince"]}
    )
    narrator = troupe.narrator.client.put(
        f"/troupes/{troupe.id}/characters/{character_id}/titles", json={"titles": ["Prince"]}
    )

    assert (unknown.status_code, not_member.status_code, narrator.status_code) == (422, 409, 403)


def test_leaving_a_troupe_leaves_its_titles(troupe: Troupe) -> None:
    character_id = member(troupe)
    troupe.assistant.client.put(
        f"/troupes/{troupe.id}/characters/{character_id}/titles", json={"titles": ["Prince"]}
    )

    troupe.player.client.delete(f"/characters/{character_id}/troupes/{troupe.id}")
    troupe.player.client.post(f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id})

    roster = troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()
    assert roster[0]["titles"] == []


def test_title_and_antecedence_are_not_player_choices_any_more(troupe: Troupe) -> None:
    catalogue = troupe.player.client.get("/rules/vampire").json()

    assert not {"title", "antecedence"} & {c["key"] for c in catalogue["categories"]}

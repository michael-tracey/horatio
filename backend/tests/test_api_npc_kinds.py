"""NPCs of every kind, sheeted or Stock (issue #215; MET: VTM pp. 489–505)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe

ANGEL = {
    "name": "Angel",
    "nature": "supernatural",
    "resource": {"name": "Grace", "size": 7, "per_turn": 2, "regains": "1 at dawn"},
}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def make(troupe: Troupe, person: Person | None = None, **body: Any) -> Any:
    person = person or troupe.storyteller
    return person.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Nemian", **body})


def made(troupe: Troupe, **body: Any) -> dict[str, Any]:
    response = make(troupe, **body)
    assert response.status_code == 201, response.text
    return response.json()


def stock(person: Person, npc_id: str, **body: Any) -> Any:
    return person.client.put(f"/characters/{npc_id}/npc/stock", json=body)


def specs(*names: str) -> list[dict[str, str]]:
    """Specializations: "Brawl" a skill, "+Potence" a discipline, path or numina."""
    return [
        {"type": "power", "name": n[1:]} if n.startswith("+") else {"type": "skill", "name": n}
        for n in names
    ]


def test_npc_kinds_come_from_the_rules_data(troupe: Troupe) -> None:
    kinds = {k["key"]: k for k in troupe.player.client.get("/npc-kinds").json()}

    werewolf = kinds["werewolf"]
    assert (werewolf["nature"], werewolf["page"], werewolf["health_per_rating"]) == (
        "supernatural",
        494,
        2,
    )
    assert werewolf["resource"] == {
        "name": "Rage",
        "size": 10,
        "per_turn": 3,
        "regains": "1 every five turns",
    }
    assert "Obeah" in werewolf["specializations"] and not werewolf["any_discipline"]
    assert kinds["vampire"]["any_discipline"]
    assert kinds["hunter_inquisition"]["numina"][0]["name"] == "True Faith"
    assert kinds["blood_brother"]["rating_max"] == 20
    assert kinds["custom"]["custom"]


def test_an_npc_made_as_before_is_a_sheeted_vampire(troupe: Troupe) -> None:
    npc = made(troupe)

    assert (npc["npc_kind"], npc["npc_kind_name"], npc["npc_form"], npc["splat"]) == (
        "vampire",
        "Vampire",
        "sheeted",
        "vampire",
    )
    listed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/npcs").json()
    assert [(n["name"], n["stock_rating"]) for n in listed] == [("Nemian", None)]


def test_a_sheeted_mage_is_built_on_the_vampire_rules(troupe: Troupe) -> None:
    npc = made(troupe, name="Sarah Juniper", npc_kind="mage")

    assert (npc["npc_kind_name"], npc["npc_form"], npc["splat"]) == ("Mage", "sheeted", "vampire")
    # It has a sheet, with its starting traits, and its ratings can be set.
    rated = troupe.storyteller.client.put(
        f"/characters/{npc['id']}/npc/ratings",
        json={"category": "skills", "name": "Occult", "rating": 3},
    )
    assert rated.status_code == 200, rated.text
    # Not a Stock NPC.
    assert troupe.storyteller.client.get(f"/characters/{npc['id']}/npc/stock").status_code == 409


@pytest.mark.usefixtures("ghoul_rules")
def test_a_ghoul_npc_is_built_on_the_ghoul_rules(troupe: Troupe) -> None:
    assert made(troupe, npc_kind="ghoul")["splat"] == "ghoul"
    assert made(troupe, name="Old way", splat="ghoul")["npc_kind"] == "ghoul"


def test_a_stock_werewolf_has_the_books_stat_block(troupe: Troupe) -> None:
    # Joseph "Bites-the-Hand" Timmeson, rating 3 (p. 495).
    npc = made(
        troupe,
        name="Joseph Timmeson",
        npc_kind="werewolf",
        npc_form="stock",
        stock={"rating": 3, "specializations": specs("Brawl", "Dodge", "+Celerity")},
    )
    assert (npc["npc_kind_name"], npc["npc_form"], npc["creation_complete"]) == (
        "Werewolf",
        "stock",
        True,
    )

    body = troupe.assistant.client.get(f"/characters/{npc['id']}/npc/stock").json()

    assert body["rating"] == 3
    stats = body["stats"]
    assert stats["pool"] == 6
    assert stats["skill_pools"] == [{"name": "Brawl", "pool": 11}, {"name": "Dodge", "pool": 11}]
    assert stats["powers"] == [{"name": "Celerity", "dots": 3}]
    assert [p["name"] for p in stats["built_in"]] == [
        "Feral Claws",
        "Shape of the Beast: fight form",
        "Shape of the Beast's Wrath",
    ]
    assert stats["health"] == 6
    assert stats["resource"]["name"] == "Rage"
    assert (stats["willpower"], stats["retests"]) == (0, False)
    assert any("Willpower" in r for r in stats["rules"])
    listed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/npcs").json()
    assert [(n["name"], n["npc_form"], n["stock_rating"]) for n in listed] == [
        ("Joseph Timmeson", "stock", 3)
    ]


def test_a_stock_npc_is_changed_as_the_rules_allow(troupe: Troupe) -> None:
    npc_id = made(troupe, npc_kind="mortal", npc_form="stock")["id"]
    st = troupe.storyteller

    body = stock(st, npc_id, npc_kind="mortal", rating=3, specializations=specs("Brawl")).json()
    assert body["stats"]["pool"] == 6
    assert body["stats"]["resource"] == {"name": "Blood", "size": 5, "per_turn": 0, "regains": ""}

    refused = stock(st, npc_id, npc_kind="mortal", rating=3, specializations=specs("+Potence"))
    assert refused.status_code == 422
    assert "skill specialisations only" in refused.json()["detail"]
    too_many = stock(
        st, npc_id, npc_kind="mortal", rating=1, specializations=specs("Brawl", "Dodge")
    )
    assert too_many.status_code == 422
    assert stock(st, npc_id, npc_kind="vampire", rating=6).status_code == 422
    assert stock(st, npc_id, npc_kind="nothing", rating=1).status_code == 422

    # Made a ghoul, it can take Potence, to its rating, and spend its 5 Blood.
    body = stock(
        st,
        npc_id,
        npc_kind="ghoul",
        rating=3,
        specializations=specs("Brawl", "+Potence"),
        notes="Tends bar at the Rack.",
    ).json()
    assert body["stats"]["powers"] == [{"name": "Potence", "dots": 3}]
    assert body["stats"]["resource"]["per_turn"] == 1
    assert body["notes"] == "Tends bar at the Rack."
    assert troupe.storyteller.client.get(f"/characters/{npc_id}").json()["splat"] == "ghoul"


def test_a_stock_npc_has_no_sheet(troupe: Troupe) -> None:
    assert make(troupe, npc_form="stock", wizard=True).status_code == 422
    npc_id = made(troupe, npc_form="stock")["id"]

    rated = troupe.storyteller.client.put(
        f"/characters/{npc_id}/npc/ratings",
        json={"category": "skills", "name": "Brawl", "rating": 3},
    )

    assert rated.status_code == 409
    assert troupe.storyteller.client.get(f"/characters/{npc_id}/sheet").json()["traits"] == []
    # A sheeted NPC has no Stock rating to give.
    assert make(troupe, stock={"rating": 2}).status_code == 422


def test_a_custom_kind_is_named_and_set_up_by_staff(troupe: Troupe) -> None:
    assert make(troupe, npc_kind="custom").status_code == 422
    assert make(troupe, npc_kind="mage", custom_kind=ANGEL).status_code == 422

    npc = made(
        troupe,
        npc_kind="custom",
        custom_kind=ANGEL,
        npc_form="stock",
        stock={"rating": 2, "specializations": specs("+Presence")},
    )

    assert npc["npc_kind_name"] == "Angel"
    body = troupe.storyteller.client.get(f"/characters/{npc['id']}/npc/stock").json()
    assert body["custom_kind"] == ANGEL
    assert body["kind"]["name"] == "Angel"
    assert body["stats"]["resource"] == ANGEL["resource"]
    assert body["stats"]["powers"] == [{"name": "Presence", "dots": 2}]
    # A mortal custom kind takes skills only.
    hermit = {**ANGEL, "name": "Hermit", "nature": "mortal"}
    refused = stock(
        troupe.storyteller,
        npc["id"],
        npc_kind="custom",
        custom_kind=hermit,
        rating=2,
        specializations=specs("+Presence"),
    )
    assert refused.status_code == 422


def test_only_running_staff_make_and_change_stock_npcs(troupe: Troupe) -> None:
    for person in (troupe.narrator, troupe.player):
        assert make(troupe, person, npc_form="stock").status_code == 403
    npc_id = made(troupe, npc_form="stock")["id"]
    for person in (troupe.narrator, troupe.player):
        assert stock(person, npc_id, npc_kind="vampire", rating=2).status_code in (403, 404)
        assert person.client.get(f"/characters/{npc_id}/npc/stock").status_code in (403, 404)

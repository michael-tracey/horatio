"""A Stock NPC made a full sheet, and sheeted NPCs of other kinds (issue #215, part 4)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe
from tests.test_api_npc_kinds import made, specs
from tests.test_api_play import send, tap, view


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def sheet(troupe: Troupe, npc_id: str) -> dict[tuple[str, str], int]:
    body = troupe.storyteller.client.get(f"/characters/{npc_id}/sheet").json()
    return {(t["category"], t["name"]): t["rating"] for t in body["traits"]}


def convert(troupe: Troupe, npc_id: str) -> Any:
    return troupe.storyteller.client.post(f"/characters/{npc_id}/npc/sheeted")


def test_a_stock_werewolf_becomes_a_sheeted_one_from_its_rating(troupe: Troupe) -> None:
    npc = made(
        troupe,
        name="Joseph Timmeson",
        npc_kind="werewolf",
        npc_form="stock",
        stock={"rating": 3, "specializations": specs("Brawl", "+Celerity"), "notes": "Wary."},
    )

    response = convert(troupe, npc["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["character"]["npc_kind"], body["character"]["npc_form"]) == ("werewolf", "sheeted")
    assert body["character"]["name"] == "Joseph Timmeson"
    # Feral Claws and the rest have no trait in the Vampire rules.
    assert "Feral Claws" in body["left_out"]
    ratings = sheet(troupe, npc["id"])
    assert ratings[("skills", "Brawl")] == 3
    assert ratings[("disciplines", "Celerity")] == 3
    # Each attribute is the pool: rating × 2.
    assert [ratings[("attributes", a)] for a in ("Physical", "Social", "Mental")] == [6, 6, 6]
    # No Humanity for a werewolf.
    assert ("paths", "Humanity") not in ratings
    # It is a sheeted NPC now: no Stock NPC, and no way back.
    assert troupe.storyteller.client.get(f"/characters/{npc['id']}/npc/stock").status_code == 409
    assert convert(troupe, npc["id"]).status_code == 409
    listed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/npcs").json()
    assert [(n["npc_form"], n["stock_rating"]) for n in listed] == [("sheeted", None)]


def test_the_conversion_is_logged_in_the_character_and_troupe_logs(troupe: Troupe) -> None:
    npc = made(
        troupe,
        npc_kind="mortal",
        npc_form="stock",
        stock={"rating": 2, "specializations": specs("Streetwise"), "notes": "Owes money."},
    )
    convert(troupe, npc["id"])

    mine = troupe.storyteller.client.get(f"/characters/{npc['id']}/log").json()
    theirs = troupe.storyteller.client.get(f"/troupes/{troupe.id}/log").json()

    for log in (mine, theirs):
        found = [e["message"] for e in log if e["action"] == "npc.made_sheeted"]
        assert len(found) == 1
        assert "made the Stock NPC Nemian a full sheet" in found[0]
        assert "Owes money." in found[0]


def test_attributes_stop_at_ten_and_skills_and_disciplines_at_five(troupe: Troupe) -> None:
    npc = made(
        troupe,
        npc_kind="blood_brother",
        npc_form="stock",
        stock={"rating": 8, "specializations": specs("Brawl")},
    )
    convert(troupe, npc["id"])

    ratings = sheet(troupe, npc["id"])
    assert ratings[("attributes", "Physical")] == 10
    assert ratings[("skills", "Brawl")] == 5
    assert ratings[("disciplines", "Potence")] == 5


def test_only_staff_convert_and_only_a_stock_npc(troupe: Troupe) -> None:
    stock_npc = made(troupe, npc_kind="mortal", npc_form="stock")["id"]
    sheeted = made(troupe, npc_kind="mortal")["id"]

    assert troupe.player.client.post(f"/characters/{stock_npc}/npc/sheeted").status_code in (
        403,
        404,
    )
    assert convert(troupe, sheeted).status_code == 409


def test_a_sheeted_mortal_has_blood_it_cannot_spend_and_no_beast_or_humanity(
    troupe: Troupe,
) -> None:
    npc = made(troupe, name="Hunter Jo", npc_kind="mortal")["id"]
    state = view(troupe.storyteller, npc)

    assert state["npc_kind_name"] == "Mortal"
    assert state["panels"] == {
        "beast": False,
        "frenzy": False,
        "morality": False,
        "generation": False,
        "feed": False,
    }
    assert state["morality"] is None
    assert (state["generation"], state["blood_name"], state["blood_per_turn"]) == (0, "Blood", 0)
    assert state["blood"]["most"] == 5
    # Taps on the Beast do nothing.
    after = send(troupe.storyteller, npc, tap("beast", 1, at=1))
    assert after["beast"]["value"] == 0


def test_a_sheeted_werewolf_spends_rage_where_blood_would_be(troupe: Troupe) -> None:
    npc = made(troupe, name="Rage Walker", npc_kind="werewolf")["id"]
    state = view(troupe.storyteller, npc)

    assert (state["blood_name"], state["blood_per_turn"]) == ("Rage", 3)
    assert state["blood"] == {"value": 10, "most": 10, "start": 10}
    assert state["panels"]["beast"] is False
    # It keeps its sheet's Willpower and health.
    assert state["willpower"]["most"] == 6
    after = send(troupe.storyteller, npc, tap("blood", -3, at=1))
    assert after["blood"]["value"] == 7
    assert "Rage 10 → 7" in " ".join(e["text"] for e in after["log"])


def test_a_sheeted_vampire_keeps_every_panel(troupe: Troupe) -> None:
    state = view(troupe.storyteller, made(troupe)["id"])

    assert all(state["panels"].values())
    assert (state["blood_name"], state["morality"] is not None) == ("Blood", True)

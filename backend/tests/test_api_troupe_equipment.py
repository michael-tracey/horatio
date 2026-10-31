"""Troupes give equipment to their home characters (issue #280): from a template or
built by hand, checked by the rules between qualities; special items with any number
of qualities and effects of the troupe's own; changes and take-backs with a reason,
told to the player; each item's history; the troupe's templates; and who may."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Character, EquipmentItem, TroupeMembership
from tests.api_helpers import Person, Troupe, backstory_optional, new_character
from tests.test_api_downtimes import member_character
from tests.test_api_renames import character_log, other_troupe, summaries, troupe_log, visit

DAGGER = {
    "name": "Silver Dagger",
    "kind": "melee",
    "grade": "standard",
    "qualities": [{"name": "Concealable"}, {"name": "Silver"}],
}
RIFLE = {
    "name": "Hunting rifle",
    "kind": "ranged",
    "grade": "standard",
    "qualities": [{"name": "Accurate"}, {"name": "Long Range"}],
}
# Four melee qualities and an effect of the troupe's own.
LEGEND = {
    "name": "Blade of Saulot",
    "kind": "melee",
    "grade": "special",
    "qualities": [
        {"name": "Accurate"},
        {"name": "Concealable"},
        {"name": "Silver"},
        {"name": "Masterwork", "detail": "cuts through chains"},
    ],
    "effects": [
        {
            "name": "Drinks the Blood",
            "effect": "Once a game, heal 1 normal damage when it draws blood.",
        }
    ],
    "description": "Said to have been Saulot's own.",
}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    return member_character(troupe, troupe.player, "Agnes")


def path(troupe: Troupe) -> str:
    return f"/troupes/{troupe.id}/equipment"


def give(troupe: Troupe, character_id: str, by: Person | None = None, **item: Any) -> Any:
    return (by or troupe.storyteller).client.post(
        path(troupe), json={"character_id": character_id, **item}
    )


def given(troupe: Troupe, character_id: str, by: Person | None = None, **item: Any) -> Any:
    response = give(troupe, character_id, by, **item)
    assert response.status_code == 201, response.text
    return response.json()


def listed(troupe: Troupe, **params: Any) -> list[dict[str, Any]]:
    response = troupe.storyteller.client.get(path(troupe), params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def change(troupe: Troupe, item: dict[str, Any], by: Person | None = None, **body: Any) -> Any:
    fields = {k: item[k] for k in ("name", "kind", "grade", "crafted", "description")}
    qualities = [{"name": q["name"], "detail": q["detail"]} for q in item["qualities"]]
    return (by or troupe.storyteller).client.put(
        f"{path(troupe)}/{item['id']}",
        json={
            **fields,
            "qualities": qualities,
            "effects": item["effects"],
            "staff_note": item["staff_note"] or "",
            **body,
        },
    )


def test_a_storyteller_gives_a_dagger_from_the_template_and_a_rifle_by_hand(
    troupe: Troupe, agnes: str
) -> None:
    dagger = given(troupe, agnes, **DAGGER, template="Silver Dagger")
    rifle = given(troupe, agnes, **RIFLE, description="Her father's.", staff_note="From the ST")

    assert dagger["character_name"] == "Agnes"
    assert dagger["player_name"] == "player"
    assert (dagger["troupe_name"], dagger["given_by_name"]) == ("Lords of the Night", "storyteller")
    assert [q["name"] for q in dagger["qualities"]] == ["Concealable", "Silver"]
    assert dagger["qualities"][1]["page"] == "517"
    assert dagger["facts"]["hands"] == 1
    assert dagger["facts"]["aggravated_against"] == ["werewolves and others vulnerable to silver"]
    assert not dagger["special"]
    assert rifle["facts"] == {
        "hands": 2,
        "damage": 2,
        "shots": 12,
        "range": "half a mile",
        "aggravated_against": [],
    }
    assert rifle["staff_note"] == "From the ST"

    assert sorted(summaries(troupe.player)) == [
        "storyteller gave Agnes Hunting rifle (ranged weapon: Accurate, Long Range).",
        "storyteller gave Agnes Silver Dagger (melee weapon: Concealable, Silver).",
    ]
    assert "storyteller gave Agnes (player) Silver Dagger (melee weapon: Concealable, Silver)." in (
        troupe_log(troupe.lead, troupe.id)
    )
    assert character_log(troupe.player, agnes)[0] == (
        "storyteller gave Agnes (player) Hunting rifle (ranged weapon: Accurate, Long Range)."
    )

    history = troupe.storyteller.client.get(f"{path(troupe)}/{dagger['id']}").json()["history"]
    assert [(e["action"], e["summary"]) for e in history] == [
        ("given", "Given to Agnes by Lords of the Night, from the template Silver Dagger"),
    ]
    assert history[0]["actor_name"] == "storyteller"


def test_an_item_breaking_the_rules_is_refused_with_the_reason(troupe: Troupe, agnes: str) -> None:
    quick = {**RIFLE, "qualities": [*RIFLE["qualities"], {"name": "Quick Draw"}]}
    refused = give(troupe, agnes, **{**quick, "grade": "special"})
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Long Range needs two hands, so it can't be Quick Draw."

    too_many = give(troupe, agnes, **quick)
    assert too_many.status_code == 422
    assert "Standard or expensive gear has at most 2 qualities, not 3." in too_many.json()["detail"]

    for item, reason in (
        ({**DAGGER, "kind": "ranged"}, "Silver isn't a ranged weapon quality."),
        ({**DAGGER, "name": "  "}, "An item needs a name."),
        (
            {**DAGGER, "effects": LEGEND["effects"]},
            "Only a special item has special effects.",
        ),
        (
            {**LEGEND, "effects": [{"name": "Drinks the Blood", "effect": ""}]},
            "Each special effect needs a name and what it does.",
        ),
        (
            {**LEGEND, "qualities": [{"name": "Silver"}, {"name": "Silver"}]},
            "Silver can only be taken once.",
        ),
        (
            {**LEGEND, "qualities": [{"name": "Brutal"}, {"name": "Concealable"}]},
            "Brutal needs two hands, so it can't be Concealable.",
        ),
    ):
        response = give(troupe, agnes, **item)
        assert response.status_code == 422, item
        assert reason in response.json()["detail"]
    assert listed(troupe) == []


def test_only_home_characters_are_given_equipment(troupe: Troupe, agnes: str) -> None:
    elsewhere = other_troupe(troupe)
    backstory_optional(troupe.session, elsewhere)
    visitor = new_character(troupe, troupe.player, "Visiting Vera")
    asked = troupe.player.client.post(
        f"/characters/{visitor}/home-troupe", json={"troupe_id": elsewhere}
    )
    assert asked.status_code == 201, asked.text
    approved = troupe.stranger.client.post(f"/approvals/{asked.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    visit(troupe.player, visitor, troupe.id)

    refused = give(troupe, visitor, **DAGGER)
    assert refused.status_code == 422
    assert "not Visiting Vera's home troupe" in refused.json()["detail"]
    # One of another troupe's characters, that this troupe's staff can't see at all.
    stranger = new_character(troupe, troupe.stranger, "Elsewhere Eli")
    assert give(troupe, stranger, **DAGGER).status_code == 404

    # Its own home troupe can, and the troupe it visits sees it, but can't change it.
    made = troupe.stranger.client.post(
        f"/troupes/{elsewhere}/equipment", json={"character_id": visitor, **DAGGER}
    )
    assert made.status_code == 201, made.text
    theirs = made.json()
    read = troupe.storyteller.client.get(f"/characters/{visitor}/equipment").json()
    assert [i["name"] for i in read["items"]] == ["Silver Dagger"]
    assert read["can_give"] is False
    assert read["items"][0]["can_change"] is False
    assert change(troupe, theirs, name="Mine now", reason="Why not").status_code == 422
    taken = troupe.storyteller.client.post(
        f"{path(troupe)}/{theirs['id']}/take-back", json={"reason": "Ours"}
    )
    assert taken.status_code == 422
    assert listed(troupe) == []


def test_the_troupes_npcs_are_given_equipment_and_not_told(troupe: Troupe) -> None:
    made = troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Marta"})
    assert made.status_code == 201, made.text
    marta = made.json()["id"]

    item = given(troupe, marta, **RIFLE)

    assert item["character_kind"] == "npc"
    assert item["player_name"] is None
    holders = troupe.storyteller.client.get(path(troupe)).json()["characters"]
    assert [(c["name"], c["kind"]) for c in holders] == [("Marta", "npc")]


def test_an_assistant_makes_a_special_item_and_a_player_is_refused(
    troupe: Troupe, agnes: str
) -> None:
    for person in (troupe.player, troupe.narrator, troupe.stranger):
        assert give(troupe, agnes, by=person, **LEGEND).status_code == 403
    blade = given(troupe, agnes, by=troupe.assistant, **LEGEND)

    assert blade["special"] is True
    assert blade["special_troupe_name"] == "Lords of the Night"
    assert len(blade["qualities"]) == 4
    assert blade["qualities"][3] == {
        "name": "Masterwork",
        "detail": "cuts through chains",
        "effect": blade["qualities"][3]["effect"],
        "play": "One of a kind; triggers the Toreador weakness",
        "page": "517",
    }
    assert blade["effects"] == LEGEND["effects"]
    assert summaries(troupe.player) == [
        "assistant gave Agnes Blade of Saulot (special melee weapon: Accurate, Concealable,"
        " Silver, Masterwork: cuts through chains; Drinks the Blood)."
    ]

    # Neither the player nor a narrator can change it, nor take it back.
    for person in (troupe.player, troupe.narrator):
        assert change(troupe, blade, by=person, reason="Mine").status_code == 403
        taken = person.client.post(f"{path(troupe)}/{blade['id']}/take-back", json={"reason": "x"})
        assert taken.status_code == 403

    # An item made special later, with four qualities, by the storyteller.
    dagger = given(troupe, agnes, **DAGGER)
    more = [*dagger["qualities"], {"name": "Accurate"}, {"name": "Fast"}]
    assert change(troupe, dagger, qualities=more, reason="Blessed").status_code == 422
    made = change(troupe, dagger, qualities=more, grade="special", reason="Blessed")
    assert made.status_code == 200, made.text
    assert made.json()["special_troupe_name"] == "Lords of the Night"


def test_the_troupe_tab_lists_items_by_holder_and_filters(troupe: Troupe, agnes: str) -> None:
    other = member_character(troupe, troupe.storyteller, "Bram")
    given(troupe, agnes, **RIFLE)
    given(troupe, agnes, **DAGGER)
    given(troupe, other, **{**DAGGER, "name": "Wooden Stake", "qualities": [{"name": "Staking"}]})

    assert [(i["character_name"], i["name"]) for i in listed(troupe)] == [
        ("Agnes", "Hunting rifle"),
        ("Agnes", "Silver Dagger"),
        ("Bram", "Wooden Stake"),
    ]
    assert [i["name"] for i in listed(troupe, character_id=agnes, kind="melee")] == [
        "Silver Dagger"
    ]
    assert [i["name"] for i in listed(troupe, kind="ranged")] == ["Hunting rifle"]
    holders = troupe.storyteller.client.get(path(troupe)).json()["characters"]
    assert [(c["name"], c["player_name"], c["splat"]) for c in holders] == [
        ("Agnes", "player", "vampire"),
        ("Bram", "storyteller", "vampire"),
    ]
    for person in (troupe.player, troupe.narrator):
        assert person.client.get(path(troupe)).status_code == 403


def test_a_change_with_a_reason_is_told_and_kept_in_its_history(troupe: Troupe, agnes: str) -> None:
    rifle = given(troupe, agnes, **RIFLE, staff_note="Watch the ammo")

    unexplained = change(troupe, rifle, name="Grandfather's rifle")
    assert unexplained.status_code == 422
    assert "Say why" in unexplained.json()["detail"]
    assert change(troupe, rifle, reason="Nothing").status_code == 422

    qualities = [{"name": "Accurate"}, {"name": "Silver Ammunition"}]
    changed = change(
        troupe, rifle, name="Grandfather's rifle", qualities=qualities, reason="Rebored"
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["facts"]["range"] == "50 steps"
    told = (
        "storyteller changed Agnes's Hunting rifle: renamed from Hunting rifle; qualities now"
        " Accurate, Silver Ammunition (Rebored)."
    )
    assert told in summaries(troupe.player)
    logged = told.replace("Agnes's", "Agnes (player)'s")
    assert character_log(troupe.player, agnes)[0] == logged

    # The staff note alone: kept in the history, needing no reason, and not told.
    noted = change(troupe, changed.json(), staff_note="Out of ammo")
    assert noted.status_code == 200, noted.text
    assert len([s for s in summaries(troupe.player) if "changed" in s]) == 1
    assert character_log(troupe.player, agnes)[0] == logged
    assert [e["summary"] for e in noted.json()["history"]] == [
        "Given to Agnes by Lords of the Night",
        "Changed: renamed from Hunting rifle; qualities now Accurate, Silver Ammunition",
        "Changed: a new staff note",
    ]
    assert noted.json()["history"][1]["reason"] == "Rebored"
    assert noted.json()["history"][1]["changes"]["name"] == {
        "from": "Hunting rifle",
        "to": "Grandfather's rifle",
    }

    # The player sees the item, but not the note.
    mine = troupe.player.client.get(f"/characters/{agnes}/equipment").json()
    assert mine["can_give"] is False
    assert mine["items"][0]["staff_note"] is None
    assert mine["items"][0]["can_change"] is False
    staff = troupe.assistant.client.get(f"/characters/{agnes}/equipment").json()
    assert staff["can_give"] is True
    assert staff["items"][0]["staff_note"] == "Out of ammo"
    assert troupe.player.client.get(f"{path(troupe)}/{rifle['id']}").status_code == 403


def test_taking_an_item_back(troupe: Troupe, agnes: str) -> None:
    dagger = given(troupe, agnes, **DAGGER)
    url = f"{path(troupe)}/{dagger['id']}/take-back"

    assert troupe.storyteller.client.post(url, json={"reason": " "}).status_code == 422
    taken = troupe.storyteller.client.post(url, json={"reason": "Lost it in a bet"})
    assert taken.status_code == 200, taken.text

    assert taken.json()["status"] == "taken_back"
    assert taken.json()["history"][-1]["summary"] == "Taken back from Agnes"
    told = "storyteller took Silver Dagger back from Agnes: Lost it in a bet"
    assert told in summaries(troupe.player)
    assert character_log(troupe.player, agnes)[0] == (
        "storyteller took Silver Dagger back from Agnes (player): Lost it in a bet"
    )
    assert listed(troupe) == []
    assert [i["name"] for i in listed(troupe, status=["held", "taken_back"])] == ["Silver Dagger"]
    assert troupe.player.client.get(f"/characters/{agnes}/equipment").json()["items"] == []
    # Taken back, it can't be taken again or changed.
    assert troupe.storyteller.client.post(url, json={"reason": "Again"}).status_code == 409
    assert change(troupe, dagger, name="Gone", reason="x").status_code == 409


def test_equipment_goes_with_the_character_to_a_new_home(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    dagger = given(troupe, agnes, **DAGGER)
    elsewhere = other_troupe(troupe)
    character = session.get_one(Character, uuid.UUID(agnes))
    character.home_troupe_id = uuid.UUID(elsewhere)
    session.add(TroupeMembership(troupe_id=uuid.UUID(elsewhere), character_id=character.id))
    session.flush()

    assert listed(troupe) == []
    assert change(troupe, dagger, name="Kept", reason="x").status_code == 422
    theirs = troupe.stranger.client.get(f"/troupes/{elsewhere}/equipment").json()["items"]
    assert [(i["name"], i["troupe_name"]) for i in theirs] == [
        ("Silver Dagger", "Lords of the Night")
    ]
    renamed = troupe.stranger.client.put(
        f"/troupes/{elsewhere}/equipment/{dagger['id']}",
        json={**DAGGER, "name": "Old dagger", "reason": "Tarnished"},
    )
    assert renamed.status_code == 200, renamed.text


def test_a_troupe_saves_its_own_templates(troupe: Troupe) -> None:
    url = f"{path(troupe)}/templates"
    pistol = {
        "name": "Sheriff's issue pistol",
        "kind": "ranged",
        "grade": "standard",
        "qualities": [{"name": "Concealable"}, {"name": "Silver Ammunition"}],
        "description": "Stamped with the Sheriff's mark.",
    }
    saved = troupe.assistant.client.post(url, json=pistol)
    assert saved.status_code == 201, saved.text
    assert troupe.storyteller.client.post(url, json=pistol).status_code == 409
    broken = {**pistol, "name": "Broken", "qualities": [{"name": "Long Range"}, {"name": "Spread"}]}
    assert troupe.storyteller.client.post(url, json=broken).status_code == 422
    assert troupe.player.client.post(url, json={**pistol, "name": "Mine"}).status_code == 403

    templates = troupe.storyteller.client.get(url).json()
    assert [(t["name"], t["description"]) for t in templates] == [
        ("Sheriff's issue pistol", "Stamped with the Sheriff's mark.")
    ]
    assert "assistant saved Sheriff's issue pistol" in troupe_log(troupe.lead, troupe.id)[0]

    deleted = troupe.storyteller.client.delete(f"{url}/{saved.json()['id']}")
    assert deleted.status_code == 204, deleted.text
    assert troupe.storyteller.client.get(url).json() == []


def test_deleting_an_npc_takes_its_equipment(troupe: Troupe, session: Session) -> None:
    made = troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Marta"})
    marta = made.json()["id"]
    given(troupe, marta, **DAGGER)

    deleted = troupe.storyteller.client.delete(f"/characters/{marta}")
    assert deleted.status_code == 204, deleted.text
    assert session.query(EquipmentItem).count() == 0

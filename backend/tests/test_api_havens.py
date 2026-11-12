"""A player's own Haven (issue #682): its player puts it on the home troupe's list,
names and describes it, says where it is and chooses its advantages, by the same
rules and log as staff; staff's part of the record is never sent to them."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe, new_character
from tests.test_api_locations import Scene


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def haven_path(scene: Scene) -> str:
    return f"/characters/{scene.agnes}/haven"


def read(scene: Scene) -> dict[str, Any]:
    found = scene.troupe.player.client.get(haven_path(scene))
    assert found.status_code == 200, found.text
    return found.json()


def made(scene: Scene, **body: Any) -> dict[str, Any]:
    added = scene.troupe.player.client.post(haven_path(scene), json=body)
    assert added.status_code == 201, added.text
    return added.json()


def changed(scene: Scene, **body: Any) -> Any:
    return scene.troupe.player.client.put(haven_path(scene), json=body)


def test_a_player_puts_their_haven_on_the_list_and_changes_it(scene: Scene) -> None:
    before = read(scene)
    assert before["haven"] is None
    assert before["cannot_create"] == "Agnes has no Haven background."
    refused = scene.troupe.player.client.post(haven_path(scene), json={"name": "Agnes's flat"})
    assert refused.status_code == 409

    scene.give(scene.agnes, "backgrounds", "Haven", 2)
    scene.give(scene.agnes, "skills", "Security", 1)
    ready = read(scene)
    assert (ready["dots"], ready["cannot_create"]) == (2, None)
    choices = {a["name"]: a for a in ready["advantages"]}
    assert (choices["Security"]["free"], choices["Library"]["free"]) == (True, False)
    assert choices["Occult"]["allowed"] is False

    haven = made(
        scene,
        name="The Bell Tower",
        description="A disused bell tower over the river.",
        address="1 Church St",
        map_link="https://maps.example.com/bell",
        haven_advantages=["Library", "Luxury", "Security"],
    )["haven"]
    assert haven["kind"] == "haven"
    assert (haven["name"], haven["description"]) == (
        "The Bell Tower",
        "A disused bell tower over the river.",
    )
    assert (haven["haven_free"], haven["haven_over"], haven["read_only"]) == (
        ["Security"],
        None,
        None,
    )

    staff = scene.troupe.storyteller.client.get(f"/locations/{haven['id']}").json()
    assert staff["haven_of"] == {"id": scene.agnes, "name": "Agnes"}
    assert (staff["rating"], staff["description"]) == (2, "A disused bell tower over the river.")
    assert "player added the location The Bell Tower." in scene.messages()

    second = scene.troupe.player.client.post(haven_path(scene), json={"name": "Another"})
    assert second.status_code == 409
    assert second.json()["detail"] == "Agnes already has a Haven."

    too_many = changed(
        scene, name="The Bell Tower", haven_advantages=["Library", "Luxury", "Size", "Security"]
    )
    assert too_many.status_code == 422
    occult = changed(scene, name="The Bell Tower", haven_advantages=["Occult"])
    assert occult.json()["detail"] == (
        "The Occult advantage needs the Occult skill (MET: VTM, p. 102)."
    )

    renamed = changed(
        scene,
        name="The Old Bell Tower",
        description="Bats.",
        address="1 Church St",
        haven_advantages=["Library", "Security"],
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["haven"]["name"] == "The Old Bell Tower"
    log = scene.troupe.storyteller.client.get(f"/locations/{haven['id']}").json()["log"]
    assert any(
        "name" in e["message"] and "description" in e["message"] and "−Luxury" in e["message"]
        for e in log
    ), [e["message"] for e in log]


def test_staff_s_part_of_the_haven_isn_t_sent_to_its_player(scene: Scene) -> None:
    scene.give(scene.agnes, "backgrounds", "Haven", 1)
    haven = made(scene, name="Agnes's flat")["haven"]
    kept = scene.change(
        {"id": haven["id"]},
        notes="She doesn't know about the cellar.",
        locked=True,
        negatives=[
            {"name": "Damaged", "level": 1},
            {"name": "Compromised", "level": 1, "secret": True, "by": "the Sheriff"},
        ],
    )
    assert kept.status_code == 200, kept.text

    found = scene.troupe.player.client.get(haven_path(scene))
    text = found.text
    assert "cellar" not in text and "Sheriff" not in text and "Compromised" not in text
    assert [n["name"] for n in found.json()["haven"]["negatives"]] == ["Damaged"]

    # The player's change leaves staff's part as it was.
    assert changed(scene, name="Agnes's flat", address="12 Elm St").status_code == 200
    staff = scene.troupe.storyteller.client.get(f"/locations/{haven['id']}").json()
    assert staff["notes"] == "She doesn't know about the cellar."
    assert staff["locked"] is True
    assert [n["name"] for n in staff["negatives"]] == ["Damaged", "Compromised"]
    assert staff["address"] == "12 Elm St"


def test_only_the_player_sees_or_changes_their_haven(scene: Scene) -> None:
    scene.give(scene.agnes, "backgrounds", "Haven", 1)
    made(scene, name="Agnes's flat")
    for other in (scene.troupe.narrator, scene.troupe.stranger, scene.troupe.storyteller):
        assert other.client.get(haven_path(scene)).status_code == 404
        put = other.client.put(haven_path(scene), json={"name": "Mine now"})
        assert put.status_code == 404


def test_a_stock_location_staff_made_a_haven_is_read_only_to_its_player(scene: Scene) -> None:
    scene.give(scene.agnes, "backgrounds", "Haven", 1)
    scene.added(name="Grove Arcade", rating=3, haven_of_id=scene.agnes)

    found = read(scene)
    assert found["haven"]["name"] == "Grove Arcade"
    assert found["haven"]["kind"] == "standard"
    assert found["haven"]["read_only"] == (
        "Staff made Grove Arcade, one of the troupe's locations, Agnes's Haven: "
        "ask them to change it."
    )
    refused = changed(scene, name="Agnes's Arcade")
    assert refused.status_code == 409
    assert found["cannot_create"] is None


def test_a_retired_character_s_haven_stays_as_it_is(scene: Scene) -> None:
    scene.give(scene.agnes, "backgrounds", "Haven", 1)
    made(scene, name="Agnes's flat")
    retired = scene.troupe.player.client.post(f"/characters/{scene.agnes}/retire")
    assert retired.status_code == 200, retired.text

    found = read(scene)
    assert found["haven"]["read_only"] == "Agnes is retired: their Haven stays as it is."
    assert changed(scene, name="Elsewhere").status_code == 409


# --- named in creation, before any troupe accepts the character (#683) ----------------


PICKS: dict[str, list[tuple[str, int]]] = {
    "attributes": [("Physical", 3), ("Social", 7), ("Mental", 5)],
    "focus_physicals": [("Dexterity", 1)],
    "focus_mentals": [("Intelligence", 1)],
    "focus_socials": [("Manipulation", 1)],
    "skills": [
        ("Leadership", 4),
        ("Subterfuge", 3),
        ("Academics", 3),
        ("Awareness", 2),
        ("Empathy", 2),
        ("Investigation", 2),
        ("Dodge", 1),
        ("Drive", 1),
        ("Medicine", 1),
        ("Security", 1),
    ],
    "backgrounds": [("Resources", 3), ("Haven", 2), ("Generation", 1)],
    "disciplines": [("Celerity", 2), ("Potence", 1), ("Presence", 1)],
}


def in_creation(scene: Scene, name: str) -> str:
    """A Brujah built in the wizard with Haven 2 and Security 1, not yet finished."""
    player = scene.troupe.player.client
    character_id = new_character(scene.troupe, scene.troupe.player, name, finished=False)
    chosen = player.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": "Brujah", "rating": None},
    )
    assert chosen.status_code == 200, chosen.text
    for category, picks in PICKS.items():
        placed = player.put(
            f"/characters/{character_id}/creation/categories/{category}",
            json={"picks": [{"name": n, "rating": r} for n, r in picks]},
        )
        assert placed.status_code == 200, placed.text
    return character_id


def accepted(scene: Scene, character_id: str) -> Any:
    player = scene.troupe.player.client
    done = player.post(f"/characters/{character_id}/creation/complete")
    assert done.status_code in (200, 204), done.text
    asked = player.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": scene.troupe.id}
    )
    assert asked.status_code == 201, asked.text
    return scene.troupe.lead.client.post(f"/approvals/{asked.json()['id']}/approve", json={})


def drafted(scene: Scene, character_id: str, **body: Any) -> Any:
    return scene.troupe.player.client.put(f"/characters/{character_id}/haven/draft", json=body)


def read_of(scene: Scene, character_id: str) -> dict[str, Any]:
    found = scene.troupe.player.client.get(f"/characters/{character_id}/haven")
    assert found.status_code == 200, found.text
    return found.json()


def test_a_haven_named_in_creation_goes_on_the_list_of_the_troupe_that_accepts_her(
    scene: Scene,
) -> None:
    nell = in_creation(scene, "Nell")
    before = read_of(scene, nell)
    assert (before["drafting"], before["cannot_create"], before["haven"]) == (True, None, None)
    # The list's rules hold for the draft: two dots, plus Security free with the skill.
    assert (
        drafted(
            scene, nell, name="Tower", haven_advantages=["Library", "Luxury", "Size"]
        ).status_code
        == 422
    )
    kept = drafted(
        scene,
        nell,
        name="The Bell Tower",
        description="A disused bell tower over the river.",
        address="1 Church St",
        haven_advantages=["Library", "Luxury", "Security"],
    )
    assert kept.status_code == 200, kept.text
    draft = kept.json()["draft"]
    assert (draft["name"], draft["haven_free"], draft["haven_over"]) == (
        "The Bell Tower",
        ["Security"],
        None,
    )
    # Nothing is on the troupe's list yet: no troupe has accepted her.
    listed = scene.troupe.storyteller.client.get(scene.path).json()
    assert all(loc["name"] != "The Bell Tower" for loc in listed)

    approved = accepted(scene, nell)
    assert approved.status_code == 200, approved.text
    after = read_of(scene, nell)
    assert (after["draft"], after["drafting"]) == (None, False)
    haven = after["haven"]
    assert (haven["name"], haven["address"], haven["haven_advantages"]) == (
        "The Bell Tower",
        "1 Church St",
        ["Library", "Luxury", "Security"],
    )
    staff = scene.troupe.storyteller.client.get(f"/locations/{haven['id']}").json()
    assert staff["haven_of"]["name"] == "Nell"
    # Put there as her player's own change.
    assert "player added the location The Bell Tower." in scene.messages()
    # Once accepted, the Haven is on the list: no more drafts.
    late = drafted(scene, nell, name="Somewhere else")
    assert late.status_code == 409


def test_a_draft_over_its_dots_is_flagged_not_dropped(scene: Scene) -> None:
    nell = in_creation(scene, "Nell")
    assert (
        drafted(
            scene, nell, name="The Bell Tower", haven_advantages=["Library", "Luxury", "Security"]
        ).status_code
        == 200
    )
    # Later in the wizard she trades Security for Stealth: Security now uses a dot.
    skills = [(n, r) for n, r in PICKS["skills"] if n != "Security"] + [("Stealth", 1)]
    placed = scene.troupe.player.client.put(
        f"/characters/{nell}/creation/categories/skills",
        json={"picks": [{"name": n, "rating": r} for n, r in skills]},
    )
    assert placed.status_code == 200, placed.text
    draft = read_of(scene, nell)["draft"]
    assert draft["haven_advantages"] == ["Library", "Luxury", "Security"]
    assert draft["haven_over"] == (
        "Nell has Haven 2: one advantage for each dot (MET: VTM, p. 102). "
        "This Haven has 3 that use a dot: drop 1."
    )


def test_a_draft_that_no_longer_fits_waits_for_its_player(scene: Scene) -> None:
    """Acceptance never fails over the draft: its name is taken on the list, so it
    stays a draft, and the player puts it on the list from the sheet."""
    nell = in_creation(scene, "Nell")
    assert drafted(scene, nell, name="The Grove Arcade").status_code == 200
    scene.added(name="The Grove Arcade", kind="standard", rating=1)

    approved = accepted(scene, nell)
    assert approved.status_code == 200, approved.text
    waiting = read_of(scene, nell)
    assert waiting["haven"] is None
    assert waiting["draft"]["name"] == "The Grove Arcade"
    assert (waiting["drafting"], waiting["cannot_create"]) == (False, None)

    placed = scene.troupe.player.client.post(
        f"/characters/{nell}/haven", json={"name": "The Grove Arcade Annexe"}
    )
    assert placed.status_code == 201, placed.text
    assert placed.json()["draft"] is None
    assert placed.json()["haven"]["name"] == "The Grove Arcade Annexe"


def test_only_the_player_names_a_draft_haven(scene: Scene) -> None:
    nell = in_creation(scene, "Nell")
    for person in (scene.troupe.storyteller, scene.troupe.stranger):
        refused = person.client.put(f"/characters/{nell}/haven/draft", json={"name": "Mine"})
        assert refused.status_code == 404

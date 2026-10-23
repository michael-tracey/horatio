"""Shared backgrounds: staff set one up with the dots each sharer puts in, the log
of dots in and out and of uses, the capped total, and who may see and log."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_downtimes import member_character

AT = "2026-10-17T21:15:00+00:00"


class Scene:
    """Agnes (the player's) and Bram (another player's) are at home in the troupe;
    Cora (a third player's) is too, but shares nothing."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.other = sign_up(troupe.client_for, "other")
        self.third = sign_up(troupe.client_for, "third")
        self.agnes = member_character(troupe, troupe.player, "Agnes")
        self.bram = member_character(troupe, self.other, "Bram")
        self.cora = member_character(troupe, self.third, "Cora")

    @property
    def path(self) -> str:
        return f"/troupes/{self.troupe.id}/shared-backgrounds"

    def create(self, by: Person | None = None, **body: Any) -> Any:
        return (by or self.troupe.storyteller).client.post(
            self.path,
            json={
                "name": "The coterie's Haven",
                "background": "Haven",
                "notes": "Security, Guards",
                "contributions": [
                    {"character_id": self.agnes, "dots": 2},
                    {"character_id": self.bram, "dots": 1},
                ],
                **body,
            },
        )

    def haven(self) -> dict[str, Any]:
        made = self.create()
        assert made.status_code == 201, made.text
        return made.json()

    def log(self, shared: dict[str, Any], by: Person | None = None, **body: Any) -> Any:
        return (by or self.troupe.storyteller).client.post(
            f"/shared-backgrounds/{shared['id']}/entries", json=body
        )

    def read(self, shared: dict[str, Any], by: Person | None = None) -> Any:
        return (by or self.troupe.storyteller).client.get(f"/shared-backgrounds/{shared['id']}")

    def messages(self) -> list[str]:
        log = self.troupe.lead.client.get(f"/troupes/{self.troupe.id}/log").json()
        return [e["message"] for e in log]


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def sharers(shared: dict[str, Any]) -> list[tuple[str, int]]:
    return [(s["name"], s["dots"]) for s in shared["sharers"]]


# --- setting one up ---------------------------------------------------------------------


def test_staff_set_up_a_shared_background_with_each_sharers_dots(scene: Scene) -> None:
    shared = scene.haven()

    assert (shared["name"], shared["background"], shared["notes"]) == (
        "The coterie's Haven",
        "Haven",
        "Security, Guards",
    )
    assert sharers(shared) == [("Agnes", 2), ("Bram", 1)]
    assert (shared["total"], shared["put_in"], shared["most"]) == (3, 3, 5)
    assert shared["can_manage"] is True
    assert [(e["kind"], e["name"], e["dots"]) for e in shared["entries"]] == [
        ("contribution", "Bram", 1),
        ("contribution", "Agnes", 2),
    ]
    assert all(e["logged_by_name"] == "storyteller" for e in shared["entries"])
    messages = scene.messages()
    assert "storyteller set up The coterie's Haven, a shared Haven." in messages
    assert "storyteller logged Agnes (player) putting 2 dots into The coterie's Haven." in (
        messages
    )
    listed = scene.troupe.assistant.client.get(scene.path)
    assert listed.status_code == 200, listed.text
    assert [s["name"] for s in listed.json()] == ["The coterie's Haven"]


def test_the_group_total_is_never_more_than_five(scene: Scene) -> None:
    made = scene.create(
        contributions=[
            {"character_id": scene.agnes, "dots": 3},
            {"character_id": scene.bram, "dots": 4},
        ]
    )

    assert made.status_code == 201, made.text
    assert (made.json()["total"], made.json()["put_in"]) == (5, 7)


def test_only_the_books_backgrounds_are_shared(scene: Scene) -> None:
    choices = scene.troupe.storyteller.client.get(f"{scene.path}/choices")
    assert choices.status_code == 200, choices.text
    assert choices.json()["backgrounds"] == ["Haven", "Herd", "Allies", "Contacts"]
    assert {c["name"] for c in choices.json()["characters"]} == {"Agnes", "Bram", "Cora"}

    refused = scene.create(background="Resources")

    assert refused.status_code == 422
    assert "Vol. 2 Issue 1, p. 88" in refused.json()["detail"]


def test_a_shared_background_needs_a_free_name_and_sharers_in_the_troupe(scene: Scene) -> None:
    scene.haven()
    assert scene.create().status_code == 409
    assert scene.create(name="Another", contributions=[]).status_code == 422
    outsider = new_character(scene.troupe, scene.troupe.stranger, "Drifter")
    elsewhere = scene.create(name="Another", contributions=[{"character_id": outsider, "dots": 1}])
    assert elsewhere.status_code == 422
    assert "not in this troupe" in elsewhere.json()["detail"]
    twice = scene.create(
        name="Another",
        contributions=[
            {"character_id": scene.agnes, "dots": 1},
            {"character_id": scene.agnes, "dots": 1},
        ],
    )
    assert twice.status_code == 422


def test_staff_rename_it_and_delete_it(scene: Scene) -> None:
    shared = scene.haven()

    changed = scene.troupe.lead.client.patch(
        f"/shared-backgrounds/{shared['id']}",
        json={"name": "The Rack's back rooms", "background": "Herd"},
    )
    assert changed.status_code == 200, changed.text
    assert (changed.json()["name"], changed.json()["background"]) == (
        "The Rack's back rooms",
        "Herd",
    )
    gone = scene.troupe.assistant.client.delete(f"/shared-backgrounds/{shared['id']}")
    assert gone.status_code == 204, gone.text

    assert scene.read(shared).status_code == 404
    messages = scene.messages()
    assert "lead changed the shared background The Rack's back rooms: name, background." in (
        messages
    )
    assert "assistant deleted the shared background The Rack's back rooms and its log." in (
        messages
    )


# --- the log ----------------------------------------------------------------------------


def test_dots_put_in_and_taken_out_change_the_total(scene: Scene) -> None:
    shared = scene.haven()

    more = scene.log(shared, kind="contribution", character_id=scene.cora, dots=2, happened_at=AT)
    assert more.status_code == 201, more.text
    out = scene.log(shared, kind="withdrawal", character_id=scene.agnes, dots=2, note="Left")
    assert out.status_code == 201, out.text

    # In the order they first put dots in: Cora's are dated before the others'.
    assert sharers(out.json()) == [("Cora", 2), ("Agnes", 0), ("Bram", 1)]
    assert out.json()["total"] == 3
    too_many = scene.log(shared, kind="withdrawal", character_id=scene.bram, dots=2)
    assert too_many.status_code == 422
    assert "only 1 dot" in too_many.json()["detail"]
    assert "storyteller logged Agnes (player) taking 2 dots out of The coterie's Haven." in (
        scene.messages()
    )


def test_a_player_logs_a_use_for_their_own_character(scene: Scene) -> None:
    shared = scene.haven()

    used = scene.log(
        shared,
        by=scene.troupe.player,
        kind="use",
        character_id=scene.agnes,
        happened_at=AT,
        purpose="Hiding from the hunters for the day",
        note="Bram knows",
    )

    assert used.status_code == 201, used.text
    # Dated at the last game, so below the dots put in today.
    assert [e["kind"] for e in used.json()["entries"]] == ["contribution", "contribution", "use"]
    entry = used.json()["entries"][-1]
    assert {k: entry[k] for k in ("kind", "name", "dots", "purpose", "note")} == {
        "kind": "use",
        "name": "Agnes",
        "dots": None,
        "purpose": "Hiding from the hunters for the day",
        "note": "Bram knows",
    }
    assert (entry["happened_at"], entry["logged_by_name"], entry["can_delete"]) == (
        "2026-10-17T21:15:00Z",
        "player",
        True,
    )
    assert used.json()["total"] == 3, "a use changes no numbers"
    # Bram's player reads it in the same log.
    seen = scene.read(shared, by=scene.other).json()
    assert seen["entries"][-1]["purpose"] == "Hiding from the hunters for the day"
    assert seen["entries"][-1]["can_delete"] is False
    assert "player logged Agnes drawing on The coterie's Haven." in scene.messages()
    agnes_log = scene.troupe.player.client.get(f"/characters/{scene.agnes}/log").json()
    assert "player logged Agnes drawing on The coterie's Haven." in [
        e["message"] for e in agnes_log
    ]


def test_a_player_logs_only_uses_and_only_for_their_own_character(scene: Scene) -> None:
    shared = scene.haven()
    player = scene.troupe.player

    for_bram = scene.log(shared, by=player, kind="use", character_id=scene.bram)
    dots = scene.log(shared, by=player, kind="contribution", character_id=scene.agnes, dots=1)

    assert for_bram.status_code == 403
    assert dots.status_code == 403
    mine = scene.read(shared, by=player).json()
    assert [(s["name"], s["can_log_use"]) for s in mine["sharers"]] == [
        ("Agnes", True),
        ("Bram", False),
    ]
    assert mine["can_manage"] is False


def test_only_a_character_with_dots_in_it_draws_on_it(scene: Scene) -> None:
    shared = scene.haven()
    out = scene.log(shared, kind="withdrawal", character_id=scene.agnes, dots=2)
    assert out.status_code == 201, out.text

    used = scene.log(shared, by=scene.troupe.player, kind="use", character_id=scene.agnes)

    assert used.status_code == 422
    assert "no dots" in used.json()["detail"]
    # Their player still reads the log Agnes was part of.
    assert scene.read(shared, by=scene.troupe.player).status_code == 200
    staff_use = scene.log(shared, kind="use", character_id=scene.cora)
    assert staff_use.status_code == 422


def test_entries_come_off_the_log(scene: Scene) -> None:
    shared = scene.haven()
    player = scene.troupe.player
    used = scene.log(shared, by=player, kind="use", character_id=scene.agnes).json()
    use_id = used["entries"][0]["id"]
    agnes_in = next(
        e["id"] for e in used["entries"] if e["kind"] == "contribution" and e["name"] == "Agnes"
    )

    assert player.client.delete(f"/shared-background-entries/{agnes_in}").status_code == 403
    assert player.client.delete(f"/shared-background-entries/{use_id}").status_code == 204
    # Dots taken out since cannot lose the entry that put them in.
    assert scene.log(shared, kind="withdrawal", character_id=scene.agnes, dots=1).status_code == 201
    blocked = scene.troupe.storyteller.client.delete(f"/shared-background-entries/{agnes_in}")
    assert blocked.status_code == 409

    assert [e["kind"] for e in scene.read(shared).json()["entries"]] == [
        "withdrawal",
        "contribution",
        "contribution",
    ]
    assert "player took Agnes's use of The coterie's Haven off its log." in scene.messages()


# --- who may see it ---------------------------------------------------------------------


def test_staff_and_the_sharers_players_see_it_and_no_one_else(scene: Scene) -> None:
    shared = scene.haven()
    troupe = scene.troupe

    for person in (troupe.lead, troupe.storyteller, troupe.assistant, troupe.custodian):
        assert scene.read(shared, by=person).status_code == 200, person.email
    for person in (troupe.player, scene.other):
        assert scene.read(shared, by=person).status_code == 200, person.email
    for person in (troupe.narrator, troupe.stranger, scene.third):
        assert scene.read(shared, by=person).status_code == 404, person.email
        assert scene.log(shared, by=person, kind="use", character_id=scene.cora).status_code == 404
    for person in (troupe.narrator, troupe.player):
        assert person.client.get(scene.path).status_code == 403
        assert scene.create(by=person, name="Theirs").status_code == 403
    assert (
        troupe.player.client.patch(f"/shared-backgrounds/{shared['id']}", json={"name": "Mine"})
    ).status_code == 403


def test_a_character_lists_the_shared_backgrounds_it_has_put_dots_in(scene: Scene) -> None:
    shared = scene.haven()
    scene.create(
        name="The coterie's Herd",
        background="Herd",
        contributions=[{"character_id": scene.bram, "dots": 2}],
    )

    agnes = scene.troupe.player.client.get(f"/characters/{scene.agnes}/shared-backgrounds")
    bram = scene.troupe.storyteller.client.get(f"/characters/{scene.bram}/shared-backgrounds")

    assert agnes.status_code == 200, agnes.text
    assert [s["id"] for s in agnes.json()] == [shared["id"]]
    assert agnes.json()[0]["troupe_name"] == "Lords of the Night"
    assert [s["name"] for s in bram.json()] == ["The coterie's Haven", "The coterie's Herd"]
    cora = scene.third.client.get(f"/characters/{scene.cora}/shared-backgrounds")
    assert cora.json() == []
    assert (
        scene.third.client.get(f"/characters/{scene.agnes}/shared-backgrounds").status_code == 404
    )

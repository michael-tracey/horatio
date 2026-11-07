"""Equipment given from a downtime response (issue #508): a new item, or a quality on
an item the character holds, added while writing the response and given when it is
delivered, with the results; changed or taken off before then; its history linking
back; and who may."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_responses import Scene

RIFLE = {
    "name": "Sniper rifle",
    "kind": "ranged",
    "grade": "standard",
    "qualities": [{"name": "Accurate"}, {"name": "Long Range"}],
}
WATCH = {"name": "Pocket watch", "kind": "miscellaneous", "grade": "standard"}


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def feed(scene: Scene) -> str:
    return scene.response_for("Feed at the docks")["id"]


def give(person: Person, response_id: str, **body: Any) -> Any:
    return person.client.post(f"/responses/{response_id}/items", json=body)


def held(scene: Scene) -> list[dict[str, Any]]:
    response = scene.troupe.player.client.get(f"/characters/{scene.agnes}/equipment")
    assert response.status_code == 200, response.text
    return [i for i in response.json()["items"] if i["status"] == "held"]


def results(scene: Scene) -> str:
    found = scene.troupe.player.client.get(f"/characters/{scene.agnes}/downtime/results").json()
    return found[0]["message"]


def deliver(scene: Scene, *, partial: bool = True) -> Any:
    return scene.troupe.assistant.client.post(
        f"/cycles/{scene.cycle['id']}/deliver", json={"partial": partial}
    )


def history(scene: Scene, item_id: str) -> list[dict[str, Any]]:
    response = scene.troupe.storyteller.client.get(
        f"/troupes/{scene.troupe.id}/equipment/{item_id}"
    )
    assert response.status_code == 200, response.text
    return response.json()["history"]


def test_an_item_from_a_response_arrives_with_the_results(scene: Scene) -> None:
    troupe = scene.troupe
    response_id = feed(scene)
    added = give(troupe.storyteller, response_id, item={**RIFLE, "template": "Hunting rifle"})
    assert added.status_code == 201, added.text
    [row] = added.json()["items"]
    assert row["text"] == "Sniper rifle (Accurate, Long Range)"
    assert row["given_at"] is None
    assert row["item"]["template"] == "Hunting rifle"
    assert added.json()["can_give"] is True

    # Written, but not yet delivered: the character doesn't have it.
    troupe.assistant.client.put(f"/responses/{response_id}", json={"body": "You find a buyer."})
    assert held(scene) == []
    troupe.assistant.client.post(f"/cycles/{scene.cycle['id']}/close")
    # The cycle shows as having something to deliver, and delivering gives it.
    assert deliver(scene).json()["delivered"] == 1
    [rifle] = held(scene)
    assert rifle["name"] == "Sniper rifle"
    assert rifle["given_by_name"] == "storyteller"
    assert results(scene).endswith(
        "*Result:* You find a buyer.\n*You received:* Sniper rifle (Accurate, Long Range)"
    )

    # Its history says where it came from, and links to the response.
    [given] = history(scene, rifle["id"])
    assert given["reason"] == "From the October 2026 downtime"
    assert given["downtime"] == {
        "cycle_id": scene.cycle["id"],
        "cycle_name": "October 2026",
        "response_id": response_id,
    }
    assert "from the template Hunting rifle" in given["summary"]

    # The results told the player; the item isn't told again.
    kinds = [n["kind"] for n in troupe.player.client.get("/notifications").json()["items"]]
    assert "downtime.delivered" in kinds
    assert "equipment.given" not in kinds

    # Given once, never again, and no longer changed here.
    assert deliver(scene).json()["delivered"] == 0
    assert len(held(scene)) == 1
    [row] = scene.response_for("Feed at the docks")["items"]
    assert row["given_at"] is not None and row["item_id"] == rifle["id"]
    path = f"/responses/{response_id}/items/{row['id']}"
    assert troupe.storyteller.client.delete(path).status_code == 409
    assert troupe.storyteller.client.put(path, json={"item": WATCH}).status_code == 409


def test_staff_change_or_take_it_off_before_delivery(scene: Scene) -> None:
    troupe = scene.troupe
    response_id = feed(scene)
    [row] = give(troupe.assistant, response_id, item=RIFLE).json()["items"]
    path = f"/responses/{response_id}/items/{row['id']}"
    changed = troupe.assistant.client.put(path, json={"item": {**RIFLE, "name": "Old rifle"}})
    assert changed.status_code == 200, changed.text
    assert [r["text"] for r in changed.json()["items"]] == ["Old rifle (Accurate, Long Range)"]
    # One that breaks the rules is refused, as on the Equipment tab.
    three = {**RIFLE, "qualities": [*RIFLE["qualities"], {"name": "Fast"}]}
    assert troupe.assistant.client.put(path, json={"item": three}).status_code == 422
    assert give(troupe.assistant, response_id, item=three).status_code == 422
    # An item or a quality, never neither nor both.
    assert give(troupe.assistant, response_id).status_code == 422

    removed = troupe.assistant.client.delete(path)
    assert removed.status_code == 200, removed.text
    assert removed.json()["items"] == []
    troupe.assistant.client.put(f"/responses/{response_id}", json={"body": "Nothing comes of it."})
    troupe.assistant.client.post(f"/cycles/{scene.cycle['id']}/close")
    assert deliver(scene).json()["delivered"] == 1
    assert held(scene) == []
    assert "You received" not in results(scene)


def test_it_waits_for_its_response_to_be_delivered(scene: Scene) -> None:
    troupe = scene.troupe
    cycle_id = scene.cycle["id"]
    patrol = scene.response_for("Patrol the park")["id"]
    give(troupe.storyteller, patrol, item=RIFLE)
    feed_id = feed(scene)
    troupe.assistant.client.put(f"/responses/{feed_id}", json={"body": "You feed well."})
    troupe.assistant.client.post(f"/cycles/{cycle_id}/close")
    # Delivered in part, without the patrol's response: the rifle waits.
    assert deliver(scene).json()["delivered"] == 1
    assert held(scene) == []
    # Written later, it goes with the update.
    troupe.assistant.client.put(f"/responses/{patrol}", json={"body": "A rifle in the bushes."})
    assert deliver(scene).json() == {"delivered": 1, "updated": 1, "queued": 0}
    assert [i["name"] for i in held(scene)] == ["Sniper rifle"]
    assert "*You received:* Sniper rifle" in results(scene)

    # Added to a response already delivered, it shows as a change, and goes with the next.
    give(troupe.storyteller, feed_id, item=WATCH)
    [agnes] = troupe.assistant.client.get(f"/cycles/{cycle_id}/deliveries").json()["participants"]
    assert agnes["changed"] is True
    deliver(scene)
    assert sorted(i["name"] for i in held(scene)) == ["Pocket watch", "Sniper rifle"]


def test_a_quality_on_an_item_the_character_holds(scene: Scene) -> None:
    troupe = scene.troupe
    watch = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/equipment", json={**WATCH, "character_id": scene.agnes}
    ).json()
    response_id = feed(scene)
    quality = {"item_id": watch["id"], "name": "Antique"}
    added = give(troupe.storyteller, response_id, quality=quality)
    assert added.status_code == 201, added.text
    [row] = added.json()["items"]
    assert row["text"] == "Antique on Pocket watch"
    assert row["quality"]["item_name"] == "Pocket watch"
    # Not twice, and not one of another kind.
    assert give(troupe.storyteller, response_id, quality=quality).status_code == 422
    other = {"item_id": watch["id"], "name": "Silver"}
    assert give(troupe.storyteller, response_id, quality=other).status_code == 422

    troupe.assistant.client.put(f"/responses/{response_id}", json={"body": "It is very old."})
    troupe.assistant.client.post(f"/cycles/{scene.cycle['id']}/close")
    assert held(scene)[0]["qualities"] == []
    deliver(scene)
    [now] = held(scene)
    assert [q["name"] for q in now["qualities"]] == ["Antique"]
    assert "*You received:* Antique on Pocket watch" in results(scene)
    changed = history(scene, watch["id"])[-1]
    assert changed["action"] == "changed"
    assert changed["reason"] == "From the October 2026 downtime"
    assert changed["downtime"]["response_id"] == response_id


def test_something_that_cant_be_given_stops_the_delivery(scene: Scene) -> None:
    troupe = scene.troupe
    watch = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/equipment", json={**WATCH, "character_id": scene.agnes}
    ).json()
    response_id = feed(scene)
    [row] = give(
        troupe.storyteller, response_id, quality={"item_id": watch["id"], "name": "Stylish"}
    ).json()["items"]
    troupe.assistant.client.put(f"/responses/{response_id}", json={"body": "Polished."})
    troupe.assistant.client.post(f"/cycles/{scene.cycle['id']}/close")
    # The player discards the watch before the results go out.
    troupe.player.client.post(
        f"/characters/{scene.agnes}/equipment/{watch['id']}/discard", json={"note": "lost"}
    )
    stopped = deliver(scene)
    assert stopped.status_code == 409
    assert "Couldn't give Agnes Stylish on Pocket watch" in stopped.json()["detail"]
    assert troupe.player.client.get(f"/characters/{scene.agnes}/downtime/results").json() == []
    # Taken off the response, the results go.
    troupe.storyteller.client.delete(f"/responses/{response_id}/items/{row['id']}")
    assert deliver(scene).json()["delivered"] == 1


def test_who_gives_equipment_from_a_response(scene: Scene) -> None:
    troupe = scene.troupe
    response_id = feed(scene)
    # Narrators answer responses but never see the sheet: they don't give equipment.
    scene.assign("Feed at the docks", user_id=troupe.narrator.id)
    assert give(troupe.narrator, response_id, item=RIFLE).status_code == 403
    assert give(troupe.player, response_id, item=RIFLE).status_code == 403
    assert give(troupe.stranger, response_id, item=RIFLE).status_code == 403
    [row] = give(troupe.lead, response_id, item=RIFLE).json()["items"]
    path = f"/responses/{response_id}/items/{row['id']}"
    assert troupe.narrator.client.delete(path).status_code == 403
    assert troupe.narrator.client.put(path, json={"item": WATCH}).status_code == 403

    # The narrator sees what it gives, as the player will, but not how it was built.
    read = troupe.narrator.client.get(f"/responses/{response_id}").json()
    assert read["can_give"] is False
    [seen] = read["items"]
    assert seen["text"] == "Sniper rifle (Accurate, Long Range)"
    assert seen["item"] is None
    mine = troupe.narrator.client.get(f"/cycles/{scene.cycle['id']}/responses/mine").json()
    assert [i["items"][0]["item"] for i in mine] == [None]
    assert troupe.lead.client.get(f"/responses/{response_id}").json()["can_give"] is True
    # A quality goes only on an item this character holds.
    gone = {"item_id": row["id"], "name": "Antique"}
    assert give(troupe.lead, response_id, quality=gone).status_code == 422

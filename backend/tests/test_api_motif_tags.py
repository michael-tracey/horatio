"""Theme and mood tags on scenes and quests (issue #880): a troupe's running staff tag
its scenes and quests with the themes and moods of its Setting Style Document, and
see which the chronicle touches and how often. Players never see a tag, and tagging
changes nothing in the document."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_downtimes import member_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def entry(troupe: Troupe, kind: str, name: str = "", description: str = "") -> str:
    """Add a theme, mood or note to the troupe's setting; its id."""
    setting = ok(
        troupe.lead.client.post(
            f"/troupes/{troupe.id}/setting/entries",
            json={"kind": kind, "name": name, "description": description},
        ),
        201,
    )
    return next(
        e["id"]
        for e in setting[f"{kind}s"]
        if (e["name"] == name if name else e["description"] == description)
    )


def new_scene(troupe: Troupe, name: str) -> str:
    return ok(
        troupe.storyteller.client.post(f"/troupes/{troupe.id}/scenes", json={"name": name}), 201
    )["id"]


def new_quest(troupe: Troupe, name: str, **body: Any) -> str:
    return ok(
        troupe.storyteller.client.post(f"/troupes/{troupe.id}/quests", json={"name": name, **body}),
        201,
    )["id"]


def tag_scene(person: Person, troupe: Troupe, scene_id: str, *ids: str) -> Any:
    return person.client.put(f"/troupes/{troupe.id}/scenes/{scene_id}/tags", json={"ids": ids})


def tag_quest(person: Person, quest_id: str, *ids: str) -> Any:
    return person.client.put(f"/quests/{quest_id}/tags", json={"ids": ids})


def names(tags: list[dict[str, Any]]) -> list[str]:
    return [t["name"] for t in tags]


def touched(person: Person, troupe: Troupe) -> list[tuple[str, str, list[str], list[str]]]:
    found = ok(person.client.get(f"/troupes/{troupe.id}/setting/tags"))
    return [(m["kind"], m["name"], names(m["scenes"]), names(m["quests"])) for m in found]


def test_staff_tag_scenes_and_quests_and_see_which_themes_the_chronicle_touches(
    troupe: Troupe,
) -> None:
    betrayal = entry(troupe, "theme", "Betrayal")
    rebirth = entry(troupe, "theme", "Rebirth")
    brooding = entry(troupe, "mood", "Brooding")
    entry(troupe, "mood", "Festive")
    ballroom = new_scene(troupe, "Elysium ballroom")
    docks = new_scene(troupe, "The docks")
    journal = new_quest(troupe, "The Lost Journal")

    # Any running staff member tags, in the troupe's order whatever the order given.
    scene = ok(tag_scene(troupe.assistant, troupe, ballroom, brooding, betrayal, betrayal))
    assert [(t["kind"], t["name"]) for t in scene["tags"]] == [
        ("theme", "Betrayal"),
        ("mood", "Brooding"),
    ]
    assert names(ok(tag_scene(troupe.lead, troupe, docks, betrayal))["tags"]) == ["Betrayal"]
    quest = ok(tag_quest(troupe.storyteller, journal, rebirth, betrayal))
    assert names(quest["tags"]) == ["Betrayal", "Rebirth"]
    assert quest["can_tag"] is True
    reread = ok(troupe.storyteller.client.get(f"/troupes/{troupe.id}/scenes/{ballroom}"))
    assert names(reread["tags"]) == ["Betrayal", "Brooding"]
    assert names(ok(troupe.assistant.client.get(f"/quests/{journal}"))["tags"]) == [
        "Betrayal",
        "Rebirth",
    ]

    # Every theme, then every mood, with what touches it; Festive, nothing yet.
    assert touched(troupe.assistant, troupe) == [
        ("theme", "Betrayal", ["Elysium ballroom", "The docks"], ["The Lost Journal"]),
        ("theme", "Rebirth", [], ["The Lost Journal"]),
        ("mood", "Brooding", ["Elysium ballroom"], []),
        ("mood", "Festive", [], []),
    ]

    # Tagging again replaces the tags; with none, it has none.
    assert names(ok(tag_scene(troupe.storyteller, troupe, ballroom, brooding))["tags"]) == [
        "Brooding"
    ]
    assert ok(tag_quest(troupe.storyteller, journal))["tags"] == []
    assert touched(troupe.lead, troupe)[:2] == [
        ("theme", "Betrayal", ["The docks"], []),
        ("theme", "Rebirth", [], []),
    ]

    # The scene's tags go in the troupe log; the quest's in its own.
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert any("tagged the scene Elysium ballroom: Brooding." in m for m in log)
    quest_log = [e["text"] for e in ok(troupe.lead.client.get(f"/quests/{journal}"))["log"]]
    assert quest_log[:2] == ["tagged it: no themes or moods", "tagged it: Betrayal, Rebirth"]


def test_only_the_troupes_own_themes_and_moods_are_tags(troupe: Troupe) -> None:
    note = entry(troupe, "note", description="Keep the Prince offstage.")
    scene = new_scene(troupe, "Haven")
    other = ok(
        troupe.custodian.client.post(
            "/troupes", json={"name": "Other Nights", "lead_handle": troupe.lead.handle}
        ),
        201,
    )["id"]
    theirs = ok(
        troupe.lead.client.post(
            f"/troupes/{other}/setting/entries", json={"kind": "theme", "name": "Hate"}
        ),
        201,
    )["themes"][0]["id"]
    for ids in ([note], [theirs], ["00000000-0000-0000-0000-000000000000"]):
        refused = tag_scene(troupe.storyteller, troupe, scene, *ids)
        assert refused.status_code == 422, refused.text
        assert "the troupe's own themes and moods" in refused.json()["detail"]


def test_removing_a_theme_or_a_scene_removes_its_tags(troupe: Troupe) -> None:
    betrayal = entry(troupe, "theme", "Betrayal")
    brooding = entry(troupe, "mood", "Brooding")
    ballroom = new_scene(troupe, "Ballroom")
    journal = new_quest(troupe, "Journal")
    ok(tag_scene(troupe.storyteller, troupe, ballroom, betrayal, brooding))
    ok(tag_quest(troupe.storyteller, journal, betrayal))

    ok(troupe.lead.client.delete(f"/troupes/{troupe.id}/setting/entries/{betrayal}"))
    scene = ok(troupe.storyteller.client.get(f"/troupes/{troupe.id}/scenes/{ballroom}"))
    assert names(scene["tags"]) == ["Brooding"]
    assert ok(troupe.storyteller.client.get(f"/quests/{journal}"))["tags"] == []
    assert touched(troupe.lead, troupe) == [("mood", "Brooding", ["Ballroom"], [])]

    removed = troupe.storyteller.client.delete(f"/troupes/{troupe.id}/scenes/{ballroom}")
    assert removed.status_code == 204, removed.text
    assert touched(troupe.lead, troupe) == [("mood", "Brooding", [], [])]


def test_tagging_is_not_a_change_to_the_setting(troupe: Troupe) -> None:
    betrayal = entry(troupe, "theme", "Betrayal")
    scene = new_scene(troupe, "Ballroom")
    quest = new_quest(troupe, "Journal")
    before = ok(troupe.player.client.get(f"/troupes/{troupe.id}/setting"))
    log_before = troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()

    ok(tag_scene(troupe.storyteller, troupe, scene, betrayal))
    ok(tag_quest(troupe.storyteller, quest, betrayal))

    assert ok(troupe.player.client.get(f"/troupes/{troupe.id}/setting")) == before
    added = troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()[: -len(log_before)]
    assert [e["action"] for e in added] == ["scene.tagged"]
    # Tagging with the tags it has already changes nothing, and logs nothing.
    ok(tag_scene(troupe.storyteller, troupe, scene, betrayal))
    assert len(troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()) == len(log_before) + 1


def test_players_never_see_or_set_tags(troupe: Troupe, session: Session) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    ok(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/quest-settings",
            json={"enabled": True, "requests_per_cycle": 1},
        )
    )
    betrayal = entry(troupe, "theme", "Betrayal")
    scene = new_scene(troupe, "Ballroom")
    quest = new_quest(troupe, "Journal", leader_id=agnes)
    ok(tag_scene(troupe.storyteller, troupe, scene, betrayal))
    ok(tag_quest(troupe.storyteller, quest, betrayal))
    ok(
        troupe.storyteller.client.post(
            f"/quests/{quest}/requirements",
            json={"options": [{"kind": "text", "text": "Access to Miles' journal"}]},
        ),
        201,
    )
    ok(troupe.storyteller.client.post(f"/quests/{quest}/send"))

    for person in (troupe.player, troupe.stranger):
        assert person.client.get(f"/troupes/{troupe.id}/setting/tags").status_code == 403
        assert tag_scene(person, troupe, scene).status_code == 403
        assert tag_quest(person, quest).status_code in (403, 404)
    # The player's own quest says nothing of its tags.
    mine = ok(troupe.player.client.get(f"/characters/{agnes}/quests/{quest}"))
    assert "tags" not in mine and "Betrayal" not in str(mine)
    assert "Betrayal" not in str(ok(troupe.player.client.get(f"/characters/{agnes}/quests")))
    # Nor does the document.
    assert "tags" not in ok(troupe.player.client.get(f"/troupes/{troupe.id}/setting"))

    # A narrator tags nothing and has no overview.
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/setting/tags").status_code == 403
    assert tag_scene(troupe.narrator, troupe, scene).status_code == 403
    assert tag_quest(troupe.narrator, quest).status_code in (403, 404)
    # Unchanged by any of it.
    assert names(ok(troupe.storyteller.client.get(f"/quests/{quest}"))["tags"]) == ["Betrayal"]

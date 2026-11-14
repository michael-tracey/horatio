"""A troupe's story bible (issue #879): the staff-only companion to the Setting Style
Document, bringing together its chronicle, NPCs and locations, with notes staff keep
for themselves. Its running staff read and keep it; players never do."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_chronicle import embraced


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def bible(person: Person, troupe: Troupe) -> dict[str, Any]:
    response = person.client.get(f"/troupes/{troupe.id}/story-bible")
    assert response.status_code == 200, response.text
    return response.json()


def add(person: Person, troupe: Troupe, **body: Any) -> Any:
    return person.client.post(f"/troupes/{troupe.id}/story-bible/notes", json=body)


def titles(found: dict[str, Any]) -> list[str]:
    return [n["title"] for n in found["notes"]]


def log(troupe: Troupe) -> list[str]:
    return [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]


def test_running_staff_keep_notes_in_the_order_they_choose(troupe: Troupe) -> None:
    made = add(troupe.assistant, troupe, title="The Prince's secret", body="She is *Tremere*.")
    assert made.status_code == 201, made.text
    add(troupe.storyteller, troupe, title="Who killed the Sheriff")
    found = bible(troupe.lead, troupe)
    assert titles(found) == ["The Prince's secret", "Who killed the Sheriff"]
    assert found["notes"][0]["body"] == "She is *Tremere*."
    secret, sheriff = (n["id"] for n in found["notes"])

    base = f"/troupes/{troupe.id}/story-bible"
    changed = troupe.lead.client.put(
        f"{base}/notes/{secret}", json={"title": "The Prince's secrets", "body": "Two."}
    )
    assert changed.status_code == 200, changed.text
    ordered = troupe.lead.client.put(f"{base}/order", json={"ids": [sheriff, secret]})
    assert titles(ordered.json()) == ["Who killed the Sheriff", "The Prince's secrets"]
    assert troupe.lead.client.put(f"{base}/order", json={"ids": [sheriff]}).status_code == 422
    assert add(troupe.lead, troupe, title="  ", body="No title").status_code == 422

    removed = troupe.storyteller.client.delete(f"{base}/notes/{sheriff}")
    assert titles(removed.json()) == ["The Prince's secrets"]

    assert log(troupe)[:5] == [
        "storyteller removed the note Who killed the Sheriff from the story bible.",
        "lead put the story bible's notes in order: Who killed the Sheriff, The Prince's secrets.",
        "lead changed the story bible's note The Prince's secrets.",
        "storyteller added the note Who killed the Sheriff to the story bible.",
        "assistant added the note The Prince's secret to the story bible.",
    ]


def test_it_brings_together_the_chronicle_npcs_and_locations(troupe: Troupe) -> None:
    npc = troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Elder Ravel"})
    assert npc.status_code == 201, npc.text
    agnes = new_character(troupe, troupe.player, "Agnes")
    embraced(troupe, agnes, date(1791, 3, 1))
    base = f"/troupes/{troupe.id}/locations"
    for body in (
        {"name": "The Rookery", "rating": 3, "control": "named", "controller_name": "The Sheriff"},
        {"name": "Asylum", "rating": 1, "description": "Elysium, of a sort."},
    ):
        made = troupe.storyteller.client.post(base, json=body)
        assert made.status_code == 201, made.text

    found = bible(troupe.assistant, troupe)
    assert [n["name"] for n in found["npcs"]] == ["Elder Ravel"]
    assert ("embrace", "Agnes") in {(e["kind"], e["character_name"]) for e in found["chronology"]}
    assert ("arrival", "Elder Ravel") in {
        (e["kind"], e["character_name"]) for e in found["chronology"]
    }
    assert [(loc["name"], loc["controller"], loc["description"]) for loc in found["locales"]] == [
        ("Asylum", None, "Elysium, of a sort."),
        ("The Rookery", "The Sheriff", ""),
    ]


def test_players_and_narrators_never_reach_it(troupe: Troupe) -> None:
    note = add(troupe.lead, troupe, title="Hidden plot", body="The Prince is a Baali.").json()
    note_id = note["notes"][0]["id"]
    base = f"/troupes/{troupe.id}/story-bible"
    new_character(troupe, troupe.player, "Agnes")
    for person in (troupe.player, troupe.narrator, troupe.stranger):
        assert person.client.get(base).status_code == 403
        assert add(person, troupe, title="Mine now").status_code == 403
        assert person.client.put(f"{base}/notes/{note_id}", json={"title": "x"}).status_code == 403
        assert person.client.delete(f"{base}/notes/{note_id}").status_code == 403
        assert person.client.put(f"{base}/order", json={"ids": [note_id]}).status_code == 403
    signed_out = troupe.client_for()
    assert signed_out.get(base).status_code == 401
    assert titles(bible(troupe.lead, troupe)) == ["Hidden plot"]

    # Nor is it any part of the Setting Style Document players read.
    setting = troupe.player.client.get(f"/troupes/{troupe.id}/setting")
    assert setting.status_code == 200, setting.text
    assert "Hidden plot" not in setting.text and "Baali" not in setting.text


def test_a_note_of_another_troupe_is_not_found(troupe: Troupe) -> None:
    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Barons of Dusk", "lead_handle": troupe.storyteller.handle}
    ).json()
    theirs = add(troupe.storyteller, troupe, title="Ours").json()["notes"][0]["id"]
    response = troupe.storyteller.client.delete(
        f"/troupes/{other['id']}/story-bible/notes/{theirs}"
    )
    assert response.status_code == 404

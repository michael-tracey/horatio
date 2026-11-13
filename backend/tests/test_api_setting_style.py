"""A troupe's Setting Style Document (issue #770): its running staff write the
subtitle, teaser and scope, and keep its themes, moods and storyteller notes as
entries of their own, in the order they choose; anyone signed in reads it."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def read(person: Person, troupe: Troupe) -> dict[str, Any]:
    response = person.client.get(f"/troupes/{troupe.id}/setting")
    assert response.status_code == 200, response.text
    return response.json()


def add(person: Person, troupe: Troupe, kind: str, **body: Any) -> Any:
    return person.client.post(f"/troupes/{troupe.id}/setting/entries", json={"kind": kind, **body})


def order(person: Person, troupe: Troupe, kind: str, ids: list[str]) -> Any:
    return person.client.put(f"/troupes/{troupe.id}/setting/order", json={"kind": kind, "ids": ids})


def names(entries: list[dict[str, Any]]) -> list[str]:
    return [e["name"] or e["description"] for e in entries]


def log(troupe: Troupe) -> list[str]:
    return [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]


def test_the_book_samples_are_its_themes_and_moods_with_their_pages(troupe: Troupe) -> None:
    presets = troupe.player.client.get("/setting-presets").json()
    themes = [(p["name"], p["page"]) for p in presets if p["kind"] == "theme"]
    moods = [(p["name"], p["page"]) for p in presets if p["kind"] == "mood"]
    assert themes == [
        (name, 325)
        for name in ("Love", "Hate", "Betrayal", "Revenge", "Rebellion", "Morality", "Chaos")
    ]
    assert moods == [
        ("Covetous", 325),
        ("Desperate", 325),
        ("Brooding", 326),
        ("Mysterious", 326),
        ("Festive", 326),
        ("Bitter", 326),
        ("Decadent", 326),
        ("Exciting", 326),
    ]
    assert all(p["description"] for p in presets)


def test_running_staff_keep_the_entries_and_players_read_them(troupe: Troupe) -> None:
    betrayal = add(
        troupe.lead,
        troupe,
        "theme",
        name="Betrayal",
        description="Who will sell out the Prince?",
        book_key="betrayal",
    )
    assert betrayal.status_code == 201, betrayal.text
    assert add(troupe.storyteller, troupe, "theme", name="  Rebirth  ").status_code == 201
    assert (
        add(troupe.assistant, troupe, "mood", name="Rain-soaked", description="Grey and *cold*.")
    ).status_code == 201
    assert add(troupe.assistant, troupe, "mood", book_key="brooding", name="Brooding").status_code
    note = add(
        troupe.lead,
        troupe,
        "note",
        name="ignored",
        description="Characters are at most ten years past the Embrace.",
    )
    assert note.status_code == 201, note.text

    seen = read(troupe.player, troupe)
    assert names(seen["themes"]) == ["Betrayal", "Rebirth"]
    assert names(seen["moods"]) == ["Rain-soaked", "Brooding"]
    assert seen["notes"] == [
        {
            "id": seen["notes"][0]["id"],
            "kind": "note",
            "name": "",
            "description": "Characters are at most ten years past the Embrace.",
            "book_key": None,
            "page": None,
        }
    ]
    assert seen["themes"][0] == {
        "id": seen["themes"][0]["id"],
        "kind": "theme",
        "name": "Betrayal",
        "description": "Who will sell out the Prince?",
        "book_key": "betrayal",
        "page": 325,
    }
    assert seen["can_edit"] is False
    assert read(troupe.assistant, troupe)["can_edit"] is True
    assert read(troupe.narrator, troupe)["can_edit"] is False

    # Narrators and players read it but don't write it.
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert add(person, troupe, "theme", name="Hope").status_code == 403

    # Each book sample once; a theme needs a name and a note its text.
    assert add(troupe.lead, troupe, "theme", name="Again", book_key="betrayal").status_code == 422
    assert add(troupe.lead, troupe, "theme", name="Hope", book_key="hope").status_code == 422
    assert add(troupe.lead, troupe, "mood", name="Hope", book_key="love").status_code == 422
    assert add(troupe.lead, troupe, "note", description="x", book_key="love").status_code == 422
    assert add(troupe.lead, troupe, "theme", name="  ").status_code == 422
    assert add(troupe.lead, troupe, "note", description="  ").status_code == 422

    assert log(troupe)[:3] == [
        "lead added the storyteller note Characters are at most ten years past the Embrace."
        " to the setting.",
        "assistant added the mood Brooding to the setting.",
        "assistant added the mood Rain-soaked to the setting.",
    ]


def test_staff_reorder_change_and_remove_entries(troupe: Troupe) -> None:
    for name in ("Love", "Hate", "Chaos"):
        assert add(troupe.lead, troupe, "theme", name=name).status_code == 201
    assert add(troupe.lead, troupe, "mood", name="Bitter").status_code == 201
    love, hate, chaos = (e["id"] for e in read(troupe.lead, troupe)["themes"])
    (bitter,) = (e["id"] for e in read(troupe.lead, troupe)["moods"])

    # Every one of the kind, once each.
    assert order(troupe.assistant, troupe, "theme", [chaos, love]).status_code == 422
    assert order(troupe.assistant, troupe, "theme", [chaos, love, love]).status_code == 422
    assert order(troupe.assistant, troupe, "theme", [chaos, love, bitter]).status_code == 422
    assert order(troupe.player, troupe, "theme", [chaos, love, hate]).status_code == 403
    moved = order(troupe.assistant, troupe, "theme", [chaos, love, hate])
    assert moved.status_code == 200, moved.text
    assert names(moved.json()["themes"]) == ["Chaos", "Love", "Hate"]
    # And again, swapping two places that were taken.
    assert names(order(troupe.lead, troupe, "theme", [love, chaos, hate]).json()["themes"]) == [
        "Love",
        "Chaos",
        "Hate",
    ]

    changed = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/setting/entries/{hate}",
        json={"name": "Hatred", "description": "What does it cost?"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["themes"][2]["description"] == "What does it cost?"
    removed = troupe.lead.client.delete(f"/troupes/{troupe.id}/setting/entries/{chaos}")
    assert removed.status_code == 200, removed.text
    assert names(removed.json()["themes"]) == ["Love", "Hatred"]
    # Added after a removal, it goes last.
    assert names(add(troupe.lead, troupe, "theme", name="Hope").json()["themes"]) == [
        "Love",
        "Hatred",
        "Hope",
    ]

    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Elsewhere", "lead_handle": troupe.lead.handle}
    ).json()
    assert (
        troupe.lead.client.delete(f"/troupes/{other['id']}/setting/entries/{bitter}").status_code
        == 404
    )

    assert log(troupe)[:4] == [
        "lead added the theme Hope to the setting.",
        "lead removed the theme Chaos from the setting.",
        "storyteller changed the setting's theme Hatred.",
        "lead put the setting's themes in order: Love, Chaos, Hate.",
    ]


def test_the_text_and_scope_with_the_profile_s_name_and_city(troupe: Troupe) -> None:
    profile = troupe.lead.client.put(
        f"/troupes/{troupe.id}/profile",
        json={"setting": {"chronicle": "Leeds by Night", "city": "Leeds", "era": "Modern"}},
    )
    assert profile.status_code == 200, profile.text
    saved = troupe.assistant.client.put(
        f"/troupes/{troupe.id}/setting",
        json={
            "subtitle": " A City Under Siege ",
            "teaser": "The river rose, and **something** came with it.",
            "power": "Neonates and ancillae.",
            "agency": "",
        },
    )
    assert saved.status_code == 200, saved.text
    seen = read(troupe.player, troupe)
    parts = ("chronicle", "locale", "subtitle", "teaser", "power", "agency")
    assert {k: seen[k] for k in parts} == {
        "chronicle": "Leeds by Night",
        "locale": "Leeds",
        "subtitle": "A City Under Siege",
        "teaser": "The river rose, and **something** came with it.",
        "power": "Neonates and ancillae.",
        "agency": "",
    }
    again = troupe.lead.client.put(
        f"/troupes/{troupe.id}/setting",
        json={
            "subtitle": "A City Under Siege",
            "teaser": "The river rose, and **something** came with it.",
            "power": "Neonates and ancillae.",
            "agency": "The city, no further.",
        },
    )
    assert again.status_code == 200
    assert troupe.narrator.client.put(f"/troupes/{troupe.id}/setting", json={}).status_code == 403
    assert log(troupe)[:2] == [
        "lead changed the setting's agency.",
        "assistant changed the setting's subtitle, teaser and power.",
    ]

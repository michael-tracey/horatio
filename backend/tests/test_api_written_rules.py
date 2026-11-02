"""A troupe's written house rules (issue #434): its storytellers add, edit, reorder and
delete them; its players read them by section, in the rules browser and on a linked
trait's details; and its profile shows them when staff choose."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def add(person: Person, troupe: Troupe, title: str, **more: Any) -> Any:
    return person.client.post(f"/troupes/{troupe.id}/written-rules", json={"title": title, **more})


def change(person: Person, troupe: Troupe, rule_id: str, **body: Any) -> Any:
    return person.client.put(f"/troupes/{troupe.id}/written-rules/{rule_id}", json=body)


def read(person: Person, troupe: Troupe) -> dict[str, Any]:
    response = person.client.get(f"/troupes/{troupe.id}/written-rules")
    assert response.status_code == 200, response.text
    return response.json()


def titles(person: Person, troupe: Troupe) -> list[tuple[str, str]]:
    return [(r["section"], r["title"]) for r in read(person, troupe)["rules"]]


def rule_id(person: Person, troupe: Troupe, title: str) -> str:
    return next(r["id"] for r in read(person, troupe)["rules"] if r["title"] == title)


def log(troupe: Troupe) -> list[str]:
    return [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]


def test_storytellers_keep_the_list_and_players_read_it_by_section(troupe: Troupe) -> None:
    harpy = add(
        troupe.lead,
        troupe,
        "  The Harpy vote  ",
        section="Status",
        body="The Harpies vote **openly**, at court.",
    )
    assert harpy.status_code == 201, harpy.text
    for title, section in (
        ("Crafts difficulties", "Skills"),
        ("Noticing mental and social attacks", "Disciplines"),
        ("Titles above Prince", "Status"),
        ("Welcome", ""),
        ("Performance difficulties", "Skills"),
    ):
        assert add(troupe.storyteller, troupe, title, section=section).status_code == 201

    # The rules with no section first, then by section, each in the order added.
    assert titles(troupe.player, troupe) == [
        ("", "Welcome"),
        ("Disciplines", "Noticing mental and social attacks"),
        ("Skills", "Crafts difficulties"),
        ("Skills", "Performance difficulties"),
        ("Status", "The Harpy vote"),
        ("Status", "Titles above Prince"),
    ]
    first = read(troupe.player, troupe)["rules"][4]
    assert first["body"] == "The Harpies vote **openly**, at court."
    assert (first["trait"], first["page"]) == (None, None)

    # Reordered within its section only.
    performance = rule_id(troupe.lead, troupe, "Performance difficulties")
    assert change(troupe.lead, troupe, performance, title="x", move="up").status_code == 200
    assert change(troupe.lead, troupe, performance, title="x", move="up").status_code == 200
    skills = [t for s, t in titles(troupe.player, troupe) if s == "Skills"]
    assert skills == ["Performance difficulties", "Crafts difficulties"]

    # Moved to another section, it goes last there; edited, its words change.
    changed = change(
        troupe.lead,
        troupe,
        performance,
        title="Performance and Crafts",
        section="Status",
        body="As Crafts.",
    )
    assert changed.status_code == 200, changed.text
    assert [t for s, t in titles(troupe.player, troupe) if s == "Status"] == [
        "The Harpy vote",
        "Titles above Prince",
        "Performance and Crafts",
    ]

    welcome = rule_id(troupe.lead, troupe, "Welcome")
    gone = troupe.lead.client.delete(f"/troupes/{troupe.id}/written-rules/{welcome}")
    assert gone.status_code == 204
    assert ("", "Welcome") not in titles(troupe.player, troupe)

    assert log(troupe)[:5] == [
        "lead deleted the written rule Welcome.",
        "lead changed the written rule Performance and Crafts.",
        "lead moved the written rule Performance difficulties up.",
        "storyteller added the written rule Performance difficulties (Skills).",
        "storyteller added the written rule Welcome (no section).",
    ]


def test_only_storytellers_change_them(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    made = add(troupe.lead, troupe, "Influence by county", section="Influence")
    rule = made.json()["rules"][0]["id"]
    for person in (troupe.assistant, troupe.narrator, troupe.player, troupe.stranger):
        assert add(person, troupe, "Mine").status_code == 403
        assert change(person, troupe, rule, title="Mine").status_code == 403
        deleted = person.client.delete(f"/troupes/{troupe.id}/written-rules/{rule}")
        assert deleted.status_code == 403
        assert read(person, troupe)["rules"][0]["title"] == "Influence by county"
    # Not signed in: nothing.
    assert client_for().get(f"/troupes/{troupe.id}/written-rules").status_code == 401

    # Another troupe's storytellers cannot reach this troupe's rule through their own.
    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Court of Ash", "lead_handle": troupe.stranger.handle}
    ).json()["id"]
    path = f"/troupes/{other}/written-rules/{rule}"
    assert troupe.stranger.client.put(path, json={"title": "Mine"}).status_code == 404
    assert troupe.stranger.client.delete(path).status_code == 404

    assert add(troupe.lead, troupe, "   ").status_code == 422


def test_a_rule_linked_to_a_trait_shows_on_its_details_and_in_the_rules_browser(
    troupe: Troupe,
) -> None:
    linked = add(
        troupe.lead,
        troupe,
        "Royalty and acquired items",
        section="Disciplines",
        body="Applies to items the character *bought*.",
        trait={"category": "merits", "name": "Lucky"},
        page="Vol. 2, p. 50",
    )
    assert linked.status_code == 201, linked.text
    rule = linked.json()["rules"][0]
    assert rule["trait"] == {"splat": "vampire", "category": "merits", "name": "Lucky"}
    assert rule["page"] == "Vol. 2, p. 50"
    missing = add(troupe.lead, troupe, "Nope", trait={"category": "merits", "name": "Nonesuch"})
    assert missing.status_code == 422
    assert missing.json()["detail"] == "There is no merits trait called 'Nonesuch' to link to."

    catalogue = troupe.player.client.get(
        "/rules/vampire", params={"troupe_id": troupe.id, "category": "merits"}
    ).json()
    lucky = next(t for t in catalogue["traits"] if t["name"] == "Lucky")
    assert lucky["written_rules"] == [{"id": rule["id"], "title": "Royalty and acquired items"}]
    assert (
        next(t for t in catalogue["traits"] if t["name"] == "Code of Honor")["written_rules"] == []
    )
    # Without the troupe, the book's alone.
    book = troupe.player.client.get("/rules/vampire", params={"category": "merits"}).json()
    assert next(t for t in book["traits"] if t["name"] == "Lucky")["written_rules"] == []

    browsed = troupe.player.client.get(
        "/rules/vampire/browse", params={"troupe_id": troupe.id}
    ).json()
    assert [r["title"] for r in browsed["written_rules"]] == ["Royalty and acquired items"]
    assert troupe.player.client.get("/rules/vampire/browse").json()["written_rules"] == []

    # The link can be taken off.
    unlinked = change(troupe.lead, troupe, rule["id"], title="Royalty and acquired items")
    assert unlinked.json()["rules"][0]["trait"] is None


def test_the_profile_shows_them_only_when_staff_choose(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    assert add(troupe.lead, troupe, "Our FAQ", section="FAQ", body="Ask us.").status_code == 201
    visitor = client_for()
    profile = troupe.player.client.get(f"/troupes/{troupe.id}/profile").json()
    assert profile["written_rules"] == []
    assert read(troupe.player, troupe)["public"] is False

    path = f"/troupes/{troupe.id}/written-rules-public"
    assert troupe.assistant.client.put(path, json={"public": True}).status_code == 403
    shown = troupe.lead.client.put(path, json={"public": True})
    assert shown.status_code == 200, shown.text
    assert shown.json()["public"] is True
    profile = troupe.player.client.get(f"/troupes/{troupe.id}/profile").json()
    assert [r["title"] for r in profile["written_rules"]] == ["Our FAQ"]
    # A private profile stays private; a public one shows them to anyone.
    assert visitor.get(f"/troupes/{troupe.id}/profile").status_code == 404
    public = troupe.lead.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": True})
    assert public.status_code == 200
    seen = visitor.get(f"/troupes/{troupe.id}/profile").json()
    assert [r["body"] for r in seen["written_rules"]] == ["Ask us."]

    assert troupe.lead.client.put(path, json={"public": False}).status_code == 200
    assert visitor.get(f"/troupes/{troupe.id}/profile").json()["written_rules"] == []
    messages = log(troupe)
    assert messages[0] == "lead set the troupe's profile so it no longer shows its written rules."
    assert "lead set the troupe's profile so it shows its written rules." in messages

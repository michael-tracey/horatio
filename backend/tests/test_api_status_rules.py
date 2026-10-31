"""The status rules page (#340): every status of the troupe's sects and the general
status, by sect, with its type, what it does, and where it comes from in the troupe:
its titles (the rule sets' and its own), social ages, factions and merits."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def rules_of(troupe: Troupe) -> dict[str, Any]:
    response = troupe.assistant.client.get(f"/troupes/{troupe.id}/status-rules")
    assert response.status_code == 200, response.text
    return response.json()


def statuses(rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["name"]: r for s in rules["sects"] for r in s["statuses"]}


def given_by(rule: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [(g["kind"], g["name"], g["condition"]) for g in rule["given_by"]]


def test_every_status_by_sect_with_what_it_does_and_where_it_comes_from(troupe: Troupe) -> None:
    rules = rules_of(troupe)

    assert [s["sect"] for s in rules["sects"]] == [
        "General",
        "Anarch",
        "Camarilla",
        "Independent Alliance",
        "Sabbat",
    ]
    assert rules["caps"] == {
        "abiding_sources": 1,
        "fleeting": 5,
        "lesser_ban": 3,
        "greater_ban": 1,
        "page": "313",
    }
    camarilla = next(s for s in rules["sects"] if s["sect"] == "Camarilla")
    assert (camarilla["accepted"], camarilla["page"]) == ("Acknowledged", "400")
    # The Accepted first, then abiding, innate, fleeting and negative status.
    types = [r["type"] for r in camarilla["statuses"]]
    assert types[0] == "Accepted"
    assert types == sorted(
        types, key=["Accepted", "Abiding", "Innate", "Fleeting", "Negative"].index
    )

    found = statuses(rules)
    noble = found["Noble"]
    assert (noble["type"], noble["sect"], noble["page"]) == ("Abiding", "Camarilla", "401")
    assert noble["passive"] and noble["source"]
    assert given_by(noble) == [
        ("title", "Archon", ""),
        ("title", "Seneschal", ""),
        ("title", "Primogen", ""),
        ("title", "Whip", "while the Primogen is absent"),
        ("title", "Harpy", ""),
    ]
    harpy = next(g for g in noble["given_by"] if g["name"] == "Harpy")
    assert (harpy["aliases"], harpy["page"], harpy["house"]) == (["Master Harpy"], "379", False)
    assert ("title", "Bishop", "one of Blessed or Enforcer, chosen each game") in given_by(
        found["Blessed"]
    )
    assert given_by(found["Confirmed"]) == [
        ("social_age", "Ancilla", ""),
        ("social_age", "Elder", ""),
    ]
    assert given_by(found["Loyalist"]) == [("faction", "Loyalist", "")]
    assert given_by(found["Loyal"]) == [("merit", "Prestigious Sire", "")]
    # Fleeting and negative status is given by people, not by a title.
    assert found["Triumphant"]["given_by"] == []
    assert found["Warned"]["duration"]

    chairman = found["Chairman"]
    assert (chairman["no_rules_yet"], chairman["passive"], chairman["page"]) == (True, "", None)


def test_a_troupe_sees_its_sects_and_its_own_titles(troupe: Troupe) -> None:
    limited = troupe.lead.client.patch(f"/troupes/{troupe.id}", json={"allowed_sects": ["Anarch"]})
    assert limited.status_code == 200, limited.text
    made = troupe.assistant.client.post(
        f"/troupes/{troupe.id}/titles",
        json={"name": "Speaker", "sect": "Anarch", "status": ["Moniker"]},
    )
    assert made.status_code == 201, made.text

    rules = rules_of(troupe)

    assert [s["sect"] for s in rules["sects"]] == ["General", "Anarch"]
    found = statuses(rules)
    assert "Noble" not in found
    speaker = next(g for g in found["Moniker"]["given_by"] if g["name"] == "Speaker")
    assert (speaker["kind"], speaker["house"]) == ("title", True)
    # The Camarilla's titles and social ages give nothing in an Anarch troupe.
    assert given_by(found["Authority"]) == [("title", "Baron", "")]
    assert given_by(found["Established"]) == [("title", "Ambassador", "")]


def test_only_running_staff_see_the_status_rules(troupe: Troupe) -> None:
    for person in (troupe.player, troupe.stranger, troupe.narrator):
        response = person.client.get(f"/troupes/{troupe.id}/status-rules")
        assert response.status_code in (403, 404), (person, response.text)
    assert troupe.storyteller.client.get(f"/troupes/{troupe.id}/status-rules").status_code == 200

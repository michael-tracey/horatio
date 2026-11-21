"""The tabs of a troupe's page a person opened last there (issue #1048), kept on their
account, so they follow the person from one device to another."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_characters import join


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def recent(person: Person, troupe: Troupe) -> list[str]:
    response = person.client.get(f"/troupes/{troupe.id}/recent-tabs")
    assert response.status_code == 200, response.text
    return response.json()["tabs"]


def keep(person: Person, troupe: Troupe, tabs: list[str]) -> list[str]:
    response = person.client.put(f"/troupes/{troupe.id}/recent-tabs", json={"tabs": tabs})
    assert response.status_code == 200, response.text
    return response.json()["tabs"]


def test_the_last_tabs_are_kept_for_each_person_and_troupe(troupe: Troupe) -> None:
    assert recent(troupe.lead, troupe) == []
    assert keep(troupe.lead, troupe, ["/approvals", "", "/roster"]) == ["/approvals", "", "/roster"]
    assert keep(troupe.lead, troupe, ["/downtimes", "/approvals", "", "/roster"]) == [
        "/downtimes",
        "/approvals",
        "",
        "/roster",
    ]
    assert recent(troupe.lead, troupe)[0] == "/downtimes"
    # Each person has their own.
    assert recent(troupe.storyteller, troupe) == []
    assert keep(troupe.narrator, troupe, ["/my-work", "/my-work", ""]) == ["/my-work", ""]


def test_only_a_few_tab_addresses_are_kept(troupe: Troupe) -> None:
    base = f"/troupes/{troupe.id}/recent-tabs"
    many = troupe.lead.client.put(base, json={"tabs": ["/a", "/b", "/c", "/d", "/e"]})
    assert many.status_code == 422
    elsewhere = troupe.lead.client.put(base, json={"tabs": ["https://example.com"]})
    assert elsewhere.status_code == 422


def test_a_player_has_them_once_their_character_is_in_the_troupe(
    troupe: Troupe, session: Session
) -> None:
    # Not a member yet: nothing kept, and nothing to read.
    assert keep(troupe.player, troupe, ["/news"]) == []
    assert recent(troupe.player, troupe) == []
    join(session, troupe, new_character(troupe, troupe.player))
    assert keep(troupe.player, troupe, ["/news", ""]) == ["/news", ""]
    assert recent(troupe.player, troupe) == ["/news", ""]
    assert recent(troupe.stranger, troupe) == []

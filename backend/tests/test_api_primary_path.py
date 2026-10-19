"""A character whose clan has no in-clan path names its primary path of
Thaumaturgy, and no other path may go above it (MET: VTM p. 187)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import XpEntry
from tests.api_helpers import Troupe, new_character
from tests.test_api_checks import take

CORRUPTION = "Thaumaturgy: Path of Corruption"
FLAMES = "Thaumaturgy: Lure of Flames"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def rich(troupe: Troupe, clan: str) -> str:
    character_id = new_character(troupe, troupe.player, clan=clan)
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="award",
            amount=200,
            reason="Test",
            entered_by=uuid.UUID(troupe.custodian.id),
        )
    )
    troupe.session.flush()
    return character_id


def name(
    troupe: Troupe, character_id: str, path: str | None, discipline: str = "Thaumaturgy"
) -> Any:
    return troupe.player.client.put(
        f"/characters/{character_id}/primary-path", json={"discipline": discipline, "path": path}
    )


def primary(troupe: Troupe, character_id: str) -> list[dict[str, Any]]:
    sheet = troupe.player.client.get(f"/characters/{character_id}/sheet").json()
    return sheet["primary_paths"]


@pytest.fixture
def learned(troupe: Troupe) -> str:
    """A Brujah with Thaumaturgic Training, two dots of Corruption and one of Flames."""
    character_id = rich(troupe, "Brujah")
    trained = take(troupe.player, character_id, "merits", "Thaumaturgic Training", 4)
    assert trained.status_code == 200, trained.text
    assert take(troupe.player, character_id, "disciplines", CORRUPTION, 2).status_code == 200
    assert take(troupe.player, character_id, "disciplines", FLAMES, 1).status_code == 200
    return character_id


def test_the_sheet_asks_for_a_primary_path(troupe: Troupe, learned: str) -> None:
    assert primary(troupe, learned) == [
        {
            "discipline": "Thaumaturgy",
            "path": None,
            "native": False,
            "options": [CORRUPTION, FLAMES],
        }
    ]


def test_the_named_primary_path_holds_the_others_below_it(troupe: Troupe, learned: str) -> None:
    named = name(troupe, learned, CORRUPTION)

    assert named.status_code == 200, named.text
    assert named.json()["primary_paths"][0]["path"] == CORRUPTION
    assert take(troupe.player, learned, "disciplines", FLAMES, 2).status_code == 200
    refused = take(troupe.player, learned, "disciplines", FLAMES, 3)
    assert refused.status_code == 409
    assert "primary path" in refused.json()["detail"]
    assert take(troupe.player, learned, "disciplines", CORRUPTION, 3).status_code == 200
    log = [e["message"] for e in troupe.player.client.get(f"/characters/{learned}/log").json()]
    assert f"player named {CORRUPTION} Agnes's primary path of Thaumaturgy." in log


def test_only_the_highest_path_can_be_named(troupe: Troupe, learned: str) -> None:
    refused = name(troupe, learned, FLAMES)

    assert refused.status_code == 409
    assert refused.json()["detail"].startswith(f"{CORRUPTION} is higher")


def test_naming_needs_a_path_held_and_a_discipline_with_a_primary(
    troupe: Troupe, learned: str
) -> None:
    assert name(troupe, learned, "Thaumaturgy: Green Path").status_code == 422
    assert name(troupe, learned, "Necromancy: Sepulchre Path", "Necromancy").status_code == 422
    assert troupe.stranger.client.put(
        f"/characters/{learned}/primary-path",
        json={"discipline": "Thaumaturgy", "path": CORRUPTION},
    ).status_code in (403, 404)


def test_unnaming(troupe: Troupe, learned: str) -> None:
    name(troupe, learned, CORRUPTION)

    assert name(troupe, learned, None).json()["primary_paths"][0]["path"] is None
    assert take(troupe.player, learned, "disciplines", FLAMES, 3).status_code == 200


def test_a_clan_with_an_in_clan_path_has_it_as_primary(troupe: Troupe) -> None:
    tremere = rich(troupe, "Tremere")
    take(troupe.player, tremere, "disciplines", "Thaumaturgy: Path of Blood", 1)

    assert primary(troupe, tremere) == [
        {
            "discipline": "Thaumaturgy",
            "path": "Thaumaturgy: Path of Blood",
            "native": True,
            "options": [],
        }
    ]
    refused = name(troupe, tremere, "Thaumaturgy: Path of Blood")
    assert refused.status_code == 409

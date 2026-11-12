"""Boon statistics through the API (#702): who reads them, the month lines, the network
and flows from the troupe's own characters, and boons registered at a game."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Boon, ScheduledGame
from tests.api_helpers import Troupe
from tests.test_api_boons import Ledger, row


@pytest.fixture
def ledger(client_for: Callable[[], TestClient], session: Session) -> Ledger:
    return Ledger(Troupe(client_for, session))


def statistics(ledger: Ledger, **query: Any) -> Any:
    found = ledger.troupe.storyteller.client.get(
        f"/troupes/{ledger.troupe.id}/boon-statistics", params=query
    )
    assert found.status_code == 200, found.text
    return found.json()


def past_game(ledger: Ledger, session: Session, days_ago: int = 3) -> str:
    start = datetime.now(UTC) - timedelta(days=days_ago)
    game = ScheduledGame(
        troupe_id=uuid.UUID(ledger.troupe.id), starts_at=start, ends_at=start + timedelta(hours=5)
    )
    session.add(game)
    session.flush()
    return str(game.id)


def test_only_running_staff_read_the_statistics_and_only_while_the_ledger_is_on(
    ledger: Ledger,
) -> None:
    troupe = ledger.troupe
    path = f"/troupes/{troupe.id}/boon-statistics"
    for person in (troupe.lead, troupe.storyteller, troupe.assistant):
        assert person.client.get(path).status_code == 200
    for person in (troupe.narrator, troupe.player):
        assert person.client.get(path).status_code == 403
    assert troupe.player.client.get(f"/troupes/{troupe.id}/boon-games").status_code == 403

    assert ledger.switch(False).status_code == 200

    assert troupe.storyteller.client.get(path).status_code == 404


def test_the_statistics_show_the_month_who_owes_whom_and_the_clans(ledger: Ledger) -> None:
    ledger.one(ledger.agnes, ledger.bram, kind="major")
    ledger.one(ledger.agnes, {"name": "The Moon"})

    found = statistics(ledger)

    month = datetime.now(UTC).strftime("%Y-%m")
    major = next(m for m in found["by_entered"] if m["month"] == month and m["kind"] == "major")
    assert (major["registered"], major["open_weight"]) == (1, 3.0)
    nodes = {n["who"]["name"]: n for n in found["nodes"]}
    assert nodes["Bram"]["net"] == 3.0
    assert nodes["The Moon"]["who"]["character_id"] is None
    assert found["links"][0]["weight"] == 3.0
    assert found["links"][0]["kinds"] == {"major": 1}
    assert "Name only" in found["clan_flow"]["groups"]


def test_boons_registered_at_a_game_are_its_activity(ledger: Ledger, session: Session) -> None:
    game = past_game(ledger, session)
    later = past_game(ledger, session, days_ago=1)

    games = ledger.troupe.storyteller.client.get(f"/troupes/{ledger.troupe.id}/boon-games")
    assert games.status_code == 200, games.text
    assert [g["id"] for g in games.json()] == [later, game]
    made = ledger.troupe.storyteller.client.post(
        ledger.path,
        json={"boons": [row(ledger.agnes, ledger.bram, count=2)], "game_id": game},
    )
    assert made.status_code == 201, made.text
    assert all(
        session.get(Boon, uuid.UUID(b["id"])).game_id == uuid.UUID(game)  # type: ignore[union-attr]
        for b in made.json()
    )

    found = {g["game"]["id"]: g for g in statistics(ledger)["games"]}

    assert found[game]["registered"] == 2
    assert found[game]["by_kind"] == {"minor": 2}
    assert found[later]["registered"] == 0


def test_a_boon_can_be_registered_only_at_one_of_the_troupe_s_past_games(
    ledger: Ledger, session: Session
) -> None:
    start = datetime.now(UTC) + timedelta(days=2)
    coming = ScheduledGame(
        troupe_id=uuid.UUID(ledger.troupe.id), starts_at=start, ends_at=start + timedelta(hours=5)
    )
    session.add(coming)
    session.flush()

    for game_id in (str(coming.id), str(uuid.uuid4())):
        refused = ledger.troupe.storyteller.client.post(
            ledger.path, json={"boons": [row(ledger.agnes, ledger.bram)], "game_id": game_id}
        )
        assert refused.status_code == 422, refused.text

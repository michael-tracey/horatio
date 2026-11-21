"""A troupe's setup, for the Overview tab of Customise: what its lead has done of
the first few things, and how many house rules it has in each part of Rules."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from horatio.models import TroupeMembership
from tests.api_helpers import Troupe, new_character
from tests.test_api_downtimes import new_cycle

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def test_a_new_troupe_has_its_staff_and_nothing_else_set_up(troupe: Troupe) -> None:
    setup = troupe.assistant.client.get(f"/troupes/{troupe.id}/setup").json()

    assert (setup["described"], setup["profile"], setup["cycles"]) == (False, False, 0)
    # The storyteller, the assistant and the narrator, besides the lead.
    assert setup["staff"] == 3
    assert setup["checks"] == 0 and setup["checks_total"] > 500
    assert (setup["costs"], setup["starting"], setup["actions"], setup["house_traits"]) == (
        0,
        0,
        0,
        0,
    )
    assert {c["kind"]: c["state"] for c in setup["connectors"]} == {
        "discord": "unavailable",
        "email": "unavailable",
    }


def test_setup_follows_what_the_lead_does(troupe: Troupe) -> None:
    lead = troupe.lead.client
    lead.patch(f"/troupes/{troupe.id}", json={"description": "Nights in Asheville."})
    lead.put(f"/troupes/{troupe.id}/profile", json={"schedule": "Second Saturday"})
    lead.put(f"/troupes/{troupe.id}/checks/merits/Calm Heart/1", json={"strength": "off"})
    new_cycle(troupe)

    setup = lead.get(f"/troupes/{troupe.id}/setup").json()

    assert (setup["described"], setup["profile"], setup["checks"], setup["cycles"]) == (
        True,
        True,
        1,
        1,
    )


def test_only_running_staff_see_the_setup(troupe: Troupe) -> None:
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/setup").status_code == 403
    assert troupe.player.client.get(f"/troupes/{troupe.id}/setup").status_code == 403


# --- Getting your troupe ready (#1049) -------------------------------------------------------


def ready(client: TestClient, troupe: Troupe) -> dict[str, bool]:
    response = client.get(f"/troupes/{troupe.id}/getting-ready")
    assert response.status_code == 200, response.text
    return {s["step"]: s["done"] for s in response.json()["steps"]}


def test_a_new_troupe_is_getting_ready_with_only_its_staff_done(troupe: Troupe) -> None:
    steps = ready(troupe.lead.client, troupe)

    # In order, and only the staff the fixture appoints done.
    assert list(steps) == [
        "profile",
        "features",
        "joining",
        "starting",
        "house_rules",
        "staff",
        "first_game",
        "players",
    ]
    assert [s for s, done in steps.items() if done] == ["staff"]
    shown = troupe.lead.client.get(f"/troupes/{troupe.id}/getting-ready").json()
    assert shown["hidden"] is False


def test_each_step_ticks_itself_from_what_the_troupe_holds(
    troupe: Troupe, session: Session
) -> None:
    lead = troupe.lead.client
    lead.patch(f"/troupes/{troupe.id}", json={"description": "Nights in Asheville."})
    lead.put(f"/troupes/{troupe.id}/profile", json={"schedule": "Second Saturday"})
    lead.put(f"/troupes/{troupe.id}/boon-ledger", json={"on": True})
    lead.patch(f"/troupes/{troupe.id}", json={"allowed_sects": ["Camarilla"]})
    lead.patch(f"/troupes/{troupe.id}", json={"starting_xp": 40})
    start = datetime.now(UTC) + timedelta(days=10)
    game = lead.post(
        f"/troupes/{troupe.id}/games",
        json={"starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=5)).isoformat()},
    )
    assert game.status_code in (200, 201), game.text
    session.add(
        TroupeMembership(
            troupe_id=uuid.UUID(troupe.id),
            character_id=uuid.UUID(new_character(troupe, troupe.player)),
        )
    )
    session.flush()

    steps = ready(lead, troupe)

    # Turning the ledger on is a feature, and the house rules don't count it.
    assert {s for s, done in steps.items() if not done} == {"house_rules"}
    lead.put(f"/troupes/{troupe.id}/checks/merits/Calm Heart/1", json={"strength": "off"})
    assert ready(lead, troupe)["house_rules"] is True


@pytest.mark.parametrize("end", [None, "decline", "withdraw"])
def test_a_character_asking_to_join_ticks_invite_players(
    troupe: Troupe, session: Session, end: str | None
) -> None:
    character_id = new_character(troupe, troupe.player)
    asked = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert asked.status_code == 201, asked.text
    if end == "decline":
        ended = troupe.lead.client.post(f"/approvals/{asked.json()['id']}/decline", json={})
        assert ended.status_code == 200, ended.text
    elif end == "withdraw":
        ended = troupe.player.client.delete(f"/characters/{character_id}/home-troupe")
        assert ended.status_code == 204, ended.text

    # Asking starts the character visiting, and it stays a visitor once the request
    # is declined or withdrawn, so the step is done all the same.
    assert ready(troupe.lead.client, troupe)["players"] is True

    # Without the visit, the request counts on its own only while it waits (#1114).
    session.execute(
        delete(TroupeMembership).where(TroupeMembership.character_id == uuid.UUID(character_id))
    )
    session.flush()
    assert ready(troupe.lead.client, troupe)["players"] is (end is None)


def test_storytellers_hide_it_and_bring_it_back(troupe: Troupe) -> None:
    path = f"/troupes/{troupe.id}/getting-ready"
    hidden = troupe.storyteller.client.put(path, json={"hidden": True})
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["hidden"] is True
    assert troupe.lead.client.get(path).json()["hidden"] is True
    log = troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()
    assert "hid Getting your troupe ready on the Overview" in log[0]["message"]

    back = troupe.lead.client.put(path, json={"hidden": False})
    assert back.json()["hidden"] is False


def test_only_storytellers_hide_it_and_running_staff_read_it(troupe: Troupe) -> None:
    path = f"/troupes/{troupe.id}/getting-ready"
    assert troupe.assistant.client.get(path).status_code == 200
    assert troupe.assistant.client.put(path, json={"hidden": True}).status_code == 403
    assert troupe.narrator.client.get(path).status_code == 403
    assert troupe.player.client.get(path).status_code == 403

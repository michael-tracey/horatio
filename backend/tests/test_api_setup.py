"""A troupe's setup, for the Overview tab of Customise: what its lead has done of
the first few things, and how many house rules it has in each part of Rules."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe
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

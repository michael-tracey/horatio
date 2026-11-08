"""Custodian › Tools: fitting the creation picks of one troupe's NPCs at once (issue
#533), as `python -m horatio.npc_picks` does for every troupe."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import npc_picks
from horatio.models import Character, CharacterTrait
from tests.api_helpers import Troupe
from tests.test_api_npc_gifts import built, given
from tests.test_api_npc_kinds import made
from tests.test_api_npc_picks import picks, placed
from tests.test_api_renames import troupe_log


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def unfitted(troupe: Troupe, name: str) -> str:
    """A quick-built NPC as one built before #527 was: its ratings set straight and no
    creation picks fitted yet."""
    npc_id = built(troupe, name=name)
    npc = troupe.session.get_one(Character, uuid.UUID(npc_id))
    npc_picks.unfit(troupe.session, npc)
    return npc_id


def pick_state(troupe: Troupe) -> list[tuple[Any, ...]]:
    troupe.session.expire_all()
    return sorted(
        (str(t.id), t.creation_pick, t.free_rating, t.pick_by)
        for t in troupe.session.scalars(select(CharacterTrait))
    )


def preview(troupe: Troupe) -> dict[str, Any]:
    response = troupe.custodian.client.get(f"/tools/npc-picks/{troupe.id}")
    assert response.status_code == 200, response.text
    return response.json()


def fit(troupe: Troupe) -> dict[str, Any]:
    response = troupe.custodian.client.post(f"/tools/npc-picks/{troupe.id}")
    assert response.status_code == 200, response.text
    return response.json()


def worth(found: dict[str, Any]) -> dict[str, tuple[int, int, bool]]:
    return {n["name"]: (n["xp_now"], n["xp_after"], n["changed"]) for n in found["fitted"]}


def test_the_preview_says_what_fitting_would_do_and_changes_nothing(troupe: Troupe) -> None:
    lucien = unfitted(troupe, "Lucien")
    built(troupe, name="Marguerite")
    wizard = made(troupe, name="Wizard Willa", wizard=True)["id"]
    made(troupe, name="Stock Stan", npc_kind="mortal", npc_form="stock")
    before = pick_state(troupe)

    found = preview(troupe)

    assert found["troupe_name"] == "Lords of the Night"
    # Lucien's dots are all priced as bought until fitted; Marguerite's were fitted
    # as she was built, so she stays as she is.
    lucien_now, lucien_after, changed = worth(found)["Lucien"]
    assert lucien_after < lucien_now and changed
    marguerite_now, marguerite_after, changed = worth(found)["Marguerite"]
    assert marguerite_now == marguerite_after and not changed
    assert lucien_after == marguerite_after
    assert found["xp_now"] == lucien_now + marguerite_now
    assert found["xp_after"] == lucien_after + marguerite_after
    assert found["changed"] == 1
    assert {s["name"]: s["why"] for s in found["skipped"]} == {
        "Stock Stan": "A Stock NPC: it has no sheet to fit picks to.",
        "Wizard Willa": "Still being built in the wizard.",
    }
    assert wizard in [s["id"] for s in found["skipped"]]
    # Nothing changed, and nothing was logged.
    assert pick_state(troupe) == before
    assert placed(picks(troupe.storyteller, lucien), "skills") == {}
    assert not any("creation picks of the troupe" in m for m in troupe_log(troupe.lead, troupe.id))


def test_fitting_fits_the_picks_once_and_logs_who_and_how_many(troupe: Troupe) -> None:
    lucien = unfitted(troupe, "Lucien")
    unfitted(troupe, "Marguerite")
    expected = worth(preview(troupe))

    done = fit(troupe)

    assert worth(done) == expected
    assert done["changed"] == 2
    assert placed(picks(troupe.storyteller, lucien), "skills") == {"Brawl": (4, "fit")}
    assert worth(preview(troupe)) == {
        name: (after, after, False) for name, (_, after, _) in expected.items()
    }
    log = troupe_log(troupe.lead, troupe.id)
    assert (
        "custodian fitted the creation picks of the troupe's NPCs built without the wizard:"
        " 2 of 2 changed." in log
    )

    # Fitting again changes nothing, and says so.
    before = pick_state(troupe)
    again = fit(troupe)
    assert again["changed"] == 0
    assert pick_state(troupe) == before
    assert (
        "custodian fitted the creation picks of the troupe's NPCs built without the wizard:"
        " 0 of 2 changed." in troupe_log(troupe.lead, troupe.id)
    )


def test_fitting_keeps_the_picks_staff_placed_and_took_off(troupe: Troupe) -> None:
    npc = built(troupe, name="Lucien")
    for skill in ("Occult", "Dodge"):
        response = troupe.storyteller.client.put(
            f"/characters/{npc}/npc/ratings",
            json={"category": "skills", "name": skill, "rating": 4},
        )
        assert response.status_code == 200, response.text
    pin = troupe.storyteller.client.put(
        f"/characters/{npc}/npc/picks",
        json={"category": "skills", "name": "Occult", "detail": "", "rating": 4},
    )
    assert pin.status_code == 200, pin.text
    off = troupe.storyteller.client.post(
        f"/characters/{npc}/npc/picks/off",
        json={"category": "skills", "name": "Brawl", "detail": ""},
    )
    assert off.status_code == 200, off.text
    kept = picks(troupe.storyteller, npc)
    npc_picks.unfit(troupe.session, troupe.session.get_one(Character, uuid.UUID(npc)))

    fit(troupe)

    after = picks(troupe.storyteller, npc)
    assert placed(after, "skills") == placed(kept, "skills")
    assert placed(after, "skills")["Occult"] == (4, "staff")
    assert after["kept_off"] == [{"category": "skills", "name": "Brawl", "detail": ""}]


def test_npcs_given_to_players_are_left_as_they_are(troupe: Troupe) -> None:
    npc = unfitted(troupe, "Lucien")
    given(troupe.lead, npc, troupe.player)
    xp_before = troupe.player.client.get(f"/characters/{npc}/xp").json()

    found = fit(troupe)

    assert found["fitted"] == []
    assert found["skipped"] == [
        {
            "id": npc,
            "name": "Lucien",
            "why": f"Given to @{troupe.player.handle}: its picks and XP are its own now.",
        }
    ]
    assert troupe.player.client.get(f"/characters/{npc}/xp").json() == xp_before


def test_only_the_custodian_fits_and_never_for_an_archived_troupe(troupe: Troupe) -> None:
    unfitted(troupe, "Lucien")
    path = f"/tools/npc-picks/{troupe.id}"
    for someone in (troupe.lead, troupe.storyteller, troupe.player, troupe.stranger):
        assert someone.client.get(path).status_code == 403
        assert someone.client.post(path).status_code == 403
    assert troupe.custodian.client.get(f"/tools/npc-picks/{uuid.uuid4()}").status_code == 404

    archived = troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"})
    assert archived.status_code == 200, archived.text
    before = pick_state(troupe)
    for refused in (troupe.custodian.client.get(path), troupe.custodian.client.post(path)):
        assert refused.status_code == 409
        assert refused.json()["detail"] == (
            "Lords of the Night is archived: reopen it to fit its NPCs' picks."
        )
    assert pick_state(troupe) == before

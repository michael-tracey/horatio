"""Troupes and their staff, through the API, as each role."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_sect_status import member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def test_only_the_custodian_creates_troupes(troupe: Troupe) -> None:
    response = troupe.lead.client.post(
        "/troupes", json={"name": "Mine", "lead_handle": troupe.lead.handle}
    )

    assert response.status_code == 403


def test_everyone_signed_in_can_see_running_troupes(troupe: Troupe) -> None:
    response = troupe.stranger.client.get("/troupes")

    assert [t["name"] for t in response.json()] == ["Lords of the Night"]
    assert response.json()[0]["my_role"] is None


def test_people_see_their_own_role(troupe: Troupe) -> None:
    for person, role in (
        (troupe.lead, "lead_storyteller"),
        (troupe.storyteller, "storyteller"),
        (troupe.assistant, "assistant_storyteller"),
        (troupe.narrator, "narrator"),
    ):
        assert person.client.get(f"/troupes/{troupe.id}").json()["my_role"] == role


def test_the_list_says_for_each_troupe_the_role_held_and_whether_whos_who_opens(
    troupe: Troupe,
) -> None:
    # Asked of the database for all the troupes at once (#334): each keeps its own answer.
    made = troupe.custodian.client.post(
        "/troupes", json={"name": "Barons of the Bay", "lead_handle": troupe.storyteller.handle}
    )
    assert made.status_code == 201, made.text
    member(troupe)

    def listed(person: Person) -> dict[str, tuple[str | None, bool]]:
        return {
            t["name"]: (t["my_role"], t["whos_who"]) for t in person.client.get("/troupes").json()
        }

    assert listed(troupe.storyteller) == {
        "Barons of the Bay": ("lead_storyteller", True),
        "Lords of the Night": ("storyteller", True),
    }
    assert listed(troupe.player) == {
        "Barons of the Bay": (None, False),
        "Lords of the Night": (None, True),
    }
    assert listed(troupe.stranger) == {
        "Barons of the Bay": (None, False),
        "Lords of the Night": (None, False),
    }
    assert listed(troupe.custodian) == {
        "Barons of the Bay": (None, True),
        "Lords of the Night": (None, True),
    }


def test_the_list_says_where_each_troupe_plays_if_it_takes_new_players_and_who_you_play_there(
    troupe: Troupe,
) -> None:
    made = troupe.custodian.client.post(
        "/troupes", json={"name": "Barons of the Bay", "lead_handle": troupe.storyteller.handle}
    )
    assert made.status_code == 201, made.text
    member(troupe, "Bertrand")
    member(troupe, "Agnes")
    profile = troupe.lead.client.put(
        f"/troupes/{troupe.id}/profile",
        json={"new_players": "welcoming", "setting": {"city": "Leeds"}},
    )
    assert profile.status_code == 200, profile.text

    def listed(person: Person) -> dict[str, tuple[str | None, str, list[str]]]:
        return {
            t["name"]: (t["new_players"], t["place"], t["my_characters"])
            for t in person.client.get("/troupes").json()
        }

    assert listed(troupe.player) == {
        "Barons of the Bay": (None, "", []),
        "Lords of the Night": ("welcoming", "Leeds", ["Agnes", "Bertrand"]),
    }
    assert listed(troupe.stranger)["Lords of the Night"] == ("welcoming", "Leeds", [])

    # The venue's region, when there is one, says where it plays before the setting's city.
    changed = troupe.lead.client.put(
        f"/troupes/{troupe.id}/profile",
        json={"venue": {"region": "West Yorkshire"}, "setting": {"city": "Leeds"}},
    )
    assert changed.status_code == 200, changed.text
    assert listed(troupe.player)["Lords of the Night"] == (
        None,
        "West Yorkshire",
        ["Agnes", "Bertrand"],
    )


def test_only_the_lead_renames_or_describes_the_troupe(troupe: Troupe) -> None:
    for person in (troupe.storyteller, troupe.assistant, troupe.narrator, troupe.player):
        assert (
            person.client.patch(f"/troupes/{troupe.id}", json={"name": "Taken"}).status_code == 403
        )
        assert (
            person.client.patch(f"/troupes/{troupe.id}", json={"description": "x"}).status_code
            == 403
        )

    response = troupe.lead.client.patch(
        f"/troupes/{troupe.id}", json={"name": "Court of Ash", "description": "Raleigh"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Court of Ash"
    assert response.json()["description"] == "Raleigh"


def test_storytellers_manage_staff_but_assistants_and_narrators_do_not(troupe: Troupe) -> None:
    newcomer = sign_up(troupe.client_for, "newcomer")
    for person in (troupe.assistant, troupe.narrator, troupe.player):
        response = person.client.put(
            f"/troupes/{troupe.id}/staff", json={"handle": newcomer.handle, "role": "narrator"}
        )
        assert response.status_code == 403

    response = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/staff", json={"handle": newcomer.handle, "role": "narrator"}
    )

    assert response.status_code == 200


def test_all_staff_can_see_the_staff_list_but_players_cannot(troupe: Troupe) -> None:
    response = troupe.narrator.client.get(f"/troupes/{troupe.id}/staff")

    assert response.status_code == 200
    assert [m["role"] for m in response.json()] == [
        "lead_storyteller",
        "assistant_storyteller",
        "narrator",
        "storyteller",
    ]
    assert troupe.player.client.get(f"/troupes/{troupe.id}/staff").status_code == 403


def test_the_lead_role_is_not_handed_out_as_staff(troupe: Troupe) -> None:
    response = troupe.lead.client.put(
        f"/troupes/{troupe.id}/staff",
        json={"handle": troupe.player.handle, "role": "lead_storyteller"},
    )
    assert response.status_code == 422

    response = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/staff", json={"handle": troupe.lead.handle, "role": "narrator"}
    )
    assert response.status_code == 409


def test_the_custodian_appoints_a_new_lead(troupe: Troupe) -> None:
    assert (
        troupe.lead.client.put(
            f"/troupes/{troupe.id}/lead", json={"handle": troupe.storyteller.handle}
        ).status_code
        == 403
    )

    response = troupe.custodian.client.put(
        f"/troupes/{troupe.id}/lead", json={"handle": troupe.storyteller.handle}
    )

    assert response.status_code == 200
    staff = troupe.storyteller.client.get(f"/troupes/{troupe.id}/staff").json()
    roles = {m["user_id"]: m["role"] for m in staff}
    # The new lead is no longer also listed as a storyteller, and the old lead is not staff.
    assert roles[troupe.storyteller.id] == "lead_storyteller"
    assert list(roles.values()).count("lead_storyteller") == 1
    assert troupe.lead.id not in roles


def test_removing_staff(troupe: Troupe) -> None:
    response = troupe.storyteller.client.delete(f"/troupes/{troupe.id}/staff/{troupe.narrator.id}")

    assert response.status_code == 204
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/staff").status_code == 403


def test_deleting_a_troupe_archives_it(troupe: Troupe) -> None:
    archive = f"/troupes/{troupe.id}/archive"
    assert troupe.storyteller.client.post(archive, json={"reason": "Done"}).status_code == 403
    assert troupe.lead.client.post(archive, json={}).status_code == 422

    assert troupe.lead.client.post(archive, json={"reason": "Done"}).status_code == 200

    assert troupe.player.client.get("/troupes").json() == []
    assert troupe.player.client.get(f"/troupes/{troupe.id}").status_code == 404
    assert troupe.storyteller.client.get(f"/troupes/{troupe.id}/staff").status_code == 403
    # Kept, not deleted: the custodian can still see it.
    archived = troupe.custodian.client.get(f"/troupes/{troupe.id}")
    assert archived.status_code == 200
    assert archived.json()["archived"] is True

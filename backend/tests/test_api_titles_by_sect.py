"""Titles by sect: a troupe gives its sects' titles, each only to a character of its
sect, and its own titles may have a sect and give status."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import titles
from horatio.models import CharacterTitle
from tests.api_helpers import Troupe
from tests.test_api_npcs_titles import make_npc, member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def limit(troupe: Troupe, sects: list[str]) -> None:
    response = troupe.lead.client.patch(f"/troupes/{troupe.id}", json={"allowed_sects": sects})
    assert response.status_code == 200, response.text


def npc_of(troupe: Troupe, name: str, sect: str | None) -> str:
    npc: str = make_npc(troupe, name)["id"]
    if sect is not None:
        rated = troupe.storyteller.client.put(
            f"/characters/{npc}/npc/ratings",
            json={"category": "sect", "name": sect, "rating": None},
        )
        assert rated.status_code == 200, rated.text
    return npc


def give(troupe: Troupe, character_id: str, names: list[str]) -> Any:
    return troupe.assistant.client.put(
        f"/troupes/{troupe.id}/characters/{character_id}/titles", json={"titles": names}
    )


def listed(troupe: Troupe) -> dict[str, dict[str, Any]]:
    response = troupe.assistant.client.get(f"/troupes/{troupe.id}/titles")
    assert response.status_code == 200, response.text
    return {t["name"]: t for t in response.json()["titles"]}


def add(troupe: Troupe, name: str, sect: str | None, status: list[str]) -> Any:
    return troupe.assistant.client.post(
        f"/troupes/{troupe.id}/titles", json={"name": name, "sect": sect, "status": status}
    )


def test_a_camarilla_troupe_lists_camarilla_titles_and_those_of_no_sect(troupe: Troupe) -> None:
    limit(troupe, ["Camarilla"])

    found = listed(troupe)

    assert (found["Prince"]["sect"], found["Prince"]["status"]) == (
        "Camarilla",
        ["Authority", "Commander", "Sovereign"],
    )
    assert found["Soldier"]["sect"] is None
    assert not {"Bishop", "Baron", "Abbot"} & set(found)
    response = troupe.assistant.client.get(f"/troupes/{troupe.id}/titles").json()
    assert response["sects"] == ["Camarilla"]
    choices = {c["name"]: c["sect"] for c in response["status_choices"]}
    assert (choices["Guardian"], choices["Authority"]) == ("Camarilla", "General")
    assert "Blessed" not in choices


def test_a_troupe_of_any_sect_lists_every_sects_titles(troupe: Troupe) -> None:
    found = listed(troupe)

    assert {found[n]["sect"] for n in ("Prince", "Bishop", "Baron", "Soldier")} == {
        "Camarilla",
        "Sabbat",
        "Anarch",
        None,
    }
    seneschal = found["Seneschal"]
    assert seneschal["while_absent"] == [
        {"title": "Prince", "status": ["Authority"], "note": seneschal["while_absent"][0]["note"]}
    ]
    assert set(found["Bishop"]["choose_one"]) == {"Blessed", "Enforcer"}


def test_the_troupes_titles_say_what_each_gives_or_why_not(troupe: Troupe) -> None:
    """Each title on the troupe's Titles page says what it is beyond its status: the
    title another name is for, why it gives none, its clan, or no rules yet (#340)."""
    found = listed(troupe)

    assert found["Master Harpy"]["alias_of"] == "Harpy"
    assert found["Master Harpy"]["status"] == ["Prominent", "Noble", "Guardian"]
    assert (found["Abbot"]["gives_none"], found["Abbot"]["page"]) == (
        "An Abbot gains no abiding status for the office.",
        "421",
    )
    assert (found["Pontifex"]["clan"], found["Pontifex"]["sect"]) == ("Tremere", None)
    assert (found["Trustee"]["no_rules_yet"], found["Trustee"]["status"]) == (True, [])
    plain = found["Prince"]
    assert (plain["alias_of"], plain["clan"], plain["gives_none"], plain["no_rules_yet"]) == (
        None,
        None,
        "",
        False,
    )


def test_a_title_goes_only_to_a_character_of_its_sect(troupe: Troupe) -> None:
    limit(troupe, ["Camarilla"])
    anarch = npc_of(troupe, "Baron Ruiz", "Anarch")
    nobody = npc_of(troupe, "Ghostly Figure", None)
    camarilla = member(troupe, "Elena")

    refused = give(troupe, anarch, ["Prince"])
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Prince is a Camarilla title, and Baron Ruiz is Anarch."
    assert give(troupe, nobody, ["Prince"]).json()["detail"].endswith("has no sect.")
    # Another sect's title isn't one this troupe gives.
    assert give(troupe, camarilla, ["Bishop"]).status_code == 422
    # A title of no sect goes to anyone.
    assert give(troupe, anarch, ["Soldier"]).status_code == 200
    assert give(troupe, nobody, ["Soldier"]).status_code == 200
    assert give(troupe, camarilla, ["Prince", "Soldier"]).json() == {
        "titles": ["Prince", "Soldier"]
    }


def test_a_house_title_has_a_sect_and_gives_status(troupe: Troupe, session: Session) -> None:
    limit(troupe, ["Camarilla"])
    elena = member(troupe, "Elena")

    made = add(troupe, "Master of Elysium", "Camarilla", ["Guardian"])

    assert made.status_code == 201, made.text
    title = {t["name"]: t for t in made.json()["titles"]}["Master of Elysium"]
    assert (title["sect"], title["status"], title["house"]) == ("Camarilla", ["Guardian"], True)
    assert give(troupe, elena, ["Master of Elysium"]).status_code == 200
    # What #252 reads to give the holder its status.
    data = titles.title_data(session, uuid.UUID(troupe.id))
    assert (data["Master of Elysium"].sect, data["Master of Elysium"].status) == (
        "Camarilla",
        ("Guardian",),
    )
    assert data["Prince"].status == ("Authority", "Commander", "Sovereign")
    assert data["Bishop"].sect == "Sabbat"  # not narrowed to the troupe's sects
    assert listed(troupe)["Master of Elysium"]["holders"] == [
        {
            "character_id": elena,
            "character_name": "Elena",
            "sect": "Camarilla",
            "out_of_sect": False,
            "active": True,
        }
    ]


def test_a_house_title_gives_only_abiding_status_of_its_sect(troupe: Troupe) -> None:
    limit(troupe, ["Camarilla"])

    assert add(troupe, "Hound", "Camarilla", ["Blessed"]).json()["detail"] == (
        "Blessed is Sabbat status: only a Sabbat title gives it."
    )
    assert add(troupe, "Hound", "Camarilla", ["Loyal"]).status_code == 422  # fleeting
    assert (
        add(troupe, "Hound", "Sabbat", []).json()["detail"].endswith("does not give Sabbat titles.")
    )
    assert add(troupe, "Hound", None, ["Guardian"]).status_code == 422
    # With no sect, it can give general status.
    made = add(troupe, "Mayor's Liaison", None, ["Prominent"])
    assert made.status_code == 201, made.text
    assert listed(troupe)["Mayor's Liaison"]["sect"] is None


def test_changing_a_house_title_changes_it_for_all_who_hold_it(
    troupe: Troupe, session: Session
) -> None:
    add(troupe, "Master of Elysium", "Camarilla", ["Guardian"])
    elena = member(troupe, "Elena")
    marco = member(troupe, "Marco")
    give(troupe, elena, ["Master of Elysium"])
    give(troupe, marco, ["Master of Elysium"])
    path = f"/troupes/{troupe.id}/titles/Master of Elysium"

    changed = troupe.assistant.client.put(
        path, json={"sect": "Camarilla", "status": ["Guardian", "Prominent"]}
    )

    assert changed.status_code == 200, changed.text
    title = {t["name"]: t for t in changed.json()["titles"]}["Master of Elysium"]
    assert title["status"] == ["Guardian", "Prominent"]
    assert [h["character_name"] for h in title["holders"]] == ["Elena", "Marco"]
    data = titles.title_data(session, uuid.UUID(troupe.id))
    assert data["Master of Elysium"].status == ("Guardian", "Prominent")
    messages = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert messages[0] == (
        "assistant changed the title Master of Elysium: now Camarilla, giving Guardian, Prominent."
    )
    # Only a troupe's own titles change.
    assert (
        troupe.assistant.client.put(
            f"/troupes/{troupe.id}/titles/Prince", json={"sect": None, "status": []}
        ).status_code
        == 409
    )
    assert troupe.narrator.client.put(path, json={"status": []}).status_code == 403


def test_a_title_held_out_of_sect_is_kept_and_flagged(troupe: Troupe, session: Session) -> None:
    limit(troupe, ["Camarilla"])
    elena = member(troupe, "Elena")
    # Given before titles had sects.
    session.add(
        CharacterTitle(troupe_id=uuid.UUID(troupe.id), character_id=uuid.UUID(elena), name="Bishop")
    )
    session.commit()

    bishop = listed(troupe)["Bishop"]
    assert (bishop["offered"], bishop["holders"][0]["out_of_sect"]) == (False, True)
    roster = troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()
    assert (roster[0]["sect"], roster[0]["out_of_sect_titles"]) == ("Camarilla", ["Bishop"])

    # It stays while she is given others, and can be taken.
    assert give(troupe, elena, ["Bishop", "Harpy"]).json() == {"titles": ["Bishop", "Harpy"]}
    assert give(troupe, elena, ["Harpy"]).json() == {"titles": ["Harpy"]}
    assert "Bishop" not in listed(troupe)

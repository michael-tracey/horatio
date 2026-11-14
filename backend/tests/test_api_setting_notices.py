"""A bell notice to a troupe's players when its Setting Style Document changes (issue
#881): it says what changed and links to the Setting tab, a burst of changes makes
one notice, and only the player-facing document counts."""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from horatio import setting_notices
from horatio.models import Notification
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_characters import join


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    troupe = Troupe(client_for, session)
    join(session, troupe, new_character(troupe, troupe.player, "Agnes"))
    return troupe


def notices(person: Person) -> list[dict[str, Any]]:
    response = person.client.get("/notifications")
    assert response.status_code == 200, response.text
    return [i for i in response.json()["items"] if i["kind"] == "setting.changed"]


def summaries(person: Person) -> list[str]:
    return [i["summary"] for i in notices(person)]


def ok(response: Any) -> Any:
    assert response.status_code in (200, 201), response.text
    return response.json()


def add(person: Person, troupe: Troupe, kind: str, name: str, **more: Any) -> str:
    made = ok(
        person.client.post(
            f"/troupes/{troupe.id}/setting/entries", json={"kind": kind, "name": name, **more}
        )
    )
    return next(e["id"] for e in made[f"{kind}s"] if e["name"] == name)


def text(person: Person, troupe: Troupe, **parts: str) -> None:
    body = {"subtitle": "", "teaser": "", "power": "", "agency": "", **parts}
    ok(person.client.put(f"/troupes/{troupe.id}/setting", json=body))


def pause(session: Session) -> None:
    """As if the last change came longer ago than a burst lasts."""
    session.execute(
        update(Notification)
        .where(Notification.kind == setting_notices.KIND)
        .values(created_at=Notification.created_at - setting_notices.GATHER - timedelta(minutes=1))
    )
    session.expire_all()


def test_a_burst_of_changes_makes_one_notice_for_the_troupe_s_players(troupe: Troupe) -> None:
    betrayal = add(troupe.lead, troupe, "theme", "Betrayal", book_key="betrayal")
    text(troupe.assistant, troupe, teaser="The river rose.")
    add(troupe.storyteller, troupe, "mood", "Brooding")
    ok(
        troupe.lead.client.put(
            f"/troupes/{troupe.id}/setting/entries/{betrayal}",
            json={"name": "Betrayal", "description": "Who sells out the Prince?"},
        )
    )
    # The same change again is not named twice.
    text(troupe.assistant, troupe, teaser="The river rose, and fell.")

    [notice] = notices(troupe.player)
    assert notice["summary"] == (
        "The setting changed: the theme Betrayal added; the teaser rewritten;"
        " the mood Brooding added; the theme Betrayal changed."
    )
    assert notice["link"] == f"/troupes/{troupe.id}/setting"
    assert notice["troupe_name"] == "Lords of the Night"
    assert not notice["read"]
    # Not those who made the changes, staff with no character here, or anyone else.
    for person in (troupe.lead, troupe.assistant, troupe.narrator, troupe.stranger):
        assert notices(person) == []


def test_a_read_notice_or_a_pause_starts_another(troupe: Troupe, session: Session) -> None:
    add(troupe.lead, troupe, "theme", "Chaos")
    [first] = notices(troupe.player)
    read = troupe.player.client.post("/notifications/read", json={"ids": [first["id"]]})
    assert read.status_code == 204, read.text

    add(troupe.lead, troupe, "note", "", description="No elders.")
    assert summaries(troupe.player) == [
        "The setting changed: a storyteller note added.",
        "The setting changed: the theme Chaos added.",
    ]

    pause(session)
    text(troupe.lead, troupe, subtitle="A City Under Siege", power="Neonates.")
    assert summaries(troupe.player) == [
        "The setting changed: the subtitle changed; the scope's power changed.",
        "The setting changed: a storyteller note added.",
        "The setting changed: the theme Chaos added.",
    ]


def test_a_long_burst_names_the_first_few_and_says_there_are_more(troupe: Troupe) -> None:
    for name in ("Love", "Hate", "Revenge", "Rebellion", "Morality", "Chaos", "Fear", "Greed"):
        add(troupe.lead, troupe, "theme", name)
    assert summaries(troupe.player) == [
        "The setting changed: the theme Love added; the theme Hate added; the theme Revenge"
        " added; the theme Rebellion added; the theme Morality added; the theme Chaos added;"
        " and more."
    ]


def test_order_and_removal_count_and_a_save_that_changes_nothing_does_not(
    troupe: Troupe, session: Session
) -> None:
    love = add(troupe.lead, troupe, "theme", "Love")
    hate = add(troupe.lead, troupe, "theme", "Hate")
    note = add(troupe.lead, troupe, "note", "", description="No elders.")
    pause(session)
    ok(
        troupe.lead.client.put(
            f"/troupes/{troupe.id}/setting/entries/{love}", json={"name": "Love"}
        )
    )
    text(troupe.lead, troupe)
    assert len(notices(troupe.player)) == 1

    ok(
        troupe.lead.client.put(
            f"/troupes/{troupe.id}/setting/order", json={"kind": "theme", "ids": [hate, love]}
        )
    )
    ok(troupe.lead.client.delete(f"/troupes/{troupe.id}/setting/entries/{note}"))
    assert summaries(troupe.player)[0] == (
        "The setting changed: the themes put in a new order; a storyteller note removed."
    )


def test_the_built_parts_players_read_count_too(troupe: Troupe) -> None:
    lead = troupe.lead.client
    ok(lead.patch(f"/troupes/{troupe.id}", json={"allowed_sects": ["Camarilla"]}))
    ok(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/clan-rarity",
            json={"rarities": {"Lasombra": "uncommon"}, "notes": {"Lasombra": "due to story"}},
        )
    )
    ok(lead.patch(f"/troupes/{troupe.id}", json={"new_character_incentive": True}))
    ok(
        lead.put(
            f"/troupes/{troupe.id}/profile",
            json={"setting": {"chronicle": "Leeds by Night", "city": "Leeds", "era": "Modern"}},
        )
    )
    assert summaries(troupe.player) == [
        "The setting changed: the sects that may join changed; Lasombra's rarity changed;"
        " the New Character Incentive switched on; the chronicle's name changed;"
        " the locale changed."
    ]


def test_what_players_do_not_read_in_it_makes_no_notice(troupe: Troupe) -> None:
    lead = troupe.lead.client
    # Settings saved as they were.
    ok(lead.patch(f"/troupes/{troupe.id}", json={"allowed_sects": []}))
    ok(lead.patch(f"/troupes/{troupe.id}", json={"new_character_incentive": False}))
    ok(lead.put(f"/troupes/{troupe.id}/clan-rarity", json={"rarities": {}}))
    # The rest of the profile, and showing the document on it.
    ok(lead.put(f"/troupes/{troupe.id}/profile", json={"setting": {"era": "Victorian"}}))
    ok(lead.put(f"/troupes/{troupe.id}/setting/public", json={"public": True}))
    # Other house rules: the starting XP.
    ok(lead.patch(f"/troupes/{troupe.id}", json={"starting_xp": 45}))
    assert notices(troupe.player) == []


def test_staff_who_play_hear_of_others_changes_but_not_their_own(
    troupe: Troupe, session: Session
) -> None:
    join(session, troupe, new_character(troupe, troupe.storyteller, "Bertram"))
    add(troupe.storyteller, troupe, "theme", "Hate")
    assert notices(troupe.storyteller) == []
    add(troupe.lead, troupe, "theme", "Love")
    assert summaries(troupe.storyteller) == ["The setting changed: the theme Love added."]
    assert summaries(troupe.player) == [
        "The setting changed: the theme Hate added; the theme Love added."
    ]


def test_the_clan_is_named_as_the_troupe_calls_it(troupe: Troupe, session: Session) -> None:
    ok(
        troupe.lead.client.put(
            f"/troupes/{troupe.id}/clan-rarity", json={"rarities": {"Assamite": "rare"}}
        )
    )
    assert summaries(troupe.player) == ["The setting changed: Banu Haqim's rarity changed."]
    stored = session.scalars(
        select(Notification.summary).where(Notification.troupe_id == uuid.UUID(troupe.id))
    ).all()
    assert "Assamite" not in " ".join(stored)

"""What a troupe calls the clan stored as "Assamite" (issue #430): Banu Haqim, the
default, or Assamite. Only what is shown changes; the rules keep "Assamite"."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from horatio.clan_names import shown, troupe_name
from horatio.models import AuditEvent, Notification
from horatio.models import Troupe as TroupeRow
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_sect_status import choose, make_home, status

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def troupe_read(person: Person, troupe: Troupe) -> dict[str, Any]:
    response = person.client.get(f"/troupes/{troupe.id}")
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


def call_it(person: Person, troupe: Troupe, name: str) -> Any:
    return person.client.put(f"/troupes/{troupe.id}/clan-names", json={"assamite": name})


def logged(session: Session) -> list[str]:
    events = session.scalars(select(AuditEvent).where(AuditEvent.action == "house.clan_names"))
    return [e.data["name"] for e in events]


def at_home(troupe: Troupe, name: str, clan: str, sect: str = "Camarilla") -> str:
    character_id = new_character(troupe, troupe.player, name, clan=clan)
    choose(troupe.player, character_id, "sect", sect)
    make_home(troupe, troupe.player, character_id)
    return character_id


# --- the name shown ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "banu_haqim"),
    [
        ("Assamite", "Banu Haqim"),
        ("Assamite: Sorcerer", "Banu Haqim: Sorcerer"),
        ("Assamite: Vizier", "Banu Haqim: Vizier"),
        ("Assamite: Diluted Blood", "Banu Haqim: Diluted Blood"),
        ("Assamite: Dual Caste", "Banu Haqim: Dual Caste"),
        ("Assamite: Unbroken", "Banu Haqim: Unbroken"),
        ("Thaumaturgy: Kiss of the Asp (Assamite)", "Thaumaturgy: Kiss of the Asp (Banu Haqim)"),
        ("Jinun's Bane (Assamite)", "Jinun's Bane (Banu Haqim)"),
        ("Assamite antitribu", "Banu Haqim antitribu"),
        (
            "Follow the Path of Blood instead of Humanity: the Assamite creed of rendering"
            " Haqim's judgment on other vampires.",
            "Follow the Path of Blood instead of Humanity: the Banu Haqim creed of rendering"
            " Haqim's judgment on other vampires.",
        ),
        ("The Assamites keep to the shadows.", "The Banu Haqim keep to the shadows."),
        (
            "Drinking non-Assamite vampire blood deals you 1 aggravated damage.",
            "Drinking non-Banu Haqim vampire blood deals you 1 aggravated damage.",
        ),
        ("an Assamite Vizier's ghoul", "a Banu Haqim Vizier's ghoul"),
        ("An Assamite hunts.", "A Banu Haqim hunts."),
        ("Brujah", "Brujah"),
        ("Assamitesque", "Assamitesque"),
    ],
)
def test_the_stored_name_as_a_banu_haqim_troupe_reads_it(stored: str, banu_haqim: str) -> None:
    assert shown(stored, "Banu Haqim") == banu_haqim
    assert shown(stored, "Assamite") == stored


def test_a_character_outside_any_troupe_gets_banu_haqim() -> None:
    assert troupe_name(None) == "Banu Haqim"


# --- the setting ------------------------------------------------------------------------


def test_a_new_troupe_calls_the_clan_banu_haqim(troupe: Troupe, session: Session) -> None:
    assert troupe_read(troupe.player, troupe)["assamite_name"] == "Banu Haqim"
    # The database's own default, for a troupe made without the model's.
    lead = session.get_one(TroupeRow, uuid.UUID(troupe.id)).lead_user_id
    made = session.scalar(
        text("insert into troupes (name, lead_user_id) values ('Raw', :lead) returning id"),
        {"lead": lead},
    )
    assert session.get_one(TroupeRow, made).assamite_name == "Banu Haqim"


def test_storytellers_choose_the_name_and_the_log_says_so(troupe: Troupe, session: Session) -> None:
    for person in (troupe.assistant, troupe.narrator, troupe.player):
        assert call_it(person, troupe, "Assamite").status_code in (403, 404)
    assert call_it(troupe.storyteller, troupe, "Ashirra").status_code == 422

    changed = call_it(troupe.storyteller, troupe, "Assamite")

    assert changed.status_code == 200, changed.text
    assert changed.json()["assamite_name"] == "Assamite"
    assert troupe_read(troupe.player, troupe)["assamite_name"] == "Assamite"
    assert logged(session) == ["Assamite"]
    # Choosing the name it already has logs nothing.
    assert call_it(troupe.storyteller, troupe, "Assamite").status_code == 200
    assert logged(session) == ["Assamite"]


def test_a_sheet_names_the_clan_as_its_home_troupe_does(troupe: Troupe) -> None:
    alone = new_character(troupe, troupe.player, "Nadia", clan="Assamite")
    homed = at_home(troupe, "Rashid", "Assamite: Vizier")

    def called(character_id: str) -> str:
        response = troupe.player.client.get(f"/characters/{character_id}")
        assert response.status_code == 200, response.text
        name: str = response.json()["assamite_name"]
        return name

    assert (called(alone), called(homed)) == ("Banu Haqim", "Banu Haqim")
    assert call_it(troupe.storyteller, troupe, "Assamite").status_code == 200
    # Outside any troupe, still the default.
    assert (called(alone), called(homed)) == ("Banu Haqim", "Assamite")
    listed = troupe.player.client.get("/characters").json()
    assert {c["name"]: c["assamite_name"] for c in listed} == {
        "Nadia": "Banu Haqim",
        "Rashid": "Assamite",
    }


def test_a_notification_names_the_clan_as_the_troupe_calls_it_then(
    troupe: Troupe, session: Session
) -> None:
    from horatio import notifications

    player, troupe_id = uuid.UUID(troupe.player.id), uuid.UUID(troupe.id)
    said = "An Assamite was Embraced."
    notifications.notify(session, [player], "test.before", said, "/", troupe_id=troupe_id)
    assert call_it(troupe.storyteller, troupe, "Assamite").status_code == 200
    session.expire_all()
    notifications.notify(session, [player], "test.after", said, "/", troupe_id=troupe_id)
    notifications.notify(session, [player], "test.no_troupe", "Assamites, everywhere.", "/")

    summaries = dict(
        session.execute(
            select(Notification.kind, Notification.summary).where(
                Notification.user_id == player, Notification.kind.startswith("test.")
            )
        ).all()
    )
    # The first keeps the name it was written with.
    assert summaries == {
        "test.before": "A Banu Haqim was Embraced.",
        "test.after": "An Assamite was Embraced.",
        "test.no_troupe": "Banu Haqim, everywhere.",
    }


def test_the_migration_keeps_assamite_for_troupes_that_were_there(
    engine: Engine, alembic_config: Config
) -> None:
    """Migration 0128: a troupe made before it sees no change; one made after starts
    with Banu Haqim."""
    command.downgrade(alembic_config, "0127")
    user, older = uuid.uuid4(), uuid.uuid4()
    newer = uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'clan-names@example.com', 'Namer', 'clan_namer')"
                ),
                {"id": user},
            )
            connection.execute(
                text("insert into troupes (id, name, lead_user_id) values (:id, 'Alamut', :lead)"),
                {"id": older, "lead": user},
            )

        command.upgrade(alembic_config, "head")

        with engine.begin() as connection:
            connection.execute(
                text("insert into troupes (id, name, lead_user_id) values (:id, 'Masyaf', :lead)"),
                {"id": newer, "lead": user},
            )
            names = dict(
                connection.execute(
                    text("select id, assamite_name from troupes where lead_user_id = :lead"),
                    {"lead": user},
                ).all()
            )
        assert names == {older: "Assamite", newer: "Banu Haqim"}
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            connection.execute(text("delete from troupes where lead_user_id = :id"), {"id": user})
            connection.execute(text("delete from users where id = :id"), {"id": user})


# --- the rules are unchanged ------------------------------------------------------------


def test_an_assamite_clan_merit_is_still_theirs_under_banu_haqim(troupe: Troupe) -> None:
    """Surprise Attack's requirement is "Assamite" (p. 238): a character of the clan, or
    a caste of it, still takes it while the troupe calls the clan Banu Haqim, and no
    one else can."""
    assert troupe_read(troupe.player, troupe)["assamite_name"] == "Banu Haqim"
    vizier = at_home(troupe, "Rashid", "Assamite: Vizier")
    brujah = at_home(troupe, "Moira", "Brujah")

    def take(character_id: str) -> Any:
        return troupe.player.client.put(
            f"/characters/{character_id}/traits",
            json={"category": "merits", "name": "Surprise Attack", "rating": 1},
        )

    taken = take(vizier)
    refused = take(brujah)

    assert taken.status_code == 200, taken.text
    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("Surprise Attack is only for Assamite.")


def test_the_pillar_clan_and_antitribu_bans_are_unchanged_under_banu_haqim(
    troupe: Troupe,
) -> None:
    """The Camarilla's pillar clans include the Assamites (p. 403), and the Sabbat bans
    Assamite antitribu (p. 449), whatever the troupe calls them."""
    camarilla = at_home(troupe, "Samira", "Assamite")
    sabbat = at_home(troupe, "Tariq", "Assamite: Sorcerer", sect="Sabbat")
    gangrel = at_home(troupe, "Ulf", "Gangrel")

    def applies(character_id: str, ban: str) -> bool:
        found = status(troupe.player, character_id)
        return next(b for b in found["bans"] if b["applies_to"].startswith(ban))["applies"]

    for name in ("Banu Haqim", "Assamite"):
        assert call_it(troupe.storyteller, troupe, name).status_code == 200
        assert applies(camarilla, "Not Embraced into a pillar clan") is False
        assert applies(gangrel, "Not Embraced into a pillar clan") is True
        assert applies(sabbat, "Assamite or Toreador antitribu") is True

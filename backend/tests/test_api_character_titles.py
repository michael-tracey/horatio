"""Status & Titles (#321): a player chooses their character's titles from their home
troupe's titles of its sect, and staff are told; one title is active and gives
status; a unique title someone holds is staff's to give; a troupe can keep titles
to staff."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.conftest import load_rules
from tests.test_api_notifications import summaries
from tests.test_api_sect_status import entitle, logged, member, status


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def titles_of(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/titles")
    assert response.status_code == 200, response.text
    return response.json()


def take(person: Person, character_id: str, name: str, *, active: bool = False) -> Any:
    return person.client.post(
        f"/characters/{character_id}/titles", json={"name": name, "active": active}
    )


def switch(person: Person, character_id: str, name: str) -> Any:
    return person.client.put(f"/characters/{character_id}/titles/active", json={"name": name})


def give_up(person: Person, character_id: str, name: str) -> Any:
    return person.client.delete(f"/characters/{character_id}/titles/{name}")


def from_titles(person: Person, character_id: str) -> dict[str, list[str]]:
    """The status the character's titles give, by title."""
    found: dict[str, list[str]] = {}
    for d in status(person, character_id)["derived"]:
        if d["kind"] == "title":
            found.setdefault(d["source"], []).append(d["name"])
    return found


def test_a_player_chooses_a_title_of_their_sect_and_staff_are_told(troupe: Troupe) -> None:
    vasquez = member(troupe, "Lady Vasquez")

    shown = titles_of(troupe.player, vasquez)

    assert (shown["troupe_name"], shown["sect"], shown["acting"]) == (
        "Lords of the Night",
        "Camarilla",
        "player",
    )
    choices = {c["name"]: c for c in shown["choices"]}
    assert choices["Harpy"]["status"] == ["Prominent", "Noble", "Guardian"]
    assert choices["Harpy"]["sect"] == "Camarilla"
    assert choices["Soldier"]["sect"] is None
    assert "Bishop" not in choices  # the Sabbat's
    # In court order: the Prince before the Harpy.
    names = [c["name"] for c in shown["choices"]]
    assert names.index("Prince") < names.index("Harpy")

    taken = take(troupe.player, vasquez, "Harpy")

    assert taken.status_code == 200, taken.text
    assert [(t["name"], t["active"]) for t in taken.json()["held"]] == [("Harpy", True)]
    assert "Harpy" not in {c["name"] for c in taken.json()["choices"]}
    assert from_titles(troupe.player, vasquez) == {"Harpy": ["Prominent", "Noble", "Guardian"]}
    told = "Lady Vasquez took the title Harpy (Camarilla): +Prominent, +Noble, +Guardian"
    for staff in (troupe.lead, troupe.storyteller, troupe.assistant):
        assert told in summaries(staff)
    assert told not in summaries(troupe.narrator)
    assert told not in summaries(troupe.player)
    items = troupe.storyteller.client.get("/notifications").json()["items"]
    item = next(i for i in items if i["summary"] == told)
    assert item["link"] == f"/characters/{vasquez}/status"
    # The player's change, in the character's log.
    assert logged(troupe.session, vasquez, "title.chosen") == [
        {"title": "Harpy", "what": "active", "character_name": "Lady Vasquez"}
    ]
    log = troupe.player.client.get(f"/characters/{vasquez}/log").json()
    assert any("chose the title Harpy for Lady Vasquez (active)" in e["message"] for e in log)
    # Staff see it as active on the Titles tab.
    listed = troupe.assistant.client.get(f"/troupes/{troupe.id}/titles").json()
    [holder] = next(t for t in listed["titles"] if t["name"] == "Harpy")["holders"]
    assert holder["active"]


def test_one_title_is_active_and_switching_changes_the_status(troupe: Troupe) -> None:
    vasquez = member(troupe, "Lady Vasquez")
    assert take(troupe.player, vasquez, "Harpy").status_code == 200

    # Taken beside the Harpy, it gives nothing until made active.
    beside = take(troupe.player, vasquez, "Keeper of Elysium")
    assert beside.status_code == 200, beside.text
    assert [(t["name"], t["active"]) for t in beside.json()["held"]] == [
        ("Harpy", True),
        ("Keeper of Elysium", False),
    ]
    assert from_titles(troupe.player, vasquez) == {"Harpy": ["Prominent", "Noble", "Guardian"]}

    switched = switch(troupe.player, vasquez, "Keeper of Elysium")
    assert switched.status_code == 200, switched.text
    assert from_titles(troupe.player, vasquez) == {"Keeper of Elysium": ["Enforcer", "Guardian"]}
    assert (
        "Lady Vasquez made Keeper of Elysium (Camarilla) the active title, in place of Harpy:"
        " +Enforcer, −Prominent, −Noble"
    ) in summaries(troupe.storyteller)

    # Giving up the active title leaves the Harpy held, and no title active.
    gone = give_up(troupe.player, vasquez, "Keeper of Elysium")
    assert gone.status_code == 200, gone.text
    assert [(t["name"], t["active"]) for t in gone.json()["held"]] == [("Harpy", False)]
    assert from_titles(troupe.player, vasquez) == {}
    assert (
        "Lady Vasquez gave up the title Keeper of Elysium (Camarilla): −Enforcer, −Guardian;"
        " no title is active"
    ) in summaries(troupe.storyteller)

    assert switch(troupe.player, vasquez, "Harpy").status_code == 200
    assert from_titles(troupe.player, vasquez) == {"Harpy": ["Prominent", "Noble", "Guardian"]}

    # Taken and made active at once, in place of the Harpy.
    made = take(troupe.player, vasquez, "Sheriff", active=True)
    assert made.status_code == 200, made.text
    assert from_titles(troupe.player, vasquez) == {"Sheriff": ["Enforcer", "Privileged"]}
    assert [e["what"] for e in logged(troupe.session, vasquez, "title.made_active")] == [
        "in place of Harpy",
        "none was active",
    ]
    assert switch(troupe.player, vasquez, "Prince").status_code == 422
    assert give_up(troupe.player, vasquez, "Prince").status_code == 422


def test_a_unique_title_someone_holds_is_staffs_to_give(troupe: Troupe) -> None:
    varga = member(troupe, "Elena Varga")
    entitle(troupe, varga, "Prince")
    vasquez = member(troupe, "Lady Vasquez")

    choices = {c["name"]: c for c in titles_of(troupe.player, vasquez)["choices"]}

    assert (choices["Prince"]["unique"], choices["Prince"]["holders"]) == (True, ["Elena Varga"])
    assert not choices["Prince"]["open"]
    # Several hold a Primogen.
    assert (choices["Primogen"]["unique"], choices["Primogen"]["open"]) == (False, True)
    refused = take(troupe.player, vasquez, "Prince")
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Elena Varga holds Prince, and only one character holds it at a time:"
        " ask your storytellers."
    )
    staff_view = {c["name"]: c for c in titles_of(troupe.storyteller, vasquez)["choices"]}
    assert staff_view["Prince"]["open"]
    assert take(troupe.storyteller, vasquez, "Prince").status_code == 200
    # Staff giving it tell no one.
    assert not any("took the title Prince" in s for s in summaries(troupe.lead))
    assert logged(troupe.session, vasquez, "title.given")[0]["title"] == "Prince"


def test_a_troupes_own_title_can_be_unique(troupe: Troupe) -> None:
    made = troupe.assistant.client.post(
        f"/troupes/{troupe.id}/titles",
        json={"name": "Master of Revels", "sect": "Camarilla", "status": [], "unique": True},
    )
    assert made.status_code == 201, made.text
    varga = member(troupe, "Elena Varga")
    entitle(troupe, varga, "Master of Revels")
    vasquez = member(troupe, "Lady Vasquez")

    assert take(troupe.player, vasquez, "Master of Revels").status_code == 409
    changed = troupe.assistant.client.put(
        f"/troupes/{troupe.id}/titles/Master of Revels",
        json={"sect": "Camarilla", "status": [], "unique": False},
    )
    assert changed.status_code == 200, changed.text
    taken = take(troupe.player, vasquez, "Master of Revels")
    assert taken.status_code == 200, taken.text
    assert "which gives no status" in summaries(troupe.storyteller)[0]


def test_a_troupe_can_keep_titles_to_staff(troupe: Troupe) -> None:
    vasquez = member(troupe, "Lady Vasquez")
    url = f"/troupes/{troupe.id}"
    assert troupe.lead.client.get(url).json()["titles_by"] == "players"
    assert troupe.assistant.client.patch(url, json={"titles_by": "staff"}).status_code == 403
    changed = troupe.lead.client.patch(url, json={"titles_by": "staff"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["titles_by"] == "staff"

    shown = titles_of(troupe.player, vasquez)
    assert shown["acting"] is None
    assert shown["why"] == "In Lords of the Night, only staff give titles: ask them for one."
    assert not any(c["open"] for c in shown["choices"])
    refused = take(troupe.player, vasquez, "Harpy")
    assert refused.status_code == 409
    assert refused.json()["detail"] == "In Lords of the Night, only staff give titles."

    # Staff give it on the character's tab, as from the Titles tab.
    assert titles_of(troupe.assistant, vasquez)["acting"] == "staff"
    assert take(troupe.assistant, vasquez, "Harpy").status_code == 200
    assert from_titles(troupe.player, vasquez) == {"Harpy": ["Prominent", "Noble", "Guardian"]}
    assert give_up(troupe.player, vasquez, "Harpy").status_code == 409
    # Which title is active stays the player's to choose.
    assert take(troupe.assistant, vasquez, "Primogen").status_code == 200
    assert titles_of(troupe.player, vasquez)["can_switch"]
    assert switch(troupe.player, vasquez, "Primogen").status_code == 200
    assert from_titles(troupe.player, vasquez) == {"Primogen": ["Noble"]}
    log = troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()
    assert any(e["message"] == "lead set Titles on sheets: only staff give titles." for e in log), [
        e["message"] for e in log
    ]


def test_only_titles_of_the_characters_sect_and_troupe(troupe: Troupe) -> None:
    rook = member(troupe, "Rook", sect="Sabbat", clan="Lasombra")

    refused = take(troupe.player, rook, "Harpy")
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Harpy is a Camarilla title, and Rook is Sabbat."
    assert take(troupe.player, rook, "Emperor").status_code == 422
    assert take(troupe.stranger, rook, "Bishop").status_code in (403, 404)
    assert take(troupe.player, rook, "Bishop").status_code == 200
    assert take(troupe.player, rook, "Bishop").status_code == 409  # held already

    homeless_id = troupe.player.client.post(
        "/characters", json={"name": "Wanderer", "splat": "vampire"}
    ).json()["id"]
    shown = titles_of(troupe.player, homeless_id)
    assert shown["why"] == "Wanderer has no home troupe: titles are held in a troupe."
    assert shown["choices"] == []


def test_staff_giving_titles_makes_the_first_active(troupe: Troupe) -> None:
    roth = member(troupe, "Roth")

    entitle(troupe, roth, "Primogen", "Seneschal")
    held = {t["name"]: t["active"] for t in titles_of(troupe.player, roth)["held"]}
    # Given together, the highest at court.
    assert held == {"Seneschal": True, "Primogen": False}

    entitle(troupe, roth, "Primogen", "Seneschal", "Whip")
    assert not next(t for t in titles_of(troupe.player, roth)["held"] if t["name"] == "Whip")[
        "active"
    ]
    # Taking the active one leaves none active.
    entitle(troupe, roth, "Primogen", "Whip")
    assert not any(t["active"] for t in titles_of(troupe.player, roth)["held"])
    entry = next(
        e
        for e in troupe.lead.client.get(f"/troupes/{troupe.id}/whos-who").json()["entries"]
        if e["name"] == "Roth"
    )
    assert entry["active_title"] is None


def test_the_migration_keeps_the_highest_title_active(
    engine: Engine, alembic_config: Config
) -> None:
    before = ScriptDirectory.from_config(alembic_config).get_revision("0109").down_revision
    assert isinstance(before, str)
    command.downgrade(alembic_config, before)
    user, troupe, character = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'titled@example.com', 'Titled', 'titled')"
                ),
                {"id": user},
            )
            connection.execute(
                text("insert into troupes (id, name, lead_user_id) values (:id, 'Court', :lead)"),
                {"id": troupe, "lead": user},
            )
            connection.execute(
                text(
                    "insert into characters (id, player_id, splat, name, home_troupe_id)"
                    " values (:id, :player, 'vampire', 'Varga', :troupe)"
                ),
                {"id": character, "player": user, "troupe": troupe},
            )
            for name in ("Harpy", "Soldier", "Prince"):
                connection.execute(
                    text(
                        "insert into character_titles (troupe_id, character_id, name)"
                        " values (:troupe, :character, :name)"
                    ),
                    {"troupe": troupe, "character": character, "name": name},
                )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            active = connection.execute(
                text("select name from character_titles where character_id = :id and active"),
                {"id": character},
            ).all()
        assert [r[0] for r in active] == ["Prince"]
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            connection.execute(
                text("delete from character_titles where character_id = :id"), {"id": character}
            )
            connection.execute(text("delete from characters where id = :id"), {"id": character})
            connection.execute(text("delete from troupes where id = :id"), {"id": troupe})
            connection.execute(text("delete from users where id = :id"), {"id": user})
        load_rules(engine)

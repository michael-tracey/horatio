"""Vampiric Texts are equipment, given by storytellers and never chosen (issue #341):
no sheet offers them; staff give one from the catalogue's texts or by a name of the
troupe's own; a player passes it on or discards it, as any item, but never equips
it; and migration 0115 makes each text held as a trait an item."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, sign_up
from tests.conftest import load_rules
from tests.test_api_downtimes import member_character
from tests.test_api_equipment_passing import equipment_of, give_to, history, names
from tests.test_api_play import send, tap, view
from tests.test_api_troupe_equipment import give, given, listed

NOD = {
    "name": "The Book of Nod",
    "kind": "text",
    "grade": "standard",
    "qualities": [],
    "description": "The legends of Caine and the first vampires.",
}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def second(client_for: Callable[[], TestClient]) -> Person:
    return sign_up(client_for, "second")


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    return member_character(troupe, troupe.player, "Agnes")


@pytest.fixture
def bram(troupe: Troupe, second: Person) -> str:
    return member_character(troupe, second, "Bram")


def test_no_sheet_offers_a_vampiric_text(troupe: Troupe, agnes: str) -> None:
    # The ghoul's rules file is checked in tests/test_equipment.py.
    response = troupe.player.client.get("/rules/vampire")
    assert response.status_code == 200, response.text
    rules = response.json()
    assert "vampiric_texts" not in {c["key"] for c in rules["categories"]}
    assert not any(t["category"] == "vampiric_texts" for t in rules["traits"])
    bought = troupe.player.client.put(
        f"/characters/{agnes}/traits",
        json={"category": "vampiric_texts", "name": "The Book of Nod", "rating": None},
    )
    assert bought.status_code >= 400


def test_the_texts_are_templates_to_give_from(troupe: Troupe) -> None:
    rules = troupe.storyteller.client.get("/rules/vampire/equipment").json()
    assert rules["kinds"][-1]["key"] == "text"
    texts = {t["name"]: t for t in rules["templates"] if t["kind"] == "text"}
    assert len(texts) == 35
    assert texts["The Book of Nod"]["page"] == "28, 421 & 453"
    assert texts["The Book of Nod"]["description"].startswith("The legends of Caine")
    assert texts["The Analects of Saulot"]["page"] is None


def test_a_storyteller_gives_the_book_of_nod_and_a_player_cannot(
    troupe: Troupe, agnes: str
) -> None:
    nod = given(troupe, agnes, **NOD, template="The Book of Nod")

    assert (nod["kind"], nod["kind_name"]) == ("text", "Vampiric text")
    assert nod["qualities"] == [] and nod["modifiers"] == []
    assert nod["facts"] == {
        "hands": None,
        "damage": None,
        "shots": None,
        "range": None,
        "aggravated_against": [],
    }
    assert not nod["from_sheet"]
    # Its player sees it, and was told.
    assert names(troupe.player, agnes) == ["The Book of Nod"]
    held = equipment_of(troupe.player, agnes)
    assert held["items"][0]["description"] == NOD["description"]
    assert not held["can_give"]
    # A player can't give one to their own character, from the book or of their own.
    assert give(troupe, agnes, troupe.player, **NOD).status_code == 403
    mine = {**NOD, "name": "My Diary", "grade": "special"}
    assert give(troupe, agnes, troupe.player, **mine).status_code == 403


def test_a_text_of_the_troupes_own_and_what_a_text_cannot_be(troupe: Troupe, agnes: str) -> None:
    own = given(troupe, agnes, name="The Ashen Codex", kind="text", grade="special", qualities=[])
    assert own["special"] and own["special_troupe_name"] == "Lords of the Night"

    for refused, why in (
        ({**NOD, "qualities": [{"name": "Accurate"}]}, "Accurate isn't a vampiric text quality."),
        ({**NOD, "grade": "cheap"}, "A text is standard"),
        ({**NOD, "crafted": True}, "A text isn't crafted."),
    ):
        response = give(troupe, agnes, **refused)
        assert response.status_code == 422, refused
        assert why in response.json()["detail"]
    checked = troupe.storyteller.client.post(
        "/rules/vampire/equipment/check", json={"kind": "text", "grade": "cheap"}
    ).json()
    assert checked["problems"] == [
        "A text is standard, as the books' texts are, or special, one of the troupe's own."
    ]


def test_the_player_passes_a_text_to_another_character_and_the_history_shows_both(
    troupe: Troupe, second: Person, agnes: str, bram: str
) -> None:
    nod = given(troupe, agnes, **NOD, template="The Book of Nod")

    response = give_to(troupe.player, agnes, nod, bram, "For safe keeping")
    assert response.status_code == 200, response.text
    assert names(second, bram) == ["The Book of Nod"]
    assert names(troupe.player, agnes) == []
    assert history(troupe, nod) == [
        ("Given to Agnes by Lords of the Night, from the template The Book of Nod", ""),
        ("Given by Agnes to Bram", "For safe keeping"),
    ]
    # Bram's player discards it; staff restore it.
    discarded = second.client.post(
        f"/characters/{bram}/equipment/{nod['id']}/discard", json={"note": "Burnt"}
    )
    assert discarded.status_code == 200, discarded.text
    restored = troupe.storyteller.client.post(f"/troupes/{troupe.id}/equipment/{nod['id']}/restore")
    assert restored.status_code == 200, restored.text
    assert names(second, bram) == ["The Book of Nod"]
    # The troupe's tab finds it by its kind.
    assert [i["name"] for i in listed(troupe, kind="text")] == ["The Book of Nod"]


def test_a_text_is_never_equipped(troupe: Troupe, agnes: str) -> None:
    nod = given(troupe, agnes, **NOD)
    knife = given(
        troupe, agnes, name="Knife", kind="melee", grade="cheap", qualities=[{"name": "Fast"}]
    )

    state = view(troupe.player, agnes)
    assert [i["name"] for i in state["equipment"]] == ["Knife"]
    state = send(troupe.player, agnes, tap(f"equip:{nod['id']}", 1), tap(f"equip:{knife['id']}", 1))
    assert state["equipped"] == [knife["id"]]


# --- migration 0115 -----------------------------------------------------------------------


def insert(connection: Any, table: str, **values: Any) -> uuid.UUID:
    columns = ", ".join(values)
    marks = ", ".join(f":{k}" for k in values)
    return connection.scalar(
        text(f"insert into {table} ({columns}) values ({marks}) returning id"), values
    )


def test_the_migration_makes_each_text_held_as_a_trait_an_item(
    engine: Engine, alembic_config: Config
) -> None:
    """A PC with a home troupe, and one without, each holding a text as a trait (one
    spelt with the catalogue's broken apostrophe): each holds it as an item after,
    with its history line, and the trait and its category are gone."""
    command.downgrade(alembic_config, "0114")
    try:
        with engine.begin() as connection:
            rule_set = connection.scalar(text("select id from rule_sets where splat = 'vampire'"))
            category = insert(
                connection,
                "trait_categories",
                rule_set_id=rule_set,
                key="vampiric_texts",
                name="Vampiric Texts",
                group_name="Backgrounds",
                position=999,
                rated=False,
            )
            nod = insert(
                connection, "trait_definitions", category_id=category, name="The Book of Nod"
            )
            wounds = insert(
                connection,
                "trait_definitions",
                category_id=category,
                name="Karavalanisha Vrana/Wounds of the Night�s Sword",
            )
            insert(
                connection, "cost_rules", rule_set_id=rule_set, category_id=category, scheme="free"
            )
            user = insert(
                connection,
                "users",
                email="texts@example.com",
                display_name="Reader",
                handle="texts-reader",
            )
            court = insert(connection, "troupes", name="Court of Texts", lead_user_id=user)
            ingrid = insert(
                connection,
                "characters",
                player_id=user,
                splat="vampire",
                name="Ingrid",
                home_troupe_id=court,
            )
            wanderer = insert(
                connection, "characters", player_id=user, splat="vampire", name="Wanderer"
            )
            insert(
                connection,
                "character_traits",
                character_id=ingrid,
                trait_definition_id=nod,
                note="Her sire's copy",
            )
            insert(
                connection, "character_traits", character_id=wanderer, trait_definition_id=wounds
            )
            connection.execute(
                text(
                    "insert into sheet_versions (character_id, troupe_id, number, snapshot,"
                    " approved_by) values (:character, :troupe, 1, cast(:snapshot as jsonb),"
                    " :user)"
                ),
                {
                    "character": ingrid,
                    "troupe": court,
                    "user": user,
                    "snapshot": '[{"category": "vampiric_texts", "name": "The Book of Nod"},'
                    ' {"category": "clan", "name": "Brujah"}]',
                },
            )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            items = connection.execute(
                text(
                    "select i.id, c.name as holder, i.name, i.kind, i.grade, i.troupe_id,"
                    " i.given_by, i.description, i.status, i.from_sheet from equipment_items i"
                    " join characters c on c.id = i.character_id"
                    " where c.id in (:ingrid, :wanderer) order by c.name"
                ),
                {"ingrid": ingrid, "wanderer": wanderer},
            ).all()
            assert [
                (i.holder, i.name, i.kind, i.grade, i.troupe_id, i.given_by, i.status)
                for i in items
            ] == [
                ("Ingrid", "The Book of Nod", "text", "standard", court, None, "held"),
                (
                    "Wanderer",
                    "Karavalanisha Vrana/Wounds of the Night's Sword",
                    "text",
                    "standard",
                    None,
                    None,
                    "held",
                ),
            ]
            assert items[0].description == "Her sire's copy"
            assert all(i.from_sheet for i in items)
            events = connection.execute(
                text(
                    "select action, to_name, troupe_id, changes from equipment_events"
                    " where item_id = :item"
                ),
                {"item": items[0].id},
            ).all()
            assert [(e.action, e.to_name, e.troupe_id, e.changes) for e in events] == [
                ("given", "Ingrid", court, {"from_sheet": True})
            ]
            assert not connection.scalar(
                text("select count(*) from character_traits where character_id in (:a, :b)"),
                {"a": ingrid, "b": wanderer},
            )
            assert not connection.scalar(
                text("select count(*) from trait_categories where key = 'vampiric_texts'")
            )
            snapshot = connection.scalar(
                text("select snapshot from sheet_versions where character_id = :c"), {"c": ingrid}
            )
            assert snapshot == [{"category": "clan", "name": "Brujah"}]
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            user = "(select id from users where handle = 'texts-reader')"
            characters = f"(select id from characters where player_id in {user})"
            for table, column in (
                ("equipment_items", "character_id"),
                ("sheet_versions", "character_id"),
                ("character_traits", "character_id"),
                ("characters", "id"),
            ):
                connection.execute(text(f"delete from {table} where {column} in {characters}"))
            connection.execute(text(f"delete from troupes where lead_user_id in {user}"))
            connection.execute(text(f"delete from users where id in {user}"))
        load_rules(engine)


def test_a_text_moved_from_the_sheet_says_so(
    troupe: Troupe, second: Person, agnes: str, bram: str, session: Session
) -> None:
    """As the migration leaves it: its history line, and the card's own words."""
    session.execute(
        text(
            "with made as (insert into equipment_items (character_id, troupe_id, given_at,"
            " name, kind, grade, from_sheet) values (:agnes, :troupe, now(), 'The Book of Nod',"
            " 'text', 'standard', true) returning id)"
            " insert into equipment_events (item_id, action, troupe_id, to_character_id,"
            " to_name, changes) select id, 'given', :troupe, :agnes, 'Agnes',"
            " '{\"from_sheet\": true}' from made"
        ),
        {"agnes": agnes, "troupe": troupe.id},
    )
    session.flush()
    [nod] = equipment_of(troupe.player, agnes)["items"]
    assert nod["from_sheet"] and nod["given_by_name"] is None
    assert give_to(troupe.player, agnes, nod, bram).status_code == 200
    assert history(troupe, nod) == [
        ("Moved from Agnes's sheet, where it was a trait", ""),
        ("Given by Agnes to Bram", ""),
    ]

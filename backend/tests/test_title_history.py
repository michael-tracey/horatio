"""The court over time (#712): every holding of a title, from when it began to when it
ended, kept as titles change; recovered from the log for the time before; shown to a
troupe's staff with status over time, and to its players only where it lets them."""

import importlib.util
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.conftest import load_rules
from tests.test_api_character_titles import give_up, take
from tests.test_api_leaving import retire
from tests.test_api_sect_status import add, entitle, logged, member, remove, status


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def court(person: Person, troupe: Troupe) -> dict[str, Any]:
    response = person.client.get(f"/troupes/{troupe.id}/court-history")
    assert response.status_code == 200, response.text
    return response.json()


def tenures(person: Person, troupe: Troupe) -> list[tuple[str, str, str | None, str | None]]:
    """Each holding: who, of what, how it began and how it ended (None: held still)."""
    return [
        (h["character_name"], h["title"], h["began_how"], h["ended_how"])
        for h in court(person, troupe)["holdings"]
    ]


# --- kept as titles change ----------------------------------------------------------------------


def test_each_way_a_title_changes_begins_or_ends_a_holding(troupe: Troupe) -> None:
    varga = member(troupe, "Varga")

    entitle(troupe, varga, "Prince")  # given by staff
    assert take(troupe.player, varga, "Harpy").status_code == 200  # chosen by the player
    assert give_up(troupe.player, varga, "Harpy").status_code == 200  # given up by the player
    entitle(troupe, varga)  # staff take the Prince
    entitle(troupe, varga, "Prince")  # and give it back

    assert tenures(troupe.storyteller, troupe) == [
        ("Varga", "Prince", "given", "taken"),
        ("Varga", "Harpy", "chosen", "given_up"),
        ("Varga", "Prince", "given", None),
    ]
    holdings = court(troupe.storyteller, troupe)["holdings"]
    assert holdings[0]["ended_at"] is not None and holdings[2]["ended_at"] is None
    assert not any(h["backfilled"] for h in holdings)
    # In court order: the Prince first.
    assert [t["name"] for t in court(troupe.storyteller, troupe)["titles"]] == ["Prince", "Harpy"]


def test_retiring_leaving_and_removing_a_title_end_holdings(troupe: Troupe) -> None:
    roth = member(troupe, "Roth")
    lena = member(troupe, "Lena")
    entitle(troupe, roth, "Seneschal", "Whip")
    added = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/titles",
        json={"name": "Master of Revels", "sect": None, "status": []},
    )
    assert added.status_code < 300, added.text
    entitle(troupe, lena, "Master of Revels")

    retire(troupe.player, roth, reason="final_death", listed=True)
    removed = troupe.storyteller.client.delete(f"/troupes/{troupe.id}/titles/Master of Revels")
    assert removed.status_code == 200, removed.text

    assert sorted(tenures(troupe.storyteller, troupe)) == [
        ("Lena", "Master of Revels", "given", "removed"),
        ("Roth", "Seneschal", "given", "retired"),
        ("Roth", "Whip", "given", "retired"),
    ]


def test_a_character_leaving_the_troupe_leaves_its_titles(troupe: Troupe) -> None:
    mara = member(troupe, "Mara")
    entitle(troupe, mara, "Keeper of Elysium")

    left = troupe.player.client.delete(f"/characters/{mara}/troupes/{troupe.id}")
    assert left.status_code < 300, left.text

    assert tenures(troupe.storyteller, troupe) == [("Mara", "Keeper of Elysium", "given", "left")]


def test_a_deleted_characters_holdings_stay_under_its_name(troupe: Troupe) -> None:
    ilse = member(troupe, "Ilse")
    entitle(troupe, ilse, "Sheriff")
    left = troupe.player.client.delete(f"/characters/{ilse}/troupes/{troupe.id}")
    assert left.status_code < 300, left.text

    assert troupe.player.client.delete(f"/characters/{ilse}").status_code == 204

    [holding] = court(troupe.storyteller, troupe)["holdings"]
    assert (holding["character_id"], holding["character_name"], holding["title"]) == (
        None,
        "Ilse",
        "Sheriff",
    )
    assert holding["ended_how"] == "left"


# --- who sees it --------------------------------------------------------------------------------


def test_staff_see_it_and_players_only_where_the_troupe_lets_them(troupe: Troupe) -> None:
    varga = member(troupe, "Varga")
    entitle(troupe, varga, "Prince")
    for person in (troupe.lead, troupe.storyteller, troupe.assistant):
        assert court(person, troupe)["full"]
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        got = person.client.get(f"/troupes/{troupe.id}/court-history")
        assert got.status_code == 403, person

    switched = troupe.lead.client.patch(
        f"/troupes/{troupe.id}", json={"court_history_players": True}
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["court_history_players"]

    shown = court(troupe.player, troupe)
    assert not shown["full"] and shown["players_see"]
    assert shown["status"] is None
    [holding] = shown["holdings"]
    assert (holding["title"], holding["began_how"], holding["ended_how"]) == ("Prince", None, None)
    # Not a member: still not.
    assert troupe.stranger.client.get(f"/troupes/{troupe.id}/court-history").status_code == 403
    # Only those who set house rules switch it.
    assert (
        troupe.player.client.patch(
            f"/troupes/{troupe.id}", json={"court_history_players": False}
        ).status_code
        == 403
    )
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert any("set the court over time to show to players and staff" in m for m in log)


def test_staff_give_a_holding_its_in_game_dates(troupe: Troupe) -> None:
    varga = member(troupe, "Varga")
    entitle(troupe, varga, "Prince")
    entitle(troupe, varga)
    [holding] = court(troupe.storyteller, troupe)["holdings"]
    url = f"/troupes/{troupe.id}/court-history/{holding['id']}/in-game"

    dated = troupe.storyteller.client.put(
        url, json={"began_in_game": "1791-03-01", "ended_in_game": "1888-10-31"}
    )

    assert dated.status_code == 200, dated.text
    assert (dated.json()["began_in_game"], dated.json()["ended_in_game"]) == (
        "1791-03-01",
        "1888-10-31",
    )
    assert logged(troupe.session, varga, "title.dated") == [
        {
            "title": "Prince",
            "what": "began 1791-03-01, ended 1888-10-31",
            "character_name": "Varga",
        }
    ]
    backwards = troupe.storyteller.client.put(
        url, json={"began_in_game": "1888-10-31", "ended_in_game": "1791-03-01"}
    )
    assert backwards.status_code == 422
    assert troupe.player.client.put(url, json={"began_in_game": "1800-01-01"}).status_code == 403

    entitle(troupe, varga, "Prince")
    held = next(h for h in court(troupe.storyteller, troupe)["holdings"] if not h["ended_how"])
    still = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/court-history/{held['id']}/in-game",
        json={"ended_in_game": "1900-01-01"},
    )
    assert still.status_code == 422
    assert "holds it still" in still.json()["detail"]


def test_status_over_time_is_worked_back_from_what_is_held_now(troupe: Troupe) -> None:
    agnes = member(troupe, "Agnes")
    assert add(troupe.storyteller, agnes, "Acclaimed", reason="A fine speech").status_code == 200
    assert add(troupe.storyteller, agnes, "Warned", reason="Rudeness").status_code == 200
    acclaimed = next(h for h in status(troupe.player, agnes)["held"] if h["name"] == "Acclaimed")
    assert remove(troupe.storyteller, agnes, acclaimed["id"], "Spent at court").status_code == 200

    [line] = court(troupe.storyteller, troupe)["status"]

    assert line["name"] == "Agnes"
    assert (line["gained"], line["lost"]) == (2, 1)
    counts = [(p["fleeting"], p["negative"]) for p in line["points"]]
    # From her making: none; then Acclaimed, then Warned beside it, then Acclaimed gone.
    assert counts == [(0, 0), (1, 0), (1, 1), (0, 1)]
    times = [p["at"] for p in line["points"]]
    assert times == sorted(times)


# --- recovered from the log ---------------------------------------------------------------------


def migration() -> ModuleType:
    path = Path(__file__).parent.parent / "migrations" / "versions" / "0186_title_history.py"
    spec = importlib.util.spec_from_file_location("title_history_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


START = datetime(2026, 1, 1, tzinfo=UTC)


def at(days: int) -> datetime:
    return START + timedelta(days=days)


def test_the_replay_opens_and_closes_holdings_as_the_log_says() -> None:
    m = migration()
    court_, varga, roth = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def event(day: int, action: str, who: uuid.UUID | None, name: str, **data: Any) -> Any:
        return m.Event(at(day), action, court_, who, name, data)

    found = m.replay(
        [
            event(1, "title.given", varga, "Varga", title="Prince"),
            event(2, "title.chosen", roth, "Roth", title="Harpy"),
            event(3, "title.given", roth, "Roth", title="Whip"),
            event(4, "title.taken", varga, "Varga", title="Prince"),
            # Retiring names its titles as a sentence.
            event(5, "title.given_up", roth, "Roth", kind="retiring", titles="Harpy and Whip"),
            event(6, "title.given", varga, "Varga", title="Prince"),
            # Taken, with nothing in the log to say when it was given.
            event(7, "title.taken", varga, "Varga", title="Sheriff"),
        ],
        [
            m.Held(court_, varga, "Varga", "Prince", at(6)),
            m.Held(court_, varga, "Varga", "Scourge", at(2)),
        ],
    )

    got = [
        (t.character_name, t.name, t.began_how, t.ended_how, t.began_at, t.ended_at)
        for t in found.tenures
    ]
    assert got == [
        ("Varga", "Prince", "given", "taken", at(1), at(4)),
        ("Roth", "Harpy", "chosen", "retired", at(2), at(5)),
        ("Roth", "Whip", "given", "retired", at(3), at(5)),
        ("Varga", "Prince", "given", None, at(6), None),
        # Held now, never opened in the log: from when its row was made.
        ("Varga", "Scourge", "unknown", None, at(2), None),
    ]
    assert (found.begun_from_log, found.begun_from_rows, found.ends_without_start) == (4, 1, 1)


def test_the_replay_closes_what_a_deleted_character_or_a_lost_record_left_open() -> None:
    m = migration()
    court_, kept = uuid.uuid4(), uuid.uuid4()
    found = m.replay(
        [
            # A deleted character: no id, its name kept.
            m.Event(at(1), "title.given", court_, None, "Ilse", {"title": "Sheriff"}),
            m.Event(at(3), "title.given", court_, None, "Ilse", {"title": "Hound"}),
            m.Event(at(4), "title.given_up", court_, None, "Ilse", {"title": "Hound"}),
            # Given, and no longer held, with nothing in between.
            m.Event(at(2), "title.given", court_, kept, "Bram", {"title": "Whip"}),
            m.Event(at(5), "troupe.leave", court_, kept, "Bram", {}),
            m.Event(at(6), "title.given", court_, kept, "Bram", {"title": "Primogen"}),
        ],
        [],
    )
    got = {(t.character_name, t.name): (t.ended_how, t.ended_at) for t in found.tenures}
    assert got == {
        ("Ilse", "Sheriff"): ("deleted", at(4)),
        ("Ilse", "Hound"): ("given_up", at(4)),
        ("Bram", "Whip"): ("left", at(5)),
        ("Bram", "Primogen"): ("unknown", at(6)),
    }
    assert found.closed_as_unknown == 2


def test_names_in_a_retiring_list_match_titles_with_and_in_their_name() -> None:
    m = migration()
    assert m.names_in("Prince, Harpy and Whip", []) == ["Prince", "Harpy", "Whip"]
    assert sorted(m.names_in("Keeper and Warden and Whip", ["Keeper and Warden"])) == [
        "Keeper and Warden",
        "Whip",
    ]


def test_the_migration_backfills_from_the_log(engine: Engine, alembic_config: Config) -> None:
    command.downgrade(alembic_config, "0181")
    user, court_, varga = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'courtly@example.com', 'Courtly', 'courtly')"
                ),
                {"id": user},
            )
            connection.execute(
                text(
                    "insert into troupes (id, name, lead_user_id) values (:id, 'Court of Ash', :u)"
                ),
                {"id": court_, "u": user},
            )
            connection.execute(
                text(
                    "insert into characters (id, player_id, splat, name, home_troupe_id)"
                    " values (:id, :u, 'vampire', 'Varga', :t)"
                ),
                {"id": varga, "u": user, "t": court_},
            )
            connection.execute(
                text(
                    "insert into character_titles (troupe_id, character_id, name, created_at)"
                    " values (:t, :c, 'Prince', :at)"
                ),
                {"t": court_, "c": varga, "at": at(3)},
            )
            for day, action, who, data in (
                (1, "title.given", varga, '{"title": "Seneschal", "character_name": "Varga"}'),
                (2, "title.taken", varga, '{"title": "Seneschal", "character_name": "Varga"}'),
                (3, "title.given", varga, '{"title": "Prince", "character_name": "Varga"}'),
                # A character since deleted: the log keeps only its name.
                (1, "title.chosen", None, '{"title": "Harpy", "character_name": "Old Mags"}'),
            ):
                connection.execute(
                    text(
                        "insert into audit_events (troupe_id, character_id, action, data,"
                        " created_at) values (:t, :c, :a, cast(:d as jsonb), :at)"
                    ),
                    {"t": court_, "c": who, "a": action, "d": data, "at": at(day)},
                )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "select character_id, character_name, name, began_how, ended_how, backfilled,"
                    " began_at from title_holdings where troupe_id = :t order by began_at, name"
                ),
                {"t": court_},
            ).all()
        assert [tuple(r) for r in rows] == [
            (None, "Old Mags", "Harpy", "chosen", "deleted", True, at(1)),
            (varga, "Varga", "Seneschal", "given", "taken", True, at(1)),
            (varga, "Varga", "Prince", "given", None, True, at(3)),
        ]
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            for sql in (
                "delete from title_holdings where troupe_id = :t",
                "delete from audit_events where troupe_id = :t",
                "delete from character_titles where troupe_id = :t",
                "delete from characters where home_troupe_id = :t",
                "delete from troupes where id = :t",
            ):
                connection.execute(text(sql), {"t": court_})
            connection.execute(text("delete from users where id = :u"), {"u": user})
        load_rules(engine)

"""The audit log's levels, what the custodian records, and how long it is kept (#1062)."""

import ast
import importlib
import pkgutil
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import horatio
from horatio import audit, audit_retention, locations
from horatio.models import AuditEvent
from tests.api_helpers import PASSWORD, Person, Troupe, new_character, sign_up

# --- every reader of the log keeps what it reads ---------------------------------------------

# Every module that names AuditEvent, and what it does with the log. A new one
# fails here until it is listed: if it reads actions back as history, filter them
# by `AuditEvent.action == ...` or `.in_(...)`, so the checks below find them, and
# make them notice in horatio.audit.
USES = {
    "horatio.audit": "writes the log",
    "horatio.audit_retention": "deletes what is kept long enough",
    "horatio.deletion": "forgets a deleted character's id",
    "horatio.api.audit": "the custodian's search: shows whatever is kept",
    "horatio.api.roster": "a troupe's log: shows whatever is kept but debug",
    "horatio.api.character_log": "a character's log: shows whatever is kept but debug",
    "horatio.api.locations": "a location's log: every location.* action, all notice",
    "horatio.locations": "a location's log: every location.* action, all notice",
    "horatio.bonds": "hides bond events while a troupe tracks no bonds",
    "horatio.boons": "hides boon events while a troupe keeps no boon ledger",
    "horatio.title_history": "reads by action",
    "horatio.chronicle": "reads by action",
    "horatio.closing": "reads by action",
    "horatio.downtimes": "reads by action",
    "horatio.troupe_fit": "reads by action",
    "horatio.play_influence": "reads by action",
    "horatio.import_boons": "reads by action",
    "horatio.import_influence_log": "reads by action",
    "horatio.auth.resets": "reads by action",
    "horatio.api.suspensions": "reads by action",
    "horatio.api.email_changes": "reads by action",
    "horatio.api.players": "reads by action",
    "horatio.api.site_services": "reads by action",
}

# Where AuditEvent.action is matched other than by ==/in_, and why that reads no
# history: each hides or skips events from a log that shows whatever is kept.
FILTERS = {
    ("horatio.api.audit", "startswith"),  # a kind of change, in the search
    ("horatio.api.audit", "not_in"),  # words of actions with no wording
    ("horatio.api.audit", "in_"),  # actions whose wording has the words searched
    ("horatio.api.character_log", "not_in"),  # what a player isn't told
    ("horatio.audit_retention", "not_in"),  # keeps every notice action from the purge
    ("horatio.bonds", "startswith"),
    ("horatio.boons", "startswith"),
}


def modules() -> Iterator[ModuleType]:
    for found in pkgutil.walk_packages(horatio.__path__, "horatio."):
        module = importlib.import_module(found.name)
        if (getattr(module, "__file__", None) or "").endswith(".py"):
            yield module


def tree(module: ModuleType) -> ast.Module:
    return ast.parse(Path(str(module.__file__)).read_text())


def is_action(node: ast.AST) -> bool:
    """`AuditEvent.action`."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "action"
        and isinstance(node.value, ast.Name)
        and node.value.id == "AuditEvent"
    )


def evaluated(module: ModuleType, node: ast.expr) -> Any:
    """What an expression in the module's code is, from the module's own names."""
    return eval(ast.unparse(node), vars(module))


def actions_in(value: Any) -> set[str]:
    return {value} if isinstance(value, str) else set(value)


def reads() -> Iterator[tuple[str, str]]:
    """Each module that reads the log by action, and each action it reads: wherever
    `AuditEvent.action == x` or `AuditEvent.action.in_(x)` is, with `x` worked out
    from the module's own names. Fails on a module or a match it can't place."""
    unlisted: set[str] = set()
    unknown: set[tuple[str, str]] = set()
    for module in modules():
        code = tree(module)
        names = any(isinstance(n, ast.Name) and n.id == "AuditEvent" for n in ast.walk(code))
        if names and module.__name__ not in USES and ".models" not in module.__name__:
            unlisted.add(module.__name__)
        for node in ast.walk(code):
            matched: ast.expr | None = None
            if isinstance(node, ast.Compare) and is_action(node.left):
                assert isinstance(node.ops[0], ast.Eq), (module.__name__, node.lineno)
                matched = node.comparators[0]
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and is_action(node.func.value)
                and (module.__name__, node.func.attr) not in FILTERS
            ):
                if node.func.attr != "in_":
                    unknown.add((module.__name__, node.func.attr))
                    continue
                matched = node.args[0]
            if matched is not None:
                for action in actions_in(evaluated(module, matched)):
                    yield module.__name__, action
    assert not unlisted, f"Say what these do with the audit log, in USES: {unlisted}"
    assert not unknown, f"Add these to FILTERS, or read by == or in_: {unknown}"


def recorded_calls() -> Iterator[tuple[ModuleType, ast.Call]]:
    """Every call of audit.record in Horatio's code."""
    for module in modules():
        for node in ast.walk(tree(module)):
            if isinstance(node, ast.Call) and len(node.args) >= 3:
                try:
                    called = evaluated(module, node.func)
                except Exception:
                    continue
                if called is audit.record:
                    yield module, node


def test_every_action_a_feature_reads_from_the_log_is_kept_forever() -> None:
    """The purge never deletes notice events, so every action read back as history
    must be notice."""
    found = list(reads())
    not_kept = {(module, action) for module, action in found if audit.level(action) != "notice"}
    assert not not_kept, f"Make these notice in horatio.audit: {not_kept}"
    # The readers were found: title history alone reads nine.
    assert len(found) > 30


def test_everything_a_locations_log_reads_is_kept_forever() -> None:
    """A location's log is every event that names it (locations.describe)."""
    found = 0
    for module, call in recorded_calls():
        described = any(
            k.arg is None
            and isinstance(k.value, ast.Call)
            and evaluated(module, k.value.func) is locations.describe
            for k in call.keywords
        )
        if described:
            action = evaluated(module, call.args[2])
            assert audit.level(action) == "notice", action
            found += 1
    assert found >= 8


def test_each_level_names_real_actions() -> None:
    """No misspelling: each action named in DEBUG or NOTICE is recorded somewhere,
    or read back by a feature (some are recorded by a name made up as it goes)."""
    assert not audit.DEBUG & audit.NOTICE
    recorded: set[str] = set()
    for module, call in recorded_calls():
        action = call.args[2]
        for each in (action.body, action.orelse) if isinstance(action, ast.IfExp) else (action,):
            try:
                recorded.add(evaluated(module, each))
            except Exception:
                continue
    read = {action for _, action in reads()}
    assert not (audit.DEBUG | audit.NOTICE) - recorded - read
    assert audit.level("troupe.join") == "debug"
    assert audit.level("sheet.purchase") == "info"
    assert audit.level("character.deleted") == "notice"


# --- what is recorded ------------------------------------------------------------------------


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def events(session: Session, action: str) -> list[AuditEvent]:
    session.flush()
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def set_log(custodian: Person, **settings: Any) -> dict[str, Any]:
    body = {"record": "info", "keep_debug": 30, "keep_info": 365, **settings}
    response = custodian.client.put("/audit/settings", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def sign_in(client_for: Callable[[], TestClient], login: str, password: str) -> TestClient:
    client = client_for()
    client.post("/auth/login", json={"login": login, "password": password})
    return client


DEBUG_SIGNING = (
    "account.signed_up",
    "account.signed_in",
    "account.sign_in_failed",
    "account.signed_out",
)


def sign_in_and_out(client_for: Callable[[], TestClient], name: str) -> None:
    person = sign_up(client_for, name)
    sign_in(client_for, person.email, "not my password")
    sign_in(client_for, "nobody_here@example.com", PASSWORD)
    signed_in = sign_in(client_for, f"@{person.handle}", PASSWORD)
    assert signed_in.post("/auth/logout").status_code == 204


def test_debug_events_are_not_recorded_unless_the_custodian_asks(
    troupe: Troupe, client_for: Callable[[], TestClient], session: Session
) -> None:
    sign_in_and_out(client_for, "quiet")
    agnes = new_character(troupe, troupe.player)
    troupe.player.client.post(f"/characters/{agnes}/troupes", json={"troupe_id": troupe.id})
    for action in (*DEBUG_SIGNING, "troupe.join"):
        assert events(session, action) == [], action
    # Info and notice are, as ever.
    assert [e.level for e in events(session, "staff.assigned")] == ["notice"] * 3
    assert {e.level for e in events(session, "sheet.purchase")} <= {"info"}

    set_log(troupe.custodian, record="debug")
    sign_in_and_out(client_for, "chatty")
    troupe.player.client.post(f"/characters/{agnes}/troupes", json={"troupe_id": troupe.id})
    for action in DEBUG_SIGNING:
        assert {e.level for e in events(session, action)} == {"debug"}, action

    failed = events(session, "account.sign_in_failed")
    assert [(e.actor_id is None, e.data.get("kind")) for e in failed] == [
        (False, None),
        (True, "unknown"),
    ]
    # Never a password, nor what was typed to sign in with.
    for event in session.scalars(select(AuditEvent).where(AuditEvent.level == "debug")):
        assert PASSWORD not in str(event.data)
        assert "not my password" not in str(event.data)
        assert "nobody_here" not in str(event.data)

    # Switched off again: at once.
    set_log(troupe.custodian, record="info")
    sign_in(client_for, "chatty@example.com", PASSWORD)
    assert len(events(session, "account.signed_in")) == 1


def test_debug_events_never_reach_a_troupes_log(troupe: Troupe, session: Session) -> None:
    set_log(troupe.custodian, record="debug")
    agnes = new_character(troupe, troupe.player)
    troupe.player.client.post(f"/characters/{agnes}/troupes", json={"troupe_id": troupe.id})
    joined = "Agnes (player) started visiting the troupe."
    [event] = events(session, "troupe.join")
    assert event.level == "debug"

    def messages(person: Person, url: str, **params: Any) -> list[str]:
        response = person.client.get(url, params=params)
        assert response.status_code == 200, response.text
        found = response.json()
        return [e["message"] for e in (found["entries"] if isinstance(found, dict) else found)]

    assert joined not in messages(troupe.lead, f"/troupes/{troupe.id}/log")
    assert joined not in messages(troupe.lead, f"/characters/{agnes}/log")
    assert joined not in messages(troupe.player, f"/characters/{agnes}/log")
    # The custodian's search finds it, unless asked for info and up.
    assert joined in messages(troupe.custodian, "/audit")
    assert joined in messages(troupe.custodian, "/audit", level="debug")
    assert joined not in messages(troupe.custodian, "/audit", level="info")
    found = troupe.custodian.client.get("/audit", params={"character_id": agnes}).json()
    assert [e["level"] for e in found["entries"] if e["message"] == joined] == ["debug"]
    notices = troupe.custodian.client.get("/audit", params={"level": "notice"}).json()
    assert {e["level"] for e in notices["entries"]} == {"notice"}
    assert "lead made storyteller storyteller." in [e["message"] for e in notices["entries"]]

    export = troupe.custodian.client.get("/audit/export", params={"level": "info"}).text
    assert "Level" in export.splitlines()[0]
    assert joined not in export


# --- the custodian's settings ----------------------------------------------------------------


def test_only_the_custodian_sees_or_changes_the_settings(troupe: Troupe) -> None:
    for person in (troupe.lead, troupe.player):
        assert person.client.get("/audit/settings").status_code == 403
        body = {"record": "debug", "keep_debug": 30, "keep_info": 365}
        assert person.client.put("/audit/settings", json=body).status_code == 403
    found = troupe.custodian.client.get("/audit/settings").json()
    assert found == {"record": "info", "keep_debug": 30, "keep_info": 365, "last_purge": None}


def test_changing_the_settings_is_itself_recorded(troupe: Troupe, session: Session) -> None:
    for wrong in ({"keep_debug": 0}, {"keep_info": 4000}, {"record": "notice"}):
        body = {"record": "info", "keep_debug": 30, "keep_info": 365, **wrong}
        assert troupe.custodian.client.put("/audit/settings", json=body).status_code == 422

    # The same again changes nothing, and records nothing.
    set_log(troupe.custodian)
    assert events(session, "audit.settings_changed") == []

    saved = set_log(troupe.custodian, record="debug", keep_debug=7, keep_info=None)
    assert saved["record"] == "debug"
    assert (saved["keep_debug"], saved["keep_info"]) == (7, None)
    [event] = events(session, "audit.settings_changed")
    assert event.level == "notice"
    found = troupe.custodian.client.get("/audit", params={"level": "notice"}).json()
    assert found["entries"][0]["message"] == (
        "custodian changed the audit log's settings: debug events recorded; debug events"
        " kept 7 days (was 30 days); info events kept forever (was 365 days)."
    )
    assert audit.settings(session) == audit.LogSettings(
        record="debug", keep_debug=7, keep_info=None
    )


# --- the purge -------------------------------------------------------------------------------

NOW = datetime(2026, 11, 19, 3, 0, tzinfo=UTC)


def old(session: Session, action: str, days: int, level: str | None = None) -> uuid.UUID:
    event = AuditEvent(
        action=action,
        level=level or audit.level(action),
        created_at=NOW - timedelta(days=days),
        data={},
    )
    session.add(event)
    session.flush()
    return event.id


def kept(session: Session, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    session.expire_all()
    found = set(session.scalars(select(AuditEvent.id).where(AuditEvent.id.in_(ids))))
    return [i for i in ids if i in found]


def test_the_purge_keeps_each_level_as_long_as_the_custodian_says(session: Session) -> None:
    gone = [
        old(session, "account.signed_in", 31),
        old(session, "troupe.join", 400),
        old(session, "sheet.purchase", 366),
    ]
    stay = [
        old(session, "account.signed_in", 29),
        old(session, "sheet.purchase", 364),
        old(session, "character.deleted", 5000),
        # Recorded before its action was notice: a feature reads it, so it stays.
        old(session, "status.added", 5000, level="info"),
        old(session, "npc.given", 5000, level="debug"),
    ]
    done = audit_retention.purge(session, NOW)
    assert done.deleted == {"debug": 2, "info": 1}
    assert done.finished
    assert kept(session, gone + stay) == stay

    # Info kept forever: only debug goes.
    audit.save_settings(session, audit.LogSettings(keep_debug=1, keep_info=None))
    assert audit_retention.purge(session, NOW + timedelta(days=4000)).deleted == {"debug": 1}
    assert kept(session, stay) == stay[1:]


def test_the_purge_runs_daily_a_batch_at_a_time(
    troupe: Troupe, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit_retention, "BATCH", 2)
    monkeypatch.setattr(audit_retention, "MOST", 3)
    for days in (40, 41, 42, 43):
        old(session, "account.signed_in", days)
    old(session, "sheet.purchase", 500)

    first = audit_retention.purge_due(session, NOW)
    assert first is not None
    assert (first.deleted, first.finished) == ({"debug": 3}, False)
    # Not finished, so the next round carries on, and counts it all as one.
    second = audit_retention.purge_due(session, NOW + timedelta(seconds=15))
    assert second is not None
    assert (second.deleted, second.finished) == ({"debug": 4, "info": 1}, True)
    # Then not again for a day.
    assert audit_retention.purge_due(session, NOW + timedelta(hours=23)) is None
    third = audit_retention.purge_due(session, NOW + timedelta(days=1, seconds=15))
    assert third is not None
    assert (third.deleted, third.finished) == ({}, True)

    found = troupe.custodian.client.get("/audit/settings").json()["last_purge"]
    assert found["debug"] == found["info"] == 0
    assert datetime.fromisoformat(found["at"]) == NOW + timedelta(days=1, seconds=15)

"""Viewing as someone (horatio.auth.viewing): the custodian sees Horatio as one
person does, read-only, for support; it is recorded, and it ends."""

import re
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import Select, select, update
from sqlalchemy.orm import Session

from horatio.api.roster import log_entries
from horatio.app import app
from horatio.auth.viewing import ALLOWED, READ_ONLY
from horatio.models import AuditEvent, Character, Notification, Scene, User, Viewing
from tests.api_helpers import Person, Troupe, new_character, sign_up

REFUSED = "You are viewing Horatio as @player, read-only. Stop viewing to make changes."
PATH_PARAM = re.compile(r"{(\w+)(?::\w+)?}")


def api_routes() -> Iterator[tuple[str, str, list[str], Callable[..., Any] | None]]:
    """Every API route: its method, its path under /api, its path's parameters and
    its endpoint."""
    for route in iter_route_contexts(app.routes):
        path = route.path or ""
        if not path.startswith("/api/"):
            continue
        for method in route.methods or ():
            yield method, path.removeprefix("/api"), PATH_PARAM.findall(path), route.endpoint


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    """The player's character, at home in the troupe."""
    character_id = new_character(troupe, troupe.player)
    asked = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    approved = troupe.lead.client.post(f"/approvals/{asked['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    return character_id


def view_as(custodian: Person, person: Person, reason: str = "Can't find her sheet") -> Any:
    response = custodian.client.post(f"/players/{person.id}/view-as", json={"reason": reason})
    assert response.status_code == 201, response.text
    return response.json()


def account_log() -> Select[AuditEvent, str]:
    return (
        select(AuditEvent, User.display_name)
        .join(User, AuditEvent.actor_id == User.id)
        .where(AuditEvent.action.like("account.view_as%"))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    )


def events(session: Session, action: str) -> list[AuditEvent]:
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.created_at)
        )
    )


def test_the_custodian_sees_horatio_as_the_player_does(troupe: Troupe, agnes: str) -> None:
    custodian = troupe.custodian.client
    started = view_as(troupe.custodian, troupe.player)
    assert (started["handle"], started["reason"]) == ("player", "Can't find her sheet")

    me = custodian.get("/auth/me").json()
    assert (me["handle"], me["is_custodian"]) == ("player", False)
    assert [c["name"] for c in custodian.get("/characters").json()] == ["Agnes"]
    assert [t["name"] for t in custodian.get("/troupes").json()] == ["Lords of the Night"]
    assert custodian.get(f"/characters/{agnes}/play").status_code == 200
    # With the player's permissions, not the custodian's.
    assert custodian.get("/players").status_code == 403
    assert custodian.get("/view-as").json()["handle"] == "player"


def test_every_change_is_refused_while_viewing(troupe: Troupe, agnes: str) -> None:
    """Every route that changes anything, whatever it is, answers 403 before it does."""
    view_as(troupe.custodian, troupe.player)
    checked = 0
    for method, path, params, endpoint in api_routes():
        if method in ("GET", "HEAD", "OPTIONS") or endpoint in ALLOWED:
            continue
        for name in params:
            path = PATH_PARAM.sub(agnes if "character" in name else troupe.id, path, count=1)
        response = troupe.custodian.client.request(method, path, json={})
        assert (response.status_code, response.json()["detail"]) == (403, REFUSED), (method, path)
        checked += 1
    assert checked > 100


def test_play_view_taps_and_marking_notifications_read_are_refused(
    troupe: Troupe, agnes: str, session: Session
) -> None:
    session.add(
        Notification(user_id=uuid.UUID(troupe.player.id), kind="test", summary="Hi", link="/")
    )
    session.flush()
    view_as(troupe.custodian, troupe.player)
    custodian = troupe.custodian.client

    tap = {
        "id": str(uuid.uuid4()),
        "tracker": "blood",
        "change": -1,
        "happened_at": "2026-10-27T20:00:00Z",
    }
    assert custodian.post(f"/characters/{agnes}/play/taps", json=tap).status_code == 403
    assert custodian.post("/notifications/read", json={}).status_code == 403
    assert custodian.get("/notifications").json()["count"] == 2  # this one, and being viewed

    custodian.post("/view-as/stop")
    unread = session.scalars(
        select(Notification).where(
            Notification.user_id == uuid.UUID(troupe.player.id), Notification.read_at.is_(None)
        )
    )
    assert len(list(unread)) == 2
    assert troupe.player.client.get(f"/characters/{agnes}/play").json()["blood"]["value"] == 10


@pytest.mark.parametrize("whom", ["player", "lead"])
def test_pages_that_only_read_still_work_while_viewing(
    troupe: Troupe, agnes: str, whom: str
) -> None:
    """Every GET about the player's character, the troupe or the person answers as it
    would for them: none of them tries to write anything on the side."""
    person: Person = getattr(troupe, whom)
    view_as(troupe.custodian, person)
    values = {"character_id": agnes, "troupe_id": troupe.id, "user_id": person.id}
    checked = 0
    for method, path, params, _ in api_routes():
        if method != "GET" or not set(params) <= set(values):
            continue
        for name in params:
            path = PATH_PARAM.sub(values[name], path, count=1)
        response = troupe.custodian.client.get(path)
        assert response.status_code < 500, (path, response.text)
        assert "Stop viewing to make changes" not in response.text, path
        checked += 1
    assert checked > 50


def test_opening_a_scene_while_viewing_leaves_it_as_it_was(
    troupe: Troupe, session: Session
) -> None:
    made = troupe.storyteller.client.post(f"/troupes/{troupe.id}/scenes", json={"name": "Elysium"})
    scene = session.get_one(Scene, uuid.UUID(made.json()["id"]))
    scene.last_used_at = last_used = datetime.now(UTC) - timedelta(days=1)
    session.flush()
    view_as(troupe.custodian, troupe.storyteller)

    opened = troupe.custodian.client.get(f"/troupes/{troupe.id}/scenes/{scene.id}")

    assert opened.status_code == 200, opened.text
    session.refresh(scene)
    assert scene.last_used_at == last_used


def test_nothing_is_written_even_by_a_read(session: Session, troupe: Troupe) -> None:
    """The database session refuses writes while it serves a viewing."""
    session.info[READ_ONLY] = REFUSED
    try:
        session.execute(update(Character).where(Character.name == "nobody").values(name="somebody"))
        raise AssertionError("the update was let through")
    except Exception as refused:
        assert REFUSED in str(refused)
    finally:
        session.info.pop(READ_ONLY)


def test_starting_and_stopping_are_recorded_with_the_reason(
    troupe: Troupe, session: Session
) -> None:
    view_as(troupe.custodian, troupe.player, "Says her XP is wrong")
    stopped = troupe.custodian.client.post("/view-as/stop")
    assert stopped.status_code == 204

    assert troupe.custodian.client.get("/auth/me").json()["is_custodian"]
    assert troupe.custodian.client.get("/view-as").json() is None
    [started] = events(session, "account.view_as")
    assert str(started.actor_id) == troupe.custodian.id
    assert started.data == {
        "member": "player",
        "user_id": troupe.player.id,
        "handle": "player",
        "reason": "Says her XP is wrong",
    }
    [ended] = events(session, "account.view_as_ended")
    assert (ended.data["kind"], ended.data["user_id"]) == ("stopped", troupe.player.id)
    assert [e.message for e in log_entries(session, account_log())] == [
        "custodian stopped viewing as player.",
        "custodian viewed Horatio as player, read-only (Says her XP is wrong).",
    ]


def test_the_person_is_told_and_sees_it_on_their_account(troupe: Troupe) -> None:
    view_as(troupe.custodian, troupe.player, "Says her XP is wrong")
    troupe.custodian.client.post("/view-as/stop")

    [message] = troupe.player.client.get("/notifications").json()["items"]
    assert message["summary"] == (
        "custodian, the custodian, viewed Horatio as you, read-only: Says her XP is wrong"
    )
    assert message["link"] == "/account"
    [visit] = troupe.player.client.get("/account/viewed-as").json()
    assert (visit["custodian"], visit["reason"]) == ("custodian", "Says her XP is wrong")
    assert visit["until"] >= visit["started_at"]
    assert troupe.stranger.client.get("/account/viewed-as").json() == []


def test_it_ends_after_30_minutes(troupe: Troupe, session: Session) -> None:
    started = view_as(troupe.custodian, troupe.player)
    ends_at = datetime.fromisoformat(started["ends_at"])
    assert timedelta(minutes=29) < ends_at - datetime.now(UTC) <= timedelta(minutes=30)

    session.execute(update(Viewing).values(ends_at=datetime.now(UTC) - timedelta(seconds=1)))
    me = troupe.custodian.client.get("/auth/me").json()

    assert me["is_custodian"]
    [ended] = events(session, "account.view_as_ended")
    assert ended.data["kind"] == "timed_out"
    assert troupe.custodian.client.get("/view-as").json() is None


def test_signing_out_ends_it(troupe: Troupe, session: Session) -> None:
    view_as(troupe.custodian, troupe.player)
    assert troupe.custodian.client.post("/auth/logout").status_code == 204

    [ended] = events(session, "account.view_as_ended")
    assert ended.data["kind"] == "signed_out"
    assert session.scalars(select(Viewing)).one().ended_at is not None


def test_only_the_custodian_and_never_as_a_custodian(
    troupe: Troupe, client_for: Callable[[], TestClient], session: Session
) -> None:
    other = sign_up(client_for, "second", custodian=True, session=session)
    for person, target in ((troupe.lead, troupe.player), (troupe.player, troupe.stranger)):
        refused = person.client.post(f"/players/{target.id}/view-as", json={"reason": "Nosy"})
        assert refused.status_code == 403
    refused = troupe.custodian.client.post(f"/players/{other.id}/view-as", json={"reason": "x"})
    assert (refused.status_code, refused.json()["detail"]) == (
        403,
        "You can't view as a custodian.",
    )
    no_reason = troupe.custodian.client.post(
        f"/players/{troupe.player.id}/view-as", json={"reason": "  "}
    )
    assert no_reason.status_code == 422
    assert session.scalars(select(Viewing)).first() is None


def test_another_sign_in_of_the_custodian_is_unaffected(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    view_as(troupe.custodian, troupe.player)
    elsewhere = client_for()
    elsewhere.post(
        "/auth/login", json={"login": troupe.custodian.email, "password": "correct horse battery"}
    )
    assert elsewhere.get("/auth/me").json()["is_custodian"]
    assert elsewhere.get("/view-as").json() is None

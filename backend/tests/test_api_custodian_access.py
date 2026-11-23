"""Custodian access (horatio.auth.custodian_access, #1213): a custodian is a player by
default, switches the custodian's powers on with their second step and a reason, and
has them for an hour from their last use; the lead storyteller of a troupe they play
in is told, once, when they use them there."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from horatio.auth import two_step
from horatio.auth.custodian_access import HEADER
from horatio.models import AuditEvent, CustodianAccess, Notification, User
from horatio.permissions import SWITCH_ON
from tests.api_helpers import PASSWORD, Person, Troupe, new_character, sign_up


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def at_home(troupe: Troupe, person: Person, name: str) -> str:
    """A character of `person`'s, at home in the troupe."""
    character_id = new_character(troupe, person, name)
    asked = person.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    approved = troupe.lead.client.post(f"/approvals/{asked['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    return character_id


@pytest.fixture
def keeper(troupe: Troupe, client_for: Callable[[], TestClient], session: Session) -> Person:
    """A second custodian, who plays in the troupe, with custodian access off."""
    keeper = sign_up(client_for, "keeper", custodian=True, session=session, switched_on=False)
    at_home(troupe, keeper, "Mina")
    return keeper


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    """Another player's character, at home in the troupe."""
    return at_home(troupe, troupe.player, "Agnes")


def switch_on(person: Person, reason: str = "Checking a reported bug", **given: str) -> dict:
    response = person.client.post(
        "/custodian-access", json={"reason": reason, "password": PASSWORD, **given}
    )
    assert response.status_code == 201, response.text
    return response.json()


def access_of(session: Session, person: Person) -> CustodianAccess:
    return session.scalars(
        select(CustodianAccess)
        .where(CustodianAccess.custodian_id == uuid.UUID(person.id))
        .order_by(CustodianAccess.created_at.desc(), CustodianAccess.id.desc())
    ).first() or pytest.fail("No custodian access")


def leads_notices(session: Session, troupe: Troupe) -> list[Notification]:
    return list(
        session.scalars(
            select(Notification).where(
                Notification.user_id == uuid.UUID(troupe.lead.id),
                Notification.kind == "troupe.custodian_access",
            )
        )
    )


def actions(session: Session, person: Person, prefix: str) -> list[AuditEvent]:
    return list(
        session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.actor_id == uuid.UUID(person.id), AuditEvent.action.startswith(prefix)
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def test_a_custodian_who_plays_sees_only_what_a_player_sees_until_they_switch_on(
    troupe: Troupe, keeper: Person, agnes: str, session: Session
) -> None:
    assert keeper.client.get("/custodian-access").json() == {
        "on": False,
        "reason": None,
        "ends_at": None,
        "second_step": [],
    }
    refused = keeper.client.get(f"/characters/{agnes}")
    assert refused.status_code == 404
    # The app offers to switch it on.
    assert refused.headers[HEADER] == "needed"
    staff_only = keeper.client.get(f"/troupes/{troupe.id}/log")
    assert staff_only.status_code == 403
    assert staff_only.headers[HEADER] == "needed"
    # The player's own refusal says nothing of it.
    other = troupe.stranger.client.get(f"/characters/{agnes}")
    assert other.status_code == 404
    assert HEADER not in other.headers
    # As a player, their own character is theirs as ever.
    mine = keeper.client.get("/characters").json()
    assert [c["name"] for c in mine] == ["Mina"]

    now = switch_on(keeper)
    assert now["on"] is True
    assert now["reason"] == "Checking a reported bug"
    ends = datetime.fromisoformat(now["ends_at"])
    assert timedelta(minutes=59) < ends - datetime.now(UTC) <= timedelta(hours=1)

    assert keeper.client.get(f"/characters/{agnes}").status_code == 200
    assert keeper.client.get(f"/troupes/{troupe.id}/log").status_code == 200
    # The lead is told once for this switch-on, however much more is opened.
    notices = leads_notices(session, troupe)
    assert len(notices) == 1
    assert notices[0].summary == (
        "keeper, the custodian, who plays in Lords of the Night, switched on custodian access"
        " and opened what only its staff see: Checking a reported bug"
    )
    assert notices[0].link == f"/troupes/{troupe.id}/log"
    # Only the bell: never email.
    assert notices[0].troupe_id == uuid.UUID(troupe.id)
    assert [e.data.get("reason") for e in actions(session, keeper, "account.custodian_access")] == [
        "Checking a reported bug"
    ]
    used = actions(session, keeper, "troupe.custodian_access_used")
    assert [(e.troupe_id, e.data["reason"]) for e in used] == [
        (uuid.UUID(troupe.id), "Checking a reported bug")
    ]
    # Switched on again, the lead is told again.
    keeper.client.post("/custodian-access/stop")
    switch_on(keeper, "Another look")
    assert keeper.client.get(f"/characters/{agnes}").status_code == 200
    assert len(leads_notices(session, troupe)) == 2


def test_a_troupe_they_dont_play_in_and_site_wide_work_tell_no_lead(
    troupe: Troupe, client_for: Callable[[], TestClient], session: Session, agnes: str
) -> None:
    keeper = sign_up(client_for, "keeper", custodian=True, session=session, switched_on=False)
    refused = keeper.client.get("/audit")
    assert refused.status_code == 403
    assert refused.json()["detail"] == SWITCH_ON
    assert refused.headers[HEADER] == "needed"
    assert troupe.stranger.client.get("/audit").json()["detail"] == (
        "Only the custodian can do that."
    )
    switch_on(keeper)
    assert keeper.client.get("/audit").status_code == 200
    assert keeper.client.get(f"/characters/{agnes}").status_code == 200
    assert leads_notices(session, troupe) == []


def test_it_lasts_an_hour_from_its_last_use(
    troupe: Troupe, keeper: Person, agnes: str, session: Session
) -> None:
    switch_on(keeper)
    access = access_of(session, keeper)
    # Used 50 minutes on: the hour starts again.
    session.execute(
        update(CustodianAccess)
        .where(CustodianAccess.id == access.id)
        .values(last_used_at=datetime.now(UTC) - timedelta(minutes=50))
    )
    assert keeper.client.get(f"/characters/{agnes}").status_code == 200
    session.refresh(access)
    assert datetime.now(UTC) - access.last_used_at < timedelta(minutes=1)
    # Its own character, or the menu's state, isn't a use of the powers.
    session.execute(
        update(CustodianAccess)
        .where(CustodianAccess.id == access.id)
        .values(last_used_at=datetime.now(UTC) - timedelta(minutes=50))
    )
    assert keeper.client.get("/custodian-access").json()["on"] is True
    session.refresh(access)
    assert datetime.now(UTC) - access.last_used_at > timedelta(minutes=49)
    # An hour after the last use, it is off.
    session.execute(
        update(CustodianAccess)
        .where(CustodianAccess.id == access.id)
        .values(last_used_at=datetime.now(UTC) - timedelta(minutes=61))
    )
    assert keeper.client.get(f"/characters/{agnes}").status_code == 404
    assert keeper.client.get("/custodian-access").json()["on"] is False
    session.refresh(access)
    assert access.ended_at is not None
    ended = actions(session, keeper, "account.custodian_access_off")
    assert [e.data["kind"] for e in ended] == ["timed_out"]


def test_switching_off_or_signing_out_ends_it_at_once(
    troupe: Troupe, keeper: Person, agnes: str, session: Session
) -> None:
    switch_on(keeper)
    stopped = keeper.client.post("/custodian-access/stop")
    assert stopped.status_code == 204
    assert keeper.client.get(f"/characters/{agnes}").status_code == 404

    switch_on(keeper)
    keeper.client.post("/auth/logout")
    signed_in = keeper.client.post(
        "/auth/login", json={"login": keeper.email, "password": PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text
    assert keeper.client.get("/custodian-access").json()["on"] is False
    assert keeper.client.get(f"/characters/{agnes}").status_code == 404
    ended = actions(session, keeper, "account.custodian_access_off")
    assert [e.data["kind"] for e in ended] == ["stopped", "signed_out"]


def test_switching_on_asks_for_their_second_step_and_a_reason(
    troupe: Troupe, keeper: Person, session: Session
) -> None:
    user = session.get_one(User, uuid.UUID(keeper.id))
    codes = two_step.new_recovery_codes(session, user)
    assert keeper.client.get("/custodian-access").json()["second_step"] == ["recovery_code"]

    def ask(**body: object) -> tuple[int, str]:
        response = keeper.client.post("/custodian-access", json={"reason": "A look", **body})
        return response.status_code, response.json()["detail"]

    assert ask(password=PASSWORD) == (422, "Give your second step.")
    assert ask(code="abcde-fghjk") == (
        401,
        "That recovery code isn't right, or has been used.",
    )
    assert ask(code="123456") == (401, "That code isn't right.")
    refused = keeper.client.post("/custodian-access", json={"reason": "  ", "code": codes[0]})
    assert refused.status_code == 422
    assert keeper.client.post(
        "/custodian-access", json={"reason": "A look", "code": codes[0]}
    ).json()["on"]
    # A recovery code works once.
    keeper.client.post("/custodian-access/stop")
    assert ask(code=codes[0])[0] == 401
    wrong = actions(session, keeper, "account.custodian_access_refused")
    assert [e.data["kind"] for e in wrong] == ["recovery_code", "app", "recovery_code"]


def test_without_a_second_step_it_asks_for_the_password(keeper: Person) -> None:
    wrong = keeper.client.post(
        "/custodian-access", json={"reason": "A look", "password": "not it at all"}
    )
    assert wrong.status_code == 403
    assert wrong.json()["detail"] == "That's not your password."
    assert keeper.client.get("/custodian-access").json()["on"] is False


def test_only_a_custodian_switches_it_on(troupe: Troupe) -> None:
    assert troupe.player.client.get("/custodian-access").json() is None
    refused = troupe.player.client.post(
        "/custodian-access", json={"reason": "A look", "password": PASSWORD}
    )
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Only the custodian can switch on custodian access."


def test_a_sign_in_elsewhere_has_it_off(
    troupe: Troupe, keeper: Person, agnes: str, client_for: Callable[[], TestClient]
) -> None:
    switch_on(keeper)
    elsewhere = client_for()
    signed_in = elsewhere.post("/auth/login", json={"login": keeper.email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    assert elsewhere.get(f"/characters/{agnes}").status_code == 404
    assert keeper.client.get(f"/characters/{agnes}").status_code == 200

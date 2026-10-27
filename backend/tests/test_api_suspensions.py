"""The custodian suspending an account, and lifting it (issue #273): signed out at
once, kept out by every way in, told why not and who to ask, and let back in when
it is lifted or ends."""

import re
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from horatio import notification_emails, preferences, suspensions
from horatio.config import get_settings
from horatio.connectors import email
from horatio.models import AuditEvent, EmailNotice, Suspension, User
from horatio.models import Session as SignInSession
from tests.api_helpers import PASSWORD, Person, Troupe, new_character
from tests.test_api_play import tap
from tests.test_api_sheets import make_home_troupe_member
from tests.test_email_connector import FakeSMTP


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSMTP]:
    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(settings, "custodian_contact", "custodian@example.org")
    monkeypatch.setattr(email, "smtp_factory", fake)
    yield fake


def suspend(troupe: Troupe, person: Person, **body: Any) -> Any:
    return troupe.custodian.client.post(
        f"/players/{person.id}/suspension", json={"reason": "Harassing other players", **body}
    )


def lift(troupe: Troupe, person: Person, reason: str = "Talked it through") -> Any:
    return troupe.custodian.client.post(
        f"/players/{person.id}/suspension/lift", json={"reason": reason}
    )


def sign_in(client: TestClient, login: str) -> Any:
    return client.post("/auth/login", json={"login": login, "password": PASSWORD})


def logged(session: Session) -> list[tuple[str, dict[str, Any]]]:
    return [
        (e.action, e.data)
        for e in session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action.startswith("account.suspen"))
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    ]


def test_a_suspended_player_is_signed_out_and_kept_out(
    troupe: Troupe, client_for: Callable[[], TestClient], session: Session
) -> None:
    player = troupe.player
    reset = troupe.custodian.client.post(f"/players/{player.id}/password-reset")
    token = reset.json()["url"].rsplit("/", 1)[1]
    assert player.client.get("/auth/me").status_code == 200

    response = suspend(troupe, player)

    assert response.status_code == 201, response.text
    # Their session stops working at once, and is gone.
    assert player.client.get("/auth/me").status_code == 401
    assert (
        session.scalar(select(SignInSession).where(SignInSession.user_id == uuid.UUID(player.id)))
        is None
    )
    # No way back in: their password, by email or handle, or a reset link.
    anyone = client_for()
    for login in (player.email, player.handle):
        refused = sign_in(anyone, login)
        assert refused.status_code == 403
        assert refused.json()["detail"] == (
            "Your account is suspended. To ask about it, contact the custodian."
        )
    assert anyone.get(f"/auth/reset/{token}").status_code == 403
    used = anyone.post("/auth/reset", json={"token": token, "password": "a new password!"})
    assert used.status_code == 403
    # A wrong password still says only that, so it gives nothing away.
    wrong = anyone.post("/auth/login", json={"login": player.email, "password": "wrong one!"})
    assert wrong.status_code == 401
    # Logged for the custodian, with the reason.
    assert logged(session) == [
        (
            "account.suspended",
            {"member": "player", "user_id": player.id, "reason": "Harassing other players"},
        )
    ]


def test_lifting_lets_them_back_in(
    troupe: Troupe, client_for: Callable[[], TestClient], session: Session
) -> None:
    player = troupe.player
    assert suspend(troupe, player).status_code == 201

    assert lift(troupe, player, " ").status_code == 422
    assert lift(troupe, player).status_code == 200

    assert sign_in(client_for(), player.email).status_code == 200
    suspension = session.scalars(select(Suspension)).one()
    assert suspension.lifted_by_id == uuid.UUID(troupe.custodian.id)
    assert suspension.lift_reason == "Talked it through"
    assert [action for action, _ in logged(session)] == [
        "account.suspended",
        "account.suspension_lifted",
    ]
    # Lifted already: nothing to lift.
    assert lift(troupe, player).status_code == 404
    # The suspension stays on record, and the player can be suspended again.
    assert suspend(troupe, player).status_code == 201
    assert len(session.scalars(select(Suspension)).all()) == 2


def test_it_ends_by_itself_on_its_end_date(
    troupe: Troupe, client_for: Callable[[], TestClient], session: Session, mail: FakeSMTP
) -> None:
    player = troupe.player
    ends_at = datetime(2030, 3, 1, 18, 0, tzinfo=UTC)
    assert suspend(troupe, player, ends_at=ends_at.isoformat()).status_code == 201

    refused = sign_in(client_for(), player.email)
    assert refused.json()["detail"] == (
        "Your account is suspended until 1 Mar 2030, 18:00 (UTC). To ask about it, "
        "contact the custodian: custodian@example.org."
    )
    # An end date already passed is no end date.
    assert suspend(troupe, troupe.narrator, ends_at="2020-01-01T00:00:00Z").status_code == 422

    # The date passes.
    session.execute(update(Suspension).values(ends_at=datetime.now(UTC) - timedelta(minutes=1)))
    assert suspensions.end_due(session) == 1

    assert sign_in(client_for(), player.email).status_code == 200
    action, data = logged(session)[-1]
    assert (action, data["kind"]) == ("account.suspension_lifted", "ended")
    assert [m["Subject"] for m in mail.sent] == [
        "Your Horatio account is suspended",
        "Your Horatio account is no longer suspended",
    ]
    log = troupe.custodian.client.get("/suspensions").json()
    assert log["suspended"] == []
    assert [e["message"] for e in log["log"]] == [
        "player's suspension ended.",
        "custodian suspended player until 1 Mar 2030, 18:00 (UTC) (Harassing other players).",
    ]


def test_signing_in_after_the_end_date_records_it_ended(
    troupe: Troupe, client_for: Callable[[], TestClient], session: Session
) -> None:
    player = troupe.player
    later = datetime.now(UTC) + timedelta(days=1)
    assert suspend(troupe, player, ends_at=later.isoformat()).status_code == 201
    session.execute(update(Suspension).values(ends_at=datetime.now(UTC) - timedelta(minutes=1)))

    assert sign_in(client_for(), player.email).status_code == 200
    assert session.scalars(select(Suspension)).one().lifted_at is not None
    assert logged(session)[-1][1]["kind"] == "ended"


def test_only_the_custodian_suspends_and_never_themselves(troupe: Troupe, session: Session) -> None:
    for person in (troupe.lead, troupe.player):
        response = person.client.post(
            f"/players/{troupe.narrator.id}/suspension", json={"reason": "No"}
        )
        assert response.status_code == 403
    assert suspend(troupe, troupe.custodian).status_code == 409
    assert suspend(troupe, troupe.player, reason="").status_code == 422
    assert troupe.player.client.get("/suspensions").status_code == 403

    # Nor the last custodian, whoever asks.
    custodian = session.get_one(User, uuid.UUID(troupe.custodian.id))
    lead = session.get_one(User, uuid.UUID(troupe.lead.id))
    with pytest.raises(Exception, match="last custodian"):
        suspensions.suspend(session, lead, custodian, "Gone rogue", None)


def test_the_person_is_emailed_but_never_told_the_reason(
    troupe: Troupe, session: Session, mail: FakeSMTP
) -> None:
    assert suspend(troupe, troupe.player).json() == {"email_error": None}
    assert lift(troupe, troupe.player).status_code == 200

    suspended, lifted = mail.sent
    assert suspended["To"] == f"player <{troupe.player.email}>"
    text = suspended.get_content()
    assert "suspended your account" in text
    assert "contact the custodian: custodian@example.org" in text
    assert "Harassing" not in text
    assert "You can sign in again" in lifted.get_content()
    assert "Talked it through" not in lifted.get_content()


def test_a_failed_email_is_logged_and_said(
    troupe: Troupe, session: Session, mail: FakeSMTP
) -> None:
    mail.fail = OSError("connection refused")

    response = suspend(troupe, troupe.player)

    assert response.status_code == 201
    assert response.json()["email_error"]
    assert [action for action, _ in logged(session)] == [
        "account.suspended",
        "account.suspension_email_failed",
    ]


def test_no_notification_emails_or_reset_links_while_suspended(
    troupe: Troupe, session: Session, mail: FakeSMTP
) -> None:
    player = session.get_one(User, uuid.UUID(troupe.player.id))
    preferences.change(player, {"email_approvals": True})
    session.flush()
    notification_emails.queue(session, [player.id], "approval.discipline", "Waiting", "/x")
    assert suspend(troupe, troupe.player).status_code == 201
    mail.sent.clear()

    # One kept before is dropped, and none is kept after.
    assert notification_emails.send_due(session) == 0
    notification_emails.queue(session, [player.id], "approval.discipline", "Waiting", "/x")
    assert session.scalars(select(EmailNotice)).all() == []
    # Asking for a reset link sends none, with the same answer as ever.
    response = troupe.player.client.post("/auth/forgot", json={"email": troupe.player.email})
    assert response.status_code == 202
    assert mail.sent == []


def test_staff_see_the_mark_and_the_character_takes_no_new_actions(
    troupe: Troupe, session: Session
) -> None:
    agnes = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, agnes)
    assert suspend(troupe, troupe.player).status_code == 201

    roster = troupe.storyteller.client.get(f"/troupes/{troupe.id}/characters").json()
    assert [(e["character_name"], e["player_suspended"]) for e in roster] == [("Agnes", True)]
    # Staff still see the sheet and its Play View, but nothing new is played.
    assert troupe.storyteller.client.get(f"/characters/{agnes}/play").status_code == 200
    taps = troupe.storyteller.client.post(f"/characters/{agnes}/play/taps", json={"taps": [tap()]})
    assert taps.status_code == 409
    assert "player is suspended" in taps.json()["detail"]

    assert lift(troupe, troupe.player).status_code == 200
    roster = troupe.storyteller.client.get(f"/troupes/{troupe.id}/characters").json()
    assert roster[0]["player_suspended"] is False
    again = troupe.storyteller.client.post(f"/characters/{agnes}/play/taps", json={"taps": [tap()]})
    assert again.status_code == 200, again.text


def test_the_custodian_sees_who_is_suspended_and_what_they_lead(
    troupe: Troupe, session: Session
) -> None:
    ends_at = datetime(2030, 3, 1, 18, 0, tzinfo=UTC)
    assert suspend(troupe, troupe.lead, ends_at=ends_at.isoformat()).status_code == 201

    listed = troupe.custodian.client.get("/suspensions").json()["suspended"]
    assert [(s["display_name"], s["reason"], s["suspended_by"]) for s in listed] == [
        ("lead", "Harassing other players", "custodian")
    ]
    assert listed[0]["ends_at"].startswith("2030-03-01T18:00")
    assert listed[0]["leads"] == [{"id": troupe.id, "name": "Lords of the Night"}]
    # The People list marks them too.
    people = troupe.custodian.client.get("/players", params={"q": "lead"}).json()
    assert [(p["display_name"], p["suspended"]) for p in people] == [("lead", True)]
    # Their staff role is kept, so a new lead is appointed by hand.
    assert troupe.custodian.client.get(f"/troupes/{troupe.id}").json()["lead_user_id"] == (
        troupe.lead.id
    )


def test_suspending_twice_is_refused(troupe: Troupe) -> None:
    assert suspend(troupe, troupe.player).status_code == 201
    again = suspend(troupe, troupe.player)
    assert again.status_code == 409
    assert re.search("suspended already", again.json()["detail"])

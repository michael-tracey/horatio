"""Confirming it's you with Discord, for an account with no password (#1140), against
a fake Discord: it must be the Discord account linked, the state works once from the
sign-in that started it, the confirmation stands in for the password once and only for
a few minutes, never for an account with a password, and each try counts towards the
limit on password tries at the account."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient
from pyotp.totp import TOTP
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from horatio.api import discord_confirm
from horatio.api import two_step as two_step_api
from horatio.auth import attempts, two_step
from horatio.config import get_settings
from horatio.connectors import discord
from horatio.models import Session as SignInSession
from horatio.models import User
from tests.api_helpers import Person, sign_up
from tests.test_api_discord_sign_in import (
    DISCORD_ID,
    START,
    FakeDiscord,
    come_back,
    events,
    record_debug,
    said,
    sign_in,
)

PAGE = "/account/sign-in?then=codes"


@pytest.fixture
def fake_discord(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeDiscord]:
    fake = FakeDiscord()
    settings = get_settings()
    monkeypatch.setattr(settings, "discord_client_id", "app-id")
    monkeypatch.setattr(settings, "discord_client_secret", "app-secret")
    monkeypatch.setattr(settings, "discord_bot_token", "test-token")
    monkeypatch.setattr(discord, "transport", httpx.MockTransport(fake.handle))
    yield fake


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    at = [START]
    monkeypatch.setattr(two_step, "now", lambda: at[0])
    return at


@pytest.fixture
def custodian(client_for: Callable[[], TestClient], session: Session) -> Person:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    record_debug(mina)
    return mina


def owl(client_for: Callable[[], TestClient]) -> TestClient:
    """Someone signed up with Discord: no password, and Discord linked."""
    visitor = client_for()
    sign_in(visitor)
    made = visitor.post("/auth/discord/sign-up", json={"display_name": "Owl"})
    assert made.status_code == 201, made.text
    return visitor


def with_app(client: TestClient, clock: list[float]) -> None:
    """Set up an authenticator app, which asks for no password, so there is something
    to turn off and recovery codes to make again."""
    secret = client.post("/two-step/app").json()["secret"]
    confirmed = client.post("/two-step/app/confirm", json={"code": TOTP(secret).at(int(clock[0]))})
    assert confirmed.status_code == 200, confirmed.text


def start(client: TestClient, next: str | None = PAGE) -> str:
    """Begin confirming with Discord; Discord's page's state."""
    started = client.post("/auth/discord/confirm", json={"next": next})
    assert started.status_code == 200, started.text
    query = parse_qs(urlparse(started.json()["url"]).query)
    assert query["scope"] == ["identify"]
    assert query["redirect_uri"] == ["http://localhost:5173/api/discord/callback"]
    state = query["state"][0]
    assert state.startswith("confirm.")
    return state


def confirm(client: TestClient, code: str = "good-code") -> httpx2.Response:
    return come_back(client, start(client), code=code)


def back(outcome: str, page: str = PAGE) -> str:
    joiner = "&" if "?" in page else "?"
    return f"{page}{joiner}discord_confirm={outcome}"


def the_session(session: Session, handle: str) -> SignInSession:
    user = session.scalars(select(User).where(User.handle == handle)).one()
    return session.scalars(select(SignInSession).where(SignInSession.user_id == user.id)).one()


def new_codes(client: TestClient) -> httpx2.Response:
    return client.post("/two-step/recovery-codes", json={"password": ""})


def test_confirming_with_discord_stands_in_for_the_password_once(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    clock: list[float],
    custodian: Person,
) -> None:
    visitor = owl(client_for)
    with_app(visitor, clock)
    before = visitor.get("/two-step").json()
    assert before["can_confirm_with_discord"] is True
    assert before["confirmed_until"] is None
    assert new_codes(visitor).json()["detail"] == two_step_api.CONFIRM_FIRST

    answer = confirm(visitor)

    assert answer.status_code == 303
    assert answer.headers["location"] == back("confirmed")
    until = visitor.get("/two-step").json()["confirmed_until"]
    assert until is not None
    left = datetime.fromisoformat(until) - datetime.now(UTC)
    assert timedelta(minutes=4) < left <= discord_confirm.CONFIRMED_FOR
    [event] = events(session, "account.discord_confirmed")
    assert said(event, "Owl") == "Owl confirmed it's them with Discord, as they have no password."

    # Refused for another reason first, it isn't used up.
    removing = visitor.post(f"/two-step/passkeys/{uuid.uuid4()}/remove", json={"password": ""})
    assert removing.status_code == 404
    made = new_codes(visitor)
    assert made.status_code == 200, made.text
    assert len(made.json()["recovery_codes"]) == 10

    # Used once: the next change asks again.
    assert visitor.get("/two-step").json()["confirmed_until"] is None
    again = visitor.post("/two-step/app/remove", json={"password": ""})
    assert again.status_code == 409
    assert again.json()["detail"] == two_step_api.CONFIRM_FIRST
    assert confirm(visitor).headers["location"] == back("confirmed")
    assert visitor.post("/two-step/app/remove", json={"password": ""}).status_code == 204


def test_a_passkey_s_options_dont_use_the_confirmation_up(
    fake_discord: FakeDiscord, client_for: Callable[[], TestClient]
) -> None:
    visitor = owl(client_for)
    assert visitor.post("/two-step/passkeys/options", json={"password": ""}).status_code == 409
    confirm(visitor)

    # Asked twice, as when the browser's prompt is cancelled and tried again: the
    # confirmation is used once the passkey is kept.
    for _ in range(2):
        options = visitor.post("/two-step/passkeys/options", json={"password": ""})
        assert options.status_code == 200, options.text
    assert visitor.get("/two-step").json()["confirmed_until"] is not None


def test_another_discord_account_confirms_nothing(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    clock: list[float],
    custodian: Person,
) -> None:
    visitor = owl(client_for)
    with_app(visitor, clock)
    fake_discord.account = {**fake_discord.account, "id": "999999", "username": "someone"}

    answer = confirm(visitor)

    assert answer.headers["location"] == back("other_account")
    assert visitor.get("/two-step").json()["confirmed_until"] is None
    assert new_codes(visitor).status_code == 409
    [event] = events(session, "account.discord_confirm_failed")
    assert event.data["kind"] == "other_account"
    assert said(event, "Owl") == (
        "Owl failed to confirm it's them with Discord: it was a Discord account not linked to"
        " theirs."
    )
    # Discord not saying who they are is refused too.
    assert confirm(visitor, code="bad-code").headers["location"] == back("failed")
    failed = events(session, "account.discord_confirm_failed")[-1]
    assert said(failed, "Owl") == (
        "Owl failed to confirm it's them with Discord: Discord didn't say who they are."
    )


def test_the_state_works_once_and_only_from_the_sign_in_that_started_it(
    fake_discord: FakeDiscord, client_for: Callable[[], TestClient], session: Session
) -> None:
    visitor = owl(client_for)
    state = start(visitor)
    token = state.removeprefix("confirm.")

    # The same account signed in somewhere else, with the cookie put back: refused.
    elsewhere = client_for()
    assert sign_in(elsewhere).headers["location"] == "/characters"
    elsewhere.cookies.set(
        discord_confirm.COOKIE, token, domain="testserver.local", path="/api/discord"
    )
    assert come_back(elsewhere, state, code="good-code").headers["location"] == back(
        "expired", "/account/sign-in"
    )
    exchanged = fake_discord.exchanged
    assert come_back(visitor, state, code="good-code").headers["location"] == back("confirmed")
    assert fake_discord.exchanged == exchanged + 1

    # Played again: used up, and Discord isn't asked.
    visitor.cookies.set(
        discord_confirm.COOKIE, token, domain="testserver.local", path="/api/discord"
    )
    assert come_back(visitor, state, code="good-code").headers["location"] == back(
        "expired", "/account/sign-in"
    )
    assert fake_discord.exchanged == exchanged + 1
    # Cancelling on Discord confirms nothing.
    session.execute(update(SignInSession).values(confirmed_until=None))
    cancelled = come_back(visitor, start(visitor), error="access_denied")
    assert cancelled.headers["location"] == back("cancelled")
    assert visitor.get("/two-step").json()["confirmed_until"] is None


def test_a_confirmation_from_more_than_a_few_minutes_ago_stands_in_for_nothing(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    clock: list[float],
) -> None:
    visitor = owl(client_for)
    with_app(visitor, clock)
    confirm(visitor)
    signed_in = the_session(session, "owl")
    assert signed_in.confirmed_until is not None
    signed_in.confirmed_until = datetime.now(UTC) - timedelta(seconds=1)
    session.flush()

    assert visitor.get("/two-step").json()["confirmed_until"] is None
    refused = new_codes(visitor)
    assert refused.status_code == 409
    assert refused.json()["detail"] == two_step_api.CONFIRM_FIRST


def test_an_account_with_a_password_gives_it_instead(
    fake_discord: FakeDiscord, client_for: Callable[[], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    session.get_one(User, uuid.UUID(agnes.id)).discord_user_id = DISCORD_ID
    session.flush()

    refused = agnes.client.post("/auth/discord/confirm", json={})
    assert refused.status_code == 409
    assert agnes.client.get("/two-step").json()["can_confirm_with_discord"] is False

    # Even confirmed somehow, the password is still asked.
    the_session(session, "agnes").confirmed_until = datetime.now(UTC) + timedelta(minutes=5)
    session.flush()
    wrong = agnes.client.post("/two-step/recovery-codes", json={"password": ""})
    assert wrong.status_code == 403


def test_without_discord_linked_they_are_told_to_set_a_password(
    fake_discord: FakeDiscord, client_for: Callable[[], TestClient], session: Session
) -> None:
    visitor = owl(client_for)
    session.scalars(select(User).where(User.handle == "owl")).one().discord_user_id = None
    session.flush()

    assert visitor.get("/two-step").json()["can_confirm_with_discord"] is False
    assert visitor.post("/auth/discord/confirm", json={}).status_code == 409
    refused = new_codes(visitor)
    assert refused.status_code == 409
    assert refused.json()["detail"] == two_step_api.NO_PASSWORD


def test_confirming_works_while_two_step_must_be_set_up_first(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visitor = owl(client_for)
    monkeypatch.setattr(get_settings(), "two_step_for_custodians", True)
    session.scalars(select(User).where(User.handle == "owl")).one().is_custodian = True
    session.flush()
    assert visitor.get("/two-step").json()["needed"] is True

    assert confirm(visitor).headers["location"] == back("confirmed")
    options = visitor.post("/two-step/passkeys/options", json={"password": ""})
    assert options.status_code == 200, options.text
    # The callback's other uses are still closed until a second step is set up.
    linking = come_back(visitor, "link.someone.token", code="good-code")
    assert linking.status_code == 403


def test_each_try_counts_towards_the_limit_on_password_tries(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    custodian: Person,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visitor = owl(client_for)
    monkeypatch.setattr(get_settings(), "auth_limits", True)
    tries = attempts.PASSWORD_CHANGE_LIMITS[0][1]
    for _ in range(tries - 1):
        assert confirm(visitor, code="bad-code").headers["location"] == back("failed")
    # Right ones count too.
    assert confirm(visitor).headers["location"] == back("confirmed")
    exchanged = fake_discord.exchanged

    held = confirm(visitor)

    assert held.headers["location"] == back("throttled")
    assert fake_discord.exchanged == exchanged
    [event] = events(session, "account.password_change_throttled")
    assert (event.data["kind"], event.data["limit"]) == ("discord_confirm", "password_changes")
    assert said(event, "Owl") == (
        "Owl was turned away from confirming it's them with Discord: too many tries at the account."
    )

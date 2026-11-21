"""Signing in, and up, with Discord (#1128), against a fake Discord: the state kept on
the server and working once, a linked account signing in, a new one made with
Discord's verified email, never linking by email, and the refusals, second step and
limits a password sign-in has."""

import uuid
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient
from pyotp.totp import TOTP
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import discord_links
from horatio.api import discord_sign_in
from horatio.api import two_step as two_step_api
from horatio.api.roster import message
from horatio.app import app
from horatio.auth import attempts, two_step
from horatio.config import get_settings
from horatio.connectors import discord
from horatio.models import AuditEvent, AuthAttempt, AuthIdentity, DiscordSignIn, User
from tests.api_helpers import Person, sign_up

DISCORD_ID = "515151"
START = 1_800_000_000.0


class FakeDiscord:
    """Discord's token exchange and `/users/@me` for an `identify email` grant."""

    def __init__(self) -> None:
        self.account: dict[str, Any] = {
            "id": DISCORD_ID,
            "username": "night.owl",
            "global_name": "Night Owl",
            "email": "owl@example.org",
            "verified": True,
        }
        self.exchanged = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/oauth2/token":
            self.exchanged += 1
            form = parse_qs(request.content.decode())
            if form.get("code") != ["good-code"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200, json={"access_token": "user-token", "scope": "identify email"}
            )
        if request.url.path == "/api/v10/users/@me":
            assert request.headers["Authorization"] == "Bearer user-token"
            return httpx.Response(200, json=self.account)
        return httpx.Response(404, json={"message": "Unknown"})


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
def limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "auth_limits", True)


@pytest.fixture
def at(client_for: Callable[[], TestClient]) -> Iterator[Callable[[str], TestClient]]:
    """A client whose requests come from an address of the test's choosing."""
    client_for()  # shares the test's database session
    clients: list[TestClient] = []

    def make(ip: str) -> TestClient:
        client = TestClient(
            app, base_url="http://testserver/api", headers={"X-Horatio": "1"}, client=(ip, 50000)
        )
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


def start(client: TestClient, next: str | None = None) -> str:
    """Begin signing in with Discord; Discord's page's state."""
    started = client.post("/auth/discord/start", json={"next": next})
    assert started.status_code == 200, started.text
    query = parse_qs(urlparse(started.json()["url"]).query)
    assert query["scope"] == ["identify email"]
    assert query["redirect_uri"] == ["http://localhost:5173/api/discord/callback"]
    assert "permissions" not in query
    state = query["state"][0]
    assert state.startswith("signin.")
    return state


def come_back(client: TestClient, state: str, **params: str) -> httpx2.Response:
    return client.get(
        "/discord/callback", params={"state": state, **params}, follow_redirects=False
    )


def sign_in(client: TestClient, next: str | None = None) -> httpx2.Response:
    return come_back(client, start(client, next), code="good-code")


def user(session: Session, person: Person) -> User:
    return session.get_one(User, uuid.UUID(person.id))


def linked(session: Session, person: Person) -> User:
    """Link the person to the fake Discord account, as linking did before #1128: with
    no identity row."""
    account = user(session, person)
    account.discord_user_id = DISCORD_ID
    session.flush()
    return account


def identities(session: Session) -> list[tuple[uuid.UUID, str]]:
    rows = session.execute(
        select(AuthIdentity.user_id, AuthIdentity.subject).where(AuthIdentity.provider == "discord")
    )
    return [(user_id, subject) for user_id, subject in rows]


def events(session: Session, action: str) -> list[AuditEvent]:
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def said(event: AuditEvent, actor: str | None = None) -> str:
    return message(event.action, actor, None, event.data)


def record_debug(custodian: Person) -> None:
    """Have the audit log keep debug events, such as signing in, as the custodian can."""
    body = {"record": "debug", "keep_debug": 30, "keep_info": 365, "sign_in_ips": False}
    assert custodian.client.put("/audit/settings", json=body).status_code == 200


@pytest.fixture
def custodian(client_for: Callable[[], TestClient], session: Session) -> Person:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    record_debug(mina)
    return mina


def test_the_pages_offer_discord_only_once_it_is_set_up(
    client_for: Callable[[], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    visitor = client_for()
    assert visitor.get("/auth/discord").json() == {"available": False}
    refused = visitor.post("/auth/discord/start", json={})
    assert refused.status_code == 409

    monkeypatch.setattr(discord, "configured", lambda: True)
    assert visitor.get("/auth/discord").json() == {"available": True}


def test_a_linked_account_signs_in_and_gets_its_identity_row(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    custodian: Person,
) -> None:
    agnes = sign_up(client_for, "agnes")
    account = linked(session, agnes)
    visitor = client_for()

    answer = sign_in(visitor, next="/troupes")

    assert answer.status_code == 303
    assert answer.headers["location"] == "/troupes"
    assert visitor.get("/auth/me").json()["handle"] == "agnes"
    # Linked before Discord could sign in: the identity row is made now.
    assert identities(session) == [(account.id, DISCORD_ID)]
    assert session.scalars(select(DiscordSignIn)).all() == []
    [event] = [e for e in events(session, "account.signed_in") if e.data.get("kind")]
    assert event.data["kind"] == "discord"
    assert said(event, "agnes") == "agnes signed in with Discord."
    # Signing in again finds it the same way, and makes no second row.
    assert sign_in(client_for()).headers["location"] == "/characters"
    assert identities(session) == [(account.id, DISCORD_ID)]


def test_a_new_discord_account_signs_up_with_its_verified_email(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    custodian: Person,
) -> None:
    visitor = client_for()

    answer = sign_in(visitor, next="/troupes")

    assert answer.status_code == 303
    assert answer.headers["location"] == "/sign-up/discord?next=%2Ftroupes"
    # Not signed in yet: they choose their name and handle first, as sign-up asks.
    assert visitor.get("/auth/me").status_code == 401
    form = visitor.get("/auth/discord/sign-up")
    assert form.status_code == 200, form.text
    assert form.json() == {
        "email": "owl@example.org",
        "discord_username": "night.owl",
        "display_name": "Night Owl",
        "handle": "night_owl",
    }
    # Another browser has nothing waiting.
    assert client_for().get("/auth/discord/sign-up").status_code == 410

    made = visitor.post("/auth/discord/sign-up", json={"display_name": "Owl", "handle": "owl"})

    assert made.status_code == 201, made.text
    me = visitor.get("/auth/me").json()
    assert (me["email"], me["display_name"], me["handle"]) == ("owl@example.org", "Owl", "owl")
    account = session.get_one(User, uuid.UUID(me["id"]))
    assert account.password_hash is None
    assert (account.discord_user_id, account.discord_handle) == (DISCORD_ID, "night.owl")
    assert identities(session) == [(account.id, DISCORD_ID)]
    assert session.scalars(select(DiscordSignIn)).all() == []
    # Discord is their only way to sign in, so it can't be unlinked.
    assert visitor.get("/account/discord").json()["can_unlink"] is False
    assert visitor.delete("/account/discord").status_code == 409
    [signed_up] = [e for e in events(session, "account.signed_up") if e.data.get("kind")]
    assert said(signed_up, "Owl") == "Owl signed up with Discord."
    assert len(events(session, "account.discord_linked")) == 1
    # It works once.
    again = visitor.post("/auth/discord/sign-up", json={"display_name": "Owl 2"})
    assert again.status_code == 410
    # And from now on Discord signs them in.
    elsewhere = client_for()
    assert sign_in(elsewhere).headers["location"] == "/characters"
    assert elsewhere.get("/auth/me").json()["handle"] == "owl"


def test_a_taken_handle_is_refused_and_the_sign_up_still_waits(
    fake_discord: FakeDiscord, client_for: Callable[[], TestClient]
) -> None:
    sign_up(client_for, "owl")
    visitor = client_for()
    sign_in(visitor)

    taken = visitor.post("/auth/discord/sign-up", json={"display_name": "Owl", "handle": "owl"})
    assert taken.status_code == 409
    made = visitor.post("/auth/discord/sign-up", json={"display_name": "Owl", "handle": "owl2"})
    assert made.status_code == 201, made.text


def test_no_account_is_made_without_an_email_discord_has_verified(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    custodian: Person,
) -> None:
    fake_discord.account["verified"] = False
    visitor = client_for()

    answer = sign_in(visitor, next="/troupes")

    assert answer.headers["location"] == "/sign-in?discord=no_email&next=%2Ftroupes"
    assert visitor.get("/auth/me").status_code == 401
    assert session.scalars(select(DiscordSignIn)).all() == []
    assert session.scalars(select(User).where(User.email == "owl@example.org")).all() == []
    [event] = [e for e in events(session, "account.sign_in_failed") if e.data.get("kind")]
    assert said(event) == (
        "Someone failed to sign in with Discord: Discord has no verified email for them, so no"
        " account was made."
    )

    del fake_discord.account["email"]
    fake_discord.account["verified"] = True
    assert sign_in(visitor).headers["location"] == "/sign-in?discord=no_email"


def test_an_account_with_the_same_email_is_never_linked_by_it(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    custodian: Person,
) -> None:
    agnes = sign_up(client_for, "agnes")
    fake_discord.account["email"] = "Agnes@Example.com"
    visitor = client_for()

    answer = sign_in(visitor)

    assert answer.headers["location"] == "/sign-in?discord=email_taken"
    assert visitor.get("/auth/me").status_code == 401
    assert user(session, agnes).discord_user_id is None
    assert identities(session) == []
    assert session.scalars(select(DiscordSignIn)).all() == []
    [event] = [e for e in events(session, "account.sign_in_failed") if e.data.get("kind")]
    assert event.data["user_id"] == agnes.id
    assert said(event) == (
        "Someone failed to sign in as agnes with a Discord account not linked to theirs, though"
        " it has their email. Nothing was linked."
    )


def test_a_suspended_account_is_refused(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    custodian: Person,
) -> None:
    agnes = sign_up(client_for, "agnes")
    linked(session, agnes)
    custodian.client.post(f"/players/{agnes.id}/suspension", json={"reason": "Harassment"})
    visitor = client_for()

    answer = sign_in(visitor)

    assert answer.headers["location"] == "/sign-in?discord=suspended"
    assert visitor.get("/auth/me").status_code == 401
    [event] = [e for e in events(session, "account.sign_in_failed") if e.data.get("kind")]
    assert event.data["kind"] == "discord_suspended"


def test_a_merged_account_is_refused(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
) -> None:
    agnes = sign_up(client_for, "agnes")
    kept = sign_up(client_for, "agnes2")
    account = linked(session, agnes)
    account.merged_into_id = uuid.UUID(kept.id)
    session.flush()
    visitor = client_for()

    assert sign_in(visitor).headers["location"] == "/sign-in?discord=merged"
    assert visitor.get("/auth/me").status_code == 401


def test_where_two_step_is_required_discord_is_the_first_step_only(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    clock: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "two_step_for_custodians", True)
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    started = mina.client.post("/two-step/app")
    secret = started.json()["secret"]
    confirmed = mina.client.post(
        "/two-step/app/confirm", json={"code": TOTP(secret).at(int(clock[0]))}
    )
    assert confirmed.status_code == 200, confirmed.text
    record_debug(mina)
    clock[0] += 30
    linked(session, mina)
    visitor = client_for()

    answer = sign_in(visitor, next="/troupes")

    assert answer.headers["location"] == "/sign-in/second-step?next=%2Ftroupes"
    # No session until the second step is given.
    assert visitor.get("/auth/me").status_code == 401
    waiting = visitor.get("/auth/second-step")
    assert waiting.status_code == 200, waiting.text
    assert "app" in waiting.json()["second_step"]
    [asked] = [e for e in events(session, "account.second_step_asked") if e.data.get("kind")]
    assert (
        said(asked, "mina") == "mina signed in with Discord, and was asked for their second step."
    )

    given = visitor.post("/auth/second-step", json={"code": TOTP(secret).at(int(clock[0]))})

    assert given.status_code == 200, given.text
    assert visitor.get("/auth/me").json()["handle"] == "mina"


def test_the_state_works_once_and_only_in_the_browser_that_started_it(
    fake_discord: FakeDiscord, client_for: Callable[[], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    linked(session, agnes)
    visitor = client_for()
    state = start(visitor)
    token = state.removeprefix("signin.")

    # Someone else's browser, sent the link, has no cookie for it: refused, and the
    # state still waits for its own browser.
    other = client_for()
    assert come_back(other, state, code="good-code").headers["location"] == (
        "/sign-in?discord=expired"
    )
    assert other.get("/auth/me").status_code == 401
    assert come_back(visitor, state, code="good-code").headers["location"] == "/characters"

    # Played again, with the cookie put back: the state is used up.
    replay = client_for()
    replay.cookies.set(
        discord_sign_in.COOKIE, token, domain="testserver.local", path="/api/discord"
    )
    exchanged = fake_discord.exchanged
    assert come_back(replay, state, code="good-code").headers["location"] == (
        "/sign-in?discord=expired"
    )
    assert replay.get("/auth/me").status_code == 401
    # Discord isn't asked.
    assert fake_discord.exchanged == exchanged
    # A cookie put back that way is sent: a state not yet used works with it.
    fresh = start(client_for())
    replay.cookies.set(
        discord_sign_in.COOKIE,
        fresh.removeprefix("signin."),
        domain="testserver.local",
        path="/api/discord",
    )
    assert come_back(replay, fresh, code="good-code").headers["location"] == "/characters"


def test_cancelling_on_discord_signs_no_one_in(
    fake_discord: FakeDiscord, client_for: Callable[[], TestClient]
) -> None:
    visitor = client_for()

    answer = come_back(visitor, start(visitor), error="access_denied")

    assert answer.headers["location"] == "/sign-in?discord=cancelled"
    assert visitor.get("/auth/me").status_code == 401


def test_discord_tries_count_as_sign_in_tries_from_where_they_come(
    fake_discord: FakeDiscord,
    at: Callable[[str], TestClient],
    session: Session,
    limits: None,
) -> None:
    there = at("203.0.113.9")
    # Five tries Discord doesn't confirm, from one place, at the login "Discord".
    for _ in range(attempts.ACCOUNT_LIMITS[0][1]):
        failed = come_back(there, start(there), code="bad-code")
        assert failed.headers["location"] == "/sign-in?discord=failed"
    exchanged = fake_discord.exchanged

    held = come_back(there, start(there), code="good-code")

    assert held.headers["location"] == "/sign-in?discord=throttled"
    assert fake_discord.exchanged == exchanged
    [event] = events(session, "account.sign_in_throttled")
    assert (event.data["kind"], event.data["limit"]) == ("discord", "failed_at_login")
    assert said(event) == (
        "Someone was turned away from signing in with Discord from 203.0.113.9: too many failed"
        " sign-ins from where they were."
    )
    # Somewhere else isn't held back.
    elsewhere = at("198.51.100.4")
    assert sign_in(elsewhere).headers["location"] == "/sign-up/discord"


def test_a_discord_sign_up_counts_as_a_sign_up(
    fake_discord: FakeDiscord,
    at: Callable[[str], TestClient],
    session: Session,
    limits: None,
) -> None:
    there = at("203.0.113.9")
    assert sign_in(there).headers["location"] == "/sign-up/discord"
    for _ in range(attempts.SIGN_UP_LIMITS[0][1]):
        session.add(AuthAttempt(action=attempts.SIGN_UP, ip_address="203.0.113.9"))
    session.flush()

    held = there.post("/auth/discord/sign-up", json={"display_name": "Owl"})

    assert held.status_code == 429
    assert held.json()["detail"] == attempts.SIGN_UP_WAIT
    [event] = events(session, "account.sign_up_throttled")
    assert said(event) == (
        "Someone was turned away from signing up with Discord from 203.0.113.9: too many"
        " sign-ups from where they were."
    )
    assert session.scalars(select(User).where(User.email == "owl@example.org")).all() == []


def test_linking_and_unlinking_keep_the_identity_row_in_step(
    fake_discord: FakeDiscord, client_for: Callable[[], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    started = agnes.client.post("/account/discord/link")
    state = parse_qs(urlparse(started.json()["url"]).query)["state"][0]

    linking = come_back(agnes.client, state, code="good-code")

    assert linking.headers["location"] == "/account/sign-in?discord=linked"
    assert identities(session) == [(uuid.UUID(agnes.id), DISCORD_ID)]
    assert agnes.client.delete("/account/discord").status_code == 200
    assert identities(session) == []


def test_linking_still_needs_someone_signed_in(
    fake_discord: FakeDiscord, client_for: Callable[[], TestClient]
) -> None:
    answer = come_back(client_for(), "link.someone.token", code="good-code")
    assert answer.status_code == 401


def test_merging_accounts_keeps_the_identity_rows_with_the_discord_link(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    custodian: Person,
) -> None:
    keep = sign_up(client_for, "agnes")
    other = sign_up(client_for, "agnes_twin")
    user(session, keep).discord_user_id = "111"
    user(session, other).discord_user_id = DISCORD_ID
    session.flush()
    for person in (keep, other):
        discord_links.keep_identity(session, user(session, person))

    found = custodian.client.get(
        "/accounts/merge", params={"keep": keep.handle, "merge": other.handle}
    ).json()
    assert "Discord" not in found["sign_in"]
    merged = custodian.client.post(
        "/accounts/merge", json={"keep": keep.handle, "merge": other.handle, "reason": "Twice"}
    )
    assert merged.status_code == 204, merged.text

    # The staying account keeps its own Discord, and the merged one's stays with it.
    assert sorted(identities(session)) == sorted(
        [(uuid.UUID(keep.id), "111"), (uuid.UUID(other.id), DISCORD_ID)]
    )
    assert sign_in(client_for()).headers["location"] == "/sign-in?discord=merged"


def test_merging_moves_the_discord_link_and_its_row_where_the_staying_one_has_none(
    fake_discord: FakeDiscord,
    client_for: Callable[[], TestClient],
    session: Session,
    custodian: Person,
) -> None:
    keep = sign_up(client_for, "agnes")
    other = sign_up(client_for, "agnes_twin")
    user(session, other).discord_user_id = DISCORD_ID
    session.flush()
    discord_links.keep_identity(session, user(session, other))

    merged = custodian.client.post(
        "/accounts/merge", json={"keep": keep.handle, "merge": other.handle, "reason": "Twice"}
    )
    assert merged.status_code == 204, merged.text

    assert identities(session) == [(uuid.UUID(keep.id), DISCORD_ID)]
    visitor = client_for()
    assert sign_in(visitor).headers["location"] == "/characters"
    assert visitor.get("/auth/me").json()["handle"] == "agnes"


def test_an_account_made_with_discord_is_told_it_needs_a_password_and_can_still_set_up_an_app(
    fake_discord: FakeDiscord, client_for: Callable[[], TestClient]
) -> None:
    visitor = client_for()
    sign_in(visitor)
    made = visitor.post("/auth/discord/sign-up", json={"display_name": "Owl"})
    assert made.status_code == 201, made.text

    assert visitor.get("/two-step").json()["has_password"] is False
    for path in ("/two-step/passkeys/options", "/two-step/recovery-codes", "/two-step/app/remove"):
        refused = visitor.post(path, json={"password": "anything at all"})
        assert refused.status_code == 409, path
        assert refused.json()["detail"] == two_step_api.NO_PASSWORD
    # Setting up an authenticator app asks for no password.
    assert visitor.post("/two-step/app").status_code == 200

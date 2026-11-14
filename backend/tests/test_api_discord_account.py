"""A player linking their own Discord account (#857), against a fake Discord: the
`identify` link, the callback that confirms who they are, the account refused when
another Horatio account has it, and unlinking."""

from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.api import discord_account
from horatio.config import get_settings
from horatio.connectors import discord
from horatio.models import AuditEvent, AuthIdentity, User
from tests.api_helpers import PASSWORD, Person, sign_up

DISCORD_ID = "424242"


class FakeDiscord:
    """Discord's token exchange and `/users/@me` for an `identify` grant."""

    def __init__(self) -> None:
        self.account: dict[str, Any] = {"id": DISCORD_ID, "username": "Night_Owl"}

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/oauth2/token":
            form = parse_qs(request.content.decode())
            if form.get("code") != ["good-code"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "user-token", "scope": "identify"})
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
def player(client_for: Callable[[], TestClient]) -> Person:
    return sign_up(client_for, "linker")


def start(person: Person) -> str:
    """Begin linking; Discord's page's state."""
    started = person.client.post("/account/discord/link")
    assert started.status_code == 200, started.text
    query = parse_qs(urlparse(started.json()["url"]).query)
    assert query["scope"] == ["identify"]
    assert query["redirect_uri"] == ["http://localhost:5173/api/discord/callback"]
    assert "permissions" not in query
    return query["state"][0]


def come_back(person: Person, state: str, **params: str) -> httpx2.Response:
    return person.client.get(
        "/discord/callback", params={"state": state, **params}, follow_redirects=False
    )


def user(session: Session, person: Person) -> User:
    return session.scalars(select(User).where(User.email == person.email)).one()


def actions(session: Session, person: Person) -> list[str]:
    return list(
        session.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.actor_id == user(session, person).id)
            .where(AuditEvent.action.startswith("account.discord"))
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def test_linking_records_the_discord_account_and_its_username(
    fake_discord: FakeDiscord, player: Person, session: Session
) -> None:
    before = player.client.get("/account/discord").json()
    assert before == {"available": True, "linked": False, "handle": None, "can_unlink": False}

    answer = come_back(player, start(player), code="good-code")

    assert answer.status_code == 303
    assert answer.headers["location"] == "/account?discord=linked"
    assert user(session, player).discord_user_id == DISCORD_ID
    assert player.client.get("/account/discord").json() == {
        "available": True,
        "linked": True,
        "handle": "night_owl",
        "can_unlink": True,
    }
    shown = player.client.get(f"/players/{player.id}").json()
    assert shown["discord_handle"] == "night_owl"
    assert shown["discord_linked"] is True
    assert actions(session, player) == ["account.discord_linked"]


def test_a_linked_username_is_not_overwritten_by_the_profile_form(
    fake_discord: FakeDiscord, player: Person
) -> None:
    come_back(player, start(player), code="good-code")

    saved = player.client.put(
        "/profile", json={"display_name": "linker", "discord_handle": "someone_else"}
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["discord_handle"] == "night_owl"


def test_a_typed_username_is_not_linked(player: Person) -> None:
    player.client.put("/profile", json={"display_name": "linker", "discord_handle": "typed_name"})

    shown = player.client.get(f"/players/{player.id}").json()

    assert shown["discord_handle"] == "typed_name"
    assert shown["discord_linked"] is False


def test_linking_needs_discord_set_up_on_the_server(player: Person) -> None:
    assert player.client.get("/account/discord").json()["available"] is False
    refused = player.client.post("/account/discord/link")
    assert refused.status_code == 409


def test_cancelling_on_discord_links_nothing(
    fake_discord: FakeDiscord, player: Person, session: Session
) -> None:
    answer = come_back(player, start(player), error="access_denied")

    assert answer.headers["location"] == "/account?discord=cancelled"
    assert user(session, player).discord_user_id is None


def test_a_bad_code_links_nothing_and_says_why(
    fake_discord: FakeDiscord, player: Person, session: Session
) -> None:
    answer = come_back(player, start(player), code="bad-code")

    assert answer.status_code == 303
    assert "discord=Discord+did+not+confirm" in answer.headers["location"]
    assert user(session, player).discord_user_id is None


def test_only_the_browser_that_started_can_finish(
    fake_discord: FakeDiscord, player: Person, client_for: Callable[[], TestClient]
) -> None:
    state = start(player)
    # Another browser of the same person: signed in, but without the linking cookie.
    elsewhere = client_for()
    signed_in = elsewhere.post("/auth/login", json={"login": player.email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text

    refused = elsewhere.get(
        "/discord/callback", params={"state": state, "code": "good-code"}, follow_redirects=False
    )

    assert refused.status_code == 400


def test_someone_else_cannot_finish_your_link(
    fake_discord: FakeDiscord, player: Person, client_for: Callable[[], TestClient]
) -> None:
    state = start(player)
    other = sign_up(client_for, "intruder")

    refused = come_back(other, state, code="good-code")

    assert refused.status_code == 400


def test_a_discord_account_linked_to_someone_else_is_refused(
    fake_discord: FakeDiscord,
    player: Person,
    client_for: Callable[[], TestClient],
    session: Session,
) -> None:
    first = sign_up(client_for, "firstlinker")
    come_back(first, start(first), code="good-code")

    answer = come_back(player, start(player), code="good-code")

    assert answer.headers["location"] == "/account?discord=taken"
    assert user(session, player).discord_user_id is None
    assert user(session, first).discord_user_id == DISCORD_ID
    assert actions(session, player) == ["account.discord_link_refused"]


def test_unlinking_forgets_the_account_but_keeps_the_username(
    fake_discord: FakeDiscord, player: Person, session: Session
) -> None:
    come_back(player, start(player), code="good-code")

    unlinked = player.client.delete("/account/discord")

    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json() == {
        "available": True,
        "linked": False,
        "handle": "night_owl",
        "can_unlink": False,
    }
    assert user(session, player).discord_user_id is None
    assert actions(session, player) == ["account.discord_linked", "account.discord_unlinked"]


def test_discord_stays_linked_while_it_is_the_only_way_to_sign_in(
    fake_discord: FakeDiscord, player: Person, session: Session
) -> None:
    come_back(player, start(player), code="good-code")
    account = user(session, player)
    account.password_hash = None
    session.add(AuthIdentity(user_id=account.id, provider="discord", subject=DISCORD_ID))
    session.flush()

    assert player.client.get("/account/discord").json()["can_unlink"] is False
    refused = player.client.delete("/account/discord")

    assert refused.status_code == 409
    assert user(session, player).discord_user_id == DISCORD_ID


def test_linking_calls_the_hook_for_pending_confirmations(
    fake_discord: FakeDiscord, player: Person, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked: list[str] = []
    monkeypatch.setattr(
        discord_account.discord_links, "account_linked", lambda db, who: linked.append(who.email)
    )

    come_back(player, start(player), code="good-code")

    assert linked == [player.email]

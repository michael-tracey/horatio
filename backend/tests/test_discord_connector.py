"""The Discord connector against a fake Discord: connecting a server, picking
channels, splitting long results, and what is worth retrying."""

import json
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import delivery
from horatio.config import get_settings
from horatio.connectors import Message, SendError, discord
from tests.api_helpers import Troupe
from tests.test_api_responses import Scene
from tests.test_delivery_connectors import START, agnes_on, deliver, scene  # noqa: F401

GUILD = "111"
OTHER_GUILD = "999"
AGNES_CHANNEL = "201"
OPEN_CHANNEL = "202"
TEST_CHANNEL = "203"


class FakeDiscord:
    """Enough of Discord's API for the connector: the code exchange, a server's
    channels, and posting messages."""

    def __init__(self) -> None:
        self.posted: list[tuple[str, str]] = []
        self.gone: set[str] = set()
        # Responses to give, in order, before posting normally: (status, body).
        self.next: list[tuple[int, dict[str, Any]]] = []
        self.waits: list[float] = []
        self.guild = (GUILD, "Court of Ash")

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v10/oauth2/token":
            form = parse_qs(request.content.decode())
            if form.get("code") != ["good-code"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"guild": {"id": self.guild[0], "name": self.guild[1]}})
        assert request.headers["Authorization"] == "Bot test-token"
        if path == f"/api/v10/guilds/{GUILD}/channels":
            everyone_denied = [{"id": GUILD, "type": 0, "deny": str(1 << 10), "allow": "0"}]
            return httpx.Response(
                200,
                json=[
                    {"id": "100", "type": 4, "name": "Players", "position": 0},
                    {
                        "id": AGNES_CHANNEL,
                        "type": 0,
                        "name": "agnes",
                        "parent_id": "100",
                        "position": 1,
                        "permission_overwrites": everyone_denied,
                    },
                    {"id": OPEN_CHANNEL, "type": 0, "name": "general", "position": 2},
                    {"id": TEST_CHANNEL, "type": 0, "name": "st-test", "position": 3},
                    {"id": "300", "type": 2, "name": "voice", "position": 4},
                ],
            )
        if path.startswith("/api/v10/channels/") and request.method == "POST":
            if self.next:
                code, body = self.next.pop(0)
                return httpx.Response(code, json=body)
            channel = path.split("/")[4]
            if channel in self.gone:
                return httpx.Response(404, json={"message": "Unknown Channel", "code": 10003})
            body = json.loads(request.content)
            assert body["allowed_mentions"] == {"parse": []}
            self.posted.append((channel, body["content"]))
            return httpx.Response(200, json={"id": str(len(self.posted))})
        return httpx.Response(404, json={"message": "Unknown"})


@pytest.fixture
def fake_discord(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeDiscord]:
    fake = FakeDiscord()
    settings = get_settings()
    monkeypatch.setattr(settings, "discord_client_id", "app-id")
    monkeypatch.setattr(settings, "discord_client_secret", "app-secret")
    monkeypatch.setattr(settings, "discord_bot_token", "test-token")
    monkeypatch.setattr(discord, "transport", httpx.MockTransport(fake.handle))
    monkeypatch.setattr(discord, "sleep", fake.waits.append)
    yield fake


def connect_server(ready: Scene, code: str = "good-code") -> httpx.Response:
    troupe = ready.troupe
    invite = troupe.storyteller.client.post(f"/troupes/{troupe.id}/discord/invite")
    assert invite.status_code == 200, invite.text
    query = parse_qs(urlparse(invite.json()["url"]).query)
    assert query["permissions"] == [str(discord.PERMISSIONS)]
    assert query["redirect_uri"] == ["http://localhost:5173/api/discord/callback"]
    return troupe.storyteller.client.get(
        "/discord/callback",
        params={"state": query["state"][0], "code": code, "guild_id": GUILD},
        follow_redirects=False,
    )


def set_up(ready: Scene, **settings: Any) -> httpx.Response:
    troupe = ready.troupe
    return troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/connectors/discord",
        json={"enabled": True, "mode": "full", "settings": settings},
    )


# --- splitting -----------------------------------------------------------------------------


def test_short_messages_go_whole() -> None:
    assert discord.split("Hello.\n\nGoodbye.") == ["Hello.\n\nGoodbye."]


def test_long_messages_split_between_paragraphs_in_order() -> None:
    paragraphs = [f"Paragraph {n}. " + "x" * 600 for n in range(6)]

    parts = discord.split("\n\n".join(paragraphs))

    assert all(len(p) <= 2000 for p in parts)
    assert "\n\n".join(parts) == "\n\n".join(paragraphs)
    assert [p.split(".")[0] for p in parts] == ["Paragraph 0", "Paragraph 3"]


def test_a_paragraph_too_long_splits_between_lines_then_anywhere() -> None:
    lines = "\n".join(["y" * 900] * 3)
    one_line = "z" * 4500

    assert [len(p) for p in discord.split(lines)] == [1801, 900]
    assert [len(p) for p in discord.split(one_line)] == [2000, 2000, 500]


# --- what is worth retrying ----------------------------------------------------------------


def message(text: str = "Results") -> Message:
    return Message(troupe="Court", subject="s", text=text, link="http://x")


def test_a_short_rate_limit_is_waited_out(fake_discord: FakeDiscord) -> None:
    fake_discord.next = [(429, {"retry_after": 1.5, "global": False})]

    sent = discord.DiscordConnector().send({}, AGNES_CHANNEL, message())

    assert sent == {"message_ids": ["1"]}
    assert fake_discord.waits == [1.5]


def test_a_long_rate_limit_is_left_to_the_worker(fake_discord: FakeDiscord) -> None:
    fake_discord.next = [(429, {"retry_after": 120})]

    with pytest.raises(SendError) as failed:
        discord.DiscordConnector().send({}, AGNES_CHANNEL, message())

    assert (failed.value.retry, failed.value.retry_after) == (True, 120)


@pytest.mark.parametrize(
    ("code", "retry"), [(500, True), (502, True), (403, False), (404, False), (400, False)]
)
def test_which_failures_are_worth_retrying(
    fake_discord: FakeDiscord, code: int, retry: bool
) -> None:
    fake_discord.next = [(code, {"message": "nope"})]

    with pytest.raises(SendError) as failed:
        discord.DiscordConnector().send({}, AGNES_CHANNEL, message())

    assert failed.value.retry is retry


def test_a_failure_part_way_says_how_much_was_sent(fake_discord: FakeDiscord) -> None:
    text = "\n\n".join(["w" * 1500] * 3)
    connector = discord.DiscordConnector()
    fake_discord.next = []
    original = fake_discord.handle

    def fail_second(request: httpx.Request) -> httpx.Response:
        if len(fake_discord.posted) == 1:
            return httpx.Response(503, json={})
        return original(request)

    discord.transport = httpx.MockTransport(fail_second)

    with pytest.raises(SendError) as failed:
        connector.send({}, AGNES_CHANNEL, message(text))

    assert failed.value.reason.endswith("(1 of 3 parts were sent.)")


# --- connecting a troupe -----------------------------------------------------------------


def test_without_server_configuration_discord_is_unavailable(scene: Scene) -> None:  # noqa: F811
    troupe = scene.troupe
    listed = next(
        c
        for c in troupe.storyteller.client.get(f"/troupes/{troupe.id}/connectors").json()
        if c["kind"] == "discord"
    )

    assert listed["kind"] == "discord"
    assert "HORATIO_DISCORD_BOT_TOKEN" in listed["unavailable"]
    assert troupe.storyteller.client.post(f"/troupes/{troupe.id}/discord/invite").status_code == 409


def test_connecting_a_server_and_choosing_channels(
    scene: Scene,  # noqa: F811
    fake_discord: FakeDiscord,
) -> None:
    troupe = scene.troupe
    assert troupe.assistant.client.post(f"/troupes/{troupe.id}/discord/invite").status_code == 403

    back = connect_server(scene)

    assert back.status_code == 303
    assert back.headers["location"] == f"/troupes/{troupe.id}/connectors?discord=connected"
    setup = troupe.assistant.client.get(f"/troupes/{troupe.id}/discord").json()
    assert (setup["guild_id"], setup["guild_name"]) == (GUILD, "Court of Ash")
    assert [(c["name"], c["category"], c["private"]) for c in setup["channels"]] == [
        ("agnes", "Players", True),
        ("general", None, False),
        ("st-test", None, False),
    ]
    assert [c["name"] for c in setup["characters"]] == ["Agnes"]

    chosen = set_up(scene, channels={scene.agnes: AGNES_CHANNEL}, test_channel=TEST_CHANNEL)

    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["settings"]["channels"] == {scene.agnes: AGNES_CHANNEL}
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller connected the Discord server Court of Ash." in log


def test_the_server_comes_only_from_discord(
    scene: Scene,  # noqa: F811
    fake_discord: FakeDiscord,
) -> None:
    troupe = scene.troupe
    # Channels need a connected server, and a server cannot be set by hand.
    assert set_up(scene, guild_id=OTHER_GUILD, test_channel=TEST_CHANNEL).status_code == 422
    connect_server(scene)
    kept = set_up(scene, guild_id=OTHER_GUILD)
    assert kept.json()["settings"]["guild_id"] == GUILD
    # Channels must be the server's text channels.
    assert set_up(scene, test_channel="300").status_code == 422
    assert set_up(scene, test_channel="555").status_code == 422
    # A callback with a made-up state, or a code Discord refuses, connects nothing.
    forged = troupe.storyteller.client.get(
        "/discord/callback",
        params={"state": f"{troupe.id}.guess", "code": "good-code"},
        follow_redirects=False,
    )
    assert forged.status_code == 400
    refused = connect_server(scene, code="bad-code")
    assert "did+not+confirm" in refused.headers["location"]


def test_disconnecting_forgets_the_server(
    scene: Scene,  # noqa: F811
    fake_discord: FakeDiscord,
) -> None:
    troupe = scene.troupe
    connect_server(scene)
    set_up(scene, test_channel=TEST_CHANNEL)

    gone = troupe.storyteller.client.delete(f"/troupes/{troupe.id}/discord")

    assert gone.status_code == 204
    listed = next(
        c
        for c in troupe.storyteller.client.get(f"/troupes/{troupe.id}/connectors").json()
        if c["kind"] == "discord"
    )
    assert (listed["enabled"], listed["settings"]) == (False, {})
    assert troupe.storyteller.client.delete(f"/troupes/{troupe.id}/discord").status_code == 404


# --- delivering ----------------------------------------------------------------------------


def test_results_go_to_the_characters_channel_split_and_in_order(
    client_for: Callable[[], TestClient],
    session: Session,
    fake_discord: FakeDiscord,
) -> None:
    long_scene = Scene(Troupe(client_for, session))
    troupe = long_scene.troupe
    night = "\n\n".join(f"Hour {n}. " + "The docks are busy. " * 40 for n in range(6))
    feed = long_scene.response_for("Feed at the docks")["id"]
    troupe.assistant.client.put(f"/responses/{feed}", json={"body": night})
    troupe.assistant.client.post(f"/cycles/{long_scene.cycle['id']}/close")
    connect_server(long_scene)
    set_up(long_scene, channels={long_scene.agnes: AGNES_CHANNEL})
    assert deliver(long_scene)["queued"] == 1

    delivery.send_due(session, START)

    assert len(fake_discord.posted) > 1
    assert {channel for channel, _ in fake_discord.posted} == {AGNES_CHANNEL}
    assert all(len(text) <= 2000 for _, text in fake_discord.posted)
    sent = "\n\n".join(text for _, text in fake_discord.posted)
    assert sent.startswith("**Downtime results for Agnes")
    assert sent.endswith(night.split("\n\n")[-1].strip())
    assert agnes_on(long_scene, "discord")["status"] == "sent"


def test_a_deleted_channel_fails_naming_the_character(
    scene: Scene,  # noqa: F811
    fake_discord: FakeDiscord,
    session: Session,
) -> None:
    connect_server(scene)
    set_up(scene, channels={scene.agnes: AGNES_CHANNEL})
    fake_discord.gone.add(AGNES_CHANNEL)
    deliver(scene)

    delivery.send_due(session, START)

    failed = agnes_on(scene, "discord")
    assert failed["status"] == "failed"
    assert failed["last_error"] == "That channel or server no longer exists."


def test_a_character_with_no_channel_fails_with_their_name(
    scene: Scene,  # noqa: F811
    fake_discord: FakeDiscord,
    session: Session,
) -> None:
    connect_server(scene)
    set_up(scene, test_channel=TEST_CHANNEL)
    deliver(scene)

    delivery.send_due(session, START)

    assert agnes_on(scene, "discord")["last_error"] == "Agnes has no Discord channel."


def test_test_mode_posts_in_the_test_channel(
    scene: Scene,  # noqa: F811
    fake_discord: FakeDiscord,
    session: Session,
) -> None:
    troupe = scene.troupe
    connect_server(scene)
    troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/connectors/discord",
        json={
            "enabled": True,
            "test_mode": True,
            "settings": {"channels": {scene.agnes: AGNES_CHANNEL}, "test_channel": TEST_CHANNEL},
        },
    )
    deliver(scene)

    delivery.send_due(session, START)

    assert [channel for channel, _ in fake_discord.posted] == [TEST_CHANNEL]
    assert fake_discord.posted[0][1].startswith("Your downtime results for Agnes")

"""The Discord connector against a fake Discord: connecting a server, picking
channels, splitting long results, and what is worth retrying.

The fake Discord speaks httpx, as the connector does; the test client's responses
are httpx2."""

import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import delivery
from horatio.config import get_settings
from horatio.connectors import Message, SendError, discord
from tests.api_helpers import Troupe
from tests.test_api_responses import Scene
from tests.test_delivery_connectors import START, agnes_on, deliver, scene, status  # noqa: F401

GUILD = "111"
OTHER_GUILD = "999"
AGNES_CHANNEL = "201"
OPEN_CHANNEL = "202"
TEST_CHANNEL = "203"
# The Horatio bot, the role Discord gives it when a server adds it, and the server's owner.
BOT = "500"
BOT_ROLE = "600"
OWNER = "700"
# What @everyone may do in a new server: see channels and send messages there.
EVERYONE = discord.VIEW_CHANNEL | discord.SEND_MESSAGES


def read_body(request: httpx.Request) -> tuple[dict[str, Any], dict[str, tuple[str, bytes]]]:
    """A message's JSON, and its files by form field (filename, bytes), whether it
    came as JSON or as a form with files."""
    kind = request.headers.get("content-type", "")
    if not kind.startswith("multipart/"):
        return json.loads(request.content), {}
    head = f"Content-Type: {kind}\r\n\r\n".encode()
    form = BytesParser(policy=policy.HTTP).parsebytes(head + request.content)
    payload: dict[str, Any] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in form.iter_parts():
        name = part.get_param("name", header="content-disposition")
        data = part.get_payload(decode=True)
        assert isinstance(name, str) and isinstance(data, bytes)
        if name == "payload_json":
            payload = json.loads(data)
        else:
            files[name] = (str(part.get_filename()), data)
    return payload, files


@dataclass
class Posted:
    channel: str
    payload: dict[str, Any]
    files: dict[str, tuple[str, bytes]]


class FakeDiscord:
    """Enough of Discord's API for the connector: the code exchange, a server's
    channels, and posting, editing and deleting messages."""

    def __init__(self) -> None:
        self.posted: list[tuple[str, str]] = []
        # Messages there now, by id; and every edit and deletion, in order.
        self.messages: dict[str, Posted] = {}
        self.edits: list[str] = []
        self.deletions: list[str] = []
        self.gone: set[str] = set()
        # Responses to give, in order, before posting normally: (status, body).
        self.next: list[tuple[int, dict[str, Any]]] = []
        self.waits: list[float] = []
        self.guild = (GUILD, "Court of Ash")
        # The permissions of the bot's own role: those an invite asked for.
        self.bot_role = discord.PERMISSIONS
        # Whether Discord answers questions about the bot and its server.
        self.answers_about_bot = True
        everyone_denied = {"id": GUILD, "type": 0, "deny": str(1 << 10), "allow": "0"}
        bot_allowed = {"id": BOT_ROLE, "type": 0, "deny": "0", "allow": str(EVERYONE)}
        self.channels: list[dict[str, Any]] = [
            {"id": "100", "type": 4, "name": "Players", "position": 0},
            {
                "id": AGNES_CHANNEL,
                "type": 0,
                "name": "agnes",
                "parent_id": "100",
                "position": 1,
                "permission_overwrites": [everyone_denied, bot_allowed],
            },
            {"id": OPEN_CHANNEL, "type": 0, "name": "general", "position": 2},
            {"id": TEST_CHANNEL, "type": 0, "name": "st-test", "position": 3},
            {"id": "300", "type": 2, "name": "voice", "position": 4},
        ]

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v10/oauth2/token":
            form = parse_qs(request.content.decode())
            if form.get("code") != ["good-code"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"guild": {"id": self.guild[0], "name": self.guild[1]}})
        assert request.headers["Authorization"] == "Bot test-token"
        if path == f"/api/v10/guilds/{GUILD}/channels":
            return httpx.Response(200, json=self.channels)
        about_bot = {
            "/api/v10/users/@me": {"id": BOT},
            f"/api/v10/guilds/{GUILD}": {
                "id": GUILD,
                "owner_id": OWNER,
                "roles": [
                    {"id": GUILD, "permissions": str(EVERYONE)},
                    {"id": BOT_ROLE, "permissions": str(self.bot_role)},
                ],
            },
            f"/api/v10/guilds/{GUILD}/members/{BOT}": {"roles": [BOT_ROLE]},
        }
        if path in about_bot:
            if not self.answers_about_bot:
                return httpx.Response(403, json={"message": "Missing Access", "code": 50001})
            return httpx.Response(200, json=about_bot[path])
        if path.startswith("/api/v10/channels/"):
            channel = path.split("/")[4]
            if request.method == "GET" and path.count("/") == 4:
                if not self.answers_about_bot:
                    return httpx.Response(403, json={"message": "Missing Access", "code": 50001})
                found = next((c for c in self.channels if c["id"] == channel), None)
                if found is None:
                    return httpx.Response(404, json={"message": "Unknown Channel", "code": 10003})
                return httpx.Response(200, json={**found, "guild_id": GUILD})
            if self.next:
                code, body = self.next.pop(0)
                return httpx.Response(code, json=body)
            if channel in self.gone:
                return httpx.Response(404, json={"message": "Unknown Channel", "code": 10003})
            message_id = path.split("/")[6] if path.count("/") >= 6 else None
            if request.method == "POST":
                body, files = read_body(request)
                assert body["allowed_mentions"] == {"parse": []}
                self.posted.append((channel, body.get("content", "")))
                new_id = str(len(self.posted))
                self.messages[new_id] = Posted(channel, body, files)
                return httpx.Response(200, json={"id": new_id})
            there = self.messages.get(message_id or "")
            if there is None or there.channel != channel:
                return httpx.Response(404, json={"message": "Unknown Message", "code": 10008})
            if request.method == "PATCH":
                body, files = read_body(request)
                assert body["allowed_mentions"] == {"parse": []}
                self.messages[message_id or ""] = Posted(channel, body, files)
                self.edits.append(message_id or "")
                return httpx.Response(200, json={"id": message_id})
            if request.method == "DELETE":
                del self.messages[message_id or ""]
                self.deletions.append(message_id or "")
                return httpx.Response(204)
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


def connect_server(ready: Scene, code: str = "good-code") -> httpx2.Response:
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


def set_up(ready: Scene, **settings: Any) -> httpx2.Response:
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


# --- embeds, edited and deleted --------------------------------------------------------------


def test_a_refusal_for_want_of_permission_names_what_the_bot_lacks(
    fake_discord: FakeDiscord,
) -> None:
    # The bot was added with the old invite: it may see channels and send messages.
    fake_discord.bot_role = discord.VIEW_CHANNEL | discord.SEND_MESSAGES
    fake_discord.next = [(403, {"message": "Missing Permissions", "code": 50013})]

    with pytest.raises(SendError) as failed:
        discord.post_message(OPEN_CHANNEL, {"embeds": [{"title": "Fire at the docks"}]})

    assert failed.value.reason == (
        "The Horatio bot needs Embed Links and Attach Files in that channel. "
        "Give it those permissions in the channel's settings on Discord."
    )
    assert failed.value.retry is False


def test_results_refused_in_a_channel_the_bot_cant_post_in_say_so(
    fake_discord: FakeDiscord,
) -> None:
    deny_send = {"id": BOT_ROLE, "type": 0, "deny": str(discord.SEND_MESSAGES), "allow": "0"}
    fake_discord.channels[3]["permission_overwrites"] = [deny_send]
    fake_discord.next = [(403, {"message": "Missing Permissions", "code": 50013})]

    with pytest.raises(SendError) as failed:
        discord.DiscordConnector().send({}, TEST_CHANNEL, message())

    assert failed.value.reason.startswith("The Horatio bot needs Send Messages in that channel.")


def test_a_refusal_discord_wont_explain_says_a_permission_is_missing(
    fake_discord: FakeDiscord,
) -> None:
    fake_discord.answers_about_bot = False
    fake_discord.next = [(403, {"message": "Missing Permissions", "code": 50013})]

    with pytest.raises(SendError) as failed:
        discord.post_message(OPEN_CHANNEL, {"content": "News"})

    assert failed.value.reason == "The Horatio bot is missing a permission in that channel."


def test_an_embed_goes_with_its_pictures_and_pings_nobody(fake_discord: FakeDiscord) -> None:
    embed = {"title": "Fire at the docks", "image": {"url": "attachment://picture.webp"}}
    picture = discord.File("picture.webp", b"RIFF-picture")

    sent = discord.post_message(OPEN_CHANNEL, {"embeds": [embed]}, [picture])

    there = fake_discord.messages[sent]
    assert there.channel == OPEN_CHANNEL
    assert there.payload["embeds"] == [embed]
    assert there.payload["attachments"] == [{"id": 0, "filename": "picture.webp"}]
    assert there.files == {"files[0]": ("picture.webp", b"RIFF-picture")}


def test_an_edit_replaces_the_message_and_its_attachments(fake_discord: FakeDiscord) -> None:
    picture = discord.File("picture.webp", b"old")
    sent = discord.post_message(OPEN_CHANNEL, {"embeds": [{"title": "Old"}]}, [picture])

    discord.edit_message(OPEN_CHANNEL, sent, {"embeds": [{"title": "New"}]})

    there = fake_discord.messages[sent]
    assert fake_discord.edits == [sent]
    assert there.payload["embeds"] == [{"title": "New"}]
    # No attachments listed: the old picture goes.
    assert there.payload["attachments"] == []
    assert there.files == {}


def test_editing_a_message_someone_deleted_says_so(fake_discord: FakeDiscord) -> None:
    with pytest.raises(SendError) as failed:
        discord.edit_message(OPEN_CHANNEL, "404404", {"embeds": []})

    assert (failed.value.status, failed.value.retry) == (404, False)


def test_deleting_a_message_already_gone_is_no_failure(fake_discord: FakeDiscord) -> None:
    sent = discord.post_message(OPEN_CHANNEL, {"embeds": [{"title": "Gone soon"}]})

    discord.delete_message(OPEN_CHANNEL, sent)
    discord.delete_message(OPEN_CHANNEL, sent)

    assert sent not in fake_discord.messages
    assert fake_discord.deletions == [sent]


def test_a_failed_delete_worth_retrying_is_raised(fake_discord: FakeDiscord) -> None:
    sent = discord.post_message(OPEN_CHANNEL, {"embeds": [{"title": "Stubborn"}]})
    fake_discord.next = [(503, {})]

    with pytest.raises(SendError) as failed:
        discord.delete_message(OPEN_CHANNEL, sent)

    assert failed.value.retry is True
    assert sent in fake_discord.messages


# --- connecting a troupe -----------------------------------------------------------------


def test_without_server_configuration_discord_is_unavailable(scene: Scene) -> None:  # noqa: F811
    troupe = scene.troupe
    listed = next(
        c
        for c in troupe.storyteller.client.get(f"/troupes/{troupe.id}/connectors").json()
        if c["kind"] == "discord"
    )

    assert listed["kind"] == "discord"
    assert listed["unavailable"] == "Discord isn't set up on this server yet."
    assert "HORATIO_DISCORD_BOT_TOKEN" not in str(listed)
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
    # Her name suggests her channel; nothing is chosen until a storyteller uses it.
    assert setup["suggestions"] == {scene.agnes: AGNES_CHANNEL}

    chosen = set_up(scene, channels={scene.agnes: AGNES_CHANNEL}, test_channel=TEST_CHANNEL)

    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["settings"]["channels"] == {scene.agnes: AGNES_CHANNEL}
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller connected the Discord server Court of Ash." in log


def test_the_invite_asks_for_what_posts_need() -> None:
    names = discord.missing(0, discord.PERMISSIONS)

    assert discord.PERMISSIONS == 52224
    assert names == ["View Channels", "Send Messages", "Embed Links", "Attach Files"]


def test_staff_see_which_permissions_the_bot_lacks_in_each_channel(
    scene: Scene,  # noqa: F811
    fake_discord: FakeDiscord,
) -> None:
    troupe = scene.troupe
    connect_server(scene)
    # A server that added the bot before Horatio asked for Embed Links and Attach Files.
    fake_discord.bot_role = discord.VIEW_CHANNEL | discord.SEND_MESSAGES
    deny_view = {"id": BOT_ROLE, "type": 0, "deny": str(discord.VIEW_CHANNEL), "allow": "0"}
    fake_discord.channels[3]["permission_overwrites"] = [deny_view]

    setup = troupe.storyteller.client.get(f"/troupes/{troupe.id}/discord").json()
    posting = troupe.storyteller.client.get(f"/troupes/{troupe.id}/post-channels").json()

    expected = {
        "agnes": ["Embed Links", "Attach Files"],
        "general": ["Embed Links", "Attach Files"],
        "st-test": ["View Channels", "Send Messages", "Embed Links", "Attach Files"],
    }
    assert {c["name"]: c["missing"] for c in setup["channels"]} == expected
    assert {c["name"]: c["missing"] for c in posting["channels"]} == expected

    fake_discord.bot_role = discord.PERMISSIONS
    fake_discord.channels[3]["permission_overwrites"] = []
    setup = troupe.storyteller.client.get(f"/troupes/{troupe.id}/discord").json()
    assert {c["name"]: c["missing"] for c in setup["channels"]} == {
        "agnes": [],
        "general": [],
        "st-test": [],
    }

    # When Discord won't say, the channels are still listed, unchecked.
    fake_discord.answers_about_bot = False
    setup = troupe.storyteller.client.get(f"/troupes/{troupe.id}/discord").json()
    assert [c["missing"] for c in setup["channels"]] == [None, None, None]


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


# --- suggesting channels -----------------------------------------------------------------


def channel(id: str, name: str, private: bool = True) -> discord.Channel:
    return discord.Channel(id=id, name=name, category=None, private=private)


def suggest(names: list[str], channels: list[discord.Channel]) -> dict[str, str]:
    """Suggestions by character name, for reading."""
    ids = {name: uuid.uuid4() for name in names}
    found = discord.suggested_channels(list((i, n) for n, i in ids.items()), channels)
    return {name: found[str(i)] for name, i in ids.items() if str(i) in found}


def test_a_channel_matches_a_name_whatever_its_case_dashes_or_accents() -> None:
    channels = [channel("1", "agnes-wren"), channel("2", "Zoë_Hart"), channel("3", "general")]

    assert suggest(["Agnes Wren", "Zoe Hart", "Ezra Vale"], channels) == {
        "Agnes Wren": "1",
        "Zoe Hart": "2",
    }
    assert discord.plain_name("Zoë  Hart-Smith") == "zoehartsmith"


def test_a_first_name_matches_only_when_no_one_else_has_it() -> None:
    channels = [channel("1", "agnes"), channel("2", "ezra")]

    assert suggest(["Agnes Wren", "Ezra Vale", "Ezra Pike"], channels) == {"Agnes Wren": "1"}


def test_private_channels_come_first_then_the_full_name() -> None:
    open_full = channel("1", "agnes-wren", private=False)
    private_first = channel("2", "agnes")
    private_full = channel("3", "agnes_wren")

    assert suggest(["Agnes Wren"], [open_full, private_first]) == {"Agnes Wren": "2"}
    assert suggest(["Agnes Wren"], [open_full, private_first, private_full]) == {"Agnes Wren": "3"}
    # A channel everyone can see is still suggested when it is the only match.
    assert suggest(["Agnes Wren"], [open_full]) == {"Agnes Wren": "1"}


def test_a_channel_two_characters_could_have_goes_to_neither() -> None:
    assert suggest(["Agnes Wren", "Agnes  Wren"], [channel("1", "agnes-wren")]) == {}


# --- the bot's permissions in a channel ------------------------------------------------------

ROLE = "800"


def access(everyone: int = EVERYONE, role: int = 0, owner: str = OWNER) -> discord.BotAccess:
    return discord.BotAccess(
        guild_id=GUILD,
        owner_id=owner,
        roles={GUILD: everyone, ROLE: role},
        bot_id=BOT,
        bot_roles=[ROLE],
    )


def rule(id: str, allow: int = 0, deny: int = 0) -> dict[str, Any]:
    return {"id": id, "allow": str(allow), "deny": str(deny)}


def lacks(bot: discord.BotAccess, *overwrites: dict[str, Any]) -> list[str]:
    return discord.missing(bot.permissions(list(overwrites)), discord.PERMISSIONS)


def test_the_bots_roles_add_to_everyones() -> None:
    assert lacks(access()) == ["Embed Links", "Attach Files"]
    assert lacks(access(role=discord.EMBED_LINKS | discord.ATTACH_FILES)) == []


def test_the_owner_and_an_administrator_may_do_anything() -> None:
    hidden = rule(GUILD, deny=discord.VIEW_CHANNEL)

    assert lacks(access(everyone=0, owner=BOT), hidden) == []
    assert lacks(access(everyone=0, role=discord.ADMINISTRATOR), hidden) == []


def test_a_private_channel_needs_the_bot_let_in() -> None:
    hidden = rule(GUILD, deny=discord.VIEW_CHANNEL)
    full = discord.PERMISSIONS

    assert lacks(access(role=full), hidden) == [
        "View Channels",
        "Send Messages",
        "Embed Links",
        "Attach Files",
    ]
    assert lacks(access(role=full), hidden, rule(ROLE, allow=discord.VIEW_CHANNEL)) == []
    assert lacks(access(role=full), hidden, rule(BOT, allow=discord.VIEW_CHANNEL)) == []


def test_the_bot_itself_comes_last_then_its_roles_allow_over_their_denials() -> None:
    full = discord.PERMISSIONS

    assert lacks(access(role=full), rule(ROLE, deny=discord.EMBED_LINKS)) == ["Embed Links"]
    assert (
        lacks(
            access(role=full),
            rule(ROLE, deny=discord.EMBED_LINKS),
            rule(BOT, allow=discord.EMBED_LINKS),
        )
        == []
    )
    assert (
        lacks(
            access(role=full),
            rule(GUILD, deny=discord.ATTACH_FILES),
            rule(ROLE, allow=discord.ATTACH_FILES),
        )
        == []
    )


def test_without_send_messages_nothing_can_be_embedded_or_attached() -> None:
    no_send = rule(ROLE, deny=discord.SEND_MESSAGES)

    assert lacks(access(role=discord.PERMISSIONS), no_send) == [
        "Send Messages",
        "Embed Links",
        "Attach Files",
    ]


def test_without_a_server_there_is_nothing_to_suggest(
    scene: Scene,  # noqa: F811
    fake_discord: FakeDiscord,
) -> None:
    troupe = scene.troupe
    setup = troupe.storyteller.client.get(f"/troupes/{troupe.id}/discord").json()

    assert (setup["channels"], setup["suggestions"]) == ([], {})


# --- warning before delivering -------------------------------------------------------------


def test_delivering_warns_of_characters_with_no_channel(
    scene: Scene,  # noqa: F811
    fake_discord: FakeDiscord,
) -> None:
    connect_server(scene)
    # Discord off: nothing to warn about.
    [agnes] = status(scene)["participants"]
    assert agnes["unreachable"] == []

    set_up(scene, test_channel=TEST_CHANNEL)
    [agnes] = status(scene)["participants"]
    assert agnes["unreachable"] == ["discord"]

    set_up(scene, channels={scene.agnes: AGNES_CHANNEL}, test_channel=TEST_CHANNEL)
    [agnes] = status(scene)["participants"]
    assert agnes["unreachable"] == []


def test_test_mode_needs_no_characters_channels(
    scene: Scene,  # noqa: F811
    fake_discord: FakeDiscord,
) -> None:
    troupe = scene.troupe
    connect_server(scene)
    troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/connectors/discord",
        json={"enabled": True, "test_mode": True, "settings": {"test_channel": TEST_CHANNEL}},
    )

    [agnes] = status(scene)["participants"]
    assert agnes["unreachable"] == []


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

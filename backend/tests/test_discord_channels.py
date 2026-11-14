"""Character channels Horatio makes on a troupe's Discord server (#855), against a
fake Discord: switching it on, staff roles, a verified player, a typed username a
storyteller confirms, an invite, the bot lacking permissions, every character
through the worker, and a verified account taking over a match (#857)."""

import json
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import character_moves, discord_channels, renames
from horatio.config import get_settings
from horatio.connectors import discord
from horatio.models import Character, TroupeConnector, User
from tests.api_helpers import Troupe
from tests.test_api_downtimes import member_character
from tests.test_discord_connector import (
    BOT,
    BOT_ROLE,
    EVERYONE,
    GUILD,
    OPEN_CHANNEL,
    OWNER,
    FakeDiscord,
)

STS = "800"
PLAYERS_ROLE = "801"
SYSTEM = "202"
PLAYER = "900"
OTHER = "901"


class FakeServer(FakeDiscord):
    """The fake Discord, with what making channels needs: the server's named roles,
    its members, member search, making channels and invites."""

    def __init__(self) -> None:
        super().__init__()
        self.bot_role = discord.FOR_MANAGED | discord.CREATE_INSTANT_INVITE
        self.members: dict[str, dict[str, Any]] = {}
        self.made: list[dict[str, Any]] = []
        self.invites: list[tuple[str, dict[str, Any]]] = []
        self.searches: list[str] = []
        # Responses to give to the next channel or category made: (status, body).
        self.refuse_making: list[tuple[int, dict[str, Any]]] = []
        # Channels renamed and overwrites set or taken off (#856), in order; and
        # responses to give to the next such change instead.
        self.changes: list[tuple[str, str, str]] = []
        self.refuse_changing: list[tuple[int, dict[str, Any]]] = []

    def add_member(self, user_id: str, username: str, nick: str | None = None) -> None:
        self.members[user_id] = {
            "user": {
                "id": user_id,
                "username": username,
                "global_name": username.title(),
                "avatar": "abc",
            },
            "nick": nick,
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v10")
        # A player linking their own Discord account (#857): an `identify` grant.
        if path == "/oauth2/token" and b"code=link-code" in request.content:
            return httpx.Response(200, json={"access_token": "user-token", "scope": "identify"})
        if path == "/users/@me" and request.headers["Authorization"] == "Bearer user-token":
            return httpx.Response(200, json={"id": PLAYER, "username": "nightowl"})
        if path == f"/guilds/{GUILD}" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": GUILD,
                    "owner_id": OWNER,
                    "system_channel_id": SYSTEM,
                    "roles": [
                        {
                            "id": GUILD,
                            "name": "@everyone",
                            "permissions": str(EVERYONE),
                            "position": 0,
                        },
                        {
                            "id": BOT_ROLE,
                            "name": "Horatio",
                            "permissions": str(self.bot_role),
                            "position": 3,
                            "managed": True,
                        },
                        {"id": STS, "name": "sts", "permissions": "0", "position": 2},
                        {"id": PLAYERS_ROLE, "name": "players", "permissions": "0", "position": 1},
                    ],
                },
            )
        if path == f"/guilds/{GUILD}/channels" and request.method == "POST":
            if self.refuse_making:
                code, body = self.refuse_making.pop(0)
                return httpx.Response(code, json=body)
            body = json.loads(request.content)
            made = {**body, "id": str(3000 + len(self.made)), "position": 10 + len(self.made)}
            self.made.append(made)
            self.channels.append(made)
            return httpx.Response(201, json=made)
        if path == f"/guilds/{GUILD}/members/search":
            query = request.url.params["query"]
            self.searches.append(query)
            found = [
                m
                for m in self.members.values()
                if m["user"]["username"].startswith(query) or (m["nick"] or "").startswith(query)
            ]
            return httpx.Response(200, json=found)
        if (
            path.startswith(f"/guilds/{GUILD}/members/")
            and path != f"/guilds/{GUILD}/members/{BOT}"
        ):
            member = self.members.get(path.rsplit("/", 1)[1])
            if member is None:
                return httpx.Response(404, json={"message": "Unknown Member", "code": 10007})
            return httpx.Response(200, json=member)
        # Keeping channels in step (#856): renaming, and one overwrite at a time.
        if path.startswith("/channels/") and request.method in ("PATCH", "PUT", "DELETE"):
            bits = path.split("/")
            channel = next((c for c in self.channels if c["id"] == bits[2]), None)
            if self.refuse_changing:
                code, body = self.refuse_changing.pop(0)
                return httpx.Response(code, json=body)
            if channel is None:
                return httpx.Response(404, json={"message": "Unknown Channel", "code": 10003})
            if request.method == "PATCH" and len(bits) == 3:
                channel.update(json.loads(request.content))
                self.changes.append(("rename", bits[2], channel["name"]))
                return httpx.Response(200, json=channel)
            if len(bits) == 5 and bits[3] == "permissions":
                rules = channel.setdefault("permission_overwrites", [])
                rules[:] = [o for o in rules if o["id"] != bits[4]]
                if request.method == "PUT":
                    rules.append({"id": bits[4], **json.loads(request.content)})
                self.changes.append((request.method.lower(), bits[2], bits[4]))
                return httpx.Response(204)
        if path.endswith("/invites") and request.method == "POST":
            self.invites.append((path.split("/")[2], json.loads(request.content)))
            return httpx.Response(200, json={"code": f"invite{len(self.invites)}"})
        return super().handle(request)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeServer]:
    server = FakeServer()
    settings = get_settings()
    monkeypatch.setattr(settings, "discord_client_id", "app-id")
    monkeypatch.setattr(settings, "discord_client_secret", "app-secret")
    monkeypatch.setattr(settings, "discord_bot_token", "test-token")
    monkeypatch.setattr(discord, "transport", httpx.MockTransport(server.handle))
    monkeypatch.setattr(discord, "sleep", server.waits.append)
    yield server


class Court:
    """A troupe with its Discord server connected and one character, Agnes."""

    def __init__(self, client_for: Callable[[], TestClient], session: Session) -> None:
        from tests.test_discord_connector import connect_server

        self.troupe = Troupe(client_for, session)
        self.session = session
        self.agnes = member_character(self.troupe, self.troupe.player, "Agnès Wren")
        back = connect_server(SimpleNamespace(troupe=self.troupe))  # type: ignore[arg-type]
        assert back.status_code == 303, back.text

    @property
    def player(self) -> User:
        return self.session.scalars(
            select(User).where(User.id == uuid.UUID(self.troupe.player.id))
        ).one()

    def manage(self, on: bool = True, roles: list[str] | None = None) -> Any:
        return self.troupe.storyteller.client.put(
            f"/troupes/{self.troupe.id}/discord/managed",
            json={"on": on, "staff_roles": roles if roles is not None else [STS]},
        )

    def make(self, character: str | None = None) -> Any:
        response = self.troupe.storyteller.client.post(
            f"/troupes/{self.troupe.id}/discord/characters/{character or self.agnes}/channel"
        )
        assert response.status_code == 200, response.text
        return response.json()

    def setup(self) -> Any:
        return self.troupe.storyteller.client.get(f"/troupes/{self.troupe.id}/discord").json()

    def settings(self) -> dict[str, Any]:
        row = self.session.scalars(
            select(TroupeConnector).where(
                TroupeConnector.troupe_id == uuid.UUID(self.troupe.id),
                TroupeConnector.kind == "discord",
            )
        ).one()
        self.session.refresh(row)
        return row.settings

    def bell(self) -> list[dict[str, Any]]:
        return self.troupe.player.client.get("/notifications").json()["items"]

    def log(self) -> list[str]:
        found = self.troupe.lead.client.get(f"/troupes/{self.troupe.id}/log").json()
        return [e["message"] for e in found]


@pytest.fixture
def court(client_for: Callable[[], TestClient], session: Session, fake: FakeServer) -> Court:
    return Court(client_for, session)


def test_storytellers_switch_it_on_and_choose_staff_roles(court: Court, fake: FakeServer) -> None:
    troupe = court.troupe
    before = court.setup()["managed"]
    assert (before["on"], before["staff_roles"], before["lacks"]) == (False, [], [])
    # The server's own roles, never @everyone nor the bot's.
    assert [r["name"] for r in before["roles"]] == ["sts", "players"]
    assert before["can_invite"] is True

    refused = troupe.assistant.client.put(
        f"/troupes/{troupe.id}/discord/managed", json={"on": True, "staff_roles": [STS]}
    )
    assert refused.status_code == 403
    assert court.manage(roles=["12345"]).status_code == 422
    assert court.manage(roles=[STS]).status_code == 204

    after = court.setup()["managed"]
    assert (after["on"], after["staff_roles"]) == (True, [STS])
    log = court.log()
    assert any("turned Horatio making the troupe's Discord character channels on" in m for m in log)
    assert any("let into every character channel Horatio makes: @sts" in m for m in log)

    # Saving the connector as usual keeps it.
    saved = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/connectors/discord",
        json={"enabled": True, "settings": {"channels": {}, "test_channel": None}},
    )
    assert saved.status_code == 200, saved.text
    assert court.settings()["managed"]["on"] is True


def test_the_bot_lacking_a_permission_says_which(court: Court, fake: FakeServer) -> None:
    fake.bot_role = discord.PERMISSIONS
    court.player.discord_user_id = PLAYER
    court.session.flush()
    court.manage()

    assert court.setup()["managed"]["lacks"] == [
        "Read Message History",
        "Manage Channels",
        "Manage Roles",
    ]
    outcome = court.make()
    assert outcome["status"] == "bot_lacks"
    assert "Read Message History, Manage Channels and Manage Roles" in outcome["note"]
    assert fake.made == []


def test_a_verified_player_gets_a_private_channel_at_once(court: Court, fake: FakeServer) -> None:
    court.player.discord_user_id = PLAYER
    court.session.flush()
    fake.add_member(PLAYER, "nightowl")
    # A channel already has the name, so Horatio's gets the next.
    fake.channels.append({"id": "250", "type": 0, "name": "agnes-wren", "position": 5})
    court.manage(roles=[STS])

    outcome = court.make()

    assert outcome["status"] == "made"
    category, channel = fake.made
    assert (category["name"], category["type"]) == ("Horatio · Characters", 4)
    assert (channel["name"], channel["type"], channel["parent_id"]) == (
        "agnes-wren-2",
        0,
        category["id"],
    )
    rules = {
        (o["id"], o["type"]): (int(o["allow"]), int(o["deny"]))
        for o in channel["permission_overwrites"]
    }
    assert rules[(GUILD, 0)] == (0, discord.VIEW_CHANNEL)
    assert rules[(BOT, 1)] == (discord_channels.BOT_ALLOW, 0)
    assert rules[(STS, 0)] == (discord_channels.STAFF_ALLOW, 0)
    assert rules[(PLAYER, 1)] == (discord_channels.PLAYER_ALLOW, 0)
    assert PLAYERS_ROLE not in {o["id"] for o in channel["permission_overwrites"]}

    settings = court.settings()
    assert settings["channels"] == {court.agnes: channel["id"]}
    assert settings["managed"]["made"] == {court.agnes: channel["id"]}
    setup = court.setup()
    assert setup["managed"]["characters"][court.agnes]["made"] is True
    assert setup["managed"]["characters"][court.agnes]["discord"] == "verified"
    [told] = [n for n in court.bell() if "Discord channel" in n["summary"]]
    assert (
        told["summary"]
        == "Your Discord channel #agnes-wren-2 is ready: Agnès Wren's results go there now."
    )
    assert told["link"] == f"https://discord.com/channels/{GUILD}/{channel['id']}"
    assert any("make Agnès Wren" in m and "Discord channel #agnes-wren-2" in m for m in court.log())

    # Asked again, it has one: nothing more is made.
    again = court.make()
    assert (again["status"], again["channel"]) == ("made", channel["id"])
    assert len(fake.made) == 2


def test_a_typed_username_waits_for_a_storyteller(court: Court, fake: FakeServer) -> None:
    court.player.discord_handle = "nightowl"
    court.session.flush()
    fake.add_member(OTHER, "nightowlette")
    fake.add_member(PLAYER, "nightowl", nick="Owl")
    court.manage()

    outcome = court.make()

    assert outcome["status"] == "confirm"
    assert fake.searches == ["nightowl"]
    assert fake.made == []
    shown = court.setup()["managed"]["characters"][court.agnes]
    assert (shown["discord"], shown["username"]) == ("typed", "nightowl")
    assert shown["match"] == {
        "username": "nightowl",
        "display_name": "Owl",
        "avatar": f"https://cdn.discordapp.com/avatars/{PLAYER}/abc.png?size=64",
    }
    answer = f"/troupes/{court.troupe.id}/discord/characters/{court.agnes}/match"
    assert court.troupe.assistant.client.post(answer, json={"its_them": True}).status_code == 403

    no = court.troupe.storyteller.client.post(answer, json={"its_them": False}).json()
    assert no["status"] == "rejected"
    assert court.setup()["managed"]["characters"][court.agnes]["match"] is None
    assert court.troupe.storyteller.client.post(answer, json={"its_them": True}).status_code == 404

    assert court.make()["status"] == "confirm"
    yes = court.troupe.storyteller.client.post(answer, json={"its_them": True}).json()

    assert yes["status"] == "made"
    [channel] = [c for c in fake.made if c["type"] == 0]
    assert PLAYER in {o["id"] for o in channel["permission_overwrites"]}
    assert court.settings()["managed"]["members"][court.troupe.player.id]["id"] == PLAYER
    shown = court.setup()["managed"]["characters"][court.agnes]
    assert (shown["discord"], shown["username"]) == ("confirmed", "nightowl")
    log = court.log()
    assert any("said the Discord user @nightowl isn't Agnès Wren" in m for m in log)
    assert any("confirmed that the Discord user @nightowl is Agnès Wren" in m for m in log)


def test_no_one_with_the_username_or_no_discord_at_all(court: Court, fake: FakeServer) -> None:
    court.manage()
    assert court.make()["status"] == "no_discord"

    court.player.discord_handle = "ghost"
    court.session.flush()
    outcome = court.make()

    assert outcome["status"] == "not_found"
    assert "@ghost" in outcome["note"]


def test_a_player_not_on_the_server_is_invited_once(court: Court, fake: FakeServer) -> None:
    court.player.discord_user_id = PLAYER
    court.session.flush()
    court.manage()

    first = court.make()
    second = court.make()

    assert (first["status"], second["status"]) == ("invited", "invited")
    [(through, asked)] = fake.invites
    assert through == SYSTEM
    assert (asked["max_uses"], asked["unique"]) == (1, True)
    [told] = [n for n in court.bell() if "invited" in n["summary"]]
    assert told["link"] == "https://discord.gg/invite1"
    assert fake.made == []

    # Once they've joined, the channel is made.
    fake.add_member(PLAYER, "nightowl")
    assert court.make()["status"] == "made"
    assert court.settings()["managed"]["invited"] == {}


def test_without_create_invite_staff_invite_them(court: Court, fake: FakeServer) -> None:
    fake.bot_role = discord.FOR_MANAGED
    court.player.discord_user_id = PLAYER
    court.session.flush()
    court.manage()

    outcome = court.make()

    assert outcome["status"] == "not_on_server"
    assert "Create Invite" in outcome["note"]
    assert court.setup()["managed"]["can_invite"] is False
    assert fake.invites == []


def test_every_character_at_once_through_the_worker(
    court: Court, fake: FakeServer, session: Session
) -> None:
    court.player.discord_user_id = PLAYER
    court.session.flush()
    fake.add_member(PLAYER, "nightowl")
    bram = member_character(court.troupe, court.troupe.stranger, "Bram")
    court.manage()
    url = f"/troupes/{court.troupe.id}/discord/channels"

    queued = court.troupe.storyteller.client.post(url).json()

    assert queued == {"queued": 2}
    assert court.setup()["managed"]["queued"] == 2
    # Discord asks Horatio to wait a while: the worker leaves the rest for later.
    fake.refuse_making = [(429, {"retry_after": 120})]
    start = discord_channels.now()
    assert discord_channels.make_due(session, start) == 1
    waiting = court.settings()["managed"]
    assert len(waiting["queue"]) == 2
    assert discord_channels.make_due(session, start + timedelta(seconds=30)) == 0

    tried = discord_channels.make_due(session, start + timedelta(minutes=3))

    assert tried == 2
    states = court.setup()["managed"]
    assert states["queued"] == 0
    assert states["characters"][court.agnes]["status"] == "made"
    assert states["characters"][bram]["status"] == "no_discord"
    assert court.settings()["channels"] == {court.agnes: fake.made[-1]["id"]}
    assert any("asked Horatio to make Discord channels for 2 characters" in m for m in court.log())


def test_switched_off_nothing_is_made(court: Court, fake: FakeServer) -> None:
    court.manage(on=False)
    outcome = court.make()
    assert outcome["status"] == "failed"
    assert "switch it on" in outcome["note"]
    refused = court.troupe.storyteller.client.post(f"/troupes/{court.troupe.id}/discord/channels")
    assert refused.status_code == 409


def test_a_full_category_starts_another(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[dict[str, Any]] = []

    def create(guild: str, body: dict[str, Any]) -> dict[str, Any]:
        made.append(body)
        return {**body, "id": "4000"}

    monkeypatch.setattr(discord, "create_channel", create)
    parts = discord_channels.managed({"managed": {"categories": ["3000", "gone"]}})
    found = [{"id": "3000", "type": 4}] + [
        {"id": str(n), "type": 0, "parent_id": "3000"} for n in range(50)
    ]
    access = discord.BotAccess(GUILD, OWNER, {}, BOT, [])

    category = discord_channels.category_for(parts, found, GUILD, access, [STS])

    assert category == "4000"
    assert made[0]["name"] == "Horatio · Characters 2"
    assert parts["categories"] == ["3000", "4000"]


def test_a_linked_discord_account_takes_over_a_match(court: Court, fake: FakeServer) -> None:
    court.player.discord_handle = "nightowl"
    court.session.flush()
    fake.add_member(PLAYER, "nightowl")
    court.manage()
    assert court.make()["status"] == "confirm"

    court.player.discord_user_id = PLAYER
    touched = discord_channels.linked(court.session, court.player)
    court.session.flush()

    assert touched == 1
    managed = court.settings()["managed"]
    assert managed["pending"] == {}
    assert managed["state"][court.agnes]["status"] == "ready"
    assert court.make()["status"] == "made"


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Agnès Wren", "agnes-wren"),
        ("  O'Neil  the Elder ", "o-neil-the-elder"),
        ("!!!", "character"),
    ],
)
def test_channel_names(name: str, slug: str) -> None:
    assert discord.channel_slug(name) == slug


def test_linking_their_discord_account_resolves_a_match(court: Court, fake: FakeServer) -> None:
    """A player linking their Discord account (#857) settles a match a storyteller
    was still to confirm: the verified account takes over, and their character is
    ready to have its channel made."""
    court.player.discord_handle = "nightowl"
    court.session.flush()
    fake.add_member(PLAYER, "nightowl")
    court.manage()
    assert court.make()["status"] == "confirm"
    player = court.troupe.player.client

    started = player.post("/account/discord/link")
    assert started.status_code == 200, started.text
    state = parse_qs(urlparse(started.json()["url"]).query)["state"][0]
    back = player.get(
        "/discord/callback", params={"state": state, "code": "link-code"}, follow_redirects=False
    )

    assert back.status_code == 303, back.text
    managed = court.settings()["managed"]
    assert managed["pending"] == {}
    assert managed["state"][court.agnes]["status"] == "ready"
    shown = court.setup()["managed"]["characters"][court.agnes]
    assert (shown["discord"], shown["match"]) == ("verified", None)
    assert court.make()["status"] == "made"


# --- keeping channels in step, checking and fixing them (#856) ----------------------------


NARRATORS = "802"


def made_channel(court: Court, fake: FakeServer) -> dict[str, Any]:
    """Agnes's channel, made by Horatio for her verified player, as the fake server
    holds it now."""
    court.player.discord_user_id = PLAYER
    court.session.flush()
    fake.add_member(PLAYER, "nightowl")
    court.manage(roles=[STS])
    assert court.make()["status"] == "made"
    [channel] = [c for c in fake.made if c["type"] == 0]
    return channel


def rules(channel: dict[str, Any]) -> dict[str, int]:
    return {o["id"]: int(o["allow"]) for o in channel["permission_overwrites"]}


def agnes(court: Court) -> Character:
    return court.session.get_one(Character, uuid.UUID(court.agnes))


def staff_bell(court: Court) -> list[str]:
    found = court.troupe.storyteller.client.get("/notifications").json()["items"]
    return [n["summary"] for n in found if "Discord channel" in n["summary"]]


def problems(court: Court) -> dict[str, dict[str, Any]]:
    return {p["kind"]: p for p in court.setup()["managed"]["problems"]}


def test_a_renamed_character_has_its_channel_renamed(court: Court, fake: FakeServer) -> None:
    channel = made_channel(court, fake)
    lead = court.session.scalars(select(User).where(User.handle == court.troupe.lead.handle)).one()

    renames.rename(court.session, lead, agnes(court), "Agnès Ash")
    court.session.flush()

    assert court.settings()["managed"]["sync"] == [court.agnes]
    assert court.setup()["managed"]["syncing"] == 1
    assert discord_channels.sync_due(court.session) == 1
    assert channel["name"] == "agnes-ash"
    assert court.settings()["managed"]["sync"] == []
    kept = "renamed #agnes-wren to #agnes-ash"
    assert any("Horatio kept" in m and kept in m for m in court.log())
    # Nothing else changed, so nothing else was asked of Discord.
    assert [c[0] for c in fake.changes] == ["rename"]


def test_a_character_given_to_another_player_lets_them_in(court: Court, fake: FakeServer) -> None:
    channel = made_channel(court, fake)
    stranger = court.session.scalars(
        select(User).where(User.handle == court.troupe.stranger.handle)
    ).one()
    stranger.discord_user_id = OTHER
    fake.add_member(OTHER, "barnowl")
    custodian = court.session.scalars(
        select(User).where(User.handle == court.troupe.custodian.handle)
    ).one()

    character_moves.move(court.session, custodian, agnes(court), stranger, "Swapped", tell=False)
    court.session.flush()
    discord_channels.sync_due(court.session)

    assert OTHER in rules(channel)
    assert PLAYER not in rules(channel)
    assert rules(channel)[OTHER] == discord_channels.PLAYER_ALLOW
    told = court.troupe.stranger.client.get("/notifications").json()["items"]
    assert any(n["summary"].startswith("Your Discord channel #agnes-wren is ready") for n in told)


def test_a_new_player_known_by_a_typed_username_waits_for_a_storyteller(
    court: Court, fake: FakeServer
) -> None:
    channel = made_channel(court, fake)
    stranger = court.session.scalars(
        select(User).where(User.handle == court.troupe.stranger.handle)
    ).one()
    stranger.discord_handle = "barnowl"
    fake.add_member(OTHER, "barnowl")
    custodian = court.session.scalars(
        select(User).where(User.handle == court.troupe.custodian.handle)
    ).one()
    character_moves.move(court.session, custodian, agnes(court), stranger, "Swapped", tell=False)
    court.session.flush()

    discord_channels.sync_due(court.session)

    # The old player is out; the new one waits for a storyteller.
    assert PLAYER not in rules(channel)
    assert OTHER not in rules(channel)
    shown = court.setup()["managed"]["characters"][court.agnes]
    assert shown["match"]["username"] == "barnowl"
    answer = f"/troupes/{court.troupe.id}/discord/characters/{court.agnes}/match"
    yes = court.troupe.storyteller.client.post(answer, json={"its_them": True}).json()
    assert yes["status"] == "made"
    assert "shortly" in yes["note"]

    discord_channels.sync_due(court.session)

    assert rules(channel)[OTHER] == discord_channels.PLAYER_ALLOW


def test_leaving_the_troupe_takes_the_player_out(court: Court, fake: FakeServer) -> None:
    channel = made_channel(court, fake)
    character = agnes(court)
    character.home_troupe_id = None
    discord_channels.changed(court.session, character)
    court.session.flush()

    discord_channels.sync_due(court.session)

    assert PLAYER not in rules(channel)
    assert STS in rules(channel)


def test_staff_roles_changing_reach_every_channel_but_hand_made_access_stays(
    court: Court, fake: FakeServer
) -> None:
    channel = made_channel(court, fake)
    # Someone lets narrators in by hand on Discord: Horatio leaves that alone.
    channel["permission_overwrites"].append(
        {"id": NARRATORS, "type": 0, "allow": str(discord.VIEW_CHANNEL), "deny": "0"}
    )

    assert court.manage(roles=[PLAYERS_ROLE]).status_code == 204
    assert court.settings()["managed"]["sync"] == ["*"]
    discord_channels.sync_due(court.session)

    found = rules(channel)
    assert STS not in found
    assert found[PLAYERS_ROLE] == discord_channels.STAFF_ALLOW
    assert NARRATORS in found
    assert any("took @sts out" in m and "let @players in" in m for m in court.log())


def test_a_retired_characters_channel_is_left_as_it_is(court: Court, fake: FakeServer) -> None:
    channel = made_channel(court, fake)
    agnes(court).status = "retired"
    court.session.flush()
    fake.changes.clear()

    court.manage(roles=[PLAYERS_ROLE])
    discord_channels.sync_due(court.session)

    assert fake.changes == []
    assert STS in rules(channel)
    assert PLAYER in rules(channel)


def test_discord_asking_to_slow_down_waits(court: Court, fake: FakeServer) -> None:
    channel = made_channel(court, fake)
    court.manage(roles=[PLAYERS_ROLE])
    fake.refuse_changing = [(429, {"retry_after": 120})]
    start = discord_channels.now()

    discord_channels.sync_due(court.session, start)

    managed = court.settings()["managed"]
    assert managed["sync"] == [court.agnes]
    assert discord_channels.sync_due(court.session, start + timedelta(seconds=30)) == 0
    assert discord_channels.sync_due(court.session, start + timedelta(minutes=3)) == 1
    assert PLAYERS_ROLE in rules(channel)


def test_a_check_finds_hand_made_changes_and_fix_puts_them_right(
    court: Court, fake: FakeServer
) -> None:
    channel = made_channel(court, fake)
    channel["name"] = "my-own-name"
    channel["permission_overwrites"] = [
        o for o in channel["permission_overwrites"] if o["id"] != STS
    ]
    url = f"/troupes/{court.troupe.id}/discord/check"
    assert court.troupe.assistant.client.post(url).status_code == 403

    assert court.troupe.storyteller.client.post(url).status_code == 204
    assert court.setup()["managed"]["checking"] is True
    assert discord_channels.check_due(court.session) == 1

    found = problems(court)
    assert set(found) == {"name", "access"}
    assert found["name"]["note"] == "Its channel #my-own-name was renamed on Discord."
    assert found["access"]["note"] == "#my-own-name was changed on Discord: @sts isn't let in."
    assert found["name"]["fix"] == found["access"]["fix"] == "fix"
    assert court.setup()["managed"]["checking"] is False
    assert len(staff_bell(court)) == 2
    # Checked again, the same problems tell no one again.
    court.troupe.storyteller.client.post(url)
    discord_channels.check_due(court.session)
    assert len(staff_bell(court)) == 2

    fixed = court.troupe.storyteller.client.post(
        f"/troupes/{court.troupe.id}/discord/characters/{court.agnes}/fix", json={"how": "fix"}
    )

    assert fixed.status_code == 200, fixed.text
    assert channel["name"] == "agnes-wren"
    assert rules(channel)[STS] == discord_channels.STAFF_ALLOW
    assert problems(court) == {}
    assert any(
        "asked Horatio to fix Agnès Wren" in m and "put its channel right" in m for m in court.log()
    )


def test_a_deleted_channel_is_made_again(court: Court, fake: FakeServer) -> None:
    channel = made_channel(court, fake)
    fake.channels.remove(channel)
    court.troupe.storyteller.client.post(f"/troupes/{court.troupe.id}/discord/check")
    discord_channels.check_due(court.session)
    assert problems(court)["deleted"]["fix"] == "remake"

    again = court.troupe.storyteller.client.post(
        f"/troupes/{court.troupe.id}/discord/characters/{court.agnes}/fix", json={"how": "remake"}
    ).json()

    assert again["status"] == "made"
    assert again["channel"] != channel["id"]
    assert court.settings()["channels"][court.agnes] == again["channel"]
    assert problems(court) == {}


def test_a_player_off_the_server_and_a_channel_no_longer_used(
    court: Court, fake: FakeServer
) -> None:
    made_channel(court, fake)
    del fake.members[PLAYER]
    saved = court.troupe.storyteller.client.put(
        f"/troupes/{court.troupe.id}/connectors/discord",
        json={"enabled": True, "settings": {"channels": {court.agnes: OPEN_CHANNEL}}},
    )
    assert saved.status_code == 200, saved.text
    court.troupe.storyteller.client.post(f"/troupes/{court.troupe.id}/discord/check")
    discord_channels.check_due(court.session)

    found = problems(court)
    assert (found["absent"]["fix"], found["unlinked"]["fix"]) == ("invite", "relink")
    fix = f"/troupes/{court.troupe.id}/discord/characters/{court.agnes}/fix"
    invited = court.troupe.storyteller.client.post(fix, json={"how": "invite"}).json()
    assert invited["status"] == "invited"
    assert len(fake.invites) == 1
    court.troupe.storyteller.client.post(fix, json={"how": "relink"})
    assert (
        court.settings()["channels"][court.agnes]
        == court.settings()["managed"]["made"][court.agnes]
    )


def test_channels_are_checked_once_a_day_unasked(court: Court, fake: FakeServer) -> None:
    made_channel(court, fake)
    start = discord_channels.now()

    assert discord_channels.check_due(court.session, start) == 1
    assert discord_channels.check_due(court.session, start + timedelta(hours=1)) == 0
    assert discord_channels.check_due(court.session, start + timedelta(hours=25)) == 1


def test_a_check_queues_what_horatio_should_have_changed(court: Court, fake: FakeServer) -> None:
    """A change no hook saw (a name changed straight in the database, say) is
    caught by the daily check and brought into step."""
    channel = made_channel(court, fake)
    agnes(court).name = "Agnès Ash"
    court.session.flush()

    discord_channels.check_due(court.session)
    assert court.settings()["managed"]["sync"] == [court.agnes]
    discord_channels.sync_due(court.session)

    assert channel["name"] == "agnes-ash"

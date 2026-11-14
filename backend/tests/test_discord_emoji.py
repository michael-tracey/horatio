"""The clan and discipline symbols as emoji on a troupe's Discord server (#870),
against a fake Discord and a folder of made-up symbols: switching it on, the
server's room, the troupe's own clans and disciplines, adding through the worker
in the order chosen, a server that fills up (counted, and as Discord says), Horatio's
own emoji as a fallback, a name someone else's emoji has, a style change, and
removing only what Horatio added."""

import base64
import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from horatio import discord_emoji, vtes_symbols
from horatio.config import get_settings
from horatio.connectors import discord
from tests.test_api_badges import give
from tests.test_api_sect_status import member as home_member
from tests.test_discord_channels import Court, FakeServer
from tests.test_discord_connector import GUILD

SYMBOLS = {
    "clan": ["brujah", "tremere", "ventrue"],
    "disc/sup": ["aus", "dom"],
    "disc/inf": ["aus", "dom"],
    "path": ["caine"],
}


class EmojiServer(FakeServer):
    """The fake Discord, with a server's emoji and boost level, and the app's own
    emoji."""

    def __init__(self) -> None:
        super().__init__()
        self.bot_role = discord.PERMISSIONS | discord.FOR_EMOJI
        self.tier = 0
        self.features: list[str] = []
        self.emoji: list[dict[str, Any]] = []
        self.own: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.uploads: list[tuple[str, int]] = []
        # Responses to give to the next emoji added instead: (status, body).
        self.refuse_adding: list[tuple[int, dict[str, Any]]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v10")
        if path == f"/guilds/{GUILD}" and request.method == "GET":
            found = super().handle(request).json()
            return httpx.Response(
                200, json={**found, "premium_tier": self.tier, "features": self.features}
            )
        if path == f"/guilds/{GUILD}/emojis" and request.method == "GET":
            return httpx.Response(200, json=self.emoji)
        if path == f"/guilds/{GUILD}/emojis" and request.method == "POST":
            if self.refuse_adding:
                code, body = self.refuse_adding.pop(0)
                return httpx.Response(code, json=body)
            body = json.loads(request.content)
            prefix = "data:image/png;base64,"
            assert body["image"].startswith(prefix)
            png = base64.b64decode(body["image"].removeprefix(prefix))
            with Image.open(io.BytesIO(png)) as picture:
                assert picture.size == (128, 128)
            self.uploads.append((body["name"], len(png)))
            made = {"id": str(5000 + len(self.uploads)), "name": body["name"], "animated": False}
            self.emoji.append(made)
            return httpx.Response(201, json=made)
        if path.startswith(f"/guilds/{GUILD}/emojis/") and request.method == "DELETE":
            emoji_id = path.rsplit("/", 1)[1]
            self.deleted.append(emoji_id)
            self.emoji = [e for e in self.emoji if e["id"] != emoji_id]
            return httpx.Response(204)
        if path == "/applications/app-id/emojis" and request.method == "GET":
            return httpx.Response(200, json={"items": self.own})
        if path == "/applications/app-id/emojis" and request.method == "POST":
            body = json.loads(request.content)
            made = {"id": str(7000 + len(self.own)), "name": body["name"], "animated": False}
            self.own.append(made)
            return httpx.Response(201, json=made)
        return super().handle(request)

    def fill(self, count: int, *, animated: bool = False) -> None:
        for n in range(count):
            self.emoji.append(
                {"id": str(100000 + len(self.emoji)), "name": f"theirs{n}", "animated": animated}
            )


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> EmojiServer:
    found = EmojiServer()
    settings = get_settings()
    monkeypatch.setattr(settings, "discord_client_id", "app-id")
    monkeypatch.setattr(settings, "discord_client_secret", "app-secret")
    monkeypatch.setattr(settings, "discord_bot_token", "test-token")
    monkeypatch.setattr(discord, "transport", httpx.MockTransport(found.handle))
    monkeypatch.setattr(discord, "sleep", found.waits.append)
    # A folder of made-up symbols, as a fetch since #869 leaves it: big, 16-bit
    # white-bordered PNGs, and plain ones.
    monkeypatch.setattr(settings, "dark_pack_dir", str(tmp_path))
    files: dict[str, list[str]] = {}
    for kind in ("png_wb", "png"):
        for group, names in SYMBOLS.items():
            folder = tmp_path / vtes_symbols.FOLDER / kind / group
            folder.mkdir(parents=True)
            for name in names:
                Image.new("RGBA", (1300, 1200), (255, 255, 255, 255)).save(folder / f"{name}.png")
            files[f"{kind}/{group}"] = names
    (tmp_path / vtes_symbols.FOLDER / "manifest.json").write_text(json.dumps({"files": files}))
    return found


@pytest.fixture
def court(client_for: Callable[[], TestClient], session: Session, server: EmojiServer) -> Court:
    return Court(client_for, session)


def setup(court: Court) -> dict[str, Any]:
    response = court.troupe.storyteller.client.get(f"/troupes/{court.troupe.id}/discord/emoji")
    assert response.status_code == 200, response.text
    return response.json()


def switch(court: Court, on: bool = True, style: str = "png_wb", own: bool = False) -> None:
    response = court.troupe.storyteller.client.put(
        f"/troupes/{court.troupe.id}/discord/emoji", json={"on": on, "style": style, "own": own}
    )
    assert response.status_code == 204, response.text


def push(court: Court, symbols: list[str], remove_others: bool = False) -> dict[str, Any]:
    response = court.troupe.storyteller.client.post(
        f"/troupes/{court.troupe.id}/discord/emoji/push",
        json={"symbols": symbols, "remove_others": remove_others},
    )
    assert response.status_code == 200, response.text
    return response.json()


def run(court: Court, rounds: int = 10) -> None:
    for _ in range(rounds):
        if not discord_emoji.push_due(court.session):
            break


def states(court: Court) -> dict[str, str]:
    return {s["key"]: s["status"] for s in setup(court)["symbols"] if s["status"]}


def test_switching_it_on_shows_the_room_and_the_symbols(court: Court, server: EmojiServer) -> None:
    server.fill(10)
    server.fill(3, animated=True)
    before = setup(court)
    assert (before["on"], before["style"], before["fetched"], before["lacks"]) == (
        False,
        "png_wb",
        True,
        [],
    )
    # Static emoji only count against a server's room: 50 at boost level 0.
    assert before["room"] == {"boost": 0, "room": 50, "used": 10}
    by_key = {s["key"]: s for s in before["symbols"]}
    assert (by_key["clan/tremere"]["label"], by_key["clan/tremere"]["name"]) == (
        "Tremere",
        "tremere",
    )
    assert by_key["disc/sup/aus"]["name"] == "aus_sup"
    assert by_key["disc/inf/aus"]["label"] == "Auspex (inferior)"
    assert by_key["path/caine"]["name"] == "path_caine"
    # Clans first, then superior and inferior disciplines, then paths.
    assert [s["group"] for s in before["symbols"]][:4] == ["clan", "clan", "clan", "disc/sup"]

    refused = court.troupe.assistant.client.put(
        f"/troupes/{court.troupe.id}/discord/emoji", json={"on": True}
    )
    assert refused.status_code == 403
    switch(court)
    assert setup(court)["on"] is True
    assert any("adding the clan and discipline symbols" in m for m in court.log())

    server.tier, server.features = 2, []
    assert setup(court)["room"]["room"] == 150
    server.tier, server.features = 0, ["MORE_EMOJI"]
    assert setup(court)["room"]["room"] == 200

    # Saving the connector as usual keeps it.
    saved = court.troupe.storyteller.client.put(
        f"/troupes/{court.troupe.id}/connectors/discord",
        json={"enabled": True, "settings": {"channels": {}, "test_channel": None}},
    )
    assert saved.status_code == 200, saved.text
    assert court.settings()["emoji"]["on"] is True


def test_the_bot_lacking_create_expressions_says_so(court: Court, server: EmojiServer) -> None:
    server.bot_role = discord.PERMISSIONS
    assert setup(court)["lacks"] == ["Create Expressions"]


def test_the_troupe_s_own_clans_and_disciplines(court: Court, server: EmojiServer) -> None:
    varga = home_member(court.troupe, "Varga", clan="Tremere")
    give(
        court.troupe,
        varga,
        ("disciplines", "Auspex", 5, ""),
        ("disciplines", "Dominate", 2, ""),
    )
    found = setup(court)
    assert found["clans"] == ["clan/tremere"]
    assert found["disciplines"] == ["disc/sup/aus", "disc/inf/dom"]


def test_pushing_adds_them_in_order_through_the_worker(court: Court, server: EmojiServer) -> None:
    switch(court)
    pushed = push(court, ["disc/sup/aus", "clan/brujah", "clan/brujah", "path/caine"])
    assert pushed == {"adding": 3, "removing": 0, "fits": 3}
    assert server.uploads == []
    assert states(court) == {k: "queued" for k in ("disc/sup/aus", "clan/brujah", "path/caine")}

    run(court)
    assert [name for name, _ in server.uploads] == ["aus_sup", "brujah", "path_caine"]
    # Each a 128 x 128 PNG within 256 KiB, however big the symbol.
    assert all(size <= discord_emoji.MOST_BYTES for _, size in server.uploads)
    after = setup(court)
    added = {s["key"]: s for s in after["symbols"] if s["added"]}
    assert set(added) == {"disc/sup/aus", "clan/brujah", "path/caine"}
    assert added["clan/brujah"]["note"] == "Added as :brujah:."
    assert after["queued"] == 0
    assert any(":aus_sup:, :brujah:, :path_caine:" in m for m in court.log())

    # Pushing the same again adds nothing.
    assert push(court, ["disc/sup/aus", "clan/brujah", "path/caine"])["adding"] == 0


def test_a_full_server_adds_what_fits_in_order(court: Court, server: EmojiServer) -> None:
    server.fill(48)
    switch(court)
    pushed = push(court, ["clan/brujah", "clan/tremere", "clan/ventrue", "path/caine"])
    assert pushed == {"adding": 4, "removing": 0, "fits": 2}
    run(court)
    assert [name for name, _ in server.uploads] == ["brujah", "tremere"]
    found = states(court)
    assert found["clan/ventrue"] == found["path/caine"] == "no_room"


def test_discord_saying_the_server_is_full_stops_adding(court: Court, server: EmojiServer) -> None:
    switch(court)
    push(court, ["clan/brujah", "clan/tremere", "clan/ventrue"])
    # Someone filled the server meanwhile: Discord refuses the second.
    original = server.handle
    added = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v10")
        if path == f"/guilds/{GUILD}/emojis" and request.method == "POST":
            added["n"] += 1
            if added["n"] >= 2:
                return httpx.Response(
                    400, json={"message": "Maximum number of emojis reached (50)", "code": 30008}
                )
        return original(request)

    discord.transport = httpx.MockTransport(handle)
    run(court)
    found = states(court)
    assert found["clan/brujah"] == "added"
    assert found["clan/tremere"] == found["clan/ventrue"] == "no_room"


def test_horatio_s_own_emoji_take_what_doesn_t_fit(court: Court, server: EmojiServer) -> None:
    server.fill(50)
    server.own.append({"id": "7999", "name": "brujah_wb", "animated": False})
    switch(court, own=True)
    push(court, ["clan/brujah", "clan/tremere"])
    run(court)
    assert server.uploads == []
    # One another troupe made already is used again; the other is made.
    assert [e["name"] for e in server.own] == ["brujah_wb", "tremere_wb"]
    after = {s["key"]: s for s in setup(court)["symbols"]}
    assert after["clan/brujah"]["added"] == after["clan/tremere"]["added"] == "own"

    # Removing them only forgets them: they're shared, and never deleted.
    push(court, [], remove_others=True)
    run(court)
    assert server.deleted == []
    assert [e["name"] for e in server.own] == ["brujah_wb", "tremere_wb"]


def test_a_name_someone_else_s_emoji_has_is_left_alone(court: Court, server: EmojiServer) -> None:
    server.emoji.append({"id": "42", "name": "brujah", "animated": False})
    switch(court)
    push(court, ["clan/brujah", "clan/tremere"])
    run(court)
    assert [name for name, _ in server.uploads] == ["tremere"]
    assert states(court)["clan/brujah"] == "name_taken"


def test_a_new_style_replaces_them_and_only_horatio_s_are_removed(
    court: Court, server: EmojiServer
) -> None:
    server.emoji.append({"id": "42", "name": "theirs", "animated": False})
    switch(court)
    push(court, ["clan/brujah", "clan/tremere"])
    run(court)
    made = {e["name"]: e["id"] for e in server.emoji}

    switch(court, style="png")
    after = setup(court)
    assert {s["key"] for s in after["symbols"] if s["other_style"]} == {
        "clan/brujah",
        "clan/tremere",
    }
    # Keep Brujah, drop Tremere: Brujah is made again in the plain style.
    assert push(court, ["clan/brujah"], remove_others=True) == {
        "adding": 1,
        "removing": 2,
        "fits": 1,
    }
    run(court)
    assert sorted(server.deleted) == sorted([made["brujah"], made["tremere"]])
    assert "42" not in server.deleted
    assert [e["name"] for e in server.emoji] == ["theirs", "brujah"]
    assert court.settings()["emoji"]["made"]["clan/brujah"]["style"] == "png"
    assert any("remove :brujah:, :tremere:" in m for m in court.log())


def test_pushing_needs_it_switched_on_and_fetched_symbols(
    court: Court, server: EmojiServer
) -> None:
    client = court.troupe.storyteller.client
    url = f"/troupes/{court.troupe.id}/discord/emoji/push"
    assert client.post(url, json={"symbols": ["clan/brujah"]}).status_code == 409
    switch(court)
    assert client.post(url, json={"symbols": ["clan/nobody"]}).status_code == 422


def test_switching_it_off_stops_what_is_queued(court: Court, server: EmojiServer) -> None:
    switch(court)
    push(court, ["clan/brujah"])
    switch(court, on=False)
    run(court)
    assert server.uploads == []
    assert court.settings()["emoji"]["queue"] == []


def test_discord_asking_to_slow_down_waits(court: Court, server: EmojiServer) -> None:
    switch(court)
    push(court, ["clan/brujah"])
    server.refuse_adding = [(429, {"retry_after": 120, "message": "slow down"})]
    run(court)
    waiting = court.settings()["emoji"]
    assert waiting["queue"] and waiting["next_at"]
    assert states(court)["clan/brujah"] == "queued"


def test_emoji_names_follow_discord_s_rules() -> None:
    assert discord_emoji.emoji_name("clan", "daughtersofcacophony") == "daughtersofcacophony"
    assert discord_emoji.emoji_name("disc/sup", "aus") == "aus_sup"
    assert discord_emoji.emoji_name("path", "caine") == "path_caine"
    assert discord_emoji.emoji_name("clan", "a-b") == "a_b"
    assert len(discord_emoji.emoji_name("clan", "x" * 40)) == 32


def test_room_by_boost_level() -> None:
    def room(tier: int, *features: str) -> int:
        return discord_emoji.room(discord.EmojiRoom(premium_tier=tier, features=features, emoji=[]))

    assert [room(t) for t in range(4)] == [50, 100, 150, 250]
    assert room(0, "MORE_EMOJI") == 200
    assert room(3, "MORE_EMOJI") == 250

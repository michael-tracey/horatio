"""Posting to Discord under another name and picture through a channel's webhook
(#883, horatio.discord_webhooks), and the signed addresses Discord fetches those
pictures from (horatio.public_pictures), against the fake Discord."""

import io
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import discord_webhooks, public_pictures
from horatio.config import get_settings
from horatio.connectors import SendError, discord
from horatio.models import DiscordWebhook
from tests import test_discord_connector
from tests.api_helpers import Troupe, new_character
from tests.test_discord_connector import OPEN_CHANNEL, TEST_CHANNEL, FakeDiscord, connect_server

fake_discord = test_discord_connector.fake_discord

EMBED = {"embeds": [{"title": "Fire at the docks"}]}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def troupe_id(troupe: Troupe) -> uuid.UUID:
    return uuid.UUID(troupe.id)


def hooks(session: Session) -> list[tuple[str, str]]:
    return [
        (h.channel, h.webhook_id)
        for h in session.scalars(select(DiscordWebhook).order_by(DiscordWebhook.channel))
    ]


# --- sending, editing and deleting ---------------------------------------------------------


def test_a_message_goes_under_its_own_name_and_picture_through_one_webhook(
    troupe: Troupe, session: Session, fake_discord: FakeDiscord
) -> None:
    first = discord_webhooks.send_as(
        session,
        troupe_id(troupe),
        OPEN_CHANNEL,
        name="The Boston Herald",
        avatar_url="https://horatio.example/herald.webp",
        payload=EMBED,
    )
    second = discord_webhooks.send_as(
        session, troupe_id(troupe), OPEN_CHANNEL, name="Agnes", avatar_url=None, payload=EMBED
    )

    sent = fake_discord.messages[first]
    assert sent.channel == OPEN_CHANNEL
    assert sent.payload["username"] == "The Boston Herald"
    assert sent.payload["avatar_url"] == "https://horatio.example/herald.webp"
    assert sent.payload["embeds"] == EMBED["embeds"]
    # Without a picture, Discord shows its default one.
    assert "avatar_url" not in fake_discord.messages[second].payload
    # One webhook for the channel, made once and kept.
    assert list(fake_discord.webhooks) == ["9001"]
    assert fake_discord.webhooks["9001"]["name"] == "Horatio"
    assert hooks(session) == [(OPEN_CHANNEL, "9001")]

    discord_webhooks.send_as(
        session, troupe_id(troupe), TEST_CHANNEL, name="Agnes", avatar_url=None, payload=EMBED
    )
    assert hooks(session) == [(OPEN_CHANNEL, "9001"), (TEST_CHANNEL, "9002")]


def test_a_webhook_horatio_made_before_is_used_again(
    troupe: Troupe, session: Session, fake_discord: FakeDiscord
) -> None:
    fake_discord.webhooks["9500"] = {
        "id": "9500",
        "type": 1,
        "token": "kept",
        "channel_id": OPEN_CHANNEL,
        "name": "Horatio",
        "application_id": "app-id",
    }
    # Someone else's webhook in the channel is left alone.
    fake_discord.webhooks["9600"] = {
        "id": "9600",
        "type": 1,
        "token": "theirs",
        "channel_id": OPEN_CHANNEL,
        "name": "Horatio",
        "application_id": "another-app",
    }

    sent = discord_webhooks.send_as(
        session, troupe_id(troupe), OPEN_CHANNEL, name="Agnes", avatar_url=None, payload=EMBED
    )

    assert fake_discord.messages[sent].webhook == "9500"
    assert len(fake_discord.webhooks) == 2


def test_a_webhook_deleted_on_discord_is_made_again(
    troupe: Troupe, session: Session, fake_discord: FakeDiscord
) -> None:
    old = discord_webhooks.send_as(
        session, troupe_id(troupe), OPEN_CHANNEL, name="Agnes", avatar_url=None, payload=EMBED
    )
    del fake_discord.webhooks["9001"]

    new = discord_webhooks.send_as(
        session, troupe_id(troupe), OPEN_CHANNEL, name="Agnes", avatar_url=None, payload=EMBED
    )

    assert fake_discord.messages[new].webhook == "9002"
    assert hooks(session) == [(OPEN_CHANNEL, "9002")]
    # Its old messages can't be changed now: an edit says so, and a deletion is done.
    with pytest.raises(SendError) as failed:
        discord_webhooks.edit_as(session, troupe_id(troupe), OPEN_CHANNEL, old, payload=EMBED)
    assert failed.value.status == 404
    discord_webhooks.delete_as(session, troupe_id(troupe), OPEN_CHANNEL, old)


def test_messages_are_edited_and_deleted_through_the_webhook(
    troupe: Troupe, session: Session, fake_discord: FakeDiscord
) -> None:
    sent = discord_webhooks.send_as(
        session,
        troupe_id(troupe),
        OPEN_CHANNEL,
        name="The Boston Herald",
        avatar_url=None,
        payload=EMBED,
    )

    discord_webhooks.edit_as(
        session,
        troupe_id(troupe),
        OPEN_CHANNEL,
        sent,
        payload={"embeds": [{"title": "Fire out at the docks"}]},
    )

    assert fake_discord.edits == [sent]
    assert fake_discord.messages[sent].payload["embeds"][0]["title"] == "Fire out at the docks"

    discord_webhooks.delete_as(session, troupe_id(troupe), OPEN_CHANNEL, sent)
    assert fake_discord.deletions == [sent]
    # Gone already: no failure.
    discord_webhooks.delete_as(session, troupe_id(troupe), OPEN_CHANNEL, sent)
    with pytest.raises(SendError) as failed:
        discord_webhooks.edit_as(session, troupe_id(troupe), OPEN_CHANNEL, sent, payload=EMBED)
    assert failed.value.status == 404


def test_without_manage_webhooks_nothing_is_sent_and_the_error_names_it(
    troupe: Troupe, session: Session, fake_discord: FakeDiscord
) -> None:
    fake_discord.bot_role = discord.PERMISSIONS

    with pytest.raises(SendError) as failed:
        discord_webhooks.send_as(
            session, troupe_id(troupe), OPEN_CHANNEL, name="Agnes", avatar_url=None, payload=EMBED
        )

    assert failed.value.status == 403
    assert failed.value.reason == (
        "The Horatio bot needs Manage Webhooks in that channel. "
        "Give it that permission in the channel's settings on Discord."
    )
    assert fake_discord.messages == {}
    assert hooks(session) == []

    # Even when Discord won't say what the bot lacks.
    fake_discord.answers_about_bot = False
    with pytest.raises(SendError) as failed:
        discord_webhooks.send_as(
            session, troupe_id(troupe), OPEN_CHANNEL, name="Agnes", avatar_url=None, payload=EMBED
        )
    assert "Manage Webhooks" in failed.value.reason


def test_a_failure_worth_retrying_says_so(
    troupe: Troupe, session: Session, fake_discord: FakeDiscord
) -> None:
    discord_webhooks.send_as(
        session, troupe_id(troupe), OPEN_CHANNEL, name="Agnes", avatar_url=None, payload=EMBED
    )
    fake_discord.next = [(503, {})]

    with pytest.raises(SendError) as failed:
        discord_webhooks.send_as(
            session, troupe_id(troupe), OPEN_CHANNEL, name="Agnes", avatar_url=None, payload=EMBED
        )

    assert failed.value.retry is True


def test_a_senders_name_is_one_discord_takes() -> None:
    assert discord_webhooks.sender_name("The  Boston\nHerald") == "The Boston Herald"
    assert discord_webhooks.sender_name("x" * 100) == "x" * 80
    assert discord_webhooks.sender_name("The Discord Daily") == "The D​iscord Daily"
    assert discord_webhooks.sender_name("CLYDE and clyde") == "C​LYDE and c​lyde"
    assert discord_webhooks.sender_name("  ") == "Horatio"


def test_disconnecting_forgets_the_troupes_webhooks(
    troupe: Troupe, session: Session, fake_discord: FakeDiscord
) -> None:
    class Ready:
        pass

    Ready.troupe = troupe  # type: ignore[attr-defined]
    assert connect_server(Ready()).status_code == 303  # type: ignore[arg-type]
    discord_webhooks.send_as(
        session, troupe_id(troupe), OPEN_CHANNEL, name="Agnes", avatar_url=None, payload=EMBED
    )

    assert troupe.storyteller.client.delete(f"/troupes/{troupe.id}/discord").status_code == 204

    assert hooks(session) == []


# --- public pictures -----------------------------------------------------------------------


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


def png(width: int = 900, height: int = 600) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (40, 60, 120)).save(out, "PNG")
    return out.getvalue()


def opened(troupe: Troupe, url: str) -> tuple[int, bytes]:
    """The address as Discord fetches it: signed in as nobody."""
    path = url.removeprefix("http://localhost:5173/api")
    response = troupe.client_for().get(path)
    return response.status_code, response.content


def test_an_agencys_portrait_has_a_signed_address_anyone_may_open(
    troupe: Troupe, session: Session, fake_discord: FakeDiscord, kept: Path
) -> None:
    made = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/agencies", json={"name": "The Boston Herald"}
    )
    agency = made.json()["id"]
    added = troupe.storyteller.client.post(
        f"/agencies/{agency}/portrait",
        files={"file": ("p.png", png(), "image/png")},
        data={"crop_x": "0.1", "crop_y": "0", "crop_size": "0.5"},
    )
    assert added.status_code == 200, added.text
    portrait = added.json()["portrait"]
    portrait_id = uuid.UUID(portrait.rsplit("/", 1)[1])
    assert added.json()["portrait_crop"] == {"x": 0.1, "y": 0.0, "size": 0.5}

    url = public_pictures.avatar_url("agency", uuid.UUID(agency), portrait_id)

    assert url.startswith(f"http://localhost:5173/api/public-pictures/agency/{agency}/")
    status, data = opened(troupe, url)
    assert status == 200
    with Image.open(io.BytesIO(data)) as image:
        assert (image.format, image.size) == ("WEBP", (128, 128))

    # A made-up signature, another kind, or another owner opens nothing.
    assert opened(troupe, url[:-10] + "0000000000")[0] == 404
    assert opened(troupe, url.replace("/agency/", "/troupe/"))[0] == 404
    other = public_pictures.avatar_url("character", uuid.UUID(agency), portrait_id)
    assert opened(troupe, other)[0] == 404

    # A new portrait has a new address; the old one stops working.
    troupe.storyteller.client.post(
        f"/agencies/{agency}/portrait", files={"file": ("p.png", png(), "image/png")}
    )
    assert opened(troupe, url)[0] == 404


def test_a_characters_picture_has_one_too(
    troupe: Troupe, session: Session, fake_discord: FakeDiscord, kept: Path
) -> None:
    character = new_character(troupe, troupe.player, "Agnes")
    added = troupe.player.client.post(
        f"/characters/{character}/picture", files={"file": ("p.png", png(), "image/png")}
    )
    assert added.status_code == 200, added.text
    picture_id = uuid.UUID(added.json()["picture"].rsplit("/", 1)[1])

    url = public_pictures.avatar_url("character", uuid.UUID(character), picture_id)

    assert opened(troupe, url)[0] == 200
    troupe.player.client.delete(f"/characters/{character}/picture")
    assert opened(troupe, url)[0] == 404


def test_without_the_discord_apps_secret_no_address_works(
    troupe: Troupe, session: Session, monkeypatch: pytest.MonkeyPatch, kept: Path
) -> None:
    monkeypatch.setattr(get_settings(), "discord_client_secret", None)

    with pytest.raises(RuntimeError):
        public_pictures.avatar_url("agency", uuid.uuid4(), uuid.uuid4())
    assert public_pictures.picture_file(session, "agency", uuid.uuid4(), uuid.uuid4(), "x") is None

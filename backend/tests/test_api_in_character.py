"""Posting as an NPC in the troupe's In-Character channel on Discord (issue #884):
choosing the channel, then posting, editing and deleting from the NPC's page, who
may, and that players never learn who spoke as an NPC. The webhooks
(horatio.discord_webhooks) and public pictures (horatio.public_pictures) are faked
here; the fake Discord (tests.test_discord_connector) stands in for the server."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import discord_webhooks, public_pictures
from horatio.connectors import SendError
from horatio.models import Character
from tests import test_discord_connector
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_npc_gifts import built, given
from tests.test_api_renames import character_log
from tests.test_discord_connector import OPEN_CHANNEL, TEST_CHANNEL, FakeDiscord, connect_server

fake_discord = test_discord_connector.fake_discord


@dataclass
class Sent:
    channel: str
    name: str
    avatar_url: str | None
    payload: dict[str, Any]


@dataclass
class FakeWebhooks:
    """What went through the channel's webhook: sent, edited and deleted, by message id."""

    sent: dict[str, Sent] = field(default_factory=dict)
    edits: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    deletions: list[tuple[str, str]] = field(default_factory=list)
    # A refusal to raise on the next call.
    refuse: SendError | None = None

    def check(self) -> None:
        if self.refuse is not None:
            error, self.refuse = self.refuse, None
            raise error

    def send_as(
        self,
        db: Session,
        troupe_id: uuid.UUID,
        channel: str,
        *,
        name: str,
        avatar_url: str | None,
        payload: dict[str, Any],
        files: Any = (),
    ) -> str:
        self.check()
        message_id = str(900 + len(self.sent))
        self.sent[message_id] = Sent(channel, name, avatar_url, dict(payload))
        return message_id

    def edit_as(
        self,
        db: Session,
        troupe_id: uuid.UUID,
        channel: str,
        message_id: str,
        *,
        payload: dict[str, Any],
    ) -> None:
        self.check()
        self.edits.append((channel, message_id, dict(payload)))

    def delete_as(self, db: Session, troupe_id: uuid.UUID, channel: str, message_id: str) -> None:
        self.check()
        self.deletions.append((channel, message_id))


@pytest.fixture
def webhooks(monkeypatch: pytest.MonkeyPatch) -> FakeWebhooks:
    fake = FakeWebhooks()
    monkeypatch.setattr(discord_webhooks, "send_as", fake.send_as)
    monkeypatch.setattr(discord_webhooks, "edit_as", fake.edit_as)
    monkeypatch.setattr(discord_webhooks, "delete_as", fake.delete_as)
    monkeypatch.setattr(
        public_pictures,
        "avatar_url",
        lambda kind, owner, picture: f"https://horatio.test/public/{kind}/{owner}/{picture}",
    )
    return fake


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def channel_of(person: Person, troupe: Troupe) -> Any:
    return person.client.get(f"/troupes/{troupe.id}/in-character-channel")


def choose(person: Person, troupe: Troupe, channel: str | None) -> Any:
    return person.client.put(
        f"/troupes/{troupe.id}/in-character-channel", json={"channel": channel}
    )


def ready(troupe: Troupe) -> None:
    """Connect the fake server and choose its open channel as the In-Character one."""

    class Scene:
        pass

    scene = Scene()
    scene.troupe = troupe  # type: ignore[attr-defined]
    assert connect_server(scene).status_code == 303  # type: ignore[arg-type]
    chosen = choose(troupe.storyteller, troupe, OPEN_CHANNEL)
    assert chosen.status_code == 200, chosen.text


def post(person: Person, npc_id: str, text: str = "The Prince will see you now.") -> Any:
    return person.client.post(f"/characters/{npc_id}/in-character", json={"text": text})


def listed(person: Person, npc_id: str) -> Any:
    return person.client.get(f"/characters/{npc_id}/in-character")


# --- the channel ---------------------------------------------------------------------------


def test_storytellers_choose_the_in_character_channel_and_it_survives_saving(
    troupe: Troupe, fake_discord: FakeDiscord
) -> None:
    ready(troupe)
    seen = channel_of(troupe.assistant, troupe)
    assert seen.status_code == 200, seen.text
    assert (seen.json()["server"], seen.json()["channel"], seen.json()["can_change"]) == (
        "Court of Ash",
        OPEN_CHANNEL,
        False,
    )
    assert choose(troupe.assistant, troupe, TEST_CHANNEL).status_code == 403
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert channel_of(person, troupe).status_code == 403, person.email
        assert choose(person, troupe, TEST_CHANNEL).status_code == 403, person.email
    assert choose(troupe.storyteller, troupe, "300").status_code == 422

    # Saving the connector keeps it, as it does the news channel.
    saved = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/connectors/discord",
        json={"enabled": True, "mode": "full", "settings": {"test_channel": TEST_CHANNEL}},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["settings"]["in_character_channel"] == OPEN_CHANNEL

    cleared = choose(troupe.storyteller, troupe, None)
    assert cleared.json()["channel"] is None
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller changed the troupe's Discord In-Character channel (cleared)." in log


def test_without_a_channel_an_npc_cannot_post_and_says_why(
    troupe: Troupe, fake_discord: FakeDiscord, webhooks: FakeWebhooks
) -> None:
    npc = built(troupe, "Lucien")
    shown = listed(troupe.storyteller, npc).json()
    assert (shown["unavailable"], shown["needs_channel"]) == (
        "No Discord server is connected.",
        True,
    )
    assert (shown["messages"], shown["can_choose_channel"]) == ([], True)
    assert listed(troupe.assistant, npc).json()["can_choose_channel"] is False

    ready(troupe)
    choose(troupe.storyteller, troupe, None)
    assert listed(troupe.storyteller, npc).json()["unavailable"] == (
        "No In-Character channel is chosen."
    )
    refused = post(troupe.storyteller, npc)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "No In-Character channel is chosen."
    assert webhooks.sent == {}


# --- posting ------------------------------------------------------------------------------


def test_staff_post_as_the_npc_under_its_name_and_picture(
    troupe: Troupe, session: Session, fake_discord: FakeDiscord, webhooks: FakeWebhooks
) -> None:
    ready(troupe)
    npc = built(troupe, "Lucien")
    picture = uuid.uuid4()
    session.get_one(Character, uuid.UUID(npc)).picture_id = picture
    session.flush()

    made = post(troupe.assistant, npc, "  The Prince will see you now. @everyone  ")

    assert made.status_code == 201, made.text
    [(message_id, sent)] = webhooks.sent.items()
    assert sent.channel == OPEN_CHANNEL
    assert sent.name == "Lucien"
    assert sent.avatar_url == f"https://horatio.test/public/character/{npc}/{picture}"
    assert sent.payload == {
        "content": "The Prince will see you now. @everyone",
        "allowed_mentions": {"parse": []},
    }
    shown = listed(troupe.storyteller, npc).json()
    assert shown["unavailable"] is None
    assert shown["channel_link"] == f"https://discord.com/channels/111/{OPEN_CHANNEL}"
    [message] = shown["messages"]
    assert (message["body"], message["sent_by"], message["edited_at"]) == (
        "The Prince will see you now. @everyone",
        "assistant",
        None,
    )
    assert message["link"] == f"https://discord.com/channels/111/{OPEN_CHANNEL}/{message_id}"
    assert (
        "assistant posted in IC chat as Lucien: “The Prince will see you now. @everyone”"
        in character_log(troupe.storyteller, npc)
    )


def test_an_npc_without_a_picture_posts_with_discords_own(
    troupe: Troupe, fake_discord: FakeDiscord, webhooks: FakeWebhooks
) -> None:
    ready(troupe)
    npc = built(troupe, "Lucien")
    assert post(troupe.storyteller, npc).status_code == 201
    [sent] = webhooks.sent.values()
    assert sent.avatar_url is None


def test_narrators_and_players_cannot_post_or_see_the_messages(
    troupe: Troupe, fake_discord: FakeDiscord, webhooks: FakeWebhooks
) -> None:
    ready(troupe)
    npc = built(troupe, "Lucien")
    assert post(troupe.storyteller, npc).status_code == 201
    [message] = listed(troupe.storyteller, npc).json()["messages"]

    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert post(person, npc).status_code == 404, person.email
        assert listed(person, npc).status_code == 404, person.email
        edit = person.client.put(f"/in-character-messages/{message['id']}", json={"text": "Hm."})
        assert edit.status_code == 404, person.email
        gone = person.client.delete(f"/in-character-messages/{message['id']}")
        assert gone.status_code == 404, person.email
    assert len(webhooks.sent) == 1
    assert (webhooks.edits, webhooks.deletions) == ([], [])


def test_a_player_character_has_no_in_character_posting(
    troupe: Troupe, fake_discord: FakeDiscord, webhooks: FakeWebhooks
) -> None:
    from tests.api_helpers import new_character
    from tests.test_api_characters import join

    ready(troupe)
    agnes = new_character(troupe, troupe.player, "Agnes")
    join(troupe.session, troupe, agnes)
    assert post(troupe.storyteller, agnes).status_code == 404
    assert post(troupe.player, agnes).status_code == 404
    assert webhooks.sent == {}


def test_a_retired_npc_cannot_post(
    troupe: Troupe, fake_discord: FakeDiscord, webhooks: FakeWebhooks
) -> None:
    ready(troupe)
    npc = built(troupe, "Lucien")
    retired = troupe.storyteller.client.post(f"/characters/{npc}/retire")
    assert retired.status_code == 200, retired.text
    refused = post(troupe.storyteller, npc)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Lucien is retired, so can't post."


def test_too_long_or_empty_is_refused(
    troupe: Troupe, fake_discord: FakeDiscord, webhooks: FakeWebhooks
) -> None:
    ready(troupe)
    npc = built(troupe, "Lucien")
    assert post(troupe.storyteller, npc, "x" * 2001).status_code == 422
    assert post(troupe.storyteller, npc, "   ").status_code == 422
    assert post(troupe.storyteller, npc, "x" * 2000).status_code == 201


def test_a_refusal_from_discord_is_shown_and_nothing_is_kept(
    troupe: Troupe, fake_discord: FakeDiscord, webhooks: FakeWebhooks
) -> None:
    ready(troupe)
    npc = built(troupe, "Lucien")
    webhooks.refuse = SendError(
        "The Horatio bot lacks Manage Webhooks in #general.", retry=False, status=403
    )
    refused = post(troupe.storyteller, npc)
    assert refused.status_code == 502
    assert refused.json()["detail"] == "The Horatio bot lacks Manage Webhooks in #general."
    assert listed(troupe.storyteller, npc).json()["messages"] == []


# --- editing and deleting -----------------------------------------------------------------


def test_editing_and_deleting_reach_discord(
    troupe: Troupe, fake_discord: FakeDiscord, webhooks: FakeWebhooks
) -> None:
    ready(troupe)
    npc = built(troupe, "Lucien")
    assert post(troupe.storyteller, npc, "Welcome to Elysium.").status_code == 201
    [message_id] = webhooks.sent
    [message] = listed(troupe.storyteller, npc).json()["messages"]

    # The channel changing afterwards doesn't move it: it is edited where it is.
    choose(troupe.storyteller, troupe, TEST_CHANNEL)
    edited = troupe.assistant.client.put(
        f"/in-character-messages/{message['id']}", json={"text": "Welcome, all, to Elysium."}
    )
    assert edited.status_code == 200, edited.text
    assert (edited.json()["body"], edited.json()["edited_by"]) == (
        "Welcome, all, to Elysium.",
        "assistant",
    )
    assert edited.json()["sent_by"] == "storyteller"
    assert webhooks.edits == [
        (
            OPEN_CHANNEL,
            message_id,
            {"content": "Welcome, all, to Elysium.", "allowed_mentions": {"parse": []}},
        )
    ]

    # A refusal leaves it as it was.
    webhooks.refuse = SendError("Discord is having trouble (503).", retry=True)
    failed = troupe.storyteller.client.delete(f"/in-character-messages/{message['id']}")
    assert failed.status_code == 502
    assert len(listed(troupe.storyteller, npc).json()["messages"]) == 1

    deleted = troupe.storyteller.client.delete(f"/in-character-messages/{message['id']}")
    assert deleted.status_code == 204
    assert webhooks.deletions == [(OPEN_CHANNEL, message_id)]
    assert listed(troupe.storyteller, npc).json()["messages"] == []
    log = character_log(troupe.storyteller, npc)
    assert "assistant edited a message Lucien posted in IC chat: “Welcome, all, to Elysium.”" in log
    assert (
        "storyteller deleted a message Lucien posted in IC chat: “Welcome, all, to Elysium.”"
        in (log)
    )


# --- players never learn who spoke as an NPC ----------------------------------------------


def test_players_never_see_who_spoke_as_an_npc(
    troupe: Troupe,
    client_for: Callable[[], TestClient],
    fake_discord: FakeDiscord,
    webhooks: FakeWebhooks,
) -> None:
    ready(troupe)
    npc = built(troupe, "Lucien")
    assert post(troupe.assistant, npc, "Elysium is closed tonight.").status_code == 201

    # On Discord it is Lucien talking: nothing names the assistant who sent it.
    [sent] = webhooks.sent.values()
    assert "assistant" not in repr(sent)

    # Given to a player later, it is theirs, but who spoke as it stays hidden: they
    # can't list its messages, and its log leaves them out.
    heir = sign_up(client_for, "heir")
    given(troupe.storyteller, npc, heir)
    assert listed(heir, npc).status_code == 404
    assert not [line for line in character_log(heir, npc) if "IC chat" in line]
    # Its troupe's staff still see them in the log.
    assert any("IC chat" in line for line in character_log(troupe.storyteller, npc))

"""Troupe news (issue #510): agencies, stories written, scheduled, published,
edited, unpublished and duplicated; who sees what, the narrator's proposals, unread
dots, the bell and email, and stories on Discord through the fake Discord."""

import io
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import delivery, posts, public_pictures
from horatio.config import get_settings
from horatio.connectors import discord
from horatio.models import Delivery, EmailNotice, Notification, Post
from tests import test_discord_connector
from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_characters import join
from tests.test_discord_connector import GUILD, OPEN_CHANNEL, TEST_CHANNEL, FakeDiscord
from tests.test_email_connector import FakeSMTP

# The fake Discord (tests.test_discord_connector), for the tests here that use it.
fake_discord = test_discord_connector.fake_discord

# The tests' clock: a day after the real one, so what is queued now is due by then.
START = (datetime.now(UTC) + timedelta(days=1)).replace(second=0, microsecond=0)


class News:
    """A troupe with a player at home in it, and an agency."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.agnes = new_character(troupe, troupe.player, "Agnes")
        join(troupe.session, troupe, self.agnes)
        self.agency = self.new_agency("The Boston Herald")

    def new_agency(self, name: str, **more: Any) -> str:
        made = self.troupe.storyteller.client.post(
            f"/troupes/{self.troupe.id}/agencies", json={"name": name, **more}
        )
        assert made.status_code == 201, made.text
        return made.json()["id"]

    def write(self, person: Person | None = None, **more: Any) -> Any:
        body = {"agency_id": self.agency, "title": "Fire at the docks", "body": "Smoke.", **more}
        return (person or self.troupe.storyteller).client.post(
            f"/troupes/{self.troupe.id}/posts", json=body
        )

    def draft(self, **more: Any) -> str:
        made = self.write(**more)
        assert made.status_code == 201, made.text
        return made.json()["id"]

    def published(self, **more: Any) -> str:
        post = self.draft(**more)
        done = self.troupe.storyteller.client.post(f"/posts/{post}/publish", json={})
        assert done.status_code == 200, done.text
        return post

    def read(self, person: Person) -> list[str]:
        page = person.client.get(f"/troupes/{self.troupe.id}/posts")
        assert page.status_code == 200, page.text
        return [p["title"] for p in page.json()["posts"]]

    def glance(self, person: Person) -> Any:
        found = person.client.get(f"/troupes/{self.troupe.id}/posts/glance")
        assert found.status_code == 200, found.text
        return found.json()

    def log(self) -> list[str]:
        entries = self.troupe.lead.client.get(f"/troupes/{self.troupe.id}/log").json()
        return [e["message"] for e in entries]


@pytest.fixture
def news(client_for: Callable[[], TestClient], session: Session) -> News:
    return News(Troupe(client_for, session))


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[datetime]]:
    at = [START]
    monkeypatch.setattr(delivery, "now", lambda: at[0])
    yield at


def bell(session: Session, person: Person) -> list[str]:
    return list(
        session.scalars(
            select(Notification.summary)
            .where(Notification.user_id == uuid.UUID(person.id))
            .order_by(Notification.created_at, Notification.id)
        )
    )


# --- agencies ------------------------------------------------------------------------------


def test_storytellers_and_assistants_keep_the_agencies(news: News) -> None:
    troupe = news.troupe
    made = troupe.assistant.client.post(
        f"/troupes/{troupe.id}/agencies",
        json={"name": "WKBN Nightly", "description": "TV news", "colour": "#204080"},
    )
    assert made.status_code == 201, made.text
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        refused = person.client.post(f"/troupes/{troupe.id}/agencies", json={"name": "Mine"})
        assert refused.status_code == 403, person.email
    # Two agencies can't share a name.
    clash = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/agencies", json={"name": "WKBN Nightly"}
    )
    assert clash.status_code == 409

    # Members see them all, for mastheads and the filter; strangers nothing.
    listed = troupe.player.client.get(f"/troupes/{troupe.id}/agencies").json()
    assert [(a["name"], a["colour"]) for a in listed] == [
        ("The Boston Herald", "#8b1e1e"),
        ("WKBN Nightly", "#204080"),
    ]
    assert troupe.stranger.client.get(f"/troupes/{troupe.id}/agencies").status_code == 404
    assert "assistant made the news agency WKBN Nightly." in news.log()


def test_a_retired_agency_takes_no_new_stories_and_keeps_its_old_ones(news: News) -> None:
    troupe = news.troupe
    old = news.published()
    retired = troupe.storyteller.client.post(f"/agencies/{news.agency}/retire")
    assert retired.json()["retired"] is True

    assert news.write().status_code == 422
    assert news.read(troupe.player) == ["Fire at the docks"]
    # A story it already had can still be edited.
    edited = troupe.storyteller.client.put(
        f"/posts/{old}", json={"agency_id": news.agency, "title": "Fire out at the docks"}
    )
    assert edited.status_code == 200, edited.text

    troupe.storyteller.client.post(f"/agencies/{news.agency}/restore")
    assert news.write().status_code == 201
    assert "storyteller retired the news agency The Boston Herald." in news.log()


def test_only_storytellers_give_an_agency_its_own_channel(news: News) -> None:
    troupe = news.troupe
    refused = troupe.assistant.client.put(
        f"/agencies/{news.agency}",
        json={"name": "The Boston Herald", "discord_channel": OPEN_CHANNEL},
    )
    assert refused.status_code == 403
    # Not without a server.
    no_server = troupe.storyteller.client.put(
        f"/agencies/{news.agency}",
        json={"name": "The Boston Herald", "discord_channel": OPEN_CHANNEL},
    )
    assert no_server.status_code == 409


# --- writing and publishing ----------------------------------------------------------------


def test_a_draft_is_for_staff_and_a_published_story_for_everyone(
    news: News, session: Session
) -> None:
    troupe = news.troupe
    post = news.draft(dateline="Boston, 3 November")

    assert news.read(troupe.player) == []
    assert troupe.player.client.get(f"/posts/{post}").status_code == 404
    assert troupe.narrator.client.get(f"/posts/{post}").status_code == 404
    desk = troupe.assistant.client.get(f"/troupes/{troupe.id}/posts/desk").json()
    assert [p["status"] for p in desk["posts"]] == ["draft"]
    assert desk["writes"] is True

    published = troupe.assistant.client.post(f"/posts/{post}/publish", json={})
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    # No Discord: in the app only, and staff are told why.
    assert published.json()["discord"] == {
        "state": "app_only",
        "reason": "Discord isn't set up on this server.",
        "next_attempt_at": None,
    }

    page = troupe.player.client.get(f"/troupes/{troupe.id}/posts").json()
    [story] = page["posts"]
    assert (story["title"], story["dateline"], story["unread"]) == (
        "Fire at the docks",
        "Boston, 3 November",
        True,
    )
    # Players aren't told about Discord.
    assert story["discord"] is None
    assert troupe.stranger.client.get(f"/troupes/{troupe.id}/posts").status_code == 404
    assert "New from The Boston Herald: Fire at the docks" in bell(session, troupe.player)
    # Not to the one who published it.
    assert bell(session, troupe.assistant) == []
    assert "assistant published the story “Fire at the docks”." in news.log()


def test_unread_dots_and_counts_are_each_persons_own(news: News) -> None:
    troupe = news.troupe
    first = news.published(title="First")
    news.published(title="Second")

    assert news.glance(troupe.player)["news_unread"] == 2
    assert news.glance(troupe.player)["latest_news"]["title"] == "Second"
    troupe.player.client.post(f"/posts/{first}/read")

    assert news.glance(troupe.player)["news_unread"] == 1
    assert news.glance(troupe.narrator)["news_unread"] == 2
    unread = {
        p["title"]: p["unread"]
        for p in troupe.player.client.get(f"/troupes/{troupe.id}/posts").json()["posts"]
    }
    assert unread == {"First": False, "Second": True}

    troupe.player.client.post(f"/troupes/{troupe.id}/posts/read")
    assert news.glance(troupe.player)["news_unread"] == 0


def test_the_list_filters_by_agency(news: News) -> None:
    troupe = news.troupe
    tv = news.new_agency("WKBN Nightly")
    news.published(title="Herald story")
    news.published(title="TV story", agency_id=tv)

    page = troupe.player.client.get(f"/troupes/{troupe.id}/posts", params={"agency_id": tv})

    assert [p["title"] for p in page.json()["posts"]] == ["TV story"]
    assert news.read(troupe.player) == ["TV story", "Herald story"]


def test_older_stories_come_a_page_at_a_time(news: News, session: Session) -> None:
    troupe = news.troupe
    for n in range(posts.AT_LEAST + 3):
        post = session.get_one(Post, uuid.UUID(news.published(title=f"Story {n}")))
        post.published_at = datetime.now(UTC) - timedelta(days=60 + n)
    session.flush()

    first = troupe.player.client.get(f"/troupes/{troupe.id}/posts").json()
    assert len(first["posts"]) == posts.AT_LEAST
    assert first["older"] is True
    older = troupe.player.client.get(
        f"/troupes/{troupe.id}/posts", params={"before": first["posts"][-1]["published_at"]}
    ).json()
    assert [p["title"] for p in older["posts"]] == ["Story 10", "Story 11", "Story 12"]
    assert older["older"] is False


def test_a_scheduled_story_publishes_when_its_time_comes(
    news: News, session: Session, clock: list[datetime]
) -> None:
    troupe = news.troupe
    post = news.draft()
    when = START + timedelta(hours=2)
    too_soon = troupe.storyteller.client.post(
        f"/posts/{post}/schedule", json={"publish_at": START.isoformat()}
    )
    assert too_soon.status_code == 422

    scheduled = troupe.storyteller.client.post(
        f"/posts/{post}/schedule", json={"publish_at": when.isoformat()}
    )
    assert scheduled.status_code == 200, scheduled.text
    assert scheduled.json()["status"] == "scheduled"

    clock[0] = when - timedelta(minutes=1)
    assert posts.publish_due(session) == 0
    assert news.read(troupe.player) == []

    clock[0] = when + timedelta(seconds=15)
    assert posts.publish_due(session) == 1
    assert news.read(troupe.player) == ["Fire at the docks"]
    assert session.get_one(Post, uuid.UUID(post)).published_at == clock[0]
    assert "New from The Boston Herald: Fire at the docks" in bell(session, troupe.player)
    assert "storyteller published the story “Fire at the docks”." in news.log()
    # Once only.
    assert posts.publish_due(session) == 0


def test_a_scheduled_story_can_be_cancelled(news: News, session: Session) -> None:
    troupe = news.troupe
    post = news.draft()
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    troupe.storyteller.client.post(f"/posts/{post}/schedule", json={"publish_at": later})

    cancelled = troupe.storyteller.client.post(f"/posts/{post}/unschedule")

    assert cancelled.json()["status"] == "draft"
    assert posts.publish_due(session, datetime.now(UTC) + timedelta(hours=2)) == 0


def schedule(news: News, post: str, when: datetime, by: Person | None = None) -> None:
    done = (by or news.troupe.storyteller).client.post(
        f"/posts/{post}/schedule", json={"publish_at": when.isoformat()}
    )
    assert done.status_code == 200, done.text


def archive(news: News) -> None:
    troupe = news.troupe
    done = troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"})
    assert done.status_code == 200, done.text


def test_an_archived_troupes_scheduled_story_never_goes_out(
    news: News,
    session: Session,
    clock: list[datetime],
    mail: FakeSMTP,
    fake_discord: FakeDiscord,
) -> None:
    troupe = news.troupe
    on_discord(news)
    troupe.narrator.client.patch("/preferences", json={"email_news": True})
    post = news.draft()
    schedule(news, post, START + timedelta(hours=1))
    # Another troupe's story, due after it, still goes out.
    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Princes of the City", "lead_handle": troupe.lead.handle}
    ).json()["id"]
    agency = troupe.lead.client.post(f"/troupes/{other}/agencies", json={"name": "Gazette"})
    live = troupe.lead.client.post(
        f"/troupes/{other}/posts",
        json={"agency_id": agency.json()["id"], "title": "Still open", "body": "Yes."},
    ).json()["id"]
    schedule(news, live, START + timedelta(hours=2), by=troupe.lead)
    archive(news)

    clock[0] = START + timedelta(hours=3)
    # The archived troupe's story is due first, and left where it is: the publisher
    # goes on past it to the other's, and then stops.
    assert posts.publish_due(session) == 1
    assert session.get_one(Post, uuid.UUID(live)).status == "published"
    waiting = session.get_one(Post, uuid.UUID(post))
    assert (waiting.status, waiting.published_at) == ("scheduled", None)
    assert posts.publish_due(session) == 0

    # Nobody hears of it: no bell, no email, nothing for Discord.
    assert not [s for s in bell(session, troupe.narrator) if "Fire at the docks" in s]
    assert session.scalars(select(EmailNotice).where(EmailNotice.topic == "news")).all() == []
    assert session.scalars(select(Delivery).where(Delivery.post_id == waiting.id)).all() == []
    assert send_all(session, clock[0]) == 0
    assert fake_discord.messages == {}


def test_nothing_is_published_or_scheduled_in_an_archived_troupe(
    news: News, session: Session
) -> None:
    troupe = news.troupe
    post = news.draft()
    archive(news)
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    # Its staff no longer see its drafts; the custodian does, but sends nothing.
    assert troupe.storyteller.client.post(f"/posts/{post}/publish", json={}).status_code == 404
    for done in (
        troupe.custodian.client.post(f"/posts/{post}/publish", json={}),
        troupe.custodian.client.post(f"/posts/{post}/schedule", json={"publish_at": later}),
    ):
        assert done.status_code == 409, done.text
        assert done.json()["detail"] == "This troupe is archived, so its posts don't go out."
    assert session.get_one(Post, uuid.UUID(post)).status == "draft"


def test_reopening_a_troupe_sends_back_to_the_drafts_what_it_missed(
    news: News, session: Session, clock: list[datetime]
) -> None:
    troupe = news.troupe
    missed = news.draft()
    schedule(news, missed, START + timedelta(hours=1))
    coming = news.draft(title="Still to come")
    schedule(news, coming, START + timedelta(hours=5))
    archive(news)

    clock[0] = START + timedelta(hours=2)
    assert posts.publish_due(session) == 0
    reopened = troupe.custodian.client.post(
        f"/troupes/{troupe.id}/reopen", json={"reason": "Starting again"}
    )
    assert reopened.status_code == 200, reopened.text

    # Its time passed while the troupe was archived: it doesn't go out late.
    back = session.get_one(Post, uuid.UUID(missed))
    assert (back.status, back.publish_at, back.published_at) == ("draft", None, None)
    assert posts.publish_due(session) == 0
    told = (
        "“Fire at the docks” wasn't published: its time came while Lords of the Night was"
        " archived. It is back in the drafts."
    )
    for person in (troupe.lead, troupe.storyteller, troupe.assistant):
        assert told in bell(session, person), person.email
    assert told not in bell(session, troupe.narrator)
    assert (
        "custodian reopened the troupe after the story “Fire at the docks” was due: it went"
        " back to the drafts unsent." in news.log()
    )

    # One still to come goes out when its time comes, as scheduled.
    assert session.get_one(Post, uuid.UUID(coming)).status == "scheduled"
    clock[0] = START + timedelta(hours=6)
    assert posts.publish_due(session) == 1
    assert session.get_one(Post, uuid.UUID(coming)).status == "published"


def test_unpublishing_takes_it_back_to_the_drafts(news: News) -> None:
    troupe = news.troupe
    post = news.published()

    taken = troupe.storyteller.client.post(f"/posts/{post}/unpublish")

    assert taken.json()["status"] == "draft"
    assert news.read(troupe.player) == []
    assert troupe.player.client.get(f"/posts/{post}").status_code == 404
    assert "storyteller unpublished the story “Fire at the docks”." in news.log()
    # A published story can't be deleted; a draft can.
    again = news.published(title="Again")
    assert troupe.storyteller.client.delete(f"/posts/{again}").status_code == 409
    assert troupe.storyteller.client.delete(f"/posts/{post}").status_code == 204


def test_duplicate_copies_a_story_as_a_new_draft(news: News) -> None:
    troupe = news.troupe
    post = news.published(dateline="Monday")

    copy = troupe.assistant.client.post(f"/posts/{post}/duplicate")

    assert copy.status_code == 201, copy.text
    made = copy.json()
    assert made["id"] != post
    assert (made["status"], made["title"], made["dateline"], made["agency_id"]) == (
        "draft",
        "Fire at the docks",
        "Monday",
        news.agency,
    )


def test_players_never_write(news: News) -> None:
    troupe = news.troupe
    post = news.published()
    assert news.write(troupe.player).status_code == 403
    assert troupe.player.client.get(f"/troupes/{troupe.id}/posts/desk").status_code == 403
    for action in ("publish", "unpublish", "duplicate", "decline"):
        assert troupe.player.client.post(f"/posts/{post}/{action}", json={}).status_code in (
            403,
            404,
        )
    assert troupe.player.client.put(f"/posts/{post}", json={"title": "Mine"}).status_code == 403


# --- narrators' proposals ------------------------------------------------------------------


@pytest.fixture
def narrator2(news: News) -> Person:
    other = sign_up(news.troupe.client_for, "narrator2")
    added = news.troupe.lead.client.put(
        f"/troupes/{news.troupe.id}/staff", json={"handle": other.handle, "role": "narrator"}
    )
    assert added.status_code == 200, added.text
    return other


def test_a_narrator_proposes_and_sees_only_their_own(news: News, narrator2: Person) -> None:
    troupe = news.troupe
    proposed = news.write(troupe.narrator, title="Rumours at Elysium")
    assert proposed.status_code == 201, proposed.text
    post = proposed.json()
    assert (post["status"], post["mine"]) == ("proposed", True)
    draft = news.draft(title="Staff draft")

    desk = troupe.narrator.client.get(f"/troupes/{troupe.id}/posts/desk").json()
    assert [p["title"] for p in desk["posts"]] == ["Rumours at Elysium"]
    assert desk["writes"] is False
    # Not another narrator's, nor the storytellers' drafts.
    assert narrator2.client.get(f"/troupes/{troupe.id}/posts/desk").json()["posts"] == []
    assert narrator2.client.get(f"/posts/{post['id']}").status_code == 404
    assert troupe.narrator.client.get(f"/posts/{draft}").status_code == 404

    # Theirs to edit while it waits; never another's, never to publish.
    changed = troupe.narrator.client.put(
        f"/posts/{post['id']}", json={"agency_id": news.agency, "title": "Rumours, again"}
    )
    assert changed.status_code == 200, changed.text
    assert (
        narrator2.client.put(f"/posts/{post['id']}", json={"title": "Mine now"}).status_code == 404
    )
    assert troupe.narrator.client.put(f"/posts/{draft}", json={"title": "x"}).status_code == 404
    for action in ("publish", "schedule", "accept", "decline", "duplicate"):
        refused = troupe.narrator.client.post(
            f"/posts/{post['id']}/{action}",
            json={"publish_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        )
        assert refused.status_code == 403, action


def test_a_narrator_is_told_when_their_proposal_is_published(news: News, session: Session) -> None:
    troupe = news.troupe
    post = news.write(troupe.narrator, title="Rumours at Elysium").json()["id"]
    desk = troupe.storyteller.client.get(f"/troupes/{troupe.id}/posts/desk").json()
    assert [(p["status"], p["proposed_by"]) for p in desk["posts"]] == [("proposed", "narrator")]

    accepted = troupe.storyteller.client.post(f"/posts/{post}/accept")
    assert accepted.json()["status"] == "draft"
    # Taken up, it is no longer the narrator's to see or edit.
    assert troupe.narrator.client.get(f"/posts/{post}").status_code == 404
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/posts/desk").json()["posts"] == []

    troupe.storyteller.client.post(f"/posts/{post}/publish", json={"note": "Nicely done."})

    assert "Your proposed story “Rumours at Elysium” is published. Nicely done." in bell(
        session, troupe.narrator
    )
    # And they read it as players do.
    assert news.read(troupe.narrator) == ["Rumours at Elysium"]


def test_a_declined_proposal_is_the_narrators_to_read_not_change(
    news: News, session: Session
) -> None:
    troupe = news.troupe
    post = news.write(troupe.narrator, title="Too much").json()["id"]

    declined = troupe.assistant.client.post(
        f"/posts/{post}/decline", json={"note": "Not this week."}
    )

    assert declined.json()["status"] == "declined"
    assert "Your proposed story “Too much” was declined. Not this week." in bell(
        session, troupe.narrator
    )
    seen = troupe.narrator.client.get(f"/posts/{post}").json()
    assert (seen["status"], seen["note"]) == ("declined", "Not this week.")
    assert troupe.narrator.client.put(f"/posts/{post}", json={"title": "x"}).status_code == 403
    # It isn't published, and can't be declined twice.
    assert news.read(troupe.player) == []
    assert troupe.assistant.client.post(f"/posts/{post}/decline", json={}).status_code == 409
    assert troupe.narrator.client.delete(f"/posts/{post}").status_code == 204


# --- the bell and email --------------------------------------------------------------------


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> FakeSMTP:
    from horatio.connectors import email

    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(email, "smtp_factory", fake)
    return fake


def test_news_comes_by_email_only_to_those_who_ask(
    news: News, session: Session, mail: FakeSMTP
) -> None:
    troupe = news.troupe
    troupe.player.client.patch("/preferences", json={"email_news": True})
    troupe.narrator.client.patch("/preferences", json={"bell_news": False})

    news.published()

    emailed = session.scalars(select(EmailNotice.user_id).where(EmailNotice.topic == "news"))
    assert set(emailed) == {uuid.UUID(troupe.player.id)}
    assert bell(session, troupe.narrator) == []
    assert bell(session, troupe.player) == ["New from The Boston Herald: Fire at the docks"]


# --- pictures ------------------------------------------------------------------------------


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


def png(width: int = 1600, height: int = 900) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (120, 20, 20)).save(out, "PNG")
    return out.getvalue()


def test_a_story_has_a_picture_for_members_only(news: News, kept: Path) -> None:
    troupe = news.troupe
    post = news.draft()

    added = troupe.storyteller.client.post(
        f"/posts/{post}/picture", files={"file": ("p.png", png(), "image/png")}
    )

    assert added.status_code == 200, added.text
    picture = added.json()["picture"]
    troupe.storyteller.client.post(f"/posts/{post}/publish", json={})
    shown = troupe.player.client.get(f"{picture}/1200.webp".removeprefix("/api"))
    assert shown.status_code == 200
    with Image.open(io.BytesIO(shown.content)) as image:
        assert image.size == (1200, 675)
    assert troupe.stranger.client.get(f"{picture}/600.webp".removeprefix("/api")).status_code == 404


# --- Discord -------------------------------------------------------------------------------


def on_discord(news: News, channel: str = OPEN_CHANNEL) -> None:
    """Connect the fake server and choose the news channel."""
    from tests.test_discord_connector import connect_server

    class Ready:
        troupe = news.troupe

    assert connect_server(Ready()).status_code == 303  # type: ignore[arg-type]
    chosen = news.troupe.storyteller.client.put(
        f"/troupes/{news.troupe.id}/post-channels", json={"kind": "news", "channel": channel}
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["news"] == channel


def send_all(session: Session, at: datetime = START) -> int:
    return delivery.send_due(session, at)


def test_a_story_goes_to_discord_as_an_embed_and_follows_edits(
    news: News, session: Session, fake_discord: FakeDiscord
) -> None:
    troupe = news.troupe
    on_discord(news)
    post = news.published(dateline="Boston, Monday")
    waiting = troupe.storyteller.client.get(f"/posts/{post}").json()["discord"]
    assert waiting["state"] == "waiting"

    assert send_all(session) == 1

    [(message_id, sent)] = fake_discord.messages.items()
    [embed] = sent.payload["embeds"]
    assert sent.channel == OPEN_CHANNEL
    assert embed["title"] == "Fire at the docks"
    assert embed["author"] == {"name": "The Boston Herald"}
    assert embed["color"] == 0x8B1E1E
    assert embed["url"] == f"http://localhost:5173/troupes/{troupe.id}/news/{post}"
    assert embed["description"].startswith("*Boston, Monday*\n\nSmoke.")
    assert "[Read in Horatio](http://localhost:5173/troupes/" in embed["description"]
    # It posts as its agency, through the channel's webhook (#883).
    assert sent.webhook is not None
    assert sent.payload["username"] == "The Boston Herald"
    assert "avatar_url" not in sent.payload
    story = session.get_one(Post, uuid.UUID(post))
    assert story.discord == {"channel": OPEN_CHANNEL, "message_ids": [message_id], "webhook": True}
    assert troupe.storyteller.client.get(f"/posts/{post}").json()["discord"]["state"] == "sent"

    # Editing it edits the same message.
    edited = troupe.storyteller.client.put(
        f"/posts/{post}", json={"agency_id": news.agency, "title": "Fire out at the docks"}
    )
    assert edited.status_code == 200, edited.text
    assert send_all(session) == 1
    assert fake_discord.edits == [message_id]
    assert fake_discord.messages[message_id].payload["embeds"][0]["title"] == (
        "Fire out at the docks"
    )
    assert "storyteller edited the story “Fire out at the docks”, which is published." in (
        news.log()
    )

    # Unpublishing deletes it.
    troupe.storyteller.client.post(f"/posts/{post}/unpublish")
    assert send_all(session) == 1
    assert fake_discord.messages == {}
    assert fake_discord.deletions == [message_id]
    assert troupe.storyteller.client.delete(f"/posts/{post}").status_code == 204


def test_a_long_story_splits_over_embeds_and_an_edit_shrinks_it(
    news: News, session: Session, fake_discord: FakeDiscord
) -> None:
    on_discord(news)
    long = "\n\n".join(f"Paragraph {n}. " + "w" * 1500 for n in range(6))
    post = news.published(body=long)

    send_all(session)

    ids = session.get_one(Post, uuid.UUID(post)).discord["message_ids"]
    assert len(ids) == 3
    embeds = [fake_discord.messages[i].payload["embeds"][0] for i in ids]
    assert all(len(e["description"]) <= 4096 for e in embeds)
    assert "title" in embeds[0] and "title" not in embeds[1]
    assert "Read in Horatio" in embeds[-1]["description"]

    news.troupe.storyteller.client.put(
        f"/posts/{post}", json={"agency_id": news.agency, "title": "Short now", "body": "Brief."}
    )
    send_all(session)

    assert fake_discord.edits == [ids[0]]
    assert sorted(fake_discord.deletions) == sorted(ids[1:])
    assert session.get_one(Post, uuid.UUID(post)).discord["message_ids"] == [ids[0]]


def test_an_agency_with_its_own_channel_posts_there(
    news: News, session: Session, fake_discord: FakeDiscord
) -> None:
    on_discord(news)
    own = news.troupe.storyteller.client.put(
        f"/agencies/{news.agency}",
        json={"name": "The Boston Herald", "discord_channel": TEST_CHANNEL, "colour": "#102030"},
    )
    assert own.status_code == 200, own.text
    news.published()

    send_all(session)

    [sent] = fake_discord.messages.values()
    assert sent.channel == TEST_CHANNEL
    assert sent.payload["embeds"][0]["color"] == 0x102030


def test_a_picture_goes_with_the_embed(
    news: News, session: Session, fake_discord: FakeDiscord, kept: Path
) -> None:
    on_discord(news)
    post = news.draft()
    news.troupe.storyteller.client.post(
        f"/posts/{post}/picture", files={"file": ("p.png", png(), "image/png")}
    )
    news.troupe.storyteller.client.post(f"/posts/{post}/publish", json={})

    send_all(session)

    [sent] = fake_discord.messages.values()
    assert sent.payload["embeds"][0]["image"] == {"url": "attachment://picture.webp"}
    assert sent.files["files[0]"][0] == "picture.webp"


def test_without_a_news_channel_it_is_in_the_app_only(
    news: News, session: Session, fake_discord: FakeDiscord
) -> None:
    on_discord(news)
    news.troupe.storyteller.client.put(
        f"/troupes/{news.troupe.id}/post-channels", json={"kind": "news", "channel": None}
    )
    post = news.published()

    assert send_all(session) == 0
    shown = news.troupe.storyteller.client.get(f"/posts/{post}").json()["discord"]
    assert shown == {
        "state": "app_only",
        "reason": "No news channel is chosen.",
        "next_attempt_at": None,
    }
    assert news.read(news.troupe.player) == ["Fire at the docks"]


def test_a_failure_backs_off_then_staff_retry_or_mark_it_sent(
    news: News, session: Session, fake_discord: FakeDiscord
) -> None:
    troupe = news.troupe
    on_discord(news)
    post = news.published()
    fake_discord.next = [(503, {})]

    send_all(session)

    shown = troupe.storyteller.client.get(f"/posts/{post}").json()["discord"]
    assert shown["state"] == "waiting"
    assert shown["reason"] == "Discord is having trouble (503)."
    assert send_all(session) == 0  # not due yet
    assert send_all(session, START + timedelta(minutes=2)) == 1
    assert len(fake_discord.messages) == 1

    # A failure not worth retrying waits for staff.
    news.troupe.storyteller.client.put(
        f"/posts/{post}", json={"agency_id": news.agency, "title": "Changed"}
    )
    fake_discord.next = [(403, {})]
    send_all(session, START + timedelta(minutes=3))
    failed = troupe.storyteller.client.get(f"/posts/{post}").json()["discord"]
    assert failed["state"] == "failed"
    assert troupe.player.client.post(f"/posts/{post}/discord/retry").status_code == 403

    retried = troupe.assistant.client.post(f"/posts/{post}/discord/retry")
    assert retried.json()["discord"]["state"] == "waiting"
    send_all(session, START + timedelta(minutes=4))
    [sent] = fake_discord.messages.values()
    assert sent.payload["embeds"][0]["title"] == "Changed"
    assert "assistant retried sending the story “Changed” to Discord." in news.log()

    fake_discord.next = [(403, {})]
    news.troupe.storyteller.client.put(
        f"/posts/{post}", json={"agency_id": news.agency, "title": "Changed again"}
    )
    send_all(session, START + timedelta(minutes=5))
    marked = troupe.storyteller.client.post(f"/posts/{post}/discord/mark-sent")
    assert marked.json()["discord"]["state"] == "sent"


def test_a_message_deleted_on_discord_is_posted_again_on_edit(
    news: News, session: Session, fake_discord: FakeDiscord
) -> None:
    on_discord(news)
    post = news.published()
    send_all(session)
    fake_discord.messages.clear()

    news.troupe.storyteller.client.put(
        f"/posts/{post}", json={"agency_id": news.agency, "title": "Back again"}
    )
    send_all(session)

    [(new_id, sent)] = fake_discord.messages.items()
    assert sent.payload["embeds"][0]["title"] == "Back again"
    assert session.get_one(Post, uuid.UUID(post)).discord["message_ids"] == [new_id]


def test_a_story_posts_under_its_agencys_portrait(
    news: News, session: Session, fake_discord: FakeDiscord, kept: Path
) -> None:
    on_discord(news)
    added = news.troupe.storyteller.client.post(
        f"/agencies/{news.agency}/portrait", files={"file": ("p.png", png(), "image/png")}
    )
    assert added.status_code == 200, added.text
    assert "storyteller changed the portrait of the news agency The Boston Herald." in news.log()
    portrait = uuid.UUID(added.json()["portrait"].rsplit("/", 1)[1])
    news.published()

    send_all(session)

    [sent] = fake_discord.messages.values()
    assert sent.payload["username"] == "The Boston Herald"
    assert sent.payload["avatar_url"] == public_pictures.avatar_url(
        "agency", uuid.UUID(news.agency), portrait
    )
    # The masthead stays where it was, beside the story.
    assert sent.payload["embeds"][0]["author"] == {"name": "The Boston Herald"}
    shown = news.troupe.client_for().get(
        sent.payload["avatar_url"].removeprefix("http://localhost:5173/api")
    )
    assert shown.status_code == 200
    # Members see it in the app too; strangers don't.
    small = added.json()["portrait"].removeprefix("/api") + "/128.webp"
    assert news.troupe.player.client.get(small).status_code == 200
    assert news.troupe.stranger.client.get(small).status_code == 404


def test_without_manage_webhooks_a_story_posts_as_the_bot_and_stays_the_bots(
    news: News, session: Session, fake_discord: FakeDiscord
) -> None:
    on_discord(news)
    fake_discord.bot_role = discord.PERMISSIONS
    post = news.published()

    send_all(session)

    [(message_id, sent)] = fake_discord.messages.items()
    assert sent.webhook is None
    assert "username" not in sent.payload
    assert session.get_one(Post, uuid.UUID(post)).discord == {
        "channel": OPEN_CHANNEL,
        "message_ids": [message_id],
    }
    shown = news.troupe.storyteller.client.get(f"/posts/{post}").json()["discord"]
    assert shown["state"] == "sent"

    # Given Manage Webhooks later, its messages stay the bot's to edit and delete.
    fake_discord.bot_role = discord.CHECKED
    news.troupe.storyteller.client.put(
        f"/posts/{post}", json={"agency_id": news.agency, "title": "Fire out at the docks"}
    )
    send_all(session)
    assert fake_discord.edits == [message_id]
    assert fake_discord.messages[message_id].webhook is None
    news.troupe.storyteller.client.post(f"/posts/{post}/unpublish")
    send_all(session)
    assert fake_discord.deletions == [message_id]


def test_a_story_sent_before_it_could_post_as_its_agency_stays_the_bots(
    news: News, session: Session, fake_discord: FakeDiscord
) -> None:
    """Stories on Discord from before #883 name no webhook: they are the bot's."""
    on_discord(news)
    post = news.published()
    message_id = discord.post_message(OPEN_CHANNEL, {"embeds": [{"title": "Fire at the docks"}]})
    story = session.get_one(Post, uuid.UUID(post))
    story.discord = {"channel": OPEN_CHANNEL, "message_ids": [message_id]}
    for pending in session.scalars(select(Delivery).where(Delivery.post_id == story.id)):
        session.delete(pending)
    session.flush()

    news.troupe.storyteller.client.put(
        f"/posts/{post}", json={"agency_id": news.agency, "title": "Fire out at the docks"}
    )
    send_all(session)

    assert fake_discord.edits == [message_id]
    assert fake_discord.messages[message_id].webhook is None
    assert fake_discord.webhooks == {}
    news.troupe.storyteller.client.post(f"/posts/{post}/unpublish")
    send_all(session)
    assert fake_discord.deletions == [message_id]


def test_a_story_that_moves_channel_goes_as_its_agency_there(
    news: News, session: Session, fake_discord: FakeDiscord
) -> None:
    on_discord(news)
    fake_discord.bot_role = discord.PERMISSIONS
    post = news.published()
    send_all(session)
    [old_id] = fake_discord.messages

    fake_discord.bot_role = discord.CHECKED
    news.troupe.storyteller.client.put(
        f"/agencies/{news.agency}",
        json={"name": "The Boston Herald", "discord_channel": TEST_CHANNEL},
    )
    news.troupe.storyteller.client.put(
        f"/posts/{post}", json={"agency_id": news.agency, "title": "Fire out at the docks"}
    )
    send_all(session)

    # The bot deletes its own message, and the agency posts it in the new channel.
    assert fake_discord.deletions == [old_id]
    [(new_id, sent)] = fake_discord.messages.items()
    assert (sent.channel, sent.payload["username"]) == (TEST_CHANNEL, "The Boston Herald")
    assert session.get_one(Post, uuid.UUID(post)).discord == {
        "channel": TEST_CHANNEL,
        "message_ids": [new_id],
        "webhook": True,
    }


def test_only_storytellers_choose_the_news_channel(news: News, fake_discord: FakeDiscord) -> None:
    troupe = news.troupe
    on_discord(news)
    seen = troupe.assistant.client.get(f"/troupes/{troupe.id}/post-channels").json()
    assert (seen["server"], seen["news"], seen["can_change"]) == (
        "Court of Ash",
        OPEN_CHANNEL,
        False,
    )
    refused = troupe.assistant.client.put(
        f"/troupes/{troupe.id}/post-channels", json={"kind": "news", "channel": TEST_CHANNEL}
    )
    assert refused.status_code == 403
    not_there = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/post-channels", json={"kind": "news", "channel": "300"}
    )
    assert not_there.status_code == 422
    # Saving the connector keeps the news channel.
    saved = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/connectors/discord",
        json={"enabled": True, "mode": "full", "settings": {"test_channel": TEST_CHANNEL}},
    )
    assert saved.json()["settings"]["post_channels"] == {"news": OPEN_CHANNEL}
    assert saved.json()["settings"]["guild_id"] == GUILD


def test_deliveries_for_posts_name_their_action(
    news: News, session: Session, fake_discord: FakeDiscord
) -> None:
    on_discord(news)
    post = news.published()
    send_all(session)
    news.troupe.storyteller.client.post(f"/posts/{post}/unpublish")

    actions = session.scalars(
        select(Delivery.action)
        .where(Delivery.post_id == uuid.UUID(post))
        # Ids are uuidv7, so they keep the order the rows were made in even when the
        # test's one transaction gives both the same created_at.
        .order_by(Delivery.id)
    )
    assert list(actions) == ["sync", "delete"]

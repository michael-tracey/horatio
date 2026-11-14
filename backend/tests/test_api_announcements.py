"""Troupe announcements (issue #511): out-of-character posts from staff, kept apart
from news everywhere; pinned to the front page until a time, with banners each
person dismisses; important ones emailed to everyone; and their own Discord
channel, through the fake Discord."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import delivery, notification_emails, posts
from horatio.models import EmailNotice, Notification
from tests import test_api_posts, test_discord_connector
from tests.api_helpers import Person, Troupe
from tests.test_api_posts import News, bell, on_discord, png, send_all
from tests.test_discord_connector import OPEN_CHANNEL, TEST_CHANNEL, FakeDiscord
from tests.test_email_connector import FakeSMTP, body, text_of

# The fake Discord and mail server, for the tests here that use them.
fake_discord = test_discord_connector.fake_discord
mail = test_api_posts.mail
kept = test_api_posts.kept

SOON = datetime.now(UTC) + timedelta(days=3)


class Board(News):
    """A troupe with a player at home in it, an agency for news, and announcements."""

    def announce(self, person: Person | None = None, **more: Any) -> Any:
        body = {"kind": "announcement", "title": "Game moved to Saturday", "body": "Same place."}
        return (person or self.troupe.lead).client.post(
            f"/troupes/{self.troupe.id}/posts", json={**body, **more}
        )

    def announced(self, **more: Any) -> str:
        made = self.announce(**more)
        assert made.status_code == 201, made.text
        post = made.json()["id"]
        done = self.troupe.lead.client.post(f"/posts/{post}/publish", json={})
        assert done.status_code == 200, done.text
        return post

    def board(self, person: Person) -> list[str]:
        page = person.client.get(
            f"/troupes/{self.troupe.id}/posts", params={"kind": "announcement"}
        )
        assert page.status_code == 200, page.text
        return [p["title"] for p in page.json()["posts"]]

    def banners(self, person: Person) -> list[str]:
        return [b["title"] for b in self.glance(person)["banners"]]


@pytest.fixture
def board(client_for: Callable[[], TestClient], session: Session) -> Board:
    return Board(Troupe(client_for, session))


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[datetime]]:
    at = [datetime.now(UTC)]
    monkeypatch.setattr(delivery, "now", lambda: at[0])
    yield at


def test_announcements_and_news_are_never_mixed(board: Board, session: Session) -> None:
    troupe = board.troupe
    board.published(title="Fire at the docks")
    board.announced(title="Game moved to Saturday")

    assert board.read(troupe.player) == ["Fire at the docks"]
    assert board.board(troupe.player) == ["Game moved to Saturday"]
    seen = board.glance(troupe.player)
    assert (seen["news_unread"], seen["announcements_unread"]) == (1, 1)
    assert seen["latest_news"]["title"] == "Fire at the docks"
    # Each has its own desk too.
    news_desk = troupe.lead.client.get(f"/troupes/{troupe.id}/posts/desk").json()["posts"]
    board.announce(title="Downtimes due Friday")
    desk = troupe.lead.client.get(
        f"/troupes/{troupe.id}/posts/desk", params={"kind": "announcement"}
    ).json()["posts"]
    assert [p["title"] for p in desk] == ["Downtimes due Friday"]
    assert all(p["kind"] == "news" for p in news_desk)
    # Reading all the news reads no announcement.
    troupe.player.client.post(f"/troupes/{troupe.id}/posts/read", params={"kind": "news"})
    seen = board.glance(troupe.player)
    assert (seen["news_unread"], seen["announcements_unread"]) == (0, 1)
    assert bell(session, troupe.player) == [
        "New from The Boston Herald: Fire at the docks",
        "Announcement: Game moved to Saturday",
    ]


def test_an_announcement_is_signed_by_its_writer_and_their_role(board: Board) -> None:
    troupe = board.troupe
    by_lead = board.announced()
    made = board.announce(troupe.assistant, title="Parking")
    troupe.assistant.client.post(f"/posts/{made.json()['id']}/publish", json={})

    found = {
        p["title"]: p["byline"]
        for p in troupe.player.client.get(
            f"/troupes/{troupe.id}/posts", params={"kind": "announcement"}
        ).json()["posts"]
    }
    assert found == {
        "Game moved to Saturday": "lead, Lead storyteller",
        "Parking": "assistant, Assistant storyteller",
    }
    assert troupe.player.client.get(f"/posts/{by_lead}").json()["agency_id"] is None


def test_narrators_neither_write_nor_propose_announcements(board: Board) -> None:
    troupe = board.troupe
    assert board.announce(troupe.narrator).status_code == 403
    desk = troupe.narrator.client.get(
        f"/troupes/{troupe.id}/posts/desk", params={"kind": "announcement"}
    )
    assert desk.status_code == 403
    draft = board.announce().json()["id"]
    assert troupe.narrator.client.get(f"/posts/{draft}").status_code == 404
    assert troupe.narrator.client.post(f"/posts/{draft}/publish", json={}).status_code == 404
    # Published, they read it as players do.
    troupe.lead.client.post(f"/posts/{draft}/publish", json={})
    assert board.board(troupe.narrator) == ["Game moved to Saturday"]
    assert troupe.narrator.client.put(f"/posts/{draft}", json={"title": "x"}).status_code == 403
    assert board.announce(troupe.player).status_code == 403


def test_a_pinned_announcement_is_a_banner_until_its_time(
    board: Board, clock: list[datetime]
) -> None:
    troupe = board.troupe
    board.announced(title="Older news")
    until = clock[0] + timedelta(days=2)
    pinned = board.announced(title="New venue parking", pinned_until=until.isoformat())
    clock[0] += timedelta(minutes=1)
    board.announced(title="Newest, not pinned")

    # Pinned ones first in the list, and as a banner.
    assert board.board(troupe.player) == ["New venue parking", "Newest, not pinned", "Older news"]
    assert board.banners(troupe.player) == ["New venue parking"]
    shown = troupe.player.client.get(f"/posts/{pinned}").json()
    assert (shown["pinned"], shown["dismissed"]) == (True, False)

    # It unpins itself once its time passes.
    clock[0] = until + timedelta(seconds=1)
    assert board.banners(troupe.player) == []
    assert board.board(troupe.player) == ["Newest, not pinned", "New venue parking", "Older news"]
    assert troupe.player.client.get(f"/posts/{pinned}").json()["pinned"] is False


def test_each_person_dismisses_a_banner_for_themselves(board: Board) -> None:
    troupe = board.troupe
    post = board.announced(pinned_until=SOON.isoformat())

    dismissed = troupe.player.client.post(f"/posts/{post}/dismiss")

    assert dismissed.status_code == 204
    assert board.banners(troupe.player) == []
    assert board.banners(troupe.narrator) == ["Game moved to Saturday"]
    # Still pinned at the top of their list, and unread until they read it.
    assert board.board(troupe.player) == ["Game moved to Saturday"]
    assert board.glance(troupe.player)["announcements_unread"] == 1
    assert troupe.player.client.get(f"/posts/{post}").json()["dismissed"] is True
    # News has no banner to dismiss.
    story = board.published()
    assert troupe.player.client.post(f"/posts/{story}/dismiss").status_code == 409


def test_the_bell_shows_an_announcements_picture_while_it_has_one(board: Board, kept: Path) -> None:
    """#832: the bell shows a published announcement's own picture beside its notice,
    looked up as it is read; news keeps to its words, as its masthead is the agency's."""
    troupe = board.troupe
    made = board.announce(title="New venue")
    post = made.json()["id"]
    added = troupe.lead.client.post(
        f"/posts/{post}/picture", files={"file": ("p.png", png(), "image/png")}
    )
    assert added.status_code == 200, added.text
    picture = added.json()["picture"]
    troupe.lead.client.post(f"/posts/{post}/publish", json={})
    story = board.published()
    troupe.lead.client.post(
        f"/posts/{story}/picture", files={"file": ("p.png", png(), "image/png")}
    )

    def shown(kind: str) -> list[str | None]:
        items = troupe.player.client.get("/notifications").json()["items"]
        return [i["picture"] for i in items if i["kind"] == kind]

    assert shown("announcement.published") == [picture]
    assert shown("news.published") == [None]
    # The bell's picture loads for the member, as the announcement's own does.
    file = troupe.player.client.get(f"{picture}/600.webp".removeprefix("/api"))
    assert file.status_code == 200

    # Taken off the announcement, it goes from the bell too.
    assert troupe.lead.client.delete(f"/posts/{post}/picture").status_code == 200
    assert shown("announcement.published") == [None]


def test_staff_unpin_sooner_and_pinning_goes_in_the_log(board: Board) -> None:
    troupe = board.troupe
    post = board.announced()
    assert troupe.lead.client.post(f"/posts/{post}/unpin").status_code == 409
    past = troupe.lead.client.put(
        f"/posts/{post}",
        json={"title": "Game moved to Saturday", "pinned_until": "2020-01-01T00:00:00Z"},
    )
    assert past.status_code == 422

    pinned = troupe.assistant.client.put(
        f"/posts/{post}", json={"title": "Game moved to Saturday", "pinned_until": SOON.isoformat()}
    )
    assert pinned.json()["pinned"] is True
    assert troupe.player.client.post(f"/posts/{post}/unpin").status_code == 403
    unpinned = troupe.storyteller.client.post(f"/posts/{post}/unpin")

    assert unpinned.json()["pinned"] is False
    assert board.banners(troupe.player) == []
    log = board.log()
    assert "assistant pinned the announcement “Game moved to Saturday” to the front page." in log
    assert "storyteller unpinned the announcement “Game moved to Saturday”." in log
    # Changing only the pin is no edit.
    assert not any("edited" in line for line in log)


def test_announcement_emails_are_on_unless_turned_off(
    board: Board, session: Session, mail: FakeSMTP
) -> None:
    troupe = board.troupe
    troupe.narrator.client.patch("/preferences", json={"email_announcements": False})

    board.announced()

    emailed = set(
        session.scalars(select(EmailNotice.user_id).where(EmailNotice.topic == "announcements"))
    )
    assert uuid.UUID(troupe.player.id) in emailed
    assert uuid.UUID(troupe.narrator.id) not in emailed
    # The bell too, unless turned off.
    troupe.player.client.patch("/preferences", json={"bell_announcements": False})
    board.announced(title="Second")
    assert bell(session, troupe.player) == ["Announcement: Game moved to Saturday"]


def test_an_important_announcement_emails_even_those_who_turned_it_off(
    board: Board, session: Session, mail: FakeSMTP
) -> None:
    troupe = board.troupe
    troupe.player.client.patch("/preferences", json={"email_announcements": False})
    board.announced(title="Not important")
    board.announced(title="Venue closed tonight", important=True)

    for_player = list(
        session.scalars(
            select(EmailNotice).where(EmailNotice.user_id == uuid.UUID(troupe.player.id))
        )
    )
    assert [(n.summary, n.forced) for n in for_player] == [
        ("Announcement: Venue closed tonight", True)
    ]

    notification_emails.send_due(session, delivery.now() + timedelta(minutes=1))

    [sent] = [m for m in mail.sent if troupe.player.email in str(m["To"])]
    assert "Announcement: Venue closed tonight" in str(sent["Subject"])
    assert "Its staff marked this important" in text_of(sent)
    assert "lead sent the announcement “Venue closed tonight” as important, emailing everyone" in (
        " ".join(board.log())
    )


def mailed_to(mail: FakeSMTP, person: Person) -> list[EmailMessage]:
    return [m for m in mail.sent if person.email in str(m["To"])]


def jpegs(message: EmailMessage) -> list[bytes]:
    return [
        part.get_content() for part in message.walk() if part.get_content_type() == "image/jpeg"
    ]


def test_an_announcement_email_carries_the_announcement_and_its_picture(
    board: Board, session: Session, mail: FakeSMTP, kept: Path
) -> None:
    """#831: the title, troupe, byline, picture (inline, a small JPEG) and words, in
    both parts, with a button to read it in Horatio."""
    troupe = board.troupe
    words = "Doors at **seven**.\n\n- Bring your sheet\n- Pay at the door\n\n<b>not bold</b>"
    post = board.announce(title="New venue", body=words).json()["id"]
    added = troupe.lead.client.post(
        f"/posts/{post}/picture", files={"file": ("p.png", png(), "image/png")}
    )
    assert added.status_code == 200, added.text
    assert troupe.lead.client.post(f"/posts/{post}/publish", json={}).status_code == 200

    notification_emails.send_due(session, delivery.now() + timedelta(minutes=1))

    [sent] = mailed_to(mail, troupe.player)
    assert str(sent["Subject"]) == "Lords of the Night: Announcement: New venue"
    link = f"/troupes/{troupe.id}/announcements/{post}"
    text = text_of(sent)
    assert "Lords of the Night: announcement\n\nNew venue\nlead, Lead storyteller" in text
    assert "Doors at seven.\n\n- Bring your sheet\n- Pay at the door" in text
    assert "Read it in Horatio: http" in text and link in text

    page = body(sent, "html")
    assert "Announcement · Lords of the Night" in page
    assert ">New venue</h1>" in page and "lead, Lead storyteller" in page
    assert "Doors at <strong>seven</strong>." in page and page.count("<li ") == 2
    assert "&lt;b&gt;not bold&lt;/b&gt;" in page and "<b>not bold" not in page
    assert ">Read it in Horatio</a>" in page
    [picture] = jpegs(sent)
    assert len(picture) <= 200 * 1024
    with Image.open(BytesIO(picture)) as shown:
        assert shown.format == "JPEG" and shown.width == 600
    cid = next(p["Content-ID"] for p in sent.walk() if p.get_content_type() == "image/jpeg").strip(
        "<>"
    )
    assert f'src="cid:{cid}"' in page
    assert ".webp" not in page  # never linked from the server


def test_without_a_picture_the_email_has_the_rest(
    board: Board, session: Session, mail: FakeSMTP
) -> None:
    troupe = board.troupe
    board.announced(title="Bring snacks", body="Anything **sweet**.")
    notification_emails.send_due(session, delivery.now() + timedelta(minutes=1))
    [sent] = mailed_to(mail, troupe.player)
    assert jpegs(sent) == []
    assert "Anything sweet." in text_of(sent)
    assert "Anything <strong>sweet</strong>." in body(sent, "html")


def test_the_digest_keeps_a_line_for_each_announcement(
    board: Board, session: Session, mail: FakeSMTP, kept: Path
) -> None:
    """Several announcements waiting for the daily digest go as a line and a link
    each: no pictures, no words."""
    troupe = board.troupe
    troupe.player.client.patch("/preferences", json={"email_digest": "daily"})
    first = board.announce(title="New venue", body="Doors at seven.").json()["id"]
    troupe.lead.client.post(
        f"/posts/{first}/picture", files={"file": ("p.png", png(), "image/png")}
    )
    troupe.lead.client.post(f"/posts/{first}/publish", json={})
    board.announced(title="Bring snacks", body="Anything sweet.")

    notification_emails.send_due(session, delivery.now() + timedelta(days=2))

    [sent] = mailed_to(mail, troupe.player)
    assert "2 notifications today" in str(sent["Subject"])
    text = text_of(sent)
    assert "Lords of the Night: Announcement: New venue" in text
    assert "Lords of the Night: Announcement: Bring snacks" in text
    assert "Doors at seven" not in text and "Anything sweet" not in text
    assert jpegs(sent) == []


def test_an_announcement_unpublished_before_its_email_goes_is_only_named(
    board: Board, session: Session, mail: FakeSMTP
) -> None:
    """The words go only while it is still out: taken back, the email is the plain
    line it always was."""
    troupe = board.troupe
    post = board.announced(title="Wrong date", body="The game is on Friday.")
    assert troupe.lead.client.post(f"/posts/{post}/unpublish").status_code == 200

    notification_emails.send_due(session, delivery.now() + timedelta(minutes=1))

    [sent] = mailed_to(mail, troupe.player)
    text = text_of(sent)
    assert "Lords of the Night: Announcement: Wrong date" in text
    assert "The game is on Friday" not in text


def test_announcements_go_to_their_own_discord_channel(
    board: Board, session: Session, fake_discord: FakeDiscord
) -> None:
    troupe = board.troupe
    on_discord(board)
    chosen = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/post-channels",
        json={"kind": "announcement", "channel": TEST_CHANNEL},
    )
    assert (chosen.json()["news"], chosen.json()["announcements"]) == (OPEN_CHANNEL, TEST_CHANNEL)
    post = board.announced(pinned_until=SOON.isoformat())
    board.published()

    send_all(session)

    by_channel = {m.channel: m.payload["embeds"][0] for m in fake_discord.messages.values()}
    assert set(by_channel) == {OPEN_CHANNEL, TEST_CHANNEL}
    embed = by_channel[TEST_CHANNEL]
    assert embed["title"] == "Game moved to Saturday"
    assert embed["author"] == {"name": "lead, Lead storyteller"}
    assert embed["color"] == posts.colour(posts.ANNOUNCEMENT_COLOUR)
    assert f"/troupes/{troupe.id}/announcements/{post}" in embed["url"]
    assert by_channel[OPEN_CHANNEL]["author"] == {"name": "The Boston Herald"}
    # An announcement posts as the bot; the story as its agency (#883).
    senders = {m.channel: m.webhook for m in fake_discord.messages.values()}
    assert senders[TEST_CHANNEL] is None and senders[OPEN_CHANNEL] is not None

    # Editing it edits the post; unpublishing deletes it.
    [message_id] = [i for i, m in fake_discord.messages.items() if m.channel == TEST_CHANNEL]
    troupe.lead.client.put(f"/posts/{post}", json={"title": "Game moved to Sunday"})
    send_all(session)
    assert fake_discord.edits == [message_id]
    assert fake_discord.messages[message_id].payload["embeds"][0]["title"] == (
        "Game moved to Sunday"
    )
    troupe.lead.client.post(f"/posts/{post}/unpublish")
    send_all(session)
    assert fake_discord.deletions == [message_id]
    assert {m.channel for m in fake_discord.messages.values()} == {OPEN_CHANNEL}
    assert board.banners(troupe.player) == []


def test_without_an_announcements_channel_staff_are_told(
    board: Board, fake_discord: FakeDiscord
) -> None:
    on_discord(board)
    post = board.announced()

    shown = board.troupe.lead.client.get(f"/posts/{post}").json()["discord"]

    assert shown["state"] == "app_only"
    assert shown["reason"] == "No announcements channel is chosen."


def test_duplicate_copies_an_announcement_unpinned(board: Board, session: Session) -> None:
    troupe = board.troupe
    post = board.announced(pinned_until=SOON.isoformat(), important=True)

    copy = troupe.assistant.client.post(f"/posts/{post}/duplicate").json()

    assert (copy["kind"], copy["status"], copy["pinned_until"], copy["important"]) == (
        "announcement",
        "draft",
        None,
        True,
    )
    assert (
        session.scalar(select(Notification.id).where(Notification.kind == "news.published")) is None
    )

"""A troupe's posts: news stories its storytellers write as the troupe's own
in-world news agencies (issue #510), and announcements, out of character, from its
storytellers and assistant storytellers (#511), for everyone in the troupe. The two
kinds share everything here, and are never mixed: each has its own list, unread
count, bell and email setting, and Discord channel.

Everyone in the troupe gets every post: its staff, and the players of its active
characters, home or visiting (horatio.permissions.is_member). Posts never cross
troupes and never repeat; Duplicate copies one as a new draft.

A post is, in turn:

- `draft`: being written by the troupe's storytellers and assistant storytellers;
- `proposed`: a narrator's news story, sent for them to take up (it becomes a draft),
  schedule, publish or decline. A narrator sees and edits only their own
  proposals, and only while they wait;
- `declined`: a proposal the storytellers turned down, with a note;
- `scheduled`: going out at `publish_at`. The delivery worker publishes it on its
  first round after then (`publish_due`, every `delivery_interval`);
- `published`: in the troupe's list at once, with an unread dot for each person
  until they read it, a bell notification for those who want it, and an email for
  those who asked for one.

On Discord a published post is an embed, in its agency's channel or else the
troupe's channel for posts of its kind. The worker sends it as a `Delivery` with
the action "sync", which makes Discord show the post as it now stands: posting it,
or editing the messages it is already in, whose ids are kept on the post. Editing a
published post queues another sync; unpublishing queues a "delete" of its messages.
Failures back off and wait for staff to retry or mark as sent, as downtime results
do (horatio.delivery). With no Discord server, or no channel chosen, a post is in
the app only, and its staff are told why.

An announcement has no agency: its byline is its writer and their role. It can be
pinned to the troupe's front page and the top of its list until a time, after which
it unpins itself; each person can dismiss its banner for themselves. An important
one emails everyone, even those who turned announcement emails off.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from horatio import audit, notification_emails, pictures, preferences
from horatio.config import get_settings
from horatio.connectors import SendError, discord
from horatio.models import (
    Character,
    Delivery,
    NewsAgency,
    Post,
    PostDismissal,
    PostRead,
    Troupe,
    TroupeConnector,
    TroupeMembership,
    TroupeStaff,
    User,
)
from horatio.notifications import notify
from horatio.permissions import Role, troupe_role


@dataclass(frozen=True)
class Kind:
    name: str
    # As the app's address names its list: /troupes/<id>/news.
    path: str
    # "story", for "the story", "a story".
    noun: str
    # The channel's name in a sentence: "No news channel is chosen."
    channel: str
    # The preference that keeps it from the bell (horatio.preferences).
    bell: str


KINDS = {
    "news": Kind("news", "news", "story", "news", "bell_news"),
    "announcement": Kind(
        "announcement", "announcements", "announcement", "announcements", "bell_announcements"
    ),
}
# An announcement's embed on Discord: Horatio's gold, as it has no masthead.
ANNOUNCEMENT_COLOUR = "#c9a24a"

# What a device keeps, and what the list shows first: the last 30 days, and at
# least the latest few, however old.
RECENT = timedelta(days=30)
AT_LEAST = 10
PAGE = 20


def now() -> datetime:
    from horatio import delivery

    return delivery.now()


def link(post: Post) -> str:
    """Where in the app the post is read."""
    return f"/troupes/{post.troupe_id}/{KINDS[post.kind].path}/{post.id}"


def members(db: Session, troupe: Troupe) -> list[uuid.UUID]:
    """Everyone in the troupe: its lead, its staff, and the players of its active
    characters, home or visiting."""
    staff = db.scalars(select(TroupeStaff.user_id).where(TroupeStaff.troupe_id == troupe.id))
    players = db.scalars(
        select(Character.player_id)
        .join(TroupeMembership, TroupeMembership.character_id == Character.id)
        .where(
            TroupeMembership.troupe_id == troupe.id,
            TroupeMembership.left_at.is_(None),
            Character.kind == "pc",
            Character.status == "active",
        )
    )
    return list(dict.fromkeys([troupe.lead_user_id, *staff, *(p for p in players if p)]))


# --- agencies -------------------------------------------------------------------------

# An agency's colour, as its masthead takes it.
COLOUR = r"^#[0-9a-f]{6}$"


def keep_agency(
    db: Session,
    user: User,
    troupe: Troupe,
    agency: NewsAgency | None,
    name: str,
    description: str,
    colour: str,
) -> NewsAgency:
    """Make a news agency, or (given one) change its name, description and colour. Its
    name is its own in the troupe; its channel and picture are set apart."""
    name = name.strip()
    clash = db.scalar(
        select(NewsAgency.id).where(
            NewsAgency.troupe_id == troupe.id,
            NewsAgency.name == name,
            NewsAgency.id != agency.id if agency else NewsAgency.id.is_not(None),
        )
    )
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"There is already an agency called {name}.")
    if agency is None:
        agency = NewsAgency(troupe_id=troupe.id, name=name)
        db.add(agency)
        audit.record(db, user, "agency.created", troupe_id=troupe.id, name=name)
    else:
        audit.record(db, user, "agency.changed", troupe_id=troupe.id, name=name, was=agency.name)
    agency.name = name
    agency.description = description.strip()
    agency.colour = colour
    db.flush()
    return agency


# --- Discord --------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """Where a post goes on Discord, or why it stays in the app."""

    channel: str | None
    reason: str | None


class Targets:
    """Where each of a troupe's posts goes on Discord, asking the database once."""

    def __init__(self, db: Session, troupe_id: uuid.UUID) -> None:
        row = db.scalar(
            select(TroupeConnector).where(
                TroupeConnector.troupe_id == troupe_id, TroupeConnector.kind == "discord"
            )
        )
        self.settings: dict[str, Any] = row.settings if row else {}
        self.agencies = {
            a.id: a for a in db.scalars(select(NewsAgency).where(NewsAgency.troupe_id == troupe_id))
        }

    def of(self, post: Post) -> Target:
        if not discord.configured():
            return Target(None, "Discord isn't set up on this server.")
        if not self.settings.get("guild_id"):
            return Target(None, "No Discord server is connected.")
        agency = self.agencies.get(post.agency_id) if post.agency_id else None
        chosen = (self.settings.get("post_channels") or {}).get(post.kind)
        channel = (agency.discord_channel if agency else None) or chosen
        if not channel:
            return Target(None, f"No {KINDS[post.kind].channel} channel is chosen.")
        return Target(channel, None)


def colour(value: str) -> int:
    return int(value.removeprefix("#"), 16)


def picture_file(post_troupe: uuid.UUID, picture_id: uuid.UUID | None, name: str) -> bytes | None:
    root = pictures.upload_dir()
    if root is None or picture_id is None:
        return None
    path = pictures.post_picture_file(root, post_troupe, picture_id, name)
    return path.read_bytes() if path is not None else None


def discord_messages(
    post: Post, agency: NewsAgency | None
) -> list[tuple[dict[str, Any], list[discord.File]]]:
    """The post as Discord messages, an embed each: the first under the masthead
    (its colour, the agency's name and picture), or for an announcement its byline,
    with the headline or title, linking to the post in Horatio; the text split over
    as many as it needs; the picture, and a Read in Horatio link, on the last."""
    url = f"{get_settings().public_url.rstrip('/')}{link(post)}"
    text = "\n\n".join(t for t in (f"*{post.dateline}*" if post.dateline else "", post.body) if t)
    # Room at the end of the last part for the link.
    read = f"[Read in Horatio]({url})"
    parts = discord.split(text, discord.EMBED_LIMIT - len(read) - 2) if text else []
    parts = parts or [""]
    parts[-1] = f"{parts[-1]}\n\n{read}" if parts[-1] else read
    tint = colour(agency.colour if agency else ANNOUNCEMENT_COLOUR)
    masthead = picture_file(post.troupe_id, agency.picture_id if agency else None, "1200.webp")
    picture = picture_file(post.troupe_id, post.picture_id, "1200.webp")
    messages: list[tuple[dict[str, Any], list[discord.File]]] = []
    for n, part in enumerate(parts):
        embed: dict[str, Any] = {"color": tint, "description": part}
        files: list[discord.File] = []
        if n == 0:
            embed["title"] = post.title[:256]
            embed["url"] = url
            if agency is not None:
                embed["author"] = {"name": agency.name[:256]}
            elif post.byline:
                embed["author"] = {"name": post.byline[:256]}
            if masthead is not None:
                embed["thumbnail"] = {"url": "attachment://masthead.webp"}
                files.append(discord.File("masthead.webp", masthead))
        if n == len(parts) - 1 and picture is not None:
            embed["image"] = {"url": "attachment://picture.webp"}
            files.append(discord.File("picture.webp", picture))
        messages.append(({"embeds": [embed]}, files))
    return messages


def sync(db: Session, post: Post) -> dict[str, Any]:
    """Make Discord show the published post as it now stands: edit the messages it
    is in, post any more it needs, and delete any it no longer needs. The ids kept
    on the post always name the messages there, even when this fails part way, so
    trying again carries on rather than posting it twice. Raises SendError."""
    if post.status != "published":
        # Unpublished since this was queued; the delete that queued sees to Discord.
        return {}
    target = Targets(db, post.troupe_id).of(post)
    if target.channel is None:
        raise SendError(target.reason or "There is nowhere on Discord to post it.", retry=False)
    channel = target.channel
    agency = db.get(NewsAgency, post.agency_id) if post.agency_id else None
    messages = discord_messages(post, agency)
    live: list[str] = list(post.discord.get("message_ids") or [])
    old_channel = post.discord.get("channel")

    def keep(where: str | None) -> None:
        post.discord = {"channel": where, "message_ids": list(live)} if live else {}

    if old_channel and old_channel != channel:
        # Its agency's channel changed: it moves.
        try:
            while live:
                discord.delete_message(old_channel, live[0])
                live.pop(0)
        finally:
            keep(old_channel)
    try:
        for n, (payload, files) in enumerate(messages):
            if n < len(live):
                try:
                    discord.edit_message(channel, live[n], payload, files)
                    continue
                except SendError as error:
                    if error.status != 404:
                        raise
                # Someone deleted it on Discord: post the rest again, in order.
                for gone in live[n:]:
                    discord.delete_message(channel, gone)
                del live[n:]
            live.append(discord.post_message(channel, payload, files))
        while len(live) > len(messages):
            discord.delete_message(channel, live[-1])
            live.pop()
    finally:
        keep(channel)
    return {"channel": channel, "message_ids": list(live)}


def delete_from_discord(delivery: Delivery) -> dict[str, Any]:
    """Delete the messages an unpublished post was in, as the delivery names them.
    Those deleted leave the list as they go, so trying again carries on."""
    channel = delivery.external_ids.get("channel")
    left: list[str] = list(delivery.external_ids.get("message_ids") or [])
    try:
        while channel and left:
            discord.delete_message(channel, left[0])
            left.pop(0)
    finally:
        delivery.external_ids = {"channel": channel, "message_ids": list(left)}
    return {"channel": channel, "deleted": True}


def send(db: Session, delivery: Delivery) -> dict[str, Any]:
    """Send one of a post's deliveries (horatio.delivery.send_one). Raises SendError."""
    assert delivery.post_id is not None
    post = db.get_one(Post, delivery.post_id, with_for_update=True)
    if delivery.action == "delete":
        return delete_from_discord(delivery)
    return sync(db, post)


def waiting(db: Session, post: Post) -> list[Delivery]:
    return list(
        db.scalars(
            select(Delivery).where(Delivery.post_id == post.id, Delivery.status == "pending")
        )
    )


def queue_sync(db: Session, post: Post, by: uuid.UUID) -> bool:
    """Have the worker bring Discord up to date with the post, unless a sync is
    already waiting (it sends the post as it stands when it goes) or there is
    nowhere on Discord for it. Returns whether it goes to Discord."""
    if Targets(db, post.troupe_id).of(post).channel is None and not post.discord:
        return False
    if any(d.action == "sync" for d in waiting(db, post)):
        return True
    db.add(
        Delivery(
            post_id=post.id,
            action="sync",
            channel="discord",
            status="pending",
            message="",
            sent_by=by,
            next_attempt_at=now(),
        )
    )
    return True


def queue_delete(db: Session, post: Post, by: uuid.UUID) -> None:
    """Take the post off Discord: drop any sync not yet sent, and delete the
    messages it is in."""
    for pending in waiting(db, post):
        if pending.action == "sync":
            db.delete(pending)
    if post.discord.get("message_ids"):
        db.add(
            Delivery(
                post_id=post.id,
                action="delete",
                channel="discord",
                status="pending",
                message="",
                sent_by=by,
                next_attempt_at=now(),
                external_ids=dict(post.discord),
            )
        )
    post.discord = {}


# --- publishing -----------------------------------------------------------------------


def summary(db: Session, post: Post) -> str:
    """What the bell says about a published post."""
    if post.kind == "announcement":
        return f"Announcement: {post.title}"
    agency = db.get(NewsAgency, post.agency_id) if post.agency_id else None
    return f"New from {agency.name}: {post.title}" if agency else post.title


ROLE_NAMES = {
    Role.LEAD_STORYTELLER: "Lead storyteller",
    Role.STORYTELLER: "Storyteller",
    Role.ASSISTANT_STORYTELLER: "Assistant storyteller",
    Role.NARRATOR: "Narrator",
}


def byline(db: Session, troupe: Troupe, user_id: uuid.UUID) -> str:
    """Who an announcement is from, as it goes out: "Mara Quinn, Lead storyteller"."""
    writer = db.get_one(User, user_id)
    role = troupe_role(db, writer, troupe)
    if role is not None:
        return f"{writer.display_name}, {ROLE_NAMES[role]}"
    return f"{writer.display_name}, Custodian" if writer.is_custodian else writer.display_name


def pinned(post: Post, at: datetime | None = None) -> bool:
    """An announcement pinned now: it unpins itself once its time passes."""
    return post.pinned_until is not None and post.pinned_until > (at or now())


def described(db: Session, post: Post) -> dict[str, Any]:
    """What the log keeps about a post, so it reads the same later."""
    agency = db.get(NewsAgency, post.agency_id) if post.agency_id else None
    return {
        "post_id": post.id,
        "what": f"the {KINDS[post.kind].noun}",
        "title": post.title,
        **({"agency": agency.name} if agency else {}),
    }


def publish(db: Session, post: Post, by: User | None, note: str = "") -> None:
    """Publish the post now: in the app at once, to Discord by the worker, and
    tell everyone in the troupe. `by` is None when the worker publishes a scheduled
    post, which was scheduled by `published_by`."""
    troupe = db.get_one(Troupe, post.troupe_id)
    at = now()
    post.status = "published"
    post.published_at = at
    post.publish_at = None
    if by is not None:
        post.published_by = by.id
    publisher = post.published_by or post.author_id
    if note:
        post.note = note
    if post.kind == "announcement":
        post.byline = byline(db, troupe, post.author_id)
    db.flush()
    queue_sync(db, post, publisher)
    tell_everyone(db, troupe, post, publisher)
    if post.proposed_by is not None and post.proposed_by != publisher:
        told = f"Your proposed {KINDS[post.kind].noun} “{post.title}” is published."
        notify(
            db,
            [post.proposed_by],
            f"{post.kind}.proposal_published",
            f"{told} {post.note}".strip() if post.note else told,
            link(post),
            troupe_id=troupe.id,
        )
    data = described(db, post)
    if by is None:
        data["scheduled"] = True
    actor = by or db.get(User, publisher)
    audit.record(db, actor, "post.published", troupe_id=troupe.id, **data)
    if post.important:
        audit.record(db, actor, "post.important", troupe_id=troupe.id, **described(db, post))


def tell_everyone(db: Session, troupe: Troupe, post: Post, publisher: uuid.UUID) -> None:
    """The bell for everyone in the troupe who keeps it on for this kind, and an
    email for those who want one (everyone, for an important announcement); never
    the person who published it."""
    people = [p for p in members(db, troupe) if p != publisher]
    if not people:
        return
    kind = f"{post.kind}.published"
    words = summary(db, post)
    bell = KINDS[post.kind].bell
    ringing = [
        u.id
        for u in db.scalars(select(User).where(User.id.in_(people)))
        if getattr(preferences.read(u), bell)
    ]
    notify(db, ringing, kind, words, link(post), troupe_id=troupe.id, email=False)
    notification_emails.queue(
        db, people, kind, words, link(post), troupe_id=troupe.id, forced=post.important
    )


def publish_due(db: Session, at: datetime | None = None, limit: int = 50) -> int:
    """Publish the scheduled posts whose time has come, each in its own transaction,
    locked so two workers never publish one twice. Returns how many."""
    published = 0
    while published < limit:
        post = db.scalar(
            select(Post)
            .where(Post.status == "scheduled", Post.publish_at <= (at or now()))
            .order_by(Post.publish_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if post is None:
            break
        publish(db, post, None)
        db.commit()
        published += 1
    return published


def publish_due_now() -> int:
    """`publish_due` in a session of its own, for the worker."""
    from horatio.db import get_sessionmaker

    with get_sessionmaker()() as db:
        return publish_due(db)


def unpublish(db: Session, post: Post, by: User) -> None:
    """Take a published post back: out of the app, off Discord, and back to a draft."""
    post.status = "draft"
    post.published_at = None
    queue_delete(db, post, by.id)
    audit.record(db, by, "post.unpublished", troupe_id=post.troupe_id, **described(db, post))


# --- reading --------------------------------------------------------------------------


def published(
    db: Session,
    troupe_id: uuid.UUID,
    kind: str,
    *,
    agency_id: uuid.UUID | None = None,
    before: datetime | None = None,
) -> tuple[list[Post], bool]:
    """Published posts, newest first, and whether there are older ones. The first
    page is the last 30 days, and at least the latest few; each older page, the
    next few before `before`. Announcements pinned now come first on the first page,
    and on no other."""
    query = select(Post).where(
        Post.troupe_id == troupe_id, Post.kind == kind, Post.status == "published"
    )
    if agency_id is not None:
        query = query.where(Post.agency_id == agency_id)
    query = query.order_by(Post.published_at.desc(), Post.id.desc())
    pins: list[Post] = []
    if kind == "announcement":
        at = now()
        if before is None:
            pins = list(db.scalars(query.where(Post.pinned_until > at)))
        query = query.where(or_(Post.pinned_until.is_(None), Post.pinned_until <= at))
    if before is not None:
        found = list(db.scalars(query.where(Post.published_at < before).limit(PAGE + 1)))
        return found[:PAGE], len(found) > PAGE
    since = now() - RECENT
    recent = list(db.scalars(query.where(Post.published_at >= since)))
    if len(recent) < AT_LEAST:
        recent = list(db.scalars(query.limit(AT_LEAST)))
    oldest = recent[-1].published_at if recent else None
    older = oldest is not None and bool(
        db.scalar(query.where(Post.published_at < oldest).limit(1).with_only_columns(Post.id))
    )
    return pins + recent, older


def read_ids(db: Session, user: User, posts: Sequence[Post]) -> set[uuid.UUID]:
    """Those of the posts the person has read."""
    if not posts:
        return set()
    return set(
        db.scalars(
            select(PostRead.post_id).where(
                PostRead.user_id == user.id, PostRead.post_id.in_([p.id for p in posts])
            )
        )
    )


def mark_read(db: Session, user: User, post_ids: Iterable[uuid.UUID]) -> None:
    ids = list(dict.fromkeys(post_ids))
    if ids:
        db.execute(
            insert(PostRead)
            .values([{"post_id": p, "user_id": user.id} for p in ids])
            .on_conflict_do_nothing(index_elements=["post_id", "user_id"])
        )


def unread_query(user: User, troupe_id: uuid.UUID, kind: str) -> Any:
    read = select(PostRead.post_id).where(PostRead.user_id == user.id)
    return select(Post).where(
        Post.troupe_id == troupe_id,
        Post.kind == kind,
        Post.status == "published",
        Post.id.not_in(read),
    )


def unread(db: Session, user: User, troupe_id: uuid.UUID, kind: str) -> int:
    """How many of the troupe's published posts of a kind the person has not read."""
    return (
        db.scalar(select(func.count()).select_from(unread_query(user, troupe_id, kind).subquery()))
        or 0
    )


def mark_all_read(db: Session, user: User, troupe_id: uuid.UUID, kind: str) -> None:
    mark_read(db, user, db.scalars(unread_query(user, troupe_id, kind).with_only_columns(Post.id)))


# --- pinned announcements --------------------------------------------------------------


def dismissed_ids(db: Session, user: User, posts: Sequence[Post]) -> set[uuid.UUID]:
    """Those of the posts whose banner the person has dismissed."""
    if not posts:
        return set()
    return set(
        db.scalars(
            select(PostDismissal.post_id).where(
                PostDismissal.user_id == user.id,
                PostDismissal.post_id.in_([p.id for p in posts]),
            )
        )
    )


def dismiss(db: Session, user: User, post: Post) -> None:
    """Hide a pinned announcement's banner, for this person only."""
    db.execute(
        insert(PostDismissal)
        .values(post_id=post.id, user_id=user.id)
        .on_conflict_do_nothing(index_elements=["post_id", "user_id"])
    )


def banners(db: Session, user: User, troupe_id: uuid.UUID) -> list[Post]:
    """The troupe's pinned announcements the person hasn't dismissed, newest first."""
    gone = select(PostDismissal.post_id).where(PostDismissal.user_id == user.id)
    return list(
        db.scalars(
            select(Post)
            .where(
                Post.troupe_id == troupe_id,
                Post.kind == "announcement",
                Post.status == "published",
                Post.pinned_until > now(),
                Post.id.not_in(gone),
            )
            .order_by(Post.published_at.desc(), Post.id.desc())
        )
    )

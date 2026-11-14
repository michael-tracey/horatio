"""A troupe's news (issue #510) and announcements (#511): news agencies, posts of
each kind, and the Discord channels they go to. What a post is and how it goes out
is in horatio.posts.

Every member of the troupe reads its published posts. Its storytellers and
assistant storytellers write, schedule, publish, edit, pin, unpublish and decline
them, and keep its agencies; a narrator proposes news stories and sees only their
own proposals, and has nothing to do with announcements. Choosing a Discord
channel is managing connectors, a storyteller's.
"""

import shutil
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, delivery, pictures, posts
from horatio.api.connectors import connector_row
from horatio.api.discord import ChannelOut
from horatio.api.pictures import uploads
from horatio.api.troupe_profiles import read_upload
from horatio.auth.deps import CurrentUser, DbSession
from horatio.connectors import SendError, discord
from horatio.models import Delivery, NewsAgency, Post, Troupe, User
from horatio.notifications import notify
from horatio.permissions import TroupeAction, allows, is_member, troupe_role

router = APIRouter(tags=["posts"])

Kind = Literal["news", "announcement"]
Status = Literal["draft", "proposed", "scheduled", "published", "declined"]
COLOUR = posts.COLOUR


# --- shapes ----------------------------------------------------------------------------


class AgencyOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    colour: str
    # Its masthead picture (add "/1200.webp" or "/600.webp"), or None for its name.
    picture: str | None
    # Its own Discord channel, or None for the troupe's news channel.
    discord_channel: str | None
    retired: bool


class AgencyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    colour: str = Field(default="#8b1e1e", pattern=COLOUR)
    # Its own channel, or None for the troupe's news channel. Left out of a change,
    # it stays as it is.
    discord_channel: str | None = None


class DiscordOut(BaseModel):
    """How a post stands on Discord, for its staff."""

    # "app_only": nowhere on Discord to send it (`reason` says why); "waiting" to
    # go; "sent"; or "failed" (`reason` says why), for staff to retry or mark sent.
    state: Literal["app_only", "waiting", "sent", "failed"]
    reason: str | None
    # When it is waiting after a failure, the next try.
    next_attempt_at: datetime | None


class PostOut(BaseModel):
    id: uuid.UUID
    troupe_id: uuid.UUID
    kind: Kind
    status: Status
    agency_id: uuid.UUID | None
    title: str
    body: str
    dateline: str
    # Its picture (add "/1200.webp" or "/600.webp"), or None.
    picture: str | None
    author: str
    # The narrator who proposed it, by name, and whether that is the caller.
    proposed_by: str | None
    mine: bool
    # The storytellers' note to the narrator who proposed it.
    note: str
    publish_at: datetime | None
    published_at: datetime | None
    # Published, and not yet read by the caller.
    unread: bool
    # An announcement's byline, once published: "Mara Quinn, Lead storyteller".
    byline: str
    # An announcement pinned to the front page until then; `pinned` while it is,
    # and `dismissed` once the caller has dismissed its banner.
    pinned_until: datetime | None
    pinned: bool
    dismissed: bool
    # An important announcement emails everyone, even those who turned it off.
    important: bool
    # For its storytellers and assistant storytellers: where it is on Discord, or
    # (not yet published) why it will be in the app only. None for anyone else.
    discord: DiscordOut | None


class PostPage(BaseModel):
    posts: list[PostOut]
    # There are older ones: ask with `before` the last one's published_at.
    older: bool


class Desk(BaseModel):
    """What staff are writing: every proposal, draft, scheduled and declined story
    for the storytellers and assistant storytellers; a narrator's own proposals."""

    posts: list[PostOut]
    # Whether the caller writes and publishes, or only proposes.
    writes: bool


class PostIn(BaseModel):
    agency_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=40_000)
    dateline: str = Field(default="", max_length=200)
    # An announcement's: pinned to the front page until then, and important.
    pinned_until: AwareDatetime | None = None
    important: bool = False


class NewPost(PostIn):
    kind: Kind = "news"


class ScheduleIn(BaseModel):
    publish_at: AwareDatetime


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=1000)


class Glance(BaseModel):
    """For the troupe's tabs and front page."""

    news_unread: int
    latest_news: PostOut | None
    # Announcements are counted apart from news, never with it.
    announcements_unread: int
    # Pinned announcements whose banner the caller hasn't dismissed, newest first.
    banners: list[PostOut]


class ChannelsOut(BaseModel):
    # The connected server's name, or why there is none to choose from.
    server: str | None
    unavailable: str | None
    channels: list[ChannelOut]
    # The channel chosen for each kind of post, if any.
    news: str | None
    announcements: str | None
    # Whether the caller may choose (a storyteller's, as connectors are).
    can_change: bool


class ChannelIn(BaseModel):
    kind: Kind
    channel: str | None


# --- who may ---------------------------------------------------------------------------


def running_troupe(db: Session, troupe_id: uuid.UUID) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def may(db: Session, user: User, troupe: Troupe, action: TroupeAction) -> bool:
    if troupe.archived_at is not None and not user.is_custodian:
        return False
    return allows(troupe_role(db, user, troupe), action, is_custodian=user.is_custodian)


def member_troupe(db: Session, user: User, troupe_id: uuid.UUID) -> Troupe:
    troupe = running_troupe(db, troupe_id)
    if not is_member(db, user, troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def writing_troupe(db: Session, user: User, troupe_id: uuid.UUID) -> Troupe:
    troupe = running_troupe(db, troupe_id)
    if not may(db, user, troupe, TroupeAction.WRITE_POSTS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot do that in this troupe.")
    return troupe


def going_out(troupe: Troupe) -> None:
    """Nothing goes out from an archived troupe, even at the custodian's hand: its
    members, Discord and email would hear from a troupe that is closed."""
    if troupe.archived_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This troupe is archived, so its posts don't go out."
        )


def proposing(db: Session, user: User, troupe: Troupe, post: Post) -> bool:
    """A narrator's own proposal, still waiting: theirs to see and edit."""
    return (
        post.kind == "news"
        and post.proposed_by == user.id
        and may(db, user, troupe, TroupeAction.PROPOSE_NEWS)
    )


def visible_post(db: Session, user: User, post_id: uuid.UUID, *, lock: bool = False) -> Post:
    """The post, if the caller may read it: published, for the troupe's members;
    any, for its storytellers and assistant storytellers; their own proposals, for a
    narrator. 404 otherwise, so nobody learns what is being written."""
    post = db.get(Post, post_id, with_for_update=lock)
    if post is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such post.")
    troupe = running_troupe(db, post.troupe_id)
    if post.status == "published" and is_member(db, user, troupe):
        return post
    if may(db, user, troupe, TroupeAction.WRITE_POSTS):
        return post
    if post.status in ("proposed", "declined") and proposing(db, user, troupe, post):
        return post
    raise HTTPException(status.HTTP_404_NOT_FOUND, "No such post.")


def written_post(db: Session, user: User, post_id: uuid.UUID) -> tuple[Post, Troupe, bool]:
    """The post, locked, if the caller may change it: storytellers and assistant
    storytellers any; a narrator their own while it is proposed. Also whether the
    caller writes (rather than only proposes)."""
    post = visible_post(db, user, post_id, lock=True)
    troupe = running_troupe(db, post.troupe_id)
    if may(db, user, troupe, TroupeAction.WRITE_POSTS):
        return post, troupe, True
    if post.status == "proposed" and proposing(db, user, troupe, post):
        return post, troupe, False
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the storytellers can change that now.")


def writer_post(db: Session, user: User, post_id: uuid.UUID) -> tuple[Post, Troupe]:
    post, troupe, writes = written_post(db, user, post_id)
    if not writes:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the storytellers and assistant storytellers can."
        )
    return post, troupe


# --- shaping ---------------------------------------------------------------------------


def agency_out(agency: NewsAgency) -> AgencyOut:
    return AgencyOut(
        id=agency.id,
        name=agency.name,
        description=agency.description,
        colour=agency.colour,
        picture=pictures.post_picture_url(agency.troupe_id, agency.picture_id),
        discord_channel=agency.discord_channel,
        retired=agency.retired_at is not None,
    )


def posts_out(db: Session, user: User, troupe: Troupe, found: list[Post]) -> list[PostOut]:
    """The posts as the caller sees them, asking the database a few times in all."""
    writes = may(db, user, troupe, TroupeAction.WRITE_POSTS)
    read = posts.read_ids(db, user, [p for p in found if p.status == "published"])
    dismissed = posts.dismissed_ids(db, user, [p for p in found if p.pinned_until])
    at = delivery.now()
    people = {p.author_id for p in found} | {p.proposed_by for p in found if p.proposed_by}
    names: dict[uuid.UUID, str] = {
        i: n for i, n in db.execute(select(User.id, User.display_name).where(User.id.in_(people)))
    }
    targets = posts.Targets(db, troupe.id) if writes else None
    latest: dict[uuid.UUID, Delivery] = {}
    if writes and found:
        for d in db.scalars(
            select(Delivery)
            .where(Delivery.post_id.in_([p.id for p in found]))
            .order_by(Delivery.created_at, Delivery.id)
        ):
            if d.post_id is not None:
                latest[d.post_id] = d
    return [
        PostOut(
            id=p.id,
            troupe_id=p.troupe_id,
            kind=p.kind,  # type: ignore[arg-type]  # checked by the database
            status=p.status,  # type: ignore[arg-type]  # checked by the database
            agency_id=p.agency_id,
            title=p.title,
            body=p.body,
            dateline=p.dateline,
            picture=pictures.post_picture_url(p.troupe_id, p.picture_id),
            author=names.get(p.author_id, ""),
            proposed_by=names.get(p.proposed_by) if p.proposed_by else None,
            mine=p.proposed_by == user.id or (p.proposed_by is None and p.author_id == user.id),
            note=p.note if writes or p.proposed_by == user.id else "",
            publish_at=p.publish_at,
            published_at=p.published_at,
            unread=p.status == "published" and p.id not in read,
            byline=p.byline,
            pinned_until=p.pinned_until,
            pinned=p.status == "published" and posts.pinned(p, at),
            dismissed=p.id in dismissed,
            important=p.important,
            discord=discord_out(p, targets, latest.get(p.id)) if targets else None,
        )
        for p in found
    ]


def discord_out(post: Post, targets: posts.Targets, last: Delivery | None) -> DiscordOut:
    target = targets.of(post)
    if last is not None and post.status == "published" and last.action == "sync":
        state = {"pending": "waiting", "sent": "sent", "failed": "failed"}[last.status]
        return DiscordOut(
            state=state,  # type: ignore[arg-type]  # one of the three
            reason=last.last_error if last.status != "sent" else None,
            next_attempt_at=last.next_attempt_at if last.status == "pending" else None,
        )
    if target.channel is None:
        return DiscordOut(state="app_only", reason=target.reason, next_attempt_at=None)
    return DiscordOut(state="waiting", reason=None, next_attempt_at=None)


def post_out(db: Session, user: User, post: Post) -> PostOut:
    return posts_out(db, user, running_troupe(db, post.troupe_id), [post])[0]


def check_agency(
    db: Session,
    troupe: Troupe,
    kind: str,
    agency_id: uuid.UUID | None,
    keeping: uuid.UUID | None = None,
) -> None:
    """News comes from one of the troupe's agencies, not retired (unless the story
    already had it)."""
    if kind != "news":
        return
    agency = db.get(NewsAgency, agency_id) if agency_id else None
    if agency is None or agency.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose the story's agency.")
    if agency.retired_at is not None and agency.id != keeping:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{agency.name} is retired; choose another."
        )


# --- reading ---------------------------------------------------------------------------


@router.get("/troupes/{troupe_id}/posts")
def list_posts(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    kind: Kind = "news",
    agency_id: uuid.UUID | None = None,
    before: AwareDatetime | None = None,
) -> PostPage:
    """The troupe's published posts of a kind, newest first: the last 30 days (and
    at least the latest few), or a page of older ones before `before`."""
    troupe = member_troupe(db, user, troupe_id)
    found, older = posts.published(db, troupe.id, kind, agency_id=agency_id, before=before)
    return PostPage(posts=posts_out(db, user, troupe, found), older=older)


@router.get("/troupes/{troupe_id}/posts/desk")
def desk(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser, kind: Kind = "news") -> Desk:
    """What is being written, not yet published."""
    troupe = running_troupe(db, troupe_id)
    writes = may(db, user, troupe, TroupeAction.WRITE_POSTS)
    query = select(Post).where(
        Post.troupe_id == troupe.id, Post.kind == kind, Post.status != "published"
    )
    if not writes:
        if kind != "news" or not may(db, user, troupe, TroupeAction.PROPOSE_NEWS):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot do that in this troupe.")
        query = query.where(Post.proposed_by == user.id, Post.status.in_(("proposed", "declined")))
    found = list(
        db.scalars(query.order_by(Post.publish_at, Post.updated_at.desc(), Post.id.desc()))
    )
    return Desk(posts=posts_out(db, user, troupe, found), writes=writes)


@router.get("/troupes/{troupe_id}/posts/glance")
def glance(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Glance:
    """How many posts of each kind the caller hasn't read, the latest headline, and
    the pinned announcements they haven't dismissed."""
    troupe = member_troupe(db, user, troupe_id)
    latest, _ = posts.published(db, troupe.id, "news")
    return Glance(
        news_unread=posts.unread(db, user, troupe.id, "news"),
        latest_news=posts_out(db, user, troupe, latest[:1])[0] if latest else None,
        announcements_unread=posts.unread(db, user, troupe.id, "announcement"),
        banners=posts_out(db, user, troupe, posts.banners(db, user, troupe.id)),
    )


@router.get("/posts/{post_id}")
def read_post(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PostOut:
    return post_out(db, user, visible_post(db, user, post_id))


@router.post("/posts/{post_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    post = visible_post(db, user, post_id)
    if post.status == "published":
        posts.mark_read(db, user, [post.id])
        db.commit()


@router.post("/troupes/{troupe_id}/posts/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser, kind: Kind = "news"
) -> None:
    troupe = member_troupe(db, user, troupe_id)
    posts.mark_all_read(db, user, troupe.id, kind)
    db.commit()


@router.post("/posts/{post_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_banner(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Hide a pinned announcement's banner from the front page, for the caller only.
    It stays at the top of the Announcements tab while it is pinned."""
    post = visible_post(db, user, post_id)
    if post.kind != "announcement" or post.status != "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an announcement has a banner.")
    posts.dismiss(db, user, post)
    db.commit()


# --- writing ---------------------------------------------------------------------------


@router.post("/troupes/{troupe_id}/posts", status_code=status.HTTP_201_CREATED)
def new_post(troupe_id: uuid.UUID, body: NewPost, db: DbSession, user: CurrentUser) -> PostOut:
    """A new draft; from a narrator, a proposal for the storytellers."""
    troupe = running_troupe(db, troupe_id)
    writes = may(db, user, troupe, TroupeAction.WRITE_POSTS)
    if not writes and not (
        body.kind == "news" and may(db, user, troupe, TroupeAction.PROPOSE_NEWS)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot do that in this troupe.")
    check_agency(db, troupe, body.kind, body.agency_id)
    check_pin(body)
    post = Post(
        troupe_id=troupe.id,
        kind=body.kind,
        status="draft" if writes else "proposed",
        agency_id=body.agency_id if body.kind == "news" else None,
        title=body.title.strip(),
        body=body.body,
        dateline=body.dateline.strip() if body.kind == "news" else "",
        author_id=user.id,
        proposed_by=None if writes else user.id,
        pinned_until=body.pinned_until if body.kind == "announcement" else None,
        important=body.important if body.kind == "announcement" else False,
    )
    db.add(post)
    db.commit()
    return post_out(db, user, post)


@router.put("/posts/{post_id}")
def change_post(post_id: uuid.UUID, body: PostIn, db: DbSession, user: CurrentUser) -> PostOut:
    """Change what a post says. A published one changes in the app at once and on
    Discord by the worker."""
    post, troupe, _ = written_post(db, user, post_id)
    check_agency(db, troupe, post.kind, body.agency_id, keeping=post.agency_id)
    news = post.kind == "news"
    said = (post.agency_id, post.title, post.body, post.dateline)
    post.agency_id = body.agency_id if news else None
    post.title = body.title.strip()
    post.body = body.body
    post.dateline = body.dateline.strip() if news else ""
    if not news:
        if body.pinned_until != post.pinned_until:
            check_pin(body)
            pin(db, user, post, body.pinned_until)
        post.important = body.important
    if said != (post.agency_id, post.title, post.body, post.dateline):
        edited(db, user, post)
    db.commit()
    return post_out(db, user, post)


def check_pin(body: PostIn) -> None:
    if body.pinned_until is not None and body.pinned_until <= delivery.now():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Pin it until a time to come, or not at all."
        )


def pin(db: Session, user: User, post: Post, until: datetime | None) -> None:
    """Pin an announcement until a time, or unpin it; a published one's pinning goes
    in the log."""
    post.pinned_until = until
    if post.status != "published":
        return
    if until is None:
        audit.record(
            db, user, "post.unpinned", troupe_id=post.troupe_id, **posts.described(db, post)
        )
    else:
        audit.record(
            db,
            user,
            "post.pinned",
            troupe_id=post.troupe_id,
            until=until.isoformat(),
            **posts.described(db, post),
        )


@router.post("/posts/{post_id}/unpin")
def unpin_post(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PostOut:
    """Take an announcement off the front page before its time."""
    post, _ = writer_post(db, user, post_id)
    if post.kind != "announcement" or post.pinned_until is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That isn't pinned.")
    pin(db, user, post, None)
    db.commit()
    return post_out(db, user, post)


def edited(db: Session, user: User, post: Post) -> None:
    """A published post changed: Discord follows, and the log says so."""
    if post.status != "published":
        return
    posts.queue_sync(db, post, user.id)
    audit.record(db, user, "post.edited", troupe_id=post.troupe_id, **posts.described(db, post))


@router.post("/posts/{post_id}/accept")
def accept_proposal(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PostOut:
    """Take up a narrator's proposal as a draft, to edit and publish later."""
    post, _ = writer_post(db, user, post_id)
    if post.status != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a proposal can be taken up.")
    post.status = "draft"
    db.commit()
    return post_out(db, user, post)


@router.post("/posts/{post_id}/schedule")
def schedule_post(
    post_id: uuid.UUID, body: ScheduleIn, db: DbSession, user: CurrentUser
) -> PostOut:
    """Publish it at a time to come; the worker publishes it then."""
    post, troupe = writer_post(db, user, post_id)
    if post.status not in ("draft", "proposed", "scheduled"):
        raise HTTPException(status.HTTP_409_CONFLICT, "That can't be scheduled now.")
    going_out(troupe)
    if body.publish_at <= delivery.now():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a time to come, or publish it now."
        )
    check_agency(db, troupe, post.kind, post.agency_id, keeping=post.agency_id)
    post.status = "scheduled"
    post.publish_at = body.publish_at
    post.published_by = user.id
    audit.record(
        db,
        user,
        "post.scheduled",
        troupe_id=troupe.id,
        at=body.publish_at.isoformat(),
        **posts.described(db, post),
    )
    db.commit()
    return post_out(db, user, post)


@router.post("/posts/{post_id}/unschedule")
def unschedule_post(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PostOut:
    """Cancel a scheduled post: it goes back to the drafts."""
    post, troupe = writer_post(db, user, post_id)
    if post.status != "scheduled":
        raise HTTPException(status.HTTP_409_CONFLICT, "That isn't scheduled.")
    post.status = "draft"
    post.publish_at = None
    audit.record(db, user, "post.unscheduled", troupe_id=troupe.id, **posts.described(db, post))
    db.commit()
    return post_out(db, user, post)


@router.post("/posts/{post_id}/publish")
def publish_post(post_id: uuid.UUID, body: NoteIn, db: DbSession, user: CurrentUser) -> PostOut:
    """Publish it now. A note goes to the narrator who proposed it, if one did."""
    post, troupe = writer_post(db, user, post_id)
    if post.status not in ("draft", "proposed", "scheduled"):
        raise HTTPException(status.HTTP_409_CONFLICT, "That can't be published now.")
    going_out(troupe)
    check_agency(db, troupe, post.kind, post.agency_id, keeping=post.agency_id)
    posts.publish(db, post, user, body.note.strip())
    db.commit()
    return post_out(db, user, post)


@router.post("/posts/{post_id}/unpublish")
def unpublish_post(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PostOut:
    """Take it out of the app and off Discord; it goes back to the drafts."""
    post, _ = writer_post(db, user, post_id)
    if post.status != "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "That isn't published.")
    posts.unpublish(db, post, user)
    db.commit()
    return post_out(db, user, post)


@router.post("/posts/{post_id}/decline")
def decline_proposal(post_id: uuid.UUID, body: NoteIn, db: DbSession, user: CurrentUser) -> PostOut:
    """Turn down a narrator's proposal, telling them, with a note if given."""
    post, troupe = writer_post(db, user, post_id)
    if post.status != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a proposal can be declined.")
    post.status = "declined"
    post.note = body.note.strip()
    if post.proposed_by is not None:
        told = f"Your proposed {posts.KINDS[post.kind].noun} “{post.title}” was declined."
        notify(
            db,
            [post.proposed_by],
            f"{post.kind}.proposal_declined",
            f"{told} {post.note}" if post.note else told,
            f"/troupes/{troupe.id}/{posts.KINDS[post.kind].path}/desk",
            troupe_id=troupe.id,
        )
    audit.record(db, user, "post.declined", troupe_id=troupe.id, **posts.described(db, post))
    db.commit()
    return post_out(db, user, post)


@router.post("/posts/{post_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_post(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PostOut:
    """A new draft with the same words, agency and picture."""
    post, troupe = writer_post(db, user, post_id)
    copy = Post(
        troupe_id=troupe.id,
        kind=post.kind,
        status="draft",
        agency_id=post.agency_id,
        title=post.title,
        body=post.body,
        dateline=post.dateline,
        author_id=user.id,
        important=post.important,
    )
    root = pictures.upload_dir()
    if post.picture_id is not None and root is not None:
        source = pictures.post_picture_dir(root, troupe.id, post.picture_id)
        if source.is_dir():
            new = uuid.uuid4()
            shutil.copytree(source, pictures.post_picture_dir(root, troupe.id, new))
            copy.picture_id = new
    db.add(copy)
    db.commit()
    return post_out(db, user, copy)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Throw away a post never published, or since unpublished: storytellers any,
    a narrator their own proposal."""
    post = visible_post(db, user, post_id, lock=True)
    troupe = running_troupe(db, post.troupe_id)
    writes = may(db, user, troupe, TroupeAction.WRITE_POSTS)
    if not writes and not (
        post.status in ("proposed", "declined") and proposing(db, user, troupe, post)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the storytellers can do that.")
    if post.status == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "Unpublish it first.")
    if post.discord or posts.waiting(db, post):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Horatio is still taking it off Discord. Try again in a minute.",
        )
    old = post.picture_id
    db.delete(post)
    db.commit()
    root = pictures.upload_dir()
    if root is not None and old is not None:
        pictures.remove(pictures.post_picture_dir(root, troupe.id, old))


# --- pictures --------------------------------------------------------------------------

PictureUpload = Annotated[UploadFile, File(description="JPEG, PNG, WebP or HEIC, up to 10 MB.")]


def save_picture(troupe_id: uuid.UUID, file: UploadFile) -> uuid.UUID:
    root = uploads()
    image = read_upload(file)
    new = uuid.uuid4()
    pictures.write_post_picture(pictures.post_picture_dir(root, troupe_id, new), image)
    return new


def drop_picture(troupe_id: uuid.UUID, picture_id: uuid.UUID | None) -> None:
    root = pictures.upload_dir()
    if root is not None and picture_id is not None:
        pictures.remove(pictures.post_picture_dir(root, troupe_id, picture_id))


@router.post("/posts/{post_id}/picture")
def upload_post_picture(
    post_id: uuid.UUID, file: PictureUpload, db: DbSession, user: CurrentUser
) -> PostOut:
    post, troupe, _ = written_post(db, user, post_id)
    old, new = post.picture_id, save_picture(troupe.id, file)
    post.picture_id = new
    with pictures.writing(pictures.post_picture_dir(uploads(), troupe.id, new)):
        edited(db, user, post)
        db.commit()
    drop_picture(troupe.id, old)
    return post_out(db, user, post)


@router.delete("/posts/{post_id}/picture")
def remove_post_picture(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PostOut:
    post, troupe, _ = written_post(db, user, post_id)
    old, post.picture_id = post.picture_id, None
    edited(db, user, post)
    db.commit()
    drop_picture(troupe.id, old)
    return post_out(db, user, post)


@router.get("/troupes/{troupe_id}/post-pictures/{picture_id}/{name}", response_class=FileResponse)
def post_picture(
    troupe_id: uuid.UUID, picture_id: uuid.UUID, name: str, db: DbSession, user: CurrentUser
) -> FileResponse:
    """A post's picture or a masthead, for the troupe's members. Its files never
    change (a new one has a new id), so browsers may keep them, privately."""
    troupe = member_troupe(db, user, troupe_id)
    root = pictures.upload_dir()
    path = pictures.post_picture_file(root, troupe.id, picture_id, name) if root else None
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such picture.")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


# --- Discord ---------------------------------------------------------------------------


def last_delivery(db: Session, post: Post) -> Delivery:
    found = db.scalar(
        select(Delivery)
        .where(Delivery.post_id == post.id)
        .order_by(Delivery.created_at.desc(), Delivery.id.desc())
        .limit(1)
        .with_for_update()
    )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "It hasn't been sent to Discord.")
    return found


@router.post("/posts/{post_id}/discord/retry")
def retry_post(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PostOut:
    """Try a failed post to Discord again, straight away."""
    post, troupe = writer_post(db, user, post_id)
    d = last_delivery(db, post)
    if d.status != "failed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a failed delivery can be retried.")
    delivery.retry(d)
    audit.record(
        db, user, "post.delivery_retried", troupe_id=troupe.id, **posts.described(db, post)
    )
    db.commit()
    return post_out(db, user, post)


@router.post("/posts/{post_id}/discord/mark-sent")
def mark_post_sent(post_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PostOut:
    """Record that someone saw to Discord by hand."""
    post, troupe = writer_post(db, user, post_id)
    d = last_delivery(db, post)
    if d.status == "sent":
        raise HTTPException(status.HTTP_409_CONFLICT, "That delivery was already sent.")
    delivery.mark_sent(d, user)
    audit.record(
        db, user, "post.delivery_marked_sent", troupe_id=troupe.id, **posts.described(db, post)
    )
    db.commit()
    return post_out(db, user, post)


def known_channel(guild_id: str, channel: str) -> str:
    """A channel of the connected server's, or 422."""
    try:
        channel = discord.snowflake(channel, "That")
        known = {c.id for c in discord.text_channels(guild_id)}
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except SendError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Could not check the channel: {error.reason}"
        ) from None
    if channel not in known:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Pick a channel from the connected server's text channels.",
        )
    return channel


@router.get("/troupes/{troupe_id}/post-channels")
def post_channels(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ChannelsOut:
    """The Discord channels the troupe's posts go to, and those to choose from."""
    troupe = writing_troupe(db, user, troupe_id)
    row = connector_row(db, troupe.id, "discord")
    settings = row.settings if row else {}
    guild_id = settings.get("guild_id")
    unavailable = discord.DiscordConnector().unavailable() or (
        None if guild_id else "No Discord server is connected."
    )
    channels: list[ChannelOut] = []
    if unavailable is None and guild_id:
        try:
            channels = [
                ChannelOut(**c.__dict__) for c in discord.text_channels(guild_id, permissions=True)
            ]
        except SendError as failure:
            unavailable = failure.reason
    chosen = settings.get("post_channels") or {}
    return ChannelsOut(
        server=settings.get("guild_name"),
        unavailable=unavailable,
        channels=channels,
        news=chosen.get("news"),
        announcements=chosen.get("announcement"),
        can_change=may(db, user, troupe, TroupeAction.MANAGE_CONNECTORS),
    )


@router.put("/troupes/{troupe_id}/post-channels")
def choose_post_channel(
    troupe_id: uuid.UUID, body: ChannelIn, db: DbSession, user: CurrentUser
) -> ChannelsOut:
    """Choose the channel for a kind of post, or none (in the app only)."""
    troupe = running_troupe(db, troupe_id)
    if not may(db, user, troupe, TroupeAction.MANAGE_CONNECTORS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the storytellers choose channels.")
    row = connector_row(db, troupe.id, "discord")
    guild_id = row.settings.get("guild_id") if row else None
    if row is None or not guild_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect a Discord server first.")
    channel = known_channel(guild_id, body.channel) if body.channel else None
    chosen = {**(row.settings.get("post_channels") or {}), body.kind: channel}
    row.settings = {**row.settings, "post_channels": {k: v for k, v in chosen.items() if v}}
    audit.record(
        db,
        user,
        "post.channel_chosen",
        troupe_id=troupe.id,
        what=f"{posts.KINDS[body.kind].channel} channel",
        state="chosen" if channel else "cleared",
    )
    db.commit()
    return post_channels(troupe.id, db, user)


# --- agencies --------------------------------------------------------------------------


@router.get("/troupes/{troupe_id}/agencies")
def list_agencies(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[AgencyOut]:
    """The troupe's news agencies, retired ones last, for its members."""
    troupe = running_troupe(db, troupe_id)
    if not is_member(db, user, troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    found = db.scalars(
        select(NewsAgency)
        .where(NewsAgency.troupe_id == troupe.id)
        .order_by(NewsAgency.retired_at.is_not(None), NewsAgency.name)
    )
    return [agency_out(a) for a in found]


def own_agency(db: Session, user: User, agency_id: uuid.UUID) -> tuple[NewsAgency, Troupe]:
    agency = db.get(NewsAgency, agency_id)
    if agency is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such agency.")
    return agency, writing_troupe(db, user, agency.troupe_id)


def agency_channel(
    db: Session, user: User, troupe: Troupe, now: str | None, wanted: str | None
) -> str | None:
    """An agency's own channel, which only those who manage connectors change."""
    wanted = wanted or None
    if wanted == now:
        return now
    if not may(db, user, troupe, TroupeAction.MANAGE_CONNECTORS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the storytellers choose channels.")
    if wanted is None:
        return None
    row = connector_row(db, troupe.id, "discord")
    guild_id = row.settings.get("guild_id") if row else None
    if not guild_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect a Discord server first.")
    return known_channel(guild_id, wanted)


@router.post("/troupes/{troupe_id}/agencies", status_code=status.HTTP_201_CREATED)
def new_agency(troupe_id: uuid.UUID, body: AgencyIn, db: DbSession, user: CurrentUser) -> AgencyOut:
    troupe = writing_troupe(db, user, troupe_id)
    channel = agency_channel(db, user, troupe, None, body.discord_channel)
    agency = posts.keep_agency(db, user, troupe, None, body.name, body.description, body.colour)
    agency.discord_channel = channel
    db.commit()
    return agency_out(agency)


@router.put("/agencies/{agency_id}")
def change_agency(
    agency_id: uuid.UUID, body: AgencyIn, db: DbSession, user: CurrentUser
) -> AgencyOut:
    agency, troupe = own_agency(db, user, agency_id)
    # Its channel is chosen under Connectors › Discord (#882): the agency's own form
    # leaves it out, and so leaves it as it is.
    if "discord_channel" in body.model_fields_set:
        agency.discord_channel = agency_channel(
            db, user, troupe, agency.discord_channel, body.discord_channel
        )
    posts.keep_agency(db, user, troupe, agency, body.name, body.description, body.colour)
    db.commit()
    return agency_out(agency)


@router.post("/agencies/{agency_id}/retire")
def retire_agency(agency_id: uuid.UUID, db: DbSession, user: CurrentUser) -> AgencyOut:
    """Take it off the list for new stories; its stories stay."""
    agency, troupe = own_agency(db, user, agency_id)
    if agency.retired_at is None:
        agency.retired_at = delivery.now()
        audit.record(db, user, "agency.retired", troupe_id=troupe.id, name=agency.name)
        db.commit()
    return agency_out(agency)


@router.post("/agencies/{agency_id}/restore")
def restore_agency(agency_id: uuid.UUID, db: DbSession, user: CurrentUser) -> AgencyOut:
    agency, troupe = own_agency(db, user, agency_id)
    if agency.retired_at is not None:
        agency.retired_at = None
        audit.record(db, user, "agency.restored", troupe_id=troupe.id, name=agency.name)
        db.commit()
    return agency_out(agency)


@router.post("/agencies/{agency_id}/picture")
def upload_masthead(
    agency_id: uuid.UUID, file: PictureUpload, db: DbSession, user: CurrentUser
) -> AgencyOut:
    """A masthead picture, shown in place of the agency's name."""
    agency, troupe = own_agency(db, user, agency_id)
    old, new = agency.picture_id, save_picture(troupe.id, file)
    agency.picture_id = new
    with pictures.writing(pictures.post_picture_dir(uploads(), troupe.id, new)):
        audit.record(db, user, "agency.masthead_changed", troupe_id=troupe.id, name=agency.name)
        db.commit()
    drop_picture(troupe.id, old)
    return agency_out(agency)


@router.delete("/agencies/{agency_id}/picture")
def remove_masthead(agency_id: uuid.UUID, db: DbSession, user: CurrentUser) -> AgencyOut:
    agency, troupe = own_agency(db, user, agency_id)
    old, agency.picture_id = agency.picture_id, None
    audit.record(db, user, "agency.masthead_changed", troupe_id=troupe.id, name=agency.name)
    db.commit()
    drop_picture(troupe.id, old)
    return agency_out(agency)

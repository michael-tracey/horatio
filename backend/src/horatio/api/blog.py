"""The game developer blog (#1156): writing articles, and the custodian's queue. What
an article is and how it moves along is in horatio.blog.

Staff of any troupe that is running write articles, and see only their own; the
custodian sees every one, and publishes, returns, unpublishes, features and tags
them. Nothing here is public yet: the blog's reading pages are #1158, and until
then a published article, and its hero picture, are shown only to its author and
the custodian.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import blog, pictures
from horatio.api.pictures import uploads
from horatio.api.troupe_profiles import read_upload
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import BlogPost, Troupe, User
from horatio.permissions import require_custodian

router = APIRouter(prefix="/blog", tags=["blog"])

Status = Literal["draft", "submitted", "published", "unpublished"]


# --- shapes ----------------------------------------------------------------------------


class BlogTagOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class BlogTroupeOut(BaseModel):
    """The troupe an article names."""

    id: uuid.UUID
    name: str
    # Archived since; the blog's pages won't link it (#1160).
    archived: bool


class BlogRevisionOut(BaseModel):
    """Changes to a published article, while the published version stays up."""

    title: str
    summary: str
    body: str
    troupe: BlogTroupeOut | None
    # Its hero picture (add "/1200.webp" or "/600.webp"), or None.
    picture: str | None
    # When they were sent to the custodian; None while still being written.
    submitted_at: datetime | None


class BlogArticleOut(BaseModel):
    id: uuid.UUID
    status: Status
    # Its address on the blog; `slug_fixed` once it has been published.
    slug: str
    slug_fixed: bool
    title: str
    summary: str
    body: str
    # Its hero picture (add "/1200.webp" or "/600.webp"), or None.
    picture: str | None
    author_id: uuid.UUID
    author_name: str
    troupe: BlogTroupeOut | None
    featured: bool
    # The custodian's note to the author: why it came back, or was unpublished.
    note: str
    tags: list[BlogTagOut]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    published_at: datetime | None
    revised_at: datetime | None
    unpublished_at: datetime | None
    revision: BlogRevisionOut | None
    # What waits for the custodian: the article, a published one's changes, or nothing.
    waiting: Literal["article", "changes"] | None
    # Whether the caller wrote it.
    mine: bool


class BlogWriterOut(BaseModel):
    """Whether the caller may write for the blog, and the troupes an article of theirs
    may name: those that are running where they're on staff."""

    can_write: bool
    troupes: list[BlogTroupeOut]


class BlogQueueOut(BaseModel):
    """For the custodian: articles and changes waiting, longest waiting first; then
    those published and unpublished, the latest first."""

    waiting: list[BlogArticleOut]
    published: list[BlogArticleOut]
    unpublished: list[BlogArticleOut]


class BlogArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=100_000)
    troupe_id: uuid.UUID | None = None


class BlogSlugIn(BaseModel):
    slug: str = Field(min_length=1, max_length=100)


class BlogNoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class BlogReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class BlogFeaturedIn(BaseModel):
    featured: bool


class BlogTagsIn(BaseModel):
    tag_ids: list[uuid.UUID] = Field(max_length=50)


# --- who may ---------------------------------------------------------------------------


def seen_article(db: Session, user: User, article_id: uuid.UUID, *, lock: bool = False) -> BlogPost:
    """The article, for its author or the custodian; 404 for anyone else, so nobody
    learns what is being written."""
    article = db.get(BlogPost, article_id, with_for_update=lock)
    if article is None or not (user.is_custodian or article.author_id == user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such article.")
    return article


def own_article(db: Session, user: User, article_id: uuid.UUID) -> BlogPost:
    """The article, locked, for its author alone: only they change its words."""
    article = seen_article(db, user, article_id, lock=True)
    if article.author_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only its author can change that.")
    return article


def custodian_article(db: Session, user: User, article_id: uuid.UUID) -> BlogPost:
    require_custodian(user)
    return seen_article(db, user, article_id, lock=True)


# --- shaping ---------------------------------------------------------------------------


def troupe_out(troupe: Troupe) -> BlogTroupeOut:
    return BlogTroupeOut(id=troupe.id, name=troupe.name, archived=troupe.archived_at is not None)


def articles_out(db: Session, user: User, found: list[BlogPost]) -> list[BlogArticleOut]:
    """The articles as the caller sees them, asking the database a few times in all."""
    revisions = {a.id: blog.revision_words(a) for a in found}
    troupe_ids = {a.troupe_id for a in found} | {
        r.troupe_id for r in revisions.values() if r is not None
    }
    troupes = {
        t.id: troupe_out(t)
        for t in db.scalars(select(Troupe).where(Troupe.id.in_(troupe_ids - {None})))
    }
    names: dict[uuid.UUID, str] = {
        i: n
        for i, n in db.execute(
            select(User.id, User.display_name).where(User.id.in_({a.author_id for a in found}))
        )
    }
    tags = blog.tags_of(db, [a.id for a in found])

    def revision_out(article: BlogPost) -> BlogRevisionOut | None:
        words = revisions[article.id]
        if words is None:
            return None
        return BlogRevisionOut(
            title=words.title,
            summary=words.summary,
            body=words.body,
            troupe=troupes.get(words.troupe_id) if words.troupe_id else None,
            picture=pictures.blog_picture_url(article.id, words.picture_id),
            submitted_at=article.revision_submitted_at,
        )

    return [
        BlogArticleOut(
            id=a.id,
            status=a.status,  # type: ignore[arg-type]  # checked by the database
            slug=a.slug,
            slug_fixed=a.published_at is not None,
            title=a.title,
            summary=a.summary,
            body=a.body,
            picture=pictures.blog_picture_url(a.id, a.picture_id),
            author_id=a.author_id,
            author_name=names.get(a.author_id, ""),
            troupe=troupes.get(a.troupe_id) if a.troupe_id else None,
            featured=a.featured,
            note=a.note,
            tags=[BlogTagOut(id=t.id, name=t.name, slug=t.slug) for t in tags[a.id]],
            created_at=a.created_at,
            updated_at=a.updated_at,
            submitted_at=a.submitted_at,
            published_at=a.published_at,
            revised_at=a.revised_at,
            unpublished_at=a.unpublished_at,
            revision=revision_out(a),
            waiting="changes"
            if blog.waiting_changes(a)
            else "article"
            if a.status == "submitted"
            else None,
            mine=a.author_id == user.id,
        )
        for a in found
    ]


def article_out(db: Session, user: User, article: BlogPost) -> BlogArticleOut:
    db.refresh(article)
    return articles_out(db, user, [article])[0]


def drop_picture(picture_id: uuid.UUID | None) -> None:
    root = pictures.upload_dir()
    if root is not None and picture_id is not None:
        pictures.remove(pictures.blog_picture_dir(root, picture_id))


# --- writing ---------------------------------------------------------------------------


@router.get("/tags")
def list_tags(db: DbSession, user: CurrentUser) -> list[BlogTagOut]:
    """The tags an article can be tagged with, in the custodian's order: not the
    retired ones, which stay only on the articles that have them (#1161)."""
    return [BlogTagOut(id=t.id, name=t.name, slug=t.slug) for t in blog.all_tags(db)]


@router.get("/writer")
def writer(db: DbSession, user: CurrentUser) -> BlogWriterOut:
    troupes = blog.writing_troupes(db, user)
    return BlogWriterOut(
        can_write=user.is_custodian or bool(troupes), troupes=[troupe_out(t) for t in troupes]
    )


@router.get("/articles/mine")
def my_articles(db: DbSession, user: CurrentUser) -> list[BlogArticleOut]:
    """The caller's own articles, the latest changed first."""
    found = list(
        db.scalars(
            select(BlogPost)
            .where(BlogPost.author_id == user.id)
            .order_by(BlogPost.updated_at.desc(), BlogPost.id.desc())
        )
    )
    return articles_out(db, user, found)


@router.post("/articles", status_code=status.HTTP_201_CREATED)
def new_article(body: BlogArticleIn, db: DbSession, user: CurrentUser) -> BlogArticleOut:
    """A new draft, by a member of staff of a troupe that is running, or the custodian."""
    article = blog.make(db, user, body.title, body.summary, body.body, body.troupe_id)
    db.commit()
    return article_out(db, user, article)


@router.get("/articles/{article_id}")
def read_article(article_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BlogArticleOut:
    return article_out(db, user, seen_article(db, user, article_id))


@router.put("/articles/{article_id}")
def change_article(
    article_id: uuid.UUID, body: BlogArticleIn, db: DbSession, user: CurrentUser
) -> BlogArticleOut:
    """Its author's change. A published article stays up as it is: the change is to
    its revision, for the custodian to publish once submitted."""
    article = own_article(db, user, article_id)
    blog.write(db, user, article, body.title, body.summary, body.body, body.troupe_id)
    db.commit()
    return article_out(db, user, article)


@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(article_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Its author throws away an article never published."""
    article = own_article(db, user, article_id)
    picture = blog.throw_away(db, user, article)
    db.commit()
    drop_picture(picture)


@router.post("/articles/{article_id}/submit")
def submit_article(article_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BlogArticleOut:
    """Send it, or a published article's changes, to the custodian to publish."""
    article = own_article(db, user, article_id)
    blog.submit(db, user, article)
    db.commit()
    return article_out(db, user, article)


@router.post("/articles/{article_id}/withdraw")
def withdraw_article(article_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BlogArticleOut:
    """Take it, or a published article's changes, back from the custodian's queue."""
    article = own_article(db, user, article_id)
    blog.withdraw(db, user, article)
    db.commit()
    return article_out(db, user, article)


@router.delete("/articles/{article_id}/revision")
def discard_revision(article_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BlogArticleOut:
    """Throw away a published article's changes; it stays as published."""
    article = own_article(db, user, article_id)
    picture = blog.discard_changes(db, user, article)
    db.commit()
    drop_picture(picture)
    return article_out(db, user, article)


@router.put("/articles/{article_id}/slug")
def change_slug(
    article_id: uuid.UUID, body: BlogSlugIn, db: DbSession, user: CurrentUser
) -> BlogArticleOut:
    """Its address on the blog, by its author or the custodian, until it is published."""
    article = seen_article(db, user, article_id, lock=True)
    blog.choose_slug(db, user, article, body.slug)
    db.commit()
    return article_out(db, user, article)


@router.put("/articles/{article_id}/tags")
def tag_article(
    article_id: uuid.UUID, body: BlogTagsIn, db: DbSession, user: CurrentUser
) -> BlogArticleOut:
    """Its tags: the custodian's at any time, its author's while it is being written."""
    article = seen_article(db, user, article_id, lock=True)
    blog.set_tags(db, user, article, body.tag_ids)
    db.commit()
    return article_out(db, user, article)


# --- its picture -----------------------------------------------------------------------

PictureUpload = Annotated[UploadFile, File(description="JPEG, PNG, WebP or HEIC, up to 10 MB.")]


@router.post("/articles/{article_id}/picture")
def upload_picture(
    article_id: uuid.UUID, file: PictureUpload, db: DbSession, user: CurrentUser
) -> BlogArticleOut:
    """Its hero picture, as a post's is kept (1200 and 600 px wide). On a published
    article it is part of the changes, so the old one stays up until they are."""
    article = own_article(db, user, article_id)
    blog.changeable(article)
    root = uploads()
    image = read_upload(file)
    new = uuid.uuid4()
    directory = pictures.blog_picture_dir(root, new)
    with pictures.writing(directory):
        pictures.write_post_picture(directory, image)
        old = blog.change_picture(article, new)
        db.commit()
    drop_picture(old)
    return article_out(db, user, article)


@router.delete("/articles/{article_id}/picture")
def remove_picture(article_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BlogArticleOut:
    article = own_article(db, user, article_id)
    old = blog.change_picture(article, None)
    db.commit()
    drop_picture(old)
    return article_out(db, user, article)


@router.get("/articles/{article_id}/pictures/{picture_id}/{name}", response_class=FileResponse)
def article_picture(
    article_id: uuid.UUID, picture_id: uuid.UUID, name: str, db: DbSession, user: CurrentUser
) -> FileResponse:
    """An article's hero picture, or its changes', for its author and the custodian
    until the blog's pages are public (#1158). Its files never change (a new one has
    a new id), so browsers may keep them, privately."""
    article = seen_article(db, user, article_id)
    revision = blog.revision_words(article)
    shown = {article.picture_id, revision.picture_id if revision else None} - {None}
    root = pictures.upload_dir()
    path = (
        pictures.blog_picture_file(root, picture_id, name)
        if root is not None and picture_id in shown
        else None
    )
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such picture.")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


# --- the custodian's -------------------------------------------------------------------


@router.get("/queue")
def queue(db: DbSession, user: CurrentUser) -> BlogQueueOut:
    """Custodian › Blog: what waits, then what is published and unpublished."""
    require_custodian(user)
    submitted = list(
        db.scalars(
            select(BlogPost).where(
                (BlogPost.status == "submitted") | BlogPost.revision_submitted_at.is_not(None)
            )
        )
    )

    def asked(article: BlogPost) -> datetime:
        waited = article.revision_submitted_at or article.submitted_at
        assert waited is not None
        return waited

    submitted.sort(key=lambda a: (asked(a), a.id))
    published = list(
        db.scalars(
            select(BlogPost)
            .where(BlogPost.status == "published")
            .order_by(BlogPost.published_at.desc(), BlogPost.id.desc())
        )
    )
    unpublished = list(
        db.scalars(
            select(BlogPost)
            .where(BlogPost.status == "unpublished")
            .order_by(BlogPost.unpublished_at.desc(), BlogPost.id.desc())
        )
    )
    shaped = {
        a.id: out
        for a, out in zip(
            submitted + published + unpublished,
            articles_out(db, user, submitted + published + unpublished),
            strict=True,
        )
    }
    return BlogQueueOut(
        waiting=[shaped[a.id] for a in submitted],
        published=[shaped[a.id] for a in published],
        unpublished=[shaped[a.id] for a in unpublished],
    )


@router.post("/articles/{article_id}/publish")
def publish_article(article_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BlogArticleOut:
    """Publish an article waiting, or put up a published one's changes in place of
    the old."""
    article = custodian_article(db, user, article_id)
    gone = blog.publish(db, user, article)
    db.commit()
    drop_picture(gone)
    return article_out(db, user, article)


@router.post("/articles/{article_id}/return")
def return_article(
    article_id: uuid.UUID, body: BlogNoteIn, db: DbSession, user: CurrentUser
) -> BlogArticleOut:
    """Send an article waiting, or a published one's changes, back to its author with
    a note."""
    article = custodian_article(db, user, article_id)
    blog.send_back(db, user, article, body.note)
    db.commit()
    return article_out(db, user, article)


@router.post("/articles/{article_id}/unpublish")
def unpublish_article(
    article_id: uuid.UUID, body: BlogReasonIn, db: DbSession, user: CurrentUser
) -> BlogArticleOut:
    """Take a published article down, telling its author why."""
    article = custodian_article(db, user, article_id)
    gone = blog.unpublish(db, user, article, body.reason)
    db.commit()
    drop_picture(gone)
    return article_out(db, user, article)


@router.put("/articles/{article_id}/featured")
def feature_article(
    article_id: uuid.UUID, body: BlogFeaturedIn, db: DbSession, user: CurrentUser
) -> BlogArticleOut:
    article = custodian_article(db, user, article_id)
    blog.feature(db, user, article, body.featured)
    db.commit()
    return article_out(db, user, article)

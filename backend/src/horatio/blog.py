"""The game developer blog (tracker #1155): articles that staff of any troupe write
on playing and running a game, which the custodian publishes for everyone (#1156).
They aren't a troupe's posts (horatio.posts): an article belongs to no troupe,
though it may name one its author runs.

Who writes: any member of staff (lead storyteller, storyteller, assistant storyteller
or narrator) of a troupe that isn't archived, and the custodian. The troupe an
article names must be one where its author is on staff then, checked again as they
submit it; it stays named if they leave later. It may name none.

An article is, in turn:

- `draft`: being written. Only its author and the custodian see it. One the
  custodian returns is a draft again, with their note.
- `submitted`: waiting in the custodian's queue (Custodian › Blog). Its author
  withdraws it, back to a draft, to change it.
- `published`: on the blog. Changing it writes a revision, which waits for the
  custodian as the article did while the published version stays up: publishing it
  puts it up in place of the old, returning it leaves the article as it was.
- `unpublished`: taken down by the custodian, with a reason. Its author can change
  it and submit it again; any revision it had becomes the article itself, as only
  one version is needed once nothing is public.

Its slug, its address on the blog, is made from the title, unique, and follows the
title until its author or the custodian sets one by hand. Once it is first
published the slug never changes, so links to it never break.

Pictures in its words (#1163) are uploaded for the article and named in its Markdown
as `blog-picture:<id>`, never by an outside address. Anyone sees one once the
published article's words name it; until then, only its author and the custodian,
so a published article's changes show nobody their new pictures before the
custodian publishes them. One that no version of the article names any more is
deleted whenever its words change hands: saved, published, thrown away or
unpublished.

Each article or change waiting is a task on the custodian's bell
(horatio.notifications), which goes once they publish or return it or its author
withdraws it. The custodian publishes, returns with a note, unpublishes with a
reason, features and tags. The author hears of each of the first three on the bell,
and every step goes in the audit log, outside any troupe's log (no troupe_id): the
blog is the whole site's. Everyone else hears of an article once, when it is first
published (horatio.blog_bell).
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import (
    BlogPost,
    BlogPostPicture,
    BlogPostTag,
    BlogTag,
    Troupe,
    TroupeStaff,
    User,
)
from horatio.notifications import blog_article_waiting, notify
from horatio.permissions import TROUPE_POLICY, TroupeAction

STATUSES = ("draft", "submitted", "published", "unpublished")
# The longest slug made from a title, before any "-2" that keeps it unique.
SLUG_LENGTH = 80
# Addresses under /blog that are the blog's own pages, not articles (#1158).
RESERVED_SLUGS = frozenset({"write", "tags", "authors", "feed", "rss"})
# The most pictures an article's words keep at once (#1163).
PICTURE_LIMIT = 20
# A picture in an article's words, as its Markdown names it.
BODY_PICTURE = re.compile(
    r"blog-picture:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)


def now() -> datetime:
    from horatio import delivery

    return delivery.now()


def link(article: BlogPost) -> str:
    """Where its author works on it (#1157 makes this the writing page)."""
    return f"/blog/write/{article.id}"


# --- who writes ---------------------------------------------------------------------------


def writing_troupes(db: Session, user: User) -> list[Troupe]:
    """The troupes that aren't archived where `user` is on staff, in any role: those
    an article of theirs may name."""
    roles = [r.value for r in TROUPE_POLICY[TroupeAction.WRITE_BLOG]]
    staffed = select(TroupeStaff.troupe_id).where(
        TroupeStaff.user_id == user.id, TroupeStaff.role.in_(roles)
    )
    return list(
        db.scalars(
            select(Troupe)
            .where(
                Troupe.archived_at.is_(None),
                or_(Troupe.lead_user_id == user.id, Troupe.id.in_(staffed)),
            )
            .order_by(Troupe.name, Troupe.id)
        )
    )


def may_write(db: Session, user: User) -> bool:
    return user.is_custodian or bool(writing_troupes(db, user))


def require_writer(db: Session, user: User) -> None:
    if not may_write(db, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the staff of a troupe that is running can write for the blog.",
        )


def check_troupe(
    db: Session, user: User, troupe_id: uuid.UUID | None, keeping: uuid.UUID | None = None
) -> None:
    """An article names a troupe where its author is on staff, or none. One it names
    already may stay while it is being written; submitting checks it again."""
    if troupe_id is None or troupe_id == keeping:
        return
    if troupe_id not in {t.id for t in writing_troupes(db, user)}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Choose a troupe where you're on staff, or none.",
        )


# --- slugs --------------------------------------------------------------------------------


def slugify(text: str, fallback: str = "article") -> str:
    """A slug from a title: "Running Your First Elysium!" is running-your-first-elysium.
    `fallback` for a title with nothing to make one from. Tags' are made the same way
    (horatio.blog_tags)."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    return slug[:SLUG_LENGTH].rstrip("-") or fallback


def free_slug(db: Session, wanted: str, keeping: uuid.UUID | None = None) -> str:
    """`wanted`, or with -2, -3... after it if another article has it."""
    query = select(BlogPost.slug).where(
        or_(BlogPost.slug == wanted, BlogPost.slug.startswith(f"{wanted}-"))
    )
    if keeping is not None:
        query = query.where(BlogPost.id != keeping)
    taken = set(db.scalars(query)) | RESERVED_SLUGS
    n = 1
    slug = wanted
    while slug in taken:
        n += 1
        slug = f"{wanted}-{n}"
    return slug


def follow_title(db: Session, article: BlogPost) -> None:
    """The slug follows the title until it is set by hand or first published."""
    if not article.slug_chosen and article.published_at is None:
        article.slug = free_slug(db, slugify(article.title), article.id)


def choose_slug(db: Session, user: User, article: BlogPost, wanted: str) -> None:
    """The author or the custodian sets the slug by hand, before it is first published."""
    if article.published_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Its address is fixed once it has been published, so links to it keep working.",
        )
    slug = slugify(wanted)
    clash = db.scalar(
        select(BlogPost.id).where(BlogPost.slug == slug, BlogPost.id != article.id).limit(1)
    )
    if slug in RESERVED_SLUGS:
        raise HTTPException(status.HTTP_409_CONFLICT, "That address is one of the blog's own.")
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Another article has that address.")
    article.slug_chosen = True
    if slug != article.slug:
        was = article.slug
        article.slug = slug
        audit.record(db, user, "blog.slug_changed", **described(article), slug=slug, was=was)


# --- what is being written ----------------------------------------------------------------


@dataclass(frozen=True)
class Words:
    """What its author writes: on the article itself, or on its revision."""

    title: str
    summary: str
    body: str
    troupe_id: uuid.UUID | None
    picture_id: uuid.UUID | None


def published_words(article: BlogPost) -> Words:
    return Words(
        article.title, article.summary, article.body, article.troupe_id, article.picture_id
    )


def revision_words(article: BlogPost) -> Words | None:
    found = article.revision
    if found is None:
        return None
    return Words(
        found["title"],
        found["summary"],
        found["body"],
        uuid.UUID(found["troupe_id"]) if found.get("troupe_id") else None,
        uuid.UUID(found["picture_id"]) if found.get("picture_id") else None,
    )


def stored(words: Words) -> dict[str, Any]:
    return {
        "title": words.title,
        "summary": words.summary,
        "body": words.body,
        "troupe_id": str(words.troupe_id) if words.troupe_id else None,
        "picture_id": str(words.picture_id) if words.picture_id else None,
    }


def working(article: BlogPost) -> Words:
    """What its author is working on: a published article's revision, if it has one,
    else the article."""
    return revision_words(article) or published_words(article)


def put_up(article: BlogPost, words: Words) -> uuid.UUID | None:
    """Make `words` the article's own. Returns the picture it no longer shows, whose
    files can go once this is saved."""
    old = article.picture_id
    article.title = words.title
    article.summary = words.summary
    article.body = words.body
    article.troupe_id = words.troupe_id
    article.picture_id = words.picture_id
    return old if old is not None and old != words.picture_id else None


def described(article: BlogPost, *, changes: bool = False) -> dict[str, Any]:
    """What the log keeps about an article, so it reads the same later."""
    return {
        "article_id": article.id,
        "what": "changes to the blog article" if changes else "the blog article",
        "title": article.title,
    }


def waiting_changes(article: BlogPost) -> bool:
    return article.status == "published" and article.revision_submitted_at is not None


# --- the author's ---------------------------------------------------------------------------


def make(
    db: Session, user: User, title: str, summary: str, body: str, troupe_id: uuid.UUID | None
) -> BlogPost:
    require_writer(db, user)
    check_troupe(db, user, troupe_id)
    article = BlogPost(
        author_id=user.id,
        troupe_id=troupe_id,
        title=title.strip(),
        summary=summary.strip(),
        body=body,
        slug="",
    )
    article.slug = free_slug(db, slugify(article.title))
    db.add(article)
    db.flush()
    audit.record(db, user, "blog.created", **described(article))
    return article


def changeable(article: BlogPost) -> None:
    """Its author changes it while it is theirs: not while it waits for the custodian."""
    if article.status == "submitted":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "It is waiting for the custodian: withdraw it to change it."
        )
    if waiting_changes(article):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Your changes are waiting for the custodian: withdraw them to change them again.",
        )


def write(
    db: Session,
    user: User,
    article: BlogPost,
    title: str,
    summary: str,
    body: str,
    troupe_id: uuid.UUID | None,
) -> None:
    """Its author's change: to the article, or, once it is published, to its revision."""
    changeable(article)
    before = working(article)
    check_troupe(db, user, troupe_id, keeping=before.troupe_id)
    words = Words(title.strip(), summary.strip(), body, troupe_id, before.picture_id)
    if article.status == "published":
        article.revision = stored(words)
        return
    put_up(article, words)
    follow_title(db, article)


def change_picture(article: BlogPost, picture_id: uuid.UUID | None) -> uuid.UUID | None:
    """A new hero picture (or none): on the article, or on its revision once it is
    published. Returns the picture whose files can go once this is saved."""
    changeable(article)
    if article.status != "published":
        old = article.picture_id
        article.picture_id = picture_id
        return old if old != picture_id else None
    words = working(article)
    article.revision = stored(
        Words(words.title, words.summary, words.body, words.troupe_id, picture_id)
    )
    old = words.picture_id
    # The published picture stays until the changes are published.
    return old if old not in (picture_id, article.picture_id) else None


def submit(db: Session, user: User, article: BlogPost) -> None:
    """Send the article, or a published one's changes, to the custodian. Its author
    must still be on the staff of a troupe that is running, and of the troupe it
    names."""
    require_writer(db, user)
    words = working(article)
    if words.troupe_id is not None and words.troupe_id not in {
        t.id for t in writing_troupes(db, user)
    }:
        troupe = db.get(Troupe, words.troupe_id)
        named = troupe.name if troupe else "that troupe"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You're no longer on the staff of {named}, or it is archived: choose another"
            " troupe, or none.",
        )
    if not words.title.strip() or not words.body.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Write the article before you submit it."
        )
    if article.status == "submitted" or waiting_changes(article):
        raise HTTPException(status.HTTP_409_CONFLICT, "It is already waiting for the custodian.")
    if article.status == "published":
        if article.revision is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Change it first: it is published as it is."
            )
        article.revision_submitted_at = now()
        audit.record(db, user, "blog.submitted", **described(article, changes=True))
    else:
        article.status = "submitted"
        article.submitted_at = now()
        audit.record(db, user, "blog.submitted", **described(article))
    blog_article_waiting(db, article, user)


def withdraw(db: Session, user: User, article: BlogPost) -> None:
    """Take the article, or a published one's changes, back from the custodian's queue."""
    if waiting_changes(article):
        article.revision_submitted_at = None
        audit.record(db, user, "blog.withdrawn", **described(article, changes=True))
        return
    if article.status != "submitted":
        raise HTTPException(status.HTTP_409_CONFLICT, "It isn't waiting for the custodian.")
    article.status = "draft"
    audit.record(db, user, "blog.withdrawn", **described(article))


def discard_changes(db: Session, user: User, article: BlogPost) -> uuid.UUID | None:
    """Throw away a published article's changes, leaving it as published. Returns
    the picture whose files can go once this is saved."""
    changeable(article)
    words = revision_words(article)
    if words is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "It has no changes to throw away.")
    article.revision = None
    audit.record(db, user, "blog.changes_discarded", **described(article))
    return words.picture_id if words.picture_id != article.picture_id else None


def throw_away(db: Session, user: User, article: BlogPost) -> uuid.UUID | None:
    """Delete an article never published, as long as it isn't waiting for the
    custodian. Returns its picture, whose files can go once this is saved."""
    if article.published_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "It has been published, so it stays: the custodian can unpublish it.",
        )
    changeable(article)
    audit.record(db, user, "blog.deleted", **described(article))
    picture = article.picture_id
    db.delete(article)
    return picture


# --- the custodian's ----------------------------------------------------------------------


def publish(db: Session, user: User, article: BlogPost) -> uuid.UUID | None:
    """Publish an article waiting for the custodian, or put up a published one's
    changes in place of the old. Returns the picture no longer shown, whose files
    can go once this is saved."""
    at = now()
    gone: uuid.UUID | None = None
    if waiting_changes(article):
        words = revision_words(article)
        assert words is not None
        gone = put_up(article, words)
        article.revision = None
        article.revision_submitted_at = None
        article.revised_at = at
        article.note = ""
        told = f"Your changes to “{article.title}” are published on the blog."
        audit.record(db, user, "blog.published", **described(article, changes=True))
    elif article.status == "submitted":
        if article.published_at is None:
            article.published_at = at
        else:
            # Back after it was unpublished.
            article.revised_at = at
        article.status = "published"
        article.published_by = user.id
        article.unpublished_at = None
        article.note = ""
        told = f"Your article “{article.title}” is published on the blog."
        audit.record(db, user, "blog.published", **described(article))
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "It isn't waiting to be published.")
    notify(db, [article.author_id], "blog.published", told, link(article))
    return gone


def send_back(db: Session, user: User, article: BlogPost, note: str) -> None:
    """Return an article waiting for the custodian to its author, with a note: a draft
    again, or, for a published one's changes, the changes to work on while the
    article stays up as it was."""
    note = note.strip()
    if waiting_changes(article):
        article.revision_submitted_at = None
        told = f"The custodian returned your changes to “{article.title}”: {note}"
        audit.record(db, user, "blog.returned", **described(article, changes=True), note=note)
    elif article.status == "submitted":
        article.status = "draft"
        told = f"The custodian returned your article “{article.title}”: {note}"
        audit.record(db, user, "blog.returned", **described(article), note=note)
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "It isn't waiting for you.")
    article.note = note
    notify(db, [article.author_id], "blog.returned", told, link(article))


def unpublish(db: Session, user: User, article: BlogPost, reason: str) -> uuid.UUID | None:
    """Take a published article down, with a reason its author is told. Any changes
    it had become the article, nothing of it being public now. Returns the picture
    no longer kept, whose files can go once this is saved."""
    if article.status != "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "It isn't published.")
    reason = reason.strip()
    gone: uuid.UUID | None = None
    words = revision_words(article)
    if words is not None:
        gone = put_up(article, words)
        article.revision = None
        article.revision_submitted_at = None
    article.status = "unpublished"
    article.unpublished_at = now()
    article.featured = False
    article.note = reason
    audit.record(db, user, "blog.unpublished", **described(article), reason=reason)
    notify(
        db,
        [article.author_id],
        "blog.unpublished",
        f"The custodian unpublished your article “{article.title}”: {reason}",
        link(article),
    )
    return gone


def feature(db: Session, user: User, article: BlogPost, featured: bool) -> None:
    if featured and article.status != "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a published article can be featured.")
    if article.featured == featured:
        return
    article.featured = featured
    audit.record(db, user, "blog.featured" if featured else "blog.unfeatured", **described(article))


# --- pictures in its words ----------------------------------------------------------------


def pictures_in(body: str) -> set[uuid.UUID]:
    """The pictures the words name."""
    return {uuid.UUID(found) for found in BODY_PICTURE.findall(body)}


def check_pictures(db: Session, article_id: uuid.UUID | None, body: str) -> None:
    """Words name only pictures uploaded for their own article."""
    named = pictures_in(body)
    if not named:
        return
    kept = (
        set(
            db.scalars(
                select(BlogPostPicture.id).where(
                    BlogPostPicture.post_id == article_id, BlogPostPicture.id.in_(named)
                )
            )
        )
        if article_id is not None
        else set()
    )
    if named - kept:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A picture in it isn't one of this article's, or was taken out when it was saved:"
            " take it out and add it again.",
        )


def add_picture(db: Session, article: BlogPost) -> BlogPostPicture:
    """A new picture for the article's words, while its author may change them."""
    changeable(article)
    count = db.scalar(
        select(func.count())
        .select_from(BlogPostPicture)
        .where(BlogPostPicture.post_id == article.id)
    )
    if (count or 0) >= PICTURE_LIMIT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"An article can have up to {PICTURE_LIMIT} pictures. Take out one you don't"
            " need and save it, then add another.",
        )
    picture = BlogPostPicture(post_id=article.id)
    db.add(picture)
    db.flush()
    return picture


def picture_public(article: BlogPost, picture_id: uuid.UUID) -> bool:
    """Anyone's to see: in the words of the article as published. Not a published
    article's changes', until the custodian publishes them."""
    return article.status == "published" and picture_id in pictures_in(article.body)


def unused_pictures(db: Session, article: BlogPost) -> list[uuid.UUID]:
    """Forget the article's pictures that neither its words nor its changes' name.
    Returns them, whose files can go once this is saved."""
    named = pictures_in(article.body)
    revision = revision_words(article)
    if revision is not None:
        named |= pictures_in(revision.body)
    gone = [
        p
        for p in db.scalars(select(BlogPostPicture).where(BlogPostPicture.post_id == article.id))
        if p.id not in named
    ]
    for picture in gone:
        db.delete(picture)
    return [p.id for p in gone]


# --- tags ---------------------------------------------------------------------------------


def all_tags(db: Session, *, retired: bool = False) -> list[BlogTag]:
    """The tags, in the list's order: those an article can be tagged with, or with
    `retired`, the retired ones too, which stay on the articles that have them
    (horatio.blog_tags)."""
    query = select(BlogTag).order_by(BlogTag.position, BlogTag.name)
    if not retired:
        query = query.where(BlogTag.retired_at.is_(None))
    return list(db.scalars(query))


def tags_of(db: Session, article_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[BlogTag]]:
    """Each article's tags, in the list's order."""
    found: dict[uuid.UUID, list[BlogTag]] = {a: [] for a in article_ids}
    if not article_ids:
        return found
    for post_id, tag in db.execute(
        select(BlogPostTag.post_id, BlogTag)
        .join(BlogTag, BlogTag.id == BlogPostTag.tag_id)
        .where(BlogPostTag.post_id.in_(article_ids))
        .order_by(BlogTag.position, BlogTag.name)
    ):
        found[post_id].append(tag)
    return found


def set_tags(db: Session, user: User, article: BlogPost, tag_ids: list[uuid.UUID]) -> None:
    """Tag the article: the custodian at any time, its author while it isn't
    published or waiting. A retired tag it has may stay, but isn't added."""
    if not user.is_custodian and article.status in ("published", "submitted"):
        raise HTTPException(status.HTTP_409_CONFLICT, "The custodian tags it once it is submitted.")
    wanted = list(dict.fromkeys(tag_ids))
    tags = list(db.scalars(select(BlogTag).where(BlogTag.id.in_(wanted)))) if wanted else []
    if len(tags) != len(wanted):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No such tag.")
    before = {t.id for t in tags_of(db, [article.id])[article.id]}
    for t in tags:
        if t.retired_at is not None and t.id not in before:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{t.name} is retired: it stays on the articles that have it, but isn't chosen"
                " for any more.",
            )
    if before == set(wanted):
        return
    db.execute(delete(BlogPostTag).where(BlogPostTag.post_id == article.id))
    db.add_all(BlogPostTag(post_id=article.id, tag_id=t) for t in wanted)
    names = ", ".join(t.name for t in sorted(tags, key=lambda t: (t.position, t.name)))
    audit.record(db, user, "blog.tagged", **described(article), tags=names or "none")

"""The blog's tags, as the custodian keeps them (#1161): in Custodian › Blog › Tags they
add, rename, merge, retire, bring back and reorder them. Articles are tagged in
horatio.blog.

A tag's name is unique whatever the case. Its slug, its address on the blog's tag
pages (#1158), is made from the name and follows it on a rename until an article that
has been published carries the tag; after that it stays, so links to the tag page keep
working. A retired tag stays on the articles that have it, and shows on them, but
isn't chosen for any more. Merging one tag into another moves it off every article
onto the other, then removes it; its address is kept as an alias of the other
(#1184), so its page and feed lead there, as do the aliases it had itself, so a
chain of merges leads to the last tag. No tag takes an alias's slug.

Every change goes in the audit log, as the blog's other steps do (blog.*).
"""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from horatio import audit
from horatio.blog import now, slugify
from horatio.models import BlogPost, BlogPostTag, BlogTag, BlogTagAlias, User


@dataclass(frozen=True)
class Kept:
    """A tag as the custodian sees it, with how many articles carry it."""

    tag: BlogTag
    articles: int
    published: int
    # Whether its slug stays put on a rename now: a published article carries it.
    slug_fixed: bool


def kept(db: Session) -> list[Kept]:
    """Every tag, retired ones too, in the list's order."""
    counts = {
        tag_id: (articles, published, bool(fixed))
        for tag_id, articles, published, fixed in db.execute(
            select(
                BlogPostTag.tag_id,
                func.count(),
                func.count().filter(BlogPost.status == "published"),
                func.bool_or(BlogPost.published_at.is_not(None)),
            )
            .join(BlogPost, BlogPost.id == BlogPostTag.post_id)
            .group_by(BlogPostTag.tag_id)
        )
    }
    tags = db.scalars(select(BlogTag).order_by(BlogTag.position, BlogTag.name))
    return [Kept(t, *counts.get(t.id, (0, 0, False))) for t in tags]


def slug_fixed(db: Session, tag: BlogTag) -> bool:
    """Whether an article that has been published carries the tag, so its address may
    be linked to already."""
    return (
        db.scalar(
            select(BlogPostTag.id)
            .join(BlogPost, BlogPost.id == BlogPostTag.post_id)
            .where(BlogPostTag.tag_id == tag.id, BlogPost.published_at.is_not(None))
            .limit(1)
        )
        is not None
    )


def free_slug(db: Session, wanted: str, keeping: uuid.UUID | None = None) -> str:
    """`wanted`, or with -2, -3... after it if another tag has it, or it is an alias:
    a merged tag's old address, which leads on to another tag for good."""
    query = select(BlogTag.slug).where(
        or_(BlogTag.slug == wanted, BlogTag.slug.startswith(f"{wanted}-"))
    )
    if keeping is not None:
        query = query.where(BlogTag.id != keeping)
    aliases = select(BlogTagAlias.slug).where(
        or_(BlogTagAlias.slug == wanted, BlogTagAlias.slug.startswith(f"{wanted}-"))
    )
    taken = set(db.scalars(query)) | set(db.scalars(aliases))
    n = 1
    slug = wanted
    while slug in taken:
        n += 1
        slug = f"{wanted}-{n}"
    return slug


def check_name(db: Session, name: str, keeping: uuid.UUID | None = None) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the tag a name.")
    query = select(BlogTag.name).where(func.lower(BlogTag.name) == name.lower())
    if keeping is not None:
        query = query.where(BlogTag.id != keeping)
    clash = db.scalar(query.limit(1))
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"There is already a tag called {clash}.")
    return name


def find(db: Session, tag_id: uuid.UUID) -> BlogTag:
    tag = db.get(BlogTag, tag_id, with_for_update=True)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such tag.")
    return tag


def add(db: Session, user: User, name: str) -> BlogTag:
    """A new tag, at the end of the list."""
    name = check_name(db, name)
    last = db.scalar(select(func.max(BlogTag.position)))
    tag = BlogTag(
        name=name,
        slug=free_slug(db, slugify(name, fallback="tag")),
        position=0 if last is None else last + 1,
    )
    db.add(tag)
    db.flush()
    audit.record(db, user, "blog.tag_added", tag_id=tag.id, name=name, slug=tag.slug)
    return tag


def rename(db: Session, user: User, tag: BlogTag, name: str) -> None:
    """A new name. The slug follows it unless a published article carries the tag."""
    name = check_name(db, name, keeping=tag.id)
    if name == tag.name:
        return
    was = tag.name
    tag.name = name
    if not slug_fixed(db, tag):
        tag.slug = free_slug(db, slugify(name, fallback="tag"), keeping=tag.id)
    audit.record(db, user, "blog.tag_renamed", tag_id=tag.id, name=name, was=was, slug=tag.slug)


def retire(db: Session, user: User, tag: BlogTag, retired: bool) -> None:
    """Retire a tag, or bring it back. Retired, it stays on the articles that have it."""
    if (tag.retired_at is not None) == retired:
        return
    tag.retired_at = now() if retired else None
    action = "blog.tag_retired" if retired else "blog.tag_restored"
    audit.record(db, user, action, tag_id=tag.id, name=tag.name)


def moved_to(db: Session, slug: str) -> BlogTag | None:
    """The tag `slug` leads to, if it is a merged tag's old address."""
    return db.scalar(
        select(BlogTag)
        .join(BlogTagAlias, BlogTagAlias.tag_id == BlogTag.id)
        .where(BlogTagAlias.slug == slug)
    )


def merge(db: Session, user: User, tag: BlogTag, into: BlogTag) -> int:
    """Move `tag` off every article onto `into`, then remove it. Its address, and
    those that led to it, lead to `into` from now on. Returns how many articles
    had it."""
    if tag.id == into.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose another tag to merge it into."
        )
    if into.retired_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{into.name} is retired: bring it back first, or merge into another tag.",
        )
    carrying = set(db.scalars(select(BlogPostTag.post_id).where(BlogPostTag.tag_id == tag.id)))
    having = set(db.scalars(select(BlogPostTag.post_id).where(BlogPostTag.tag_id == into.id)))
    db.add_all(BlogPostTag(post_id=p, tag_id=into.id) for p in sorted(carrying - having))
    db.execute(delete(BlogPostTag).where(BlogPostTag.tag_id == tag.id))
    # Its address, and the old ones that led to it, lead to `into` now.
    moved = sorted(db.scalars(select(BlogTagAlias.slug).where(BlogTagAlias.tag_id == tag.id)))
    db.execute(update(BlogTagAlias).where(BlogTagAlias.tag_id == tag.id).values(tag_id=into.id))
    db.add(BlogTagAlias(slug=tag.slug, tag_id=into.id))
    audit.record(
        db,
        user,
        "blog.tag_merged",
        tag_id=tag.id,
        name=tag.name,
        slug=tag.slug,
        into=into.name,
        into_id=into.id,
        into_slug=into.slug,
        articles=articles_text(len(carrying)),
        aliases=[tag.slug, *moved],
    )
    db.delete(tag)
    db.flush()
    return len(carrying)


def articles_text(n: int) -> str:
    return "no articles" if n == 0 else "1 article" if n == 1 else f"{n} articles"


def reorder(db: Session, user: User, tag_ids: list[uuid.UUID]) -> None:
    """Put every tag, retired ones too, in the order given."""
    tags = {t.id: t for t in db.scalars(select(BlogTag).with_for_update())}
    if len(tag_ids) != len(set(tag_ids)) or set(tag_ids) != set(tags):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The tags have changed since you looked: try again."
        )
    if tag_ids == [t.id for t in sorted(tags.values(), key=lambda t: (t.position, t.name))]:
        return
    for n, tag_id in enumerate(tag_ids):
        tags[tag_id].position = n
    audit.record(db, user, "blog.tags_reordered", names=", ".join(tags[i].name for i in tag_ids))

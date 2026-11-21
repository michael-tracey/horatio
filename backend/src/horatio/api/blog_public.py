"""The game developer blog's reading pages (#1158), for anyone at all, signed in or
not. What an article is and how it is published is in horatio.blog.

Only published articles are here, and only what the blog shows of them: never a
draft, an article waiting or unpublished, a published article's changes, the
custodian's note, or who wrote it beyond their name. Everything is under
/blog/public, apart from the routes for writing (/blog/articles, /blog/writer,
/blog/tags), the custodian's (/blog/queue) and the authors' (/blog/author...).

A hero picture's address is the one its author sees (/blog/articles/<id>/pictures/...):
api/blog.py serves it to anyone once its article is published.
"""

import math
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from horatio import blog, pictures
from horatio.auth.deps import DbSession, MaybeUser
from horatio.models import BlogPost, BlogPostTag, BlogTag, Troupe, User

router = APIRouter(prefix="/blog/public", tags=["blog"])

# Articles on a page of the blog.
PAGE_SIZE = 12
# Featured articles across the top of the blog's first page.
FEATURED = 3


# --- shapes ----------------------------------------------------------------------------


class BlogPublicTagOut(BaseModel):
    name: str
    slug: str


class BlogPublicTagCountOut(BlogPublicTagOut):
    # How many published articles have it.
    articles: int


class BlogPublicAuthorOut(BaseModel):
    """Who wrote it, as the blog shows them."""

    name: str
    # Their author page's handle (/blog/authors/<handle>), once they have one (#1159);
    # None until then.
    handle: str | None


class BlogPublicTroupeOut(BaseModel):
    """The troupe an article names. A private or archived troupe is its name only."""

    name: str
    # For its public profile (/t/<id>) and troupe card (#1160); None when it is
    # private or archived, so it isn't linked.
    id: uuid.UUID | None


class BlogPublicSummaryOut(BaseModel):
    """An article in a list of them."""

    slug: str
    title: str
    summary: str
    # Its hero picture (add "/1200.webp" or "/600.webp"), or None.
    picture: str | None
    author: BlogPublicAuthorOut
    troupe: BlogPublicTroupeOut | None
    tags: list[BlogPublicTagOut]
    featured: bool
    # When it was first published: its date on the blog.
    published_at: datetime
    # When changes to it were last published, if ever.
    revised_at: datetime | None


class BlogPublicArticleOut(BlogPublicSummaryOut):
    """An article, to read."""

    # Markdown.
    body: str
    # Where the viewer changes it, when they wrote it; None for anyone else.
    edit: str | None


class BlogPublicPageOut(BaseModel):
    """A page of articles, newest first, with the featured ones for the top of the
    blog."""

    articles: list[BlogPublicSummaryOut]
    page: int
    pages: int
    total: int
    featured: list[BlogPublicSummaryOut]


class BlogPublicTagPageOut(BlogPublicPageOut):
    tag: BlogPublicTagOut


class BlogPublicAuthorPageOut(BlogPublicPageOut):
    author: BlogPublicAuthorOut


# --- reading ---------------------------------------------------------------------------


def published() -> Select[BlogPost]:
    return select(BlogPost).where(BlogPost.status == "published")


def newest(query: Select[BlogPost]) -> Select[BlogPost]:
    return query.order_by(BlogPost.published_at.desc(), BlogPost.id.desc())


def troupe_shown(troupe: Troupe) -> BlogPublicTroupeOut:
    linked = troupe.public and troupe.archived_at is None
    return BlogPublicTroupeOut(name=troupe.name, id=troupe.id if linked else None)


def summaries(db: Session, found: list[BlogPost]) -> list[BlogPublicSummaryOut]:
    """The articles as the blog lists them, asking the database a few times in all."""
    troupe_ids = {a.troupe_id for a in found if a.troupe_id is not None}
    troupes = {
        t.id: troupe_shown(t) for t in db.scalars(select(Troupe).where(Troupe.id.in_(troupe_ids)))
    }
    names: dict[uuid.UUID, str] = {
        i: n
        for i, n in db.execute(
            select(User.id, User.display_name).where(User.id.in_({a.author_id for a in found}))
        )
    }
    tags = blog.tags_of(db, [a.id for a in found])
    out: list[BlogPublicSummaryOut] = []
    for a in found:
        assert a.published_at is not None
        out.append(
            BlogPublicSummaryOut(
                slug=a.slug,
                title=a.title,
                summary=a.summary,
                picture=pictures.blog_picture_url(a.id, a.picture_id),
                author=BlogPublicAuthorOut(name=names.get(a.author_id, ""), handle=None),
                troupe=troupes.get(a.troupe_id) if a.troupe_id else None,
                tags=[BlogPublicTagOut(name=t.name, slug=t.slug) for t in tags[a.id]],
                featured=a.featured,
                published_at=a.published_at,
                revised_at=a.revised_at,
            )
        )
    return out


def page_of(db: Session, query: Select[BlogPost], page: int) -> BlogPublicPageOut:
    """A page of the articles `query` finds, newest first, and the featured ones."""
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    found = list(db.scalars(newest(query).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)))
    featured = list(db.scalars(newest(published().where(BlogPost.featured)).limit(FEATURED)))
    shaped = summaries(db, found + featured)
    return BlogPublicPageOut(
        articles=shaped[: len(found)],
        page=page,
        pages=max(1, math.ceil(total / PAGE_SIZE)),
        total=total,
        featured=shaped[len(found) :],
    )


def tag_by_slug(db: Session, slug: str) -> BlogTag:
    tag = db.scalar(select(BlogTag).where(BlogTag.slug == slug))
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such tag.")
    return tag


def tagged(query: Select[BlogPost], tag: BlogTag) -> Select[BlogPost]:
    return query.where(
        BlogPost.id.in_(select(BlogPostTag.post_id).where(BlogPostTag.tag_id == tag.id))
    )


Page = Query(1, ge=1, le=10_000, description="Counting from 1.")


@router.get("/articles")
def list_articles(
    db: DbSession, page: int = Page, tag: str | None = Query(None, max_length=100)
) -> BlogPublicPageOut:
    """The blog: published articles, newest first, a page at a time, with those its
    `tag` (a slug) has if given; and the featured ones for the top."""
    query = published()
    if tag is not None:
        query = tagged(query, tag_by_slug(db, tag))
    return page_of(db, query, page)


@router.get("/articles/{slug}")
def read_article(slug: str, db: DbSession, user: MaybeUser) -> BlogPublicArticleOut:
    """A published article, by its address. Anything else is "no such article", so
    nobody learns what is being written."""
    article = db.scalar(published().where(BlogPost.slug == slug))
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such article.")
    [shown] = summaries(db, [article])
    yours = user is not None and user.id == article.author_id
    return BlogPublicArticleOut(
        **shown.model_dump(), body=article.body, edit=blog.link(article) if yours else None
    )


@router.get("/tags")
def list_tags(db: DbSession) -> list[BlogPublicTagCountOut]:
    """The blog's tags, in the custodian's order, with how many published articles
    have each."""
    counts: dict[uuid.UUID, int] = {
        t: n
        for t, n in db.execute(
            select(BlogPostTag.tag_id, func.count())
            .join(BlogPost, BlogPost.id == BlogPostTag.post_id)
            .where(BlogPost.status == "published")
            .group_by(BlogPostTag.tag_id)
        )
    }
    return [
        BlogPublicTagCountOut(name=t.name, slug=t.slug, articles=counts.get(t.id, 0))
        for t in blog.all_tags(db)
    ]


@router.get("/tags/{slug}")
def tag_articles(slug: str, db: DbSession, page: int = Page) -> BlogPublicTagPageOut:
    """A tag's published articles, newest first, a page at a time."""
    tag = tag_by_slug(db, slug)
    found = page_of(db, tagged(published(), tag), page)
    return BlogPublicTagPageOut(
        **found.model_dump(), tag=BlogPublicTagOut(name=tag.name, slug=tag.slug)
    )

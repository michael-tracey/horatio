"""The game developer blog's reading pages (#1158), for anyone at all, signed in or
not. What an article is and how it is published is in horatio.blog.

Only published articles are here, and only what the blog shows of them: never a
draft, an article waiting or unpublished, a published article's changes, the
custodian's note, or anything of who wrote it beyond their author card (#1159). Everything is under
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
from horatio.api import blog_authors
from horatio.api.blog import BlogTagOut, BlogTroupeOut, troupe_out
from horatio.api.blog_authors import AuthorCard
from horatio.auth.deps import DbSession, MaybeUser
from horatio.models import BlogAuthor, BlogPost, BlogPostTag, BlogTag, Troupe, User

router = APIRouter(prefix="/blog/public", tags=["blog"])

# Articles on a page of the blog.
PAGE_SIZE = 12
# Featured articles across the top of the blog's first page.
FEATURED = 3


# --- shapes ----------------------------------------------------------------------------


class BlogPublicTagCountOut(BlogTagOut):
    # How many published articles have it.
    articles: int


class BlogPublicAuthorOut(BaseModel):
    """Who wrote it, as the blog shows them: their author profile's name (#1159), or
    their own display name until they save one."""

    name: str
    # Their author page's handle (/blog/authors/<handle>), once they have saved an
    # author profile; None until then, or for an account merged into another.
    handle: str | None


class BlogPublicSummaryOut(BaseModel):
    """An article in a list of them."""

    slug: str
    title: str
    summary: str
    # Its hero picture (add "/1200.webp" or "/600.webp"), or None.
    picture: str | None
    author: BlogPublicAuthorOut
    # The troupe it names: the writing page's shape, so the blog and its preview draw
    # it alike. The blog links it only while it is public and not archived.
    troupe: BlogTroupeOut | None
    tags: list[BlogTagOut]
    featured: bool
    # When it was first published: its date on the blog.
    published_at: datetime
    # When changes to it were last published, if ever.
    revised_at: datetime | None


class BlogPublicArticleOut(BlogPublicSummaryOut):
    """An article, to read."""

    # Markdown.
    body: str
    # Its author's card, to go under it (#1159), once they have a profile.
    author_card: AuthorCard | None
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
    tag: BlogTagOut


class BlogPublicAuthorPageOut(BlogPublicPageOut):
    """An author's published articles, for their page (/blog/authors/<handle>)."""

    author: BlogPublicAuthorOut


# --- reading ---------------------------------------------------------------------------


def published() -> Select[BlogPost]:
    return select(BlogPost).where(BlogPost.status == "published")


def newest(query: Select[BlogPost]) -> Select[BlogPost]:
    return query.order_by(BlogPost.published_at.desc(), BlogPost.id.desc())


def authors_of(
    db: Session, user_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[BlogPublicAuthorOut, BlogAuthor | None]]:
    """Each author as the blog names them, and their author profile if they have one
    that is shown: an author with an article published is, unless their account was
    merged into another (blog_authors.shown)."""
    profiles = {
        p.user_id: p for p in db.scalars(select(BlogAuthor).where(BlogAuthor.user_id.in_(user_ids)))
    }
    found: dict[uuid.UUID, tuple[BlogPublicAuthorOut, BlogAuthor | None]] = {}
    for user_id, name, merged in db.execute(
        select(User.id, User.display_name, User.merged_into_id).where(User.id.in_(user_ids))
    ):
        profile = profiles.get(user_id) if merged is None else None
        found[user_id] = (
            BlogPublicAuthorOut(
                name=profile.display_name if profile else name,
                handle=profile.handle if profile else None,
            ),
            profile,
        )
    return found


def summaries(db: Session, found: list[BlogPost]) -> list[BlogPublicSummaryOut]:
    """The articles as the blog lists them, asking the database a few times in all."""
    troupe_ids = {a.troupe_id for a in found if a.troupe_id is not None}
    troupes = {
        t.id: troupe_out(t) for t in db.scalars(select(Troupe).where(Troupe.id.in_(troupe_ids)))
    }
    authors = authors_of(db, {a.author_id for a in found})
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
                author=authors[a.author_id][0],
                troupe=troupes.get(a.troupe_id) if a.troupe_id else None,
                tags=[BlogTagOut(id=t.id, name=t.name, slug=t.slug) for t in tags[a.id]],
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
    profile = authors_of(db, {article.author_id})[article.author_id][1]
    yours = user is not None and user.id == article.author_id
    return BlogPublicArticleOut(
        **shown.model_dump(),
        body=article.body,
        author_card=blog_authors.card(profile) if profile else None,
        edit=blog.link(article) if yours else None,
    )


@router.get("/tags")
def list_tags(db: DbSession) -> list[BlogPublicTagCountOut]:
    """The tags with published articles, in the custodian's order, with how many each
    has: retired ones too, as they stay on the articles that have them (#1161)."""
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
        BlogPublicTagCountOut(id=t.id, name=t.name, slug=t.slug, articles=counts[t.id])
        for t in blog.all_tags(db, retired=True)
        if counts.get(t.id)
    ]


@router.get("/tags/{slug}")
def tag_articles(slug: str, db: DbSession, page: int = Page) -> BlogPublicTagPageOut:
    """A tag's published articles, newest first, a page at a time. A retired tag's page
    stays; one merged into another has gone, and with it its address (#1161)."""
    tag = tag_by_slug(db, slug)
    found = page_of(db, tagged(published(), tag), page)
    return BlogPublicTagPageOut(
        **found.model_dump(), tag=BlogTagOut(id=tag.id, name=tag.name, slug=tag.slug)
    )


@router.get("/authors/{handle}/articles")
def author_articles(
    handle: str, db: DbSession, user: MaybeUser, page: int = Page
) -> BlogPublicAuthorPageOut:
    """An author's published articles, newest first, a page at a time: for their page,
    to whoever may see it (blog_authors.viewable)."""
    profile = blog_authors.viewable(db, user, handle)
    found = page_of(db, published().where(BlogPost.author_id == profile.user_id), page)
    author = authors_of(db, {profile.user_id})[profile.user_id][0]
    return BlogPublicAuthorPageOut(**found.model_dump(), author=author)

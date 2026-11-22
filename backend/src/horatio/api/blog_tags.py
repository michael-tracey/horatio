"""Custodian › Blog › Tags (#1161): the custodian keeps the blog's tags. What a tag is,
and how its slug and retiring work, is in horatio.blog_tags. Each change answers with
the whole list, as the tab shows it."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import blog_tags
from horatio.auth.deps import CurrentUser, DbSession
from horatio.permissions import require_custodian

router = APIRouter(prefix="/blog", tags=["blog"])


class BlogTagKeptOut(BaseModel):
    id: uuid.UUID
    name: str
    # Its address on the blog's tag pages (#1158).
    slug: str
    # It stays on a rename: a published article carries the tag.
    slug_fixed: bool
    retired: bool
    # How many articles carry it, and how many of those are published.
    articles: int
    published: int


class BlogTagNameIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class BlogTagRetiredIn(BaseModel):
    retired: bool


class BlogTagMergeIn(BaseModel):
    into_id: uuid.UUID


class BlogTagOrderIn(BaseModel):
    tag_ids: list[uuid.UUID] = Field(max_length=500)


def kept_out(db: DbSession) -> list[BlogTagKeptOut]:
    return [
        BlogTagKeptOut(
            id=k.tag.id,
            name=k.tag.name,
            slug=k.tag.slug,
            slug_fixed=k.slug_fixed,
            retired=k.tag.retired_at is not None,
            articles=k.articles,
            published=k.published,
        )
        for k in blog_tags.kept(db)
    ]


@router.get("/tags/kept")
def kept_tags(db: DbSession, user: CurrentUser) -> list[BlogTagKeptOut]:
    """Every tag, retired ones too, with how many articles carry each."""
    require_custodian(user)
    return kept_out(db)


@router.post("/tags")
def add_tag(body: BlogTagNameIn, db: DbSession, user: CurrentUser) -> list[BlogTagKeptOut]:
    """A new tag, at the end of the list."""
    require_custodian(user)
    blog_tags.add(db, user, body.name)
    db.commit()
    return kept_out(db)


@router.put("/tags/{tag_id}")
def rename_tag(
    tag_id: uuid.UUID, body: BlogTagNameIn, db: DbSession, user: CurrentUser
) -> list[BlogTagKeptOut]:
    require_custodian(user)
    blog_tags.rename(db, user, blog_tags.find(db, tag_id), body.name)
    db.commit()
    return kept_out(db)


@router.put("/tags/{tag_id}/retired")
def retire_tag(
    tag_id: uuid.UUID, body: BlogTagRetiredIn, db: DbSession, user: CurrentUser
) -> list[BlogTagKeptOut]:
    """Retire a tag, or bring it back. Retired, it stays on the articles that have it."""
    require_custodian(user)
    blog_tags.retire(db, user, blog_tags.find(db, tag_id), body.retired)
    db.commit()
    return kept_out(db)


@router.post("/tags/{tag_id}/merge")
def merge_tag(
    tag_id: uuid.UUID, body: BlogTagMergeIn, db: DbSession, user: CurrentUser
) -> list[BlogTagKeptOut]:
    """Move the tag off every article onto another, then remove it."""
    require_custodian(user)
    tag = blog_tags.find(db, tag_id)
    blog_tags.merge(db, user, tag, blog_tags.find(db, body.into_id))
    db.commit()
    return kept_out(db)


@router.put("/tag-order")
def order_tags(body: BlogTagOrderIn, db: DbSession, user: CurrentUser) -> list[BlogTagKeptOut]:
    """Every tag, retired ones too, in a new order."""
    require_custodian(user)
    blog_tags.reorder(db, user, body.tag_ids)
    db.commit()
    return kept_out(db)

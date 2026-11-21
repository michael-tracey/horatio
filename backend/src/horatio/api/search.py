"""Searching everything from the top bar (horatio.search, #1046)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from horatio import search
from horatio.auth.deps import CurrentUser, DbSession

router = APIRouter(tags=["search"])


class HitOut(BaseModel):
    id: uuid.UUID
    title: str
    # A few words more: a boon's reason, who holds an item, a player's handle.
    detail: str
    # Its page in the app.
    to: str
    troupe_id: uuid.UUID | None
    # The troupe it is in, and what that troupe goes by, for its pill (#1153).
    troupe: str | None
    troupe_abbreviation: str | None = None


class GroupOut(BaseModel):
    # characters | players | boons | locations | quests | equipment | news | announcements
    kind: str
    label: str
    hits: list[HitOut]
    # More were found than are shown: a longer search narrows them.
    more: bool


class SearchOut(BaseModel):
    groups: list[GroupOut]


@router.get("/search")
def search_everything(
    db: DbSession,
    user: CurrentUser,
    q: Annotated[str, Query(max_length=200)] = "",
    troupe_id: uuid.UUID | None = None,
) -> SearchOut:
    """What `q` finds among what the person may see, each kind a group, the hits of
    `troupe_id` (the troupe they are in now) first. Nothing for fewer than two letters."""
    groups = search.search(db, user, q, troupe_id)
    names = search.troupe_names(db, groups)

    def hit_out(h: search.Hit) -> HitOut:
        troupe = names.get(h.troupe_id) if h.troupe_id else None
        return HitOut(
            id=h.key,
            title=h.title,
            detail=h.detail,
            to=h.to,
            troupe_id=h.troupe_id,
            troupe=troupe.name if troupe else None,
            troupe_abbreviation=troupe.abbreviation if troupe else None,
        )

    return SearchOut(
        groups=[
            GroupOut(kind=g.kind, label=g.label, more=g.more, hits=[hit_out(h) for h in g.hits])
            for g in groups
        ]
    )

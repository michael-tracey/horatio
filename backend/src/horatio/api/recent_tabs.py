"""The tabs of a troupe's page the signed-in person opened last there
(horatio.recent_tabs, #1048), for the top of its tab list on a phone."""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints

from horatio import recent_tabs
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe
from horatio.permissions import open_to

router = APIRouter(prefix="/troupes/{troupe_id}/recent-tabs", tags=["troupes"])

# A tab's address under the troupe's: "/approvals", "/settings", or "" for the Overview.
TabAddress = Annotated[str, StringConstraints(pattern=r"^(/[a-z0-9-]+)*$", max_length=100)]


class RecentTabsIn(BaseModel):
    # Newest first.
    tabs: list[TabAddress] = Field(max_length=recent_tabs.KEPT)


class RecentTabsOut(BaseModel):
    # Newest first, at most four: the three shown and the one open.
    tabs: list[str]


def open_troupe(db: DbSession, user: CurrentUser, troupe_id: uuid.UUID) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or not open_to(user, troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


@router.get("")
def read_recent_tabs(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> RecentTabsOut:
    return RecentTabsOut(tabs=recent_tabs.read(db, user, open_troupe(db, user, troupe_id)))


@router.put("")
def keep_recent_tabs(
    troupe_id: uuid.UUID, body: RecentTabsIn, db: DbSession, user: CurrentUser
) -> RecentTabsOut:
    """Keep the list the page sends, whole: the page puts the tab just opened first."""
    kept = recent_tabs.keep(db, user, open_troupe(db, user, troupe_id), body.tabs)
    db.commit()
    return RecentTabsOut(tabs=kept)

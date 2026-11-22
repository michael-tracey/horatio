"""The troupes anyone may find (#1164): those whose profile is public and that are
still running, for the landing page, signed in or not. Each is only what its public
profile shows already (api/troupe_profiles.py): its name, what it goes by, its
portrait, its description and where it plays. Its profile is at /t/<troupe id>.
"""

import math
import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from horatio import pictures, troupe_abbreviations
from horatio.api.troupe_profiles import Profile
from horatio.auth.deps import DbSession
from horatio.models import Troupe

router = APIRouter(prefix="/public/troupes", tags=["troupe profiles"])

# Troupes on a page of the list.
PAGE_SIZE = 12


class PublicTroupeOut(BaseModel):
    id: uuid.UUID
    name: str
    # What it goes by where its name won't fit (horatio.troupe_abbreviations).
    abbreviation: str
    # Where its portrait is (add "/48.webp", "/128.webp" or "/512.webp"), or None.
    portrait: str | None
    # Markdown, as on its profile.
    description: str
    # Its venue's city or region, else its setting's city; "" for neither.
    place: str


class PublicTroupePageOut(BaseModel):
    """A page of public troupes, by name."""

    troupes: list[PublicTroupeOut]
    page: int
    pages: int
    total: int


# Which troupes anyone may find: as the sitemap lists them (api/sharing.py).
SHOWN = (Troupe.public, Troupe.archived_at.is_(None))


@router.get("")
def list_public_troupes(
    db: DbSession, page: int = Query(1, ge=1, le=10_000, description="Counting from 1.")
) -> PublicTroupePageOut:
    """The troupes whose profiles are public and that aren't archived, by name, a page
    at a time. For anyone at all."""
    total = db.scalar(select(func.count()).select_from(Troupe).where(*SHOWN)) or 0
    found = list(
        db.scalars(
            select(Troupe)
            .where(*SHOWN)
            .order_by(func.lower(Troupe.name), Troupe.id)
            .limit(PAGE_SIZE)
            .offset((page - 1) * PAGE_SIZE)
        )
    )
    goes_by = troupe_abbreviations.effective(db) if found else {}
    troupes: list[PublicTroupeOut] = []
    for troupe in found:
        kept = Profile.model_validate(troupe.profile)
        troupes.append(
            PublicTroupeOut(
                id=troupe.id,
                name=troupe.name,
                abbreviation=goes_by[troupe.id].abbreviation,
                portrait=pictures.troupe_portrait_url(troupe.id, troupe.portrait_id),
                description=troupe.description,
                place=kept.venue.region or kept.setting.city,
            )
        )
    return PublicTroupePageOut(
        troupes=troupes,
        page=page,
        pages=max(1, math.ceil(total / PAGE_SIZE)),
        total=total,
    )

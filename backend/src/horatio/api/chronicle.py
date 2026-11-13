"""A troupe's chronicle timeline (horatio.chronicle, #711): its history, every event
for its running staff, and, where the troupe lets them, the public events for its
members."""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import chronicle
from horatio.api.court import runs
from horatio.api.troupes import get_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.permissions import is_member

router = APIRouter(tags=["chronicle"])


class ChronicleEventOut(BaseModel):
    key: str
    kind: Literal["title", "status", "embrace", "diablerie", "death", "arrival", "departure"]
    # None once the character is deleted: its name stays.
    character_id: uuid.UUID | None
    character_name: str
    clan: str | None
    label: str
    detail: str
    # When Horatio recorded it, and, where its record keeps one, the in-game date.
    at: datetime
    on: date | None
    # A title's holding: when it ended, or `ongoing` while it is held.
    ends_at: datetime | None
    ends_on: date | None
    ongoing: bool


class ChronicleOut(BaseModel):
    # Staff see every event; members, the public ones.
    full: bool
    # Whether the troupe shows its players the chronicle.
    players_see: bool
    events: list[ChronicleEventOut]


@router.get("/troupes/{troupe_id}/chronicle")
def troupe_chronicle(troupe_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ChronicleOut:
    troupe = get_troupe(db, troupe_id)
    full = runs(db, user, troupe)
    if not full and not (troupe.chronicle_players and is_member(db, user, troupe)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The chronicle is for staff here.")
    return ChronicleOut(
        full=full,
        players_see=troupe.chronicle_players,
        events=[
            ChronicleEventOut(
                key=e.key,
                kind=e.kind,
                character_id=e.character_id,
                character_name=e.character_name,
                clan=e.clan,
                label=e.label,
                detail=e.detail,
                at=e.at,
                on=e.on,
                ends_at=e.ends_at,
                ends_on=e.ends_on,
                ongoing=e.ongoing,
            )
            for e in chronicle.events(db, troupe, full=full)
        ],
    )

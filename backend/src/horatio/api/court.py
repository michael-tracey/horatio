"""The court over time (horatio.title_history, #712): who held each of a troupe's
titles, and when, for its running staff, with each home character's status over
time; and, where the troupe lets them, for its players, the titles alone. Staff
add the in-game dates of a holding."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from horatio import audit, social_age, title_history, titles
from horatio.api.downtimes import staff_troupe
from horatio.api.troupes import get_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import TitleHolding, Troupe, User
from horatio.permissions import TroupeAction, allows, is_member, troupe_role
from horatio.sheets import unprocessable

router = APIRouter(tags=["court"])


class CourtTitleOut(BaseModel):
    name: str
    # Its sect; None for a title of no sect, or one no longer in the troupe's list.
    sect: str | None


class HoldingOut(BaseModel):
    id: uuid.UUID
    title: str
    # None once the character is deleted: its name stays.
    character_id: uuid.UUID | None
    character_name: str
    clan: str | None
    began_at: datetime
    # None while it is held.
    ended_at: datetime | None
    began_in_game: date | None
    ended_in_game: date | None
    # How it began and ended, and whether it was recovered from the log: for staff.
    began_how: str | None
    ended_how: str | None
    backfilled: bool


class StatusPointOut(BaseModel):
    at: datetime
    fleeting: int
    negative: int


class StatusLineOut(BaseModel):
    character_id: uuid.UUID
    name: str
    clan: str | None
    points: list[StatusPointOut]
    gained: int
    lost: int


class ClanCountOut(BaseModel):
    clan: str | None
    count: int


class CourtHistoryOut(BaseModel):
    # Staff see how each holding began and ended, and status over time.
    full: bool
    # Whether the troupe shows its players the titles.
    players_see: bool
    # The titles held at some time, in court order.
    titles: list[CourtTitleOut]
    holdings: list[HoldingOut]
    # Each home character's status over time: for staff only.
    status: list[StatusLineOut] | None
    # The troupe's characters now, by clan: what fixes each clan's colour.
    clans: list[ClanCountOut]


class HoldingDatesIn(BaseModel):
    began_in_game: date | None = None
    ended_in_game: date | None = None


def holding_out(h: TitleHolding, clan: str | None, full: bool) -> HoldingOut:
    """A holding as the reader sees it: how it began and ended only for staff."""
    return HoldingOut(
        id=h.id,
        title=h.name,
        character_id=h.character_id,
        character_name=h.character_name,
        clan=clan,
        began_at=h.began_at,
        ended_at=h.ended_at,
        began_in_game=h.began_in_game,
        ended_in_game=h.ended_in_game,
        began_how=h.began_how if full else None,
        ended_how=h.ended_how if full else None,
        backfilled=h.backfilled and full,
    )


def runs(db: Session, user: User, troupe: Troupe) -> bool:
    return allows(
        troupe_role(db, user, troupe), TroupeAction.MANAGE_TITLES, is_custodian=user.is_custodian
    )


@router.get("/troupes/{troupe_id}/court-history")
def court_history(troupe_id: uuid.UUID, user: CurrentUser, db: DbSession) -> CourtHistoryOut:
    troupe = get_troupe(db, troupe_id)
    full = runs(db, user, troupe)
    if not full and not (troupe.court_history_players and is_member(db, user, troupe)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The court over time is for staff here.")
    held = title_history.holdings(db, troupe)
    order = titles.court_order(db, troupe.id)
    known = titles.title_data(db, troupe.id)
    names = sorted({h.name for h in held}, key=lambda n: titles.court_key(order, n))
    members = title_history.members(db, troupe)
    ids = {h.character_id for h in held if h.character_id} | set(members)
    standing = social_age.standings(db, list(ids)) if ids else {}

    def clan(character_id: uuid.UUID | None) -> str | None:
        found = standing.get(character_id) if character_id else None
        return found.clan if found else None

    counts: dict[str | None, int] = {}
    for character_id in members:
        counts[clan(character_id)] = counts.get(clan(character_id), 0) + 1
    return CourtHistoryOut(
        full=full,
        players_see=troupe.court_history_players,
        titles=[CourtTitleOut(name=n, sect=known[n].sect if n in known else None) for n in names],
        holdings=[holding_out(h, clan(h.character_id), full) for h in held],
        status=[
            StatusLineOut(
                character_id=line.character_id,
                name=line.name,
                clan=line.clan,
                points=[
                    StatusPointOut(at=p.at, fleeting=p.fleeting, negative=p.negative)
                    for p in line.points
                ],
                gained=line.gained,
                lost=line.lost,
            )
            for line in title_history.status_lines(db, troupe)
        ]
        if full
        else None,
        clans=[ClanCountOut(clan=c, count=n) for c, n in counts.items()],
    )


def words(began: date | None, ended: date | None) -> str:
    began_text = began.isoformat() if began else "not given"
    ended_text = ended.isoformat() if ended else "not given"
    return f"began {began_text}, ended {ended_text}"


@router.put("/troupes/{troupe_id}/court-history/{holding_id}/in-game")
def date_holding(
    troupe_id: uuid.UUID,
    holding_id: uuid.UUID,
    body: HoldingDatesIn,
    user: CurrentUser,
    db: DbSession,
) -> HoldingOut:
    """Set the in-game dates a holding began and ended; none, to clear them."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    holding = db.get(TitleHolding, holding_id)
    if holding is None or holding.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such holding of a title here.")
    if body.ended_in_game is not None and holding.ended_at is None:
        raise unprocessable(f"{holding.character_name} holds it still.")
    if body.began_in_game and body.ended_in_game and body.ended_in_game < body.began_in_game:
        raise unprocessable("It can't end before it began.")
    if (holding.began_in_game, holding.ended_in_game) != (body.began_in_game, body.ended_in_game):
        holding.began_in_game, holding.ended_in_game = body.began_in_game, body.ended_in_game
        db.flush()
        audit.record(
            db,
            user,
            "title.dated",
            troupe_id=troupe.id,
            character_id=holding.character_id,
            **({} if holding.character_id else {"character_name": holding.character_name}),
            title=holding.name,
            what=words(body.began_in_game, body.ended_in_game),
        )
        db.commit()
    standing = social_age.standings(db, [holding.character_id]) if holding.character_id else {}
    found = standing.get(holding.character_id) if holding.character_id else None
    return holding_out(holding, found.clan if found else None, True)

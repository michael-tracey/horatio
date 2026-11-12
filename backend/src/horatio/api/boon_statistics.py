"""Boon statistics (horatio.boon_statistics, #702): the boon ledger over time, who owes
whom, debt between clans and sects, and each game's activity, for the statistics
page's charts; and the troupe's games a boon can be registered at.

Those who may read the standings read these (`boon_standings.can_read`)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import boon_statistics as statistics
from horatio import boons
from horatio.api.boon_standings import (
    BoonStandingPartyOut,
    BoonWeightsOut,
    Scope,
    party_out,
    standings_troupe,
    weights_out,
)
from horatio.api.boons import Kind
from horatio.auth.deps import CurrentUser, DbSession

router = APIRouter(tags=["boons"])


class BoonMonthOut(BaseModel):
    """One kind of boon in one month ("2026-10"): registered, settled, and what stood
    at the month's end, by count and weight."""

    month: str
    kind: Kind
    registered: int
    registered_weight: float
    settled: int
    settled_weight: float
    open: int
    open_weight: float


class BoonNodeOut(BaseModel):
    who: BoonStandingPartyOut
    owes: float
    owed: float
    net: float
    owes_count: int
    owed_count: int


class BoonLinkOut(BaseModel):
    """What `debtor` owes `creditor` (parties' keys), still open."""

    debtor: str
    creditor: str
    count: int
    weight: float
    # How many of each kind.
    kinds: dict[str, int]


class BoonFlowOut(BaseModel):
    """`matrix[i][j]`: the open weight `groups[i]` owes `groups[j]`; `counts`, how many."""

    groups: list[str]
    matrix: list[list[float]]
    counts: list[list[int]]


class BoonGameOut(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime


class BoonActiveOut(BaseModel):
    who: BoonStandingPartyOut
    boons: int


class BoonGameActivityOut(BaseModel):
    game: BoonGameOut
    registered: int
    registered_weight: float
    by_kind: dict[str, int]
    settled: int
    settled_weight: float
    most_active: list[BoonActiveOut]


class BoonStatisticsOut(BaseModel):
    scope: Scope
    weights: BoonWeightsOut
    # By month, from the first boon entered: by the day each went in the ledger.
    by_entered: list[BoonMonthOut]
    # Registered by the in-game night each was made, only months that have any.
    by_night: list[BoonMonthOut]
    nodes: list[BoonNodeOut]
    links: list[BoonLinkOut]
    clan_flow: BoonFlowOut
    sect_flow: BoonFlowOut
    # The latest games already started, newest first.
    games: list[BoonGameActivityOut]


def month_out(line: statistics.MonthLine) -> BoonMonthOut:
    return BoonMonthOut(
        month=line.month,
        kind=line.kind,  # type: ignore[arg-type]  # one of boons.KINDS
        registered=line.registered,
        registered_weight=line.registered_weight,
        settled=line.settled,
        settled_weight=line.settled_weight,
        open=line.open,
        open_weight=line.open_weight,
    )


def flow_out(found: statistics.Flow) -> BoonFlowOut:
    return BoonFlowOut(groups=found.groups, matrix=found.matrix, counts=found.counts)


def game_out(game: statistics.Game) -> BoonGameOut:
    return BoonGameOut(id=game.id, starts_at=game.starts_at, ends_at=game.ends_at)


@router.get("/troupes/{troupe_id}/boon-statistics")
def boon_statistics(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser, scope: Scope = "active"
) -> BoonStatisticsOut:
    """The boon ledger's statistics: by month, who owes whom, debt between clans and
    sects, and each recent game's boons. "active" leaves out boons that involve
    someone dead or off-field."""
    troupe = standings_troupe(db, user, troupe_id)
    found = statistics.statistics_of(db, troupe, datetime.now(UTC), scope)
    return BoonStatisticsOut(
        scope=scope,
        weights=weights_out(troupe),
        by_entered=[month_out(m) for m in found.by_entered],
        by_night=[month_out(m) for m in found.by_night],
        nodes=[
            BoonNodeOut(
                who=party_out(n.who),
                owes=n.owes,
                owed=n.owed,
                net=n.net,
                owes_count=n.owes_count,
                owed_count=n.owed_count,
            )
            for n in found.nodes
        ],
        links=[
            BoonLinkOut(
                debtor=link.debtor,
                creditor=link.creditor,
                count=link.count,
                weight=link.weight,
                kinds=link.kinds,
            )
            for link in found.links
        ],
        clan_flow=flow_out(found.clan_flow),
        sect_flow=flow_out(found.sect_flow),
        games=[
            BoonGameActivityOut(
                game=game_out(g.game),
                registered=g.registered,
                registered_weight=g.registered_weight,
                by_kind=g.by_kind,
                settled=g.settled,
                settled_weight=g.settled_weight,
                most_active=[BoonActiveOut(who=party_out(w), boons=n) for w, n in g.most_active],
            )
            for g in found.games
        ],
    )


@router.get("/troupes/{troupe_id}/boon-games")
def boon_games(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[BoonGameOut]:
    """The troupe's latest games already started, newest first: those its boons can be
    registered at, for those who keep its ledger."""
    troupe = standings_troupe(db, user, troupe_id)
    if not boons.can_manage(db, user, troupe):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the troupe's staff see this.")
    return [game_out(g) for g in statistics.games_of(db, troupe, datetime.now(UTC))]

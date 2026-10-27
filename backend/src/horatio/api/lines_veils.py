"""A player's lines and veils (horatio.lines_veils): the player keeps their own, and
a troupe's staff see everyone's on one list. Where else they show (a profile, the
Who's Who, the Characters tab, the Play View), the route asks
horatio.permissions who may see them."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from horatio import lines_veils
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import User
from horatio.permissions import TroupeAction

router = APIRouter(tags=["lines-veils"])


class LinesVeils(BaseModel):
    # Each in the player's own words: "spiders", "harm to children".
    lines: list[str]
    veils: list[str]
    # They share them with the other players in their troupes, not only staff.
    shared: bool


class LinesVeilsIn(BaseModel):
    lines: list[str] = []
    veils: list[str] = []
    shared: bool = False


class Owner(BaseModel):
    id: uuid.UUID
    display_name: str
    handle: str


class GatheredOut(BaseModel):
    text: str
    # How many of the troupe's players gave it.
    count: int
    # Those of them who share theirs with players; the rest go unnamed here.
    shared_by: list[Owner]


class TroupeLinesVeils(BaseModel):
    # Every line and veil the troupe's players gave, each once, most given first.
    lines: list[GatheredOut]
    veils: list[GatheredOut]
    # The players who gave any, by name, for staff to open each one's profile.
    players: list[Owner]


def lines_veils_of(player: User) -> LinesVeils:
    return LinesVeils(lines=player.lines, veils=player.veils, shared=player.share_lines_veils)


def owner(player: User) -> Owner:
    return Owner(id=player.id, display_name=player.display_name, handle=player.handle)


@router.put("/profile/lines-veils")
def set_lines_veils(body: LinesVeilsIn, db: DbSession, user: CurrentUser) -> LinesVeils:
    """The signed-in player's own lines and veils, and whether they share them with
    other players. Not logged: they are the player's private settings."""
    lines = lines_veils.clean(body.lines, "lines")
    veils = lines_veils.clean(body.veils, "veils")
    user.lines, user.veils = lines, veils
    user.share_lines_veils = body.shared
    db.commit()
    return lines_veils_of(user)


@router.get("/troupes/{troupe_id}/lines-veils")
def troupe_lines_veils(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TroupeLinesVeils:
    """Every line and veil across the troupe's players, for its staff to plan games.
    Whose each one is shows only for players who share theirs."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_LINES_VEILS)
    found = lines_veils.troupe_list(db, troupe)

    def out(gathered: list[lines_veils.Gathered]) -> list[GatheredOut]:
        return [
            GatheredOut(text=g.text, count=g.count, shared_by=[owner(p) for p in g.shared_by])
            for g in gathered
        ]

    return TroupeLinesVeils(
        lines=out(found.lines), veils=out(found.veils), players=[owner(p) for p in found.players]
    )

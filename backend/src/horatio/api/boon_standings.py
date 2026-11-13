"""Boon standings (horatio.boon_standings, #691): where everyone stands in a troupe's
boon ledger, live, for its running staff; and what each kind of boon weighs there.

The statistics page (#702) builds on the same sums: `GET …/boon-standings` gives
every section, and `horatio.boon_standings.compute` works them out from rows."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import boon_standings as standings
from horatio import boons
from horatio.api.boons import Kind, Standing
from horatio.auth.deps import CurrentUser, DbSession
from horatio.boon_harpy import Keeper
from horatio.models import Troupe, User

router = APIRouter(tags=["boons"])

Scope = Literal["active", "everyone"]


class BoonWeightsIn(BaseModel):
    """What each kind of boon weighs: every kind, more than 0 and at most 100."""

    trivial: float = Field(gt=0, le=standings.HEAVIEST)
    minor: float = Field(gt=0, le=standings.HEAVIEST)
    major: float = Field(gt=0, le=standings.HEAVIEST)
    blood: float = Field(gt=0, le=standings.HEAVIEST)
    life: float = Field(gt=0, le=standings.HEAVIEST)


class BoonWeightsOut(BaseModel):
    trivial: float
    minor: float
    major: float
    blood: float
    life: float
    # The troupe keeps the defaults: Trivial 0.5, Minor 1, Major 3, Blood 5, Life 10.
    defaults: bool


class BoonStandingPartyOut(BaseModel):
    """Someone in the standings: a character (with what Horatio knows of them), or a
    name only."""

    key: str
    name: str
    character_id: uuid.UUID | None
    # Active, or why it retired; None for a name only.
    standing: Standing | None
    clan: str | None
    age: str | None
    sect: str | None
    titles: list[str]


class BoonStandingTotalsOut(BaseModel):
    open: int
    departed: int
    settled: int
    pending: int
    name_only: int


class BoonKindLineOut(BaseModel):
    kind: Kind
    weight: float
    count: int
    total: float


class BoonStandingOut(BaseModel):
    who: BoonStandingPartyOut
    owes: float
    owed: float
    net: float
    owes_count: int
    owed_count: int


class BoonTallyOut(BaseModel):
    who: BoonStandingPartyOut
    count: int
    weight: float


class BoonOfficerOut(BaseModel):
    title: str
    standing: BoonStandingOut
    # Those who owe them most, and those they owe most.
    owe_them: list[BoonTallyOut]
    they_owe: list[BoonTallyOut]


class BoonGroupOut(BaseModel):
    label: str
    characters: int
    owes: float
    owed: float
    net: float


class BoonBandOut(BaseModel):
    label: str
    count: int
    weight: float


class BoonSettledKindOut(BaseModel):
    kind: Kind
    count: int
    weight: float
    called_in: int
    forgiven: int
    ignored: int
    median_months: float | None


class BoonCollectorOut(BaseModel):
    who: BoonStandingPartyOut
    called_in: float
    open: float
    # The share of their weight called in, of all they have called in or still hold.
    rate: int


class BoonSettlingOut(BaseModel):
    count: int
    weight: float
    median_months: float | None
    by_kind: list[BoonSettledKindOut]
    by_clan: list[BoonBandOut]
    calls_in: list[BoonCollectorOut]
    leaves: list[BoonCollectorOut]


class BoonPairOut(BaseModel):
    label: str
    count: int
    weight: float


class BoonAcrossOut(BaseModel):
    crossing: int
    crossing_weight: float
    of: int
    pairs: list[BoonPairOut]
    most: list[BoonTallyOut]


class BoonMutualOut(BaseModel):
    first: BoonStandingPartyOut
    second: BoonStandingPartyOut
    owes: float
    back: float
    net: float


class BoonStandingsOut(BaseModel):
    scope: Scope
    weights: BoonWeightsOut
    totals: BoonStandingTotalsOut
    by_kind: list[BoonKindLineOut]
    characters: list[BoonStandingOut]
    court: list[BoonOfficerOut]
    clans: list[BoonGroupOut]
    ages: list[BoonGroupOut]
    sects: list[BoonGroupOut]
    debt_age: list[BoonBandOut]
    settling: BoonSettlingOut
    across_clans: BoonAcrossOut
    across_sects: BoonAcrossOut
    mutual: list[BoonMutualOut]


def weights_out(troupe: Troupe) -> BoonWeightsOut:
    return BoonWeightsOut(**standings.weights_of(troupe), defaults=not troupe.boon_weights)


def party_out(who: standings.Who) -> BoonStandingPartyOut:
    return BoonStandingPartyOut(
        key=who.key,
        name=who.name,
        character_id=who.character_id,
        standing=who.standing,  # type: ignore[arg-type]  # one of boons.STANDINGS
        clan=who.clan,
        age=who.age,
        sect=who.sect,
        titles=list(who.titles),
    )


def standing_out(s: standings.Standing) -> BoonStandingOut:
    return BoonStandingOut(
        who=party_out(s.who),
        owes=s.owes,
        owed=s.owed,
        net=standings.rounded(s.net),
        owes_count=s.owes_count,
        owed_count=s.owed_count,
    )


def tally_out(t: standings.Tally) -> BoonTallyOut:
    return BoonTallyOut(who=party_out(t.who), count=t.count, weight=t.weight)


def group_out(g: standings.Group) -> BoonGroupOut:
    return BoonGroupOut(
        label=g.label,
        characters=g.characters,
        owes=g.owes,
        owed=g.owed,
        net=standings.rounded(g.net),
    )


def band_out(b: standings.Band) -> BoonBandOut:
    return BoonBandOut(label=b.label, count=b.count, weight=b.weight)


def collector_out(c: standings.Collector) -> BoonCollectorOut:
    return BoonCollectorOut(who=party_out(c.who), called_in=c.called_in, open=c.open, rate=c.rate)


def across_out(a: standings.Across) -> BoonAcrossOut:
    return BoonAcrossOut(
        crossing=a.crossing,
        crossing_weight=a.crossing_weight,
        of=a.of,
        pairs=[BoonPairOut(label=p.label, count=p.count, weight=p.weight) for p in a.pairs],
        most=[tally_out(t) for t in a.most],
    )


def standings_out(troupe: Troupe, found: standings.Standings) -> BoonStandingsOut:
    s = found.settling
    return BoonStandingsOut(
        scope=found.scope,
        weights=weights_out(troupe),
        totals=BoonStandingTotalsOut(**vars(found.totals)),
        by_kind=[
            BoonKindLineOut(kind=k.kind, weight=k.weight, count=k.count, total=k.total)  # type: ignore[arg-type]
            for k in found.by_kind
        ],
        characters=[standing_out(c) for c in found.characters],
        court=[
            BoonOfficerOut(
                title=o.title,
                standing=standing_out(o.standing),
                owe_them=[tally_out(t) for t in o.owe_them],
                they_owe=[tally_out(t) for t in o.they_owe],
            )
            for o in found.court
        ],
        clans=[group_out(g) for g in found.clans],
        ages=[group_out(g) for g in found.ages],
        sects=[group_out(g) for g in found.sects],
        debt_age=[band_out(b) for b in found.debt_age],
        settling=BoonSettlingOut(
            count=s.count,
            weight=s.weight,
            median_months=s.median_months,
            by_kind=[
                BoonSettledKindOut(
                    kind=k.kind,  # type: ignore[arg-type]  # one of boons.KINDS
                    count=k.count,
                    weight=k.weight,
                    called_in=k.called_in,
                    forgiven=k.forgiven,
                    ignored=k.ignored,
                    median_months=k.median_months,
                )
                for k in s.by_kind
            ],
            by_clan=[band_out(b) for b in s.by_clan],
            calls_in=[collector_out(c) for c in s.calls_in],
            leaves=[collector_out(c) for c in s.leaves],
        ),
        across_clans=across_out(found.across_clans),
        across_sects=across_out(found.across_sects),
        mutual=[
            BoonMutualOut(
                first=party_out(m.first),
                second=party_out(m.second),
                owes=m.owes,
                back=m.back,
                net=standings.rounded(m.net),
            )
            for m in found.mutual
        ],
    )


def standings_reader(db: DbSession, user: User, troupe_id: uuid.UUID) -> tuple[Troupe, Keeper]:
    """The troupe, and who reads its standings (horatio.boon_standings.reader): its
    staff, or its Harpy where the troupe allows it (#749), while it keeps a ledger.
    Switched off, there is nothing to see."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    reader = standings.reader(db, user, troupe)
    if reader is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the troupe's staff, and its Harpy where the troupe allows it, see this.",
        )
    if not boons.tracked(troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This troupe doesn't keep a boon ledger.")
    return troupe, reader


def standings_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> Troupe:
    """The troupe, for those who may read its standings (`standings_reader`)."""
    return standings_reader(db, user, troupe_id)[0]


@router.get("/troupes/{troupe_id}/boon-standings")
def boon_standings(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser, scope: Scope = "active"
) -> BoonStandingsOut:
    """Where everyone stands in the troupe's boon ledger, now: totals, open boons by
    kind, each party's net, the court, clans, ages and sects, how old open debt is,
    how boons get settled, boons across clan and sect lines, and those who owe each
    other. "active" leaves out boons that involve someone dead or off-field. A Harpy
    (#749) reads who has left only as the court knows it."""
    troupe, reader = standings_reader(db, user, troupe_id)
    return standings_out(troupe, standings.standings_of(db, troupe, scope, reader.court))


@router.put("/troupes/{troupe_id}/boon-weights")
def set_boon_weights(
    troupe_id: uuid.UUID, body: BoonWeightsIn, db: DbSession, user: CurrentUser
) -> BoonWeightsOut:
    """What each kind of boon weighs in the troupe's standings."""
    troupe = standings_troupe(db, user, troupe_id)
    if not boons.can_manage(db, user, troupe):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the troupe's staff set this.")
    standings.set_weights(db, user, troupe, body.model_dump())
    db.commit()
    return weights_out(troupe)

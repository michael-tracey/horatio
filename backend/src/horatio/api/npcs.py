"""NPCs: a troupe's own characters, built quickly by its storytellers and assistants.
Each has a kind and a form: sheeted, or a Stock NPC (horatio.rules.stock)."""

import uuid
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import npcs, sheets
from horatio.api.characters import CharacterOut, character_out, characters_out
from horatio.api.downtimes import staff_troupe
from horatio.api.sheets import players_character
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, RuleSet, StockNpc
from horatio.permissions import TroupeAction
from horatio.rules import stock
from horatio.rules.npc_kinds import BuiltInPower, NpcKind, Resource, npc_kinds

router = APIRouter(tags=["npcs"])


class ResourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    size: int = Field(ge=1, le=50)
    # The most it can spend in a turn; 0 for none.
    per_turn: int = Field(ge=0, le=10)
    regains: str = Field(default="", max_length=200)


class CustomKind(BaseModel):
    """A custom kind, for one the book does not cover: its name, whether it is
    mortal or supernatural, and its resource."""

    name: str = Field(min_length=1, max_length=60)
    nature: Literal["mortal", "supernatural"]
    resource: ResourceIn


class Specialization(BaseModel):
    # A skill, or a discipline, path or numina the NPC's kind allows.
    type: Literal["skill", "power"]
    name: str = Field(min_length=1, max_length=200)


class StockFields(BaseModel):
    """What a Stock NPC has in place of a sheet (MET: VTM pp. 489–490)."""

    rating: int = Field(ge=1, le=20)
    specializations: list[Specialization] = Field(default=[], max_length=20)
    notes: str = Field(default="", max_length=10000)


class StockIn(StockFields):
    npc_kind: str
    custom_kind: CustomKind | None = None


class NewNpc(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # The rule set, for an NPC made without a kind: "ghoul" makes a ghoul, anything
    # else a vampire. With a kind, the kind decides.
    splat: str = "vampire"
    # Build through the creation wizard rather than setting ratings directly.
    wizard: bool = False
    # What it is (GET /npc-kinds), and the custom kind's set-up for "custom".
    npc_kind: str | None = None
    custom_kind: CustomKind | None = None
    npc_form: Literal["sheeted", "stock"] = "sheeted"
    # A Stock NPC's rating and specializations; rating 1 and none if left out.
    stock: StockFields | None = None


class NpcOut(CharacterOut):
    # A Stock NPC's rating; None for a sheeted one.
    stock_rating: int | None
    # Staff list it on the troupe's Who's Who though it holds no title there.
    on_whos_who: bool


class ResourceOut(BaseModel):
    name: str
    size: int
    per_turn: int
    regains: str


class BuiltInPowerOut(BaseModel):
    name: str
    # Dots of the discipline `name`: a number, or "rating"; None for one power.
    dots: int | Literal["rating"] | None
    discipline: str | None
    category: str | None
    from_rating: int | None
    note: str


class NuminaOut(BaseModel):
    name: str
    page: int
    levels: list[str]


class PanelsOut(BaseModel):
    """The panels of the sheet and Play View a kind has (horatio.rules.npc_kinds)."""

    beast: bool
    frenzy: bool
    morality: bool
    generation: bool
    feed: bool


class NpcKindOut(BaseModel):
    key: str
    name: str
    group: str
    nature: Literal["mortal", "partly_mortal", "supernatural"]
    page: int
    to_page: int | None
    resource: ResourceOut
    # Any discipline or path may be a specialization; else only `specializations`
    # ("Thaumaturgy: *" for any Thaumaturgy path) and its numina.
    any_discipline: bool
    specializations: list[str]
    specialization_label: str
    numina: list[NuminaOut]
    powers: list[BuiltInPowerOut]
    health_per_rating: int
    rating_max: int
    notes: list[str]
    # The storyteller names it and sets it up on each NPC.
    custom: bool
    # What a sheeted NPC of this kind has of the Vampire sheet and Play View.
    panels: PanelsOut


class SkillPool(BaseModel):
    name: str
    pool: int


class PowerDots(BaseModel):
    name: str
    dots: int


class StatBlockOut(BaseModel):
    """What the book prints for a Stock NPC (MET: VTM p. 490)."""

    rating: int
    # The test pool in most challenges.
    pool: int
    skill_pools: list[SkillPool]
    powers: list[PowerDots]
    built_in: list[BuiltInPowerOut]
    health: int
    resource: ResourceOut
    willpower: int
    retests: bool
    # What no Stock NPC has (p. 490).
    rules: list[str]


class StockNpcOut(BaseModel):
    character_id: uuid.UUID
    # The troupe it belongs to, whose NPCs tab has its builder.
    troupe_id: uuid.UUID | None
    npc_kind: str
    kind: NpcKindOut
    custom_kind: CustomKind | None
    rating: int
    specializations: list[Specialization]
    notes: str
    stats: StatBlockOut


def resource_out(resource: Resource) -> ResourceOut:
    return ResourceOut(
        name=resource.name,
        size=resource.size,
        per_turn=resource.per_turn,
        regains=resource.regains,
    )


def power_out(power: BuiltInPower) -> BuiltInPowerOut:
    return BuiltInPowerOut(
        name=power.name,
        dots=power.dots,
        discipline=power.discipline,
        category=power.category,
        from_rating=power.from_rating,
        note=power.note,
    )


def kind_out(kind: NpcKind) -> NpcKindOut:
    return NpcKindOut(
        key=kind.key,
        name=kind.label,
        group=kind.group,
        nature=kind.nature,
        page=kind.page,
        to_page=kind.to_page,
        resource=resource_out(kind.resource),
        any_discipline=kind.specializations == "any",
        specializations=[] if kind.specializations == "any" else list(kind.specializations),
        specialization_label=kind.specialization_label,
        numina=[NuminaOut(name=n.name, page=n.page, levels=list(n.levels)) for n in kind.numina],
        powers=[power_out(p) for p in kind.powers],
        health_per_rating=kind.health_per_rating,
        rating_max=kind.rating_max,
        notes=list(kind.notes),
        custom=kind.custom,
        panels=PanelsOut(**asdict(kind.panels)),
    )


def stock_out(db: DbSession, npc: Character) -> StockNpcOut:
    row, stats = npcs.stat_block(db, npc)
    assert npc.npc_kind is not None
    return StockNpcOut(
        character_id=npc.id,
        troupe_id=npc.owner_troupe_id,
        npc_kind=npc.npc_kind,
        kind=kind_out(npcs.kind_of(npc)),
        custom_kind=CustomKind.model_validate(npc.npc_custom_kind) if npc.npc_custom_kind else None,
        rating=row.rating,
        specializations=[Specialization.model_validate(s) for s in row.specializations],
        notes=row.notes,
        stats=StatBlockOut(
            rating=stats.rating,
            pool=stats.pool,
            skill_pools=[SkillPool(name=n, pool=p) for n, p in stats.skill_pools],
            powers=[PowerDots(name=n, dots=d) for n, d in stats.powers],
            built_in=[power_out(p) for p in stats.built_in],
            health=stats.health,
            resource=resource_out(stats.resource),
            willpower=stats.willpower,
            retests=stats.retests,
            rules=list(stock.STOCK_RULES),
        ),
    )


def custom_dict(custom: CustomKind | None) -> dict[str, Any] | None:
    return custom.model_dump() if custom is not None else None


class Rating(BaseModel):
    category: str
    name: str
    detail: str = Field(default="", max_length=200)
    # Null for an unrated choice such as a clan; 0 removes a rated trait.
    rating: int | None = Field(default=None, ge=0)


class TallyLineOut(BaseModel):
    category: str
    name: str
    detail: str
    rating: int
    cost: int | None
    note: str


class Tally(BaseModel):
    total: int
    lines: list[TallyLineOut]


@router.get("/npc-kinds")
def list_npc_kinds(user: CurrentUser) -> list[NpcKindOut]:
    """Every kind an NPC can be, from the rules data (MET: VTM pp. 489–505)."""
    return [kind_out(kind) for kind in npc_kinds().values()]


@router.get("/troupes/{troupe_id}/npcs")
def list_npcs(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[NpcOut]:
    staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_NPCS)
    found = list(
        db.scalars(
            select(Character)
            .where(Character.kind == "npc", Character.owner_troupe_id == troupe_id)
            .order_by(Character.name)
        )
    )
    ratings = {
        row.character_id: row.rating
        for row in db.scalars(
            select(StockNpc).where(StockNpc.character_id.in_([c.id for c in found]))
        )
    }
    listed = {c.id for c in found if c.on_whos_who}
    return [
        NpcOut(**out.model_dump(), stock_rating=ratings.get(out.id), on_whos_who=out.id in listed)
        for out in characters_out(db, found)
    ]


@router.post("/troupes/{troupe_id}/npcs", status_code=status.HTTP_201_CREATED)
def create_npc(
    troupe_id: uuid.UUID, body: NewNpc, db: DbSession, user: CurrentUser
) -> CharacterOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_NPCS)
    npc_kind = body.npc_kind or ("ghoul" if body.splat == "ghoul" else "vampire")
    splat = npcs.splat_for(npc_kind)
    if db.scalar(select(RuleSet.id).where(RuleSet.splat == splat)) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No rules for {splat!r}.")
    if body.stock is not None and body.npc_form != "stock":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Only a Stock NPC has a rating of its own."
        )
    custom = custom_dict(body.custom_kind)
    npc = npcs.create_npc(
        db, user, troupe, splat, body.name, body.wizard, npc_kind, body.npc_form, custom
    )
    if body.stock is not None:
        set_stock_fields(db, user, npc, npc_kind, custom, body.stock)
    db.commit()
    return character_out(db, npc)


def set_stock_fields(
    db: DbSession,
    user: CurrentUser,
    npc: Character,
    npc_kind: str,
    custom: dict[str, Any] | None,
    fields: StockFields,
) -> None:
    npcs.set_stock(
        db,
        user,
        npc,
        npc_kind,
        custom,
        fields.rating,
        [stock.Specialization(s.type, s.name) for s in fields.specializations],
        fields.notes,
    )


@router.get("/characters/{character_id}/npc/stock")
def read_stock(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> StockNpcOut:
    """A Stock NPC's rating, specializations and notes, and the stat block they make."""
    return stock_out(db, players_character(db, user, character_id))


@router.put("/characters/{character_id}/npc/stock")
def set_stock(
    character_id: uuid.UUID, body: StockIn, db: DbSession, user: CurrentUser
) -> StockNpcOut:
    """Change a Stock NPC's kind, rating, specializations and notes."""
    npc = players_character(db, user, character_id)
    set_stock_fields(db, user, npc, body.npc_kind, custom_dict(body.custom_kind), body)
    db.commit()
    return stock_out(db, npc)


class SheetedOut(BaseModel):
    character: CharacterOut
    # What the sheet could not carry over: powers and numina the Vampire rule set
    # has no trait for.
    left_out: list[str]


@router.post("/characters/{character_id}/npc/sheeted")
def make_sheeted(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> SheetedOut:
    """Turn a Stock NPC into a sheeted one, its sheet starting from its rating and
    specializations (horatio.npcs.make_sheeted). There is no turning back."""
    npc = players_character(db, user, character_id)
    if npc.kind != "npc" or npc.npc_form != "stock":
        raise HTTPException(status.HTTP_409_CONFLICT, f"{npc.name} is not a Stock NPC.")
    with sheets.checked(db, npc, user):
        made = npcs.make_sheeted(db, user, npc)
    db.commit()
    return SheetedOut(character=character_out(db, npc), left_out=list(made.left_out))


@router.put("/characters/{character_id}/npc/ratings")
def set_rating(character_id: uuid.UUID, body: Rating, db: DbSession, user: CurrentUser) -> Tally:
    """Set one of an NPC's traits straight to a rating, and get the new tally."""
    npc = players_character(db, user, character_id)
    with sheets.checked(db, npc, user):
        npcs.set_rating(db, user, npc, body.category, body.name, body.detail, body.rating)
    db.commit()
    return tally(character_id, db, user)


@router.get("/characters/{character_id}/npc/tally")
def tally(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Tally:
    """What the NPC's sheet would be worth in experience under its troupe's rules."""
    npc = players_character(db, user, character_id)
    if npc.kind != "npc":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only NPCs have a tally.")
    total, lines = npcs.tally(db, npc)
    return Tally(
        total=total,
        lines=[
            TallyLineOut(
                category=line.category,
                name=line.name,
                detail=line.detail,
                rating=line.rating,
                cost=line.cost,
                note=line.note,
            )
            for line in lines
        ],
    )

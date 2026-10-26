"""A troupe's house merits and flaws (horatio.house_traits): its storytellers make,
change, archive and delete them; its running staff apply them to its characters,
and remove them."""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import house_preview, house_traits, sheets
from horatio.api.downtimes import staff_troupe
from horatio.api.sheets import SheetOut, sheet_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, CharacterTrait, HouseTrait, Troupe
from horatio.permissions import TroupeAction, require_troupe_action, visible_character
from horatio.rules.house_effects import DEFAULTS, normalised
from horatio.rules.model import house_label, house_page

router = APIRouter(tags=["house traits"])


class EffectBlock(BaseModel):
    """One thing a house merit or flaw does on the sheet (horatio.rules.house_effects).
    Each kind reads only its own fields."""

    # free_up_to: the first `amount` dots of `names` (one, or the player's choice of
    # one) are free; free_choices: the player picks `count` of `names`, each with
    # `amount` free; add: each of `names` goes up or down by `amount` (health
    # levels); raise_max: `names` (none: the whole category) go `amount` higher;
    # cost_percent, price_in_clan, price_out_of_clan: what `names` cost; extra_in_clan:
    # one more in-clan discipline from `names`; requires, forbids: a clan, a sect or a
    # trait at a rating (`test`), with a check's `strength`.
    kind: Literal[
        "free_up_to",
        "free_choices",
        "add",
        "raise_max",
        "cost_percent",
        "price_in_clan",
        "price_out_of_clan",
        "extra_in_clan",
        "requires",
        "forbids",
    ]
    category: str = Field(default="", max_length=100)
    names: list[str] = Field(default_factory=list[str], max_length=60)
    amount: int = 0
    count: int = 1
    # One field of the trait (Performance: Singing), for a raise or a price.
    detail: str = Field(default="", max_length=100)
    test: Literal["clan", "sect", "trait"] = "trait"
    # For a check on a trait: which, and at least what rating.
    name: str = Field(default="", max_length=100)
    rating: int | None = None
    # As a check's: "refuse", "complete" (by the end of creation), "review" (or staff
    # approve it), "note".
    strength: Literal["refuse", "complete", "review", "note"] = "refuse"


def block_out(stored: dict[str, Any]) -> EffectBlock:
    return EffectBlock.model_validate({**DEFAULTS, **stored})


class HouseTraitIn(BaseModel):
    category: house_traits.Category
    name: str = Field(min_length=1, max_length=100)
    points: int = Field(ge=1, le=7)
    # General, Clan or Sabbat: for the merit limit and the filters.
    kind: house_traits.Kind = "General"
    # "staff": given by staff only; "building": available when building for the troupe.
    availability: house_traits.Availability
    # Only chosen during character creation, like some book merits.
    creation_only: bool = False
    description: str = Field(default="", max_length=4000)
    requirement: str = Field(default="", max_length=200)
    splat: str = "vampire"
    # What it does on the sheet; none: what its description says, ruled at the table.
    effects: list[EffectBlock] = Field(default_factory=list[EffectBlock], max_length=20)

    def to_spec(self) -> house_traits.Spec:
        return house_traits.Spec(
            category=self.category,
            name=self.name.strip(),
            points=self.points,
            kind=self.kind,
            availability=self.availability,
            creation_only=self.creation_only,
            description=self.description.strip(),
            requirement=self.requirement.strip(),
            splat=self.splat,
            effects=tuple(normalised(b.model_dump()) for b in self.effects),
        )


class HouseTraitOut(BaseModel):
    id: uuid.UUID
    troupe_id: uuid.UUID
    splat: str
    category: str
    name: str
    points: int
    kind: str
    availability: str
    creation_only: bool
    description: str
    requirement: str
    archived: bool
    # "House merit of Night Court", and its page reference, "House rule — Night Court".
    label: str
    page: str
    # How many characters hold it.
    holders: int
    effects: list[EffectBlock]
    # What the effects do, in words: shown under its description.
    summary: str


class HolderOut(BaseModel):
    character_id: uuid.UUID
    name: str
    kind: str


class ArchiveIn(BaseModel):
    archived: bool


def out(db: DbSession, house: HouseTrait, troupe: Troupe) -> HouseTraitOut:
    read = house_traits.effects_of(db, house)
    return HouseTraitOut(
        id=house.id,
        troupe_id=house.troupe_id,
        splat=house.splat,
        category=house.category,
        name=house.name,
        points=house.points,
        kind=house.kind,
        availability=house.availability,
        creation_only=house.creation_only,
        description=house.description,
        requirement=house.requirement,
        archived=house.archived_at is not None,
        label=house_label(house.category, troupe.name),
        page=house_page(troupe.name),
        holders=len(house_traits.holders(db, house)),
        effects=[block_out(b) for b in house.effects],
        summary=read.summary if read is not None else "",
    )


def troupe_house_trait(db: DbSession, troupe: Troupe, house_trait_id: uuid.UUID) -> HouseTrait:
    house = db.get(HouseTrait, house_trait_id)
    if house is None or house.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such house merit or flaw.")
    return house


@router.get("/troupes/{troupe_id}/house-traits")
def list_house_traits(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[HouseTraitOut]:
    """The troupe's own merits and flaws, archived ones too, for its staff."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return [
        out(db, h, troupe)
        for h in db.scalars(
            select(HouseTrait)
            .where(HouseTrait.troupe_id == troupe.id)
            .order_by(HouseTrait.category.desc(), HouseTrait.name)
        )
    ]


@router.post("/troupes/{troupe_id}/house-traits", status_code=status.HTTP_201_CREATED)
def add_house_trait(
    troupe_id: uuid.UUID, body: HouseTraitIn, db: DbSession, user: CurrentUser
) -> HouseTraitOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    house = house_traits.create(db, user, troupe, body.to_spec())
    db.commit()
    return out(db, house, troupe)


@router.put("/troupes/{troupe_id}/house-traits/{house_trait_id}")
def change_house_trait(
    troupe_id: uuid.UUID,
    house_trait_id: uuid.UUID,
    body: HouseTraitIn,
    db: DbSession,
    user: CurrentUser,
) -> HouseTraitOut:
    """Change it for every character that holds it (`holders` lists them first).
    Their ratings follow its points; XP already spent is not worked out again."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    house = troupe_house_trait(db, troupe, house_trait_id)
    house_traits.change(db, user, troupe, house, body.to_spec())
    db.commit()
    return out(db, house, troupe)


class PreviewIn(BaseModel):
    trait: HouseTraitIn
    # The one being changed; none for a new one.
    house_trait_id: uuid.UUID | None = None
    # One of the troupe's characters to try it on; none for a new character.
    character_id: uuid.UUID | None = None


class BlockProblemOut(BaseModel):
    # Which block, counted from 0.
    index: int
    message: str


class CheckPreviewOut(BaseModel):
    text: str
    met: bool
    strength: str


class SampleOut(BaseModel):
    character_id: uuid.UUID
    name: str
    kind: str


class PreviewOut(BaseModel):
    """ "A character with this would…": what it does on a sample sheet."""

    # "a new character", or the character's name.
    sample: str
    # Where the player chooses, what they were taken to choose: "Herd".
    choosing: str
    summary: str
    changes: list[str]
    checks: list[CheckPreviewOut]
    problems: list[BlockProblemOut]
    # The troupe's characters it can be tried on.
    samples: list[SampleOut]


@router.post("/troupes/{troupe_id}/house-traits/preview")
def preview_house_trait(
    troupe_id: uuid.UUID, body: PreviewIn, db: DbSession, user: CurrentUser
) -> PreviewOut:
    """Try a house merit or flaw, as it is being made, on a sample sheet: what its
    effects would change there, and which blocks cannot be used and why. Nothing is
    saved."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    house = (
        troupe_house_trait(db, troupe, body.house_trait_id)
        if body.house_trait_id is not None
        else None
    )
    spec = body.trait.to_spec()
    house_traits.check_spec(db, troupe, spec, house)
    character = house_preview.sample_character(db, body.character_id)
    found = house_preview.preview(db, troupe, spec, house, character)
    return PreviewOut(
        sample=found.sample,
        choosing=found.choosing,
        summary=found.summary,
        changes=found.changes,
        checks=[CheckPreviewOut(text=c.text, met=c.met, strength=c.strength) for c in found.checks],
        problems=[BlockProblemOut(index=i, message=m) for i, m in found.problems],
        samples=[SampleOut(character_id=c.id, name=c.name, kind=c.kind) for c in found.samples],
    )


@router.get("/troupes/{troupe_id}/house-traits/{house_trait_id}/holders")
def house_trait_holders(
    troupe_id: uuid.UUID, house_trait_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[HolderOut]:
    """The characters a change to it would change."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    house = troupe_house_trait(db, troupe, house_trait_id)
    return [
        HolderOut(character_id=c.id, name=c.name, kind=c.kind)
        for c in house_traits.holders(db, house)
    ]


@router.put("/troupes/{troupe_id}/house-traits/{house_trait_id}/archived")
def archive_house_trait(
    troupe_id: uuid.UUID,
    house_trait_id: uuid.UUID,
    body: ArchiveIn,
    db: DbSession,
    user: CurrentUser,
) -> HouseTraitOut:
    """Archive it, so no one new takes it while those who hold it keep it; or bring it back."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    house = troupe_house_trait(db, troupe, house_trait_id)
    house_traits.archive(db, user, troupe, house, body.archived)
    db.commit()
    return out(db, house, troupe)


@router.delete(
    "/troupes/{troupe_id}/house-traits/{house_trait_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_house_trait(
    troupe_id: uuid.UUID, house_trait_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Response:
    """Only one nobody holds."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    house = troupe_house_trait(db, troupe, house_trait_id)
    house_traits.delete(db, user, troupe, house)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- On a character ------------------------------------------------------------


class OfferOut(BaseModel):
    """A house merit or flaw staff can apply to the character."""

    id: uuid.UUID
    category: str
    name: str
    points: int
    kind: str
    availability: str
    description: str
    label: str
    # What its effects do, in words.
    summary: str
    # The character holds it already.
    held: bool


class ApplyIn(BaseModel):
    house_trait_id: uuid.UUID
    # Given free, costing no XP; otherwise charged at its points, like a purchase.
    free: bool = False
    # A free merit counts toward the 7-point merit limit unless this is False.
    counts_toward_limit: bool = True
    reason: str = Field(min_length=1, max_length=500)


class RemoveIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def staffed_character(
    db: DbSession, user: CurrentUser, character_id: uuid.UUID
) -> tuple[Character, Troupe]:
    """The character, and the troupe whose house traits it can hold, whose running
    staff `user` must be."""
    character = visible_character(db, user, character_id)
    troupe_id = sheets.rules_troupe(character)
    if troupe_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only a character with a home troupe, or being built for one, holds house merits.",
        )
    troupe = db.get_one(Troupe, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.APPROVE_CHANGES)
    return character, troupe


@router.get("/characters/{character_id}/house-traits")
def character_house_traits(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[OfferOut]:
    """The house merits and flaws staff can apply to the character: its home troupe's
    (or, while it is being built, the troupe it is built for), not archived."""
    character, troupe = staffed_character(db, user, character_id)
    held = set(
        db.scalars(
            select(CharacterTrait.trait_definition_id).where(
                CharacterTrait.character_id == character.id
            )
        )
    )
    return [
        OfferOut(
            id=h.id,
            category=h.category,
            name=h.name,
            points=h.points,
            kind=h.kind,
            availability=h.availability,
            description=h.description,
            label=house_label(h.category, troupe.name),
            summary=read.summary if (read := house_traits.effects_of(db, h)) else "",
            held=h.trait_definition_id in held,
        )
        for h in house_traits.offered_to(db, character)
    ]


@router.post("/characters/{character_id}/house-traits")
def apply_house_trait(
    character_id: uuid.UUID, body: ApplyIn, db: DbSession, user: CurrentUser
) -> SheetOut:
    """Running staff of the character's own troupe apply one of its house merits or
    flaws: free or charged, and with a reason for the logs. Never to a character
    only visiting the troupe."""
    character = visible_character(db, user, character_id)
    house = db.get(HouseTrait, body.house_trait_id)
    if house is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such house merit or flaw.")
    require_troupe_action(
        db, user, db.get_one(Troupe, house.troupe_id), TroupeAction.APPROVE_CHANGES
    )
    character = sheets.lock_character(db, character.id)
    house_traits.apply(
        db,
        user,
        character,
        house,
        free=body.free,
        counts_toward_limit=body.counts_toward_limit,
        reason=body.reason.strip(),
    )
    db.commit()
    return sheet_out(db, character)


@router.post("/characters/{character_id}/house-traits/{house_trait_id}/remove")
def remove_house_trait(
    character_id: uuid.UUID,
    house_trait_id: uuid.UUID,
    body: RemoveIn,
    db: DbSession,
    user: CurrentUser,
) -> SheetOut:
    """Running staff of the troupe take one of its house merits or flaws off the
    character, with a reason."""
    character, troupe = staffed_character(db, user, character_id)
    house = db.get(HouseTrait, house_trait_id)
    if house is None or house.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such house merit or flaw.")
    character = sheets.lock_character(db, character.id)
    house_traits.remove(db, user, character, house, body.reason.strip())
    db.commit()
    return sheet_out(db, character)

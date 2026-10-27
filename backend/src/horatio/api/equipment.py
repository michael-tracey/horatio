"""Equipment (horatio.equipment): the rule set's kinds, grades, qualities and sample
items, and the check an item's editor asks as it is built."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import NoResultFound

from horatio.auth.deps import CurrentUser, DbSession
from horatio.equipment import ItemModifier, ItemQuality, assess, equipment_rules
from horatio.rules.equipment import EquipmentRules, Facts

router = APIRouter(prefix="/rules/{splat}/equipment", tags=["equipment"])


class EquipmentKindOut(BaseModel):
    key: str
    name: str
    description: str
    # What an item of the kind is with no qualities: None where it doesn't apply.
    hands: int | None
    damage: int | None
    shots: int | None
    range: str | None
    # A rule about the kind as a whole: one worn at a time.
    note: str
    page: str | None


class EquipmentGradeOut(BaseModel):
    key: str
    name: str
    description: str
    # None: no limit (a special item).
    max_qualities: int | None
    page: str | None


class EquipmentQualityOut(BaseModel):
    kind: str
    name: str
    # What it does, in a line of our own words.
    effect: str
    # What it does at the table, in a few words: "+3 initiative".
    play: str
    page: str | None
    # What it does to an item (horatio.rules.equipment).
    two_handed: bool
    needs_one_hand: bool
    no_slot_when_crafted: bool
    repeatable: bool
    needs_detail: bool
    # What its detail is, to ask for it; set without needs_detail, it is optional.
    detail_prompt: str | None
    ammo: bool
    excludes: list[str]


class EquipmentItemQuality(BaseModel):
    name: str
    detail: str = ""


class EquipmentFactsOut(BaseModel):
    hands: int | None
    damage: int | None
    shots: int | None
    range: str | None
    # Whom it does aggravated damage to.
    aggravated_against: list[str]


class EquipmentModifierOut(BaseModel):
    """What one of an item's qualities does to its holder's test pools while it is
    equipped (issue #306): a modifier, as a player's own is."""

    quality: str
    # The item and quality: "Katana: Accurate".
    label: str
    amount: int
    # As a player's own modifier names them ("pool:attack:Melee", "pool:dodge"), or
    # "purpose": the challenges a piece of miscellaneous gear is for, which no pool
    # on the Pools tab is.
    pools: str
    # When it counts: "attacks with it", "against firearms".
    when: str
    # It counts only in a situation the Pools tab can't tell, so the pool shows it
    # on a line of its own rather than in its total.
    situational: bool


def modifier_out(modifier: ItemModifier) -> EquipmentModifierOut:
    return EquipmentModifierOut(
        quality=modifier.quality,
        label=modifier.label,
        amount=modifier.amount,
        pools=modifier.pools,
        when=modifier.when,
        situational=modifier.situational,
    )


class EquipmentTemplateOut(BaseModel):
    name: str
    kind: str
    grade: str
    qualities: list[EquipmentItemQuality]
    page: str | None
    facts: EquipmentFactsOut


class EquipmentOut(BaseModel):
    kinds: list[EquipmentKindOut]
    grades: list[EquipmentGradeOut]
    # Every kind's, in the book's order.
    qualities: list[EquipmentQualityOut]
    templates: list[EquipmentTemplateOut]


class EquipmentCheckIn(BaseModel):
    kind: str
    grade: str
    qualities: list[EquipmentItemQuality] = Field(default_factory=list[EquipmentItemQuality])
    # Its Artisan and Masterwork were added while crafting, and take no slot.
    crafted: bool = False


class EquipmentCheckOut(EquipmentFactsOut):
    # Each rule the item breaks, in a sentence; empty when it keeps them all.
    problems: list[str]


def rules_for(db: DbSession, splat: str) -> EquipmentRules:
    try:
        return equipment_rules(db, splat)
    except NoResultFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No rules for {splat!r}.") from None


def facts_out(facts: Facts) -> EquipmentFactsOut:
    return EquipmentFactsOut(
        hands=facts.hands,
        damage=facts.damage,
        shots=facts.shots,
        range=facts.range,
        aggravated_against=list(facts.aggravated_against),
    )


@router.get("")
def equipment(splat: str, db: DbSession, user: CurrentUser) -> EquipmentOut:
    """The kinds of item, the grades, every quality of each kind and the book's
    sample items, each with its facts."""
    rules = rules_for(db, splat)
    return EquipmentOut(
        kinds=[
            EquipmentKindOut(
                key=k.key,
                name=k.name,
                description=k.description,
                hands=k.hands,
                damage=k.damage,
                shots=k.shots,
                range=k.range,
                note=k.note,
                page=k.page,
            )
            for k in rules.kinds.values()
        ],
        grades=[
            EquipmentGradeOut(
                key=g.key,
                name=g.name,
                description=g.description,
                max_qualities=g.max_qualities,
                page=g.page,
            )
            for g in rules.grades.values()
        ],
        qualities=[
            EquipmentQualityOut(
                kind=q.kind,
                name=q.name,
                effect=q.effect,
                play=q.play,
                page=q.page,
                two_handed=q.two_handed,
                needs_one_hand=q.needs_one_hand,
                no_slot_when_crafted=q.no_slot_when_crafted,
                repeatable=q.repeatable,
                needs_detail=q.needs_detail,
                detail_prompt=q.detail_prompt,
                ammo=q.ammo,
                excludes=list(q.excludes),
            )
            for q in rules.qualities.values()
        ],
        templates=[
            EquipmentTemplateOut(
                name=t.name,
                kind=t.kind,
                grade=t.grade,
                qualities=[EquipmentItemQuality(name=q.name, detail=q.detail) for q in t.qualities],
                page=t.page,
                facts=facts_out(assess(rules, t.kind, t.qualities, t.grade).facts),
            )
            for t in rules.templates
        ],
    )


@router.post("/check")
def check(
    splat: str, body: EquipmentCheckIn, db: DbSession, user: CurrentUser
) -> EquipmentCheckOut:
    """An item's facts and every rule it breaks, without making it: what an editor
    shows as the item is built."""
    found = assess(
        rules_for(db, splat),
        body.kind,
        [ItemQuality(q.name, q.detail) for q in body.qualities],
        body.grade,
        crafted=body.crafted,
    )
    return EquipmentCheckOut(**facts_out(found.facts).model_dump(), problems=list(found.problems))

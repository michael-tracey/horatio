"""The rules a character plays by: categories, the trait catalogue, and house rules."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import RuleSet, Troupe
from horatio.rules.grants import choices
from horatio.rules.model import HouseTraitData
from horatio.rules.splats import SPLATS, splat_order
from horatio.rules.status import GENERAL
from horatio.rules.store import read_troupe_rules

router = APIRouter(prefix="/rules", tags=["rules"])


class CategoryOut(BaseModel):
    key: str
    name: str
    group: str
    rated: bool
    max_rating: int | None
    # Only shown when the character has this choice, e.g. faction needs the Sabbat sect.
    requires: dict[str, str] | None = None
    # XP to swap the choice for another after creation (a focus); None if it cannot be.
    change_cost: int | None = None
    # Most points a character can hold here (merits) or be paid by it (flaws).
    points_limit: int | None = None
    # Worked out from the rest of the sheet (health, Willpower); never bought.
    derived: bool = False
    # For a specialisation category: the skill or background it specialises.
    specializes: dict[str, str] | None = None


class HouseOut(BaseModel):
    """A troupe's own merit or flaw (horatio.house_traits), marked ★ wherever it shows."""

    id: uuid.UUID
    troupe_id: uuid.UUID
    troupe_name: str
    # "House merit of Night Court".
    label: str
    # "staff" (given by staff only) or "building".
    availability: str
    archived: bool
    creation_only: bool
    # Whether a player can pick it: available when building, and not archived.
    offered: bool
    # What its effects do, in words: shown under its description.
    summary: str = ""
    # The disciplines it lets the character add in-clan, one of them.
    in_clan: list[str] = Field(default_factory=list[str])


class TraitOut(BaseModel):
    category: str
    name: str
    description: str | None
    page_reference: str | None
    # A merit or flaw is always bought at this rating.
    fixed_rating: int | None
    # Text from a house rule for this trait in the troupe asked about.
    house_rule: str | None
    # For a clan: its in-clan disciplines.
    in_clan: list[str] | None
    # For a skill: the attribute it generally goes with (Physical, Social or Mental).
    attribute: str | None
    # For a trait that grants something the player picks (Personal Cult: which
    # background): the picks, to put in its detail.
    choices: list[str] | None = None
    # For a merit or flaw: its kind (General, Clan, Morality, ...) and who it is
    # for (a clan, bloodline or generation), for filtering lists.
    kind: str | None = None
    requirement: str | None = None
    # A skill bought once per field, such as Performance: Singing (p. 92): one
    # the catalogue says needs a specialisation.
    needs_field: bool = False
    # A trait bought once for each of several, each named in its detail with its
    # own dots (Retainers, Alternate Identity, pp. 98-99, 104): what one is called.
    instance: str | None = None
    # A troupe's own merit or flaw; its page reference reads "House rule — <troupe>".
    house: HouseOut | None = None


class CatalogueOut(BaseModel):
    splat: str
    name: str
    categories: list[CategoryOut]
    traits: list[TraitOut]


class SplatOut(BaseModel):
    splat: str
    # Its name in the app: "Vampire", "Ghoul".
    label: str
    # A character of it is bound to a vampire, its domitor, whose clan it takes.
    has_domitor: bool


@router.get("")
def splats(db: DbSession, user: CurrentUser) -> list[SplatOut]:
    """The splats there are rules for, vampires first: what a character can be."""
    loaded = sorted(db.scalars(select(RuleSet.splat)), key=splat_order)
    return [
        SplatOut(splat=s, label=SPLATS[s].label or s, has_domitor=SPLATS[s].has_domitor)
        for s in loaded
        if s in SPLATS
    ]


@router.get("/{splat}")
def catalogue(
    splat: str,
    db: DbSession,
    user: CurrentUser,
    category: str | None = None,
    troupe_id: uuid.UUID | None = None,
) -> CatalogueOut:
    """The rule set's categories and traits, with any house-rule text from `troupe_id`.
    A troupe that takes only some sects does not see traits for the others (the
    Sabbat's Rituals), nor a category left empty without them."""
    troupe = db.get(Troupe, troupe_id) if troupe_id is not None else None
    if troupe_id is not None and troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    try:
        rules = read_troupe_rules(db, splat, troupe_id)
    except NoResultFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No rules for {splat!r}.") from None
    house_text = {(r.category, r.trait): r.text for r in rules.house_rules if r.trait and r.text}
    chooses: dict[tuple[str, str], list[str]] = {}
    for grant in rules.rule_set.grants:
        # The player of a free_choices grant chooses beside the merit, not in its detail.
        options = choices(grant, rules.rule_set) if grant.kind != "free_choices" else []
        if options:
            source = (grant.source["category"], grant.source["name"])
            chooses[source] = sorted(set(chooses.get(source, [])) | set(options))
    sects = set(troupe.allowed_sects) if troupe is not None else set()
    # General status is every sect's (horatio.rules.status).
    traits = [
        t
        for t in sorted(rules.rule_set.traits.values(), key=lambda t: (t.category, t.name))
        if not (sects and t.properties.get("sect", GENERAL) not in sects | {GENERAL})
    ]
    emptied = {c for c, _ in rules.rule_set.traits} - {t.category for t in traits}
    return CatalogueOut(
        splat=rules.splat,
        name=rules.rule_set.name,
        categories=[
            CategoryOut(
                key=c.key,
                name=c.name,
                group=c.group,
                rated=c.rated,
                max_rating=c.max_rating,
                requires=dict(c.requires) if c.requires else None,
                change_cost=c.change_cost,
                points_limit=c.points_limit,
                derived=c.derived,
                specializes=dict(c.specializes) if c.specializes else None,
            )
            for c in rules.rule_set.categories.values()
            if c.key not in emptied
        ],
        traits=[
            TraitOut(
                category=t.category,
                name=t.name,
                description=t.description,
                page_reference=t.page_reference,
                fixed_rating=rules.fixed_rating(t.category, t.name),
                house_rule=house_text.get((t.category, t.name)),
                in_clan=t.properties.get("in_clan"),
                attribute=t.properties.get("attribute"),
                choices=chooses.get((t.category, t.name)),
                kind=t.properties.get("type"),
                requirement=t.properties.get("requirement")
                if t.properties.get("requirement") != "requires_specialization"
                else None,
                needs_field=t.category == "skills"
                and t.properties.get("requirement") == "requires_specialization",
                instance=t.properties.get("instance"),
                house=house_out(rules.house_trait(t.category, t.name)),
            )
            for t in traits
            if category is None or t.category == category
        ],
    )


def house_out(house: HouseTraitData | None) -> HouseOut | None:
    if house is None:
        return None
    return HouseOut(
        id=house.id,
        troupe_id=house.troupe_id,
        troupe_name=house.troupe_name,
        label=house.label,
        availability=house.availability,
        archived=house.archived,
        creation_only=house.creation_only,
        offered=house.offered,
        summary=house.summary,
        in_clan=list(house.in_clan),
    )

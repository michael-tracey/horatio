"""The rules a character plays by: categories, the trait catalogue, and house rules;
and all of it at once for the rules browser, as played in one troupe."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from horatio.auth.deps import CurrentUser, DbSession
from horatio.clan_merits import book_defaults
from horatio.models import RuleSet, Troupe
from horatio.reference import catalogue as power_catalogue
from horatio.rules import conditions, pricing
from horatio.rules.feeding import clan_family
from horatio.rules.files import EVERYWHERE
from horatio.rules.grants import choices
from horatio.rules.model import CostRuleData, HouseTraitData, RuleSetData, TraitData, TroupeRules
from horatio.rules.splats import SPLATS, splat_order
from horatio.rules.status import GENERAL
from horatio.rules.store import read_troupe_rules, same_subject

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
    # For a clan: its weakness in a line, and the book's page for it. A bloodline with
    # none of its own has its clan's.
    weakness: str | None = None
    weakness_page: str | None = None
    # For a skill: the attribute it generally goes with (Physical, Social or Mental).
    attribute: str | None
    # For a trait that grants something the player picks (Personal Cult: which
    # background), or names one of a few in its detail (Stolen Potential: which
    # attribute): the picks, to put in its detail.
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
                **clan_weakness(rules.rule_set, t),
                attribute=t.properties.get("attribute"),
                choices=chooses.get((t.category, t.name)) or t.properties.get("choices"),
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


def clan_weakness(rule_set: RuleSetData, trait: TraitData) -> dict[str, str | None]:
    """A clan's weakness and its page: its own, or for a bloodline with none, its
    clan's (MET: VtM p. 42). Nothing for any other trait."""
    if trait.category != "clan":
        return {}
    found = trait.properties
    if "weakness" not in found:
        found = rule_set.trait_properties("clan", clan_family(trait.name))
    return {"weakness": found.get("weakness"), "weakness_page": found.get("weakness_page")}


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


# --- The rules browser --------------------------------------------------------


class PriceOut(BaseModel):
    """A cost rule in words: for one trait, or every trait of its category."""

    category: str
    trait: str | None
    # When it applies, such as "in-clan"; None for always.
    when: str | None
    price: str
    # A house rule of the troupe asked about: its own wording, and the rule set's
    # price it replaces (None for one the rule set does not have).
    house: bool
    text: str | None = None
    book: str | None = None


class TraitCheckOut(BaseModel):
    """A check, in the words a player reads when a change breaks it: about one trait,
    every trait whose name starts with `prefix`, or (neither) a whole category."""

    key: str
    category: str
    trait: str | None
    prefix: str | None
    message: str
    page: str | None
    # As the rule set has it (refuse, complete, review or note), and the troupe's
    # own strength where it changed it: one of those, or "off".
    strength: str
    house: str | None = None


class NotAllowedOut(BaseModel):
    """A trait the troupe does not let anyone buy: a house price of "cannot be bought"
    for it, or for its whole category, that nothing more particular overrides."""

    category: str
    name: str
    text: str | None


class DisciplinePowerOut(BaseModel):
    """A discipline's power at one dot, from the Play View's power reference: a
    short note in our own words."""

    discipline: str
    level: int
    name: str
    note: str


class RarityOut(BaseModel):
    """How rare a clan is: in the troupe's setting, or in each sect's as the book has it.
    Its bloodlines are as rare as it."""

    clan: str
    text: str
    page: str | None
    # The troupe's own rarity, not the book's.
    house: bool
    # The bloodline it plays as by default, in words ("Tzimisce: Carpathian", or each
    # sect's as the book has it); None for none. `default_house`: the troupe's own.
    default: str | None = None
    default_house: bool = False


class RulesBrowserOut(BaseModel):
    catalogue: CatalogueOut
    # The troupe whose house rules are applied; None for the book's rules.
    troupe_name: str | None
    prices: list[PriceOut]
    requirements: list[TraitCheckOut]
    not_allowed: list[NotAllowedOut]
    powers: list[DisciplinePowerOut]
    rarities: list[RarityOut]


@router.get("/{splat}/browse")
def browse(
    splat: str, db: DbSession, user: CurrentUser, troupe_id: uuid.UUID | None = None
) -> RulesBrowserOut:
    """Every trait of the rule set with what the rules browser shows beside it: its
    prices, the checks about it, its powers and a clan's rarity, all read from the
    rules already loaded. Given `troupe_id`, as played there: its house prices, checks,
    merits and flaws and clan rarities, and the traits it does not allow. Anyone
    signed in may read it, as they may the troupe's house rules."""
    troupe = db.get(Troupe, troupe_id) if troupe_id is not None else None
    if troupe_id is not None and (
        troupe is None or (troupe.archived_at is not None and not user.is_custodian)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    found = catalogue(splat, db, user, troupe_id=troupe_id)
    rules = read_troupe_rules(db, splat, troupe_id)
    rule_set = rules.rule_set
    # Archived house merits are for the characters that hold them, not to read about.
    found.traits = [t for t in found.traits if not (t.house and t.house.archived)]
    shown = {t.category for t in found.traits}
    disciplines = {t.name for t in found.traits if t.category == "disciplines"}
    powers = power_catalogue().powers
    return RulesBrowserOut(
        catalogue=found,
        troupe_name=troupe.name if troupe is not None else None,
        prices=prices(rules, shown),
        requirements=[
            TraitCheckOut(
                key=c.key,
                category=c.category,
                trait=c.name,
                prefix=c.name_prefix,
                message=c.message,
                page=c.page,
                strength=c.strength,
                house=rules.check_overrides.get(c.key),
            )
            for c in rule_set.checks
            if c.category in shown and c.message and c.detail is None
        ],
        not_allowed=not_allowed(rules, found.traits),
        powers=[
            DisciplinePowerOut(discipline=d, level=p["level"], name=p["name"], note=p["note"])
            for d in sorted(disciplines)
            for p in powers.get(d, [])
        ],
        rarities=clan_rarities(rule_set, troupe),
    )


def unit_of(rule_set: RuleSetData, category: str) -> str:
    return "point" if rule_set.categories[category].points_limit is not None else "dot"


def prices(rules: TroupeRules, categories: set[str]) -> list[PriceOut]:
    """The rule set's prices for those categories, each the troupe has replaced
    swapped for its own, then the troupe's other prices. A troupe's price for a
    merit or flaw of fixed value says the book's value beside it."""
    rule_set = rules.rule_set
    words = SPLATS[rule_set.splat].fact_words

    def out(rule: CostRuleData, book: str | None = None) -> PriceOut:
        return PriceOut(
            category=rule.category,
            trait=rule.trait,
            when=conditions.describe(rule.condition, words),
            price=pricing.describe(rule, unit_of(rule_set, rule.category)),
            house=rule.house,
            text=rule.text,
            book=book,
        )

    found: list[PriceOut] = []
    house = [r for r in rules.house_rules if r.category in categories]
    for rule in rule_set.cost_rules:
        if rule.category not in categories:
            continue
        replacing = next((h for h in house if same_subject(h, rule)), None)
        if replacing is None:
            found.append(out(rule))
        else:
            found.append(out(replacing, pricing.describe(rule, unit_of(rule_set, rule.category))))
    for h in house:
        if any(same_subject(h, r) for r in rule_set.cost_rules):
            continue
        value = rule_set.trait_properties(h.category, h.trait).get("rating") if h.trait else None
        unit = unit_of(rule_set, h.category)
        found.append(out(h, f"{value} {unit}{'' if value == 1 else 's'}" if value else None))
    return found


def not_allowed(rules: TroupeRules, traits: list[TraitOut]) -> list[NotAllowedOut]:
    """The traits the troupe's house prices bar outright: "cannot be bought" with no
    condition, for the trait or its whole category, where no price could beat it for
    any character (pricing.choose_rule: a price naming the trait beats its category's,
    and one with a condition beats one without)."""
    bars = {
        (r.category, r.trait): r
        for r in rules.house_rules
        if r.scheme == "not_allowed" and not r.condition
    }
    if not bars:
        return []
    every = [*rules.house_rules, *rules.rule_set.cost_rules]

    def beaten(bar: CostRuleData, name: str) -> bool:
        return any(
            r is not bar
            and r.category == bar.category
            and ((bar.trait is None and r.trait == name) or (r.trait == bar.trait and r.condition))
            for r in every
        )

    found: list[NotAllowedOut] = []
    for t in traits:
        bar = bars.get((t.category, t.name)) or bars.get((t.category, None))
        if bar is not None and not beaten(bar, t.name):
            found.append(NotAllowedOut(category=t.category, name=t.name, text=bar.text))
    return found


def clan_rarities(rule_set: RuleSetData, troupe: Troupe | None) -> list[RarityOut]:
    """Each clan's rarity (MET: VTM pp. 403-404 and on): the troupe's own where it
    names one; else in the troupe's setting, if it takes one sect only; else in each
    sect's setting, as the book gives it (horatio.api.house_rules.clan_rarity_out)."""
    setting = troupe.allowed_sects[0] if troupe and len(troupe.allowed_sects) == 1 else None
    found: list[RarityOut] = []
    for (category, clan), trait in sorted(rule_set.traits.items()):
        if category != "clan" or ":" in clan:
            continue
        default = default_of(rule_set, clan, troupe, setting)
        book: dict[str, dict[str, str]] = dict(trait.properties.get("rarity", {}))
        house = troupe.clan_rarity.get(clan) if troupe else None
        if house:
            found.append(
                RarityOut(clan=clan, text=house.capitalize(), page=None, house=True, **default)
            )
            continue
        one = book.get(EVERYWHERE) or (book.get(setting) if setting else None)
        if one:
            text, page = one["rarity"].capitalize(), one["page"]
        elif book:
            text = ", ".join(f"{r['rarity']} for the {sect}" for sect, r in book.items())
            text, page = text[0].upper() + text[1:], None
        else:
            continue
        found.append(RarityOut(clan=clan, text=text, page=page, house=False, **default))
    return found


def default_of(
    rule_set: RuleSetData, clan: str, troupe: Troupe | None, setting: str | None
) -> dict[str, Any]:
    """The clan's default bloodline in words, for its RarityOut: the troupe's own where
    it names one, else the book's in the troupe's setting, or in each sect's."""
    house = troupe.default_bloodlines.get(clan) if troupe else None
    if house is not None:
        text = house if house != clan else f"None: the plain {clan}"
        return {"default": text, "default_house": True}
    book = book_defaults(rule_set, clan)
    if setting:
        return {"default": book.get(setting)}
    text = ", ".join(f"{line} for the {sect}" for sect, line in book.items())
    return {"default": text or None}

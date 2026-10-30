"""A troupe's locations (horatio.locations): kept by its storytellers and assistant
storytellers, with the catalogue of qualities as the troupe plays it. Its house
options for locations and its own qualities are house rules, which only
storytellers change. Narrators and players never see the record."""

import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from horatio import audit, locations, specializations
from horatio.api.downtimes import staff_troupe
from horatio.api.roster import LogEntry, log_entries
from horatio.auth.deps import CurrentUser, DbSession
from horatio.influence import SPECIALIZATIONS, TYPES
from horatio.models import (
    AuditEvent,
    Character,
    Location,
    Troupe,
    TroupeLocationQuality,
    TroupeMembership,
    User,
)
from horatio.permissions import (
    TroupeAction,
    allows,
    is_staff_for,
    require_troupe_action,
    troupe_role,
    visible_character,
)
from horatio.rules import locations as catalogue
from horatio.rules.locations import LocationRules, Quality, Suggestion
from horatio.rules.store import read_troupe_rules
from horatio.sheets import unprocessable

router = APIRouter(tags=["locations"])

Kind = Literal["standard", "prestige", "iconic", "haven"]
Control = Literal["character", "named", "none", "uncontrollable"]
InfluenceType = Literal["elite", "underworld"]
QualityKind = Literal["standard", "iconic", "supernatural", "elysium"]
Strength = Literal["refuse", "note"]


# --- the catalogue ----------------------------------------------------------------------


class LocationSuggestion(BaseModel):
    """What a quest for a quality should ask for: a trait (or any one of `traits`)
    at `levels` by the location's rating, lowest first, or a power, or words."""

    trait: str = ""
    traits: list[str] = []
    power: str = ""
    levels: list[int] = []
    detail: str = ""
    expend: bool = False
    alternative: str = ""
    text: str = ""


class LocationQualityOut(BaseModel):
    name: str
    kind: QualityKind
    text: str
    page: str | None
    detail: str
    repeatable: bool
    counts: bool
    excludes: list[str]
    # The skill that gives it free on a Haven of its holder's.
    haven_free: str
    suggested: list[LocationSuggestion]
    # The house option it comes with, by name; the troupe's own quality.
    option: str | None
    house: bool
    # A house option's limits on it.
    min_rating: int | None
    per_qualities: int | None


class NegativeQualityOut(BaseModel):
    name: str
    page: str
    removed: str
    levels: list[str]
    raised_by: str
    names_who: bool


class HavenAdvantageOut(BaseModel):
    name: str
    page: str
    text: str
    needs: str


class LocationTypeOut(BaseModel):
    key: Kind
    name: str
    per_rating: int
    iconic: bool
    quest: str
    text: str


class LocationOptionOut(BaseModel):
    key: str
    name: str
    text: str
    on: bool


class OwnLocationQualityOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: QualityKind
    text: str
    detail: str
    repeatable: bool
    suggested: list[LocationSuggestion]
    archived: bool
    # The troupe's locations that have it.
    held_by: int


class LocationCharacter(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    # Its Haven background's dots, for placing its Haven.
    haven: int


class LocationCatalogueOut(BaseModel):
    types: list[LocationTypeOut]
    options: list[LocationOptionOut]
    qualities: list[LocationQualityOut]
    negatives: list[NegativeQualityOut]
    haven_advantages: list[HavenAdvantageOut]
    own: list[OwnLocationQualityOut]
    # What going over a character's control limit does here.
    limit: Strength
    pages: dict[str, str]
    book: str
    # Each influence type's areas, the troupe's list where it has one.
    influence_areas: dict[str, list[str]]
    characters: list[LocationCharacter]
    feeding_blocks: list[str]
    # The reader changes the house options and the troupe's own qualities.
    can_change_house: bool


def suggestion_model(s: Suggestion) -> LocationSuggestion:
    return LocationSuggestion(**{**asdict(s), "traits": list(s.traits), "levels": list(s.levels)})


def option_name(rules: LocationRules, key: str | None) -> str | None:
    return rules.catalogue.options[key].name if key else None


def quality_out(rules: LocationRules, q: Quality) -> LocationQualityOut:
    return LocationQualityOut(
        name=q.name,
        kind=q.kind,
        text=q.text,
        page=q.page,
        detail=q.detail,
        repeatable=q.repeatable or q.name in rules.per_qualities,
        counts=q.counts and q.kind != "elysium",
        excludes=list(q.excludes),
        haven_free=q.haven_free,
        suggested=[suggestion_model(s) for s in q.suggested],
        option=option_name(rules, q.option),
        house=q.house,
        min_rating=rules.min_rating.get(q.name),
        per_qualities=rules.per_qualities.get(q.name),
    )


def troupe_characters(db: DbSession, troupe_id: uuid.UUID) -> list[Character]:
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe_id, TroupeMembership.left_at.is_(None)
    )
    return list(
        db.scalars(
            select(Character)
            .where(
                or_(Character.id.in_(members), Character.owner_troupe_id == troupe_id),
                Character.status != "retired",
            )
            .order_by(Character.name)
        )
    )


def influence_areas(db: DbSession, troupe: Troupe) -> dict[str, list[str]]:
    rules = read_troupe_rules(db, "vampire", troupe.id)
    listed = specializations.troupe_options(db, troupe.id)
    found: dict[str, list[str]] = {}
    for t in TYPES:
        category = SPECIALIZATIONS[t]
        found[t] = listed.get(category) or sorted(
            n for (c, n) in rules.rule_set.traits if c == category and n != specializations.CUSTOM
        )
    return found


def own_out(db: DbSession, troupe: Troupe, row: TroupeLocationQuality) -> OwnLocationQualityOut:
    return OwnLocationQualityOut(
        id=row.id,
        name=row.name,
        kind=row.kind,  # type: ignore[arg-type]
        text=row.text,
        detail=row.detail,
        repeatable=row.repeatable,
        suggested=[LocationSuggestion(**s) for s in row.suggested],
        archived=row.archived_at is not None,
        held_by=len(locations.holders(db, troupe, row.name)),
    )


def catalogue_out(db: DbSession, user: User, troupe: Troupe) -> LocationCatalogueOut:
    rules = locations.rules_for(db, troupe)
    cat = rules.catalogue
    blocks = db.scalars(
        select(Location.feeding_block)
        .where(Location.troupe_id == troupe.id, Location.feeding_block != "")
        .distinct()
    )
    return LocationCatalogueOut(
        types=[LocationTypeOut(**asdict(t)) for t in cat.types.values()],  # type: ignore[arg-type]
        options=[
            LocationOptionOut(key=o.key, name=o.name, text=o.text, on=rules.on(o.key))
            for o in cat.options.values()
        ],
        qualities=[quality_out(rules, q) for q in rules.qualities.values()],
        negatives=[
            NegativeQualityOut(**{**asdict(n), "levels": list(n.levels)})
            for n in cat.negatives.values()
        ],
        haven_advantages=[HavenAdvantageOut(**asdict(a)) for a in cat.haven_advantages.values()],
        own=[own_out(db, troupe, q) for q in locations.own_qualities(db, troupe.id)],
        limit=troupe.location_limit,  # type: ignore[arg-type]
        pages=dict(cat.pages),
        book=catalogue.BOOK,
        influence_areas=influence_areas(db, troupe),
        characters=[
            LocationCharacter(
                id=c.id,
                name=c.name,
                kind=c.kind,
                haven=locations.rating_of(db, c, "backgrounds", locations.HAVEN),
            )
            for c in troupe_characters(db, troupe.id)
        ],
        feeding_blocks=sorted(blocks, key=str.casefold),
        can_change_house=allows(
            troupe_role(db, user, troupe),
            TroupeAction.MANAGE_HOUSE_RULES,
            is_custodian=user.is_custodian,
        ),
    )


@router.get("/troupes/{troupe_id}/locations/catalogue")
def read_catalogue(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> LocationCatalogueOut:
    """The location types, qualities, negative qualities and Haven advantages as the
    troupe plays them, with its house options, and what a location can name."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_LOCATIONS)
    return catalogue_out(db, user, troupe)


# --- house options --------------------------------------------------------------------


class LocationOptionIn(BaseModel):
    on: bool


@router.put("/troupes/{troupe_id}/location-options/{key}")
def set_option(
    troupe_id: uuid.UUID, key: str, body: LocationOptionIn, db: DbSession, user: CurrentUser
) -> LocationCatalogueOut:
    """Switch one of the house options for locations on or off."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    option = catalogue.load_catalogue().options.get(key)
    if option is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such house option.")
    off = [k for k in troupe.location_options_off if k != key]
    troupe.location_options_off = off if body.on else [*off, key]
    audit.record(
        db,
        user,
        "house.location_option",
        troupe_id=troupe.id,
        option=option.name,
        setting="on" if body.on else "off",
    )
    db.commit()
    return catalogue_out(db, user, troupe)


class LocationLimitIn(BaseModel):
    strength: Strength


LIMIT_TEXT = {"refuse": "refuse it", "note": "allow it, and show staff"}


@router.put("/troupes/{troupe_id}/location-limit")
def set_limit(
    troupe_id: uuid.UUID, body: LocationLimitIn, db: DbSession, user: CurrentUser
) -> LocationCatalogueOut:
    """What going over a character's control limit does: refuse it, or note it."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    troupe.location_limit = body.strength
    audit.record(
        db, user, "house.location_limit", troupe_id=troupe.id, setting=LIMIT_TEXT[body.strength]
    )
    db.commit()
    return catalogue_out(db, user, troupe)


# --- the troupe's own qualities -------------------------------------------------------


class OwnLocationQualityIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: QualityKind = "standard"
    text: str = Field(min_length=1, max_length=2000)
    detail: str = Field(default="", max_length=80)
    repeatable: bool = False
    suggested: list[LocationSuggestion] = []


def checked_suggestions(body: OwnLocationQualityIn) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for n, s in enumerate(body.suggested):
        raw = {k: v for k, v in s.model_dump().items() if v not in ("", [], False)}
        try:
            catalogue.suggestion_from(raw, f"Suggested requirement {n + 1}")
        except ValueError as e:
            raise unprocessable(f"{e}.") from e
        found.append(raw)
    return found


def own_row(db: DbSession, troupe: Troupe, quality_id: uuid.UUID) -> TroupeLocationQuality:
    row = db.get(TroupeLocationQuality, quality_id)
    if row is None or row.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such location quality.")
    return row


@router.post("/troupes/{troupe_id}/location-qualities", status_code=status.HTTP_201_CREATED)
def add_quality(
    troupe_id: uuid.UUID, body: OwnLocationQualityIn, db: DbSession, user: CurrentUser
) -> OwnLocationQualityOut:
    """Add a quality of the troupe's own to the catalogue."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    row = TroupeLocationQuality(
        troupe_id=troupe.id,
        name=locations.checked_quality_name(db, troupe, body.name, None),
        kind=body.kind,
        text=body.text.strip(),
        detail=locations.tidy(body.detail),
        repeatable=body.repeatable,
        suggested=checked_suggestions(body),
    )
    db.add(row)
    audit.record(
        db, user, "house.location_quality_added", troupe_id=troupe.id, name=row.name, kind=row.kind
    )
    db.commit()
    return own_out(db, troupe, row)


@router.put("/troupes/{troupe_id}/location-qualities/{quality_id}")
def change_quality(
    troupe_id: uuid.UUID,
    quality_id: uuid.UUID,
    body: OwnLocationQualityIn,
    db: DbSession,
    user: CurrentUser,
) -> OwnLocationQualityOut:
    """Change one of the troupe's own qualities; locations that have it keep it,
    renamed with it."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    row = own_row(db, troupe, quality_id)
    name = locations.checked_quality_name(db, troupe, body.name, row)
    if name != row.name:
        locations.rename_quality(db, troupe, row.name, name)
    row.name = name
    row.kind = body.kind
    row.text = body.text.strip()
    row.detail = locations.tidy(body.detail)
    row.repeatable = body.repeatable
    row.suggested = checked_suggestions(body)
    audit.record(db, user, "house.location_quality_changed", troupe_id=troupe.id, name=row.name)
    db.commit()
    return own_out(db, troupe, row)


class LocationQualityArchivedIn(BaseModel):
    archived: bool


@router.put("/troupes/{troupe_id}/location-qualities/{quality_id}/archived")
def archive_quality(
    troupe_id: uuid.UUID,
    quality_id: uuid.UUID,
    body: LocationQualityArchivedIn,
    db: DbSession,
    user: CurrentUser,
) -> OwnLocationQualityOut:
    """Stop offering one of the troupe's qualities, or offer it again. Locations that
    have it keep it."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    row = own_row(db, troupe, quality_id)
    row.archived_at = datetime.now(UTC) if body.archived else None
    audit.record(
        db,
        user,
        "house.location_quality_archived" if body.archived else "house.location_quality_restored",
        troupe_id=troupe.id,
        name=row.name,
    )
    db.commit()
    return own_out(db, troupe, row)


# --- locations ------------------------------------------------------------------------


class LocationQualityIn(BaseModel):
    name: str = Field(max_length=80)
    detail: str = Field(default="", max_length=120)


class LocationNegativeIn(BaseModel):
    name: str
    level: int = Field(default=1, ge=1, le=4)
    # Kept from the controller (p. 127).
    secret: bool = False
    # LocationPerson is behind it, such as "hunters".
    by: str = Field(default="", max_length=120)


class LocationIn(BaseModel):
    """A location's fields; on a change, those left out stay as they are."""

    name: str = Field(min_length=1, max_length=120)
    kind: Kind = "standard"
    rating: int = Field(default=1, ge=1, le=5)
    parent_id: uuid.UUID | None = None
    qualities: list[LocationQualityIn] = []
    negatives: list[LocationNegativeIn] = []
    control: Control = "none"
    controller_id: uuid.UUID | None = None
    controller_name: str = Field(default="", max_length=120)
    joint_id: uuid.UUID | None = None
    joint_name: str = Field(default="", max_length=120)
    heir_id: uuid.UUID | None = None
    heir_name: str = Field(default="", max_length=120)
    influence_type: InfluenceType | None = None
    influence_area: str = Field(default="", max_length=120)
    address: str = Field(default="", max_length=500)
    web_address: str = Field(default="", max_length=500)
    map_link: str = Field(default="", max_length=1000)
    feeding_block: str = Field(default="", max_length=120)
    locked: bool = False
    haven_of_id: uuid.UUID | None = None
    haven_advantages: list[str] = []
    elysium_since: int | None = Field(default=None, ge=1, le=9999)
    notes: str = Field(default="", max_length=10000)


class LocationChange(LocationIn):
    name: str = Field(default="", max_length=120)


class LocationPerson(BaseModel):
    # None for someone known only by name.
    id: uuid.UUID | None
    name: str


class LocationRef(BaseModel):
    id: uuid.UUID
    name: str


class HeldLocationQualityOut(BaseModel):
    name: str
    detail: str
    kind: QualityKind
    # Still in the troupe's catalogue; one no longer offered stays.
    known: bool
    # It counts toward the location's qualities.
    counts: bool
    house: bool
    # Its holder has it free here, as their Haven (Firewall, Security): why.
    free_here: str


class HeldNegativeQualityOut(BaseModel):
    name: str
    level: int
    secret: bool
    by: str
    # What its level does.
    effect: str


class LocationSubsidiaryOut(BaseModel):
    id: uuid.UUID
    name: str
    control: Control
    controller: LocationPerson | None
    # Its parent's controller controls it too.
    with_parent: bool


class LocationOut(BaseModel):
    id: uuid.UUID
    troupe_id: uuid.UUID
    name: str
    parent: LocationRef | None
    kind: Kind
    rating: int
    qualities: list[HeldLocationQualityOut]
    # How many count toward its limit, and the limit (p. 121).
    quality_count: int
    most_qualities: int
    negatives: list[HeldNegativeQualityOut]
    control: Control
    controller: LocationPerson | None
    joint: LocationPerson | None
    heir: LocationPerson | None
    influence_type: InfluenceType | None
    influence_area: str
    address: str
    web_address: str
    map_link: str
    feeding_block: str
    locked: bool
    haven_of: LocationPerson | None
    haven_advantages: list[str]
    elysium_since: int | None
    # How many Elysium qualities it has earned.
    elysium_qualities: int | None
    notes: str
    subsidiaries: list[LocationSubsidiaryOut]
    # For the controller: why it doesn't count toward their control limit, if not.
    not_counted: str | None
    updated_at: datetime


class SavedLocationOut(LocationOut):
    # What staff should know about the change: a control limit gone over.
    warnings: list[str]


class LocationDetailOut(LocationOut):
    log: list[LogEntry]


def who_out(db: DbSession, character_id: uuid.UUID | None, name: str) -> LocationPerson | None:
    if character_id is not None:
        character = db.get(Character, character_id)
        return LocationPerson(id=character_id, name=character.name if character else "")
    return LocationPerson(id=None, name=name) if name else None


def free_here(db: DbSession, location: Location, q: Quality | None) -> str:
    """Why the Haven's owner has the quality's benefit free here (pp. 122, 123)."""
    if q is None or not q.haven_free or location.haven_of_id is None:
        return ""
    owner = db.get(Character, location.haven_of_id)
    if owner is None:
        return ""
    if locations.rating_of(db, owner, "skills", q.haven_free) < 1:
        return f"Free on a Haven of someone with {q.haven_free}{locations.page(q.page)}."
    where = locations.page(q.page)
    return f"Free for {owner.name}, whose Haven this is, with {q.haven_free}{where}."


def location_out(db: DbSession, rules: LocationRules, location: Location) -> LocationOut:
    parent = db.get(Location, location.parent_id) if location.parent_id else None
    draft = locations.draft_of(location)
    held: list[HeldLocationQualityOut] = []
    for q in location.qualities:
        known = rules.qualities.get(q["name"])
        held.append(
            HeldLocationQualityOut(
                name=q["name"],
                detail=q.get("detail", ""),
                kind=known.kind if known else "standard",
                known=known is not None,
                counts=known is None or (known.counts and known.kind != "elysium"),
                house=known.house if known else False,
                free_here=free_here(db, location, known),
            )
        )
    negatives = [
        HeldNegativeQualityOut(
            name=n["name"],
            level=n["level"],
            secret=n.get("secret", False),
            by=n.get("by", ""),
            effect=effect(rules, n["name"], n["level"]),
        )
        for n in location.negatives
    ]
    under = locations.subsidiaries(db, location)
    controller = location.controller_id
    return LocationOut(
        id=location.id,
        troupe_id=location.troupe_id,
        name=location.name,
        parent=LocationRef(id=parent.id, name=parent.name) if parent else None,
        kind=location.kind,  # type: ignore[arg-type]
        rating=location.rating,
        qualities=held,
        quality_count=locations.counted_qualities(rules, draft),
        most_qualities=locations.most_qualities(rules, draft),
        negatives=negatives,
        control=location.control,  # type: ignore[arg-type]
        controller=who_out(db, location.controller_id, location.controller_name),
        joint=who_out(db, location.joint_id, location.joint_name),
        heir=who_out(db, location.heir_id, location.heir_name),
        influence_type=location.influence_type,  # type: ignore[arg-type]
        influence_area=location.influence_area,
        address=location.address,
        web_address=location.web_address,
        map_link=location.map_link,
        feeding_block=location.feeding_block,
        locked=location.locked,
        haven_of=who_out(db, location.haven_of_id, ""),
        haven_advantages=list(location.haven_advantages),
        elysium_since=location.elysium_since,
        elysium_qualities=(
            catalogue.elysium_qualities(max(0, locations.this_year() - location.elysium_since))
            if location.elysium_since is not None
            else None
        ),
        notes=location.notes,
        subsidiaries=[
            LocationSubsidiaryOut(
                id=s.id,
                name=s.name,
                control=s.control,  # type: ignore[arg-type]
                controller=who_out(db, s.controller_id, s.controller_name),
                with_parent=controller is not None and controller in (s.controller_id, s.joint_id),
            )
            for s in under
        ],
        not_counted=(
            locations.not_counted(db, location, controller) if controller is not None else None
        ),
        updated_at=location.updated_at,
    )


def effect(rules: LocationRules, name: str, level: int) -> str:
    known = rules.negatives.get(name)
    if known is None:
        return ""
    return known.levels[min(level, len(known.levels)) - 1]


def managed_location(db: DbSession, user: User, location_id: uuid.UUID) -> tuple[Location, Troupe]:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such location.")
    troupe = db.get_one(Troupe, location.troupe_id)
    try:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_LOCATIONS)
    except HTTPException:
        # Not even whether it exists, to those who can't see the list.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such location.") from None
    return location, troupe


def draft_from(body: LocationIn, base: locations.Draft | None = None) -> locations.Draft:
    given = body.model_dump(exclude_unset=base is not None)
    if "qualities" in given:
        given["qualities"] = [locations.QualityIn(**q) for q in given["qualities"]]
    if "negatives" in given:
        given["negatives"] = [locations.NegativeIn(**n) for n in given["negatives"]]
    if base is None:
        return locations.Draft(**given)
    return replace(base, **given)


def detail_out(db: DbSession, location: Location) -> LocationDetailOut:
    troupe = db.get_one(Troupe, location.troupe_id)
    rules = locations.rules_for(db, troupe)
    query = (
        select(AuditEvent, User.display_name)
        .outerjoin(User, AuditEvent.actor_id == User.id)
        .where(
            AuditEvent.troupe_id == location.troupe_id,
            AuditEvent.data["location_id"].astext == str(location.id),
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(200)
    )
    return LocationDetailOut(
        **location_out(db, rules, location).model_dump(), log=log_entries(db, query)
    )


@router.get("/troupes/{troupe_id}/locations")
def list_locations(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[LocationOut]:
    """Every location the troupe keeps, by name."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_LOCATIONS)
    rules = locations.rules_for(db, troupe)
    found = db.scalars(
        select(Location).where(Location.troupe_id == troupe.id).order_by(Location.name)
    )
    return [location_out(db, rules, loc) for loc in found]


@router.post("/troupes/{troupe_id}/locations", status_code=status.HTTP_201_CREATED)
def add_location(
    troupe_id: uuid.UUID, body: LocationIn, db: DbSession, user: CurrentUser
) -> SavedLocationOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_LOCATIONS)
    location, warnings = locations.save(db, user, troupe, None, draft_from(body))
    db.commit()
    rules = locations.rules_for(db, troupe)
    return SavedLocationOut(**location_out(db, rules, location).model_dump(), warnings=warnings)


@router.get("/locations/{location_id}")
def read_location(location_id: uuid.UUID, db: DbSession, user: CurrentUser) -> LocationDetailOut:
    location, _ = managed_location(db, user, location_id)
    return detail_out(db, location)


@router.patch("/locations/{location_id}")
def change_location(
    location_id: uuid.UUID, body: LocationChange, db: DbSession, user: CurrentUser
) -> SavedLocationOut:
    """Change a location: the fields given, the rest as they are."""
    location, troupe = managed_location(db, user, location_id)
    draft = draft_from(body, locations.draft_of(location))
    location, warnings = locations.save(db, user, troupe, location, draft)
    db.commit()
    rules = locations.rules_for(db, troupe)
    return SavedLocationOut(**location_out(db, rules, location).model_dump(), warnings=warnings)


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_location(location_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Take a location off the list; its subsidiaries stay, with no conglomerate."""
    location, _ = managed_location(db, user, location_id)
    locations.remove(db, user, location)
    db.commit()


# --- a character's locations, for staff ---------------------------------------------------


class HeldLocationOut(BaseModel):
    id: uuid.UUID
    troupe_id: uuid.UUID
    name: str
    joint: bool
    not_counted: str | None


class LocationControlOut(BaseModel):
    # Locations counted toward its limit, in every troupe, and the limit.
    controls: int
    limit: int
    why: str
    over: bool
    # Those in troupes the reader keeps locations for.
    locations: list[HeldLocationOut]
    # Counted, in troupes the reader can't see.
    elsewhere: int


@router.get("/characters/{character_id}/locations")
def character_locations(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> LocationControlOut:
    """For staff: how many locations the character controls, of how many it may."""
    character = visible_character(db, user, character_id)
    if not is_staff_for(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only staff see a character's locations.")
    found = locations.standing(db, character)
    readable: dict[uuid.UUID, bool] = {}

    def can_read(troupe_id: uuid.UUID) -> bool:
        if troupe_id not in readable:
            troupe = db.get_one(Troupe, troupe_id)
            readable[troupe_id] = troupe.archived_at is None and allows(
                troupe_role(db, user, troupe),
                TroupeAction.MANAGE_LOCATIONS,
                is_custodian=user.is_custodian,
            )
        return readable[troupe_id]

    shown = [h for h in found.held if can_read(h.location.troupe_id)]
    return LocationControlOut(
        controls=found.controls,
        limit=found.limit,
        why=found.why,
        over=found.over,
        locations=[
            HeldLocationOut(
                id=h.location.id,
                troupe_id=h.location.troupe_id,
                name=h.location.name,
                joint=h.location.joint_id == character.id,
                not_counted=h.not_counted,
            )
            for h in shown
        ],
        elsewhere=sum(
            1 for h in found.held if h.not_counted is None and not can_read(h.location.troupe_id)
        ),
    )

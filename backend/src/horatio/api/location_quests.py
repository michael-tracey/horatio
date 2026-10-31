"""Location quests and what locations give (horatio.location_quests): players' location
requests and what their characters' locations give them; staff matching a request
to a location, planning and building a quest from it, removing negatives,
confirming a forfeit, and the Resources a party spends on a scenario."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import location_quests, locations, quests
from horatio.api.locations import (
    LocationDetailOut,
    LocationQualityIn,
    detail_out,
    managed_location,
)
from horatio.api.quests import (
    Category,
    PlayerRequestOut,
    QuestOut,
    QuestRequestOut,
    RequirementIn,
    own_character,
    player_request_out,
    quest_out,
    request_out,
    running_quest,
    staff_request,
)
from horatio.auth.deps import CurrentUser, DbSession
from horatio.location_quests import Change, RequestFields
from horatio.models import Character, Location, QuestRequest, QuestScenario, Troupe
from horatio.permissions import (
    TroupeAction,
    is_staff_for,
    require_troupe_action,
    visible_character,
)
from horatio.quest_requirements import Option, requirement_label

router = APIRouter(tags=["locations"])


# --- what a character's locations give it ------------------------------------------------


class LocationEffectOut(BaseModel):
    quality: str
    # What it gives: "Resources 1".
    gives: str
    on: bool
    # Why it is off, for staff only; its player isn't told.
    off_because: str


class HeldLocationNameOut(BaseModel):
    id: uuid.UUID
    name: str
    joint: bool
    effects: list[LocationEffectOut]


class AskableQualityOut(BaseModel):
    name: str
    text: str
    # What it can name, such as a Hangout's Contacts specialisation.
    detail: str


class HeldLocationsOut(BaseModel):
    locations: list[HeldLocationNameOut]
    # The qualities its player can ask to add, from its home troupe's catalogue.
    qualities: list[AskableQualityOut]
    # The reader is staff, so sees why an effect is off.
    staff: bool


@router.get("/characters/{character_id}/held-locations")
def held_locations(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> HeldLocationsOut:
    """The names of the locations the character controls, and what their qualities
    give it: for its player, without why one is off; for staff, with it."""
    character = visible_character(db, user, character_id)
    mine = character.kind == "pc" and character.player_id == user.id
    staff = is_staff_for(db, user, character)
    if not mine and not staff:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    held = location_quests.held(db, character)
    troupe = quests.home_troupe(db, character)
    qualities: list[AskableQualityOut] = []
    if troupe is not None and troupe.quests_enabled:
        rules = locations.rules_for(db, troupe)
        qualities = [
            AskableQualityOut(name=q.name, text=q.text, detail=q.detail)
            for q in rules.qualities.values()
            if q.kind in ("standard", "supernatural", "iconic")
        ]
    return HeldLocationsOut(
        locations=[
            HeldLocationNameOut(
                id=h.location.id,
                name=h.location.name,
                joint=h.location.joint_id == character.id,
                effects=[
                    LocationEffectOut(
                        quality=e.quality,
                        gives=e.gives,
                        on=e.on,
                        off_because=e.off_because if staff else "",
                    )
                    for e in h.effects
                    # A secret negative's own effects are off the player's sheet too.
                    if staff or not secret_effect(h.location, e.quality)
                ],
            )
            for h in held
        ],
        qualities=qualities,
        staff=staff,
    )


def secret_effect(location: Location, quality: str) -> bool:
    """Shunned's own effects, when Shunned is secret from the controller."""
    return quality == "Shunned" and any(
        n["name"] == "Shunned" and n.get("secret") for n in location.negatives
    )


# --- players' location requests ------------------------------------------------------------


@router.post("/characters/{character_id}/location-requests", status_code=status.HTTP_201_CREATED)
def request_location_quest(
    character_id: uuid.UUID, body: RequestFields, db: DbSession, user: CurrentUser
) -> PlayerRequestOut:
    """Ask to acquire, add a quality to, undermine or repair a location, or to learn
    whose locations are whose. Counts toward the troupe's requests per cycle."""
    character = own_character(db, user, character_id)
    request = location_quests.make_request(db, user, character, body)
    db.commit()
    return player_request_out(db, request)


# --- staff: matching a request ---------------------------------------------------------------


class NewLocationIn(BaseModel):
    rating: int = Field(default=1, ge=1, le=5)
    qualities: list[LocationQualityIn] = []


class MatchIn(BaseModel):
    # One of the troupe's locations; or, left out, a new standard one made from the
    # request's name, address and map link.
    location_id: uuid.UUID | None = None
    new: NewLocationIn | None = None


def keeper_request(
    db: DbSession, user: CurrentUser, request_id: uuid.UUID
) -> tuple[QuestRequest, Troupe]:
    request, troupe = staff_request(db, user, request_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_LOCATIONS)
    return request, troupe


@router.put("/quest-requests/{request_id}/location")
def match_request(
    request_id: uuid.UUID, body: MatchIn, db: DbSession, user: CurrentUser
) -> QuestRequestOut:
    """Match a request to acquire or undermine a place to the troupe's record of it,
    or make a new standard location from it."""
    request, troupe = keeper_request(db, user, request_id)
    new = (
        locations.Draft(
            name="",
            kind="standard",
            rating=body.new.rating,
            qualities=[locations.QualityIn(q.name, q.detail) for q in body.new.qualities],
        )
        if body.new is not None
        else None
    )
    location_quests.match(db, user, troupe, request, body.location_id, new)
    db.commit()
    return request_out(db, user, troupe, request)


# --- staff: planning and building a location quest -----------------------------------------


class PlanIn(BaseModel):
    change: Change
    # Who it is for: the leader, or the request's character.
    leader_id: uuid.UUID | None = None
    request_id: uuid.UUID | None = None


class DifficultyModifierOut(BaseModel):
    reason: str
    amount: int


class SuggestedRequirementOut(BaseModel):
    # The quality that suggests it.
    source: str
    # The requirement's alternatives, as the quest builder takes them.
    options: list[Option]
    label: str


class LocationQuestPlanOut(BaseModel):
    category: Category
    category_note: str
    difficulty: int
    modifiers: list[DifficultyModifierOut]
    suggestions: list[SuggestedRequirementOut]
    fewer: list[str]
    refusal: str | None
    # How the change reads: "control passes to its leader".
    change: str


def leader_of(
    db: DbSession, troupe: Troupe, leader_id: uuid.UUID | None, request_id: uuid.UUID | None
) -> tuple[Character | None, QuestRequest | None]:
    request = db.get(QuestRequest, request_id) if request_id else None
    if request_id is not None and (request is None or request.troupe_id != troupe.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such request.")
    who = request.character_id if request is not None else leader_id
    return (db.get(Character, who) if who else None), request


@router.post("/locations/{location_id}/quest-plan")
def plan_quest(
    location_id: uuid.UUID, body: PlanIn, db: DbSession, user: CurrentUser
) -> LocationQuestPlanOut:
    """The quest a change to the location takes: its category and difficulty, with
    the reasons, the requirements its qualities suggest, and why it can't be built,
    if it can't."""
    location, troupe = managed_location(db, user, location_id)
    leader, _ = leader_of(db, troupe, body.leader_id, body.request_id)
    found = location_quests.plan(db, troupe, location, body.change, leader)
    return LocationQuestPlanOut(
        category=found.category,  # type: ignore[arg-type]  # from the table
        category_note=found.category_note,
        difficulty=found.difficulty,
        modifiers=[
            DifficultyModifierOut(reason=m.reason, amount=m.amount) for m in found.modifiers
        ],
        suggestions=[
            SuggestedRequirementOut(
                source=s.source, options=s.options, label=requirement_label(s.options)
            )
            for s in found.suggestions
        ],
        fewer=found.fewer,
        refusal=found.refusal,
        change=location_quests.describe_change(location, body.change),
    )


class LocationQuestIn(BaseModel):
    location_id: uuid.UUID
    change: Change
    request_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    objective: str = Field(default="", max_length=8000)
    category: Category = "simple"
    difficulty: int = Field(default=1, ge=1, le=10)
    downtime_only: bool = False
    staff_notes: str = Field(default="", max_length=8000)
    leader_id: uuid.UUID | None = None
    # The requirements picked from the plan's suggestions, and any staff added.
    requirements: list[RequirementIn] = Field(default=[], max_length=30)


@router.post("/troupes/{troupe_id}/location-quests", status_code=status.HTTP_201_CREATED)
def build_location_quest(
    troupe_id: uuid.UUID, body: LocationQuestIn, db: DbSession, user: CurrentUser
) -> QuestOut:
    """Build a quest that changes a location when it is completed, in draft: from a
    request, or from the location's page. Refused, with the reason, when the
    location can't be targeted."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_LOCATIONS)
    location = location_quests.checked_location(db, troupe, body.location_id)
    _, request = leader_of(db, troupe, body.leader_id, body.request_id)
    fields = quests.QuestFields(
        name=body.name,
        objective=body.objective,
        category=body.category,
        difficulty=body.difficulty,
        downtime_only=body.downtime_only,
        staff_notes=body.staff_notes,
        leader_id=body.leader_id,
    )
    quest = location_quests.build(
        db,
        user,
        troupe,
        location,
        body.change,
        fields,
        [r.options for r in body.requirements],
        request,
    )
    db.commit()
    return quest_out(db, user, troupe, quest)


# --- staff: negatives and forfeits ----------------------------------------------------------


class RemoveNegativeIn(BaseModel):
    name: str
    # Who spends what removing it takes.
    character_id: uuid.UUID
    # The repair request it answers.
    request_id: uuid.UUID | None = None


@router.post("/locations/{location_id}/negatives/remove")
def remove_negative(
    location_id: uuid.UUID, body: RemoveNegativeIn, db: DbSession, user: CurrentUser
) -> LocationDetailOut:
    """Take one level of a negative off, spending what the book asks: Resources dots,
    or an Elite or Underworld action, at the location's rating (pp. 127-129)."""
    location, troupe = managed_location(db, user, location_id)
    character = db.get(Character, body.character_id)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    request = None
    if body.request_id is not None:
        request = db.get(QuestRequest, body.request_id)
        if request is None or request.troupe_id != troupe.id or request.kind != "repair":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such request.")
        if request.status in ("answered", "withdrawn"):
            raise HTTPException(status.HTTP_409_CONFLICT, "This request is already answered.")
    location_quests.remove_negative(db, user, troupe, location, body.name, character, request)
    db.commit()
    return detail_out(db, location)


@router.post("/locations/{location_id}/forfeit")
def forfeit_location(location_id: uuid.UUID, db: DbSession, user: CurrentUser) -> LocationDetailOut:
    """Confirm Insolvent ×2's forfeit: the controller, whose Resources are below its
    rating, gives it up (p. 128)."""
    location, _ = managed_location(db, user, location_id)
    location_quests.forfeit(db, user, location)
    db.commit()
    return detail_out(db, location)


# --- staff: the Resources shortcut ----------------------------------------------------------


class ResourcesIn(BaseModel):
    character_id: uuid.UUID
    dots: int = Field(ge=1, le=10)


@router.post("/quests/{quest_id}/scenarios/{number}/resources")
def expend_resources(
    quest_id: uuid.UUID, number: int, body: ResourcesIn, db: DbSession, user: CurrentUser
) -> QuestOut:
    """A member expends Resources to succeed a step of a location quest: dots equal to
    the difficulty give one success, each dot over one more (p. 120)."""
    quest, troupe = running_quest(db, user, quest_id)
    scenario = db.scalar(
        select(QuestScenario).where(
            QuestScenario.quest_id == quest.id, QuestScenario.number == number
        )
    )
    character = db.get(Character, body.character_id)
    if scenario is None or character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such scenario or character.")
    location_quests.expend_resources(db, user, quest, scenario, character, body.dots)
    db.commit()
    return quest_out(db, user, troupe, quest)

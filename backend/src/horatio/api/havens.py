"""A player's own Haven (horatio.locations, "a player's own Haven"; issue #682): the
part of their character's Haven they keep, from its sheet. Staff keep the rest on
the troupe's list of locations; what is theirs alone (notes, locks, heirs, quests,
secret negatives) is never sent here."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import locations, quests
from horatio.api.locations import Kind, effect
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Location, Troupe, User
from horatio.permissions import visible_character
from horatio.rules import locations as catalogue
from horatio.rules.locations import LocationRules

router = APIRouter(tags=["locations"])


class HavenAdvantageChoiceOut(BaseModel):
    name: str
    page: str
    text: str
    # A skill needed to take it, and whether the owner has it.
    needs: str
    allowed: bool
    # A skill that gives it free (Security), and whether the owner has it.
    free_with: str
    free: bool


class HavenNegativeOut(BaseModel):
    name: str
    level: int
    # What its level does.
    effect: str


class OwnHavenOut(BaseModel):
    id: uuid.UUID
    troupe_name: str
    name: str
    kind: Kind
    description: str
    address: str
    map_link: str
    haven_advantages: list[str]
    # Those the owner has free, with a skill that gives them.
    haven_free: list[str]
    # More advantages than the owner's Haven allows, since a skill or a dot went.
    haven_over: str | None
    # The harm done to it that its owner knows of; staff's secret ones aren't sent.
    negatives: list[HavenNegativeOut]
    # Why the owner can't change it, if they can't: retired, or a Stock Location
    # staff made their Haven.
    read_only: str | None
    updated_at: datetime


class HavenDraftOut(BaseModel):
    """The Haven its player named before any troupe accepted the character (#683)."""

    name: str
    description: str
    address: str
    map_link: str
    haven_advantages: list[str]
    haven_free: list[str]
    # More advantages than the owner's Haven allows, since a skill or a dot went.
    haven_over: str | None


class HavenOut(BaseModel):
    character_name: str
    # The owner's dots of Haven: one advantage for each (MET: VTM p. 102).
    dots: int
    advantages: list[HavenAdvantageChoiceOut]
    haven: OwnHavenOut | None
    # With no Haven on the list yet: why the owner can't put it there, if not.
    cannot_create: str | None
    # The Haven named before a troupe accepted the character: kept until one does,
    # or, if it didn't fit then, until its player puts it on the list.
    draft: HavenDraftOut | None
    # No troupe has accepted the character yet: saving keeps a draft, which the
    # first troupe to accept it puts on its list.
    drafting: bool


class OwnHavenIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)
    address: str = Field(default="", max_length=500)
    map_link: str = Field(default="", max_length=locations.MAP_LINK)
    haven_advantages: list[str] = []


def own_character(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    """The user's own PC; to anyone else it isn't there."""
    character = visible_character(db, user, character_id)
    if character.kind != "pc" or character.player_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    return character


def rules_of(db: DbSession, troupe: Troupe | None) -> LocationRules:
    if troupe is None:
        return catalogue.played(catalogue.load_catalogue(), [], [])
    return locations.rules_for(db, troupe)


def haven_out(db: DbSession, character: Character) -> HavenOut:
    location = locations.own_haven(db, character)
    home = quests.home_troupe(db, character)
    if location:
        rules = rules_of(db, db.get_one(Troupe, location.troupe_id))
    else:
        rules = locations.draft_rules(db, character) if home is None else rules_of(db, home)
    free = set(locations.free_advantages(db, rules, character))
    advantages = [
        HavenAdvantageChoiceOut(
            name=a.name,
            page=a.page,
            text=a.text,
            needs=a.needs,
            allowed=not a.needs or locations.rating_of(db, character, "skills", a.needs) > 0,
            free_with=a.free_with,
            free=a.name in free,
        )
        for a in rules.haven_advantages.values()
    ]
    drafting = location is None and home is None
    if location:
        cannot = None
    elif drafting:
        cannot = locations.cannot_draft(db, character)
    else:
        cannot = locations.cannot_create(db, character, home)
    own = None if location else locations.haven_draft(character)
    return HavenOut(
        character_name=character.name,
        dots=locations.rating_of(db, character, "backgrounds", locations.HAVEN),
        advantages=advantages,
        haven=own_out(db, rules, character, location) if location else None,
        cannot_create=cannot,
        draft=draft_out(db, rules, character, own) if own else None,
        drafting=drafting and cannot is None,
    )


def draft_out(
    db: DbSession, rules: LocationRules, character: Character, own: locations.OwnHaven
) -> HavenDraftOut:
    count = locations.haven_count(db, rules, character, own.haven_advantages)
    return HavenDraftOut(
        name=own.name,
        description=own.description,
        address=own.address,
        map_link=own.map_link,
        haven_advantages=list(own.haven_advantages),
        haven_free=list(count.free),
        haven_over=locations.haven_over(character, count),
    )


def own_out(
    db: DbSession, rules: LocationRules, character: Character, location: Location
) -> OwnHavenOut:
    count = locations.haven_count(db, rules, character, location.haven_advantages)
    return OwnHavenOut(
        id=location.id,
        troupe_name=db.get_one(Troupe, location.troupe_id).name,
        name=location.name,
        kind=location.kind,  # type: ignore[arg-type]
        description=location.description,
        address=location.address,
        map_link=location.map_link,
        haven_advantages=list(location.haven_advantages),
        haven_free=list(count.free),
        haven_over=locations.haven_over(character, count),
        negatives=[
            HavenNegativeOut(
                name=n["name"], level=n["level"], effect=effect(rules, n["name"], n["level"])
            )
            for n in location.negatives
            if not n.get("secret", False)
        ],
        read_only=locations.read_only(db, character, location),
        updated_at=location.updated_at,
    )


def own_from(body: OwnHavenIn) -> locations.OwnHaven:
    return locations.OwnHaven(
        name=body.name,
        description=body.description,
        address=body.address,
        map_link=body.map_link,
        haven_advantages=list(body.haven_advantages),
    )


@router.get("/characters/{character_id}/haven")
def read_haven(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> HavenOut:
    """The character's Haven as its player keeps it, and the advantages to choose from."""
    return haven_out(db, own_character(db, user, character_id))


@router.post("/characters/{character_id}/haven", status_code=status.HTTP_201_CREATED)
def add_haven(
    character_id: uuid.UUID, body: OwnHavenIn, db: DbSession, user: CurrentUser
) -> HavenOut:
    """Put the character's Haven on its home troupe's list of locations."""
    character = own_character(db, user, character_id)
    home = quests.home_troupe(db, character)
    locations.save_own_haven(db, user, character, home, None, own_from(body))
    # A draft that didn't fit when the troupe accepted the character is now placed.
    character.haven_draft = None
    db.commit()
    return haven_out(db, character)


@router.put("/characters/{character_id}/haven/draft")
def keep_haven_draft(
    character_id: uuid.UUID, body: OwnHavenIn, db: DbSession, user: CurrentUser
) -> HavenOut:
    """Name the Haven before any troupe has accepted the character, as in creation:
    the first troupe to accept it puts it on its list (#683)."""
    character = own_character(db, user, character_id)
    locations.save_haven_draft(db, user, character, own_from(body))
    db.commit()
    return haven_out(db, character)


@router.put("/characters/{character_id}/haven")
def change_haven(
    character_id: uuid.UUID, body: OwnHavenIn, db: DbSession, user: CurrentUser
) -> HavenOut:
    """Change the owner's part of the character's Haven: the rest stays as staff set it."""
    character = own_character(db, user, character_id)
    location = locations.own_haven(db, character)
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{character.name} has no Haven yet.")
    locations.save_own_haven(db, user, character, None, location, own_from(body))
    db.commit()
    return haven_out(db, character)

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import (
    clan_merits,
    clan_names,
    deletion,
    domitors,
    downtimes,
    leaving,
    pictures,
    pronouns,
    renames,
    social_age,
)
from horatio.auth.deps import CurrentUser, DbSession
from horatio.creation import grant_starting_traits
from horatio.models import Approval, Character, RuleSet, Troupe, User
from horatio.permissions import (
    TroupeAction,
    allows,
    can_change_leaving,
    can_edit_character,
    troupe_role,
    visible_character,
)
from horatio.rules.npc_kinds import kind_name
from horatio.rules.splats import SPLATS
from horatio.sheets import (
    ensure_house_traits_fit,
    lock_character,
    rules_for,
    start_character,
    sync_fixed_ratings,
)

router = APIRouter(prefix="/characters", tags=["characters"])


class CharacterOut(BaseModel):
    id: uuid.UUID
    player_id: uuid.UUID
    splat: str
    name: str
    # Its pronouns, such as "she/her"; None for none given.
    pronouns: str | None
    status: str
    home_troupe_id: uuid.UUID | None
    # Until a home troupe accepts it, the troupe whose rules it is built by.
    building_troupe_id: uuid.UUID | None
    # The troupe it has asked to make its home, while the storytellers decide.
    asking_troupe_id: uuid.UUID | None
    creation_complete: bool
    kind: str  # pc | npc
    # The troupe an NPC belongs to.
    owner_troupe_id: uuid.UUID | None
    # The first day its player can rename it again; None if they can now.
    next_rename_on: date | None
    # Where its picture is (add "/48.webp" and so on; see horatio.pictures), or None.
    picture: str | None
    # For the placeholder shown without a picture: initials on the clan's colour.
    clan: str | None
    # What an NPC is (horatio.rules.npc_kinds), its kind's name (a custom kind's
    # own), and its form: sheeted or stock. All None for a PC.
    npc_kind: str | None
    npc_kind_name: str | None
    npc_form: str | None
    # Why a retired character left (horatio.leaving): final_death, off_field or
    # inactive; None while it is active, or if it was retired without one.
    left_reason: str | None
    # Its troupes' Who's Who lists it under "No longer with us".
    left_listed: bool
    # What its sheet calls the clan stored as "Assamite" (horatio.clan_names): as the
    # troupe whose rules it plays by does, or Banu Haqim outside any troupe.
    assamite_name: Literal["Banu Haqim", "Assamite"] = "Banu Haqim"


class CharacterListOut(CharacterOut):
    """A character in its player's list, with where it stands and what waits for them."""

    home_troupe_name: str | None
    asking_troupe_name: str | None
    # When the downtime it has yet to submit is due; None for none.
    downtime_due: datetime | None
    # When each cycle's results last reached the player, newest first; the page judges
    # which are new to them.
    delivered: list[datetime]


class PlacedDots(BaseModel):
    name: str
    detail: str = ""
    rating: int


class DomitorIn(BaseModel):
    """A ghoul's domitor: a vampire PC or NPC in Horatio, or one that is not, by name
    and clan ("Brujah: True Brujah" for a bloodline)."""

    character_id: uuid.UUID | None = None
    name: str = Field(default="", max_length=200)
    clan: str | None = None
    # For a Caitiff not in Horatio: the three in-clan disciplines it chose (MET: VTM
    # p. 246), which staff check at approval. A linked domitor's are its own.
    in_clan: list[str] = []
    # When the ghoul already has discipline dots: keep them, or move all of them to
    # the new domitor's in-clan disciplines, as `moved` says (MET: VTM p. 297).
    disciplines: Literal["keep", "move"] = "keep"
    moved: list[PlacedDots] = []


class DomitorOut(BaseModel):
    # The linked domitor, if it is in Horatio.
    character_id: uuid.UUID | None
    name: str
    # The domitor's clan and bloodline, which are the ghoul's.
    clan: str | None
    # The domitor's in-clan disciplines, which are the ghoul's: its clan's, or the
    # three a Caitiff chose.
    in_clan: list[str]


class DomitorChoiceOut(BaseModel):
    """A vampire a ghoul could be bound to."""

    character_id: uuid.UUID
    name: str
    kind: str  # pc | npc
    clan: str
    # The in-clan disciplines the ghoul would take from it: its clan's, or the three a
    # Caitiff chose.
    in_clan: list[str]


class NewCharacter(BaseModel):
    splat: str
    name: str = Field(min_length=1, max_length=200)
    # Build by this troupe's rules; None for the plain rule set.
    building_troupe_id: uuid.UUID | None = None
    # A ghoul's domitor, if known yet.
    domitor: DomitorIn | None = None


class BuildingTroupe(BaseModel):
    troupe_id: uuid.UUID | None


class CharacterChanges(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class Leaving(BaseModel):
    """Why a character left, and whether its troupes' Who's Who lists it."""

    reason: leaving.Reason
    # For its log.
    note: str = Field(default="", max_length=2000)
    listed: bool


class PronounsIn(BaseModel):
    # Free text, such as "she/her" or "any"; empty or None for none.
    pronouns: str | None = Field(default=None, max_length=200)


def character_out(db: Session, character: Character) -> CharacterOut:
    return characters_out(db, [character])[0]


def characters_out(db: Session, characters: Iterable[Character]) -> list[CharacterOut]:
    found = list(characters)
    standing = social_age.standings(db, [c.id for c in found])
    pending = select(Approval.character_id, Approval.troupe_id).where(
        Approval.character_id.in_([c.id for c in found]),
        Approval.kind == "home_troupe_change",
        Approval.status == "pending",
    )
    asking = {character_id: troupe_id for character_id, troupe_id in db.execute(pending)}
    called = clan_names.for_characters(db, found)
    return [
        CharacterOut(
            id=character.id,
            player_id=character.player_id,
            splat=character.splat,
            name=character.name,
            pronouns=character.pronouns,
            status=character.status,
            home_troupe_id=character.home_troupe_id,
            building_troupe_id=character.building_troupe_id,
            asking_troupe_id=asking.get(character.id),
            creation_complete=character.creation_completed_at is not None,
            kind=character.kind,
            owner_troupe_id=character.owner_troupe_id,
            picture=pictures.picture_url(character.id, character.picture_id),
            clan=standing[character.id].clan,
            next_rename_on=renames.next_rename_on(db, character),
            npc_kind=character.npc_kind,
            npc_kind_name=kind_name(character.npc_kind, character.npc_custom_kind),
            npc_form=character.npc_form,
            left_reason=character.left_reason,
            left_listed=character.left_listed,
            assamite_name=called[character.id],  # type: ignore[arg-type]  # checked by the database
        )
        for character in found
    ]


def editable_character(db: DbSession, user: CurrentUser, character_id: uuid.UUID) -> Character:
    character = visible_character(db, user, character_id)
    if not can_edit_character(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the character's player can change it.")
    if character.status == "retired":
        raise HTTPException(status.HTTP_409_CONFLICT, "This character is retired.")
    return character


@router.get("")
def my_characters(db: DbSession, user: CurrentUser) -> list[CharacterListOut]:
    """The player's characters, each with its troupes' names and its downtime, in a few
    queries for the whole list."""
    found = characters_out(
        db,
        db.scalars(
            select(Character)
            .where(Character.player_id == user.id, Character.kind == "pc")
            .order_by(Character.name)
        ),
    )
    troupe_ids = {t for c in found for t in (c.home_troupe_id, c.asking_troupe_id) if t}
    names = {
        troupe_id: name
        for troupe_id, name in db.execute(
            select(Troupe.id, Troupe.name).where(Troupe.id.in_(troupe_ids))
        )
    }
    waiting = downtimes.waiting(db, [c.id for c in found])
    listed: list[CharacterListOut] = []
    for c in found:
        due = waiting.get(c.id, downtimes.Waiting())
        listed.append(
            CharacterListOut(
                **c.model_dump(),
                home_troupe_name=names.get(c.home_troupe_id) if c.home_troupe_id else None,
                asking_troupe_name=names.get(c.asking_troupe_id) if c.asking_troupe_id else None,
                downtime_due=due.due,
                delivered=list(due.delivered),
            )
        )
    return listed


@router.post("", status_code=status.HTTP_201_CREATED)
def create_character(body: NewCharacter, db: DbSession, user: CurrentUser) -> CharacterOut:
    """Players build characters on their own, outside any troupe: of any splat with
    no building troupe, else of a splat it takes."""
    if db.scalar(select(RuleSet.id).where(RuleSet.splat == body.splat)) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No rules for {body.splat!r}.")
    if body.domitor is not None and not SPLATS[body.splat].has_domitor:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Only a ghoul has a domitor.")
    character = Character(
        player_id=user.id,
        splat=body.splat,
        name=body.name,
        building_troupe_id=running_troupe_id(db, body.building_troupe_id, body.splat),
    )
    db.add(character)
    db.flush()
    start_character(db, user, character)
    grant_starting_traits(db, rules_for(db, character), character)
    if body.domitor is not None:
        bind(db, user, character, body.domitor)
    db.commit()
    db.refresh(character)
    return character_out(db, character)


@router.get("/{character_id}")
def read_character(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CharacterOut:
    return character_out(db, visible_character(db, user, character_id))


@router.patch("/{character_id}")
def change_character(
    character_id: uuid.UUID, body: CharacterChanges, db: DbSession, user: CurrentUser
) -> CharacterOut:
    """Rename the character: its player, at most once every three months while it is
    in a troupe, or the custodian at any time (see horatio/renames.py)."""
    character = visible_character(db, user, character_id)
    if not user.is_custodian:
        character = editable_character(db, user, character_id)
    renames.rename(db, user, lock_character(db, character.id), body.name)
    db.commit()
    return character_out(db, character)


@router.put("/{character_id}/pronouns")
def set_pronouns(
    character_id: uuid.UUID, body: PronounsIn, db: DbSession, user: CurrentUser
) -> CharacterOut:
    """Set the character's pronouns: its player, or for an NPC its troupe's staff."""
    character = editable_character(db, user, character_id)
    pronouns.set_character(db, user, character, body.pronouns)
    db.commit()
    return character_out(db, character)


def running_troupe_id(db: DbSession, troupe_id: uuid.UUID | None, splat: str) -> uuid.UUID | None:
    """The troupe to build by, if it is running and takes characters of `splat`."""
    if troupe_id is None:
        return None
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or troupe.archived_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    if splat not in troupe.allowed_splats:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{troupe.name} does not take {SPLATS[splat].label.lower() or splat} characters.",
        )
    return troupe.id


@router.put("/{character_id}/building-troupe")
def set_building_troupe(
    character_id: uuid.UUID, body: BuildingTroupe, db: DbSession, user: CurrentUser
) -> CharacterOut:
    """Build by a troupe's rules (or, with none, the plain rule set) until a home
    troupe accepts the character; then that troupe's rules apply."""
    character = editable_character(db, user, character_id)
    if character.home_troupe_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The character has a home troupe; its rules apply."
        )
    building = running_troupe_id(db, body.troupe_id, character.splat)
    ensure_house_traits_fit(db, character, building)
    character.building_troupe_id = building
    sync_fixed_ratings(db, character)
    clan_merits.resync(db, [character])
    db.commit()
    return character_out(db, character)


def bind(db: DbSession, user: User, ghoul: Character, body: DomitorIn) -> None:
    domitor = None
    if body.character_id is not None:
        try:
            domitor = visible_character(db, user, body.character_id)
        except HTTPException as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such domitor.") from error
    domitors.set_domitor(
        db,
        user,
        ghoul,
        domitor=domitor,
        name=body.name,
        clan=body.clan,
        in_clan=body.in_clan,
        disciplines=body.disciplines,
        moved=[domitors.Placed(p.name, p.rating, p.detail) for p in body.moved],
    )
    # The domitor's clan and bloodline are the ghoul's, and so are their merits.
    clan_merits.refuse_overspent(clan_merits.sync(db, ghoul))


def domitor_out(db: DbSession, ghoul: Character) -> DomitorOut | None:
    found = domitors.domitor_info(db, ghoul)
    if found is None:
        return None
    return DomitorOut(
        character_id=found.character.id if found.character is not None else None,
        name=found.name,
        clan=found.clan,
        in_clan=found.in_clan,
    )


@router.get("/{character_id}/domitor")
def read_domitor(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DomitorOut | None:
    """A ghoul's domitor; None while it has none, and for a vampire."""
    return domitor_out(db, visible_character(db, user, character_id))


def binding_ghoul(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    """The ghoul, if `user` may bind it to a domitor: its player, until a home troupe
    accepts it; after that, the home troupe's running staff."""
    ghoul = visible_character(db, user, character_id)
    if ghoul.home_troupe_id is None:
        return editable_character(db, user, character_id)
    home = db.get_one(Troupe, ghoul.home_troupe_id)
    if not allows(
        troupe_role(db, user, home), TroupeAction.APPROVE_CHANGES, is_custodian=user.is_custodian
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Once a home troupe accepts a ghoul, its staff change its domitor.",
        )
    return ghoul


@router.get("/{character_id}/domitor/choices")
def domitor_choices(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser, q: str = ""
) -> list[DomitorChoiceOut]:
    """The vampires, PCs and NPCs, that the ghoul's player can see and bind it to,
    whose names hold `q`: the first 20 by name."""
    ghoul = binding_ghoul(db, user, character_id)
    if not domitors.has_domitor(ghoul):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a ghoul has a domitor.")
    return [
        DomitorChoiceOut(
            character_id=c.character.id,
            name=c.character.name,
            kind=c.character.kind,
            clan=c.clan,
            in_clan=c.in_clan,
        )
        for c in domitors.candidates(db, user, ghoul, q)
    ]


@router.put("/{character_id}/domitor")
def change_domitor(
    character_id: uuid.UUID, body: DomitorIn, db: DbSession, user: CurrentUser
) -> DomitorOut | None:
    """Bind a ghoul to its domitor (MET: VTM pp. 296–297): its player, until a home
    troupe accepts it; after that, the home troupe's running staff, once the old bond
    has faded."""
    ghoul = binding_ghoul(db, user, character_id)
    bind(db, user, lock_character(db, ghoul.id), body)
    db.commit()
    return domitor_out(db, ghoul)


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Delete a character for good. It must be in no troupe: leaving each one first
    is what tells those troupes' storytellers."""
    character = visible_character(db, user, character_id)
    if not can_edit_character(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the character's player can delete it.")
    deletion.delete_character(db, user, lock_character(db, character.id))
    db.commit()
    root = pictures.upload_dir()
    if root is not None:
        pictures.remove(pictures.character_dir(root, character_id))


@router.post("/{character_id}/retire")
def retire_character(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser, body: Leaving | None = None
) -> CharacterOut:
    """Characters are never deleted, only retired: for a reason, which goes in the log
    with the note, and listed on its troupes' Who's Who if the player chooses. With
    no reason it is not listed."""
    character = editable_character(db, user, character_id)
    if body is None:
        leaving.retire(db, user, character, None, "", listed=False)
    else:
        leaving.retire(db, user, character, body.reason, body.note, body.listed)
    db.commit()
    return character_out(db, character)


@router.put("/{character_id}/leaving")
def change_leaving(
    character_id: uuid.UUID, body: Leaving, db: DbSession, user: CurrentUser
) -> CharacterOut:
    """Change why a retired character left, or whether its troupes' Who's Who lists
    it: its player, or its home troupe's running staff."""
    character = visible_character(db, user, character_id)
    if not can_change_leaving(db, user, character):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the character's player or its home troupe's staff can change why it left.",
        )
    if character.status != "retired":
        raise HTTPException(status.HTTP_409_CONFLICT, "This character is not retired.")
    leaving.change(db, user, character, body.reason, body.note, body.listed)
    db.commit()
    return character_out(db, character)

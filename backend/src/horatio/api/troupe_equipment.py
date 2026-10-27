"""A troupe's equipment (horatio.equipment): given to its home characters by its
storytellers and assistant storytellers, changed and taken back by them, with the
troupe's own templates; and a character's equipment, for whoever sees its sheet,
which its player or staff give to another home character or discard, and staff
restore."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import equipment
from horatio.api.downtimes import staff_troupe
from horatio.api.equipment import EquipmentFactsOut, EquipmentItemQuality, facts_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.equipment import EquipmentRefused, ItemFields, ItemQuality, SpecialEffect
from horatio.models import (
    Character,
    EquipmentEvent,
    EquipmentItem,
    EquipmentTemplate,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, can_view_character, visible_character
from horatio.rules.equipment import EquipmentRules, item_qualities

router = APIRouter(tags=["equipment"])

Status = Literal["held", "taken_back", "discarded"]
Kind = Literal["melee", "ranged", "protective", "miscellaneous"]


class SpecialEffectModel(BaseModel):
    name: str = Field(max_length=100)
    # What it does, in the troupe's words.
    effect: str = Field(max_length=1000)


class EquipmentItemQualityOut(BaseModel):
    name: str
    detail: str
    # What it does and where, from the holder's rules; None for a quality they no
    # longer have.
    effect: str | None
    # What it does at the table, in a few words: "+3 initiative".
    play: str | None
    page: str | None


class DiscardedOut(BaseModel):
    """When a discarded item was discarded, by whom, and the note they left."""

    at: datetime
    by_name: str | None
    note: str


class EquipmentItemOut(BaseModel):
    id: uuid.UUID
    # Who holds it; once taken back or discarded, who last held it.
    character_id: uuid.UUID
    character_name: str
    character_kind: str  # pc | npc
    # A PC's player.
    player_name: str | None
    name: str
    kind: str
    # The kind as the holder's rules name it: "Melee weapon".
    kind_name: str
    grade: str
    # Made special by a troupe's staff: any number of qualities, and effects of its own.
    special: bool
    special_troupe_name: str | None
    qualities: list[EquipmentItemQualityOut]
    # Its Artisan and Masterwork were added while crafting, and take no slot.
    crafted: bool
    effects: list[SpecialEffectModel]
    description: str
    # None unless the reader is staff of the holder's home troupe.
    staff_note: str | None
    facts: EquipmentFactsOut
    status: Status
    # The troupe that gave it, who gave it and when.
    troupe_id: uuid.UUID
    troupe_name: str
    given_by_name: str | None
    given_at: datetime
    # The reader can change it or take it back: staff of the holder's home troupe.
    can_change: bool
    # Set once it is discarded.
    discarded: DiscardedOut | None


class EquipmentEventOut(BaseModel):
    id: uuid.UUID
    # given | changed | taken_back, and from #282 passed | discarded | restored.
    action: str
    at: datetime
    actor_name: str | None
    # The troupe whose staff did it.
    troupe_name: str | None
    from_character_id: uuid.UUID | None
    from_name: str
    to_character_id: uuid.UUID | None
    to_name: str
    reason: str
    # A line saying what happened: "Changed: qualities now Accurate, Long Range".
    summary: str
    # For a change, each field changed: {field: {"from": ..., "to": ...}}.
    changes: dict[str, Any]


class EquipmentItemDetailOut(EquipmentItemOut):
    # Oldest first.
    history: list[EquipmentEventOut]


class EquipmentHolderOut(BaseModel):
    """A home character of the troupe, which it can give equipment to."""

    id: uuid.UUID
    name: str
    kind: str  # pc | npc
    player_name: str | None
    # Its rules check what it is given.
    splat: str


class TroupeEquipmentOut(BaseModel):
    items: list[EquipmentItemOut]
    # The troupe's active home characters, PCs and NPCs, by name.
    characters: list[EquipmentHolderOut]


class EquipmentReceiverOut(BaseModel):
    """A character the holder's items can be given to."""

    id: uuid.UUID
    name: str
    kind: str  # pc | npc
    player_name: str | None
    # The titles it holds in the home troupe, "Prince"; empty for none.
    title: str


class CharacterEquipmentOut(BaseModel):
    items: list[EquipmentItemOut]
    # Its home troupe, which gives it equipment; None if it has none.
    home_troupe_id: uuid.UUID | None
    # The reader is staff of that troupe, who give it equipment.
    can_give: bool
    # The reader gives its items to another character, or discards them: its player
    # or its home troupe's staff.
    can_pass: bool
    # Who they can go to, if the reader can pass them: the home troupe's PCs and the
    # NPCs holding a title there, or for staff every home character. Kept on the
    # phone with the items, so a give works at a game with no signal.
    receivers: list[EquipmentReceiverOut]


class EquipmentFieldsIn(BaseModel):
    name: str = Field(max_length=200)
    kind: Kind
    grade: Literal["cheap", "standard", "special"]
    qualities: list[EquipmentItemQuality] = Field(
        default_factory=list[EquipmentItemQuality], max_length=30
    )
    crafted: bool = False
    # Only a special item has them.
    effects: list[SpecialEffectModel] = Field(
        default_factory=list[SpecialEffectModel], max_length=20
    )
    description: str = Field(default="", max_length=4000)


class EquipmentItemFieldsIn(EquipmentFieldsIn):
    staff_note: str = Field(default="", max_length=4000)


class GiveEquipmentIn(EquipmentItemFieldsIn):
    character_id: uuid.UUID
    # The template it was started from, for its history.
    template: str | None = Field(default=None, max_length=200)


class ChangeEquipmentIn(EquipmentItemFieldsIn):
    # Told to the holder's player; needed unless only the staff note changes.
    reason: str = Field(default="", max_length=1000)


class TakeBackEquipmentIn(BaseModel):
    reason: str = Field(max_length=1000)


class GiveToIn(BaseModel):
    to_character_id: uuid.UUID
    # Why, if anyone likes: "lost at cards".
    note: str = Field(default="", max_length=300)


class DiscardIn(BaseModel):
    # Where it went, if anyone likes: "lost in the river", "sold".
    note: str = Field(default="", max_length=300)


class EquipmentTemplateIn(EquipmentFieldsIn):
    # The splat whose rules check it: those of the character it was built for.
    splat: str = "vampire"


class TroupeTemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    grade: str
    qualities: list[EquipmentItemQuality]
    crafted: bool
    effects: list[SpecialEffectModel]
    description: str


# --- helpers ----------------------------------------------------------------------------


def fields_in(body: EquipmentFieldsIn) -> ItemFields:
    return ItemFields(
        name=body.name,
        kind=body.kind,
        grade=body.grade,
        qualities=tuple(ItemQuality(q.name, q.detail) for q in body.qualities),
        crafted=body.crafted,
        effects=tuple(SpecialEffect(e.name, e.effect) for e in body.effects),
        description=body.description,
        staff_note=body.staff_note if isinstance(body, EquipmentItemFieldsIn) else "",
    )


def refusal(error: EquipmentRefused) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


class Reader:
    """What the reader may see and do, asked once per troupe and rules once per
    splat, for a list. With no reader (a printed sheet), no staff note and no
    changes."""

    def __init__(self, db: Session, user: User | None) -> None:
        self.db = db
        self.user = user
        self.troupes: dict[uuid.UUID, Troupe] = {}
        self.managing: dict[uuid.UUID, bool] = {}
        self.rules: dict[tuple[str, uuid.UUID | None], EquipmentRules] = {}
        self.names: dict[uuid.UUID, str] = {}

    def troupe(self, troupe_id: uuid.UUID) -> Troupe:
        if troupe_id not in self.troupes:
            self.troupes[troupe_id] = self.db.get_one(Troupe, troupe_id)
        return self.troupes[troupe_id]

    def manages(self, character: Character) -> bool:
        if self.user is None:
            return False
        home = equipment.home_of(character)
        if home is None:
            return self.user.is_custodian
        if home not in self.managing:
            self.managing[home] = equipment.can_manage(self.db, self.user, self.troupe(home))
        return self.managing[home]

    def rules_for(self, character: Character) -> EquipmentRules:
        key = (character.splat, equipment.home_of(character))
        if key not in self.rules:
            self.rules[key] = equipment.equipment_rules(self.db, *key)
        return self.rules[key]

    def user_name(self, user_id: uuid.UUID | None) -> str | None:
        if user_id is None:
            return None
        if user_id not in self.names:
            found = self.db.get(User, user_id)
            self.names[user_id] = found.display_name if found else ""
        return self.names[user_id] or None

    def player_name(self, character: Character) -> str | None:
        return self.user_name(character.player_id) if character.kind == "pc" else None

    def item(self, item: EquipmentItem, character: Character) -> EquipmentItemOut:
        rules = self.rules_for(character)
        qualities = item_qualities(item.qualities)
        found = equipment.assess(rules, item.kind, qualities, item.grade, crafted=item.crafted)
        manages = self.manages(character)
        return EquipmentItemOut(
            id=item.id,
            character_id=character.id,
            character_name=character.name,
            character_kind=character.kind,
            player_name=self.player_name(character),
            name=item.name,
            kind=item.kind,
            kind_name=kind.name if (kind := rules.kinds.get(item.kind)) else item.kind,
            grade=item.grade,
            special=item.grade == "special",
            special_troupe_name=(
                self.troupe(item.special_troupe_id).name if item.special_troupe_id else None
            ),
            qualities=[
                EquipmentItemQualityOut(
                    name=q.name,
                    detail=q.detail,
                    effect=quality.effect if quality else None,
                    play=quality.play if quality else None,
                    page=quality.page if quality else None,
                )
                for q in qualities
                for quality in [rules.qualities.get((item.kind, q.name))]
            ],
            crafted=item.crafted,
            effects=[SpecialEffectModel(**e) for e in item.effects],
            description=item.description,
            staff_note=item.staff_note if manages else None,
            facts=facts_out(found.facts),
            status=item.status,  # type: ignore[arg-type]  # checked by the database
            troupe_id=item.troupe_id,
            troupe_name=self.troupe(item.troupe_id).name,
            given_by_name=self.user_name(item.given_by),
            given_at=item.given_at,
            can_change=manages and item.status == "held",
            discarded=self.discarded(item) if item.status == "discarded" else None,
        )

    def discarded(self, item: EquipmentItem) -> DiscardedOut | None:
        event = self.db.scalar(
            select(EquipmentEvent)
            .where(EquipmentEvent.item_id == item.id, EquipmentEvent.action == "discarded")
            .order_by(EquipmentEvent.created_at.desc(), EquipmentEvent.id.desc())
            .limit(1)
        )
        if event is None:
            return None
        return DiscardedOut(
            at=event.created_at, by_name=self.user_name(event.actor_id), note=event.reason
        )

    def detail(self, item: EquipmentItem, character: Character) -> EquipmentItemDetailOut:
        rules = self.rules_for(character)
        history = [
            EquipmentEventOut(
                id=e.id,
                action=e.action,
                at=e.created_at,
                actor_name=self.user_name(e.actor_id),
                troupe_name=self.troupe(e.troupe_id).name if e.troupe_id else None,
                from_character_id=e.from_character_id,
                from_name=e.from_name,
                to_character_id=e.to_character_id,
                to_name=e.to_name,
                reason=e.reason,
                summary=equipment.event_summary(
                    rules, e, self.troupe(e.troupe_id).name if e.troupe_id else None
                ),
                changes=e.changes,
            )
            for e in equipment.history(self.db, item)
        ]
        return EquipmentItemDetailOut(**self.item(item, character).model_dump(), history=history)


def troupe_item(db: DbSession, user: User, troupe: Troupe, item_id: uuid.UUID) -> EquipmentItem:
    """The item, held by a character the reader can see, or 404. One held by a
    character of another home troupe is refused by horatio.equipment."""
    item = db.get(EquipmentItem, item_id)
    if item is None or not can_view_character(db, user, db.get_one(Character, item.character_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item.")
    equipment.require_home(troupe, db.get_one(Character, item.character_id))
    return item


def template_out(t: EquipmentTemplate) -> TroupeTemplateOut:
    return TroupeTemplateOut(
        id=t.id,
        name=t.name,
        kind=t.kind,
        grade=t.grade,
        qualities=[
            EquipmentItemQuality(name=q.name, detail=q.detail) for q in item_qualities(t.qualities)
        ],
        crafted=t.crafted,
        effects=[SpecialEffectModel(**e) for e in t.effects],
        description=t.description,
    )


# --- the troupe's Equipment tab -----------------------------------------------------------


@router.get("/troupes/{troupe_id}/equipment")
def troupe_equipment(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    character_id: uuid.UUID | None = None,
    kind: Kind | None = None,
    status: Annotated[list[Status] | None, Query()] = None,
) -> TroupeEquipmentOut:
    """Every item the troupe's home characters hold, whichever troupe gave it, by
    holder: of one character, or one kind, if asked. `status` asks for those taken
    back (or discarded) as well or instead."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_EQUIPMENT)
    reader = Reader(db, user)
    found = equipment.troupe_items(
        db, troupe.id, character_id=character_id, kind=kind, statuses=status or ["held"]
    )
    return TroupeEquipmentOut(
        items=[reader.item(item, character) for item, character in found],
        characters=[
            EquipmentHolderOut(
                id=c.id,
                name=c.name,
                kind=c.kind,
                player_name=reader.player_name(c),
                splat=c.splat,
            )
            for c in equipment.home_characters(db, troupe.id)
        ],
    )


@router.post("/troupes/{troupe_id}/equipment", status_code=status.HTTP_201_CREATED)
def give_equipment(
    troupe_id: uuid.UUID, body: GiveEquipmentIn, db: DbSession, user: CurrentUser
) -> EquipmentItemOut:
    """Give one of the troupe's home characters an item. One for a character whose
    home is elsewhere, or that breaks the rules between qualities, is refused with
    the reason."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_EQUIPMENT)
    character = visible_character(db, user, body.character_id)
    try:
        item = equipment.give(db, user, troupe, character, fields_in(body), template=body.template)
    except EquipmentRefused as error:
        raise refusal(error) from None
    db.commit()
    return Reader(db, user).item(item, character)


@router.get("/troupes/{troupe_id}/equipment/templates")
def troupe_templates(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[TroupeTemplateOut]:
    """The troupe's own templates. The book's are with the rules (GET
    /rules/{splat}/equipment)."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_EQUIPMENT)
    return [template_out(t) for t in equipment.troupe_templates(db, troupe.id)]


@router.post("/troupes/{troupe_id}/equipment/templates", status_code=status.HTTP_201_CREATED)
def save_template(
    troupe_id: uuid.UUID, body: EquipmentTemplateIn, db: DbSession, user: CurrentUser
) -> TroupeTemplateOut:
    """Keep an item as one of the troupe's templates, checked as any item is."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_EQUIPMENT)
    try:
        template = equipment.save_template(db, user, troupe, body.splat, fields_in(body))
    except EquipmentRefused as error:
        raise refusal(error) from None
    db.commit()
    return template_out(template)


@router.delete(
    "/troupes/{troupe_id}/equipment/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_template(
    troupe_id: uuid.UUID, template_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> None:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_EQUIPMENT)
    template = db.get(EquipmentTemplate, template_id)
    if template is None or template.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such template.")
    equipment.delete_template(db, user, troupe, template)
    db.commit()


@router.get("/troupes/{troupe_id}/equipment/{item_id}")
def equipment_item(
    troupe_id: uuid.UUID, item_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> EquipmentItemDetailOut:
    """An item, with its history: where it came from and every change since."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_EQUIPMENT)
    item = troupe_item(db, user, troupe, item_id)
    return Reader(db, user).detail(item, db.get_one(Character, item.character_id))


@router.put("/troupes/{troupe_id}/equipment/{item_id}")
def change_equipment(
    troupe_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ChangeEquipmentIn,
    db: DbSession,
    user: CurrentUser,
) -> EquipmentItemDetailOut:
    """Change an item, with a reason its holder's player is told."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_EQUIPMENT)
    item = troupe_item(db, user, troupe, item_id)
    try:
        equipment.change(db, user, troupe, item, fields_in(body), body.reason)
    except EquipmentRefused as error:
        raise refusal(error) from None
    db.commit()
    return Reader(db, user).detail(item, db.get_one(Character, item.character_id))


@router.post("/troupes/{troupe_id}/equipment/{item_id}/restore")
def restore_equipment(
    troupe_id: uuid.UUID, item_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> EquipmentItemDetailOut:
    """Give a discarded item back to the character that discarded it, if that was a
    mistake. Its player is told."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_EQUIPMENT)
    item = troupe_item(db, user, troupe, item_id)
    equipment.restore(db, user, troupe, item)
    db.commit()
    return Reader(db, user).detail(item, db.get_one(Character, item.character_id))


@router.post("/troupes/{troupe_id}/equipment/{item_id}/take-back")
def take_back(
    troupe_id: uuid.UUID,
    item_id: uuid.UUID,
    body: TakeBackEquipmentIn,
    db: DbSession,
    user: CurrentUser,
) -> EquipmentItemDetailOut:
    """Take an item away from its holder, with a reason its player is told."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_EQUIPMENT)
    item = troupe_item(db, user, troupe, item_id)
    equipment.take_back(db, user, troupe, item, body.reason)
    db.commit()
    return Reader(db, user).detail(item, db.get_one(Character, item.character_id))


# --- a character's equipment --------------------------------------------------------------


@router.get("/characters/{character_id}/equipment")
def character_equipment(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> CharacterEquipmentOut:
    """What the character holds, for whoever sees its sheet; the staff note only for
    its home troupe's staff."""
    character = visible_character(db, user, character_id)
    reader = Reader(db, user)
    home = equipment.home_of(character)
    manages = home is not None and reader.manages(character)
    can_pass = (
        character.status == "active"
        and home is not None
        and reader.troupe(home).archived_at is None
        and (manages or equipment.is_player(user, character))
    )
    return CharacterEquipmentOut(
        items=[reader.item(item, character) for item in equipment.items_of(db, character)],
        home_troupe_id=home,
        can_give=manages,
        can_pass=can_pass,
        receivers=[
            EquipmentReceiverOut(
                id=r.character.id,
                name=r.character.name,
                kind=r.character.kind,
                player_name=reader.player_name(r.character),
                title=r.title,
            )
            for r in equipment.receivers(db, character, staff=manages)
        ]
        if can_pass
        else [],
    )


def holder_item(
    db: DbSession, user: User, character_id: uuid.UUID, item_id: uuid.UUID
) -> EquipmentItem:
    """The character's item, or 404."""
    character = visible_character(db, user, character_id)
    item = db.get(EquipmentItem, item_id)
    if item is None or item.character_id != character.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item.")
    return item


@router.post("/characters/{character_id}/equipment/{item_id}/give")
def give_to(
    character_id: uuid.UUID, item_id: uuid.UUID, body: GiveToIn, db: DbSession, user: CurrentUser
) -> EquipmentItemOut:
    """Give the item to another character of the holder's home troupe, at once: by
    the holder's player, to the troupe's PCs and the NPCs holding a title there, or
    by its staff, to any home character. One for a character of another home troupe
    is refused."""
    item = holder_item(db, user, character_id, item_id)
    equipment.give_to(db, user, item, body.to_character_id, body.note)
    db.commit()
    return Reader(db, user).item(item, db.get_one(Character, item.character_id))


@router.post("/characters/{character_id}/equipment/{item_id}/discard")
def discard(
    character_id: uuid.UUID, item_id: uuid.UUID, body: DiscardIn, db: DbSession, user: CurrentUser
) -> EquipmentItemOut:
    """Discard the item, by the holder's player or its home troupe's staff. It is
    kept, with its history, for staff to restore."""
    item = holder_item(db, user, character_id, item_id)
    equipment.discard(db, user, item, body.note)
    db.commit()
    return Reader(db, user).item(item, db.get_one(Character, item.character_id))

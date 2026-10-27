"""What a printed character sheet shows: the sheet as it stands, with any discipline
dots still waiting on the home troupe marked."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import (
    diablerie,
    domitors,
    equipment,
    house_traits,
    pictures,
    play,
    reference,
    retainers,
    sect_status,
    sheets,
    titles,
)
from horatio.api.retainers import IdentityOut, RetainerOut, identities_out, listed
from horatio.api.troupe_equipment import EquipmentItemOut, Reader
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, SheetVersion, TraitCategory, TraitDefinition, Troupe, User
from horatio.permissions import visible_character
from horatio.pool_modifiers import ModifierOut, modifiers_out
from horatio.rules.store import read_troupe_rules

router = APIRouter(prefix="/characters/{character_id}", tags=["printing"])


class PrintedTrait(BaseModel):
    category: str
    category_name: str
    group: str
    name: str
    detail: str
    rating: int | None
    # For a skill: Physical, Social or Mental.
    attribute: str | None
    # Dots waiting on the home troupe: the rating they were bought from.
    pending_from: int | None
    # For a specialisation: the skill or background it belongs to, as its
    # category and name (from the rule set's `specializes`).
    specializes: dict[str, str] | None
    # A troupe's own merit or flaw: "House merit of Night Court", printed with a ★.
    house: str | None = None


class PrintedBlood(BaseModel):
    """The Blood boxes to print: `most` that can be spent, `per_turn` a turn. A
    ghoul's are its vitae, and the rest of its `pool` is human Blood, which cannot
    be spent (MET: VtM core p. 297); `pool` is None for a vampire's."""

    most: int
    per_turn: int
    pool: int | None = None


class PrintedSheet(BaseModel):
    character_name: str
    player_name: str
    splat: str
    troupe_name: str | None
    # That troupe's portrait (horatio.pictures), small beside its name, or None.
    troupe_portrait: str | None
    # Titles held in that troupe.
    titles: list[str]
    # The character's picture (horatio.pictures), small in the header, or None.
    picture: str | None
    kind: str  # pc | npc
    # Whether `troupe_name` is the home troupe, and when and by whom it accepted the character.
    home: bool
    accepted_at: datetime | None
    accepted_by: str | None
    # When the character committed diablerie (p. 306 asks for the date on the sheet).
    diablerie: list[date]
    blood: PrintedBlood
    # A ghoul's domitor, by name; None for a vampire.
    domitor: str | None = None
    traits: list[PrintedTrait]
    # Its sect status as it carries it into a game in that troupe (horatio.sect_status);
    # with no troupe, what it holds and its merits give.
    status: list[str] = []
    # Its Retainers, listed under the background.
    retainers: list[RetainerOut]
    # Each Alternate Identity, with what its rating means.
    identities: list[IdentityOut] = []
    # The test pools worked out from the sheet, and the player's modifiers that are on.
    pools: list[reference.TestPool]
    modifiers: list[ModifierOut]
    # What it holds (horatio.equipment), with no staff note, and the items equipped
    # now, whose modifiers count as the player's own do.
    equipment: list[EquipmentItemOut] = []
    equipped: list[uuid.UUID] = []


@router.get("/print")
def printed_sheet(
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    troupe_id: uuid.UUID | None = None,
) -> PrintedSheet:
    """The sheet as it stands, headed for `troupe_id` (by default the home troupe, else
    the first troupe joined), whose titles it shows."""
    return print_sheet(db, visible_character(db, user, character_id), troupe_id)


def printed_status(db: Session, character: Character, troupe_id: uuid.UUID | None) -> list[str]:
    if troupe_id is not None:
        return [c.name for c in sect_status.carried(db, character, troupe_id)]
    found = sect_status.standing(db, character)
    return [d.name for d in found.derived if d.kind == "merit"] + [h.name for h in found.held]


def print_sheet(db: Session, character: Character, troupe_id: uuid.UUID | None) -> PrintedSheet:
    """`character`'s printed sheet, headed for `troupe_id` if it belongs there."""
    joined = [m.troupe_id for m in sheets.memberships(db, character)]
    troupe = next((t for t in (troupe_id, character.home_troupe_id, *joined) if t in joined), None)
    found = (
        sheets.membership(db, character, character.home_troupe_id)
        if character.home_troupe_id
        else None
    )
    version = (
        db.get(SheetVersion, found.approved_version_id)
        if found is not None and found.approved_version_id is not None
        else None
    )
    rows = sheets.sheet_rows(db, character)
    snapshot = [r.snapshot() for r in rows]
    found_marks = house_traits.marks(db, [r.definition.id for r in rows if r.definition.troupe_id])
    house = {
        (r.category.key, r.definition.name): found_marks[r.definition.id].label
        for r in rows
        if r.definition.id in found_marks
    }
    held = {
        (name, d.detail): d.from_rating
        for (_, d), name in (
            (pair, db.get_one(TraitDefinition, pair[1].trait_definition_id).name)
            for pair in sheets.pending_disciplines(db, character)
        )
    }

    heading = db.get_one(Troupe, troupe) if troupe else None
    rule_set = read_troupe_rules(db, character.splat, troupe).rule_set
    categories = list(
        db.execute(
            select(TraitCategory.key, TraitCategory.position).order_by(TraitCategory.position)
        )
    )
    order = {key: position for key, position in categories}
    names = {
        (key, name): props
        for key, name, props in db.execute(
            select(TraitCategory.key, TraitDefinition.name, TraitDefinition.properties)
            .join(TraitDefinition, TraitDefinition.category_id == TraitCategory.id)
            .where(TraitDefinition.troupe_id.is_(None))
        )
    }
    traits = [
        PrintedTrait(
            category=t["category"],
            category_name=rule_set.categories[t["category"]].name,
            group=rule_set.categories[t["category"]].group,
            name=t["name"],
            detail=t["detail"],
            rating=t["rating"],
            attribute=names.get((t["category"], t["name"]), {}).get("attribute"),
            pending_from=held.get((t["name"], t["detail"]))
            if t["category"] == "disciplines"
            else None,
            specializes=dict(rule_set.categories[t["category"]].specializes or {}) or None,
            house=house.get((t["category"], t["name"])),
        )
        for t in sorted(snapshot, key=lambda t: (order.get(t["category"], 999), t["name"]))
        if t["category"] in rule_set.categories
    ]
    limits = play.limits(db, character)
    # No reader: a printed sheet shows no staff note.
    reader = Reader(db, None)
    domitor = domitors.domitor_info(db, character) if domitors.has_domitor(character) else None
    return PrintedSheet(
        character_name=character.name,
        player_name=(
            db.get_one(User, character.player_id).display_name if character.kind == "pc" else "NPC"
        ),
        splat=character.splat,
        troupe_name=heading.name if heading else None,
        troupe_portrait=pictures.troupe_portrait_url(heading.id, heading.portrait_id)
        if heading
        else None,
        titles=titles.held(db, troupe, character.id) if troupe else [],
        kind=character.kind,
        home=troupe is not None and troupe == character.home_troupe_id,
        accepted_at=version.approved_at if version else None,
        accepted_by=db.get_one(User, version.approved_by).display_name if version else None,
        diablerie=[d.committed_on for d in diablerie.recorded(db, character)],
        blood=PrintedBlood(
            most=limits.blood,
            per_turn=limits.blood_per_turn,
            pool=limits.vitae.pool if limits.vitae else None,
        ),
        domitor=domitor.name if domitor else None,
        traits=traits,
        status=printed_status(db, character, troupe),
        retainers=listed(db, retainers.read(db, character), None),
        identities=identities_out(db, character),
        pools=reference.reference(
            sheets.sheet_rows(db, character),
            sheets.rules_for(db, character).rule_set,
            limits.blood_per_turn,
        ).pools,
        modifiers=modifiers_out(db, character, only_on=True),
        equipment=[reader.item(item, character) for item in equipment.items_of(db, character)],
        equipped=[uuid.UUID(key) for key, _ in limits.equipped],
        picture=pictures.picture_url(character.id, character.picture_id),
    )

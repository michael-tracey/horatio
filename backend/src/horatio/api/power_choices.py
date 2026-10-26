"""What a player chooses when buying a power (issue #200), such as Shape of the
Beast's flight and fight animals and its fight form's template (MET: VtM core,
p. 155). The choices are kept on the discipline's trait and are fixed once made,
as the book says, though the player may still change them while the character
has no home troupe, and staff who see the sheet can change them at any time. The
Play View's forms use them (horatio.reference)."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from horatio import audit, reference, sheets
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, User
from horatio.permissions import can_edit_character, is_staff_for, visible_character

router = APIRouter(prefix="/characters/{character_id}", tags=["sheets"])


class ChoiceOut(BaseModel):
    key: str
    label: str
    # What it is until chosen: "wolf"; "" for none.
    default: str
    # The choices there are, for one with a list; empty for a free choice.
    options: list[str]
    # What was chosen; "" if nothing yet.
    value: str


class PowerChoicesOut(BaseModel):
    discipline: str
    power: str
    level: int
    choices: list[ChoiceOut]
    # Something has been chosen, so it is fixed for the player.
    chosen: bool
    # The person asking may choose, or change what was chosen, now.
    can_change: bool


class PowerChoicesIn(BaseModel):
    discipline: str = Field(max_length=80)
    power: str = Field(max_length=80)
    # By the choice's key; those left out stay as they are, and "" clears one.
    values: dict[str, str]


def may_change(db: Session, user: User, character: Character, chosen: bool) -> bool:
    """Staff who see the sheet may always; the player may until something is
    chosen, or while the character has no home troupe and is edited freely."""
    if is_staff_for(db, user, character):
        return True
    if not can_edit_character(db, user, character):
        return False
    return not chosen or character.kind != "pc" or character.home_troupe_id is None


def choices_out(db: Session, user: User, character: Character) -> list[PowerChoicesOut]:
    """Each power the character has reached that asks for a choice when bought."""
    book = reference.catalogue()
    found: list[PowerChoicesOut] = []
    for row in sheets.sheet_rows(db, character):
        if row.category.key != "disciplines" or not row.trait.rating:
            continue
        name = row.definition.name
        for power in book.powers.get(name, []):
            if power["level"] > row.trait.rating or not power.get("choices"):
                continue
            made = row.trait.power_choices.get(power["name"], {})
            chosen = any(made.values())
            found.append(
                PowerChoicesOut(
                    discipline=name,
                    power=power["name"],
                    level=power["level"],
                    choices=[
                        ChoiceOut(
                            key=c["key"],
                            label=c["label"],
                            default=c.get("default", ""),
                            options=list(c.get("options", [])),
                            value=made.get(c["key"], ""),
                        )
                        for c in power["choices"]
                    ],
                    chosen=chosen,
                    can_change=may_change(db, user, character, chosen),
                )
            )
    return found


@router.get("/power-choices")
def read_power_choices(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[PowerChoicesOut]:
    character = visible_character(db, user, character_id)
    return choices_out(db, user, character)


def checked(power: dict[str, Any] | Any, values: dict[str, str]) -> dict[str, str]:
    """The values, trimmed, each a choice the power has and one of its options
    ("" for none)."""
    specs = {c["key"]: c for c in power.get("choices", [])}
    kept: dict[str, str] = {}
    for key, value in values.items():
        spec = specs.get(key)
        value = value.strip()
        if spec is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No choice {key}.")
        if value and spec.get("options") and value not in spec["options"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{spec['label']} is one of {', '.join(spec['options'])}.",
            )
        if len(value) > 40:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"{spec['label']} is too long."
            )
        kept[key] = value
    return kept


@router.put("/power-choices")
def set_power_choices(
    character_id: uuid.UUID, body: PowerChoicesIn, db: DbSession, user: CurrentUser
) -> list[PowerChoicesOut]:
    """Choose, or for staff change, what a power was bought with."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    power = reference.catalogue().power(body.discipline, body.power)
    row = next(
        (
            r
            for r in sheets.sheet_rows(db, character)
            if r.category.key == "disciplines" and r.definition.name == body.discipline
        ),
        None,
    )
    if power is None or not power.get("choices") or row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such power on this sheet.")
    if (row.trait.rating or 0) < power["level"]:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.power} needs more dots first.")
    before = row.trait.power_choices.get(body.power, {})
    if not may_change(db, user, character, any(before.values())):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"{body.power} is fixed once chosen; your storytellers can change it.",
        )
    merged = {**before, **checked(power, body.values)}
    values = {k: v for k, v in merged.items() if v}
    # A new dict, so the change to the JSON column is seen.
    row.trait.power_choices = {**row.trait.power_choices, body.power: values}
    audit.record(
        db,
        user,
        "sheet.power_choices",
        character_id=character.id,
        power=body.power,
        before=before,
        after=values,
    )
    db.commit()
    return choices_out(db, user, character)

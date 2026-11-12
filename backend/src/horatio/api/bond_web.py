"""The troupe's blood bonds as a web (#708), for the staff who run them: everyone on
either side of a bond, with their clan, whether they are still in play and the titles
they hold here, and every bond between them. Exactly who may open the Bonds screen
may see it, and only while the troupe tracks bonds; players never do."""

import uuid
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import bonds, social_age, title_history
from horatio.api.bonds import bonds_troupe
from horatio.api.court import ClanCountOut
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import BloodBond, Character, CharacterTitle

router = APIRouter(tags=["bonds"])


class WebPersonOut(BaseModel):
    # The character's id, or "name:" and the name in lower case for a name only, so
    # a name used on several bonds is one person.
    key: str
    character_id: uuid.UUID | None
    name: str
    # pc | npc, or None for a name only.
    kind: str | None
    clan: str | None
    # active, or how they left play: final_death | off_field | inactive | retired
    # (retired before reasons were kept). A name only counts as active.
    standing: str
    # The titles they hold in this troupe.
    titles: list[str]


class WebBondOut(BaseModel):
    id: uuid.UUID
    # Keys into the people.
    thrall: str
    regnant: str
    # 1 to 3, from its log.
    level: int
    # active | fading | ended | broken
    status: str
    # A fading bond's last day.
    fades_on: date | None


class BondWebOut(BaseModel):
    people: list[WebPersonOut]
    bonds: list[WebBondOut]
    # The troupe's characters now, by clan: what fixes each clan's colour, as on the
    # troupe's other charts.
    clans: list[ClanCountOut]


def key_of(character_id: uuid.UUID | None, name: str) -> str:
    return str(character_id) if character_id else f"name:{name.strip().lower()}"


def standing_of(character: Character) -> str:
    if character.status != "retired":
        return "active"
    return character.left_reason or "retired"


def held_titles(
    db: Session, troupe_id: uuid.UUID, ids: set[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    held: dict[uuid.UUID, list[str]] = {}
    if not ids:
        return held
    for t in db.scalars(
        select(CharacterTitle)
        .where(CharacterTitle.troupe_id == troupe_id, CharacterTitle.character_id.in_(ids))
        .order_by(CharacterTitle.name)
    ):
        held.setdefault(t.character_id, []).append(t.name)
    return held


@router.get("/troupes/{troupe_id}/bond-web")
def bond_web(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BondWebOut:
    """Every bond the troupe keeps, and the people on either side, for its running staff."""
    troupe = bonds_troupe(db, user, troupe_id)
    db.commit()
    # Oldest first, for a steady order.
    kept = list(
        db.scalars(
            select(BloodBond)
            .where(BloodBond.troupe_id == troupe.id)
            .order_by(BloodBond.created_at, BloodBond.id)
        )
    )
    ids = {i for b in kept for i in (b.thrall_id, b.regnant_id) if i}
    characters = (
        {c.id: c for c in db.scalars(select(Character).where(Character.id.in_(ids)))} if ids else {}
    )
    members = title_history.members(db, troupe)
    standing = social_age.standings(db, list(ids | set(members))) if ids or members else {}
    titles = held_titles(db, troupe.id, ids)

    def clan(character_id: uuid.UUID | None) -> str | None:
        found = standing.get(character_id) if character_id else None
        return found.clan if found else None

    people: dict[str, WebPersonOut] = {}

    def person(character_id: uuid.UUID | None, name: str) -> str:
        character = characters.get(character_id) if character_id else None
        key = key_of(character.id if character else None, name)
        if key not in people:
            people[key] = (
                WebPersonOut(
                    key=key,
                    character_id=character.id,
                    name=character.name,
                    kind=character.kind,
                    clan=clan(character.id),
                    standing=standing_of(character),
                    titles=titles.get(character.id, []),
                )
                if character
                else WebPersonOut(
                    key=key,
                    character_id=None,
                    name=name,
                    kind=None,
                    clan=None,
                    standing="active",
                    titles=[],
                )
            )
        elif character is None:
            # A name written in more than one way shows as the first of them in plain
            # alphabetical order, capitals first: "Old Marguerite" over "old marguerite".
            people[key].name = min(people[key].name, name)
        return key

    found = [
        WebBondOut(
            id=b.id,
            thrall=person(b.thrall_id, b.thrall_name),
            regnant=person(b.regnant_id, b.regnant_name),
            level=bonds.level(db, b),
            status=b.status,
            fades_on=b.fades_on,
        )
        for b in kept
    ]
    counts: dict[str | None, int] = {}
    for character_id in members:
        counts[clan(character_id)] = counts.get(clan(character_id), 0) + 1
    return BondWebOut(
        people=sorted(people.values(), key=lambda p: p.name.casefold()),
        bonds=found,
        clans=[ClanCountOut(clan=c, count=n) for c, n in counts.items()],
    )

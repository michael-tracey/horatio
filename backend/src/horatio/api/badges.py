"""Game badges for a troupe's staff to print (horatio.badges): characters', from the
roster or one character's page, and the storytellers' own."""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import badges, sheets
from horatio.api.downtimes import staff_troupe
from horatio.api.roster import roster
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe, TroupeStaff, User
from horatio.permissions import TroupeAction, is_staff_for, visible_character

router = APIRouter(tags=["badges"])

ROLE_NAMES = {
    "lead_storyteller": "Lead Storyteller",
    "storyteller": "Storyteller",
    "assistant_storyteller": "Assistant Storyteller",
    "narrator": "Narrator",
}


class BadgeOut(BaseModel):
    character_id: uuid.UUID
    name: str
    clan: str | None
    # Neonate, Ancilla or Elder.
    social_age: str
    titles: list[str]
    status: list[str]
    # What others can see or sense, from the rules data and the staff's note.
    visible: list[str]
    # Where the picture is (horatio.pictures; "/portrait.jpg" prints), or None.
    picture: str | None
    # Where the clan's logo is (add "/600.webp"), or None: the custodian's upload,
    # or the clan's Dark Pack symbol.
    logo: str | None
    # The same in white, for a dark badge, where there is one.
    logo_white: str | None


class BadgesOut(BaseModel):
    troupe_name: str | None
    badges: list[BadgeOut]


class StaffBadgeOut(BaseModel):
    name: str
    role: str


class StaffBadgesOut(BaseModel):
    # Printed small at the foot of every badge.
    troupe_name: str
    staff: list[StaffBadgeOut]


class VisibleNote(BaseModel):
    # One thing per line, as it is to read on the badge.
    note: str = Field(max_length=500)


def badges_out(db: DbSession, troupe: Troupe | None, characters: list[Character]) -> BadgesOut:
    found = badges.badges(db, troupe.id if troupe else None, characters)
    return BadgesOut(
        troupe_name=troupe.name if troupe else None,
        badges=[BadgeOut(**vars(b)) for b in found],
    )


@router.get("/troupes/{troupe_id}/badges")
def troupe_badges(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    characters: Annotated[list[uuid.UUID] | None, Query()] = None,
) -> BadgesOut:
    """Badges for the characters named, in that order, or every character in the
    troupe now, in the roster's order."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    members = [e.character_id for e in roster(troupe_id, db, user)]
    wanted = characters or members
    if not set(wanted) <= set(members):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Not all of those characters are in this troupe."
        )
    return badges_out(db, troupe, [db.get_one(Character, c) for c in wanted])


@router.get("/characters/{character_id}/badge")
def character_badge(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser, troupe_id: uuid.UUID | None = None
) -> BadgesOut:
    """One character's badge, with its titles in `troupe_id` (by default its home
    troupe, else the first troupe it joined)."""
    character = visible_character(db, user, character_id)
    joined = [m.troupe_id for m in sheets.memberships(db, character)]
    chosen = next((t for t in (troupe_id, character.home_troupe_id, *joined) if t in joined), None)
    return badges_out(db, db.get(Troupe, chosen) if chosen else None, [character])


@router.get("/troupes/{troupe_id}/staff-badges")
def staff_badges(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> StaffBadgesOut:
    """Badges for the troupe's staff: each person's name and role, lead first."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    lead = db.get_one(User, troupe.lead_user_id)
    order = list(ROLE_NAMES)
    staff = sorted(
        db.execute(
            select(User.display_name, TroupeStaff.role)
            .join(TroupeStaff, TroupeStaff.user_id == User.id)
            .where(TroupeStaff.troupe_id == troupe_id)
        ),
        key=lambda s: (order.index(s[1]), s[0].lower()),
    )
    return StaffBadgesOut(
        troupe_name=troupe.name,
        staff=[StaffBadgeOut(name=lead.display_name, role=ROLE_NAMES["lead_storyteller"])]
        + [StaffBadgeOut(name=name, role=ROLE_NAMES[role]) for name, role in staff],
    )


@router.get("/characters/{character_id}/visible-note")
def read_visible_note(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> VisibleNote:
    return VisibleNote(note=visible_character(db, user, character_id).visible_note)


@router.put("/characters/{character_id}/visible-note")
def set_visible_note(
    character_id: uuid.UUID, body: VisibleNote, db: DbSession, user: CurrentUser
) -> VisibleNote:
    """What others can see or sense about the character that the rules data does
    not cover, for its badge. Written by staff, not the player."""
    character = visible_character(db, user, character_id)
    if not is_staff_for(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only staff can write the badge note.")
    note = "\n".join(line.strip() for line in body.note.strip().splitlines() if line.strip())
    if note != character.visible_note:
        character.visible_note = note
        record(
            db,
            user,
            "character.visible_note",
            troupe_id=character.home_troupe_id or character.owner_troupe_id,
            character_id=character.id,
            note=note,
        )
    db.commit()
    return VisibleNote(note=note)

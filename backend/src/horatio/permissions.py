"""Who may do what. Every route asks here; nothing checks roles ad hoc (ADR 0002).

Roles come from CONTEXT.md:

- the custodian runs the whole system, above every troupe;
- a troupe's lead storyteller is a storyteller who can also rename, describe
  and archive it;
- storytellers and the lead are the only ones who manage staff and house rules;
- assistant storytellers can do everything else a storyteller can;
- narrators can do whatever a player in the troupe can, and answer downtime
  actions assigned to them or to any narrator, but never see character sheets;
- players see only their own characters' sheets.

`TROUPE_POLICY` is the whole of that as data, so it can be read and tested in
one place.
"""

import uuid
from enum import StrEnum

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from horatio.models import Character, Troupe, TroupeMembership, TroupeStaff, User


class Role(StrEnum):
    LEAD_STORYTELLER = "lead_storyteller"
    STORYTELLER = "storyteller"
    ASSISTANT_STORYTELLER = "assistant_storyteller"
    NARRATOR = "narrator"


class TroupeAction(StrEnum):
    RENAME = "rename"
    EDIT_DESCRIPTION = "edit_description"
    ARCHIVE = "archive"
    MANAGE_STAFF = "manage_staff"
    MANAGE_HOUSE_RULES = "manage_house_rules"
    VIEW_STAFF = "view_staff"
    VIEW_MEMBER_CHARACTERS = "view_member_characters"
    APPROVE_CHANGES = "approve_changes"
    MANAGE_CYCLES = "manage_cycles"
    ASSIGN_RESPONSES = "assign_responses"
    ADJUST_ALLOWANCES = "adjust_allowances"
    DELIVER_RESPONSES = "deliver_responses"
    ANSWER_ASSIGNED_RESPONSES = "answer_assigned_responses"


_LEAD = {Role.LEAD_STORYTELLER}
_STORYTELLERS = _LEAD | {Role.STORYTELLER}
_RUNNING = _STORYTELLERS | {Role.ASSISTANT_STORYTELLER}
_ALL_STAFF = _RUNNING | {Role.NARRATOR}

TROUPE_POLICY: dict[TroupeAction, frozenset[Role]] = {
    TroupeAction.RENAME: frozenset(_LEAD),
    TroupeAction.EDIT_DESCRIPTION: frozenset(_LEAD),
    TroupeAction.ARCHIVE: frozenset(_LEAD),
    TroupeAction.MANAGE_STAFF: frozenset(_STORYTELLERS),
    TroupeAction.MANAGE_HOUSE_RULES: frozenset(_STORYTELLERS),
    TroupeAction.VIEW_STAFF: frozenset(_ALL_STAFF),
    TroupeAction.VIEW_MEMBER_CHARACTERS: frozenset(_RUNNING),
    TroupeAction.APPROVE_CHANGES: frozenset(_RUNNING),
    TroupeAction.MANAGE_CYCLES: frozenset(_RUNNING),
    TroupeAction.ASSIGN_RESPONSES: frozenset(_RUNNING),
    TroupeAction.ADJUST_ALLOWANCES: frozenset(_RUNNING),
    TroupeAction.DELIVER_RESPONSES: frozenset(_RUNNING),
    TroupeAction.ANSWER_ASSIGNED_RESPONSES: frozenset(_ALL_STAFF),
}


def allows(role: Role | None, action: TroupeAction, *, is_custodian: bool = False) -> bool:
    """The policy itself, without the database."""
    return is_custodian or (role is not None and role in TROUPE_POLICY[action])


def troupe_role(db: Session, user: User, troupe: Troupe) -> Role | None:
    if troupe.lead_user_id == user.id:
        return Role.LEAD_STORYTELLER
    role = db.scalar(
        select(TroupeStaff.role).where(
            TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == user.id
        )
    )
    return Role(role) if role else None


def require_troupe_action(db: Session, user: User, troupe: Troupe, action: TroupeAction) -> None:
    """Refuse with 403 unless `user` may take `action` in `troupe`. An archived
    troupe is closed to everything except the custodian."""
    if troupe.archived_at is not None and not user.is_custodian:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This troupe is archived.")
    if not allows(troupe_role(db, user, troupe), action, is_custodian=user.is_custodian):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot do that in this troupe.")


def require_custodian(user: User) -> None:
    if not user.is_custodian:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the custodian can do that.")


def can_view_character(db: Session, user: User, character: Character) -> bool:
    """Its player, the custodian, and the running staff of any troupe it currently belongs to."""
    if user.is_custodian or character.player_id == user.id:
        return True
    running = [r.value for r in TROUPE_POLICY[TroupeAction.VIEW_MEMBER_CHARACTERS]]
    member_troupes = select(TroupeMembership.troupe_id).where(
        TroupeMembership.character_id == character.id, TroupeMembership.left_at.is_(None)
    )
    is_lead = exists().where(
        Troupe.id.in_(member_troupes), Troupe.lead_user_id == user.id, Troupe.archived_at.is_(None)
    )
    is_staff = exists().where(
        TroupeStaff.troupe_id.in_(member_troupes),
        TroupeStaff.user_id == user.id,
        TroupeStaff.role.in_(running),
    )
    return bool(db.scalar(select(is_lead | is_staff)))


def can_edit_character(user: User, character: Character) -> bool:
    """Only the player edits their character; staff approve, they do not edit."""
    return character.player_id == user.id


def visible_character(db: Session, user: User, character_id: uuid.UUID) -> Character:
    """The character, or 404 if it does not exist or `user` may not see it, so
    that the API does not reveal which characters exist."""
    character = db.get(Character, character_id)
    if character is None or not can_view_character(db, user, character):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    return character

"""Who may do what. Every route asks here; nothing checks roles ad hoc (ADR 0002).

Roles come from CONTEXT.md:

- the custodian runs the whole system, above every troupe;
- a troupe's lead storyteller is a storyteller who can also rename, describe
  and archive it;
- storytellers and the lead are the only ones who manage staff, house rules and
  connectors, and edit the troupe's profile;
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
from sqlalchemy import ColumnElement, and_, exists, or_, select, true
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
    MANAGE_CONNECTORS = "manage_connectors"
    EDIT_PROFILE = "edit_profile"
    VIEW_STAFF = "view_staff"
    VIEW_MEMBER_CHARACTERS = "view_member_characters"
    APPROVE_CHANGES = "approve_changes"
    AWARD_XP = "award_xp"
    MANAGE_CYCLES = "manage_cycles"
    ASSIGN_RESPONSES = "assign_responses"
    ADJUST_ALLOWANCES = "adjust_allowances"
    DELIVER_RESPONSES = "deliver_responses"
    ANSWER_ASSIGNED_RESPONSES = "answer_assigned_responses"
    MANAGE_RANDOM_TABLES = "manage_random_tables"
    VIEW_LOG = "view_log"
    MANAGE_NPCS = "manage_npcs"
    MANAGE_TITLES = "manage_titles"
    CHANGE_STATUS = "change_status"
    RESET_GAMES = "reset_games"
    MANAGE_INFLUENCE_LOG = "manage_influence_log"
    MANAGE_SHARED_BACKGROUNDS = "manage_shared_backgrounds"
    RUN_SCENES = "run_scenes"
    CHANGE_ANY_SCENE = "change_any_scene"


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
    TroupeAction.MANAGE_CONNECTORS: frozenset(_STORYTELLERS),
    # The troupe's profile: its portrait, links, schedule, venue and the rest.
    TroupeAction.EDIT_PROFILE: frozenset(_STORYTELLERS),
    TroupeAction.VIEW_STAFF: frozenset(_ALL_STAFF),
    TroupeAction.VIEW_MEMBER_CHARACTERS: frozenset(_RUNNING),
    TroupeAction.APPROVE_CHANGES: frozenset(_RUNNING),
    TroupeAction.AWARD_XP: frozenset(_RUNNING),
    TroupeAction.MANAGE_CYCLES: frozenset(_RUNNING),
    TroupeAction.ASSIGN_RESPONSES: frozenset(_RUNNING),
    TroupeAction.ADJUST_ALLOWANCES: frozenset(_RUNNING),
    TroupeAction.DELIVER_RESPONSES: frozenset(_RUNNING),
    TroupeAction.ANSWER_ASSIGNED_RESPONSES: frozenset(_ALL_STAFF),
    TroupeAction.MANAGE_RANDOM_TABLES: frozenset(_RUNNING),
    TroupeAction.VIEW_LOG: frozenset(_RUNNING),
    TroupeAction.MANAGE_NPCS: frozenset(_RUNNING),
    TroupeAction.MANAGE_TITLES: frozenset(_RUNNING),
    # Adding and removing a character's fleeting and negative status, and marking
    # its status bans, whatever the troupe's Status on sheets setting says
    # (horatio.sect_status).
    TroupeAction.CHANGE_STATUS: frozenset(_RUNNING),
    # Resetting every character's Play View after a game.
    TroupeAction.RESET_GAMES: frozenset(_RUNNING),
    # Reading and keeping the troupe's influence log. Players never see it.
    TroupeAction.MANAGE_INFLUENCE_LOG: frozenset(_RUNNING),
    # Setting up shared backgrounds and keeping their logs. The players of the
    # characters sharing one also see it (horatio.shared_backgrounds).
    TroupeAction.MANAGE_SHARED_BACKGROUNDS: frozenset(_RUNNING),
    # Opening the troupe's scenes, making them, and pinning in any of them. Its
    # maker renames or removes a scene (horatio.api.scenes).
    TroupeAction.RUN_SCENES: frozenset(_RUNNING),
    # Renaming or removing a scene someone else made, and clearing old ones.
    TroupeAction.CHANGE_ANY_SCENE: frozenset(_LEAD),
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
    """A PC's player, the custodian, and the running staff of any troupe it currently
    belongs to (for an NPC, the troupe that keeps it)."""
    if user.is_custodian or (character.kind == "pc" and character.player_id == user.id):
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


def viewable_characters(user: User) -> ColumnElement[bool]:
    """The characters `user` can see, as `can_view_character` says, as a condition on
    Character: to list them."""
    if user.is_custodian:
        return true()
    running = [r.value for r in TROUPE_POLICY[TroupeAction.VIEW_MEMBER_CHARACTERS]]
    led = select(Troupe.id).where(Troupe.lead_user_id == user.id, Troupe.archived_at.is_(None))
    staffed = select(TroupeStaff.troupe_id).where(
        TroupeStaff.user_id == user.id, TroupeStaff.role.in_(running)
    )
    in_their_troupes = select(TroupeMembership.character_id).where(
        TroupeMembership.left_at.is_(None),
        or_(TroupeMembership.troupe_id.in_(led), TroupeMembership.troupe_id.in_(staffed)),
    )
    return or_(
        and_(Character.kind == "pc", Character.player_id == user.id),
        Character.id.in_(in_their_troupes),
    )


def is_staff_for(db: Session, user: User, character: Character) -> bool:
    """The custodian, and the running staff of a troupe the character belongs to
    now: those who see its sheet without being its player."""
    if user.is_custodian:
        return True
    if character.kind == "pc" and character.player_id == user.id:
        # Its player may also be staff where it plays; check as if they were not.
        return _running_staff_of(db, user, character)
    return can_view_character(db, user, character)


def _running_staff_of(db: Session, user: User, character: Character) -> bool:
    troupe_ids = select(TroupeMembership.troupe_id).where(
        TroupeMembership.character_id == character.id, TroupeMembership.left_at.is_(None)
    )
    for troupe in db.scalars(select(Troupe).where(Troupe.id.in_(troupe_ids))):
        if troupe.archived_at is None and allows(
            troupe_role(db, user, troupe), TroupeAction.VIEW_MEMBER_CHARACTERS
        ):
            return True
    return False


def can_edit_character(db: Session, user: User, character: Character) -> bool:
    """A PC is edited only by its player; staff approve, they do not edit. An NPC is
    edited by the running staff of the troupe it belongs to (CONTEXT.md: NPC)."""
    if character.kind == "pc":
        return character.player_id == user.id
    troupe = db.get(Troupe, character.owner_troupe_id)
    return troupe is not None and allows(
        troupe_role(db, user, troupe), TroupeAction.MANAGE_NPCS, is_custodian=user.is_custodian
    )


def visible_character(db: Session, user: User, character_id: uuid.UUID) -> Character:
    """The character, or 404 if it does not exist or `user` may not see it, so
    that the API does not reveal which characters exist."""
    character = db.get(Character, character_id)
    if character is None or not can_view_character(db, user, character):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    return character

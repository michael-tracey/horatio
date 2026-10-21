import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import audit, handles, xp_range
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import TraitCategory, TraitDefinition, Troupe, TroupeStaff, User
from horatio.permissions import (
    Role,
    TroupeAction,
    require_custodian,
    require_troupe_action,
    troupe_role,
)

router = APIRouter(prefix="/troupes", tags=["troupes"])

STAFF_ROLES = (Role.STORYTELLER, Role.ASSISTANT_STORYTELLER, Role.NARRATOR)


class TroupeOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    lead_user_id: uuid.UUID
    archived: bool
    # Sects whose player characters may join; empty means any.
    allowed_sects: list[str]
    # The usual XP for a game session and for completing a downtime.
    session_xp: int
    downtime_xp: int
    # The XP a character had when the chronicle began, and the troupe's XP floor
    # and ceiling now (horatio.xp_range): a new character built for it starts at the floor.
    starting_xp: int
    xp_floor: int
    xp_ceiling: int
    # House rule: the blood characters start a game with; None for full.
    starting_blood: int | None
    # The caller's own role here, if any.
    my_role: Role | None


class NewTroupe(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    # The lead storyteller's handle.
    lead_handle: str


class TroupeChanges(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    allowed_sects: list[str] | None = None
    session_xp: int | None = Field(default=None, ge=0, le=100)
    downtime_xp: int | None = Field(default=None, ge=0, le=100)
    starting_xp: int | None = Field(default=None, ge=0, le=10000)


class NewLead(BaseModel):
    handle: str


class StaffMember(BaseModel):
    user_id: uuid.UUID
    display_name: str
    handle: str
    role: Role


class StaffAssignment(BaseModel):
    handle: str
    role: Role


def troupe_out(db: DbSession, user: User, troupe: Troupe) -> TroupeOut:
    figures = xp_range.figures(db, troupe)
    return TroupeOut(
        id=troupe.id,
        name=troupe.name,
        description=troupe.description,
        lead_user_id=troupe.lead_user_id,
        archived=troupe.archived_at is not None,
        allowed_sects=troupe.allowed_sects,
        session_xp=troupe.session_xp,
        downtime_xp=troupe.downtime_xp,
        starting_xp=troupe.starting_xp,
        xp_floor=figures.floor,
        xp_ceiling=figures.ceiling,
        starting_blood=troupe.starting_blood,
        my_role=troupe_role(db, user, troupe),
    )


def staff_member(user: User, role: Role) -> StaffMember:
    return StaffMember(
        user_id=user.id, display_name=user.display_name, handle=user.handle, role=role
    )


def get_troupe(db: DbSession, troupe_id: uuid.UUID) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def existing_user(db: DbSession, handle: str) -> User:
    """Whoever has the handle, or had it lately (horatio.handles)."""
    user = handles.holder(db, handle) if handle.strip() else None
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Nobody has the handle {handle.strip()}.")
    return user


@router.get("")
def list_troupes(db: DbSession, user: CurrentUser) -> list[TroupeOut]:
    """Every troupe still running. Players need to see them to ask to join."""
    troupes = db.scalars(select(Troupe).where(Troupe.archived_at.is_(None)).order_by(Troupe.name))
    return [troupe_out(db, user, t) for t in troupes]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_troupe(body: NewTroupe, db: DbSession, user: CurrentUser) -> TroupeOut:
    """The custodian sets up a troupe and names its lead storyteller."""
    require_custodian(user)
    lead = existing_user(db, body.lead_handle)
    troupe = Troupe(name=body.name, description=body.description, lead_user_id=lead.id)
    db.add(troupe)
    db.commit()
    return troupe_out(db, user, troupe)


@router.get("/{troupe_id}")
def read_troupe(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TroupeOut:
    troupe = get_troupe(db, troupe_id)
    if troupe.archived_at is not None and not user.is_custodian:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe_out(db, user, troupe)


@router.patch("/{troupe_id}")
def change_troupe(
    troupe_id: uuid.UUID, body: TroupeChanges, db: DbSession, user: CurrentUser
) -> TroupeOut:
    troupe = get_troupe(db, troupe_id)
    if body.name is not None:
        require_troupe_action(db, user, troupe, TroupeAction.RENAME)
        troupe.name = body.name
        audit.record(db, user, "troupe.renamed", troupe_id=troupe.id, name=body.name)
    if body.description is not None:
        require_troupe_action(db, user, troupe, TroupeAction.EDIT_DESCRIPTION)
        troupe.description = body.description
    if body.allowed_sects is not None:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        known = set(
            db.scalars(
                select(TraitDefinition.name)
                .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
                .where(TraitCategory.key == "sect")
            )
        )
        unknown = sorted(set(body.allowed_sects) - known)
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"No such sect: {', '.join(unknown)}."
            )
        troupe.allowed_sects = sorted(set(body.allowed_sects))
        audit.record(
            db,
            user,
            "troupe.sects_limited",
            troupe_id=troupe.id,
            sects=", ".join(troupe.allowed_sects) or "any",
        )
    if body.session_xp is not None or body.downtime_xp is not None:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        if body.session_xp is not None:
            troupe.session_xp = body.session_xp
        if body.downtime_xp is not None:
            troupe.downtime_xp = body.downtime_xp
        audit.record(
            db,
            user,
            "troupe.xp_defaults",
            troupe_id=troupe.id,
            session_xp=troupe.session_xp,
            downtime_xp=troupe.downtime_xp,
        )
    if body.starting_xp is not None:
        # The floor and ceiling both start from it, so both move with it.
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
        troupe.starting_xp = body.starting_xp
        audit.record(
            db, user, "troupe.starting_xp", troupe_id=troupe.id, starting_xp=troupe.starting_xp
        )
    db.commit()
    return troupe_out(db, user, troupe)


@router.delete("/{troupe_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_troupe(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Deleting a troupe archives it: closed to use, history kept."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.ARCHIVE)
    troupe.archived_at = datetime.now(UTC)
    audit.record(db, user, "troupe.archived", troupe_id=troupe.id)
    db.commit()


@router.put("/{troupe_id}/lead")
def appoint_lead(
    troupe_id: uuid.UUID, body: NewLead, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """The custodian appoints a troupe's lead storyteller."""
    require_custodian(user)
    troupe = get_troupe(db, troupe_id)
    lead = existing_user(db, body.handle)
    # The lead is never also listed as ordinary staff.
    staff_row = db.scalar(
        select(TroupeStaff).where(
            TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == lead.id
        )
    )
    if staff_row is not None:
        db.delete(staff_row)
    troupe.lead_user_id = lead.id
    audit.record(db, user, "troupe.lead_appointed", troupe_id=troupe.id, member=lead.display_name)
    db.commit()
    return troupe_out(db, user, troupe)


@router.get("/{troupe_id}/staff")
def list_staff(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[StaffMember]:
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.VIEW_STAFF)
    lead = db.get_one(User, troupe.lead_user_id)
    staff = db.execute(
        select(User, TroupeStaff.role)
        .join(TroupeStaff, TroupeStaff.user_id == User.id)
        .where(TroupeStaff.troupe_id == troupe.id)
        .order_by(User.display_name)
    )
    return [staff_member(lead, Role.LEAD_STORYTELLER)] + [
        staff_member(u, Role(role)) for u, role in staff
    ]


@router.put("/{troupe_id}/staff")
def assign_staff(
    troupe_id: uuid.UUID, body: StaffAssignment, db: DbSession, user: CurrentUser
) -> StaffMember:
    """Add someone to the staff, or change their role."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_STAFF)
    if body.role not in STAFF_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The lead storyteller is appointed by the custodian.",
        )
    member = existing_user(db, body.handle)
    if member.id == troupe.lead_user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "That person is the lead storyteller.")
    row = db.scalar(
        select(TroupeStaff).where(
            TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == member.id
        )
    )
    if row is None:
        row = TroupeStaff(troupe_id=troupe.id, user_id=member.id, role=body.role)
        db.add(row)
    else:
        row.role = body.role
    audit.record(
        db,
        user,
        "staff.assigned",
        troupe_id=troupe.id,
        member=member.display_name,
        role=body.role.value.replace("_", " "),
    )
    db.commit()
    return staff_member(member, body.role)


@router.delete("/{troupe_id}/staff/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_staff(
    troupe_id: uuid.UUID, user_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> None:
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_STAFF)
    row = db.scalar(
        select(TroupeStaff).where(
            TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == user_id
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That person is not on the staff.")
    member = db.get_one(User, user_id)
    db.delete(row)
    audit.record(db, user, "staff.removed", troupe_id=troupe.id, member=member.display_name)
    db.commit()

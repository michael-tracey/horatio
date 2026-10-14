import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe, TroupeStaff, User
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
    # The caller's own role here, if any.
    my_role: Role | None


class NewTroupe(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    lead_email: EmailStr


class TroupeChanges(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class NewLead(BaseModel):
    email: EmailStr


class StaffMember(BaseModel):
    user_id: uuid.UUID
    display_name: str
    role: Role


class StaffAssignment(BaseModel):
    email: EmailStr
    role: Role


def troupe_out(db: DbSession, user: User, troupe: Troupe) -> TroupeOut:
    return TroupeOut(
        id=troupe.id,
        name=troupe.name,
        description=troupe.description,
        lead_user_id=troupe.lead_user_id,
        archived=troupe.archived_at is not None,
        my_role=troupe_role(db, user, troupe),
    )


def get_troupe(db: DbSession, troupe_id: uuid.UUID) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def existing_user(db: DbSession, email: str) -> User:
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nobody has an account with that email.")
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
    lead = existing_user(db, body.lead_email)
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
    if body.description is not None:
        require_troupe_action(db, user, troupe, TroupeAction.EDIT_DESCRIPTION)
        troupe.description = body.description
    db.commit()
    return troupe_out(db, user, troupe)


@router.delete("/{troupe_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_troupe(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Deleting a troupe archives it: closed to use, history kept."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.ARCHIVE)
    troupe.archived_at = datetime.now(UTC)
    db.commit()


@router.put("/{troupe_id}/lead")
def appoint_lead(
    troupe_id: uuid.UUID, body: NewLead, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """The custodian appoints a troupe's lead storyteller."""
    require_custodian(user)
    troupe = get_troupe(db, troupe_id)
    lead = existing_user(db, body.email)
    # The lead is never also listed as ordinary staff.
    staff_row = db.scalar(
        select(TroupeStaff).where(
            TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == lead.id
        )
    )
    if staff_row is not None:
        db.delete(staff_row)
    troupe.lead_user_id = lead.id
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
    return [
        StaffMember(user_id=lead.id, display_name=lead.display_name, role=Role.LEAD_STORYTELLER)
    ] + [
        StaffMember(user_id=u.id, display_name=u.display_name, role=Role(role)) for u, role in staff
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
    member = existing_user(db, body.email)
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
    db.commit()
    return StaffMember(user_id=member.id, display_name=member.display_name, role=body.role)


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
    db.delete(row)
    db.commit()

"""A troupe's own checks (horatio.house_checks): its storytellers add, change and
remove them on the Checks page; its running staff see them, and which characters
break each."""

import uuid
from dataclasses import replace
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import house_checks
from horatio.api.downtimes import staff_troupe
from horatio.api.house_rules import house_splat
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import HouseCheck, Troupe
from horatio.permissions import TroupeAction
from horatio.rules.house_checks import (
    HouseCheckData,
    HouseCheckProblem,
    check_house_check,
    key_of,
    to_check,
)
from horatio.rules.house_checks import describe as describe_check
from horatio.rules.store import house_check_data, house_check_problem, read_troupe_rules

router = APIRouter(prefix="/troupes/{troupe_id}/house-checks", tags=["house rules"])


class OwnCheckIn(BaseModel):
    splat: str = "vampire"
    # The subject: a category, and in it one trait (`name`), the names starting with
    # `name_prefix`, or the traits of one catalogue type (`kind`); none of these for
    # every trait of the category.
    category: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    name_prefix: str | None = Field(default=None, max_length=200)
    kind: str | None = Field(default=None, max_length=100)
    mode: Literal["requires", "forbids"]
    # In horatio.rules.checks' vocabulary, the part horatio.rules.house_checks allows.
    condition: dict[str, Any]
    strength: Literal["refuse", "complete", "review", "note"] = "refuse"
    message: str = Field(max_length=500)
    # For a check needed to finish creation: the step (a category) it holds the wizard on.
    step: str | None = Field(default=None, max_length=100)

    def to_data(self, check_id: object = "draft") -> HouseCheckData:
        return HouseCheckData(
            id=str(check_id),
            splat=self.splat,
            category=self.category,
            name=self.name or None,
            name_prefix=self.name_prefix or None,
            kind=self.kind or None,
            mode=self.mode,
            condition=self.condition,
            strength=self.strength,
            message=self.message,
            step=self.step or None,
        )


class BreakingOut(BaseModel):
    character_id: uuid.UUID
    name: str
    kind: str
    # The message the check gives on that sheet.
    message: str


class OwnCheckOut(OwnCheckIn):
    id: uuid.UUID
    # The key the engine knows it by, as the sheet's notes and approvals name it.
    key: str
    # The check in plain words: "Pliable Blood: refused once creation is finished.".
    text: str
    # Why the rules cannot run it now (a trait the book has since lost), or None.
    problem: str | None
    # The troupe's characters it breaks now: flagged on their sheets, not changed.
    breaking: list[BreakingOut]


class OwnCheckPreviewIn(BaseModel):
    check: OwnCheckIn
    # The one being changed; none for a new one.
    house_check_id: uuid.UUID | None = None


class OwnCheckPreviewOut(BaseModel):
    text: str
    # Why it cannot be saved as it is, or None.
    problem: str | None
    breaking: list[BreakingOut]


def breaking_out(found: list[house_checks.Breaking]) -> list[BreakingOut]:
    return [
        BreakingOut(
            character_id=b.character.id, name=b.character.name, kind=b.character.kind,
            message=b.message,
        )
        for b in found
    ]  # fmt: skip


def checked_in(db: DbSession, troupe: Troupe, body: OwnCheckIn) -> OwnCheckIn:
    house_splat(db, troupe.id, body.splat)
    return body


def troupe_check(db: DbSession, troupe: Troupe, check_id: uuid.UUID) -> HouseCheck:
    row = house_checks.row_of(db, troupe, check_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such check.")
    return row


def checks_of(db: DbSession, troupe: Troupe) -> list[OwnCheckOut]:
    """The troupe's own checks, each with what it says and the characters it breaks."""
    rows = list(
        db.scalars(
            select(HouseCheck)
            .where(HouseCheck.troupe_id == troupe.id)
            .order_by(HouseCheck.created_at, HouseCheck.id)
        )
    )
    found: list[OwnCheckOut] = []
    by_splat: dict[str, list[HouseCheck]] = {}
    for row in rows:
        by_splat.setdefault(row.splat, []).append(row)
    breaks: dict[str, list[house_checks.Breaking]] = {}
    texts: dict[uuid.UUID, tuple[str, str | None]] = {}
    for splat, splat_rows in by_splat.items():
        rule_set = read_troupe_rules(db, splat, troupe.id).rule_set
        usable = []
        for row in splat_rows:
            data = house_check_data(row)
            problem = house_check_problem(data, rule_set)
            text = describe_check(data, rule_set) if problem is None else row.message
            texts[row.id] = (text, problem)
            if problem is None:
                usable.append(to_check(data, troupe.name))
        breaks |= house_checks.breaking(db, troupe, splat, usable)
    for row in rows:
        text, problem = texts[row.id]
        found.append(
            OwnCheckOut(
                id=row.id,
                key=key_of(row.id),
                splat=row.splat,
                category=row.category,
                name=row.name,
                name_prefix=row.name_prefix,
                kind=row.kind,
                mode=row.mode,  # type: ignore[arg-type]  # checked by the database
                condition=row.condition,
                strength=row.strength,  # type: ignore[arg-type]  # checked by the database
                message=row.message,
                step=row.step,
                text=text,
                problem=problem,
                breaking=breaking_out(breaks.get(key_of(row.id), [])),
            )
        )
    return found


@router.get("")
def list_own_checks(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[OwnCheckOut]:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return checks_of(db, troupe)


@router.post("", status_code=status.HTTP_201_CREATED)
def add_own_check(
    troupe_id: uuid.UUID, body: OwnCheckIn, db: DbSession, user: CurrentUser
) -> OwnCheckOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    row = house_checks.create(db, user, troupe, checked_in(db, troupe, body).to_data())
    db.commit()
    return next(c for c in checks_of(db, troupe) if c.id == row.id)


@router.put("/{check_id}")
def change_own_check(
    troupe_id: uuid.UUID, check_id: uuid.UUID, body: OwnCheckIn, db: DbSession, user: CurrentUser
) -> OwnCheckOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    row = troupe_check(db, troupe, check_id)
    house_checks.change(db, user, troupe, row, checked_in(db, troupe, body).to_data(row.id))
    db.commit()
    return next(c for c in checks_of(db, troupe) if c.id == row.id)


@router.delete("/{check_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_own_check(
    troupe_id: uuid.UUID, check_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Response:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    house_checks.delete(db, user, troupe, troupe_check(db, troupe, check_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/preview")
def preview_own_check(
    troupe_id: uuid.UUID, body: OwnCheckPreviewIn, db: DbSession, user: CurrentUser
) -> OwnCheckPreviewOut:
    """The check as it is being built, in plain words, and the troupe's characters it
    would break; or why it cannot be saved as it is. Nothing is saved."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    if body.house_check_id is not None:
        troupe_check(db, troupe, body.house_check_id)
    checked_in(db, troupe, body.check)
    data = body.check.to_data(body.house_check_id or "draft")
    rule_set = read_troupe_rules(db, data.splat, troupe.id).rule_set
    # The message is written last: until then, the check is tried with its words.
    unwritten = not data.message.strip()
    try:
        check_house_check(replace(data, message="-") if unwritten else data, rule_set)
    except HouseCheckProblem as problem:
        return OwnCheckPreviewOut(text="", problem=str(problem), breaking=[])
    text = describe_check(data, rule_set)
    if unwritten:
        data = replace(data, message=text)
    return OwnCheckPreviewOut(
        text=text,
        problem=None,
        breaking=breaking_out(house_checks.would_break(db, troupe, data)),
    )

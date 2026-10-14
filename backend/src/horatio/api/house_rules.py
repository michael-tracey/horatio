"""A troupe's house rules for checks: switching one off, or changing how strict it is."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import audit
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.permissions import TroupeAction
from horatio.rules.store import read_troupe_rules, set_check_override

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["house rules"])

Strength = Literal["refuse", "complete", "review", "note", "off"]


class CheckOut(BaseModel):
    key: str
    # What it is about: a trait, a category, or names starting with a prefix.
    category: str
    about: str
    message: str
    page: str | None
    # As the rule set has it, and as this troupe plays it.
    strength: str
    house: str | None


class CheckChange(BaseModel):
    # None goes back to the rule set's strength.
    strength: Strength | None


def checks_out(db: DbSession, troupe_id: uuid.UUID, splat: str = "vampire") -> list[CheckOut]:
    rules = read_troupe_rules(db, splat, troupe_id)
    return [
        CheckOut(
            key=c.key,
            category=c.category,
            about=c.name or (f"{c.name_prefix}…" if c.name_prefix else "any"),
            message=c.message,
            page=c.page,
            strength=c.strength,
            house=rules.check_overrides.get(c.key),
        )
        for c in rules.rule_set.checks
    ]


@router.get("/checks")
def list_checks(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[CheckOut]:
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return checks_out(db, troupe_id)


@router.put("/checks/{key:path}")
def change_check(
    troupe_id: uuid.UUID, key: str, body: CheckChange, db: DbSession, user: CurrentUser
) -> CheckOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    known = {c.key for c in read_troupe_rules(db, "vampire", troupe_id).rule_set.checks}
    if key not in known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such check.")
    set_check_override(db, troupe.id, key, body.strength)
    audit.record(
        db,
        user,
        "house.check",
        troupe_id=troupe.id,
        check=key,
        strength=body.strength or "as the rules say",
    )
    db.commit()
    return next(c for c in checks_out(db, troupe_id) if c.key == key)

"""A troupe's written house rules (horatio.written_rules): its storytellers add, edit,
reorder and delete them under Customise › Rules; anyone signed in reads them, as they
may the troupe's other house rules."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.orm import Session

from horatio import audit
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe, WrittenRule
from horatio.permissions import TroupeAction
from horatio.written_rules import LinkedTrait, find_trait, last_in, linked_traits, listed, move

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["written rules"])

Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


class TraitLink(BaseModel):
    """A trait of the rule set for `splat`, or one of the troupe's own merits or flaws."""

    splat: str = "vampire"
    category: str
    name: str


class WrittenRuleIn(BaseModel):
    section: Annotated[Trimmed, Field(max_length=100)] = ""
    title: Annotated[Trimmed, Field(min_length=1, max_length=200)]
    # Markdown.
    body: Annotated[str, Field(max_length=20000)] = ""
    trait: TraitLink | None = None
    page: Annotated[Trimmed, Field(max_length=300)] | None = None


class WrittenRuleChange(WrittenRuleIn):
    # Swap it with the rule before or after it in its section; with this, the rest of
    # the body is left as it is.
    move: Literal["up", "down"] | None = None


class WrittenRuleOut(BaseModel):
    id: uuid.UUID
    section: str
    title: str
    body: str
    position: int
    trait: TraitLink | None
    page: str | None


class WrittenRulesOut(BaseModel):
    # Whether the troupe's profile shows them too.
    public: bool
    # In reading order: the rules with no section first, then by section, each
    # section in the order staff put it.
    rules: list[WrittenRuleOut]


class PublicIn(BaseModel):
    public: bool


def rule_out(rule: WrittenRule, trait: LinkedTrait | None) -> WrittenRuleOut:
    return WrittenRuleOut(
        id=rule.id,
        section=rule.section,
        title=rule.title,
        body=rule.body,
        position=rule.position,
        trait=TraitLink(splat=trait.splat, category=trait.category, name=trait.name)
        if trait
        else None,
        page=rule.page,
    )


def rules_out(db: Session, troupe_id: uuid.UUID) -> list[WrittenRuleOut]:
    found = listed(db, troupe_id)
    traits = linked_traits(db, found)
    return [
        rule_out(r, traits.get(r.trait_definition_id) if r.trait_definition_id else None)
        for r in found
    ]


def written_out(db: Session, troupe: Troupe) -> WrittenRulesOut:
    return WrittenRulesOut(public=troupe.written_rules_public, rules=rules_out(db, troupe.id))


def readable(db: Session, user: CurrentUser, troupe_id: uuid.UUID) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or (troupe.archived_at is not None and not user.is_custodian):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def editable(db: Session, user: CurrentUser, troupe_id: uuid.UUID) -> Troupe:
    return staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)


def troupe_rule(db: Session, troupe: Troupe, rule_id: uuid.UUID) -> WrittenRule:
    rule = db.get(WrittenRule, rule_id)
    if rule is None or rule.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such rule.")
    return rule


def trait_of(db: Session, troupe: Troupe, link: TraitLink | None) -> uuid.UUID | None:
    if link is None:
        return None
    found = find_trait(db, troupe.id, link.splat, link.category, link.name)
    if found is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"There is no {link.category} trait called {link.name!r} to link to.",
        )
    return found.id


@router.get("/written-rules")
def read_written_rules(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> WrittenRulesOut:
    """The troupe's written house rules, in reading order. Anyone signed in may read
    them, as they may its other house rules."""
    return written_out(db, readable(db, user, troupe_id))


@router.post("/written-rules", status_code=status.HTTP_201_CREATED)
def add_written_rule(
    troupe_id: uuid.UUID, body: WrittenRuleIn, db: DbSession, user: CurrentUser
) -> WrittenRulesOut:
    """Add a written rule, last in its section."""
    troupe = editable(db, user, troupe_id)
    rule = WrittenRule(
        troupe_id=troupe.id,
        section=body.section,
        title=body.title,
        body=body.body,
        position=last_in(db, troupe.id, body.section),
        trait_definition_id=trait_of(db, troupe, body.trait),
        page=body.page or None,
    )
    db.add(rule)
    audit.record(
        db,
        user,
        "house.written_rule_added",
        troupe_id=troupe.id,
        title=rule.title,
        section=rule.section or "no section",
    )
    db.commit()
    return written_out(db, troupe)


@router.put("/written-rules/{rule_id}")
def change_written_rule(
    troupe_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: WrittenRuleChange,
    db: DbSession,
    user: CurrentUser,
) -> WrittenRulesOut:
    """Change a written rule's words, section or links; or move it up or down its
    section. Moved to another section, it goes last there."""
    troupe = editable(db, user, troupe_id)
    rule = troupe_rule(db, troupe, rule_id)
    if body.move is not None:
        if move(db, rule, body.move == "up"):
            audit.record(
                db,
                user,
                "house.written_rule_moved",
                troupe_id=troupe.id,
                title=rule.title,
                direction=body.move,
            )
        db.commit()
        return written_out(db, troupe)
    if body.section != rule.section:
        rule.position = last_in(db, troupe.id, body.section)
        rule.section = body.section
    rule.title = body.title
    rule.body = body.body
    rule.trait_definition_id = trait_of(db, troupe, body.trait)
    rule.page = body.page or None
    audit.record(db, user, "house.written_rule_changed", troupe_id=troupe.id, title=rule.title)
    db.commit()
    return written_out(db, troupe)


@router.delete("/written-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_written_rule(
    troupe_id: uuid.UUID, rule_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Response:
    troupe = editable(db, user, troupe_id)
    rule = troupe_rule(db, troupe, rule_id)
    db.delete(rule)
    audit.record(db, user, "house.written_rule_deleted", troupe_id=troupe.id, title=rule.title)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/written-rules-public")
def set_written_rules_public(
    troupe_id: uuid.UUID, body: PublicIn, db: DbSession, user: CurrentUser
) -> WrittenRulesOut:
    """Show the written rules on the troupe's profile too, or not: off unless staff
    switch it on. A public profile shows them to anyone at all."""
    troupe = editable(db, user, troupe_id)
    if body.public != troupe.written_rules_public:
        troupe.written_rules_public = body.public
        audit.record(
            db,
            user,
            "house.written_rules_public",
            troupe_id=troupe.id,
            state="shows its written rules" if body.public else "no longer shows its written rules",
        )
    db.commit()
    return written_out(db, troupe)

"""Downtime keywords as a troupe's house rules (horatio.keywords): its storytellers
change them under Customise › Rules › Keywords; its running staff read them there."""

import uuid
from dataclasses import replace

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import downtimes, keywords, social_age
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.permissions import TroupeAction

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["house rules"])


class KeywordIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    explanation: str = Field(default="", max_length=300)
    # What it asks for besides the description (horatio.keywords.FIELDS).
    fields: list[str] = Field(default_factory=list[str], max_length=6)
    # The action kinds it can be spent from.
    action_kinds: list[str] = Field(default_factory=lambda: ["general"], max_length=20)
    # Only as the one action a cycle the Computer skill gives.
    computers_only: bool = False
    # Fits a Science action.
    science: bool = False
    cost: int = Field(default=1, ge=0, le=5)
    # Required each cycle of characters of these social ages.
    required_for: list[str] = Field(default_factory=list[str], max_length=3)
    # Its step in the resolution order, 1 to 6.
    step: int = Field(default=keywords.NORMAL_STEP, ge=1, le=6)

    def to_change(self) -> keywords.Change:
        return keywords.Change(
            name=self.name,
            explanation=self.explanation,
            fields=self.fields,
            action_kinds=self.action_kinds,
            computers_only=self.computers_only,
            science=self.science,
            cost=self.cost,
            required_for=self.required_for,
            step=self.step,
        )


class KeywordOut(KeywordIn):
    key: str
    position: int
    retired: bool
    # What follows from it on its own: its default's key, or None for the troupe's own.
    effect: str | None


class TroupeKeywordOut(KeywordOut):
    # Horatio's default it started as, where it differs; None when it doesn't, or for
    # the troupe's own.
    default: KeywordOut | None = None
    # The rule in words.
    text: str


class StepOut(BaseModel):
    step: int
    name: str


class FieldOut(BaseModel):
    key: str
    label: str


class KeywordsOut(BaseModel):
    keywords: list[TroupeKeywordOut]
    steps: list[StepOut]
    fields: list[FieldOut]
    action_kinds: dict[str, str]
    ages: list[str]


class RetiredIn(BaseModel):
    retired: bool


class OrderIn(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=200)


def keyword_out(keyword: keywords.Keyword) -> KeywordOut:
    return KeywordOut(
        key=keyword.key,
        name=keyword.name,
        explanation=keyword.explanation,
        fields=list(keyword.fields),
        action_kinds=list(keyword.action_kinds),
        computers_only=keyword.computers_only,
        science=keyword.science,
        cost=keyword.cost,
        required_for=list(keyword.required_for),
        step=keyword.step,
        position=keyword.position,
        retired=keyword.retired,
        effect=keyword.effect,
    )


def listing(db: DbSession, troupe_id: uuid.UUID, kinds: dict[str, str]) -> KeywordsOut:
    found: list[TroupeKeywordOut] = []
    for keyword in keywords.troupe_keywords(db, troupe_id):
        default = keywords.DEFAULT_BY_KEY.get(keyword.key)
        same = default is not None and replace(keyword, position=default.position) == default
        found.append(
            TroupeKeywordOut(
                **keyword_out(keyword).model_dump(),
                default=keyword_out(default) if default is not None and not same else None,
                text=keywords.describe(keyword, kinds),
            )
        )
    return KeywordsOut(
        keywords=found,
        steps=[StepOut(step=n, name=name) for n, name in keywords.STEPS.items()],
        fields=[FieldOut(key=k, label=label) for k, label in keywords.FIELDS.items()],
        action_kinds=kinds,
        ages=list(social_age.AGES),
    )


@router.get("/keywords")
def list_keywords(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> KeywordsOut:
    """The troupe's downtime keywords, retired ones too, in its order: for its running
    staff."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_CYCLES)
    return listing(db, troupe.id, downtimes.troupe_action_kinds(db, troupe))


@router.post("/keywords", status_code=201)
def add_keyword(
    troupe_id: uuid.UUID, body: KeywordIn, db: DbSession, user: CurrentUser
) -> KeywordsOut:
    """A keyword of the troupe's own, at the end of its list."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    kinds = downtimes.troupe_action_kinds(db, troupe)
    keywords.add(db, user, troupe, body.to_change(), kinds)
    db.commit()
    return listing(db, troupe.id, kinds)


@router.put("/keywords/{key}")
def change_keyword(
    troupe_id: uuid.UUID, key: str, body: KeywordIn, db: DbSession, user: CurrentUser
) -> KeywordsOut:
    """Rename, reword or change the rules of one keyword. A default keeps what follows
    from it, under its new name."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    kinds = downtimes.troupe_action_kinds(db, troupe)
    keywords.change(db, user, troupe, key, body.to_change(), kinds)
    db.commit()
    return listing(db, troupe.id, kinds)


@router.put("/keywords/{key}/retired")
def retire_keyword(
    troupe_id: uuid.UUID, key: str, body: RetiredIn, db: DbSession, user: CurrentUser
) -> KeywordsOut:
    """Retire a keyword, so it is no longer offered, or bring it back. Past downtimes
    keep it either way."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    keywords.retire(db, user, troupe, key, body.retired)
    db.commit()
    return listing(db, troupe.id, downtimes.troupe_action_kinds(db, troupe))


@router.put("/keyword-order")
def reorder_keywords(
    troupe_id: uuid.UUID, body: OrderIn, db: DbSession, user: CurrentUser
) -> KeywordsOut:
    """The order the form offers them in, which is also their order within a step of the
    resolution order."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    keywords.reorder(db, user, troupe, body.keys)
    db.commit()
    return listing(db, troupe.id, downtimes.troupe_action_kinds(db, troupe))


@router.delete("/keywords")
def reset_keywords(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> KeywordsOut:
    """Back to Horatio's keywords. The troupe's own are retired, so past downtimes keep
    them."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    keywords.reset(db, user, troupe)
    db.commit()
    return listing(db, troupe.id, downtimes.troupe_action_kinds(db, troupe))

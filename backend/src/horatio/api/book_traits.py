"""A troupe's changes to book traits (horatio.book_traits): its running staff see
them and who holds a banned trait; its storytellers make them."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import book_traits
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe
from horatio.permissions import TroupeAction
from horatio.rules.model import TraitChangeData
from horatio.rules.splats import SPLATS
from horatio.rules.store import read_troupe_rules

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["book traits"])


class BookTraitOut(BaseModel):
    """A troupe's change to one book trait."""

    splat: str
    # The splat's name in the app, "Vampire".
    splat_label: str
    category: str
    category_name: str
    name: str
    # The book's page, still shown beside the troupe's change.
    page: str | None
    banned: bool
    # Why, in the troupe's words, for its players; "" for no reason given.
    ban_reason: str


class BannedHolderOut(BaseModel):
    """A character playing by the troupe's rules who holds a trait it bans."""

    character_id: uuid.UUID
    character_name: str
    splat: str
    category: str
    name: str
    detail: str
    # An exception lets this character have it.
    excepted: bool


class BookTraitsOut(BaseModel):
    changes: list[BookTraitOut]
    holders: list[BannedHolderOut]


class BookTraitChange(BaseModel):
    """A change to one book trait. Only the fields given change; the rest stay."""

    splat: str = "vampire"
    category: str = Field(max_length=100)
    name: str = Field(max_length=200)
    banned: bool | None = None
    ban_reason: str | None = Field(default=None, max_length=500)


def book_trait_out(
    db: DbSession, troupe: Troupe, splat: str, change: TraitChangeData
) -> BookTraitOut:
    rule_set = read_troupe_rules(db, splat, troupe.id).rule_set
    trait = rule_set.traits.get((change.category, change.name))
    return BookTraitOut(
        splat=splat,
        splat_label=SPLATS[splat].label or splat,
        category=change.category,
        category_name=rule_set.categories[change.category].name,
        name=change.name,
        page=trait.page_reference if trait else None,
        banned=change.banned,
        ban_reason=change.ban_reason,
    )


def book_traits_out(db: DbSession, troupe: Troupe) -> list[BookTraitOut]:
    """The troupe's changes to book traits, as players read them on the House rules tab."""
    return [book_trait_out(db, troupe, s, c) for s, c in book_traits.changes(db, troupe)]


@router.get("/book-traits")
def list_book_traits(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BookTraitsOut:
    """The troupe's changes to book traits, and the characters holding a trait it bans."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return BookTraitsOut(
        changes=book_traits_out(db, troupe),
        holders=[
            BannedHolderOut(
                character_id=h.character_id,
                character_name=h.character_name,
                splat=h.splat,
                category=h.category,
                name=h.name,
                detail=h.detail,
                excepted=h.excepted,
            )
            for h in book_traits.holders(db, troupe)
        ],
    )


@router.put("/book-traits")
def change_book_trait(
    troupe_id: uuid.UUID, body: BookTraitChange, db: DbSession, user: CurrentUser
) -> BookTraitOut:
    """Change a book trait in the troupe: ban it, with a reason, or lift the ban. Those
    who hold it keep it."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    if body.splat not in book_traits.splats_of(troupe):
        book_traits.no_such_trait()
    definition = book_traits.book_definition(db, body.splat, body.category, body.name)
    before = book_traits.change_of(db, troupe, body.splat, body.category, body.name)
    if body.banned is not None or body.ban_reason is not None:
        banned = before.banned if body.banned is None else body.banned
        reason = before.ban_reason if body.ban_reason is None else body.ban_reason
        book_traits.set_ban(
            db, user, troupe, body.splat, definition, body.category, banned=banned, reason=reason
        )
    db.commit()
    return book_trait_out(
        db,
        troupe,
        body.splat,
        book_traits.change_of(db, troupe, body.splat, body.category, body.name),
    )

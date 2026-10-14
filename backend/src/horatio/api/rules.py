"""The rules a character plays by: categories, the trait catalogue, and house rules."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import NoResultFound

from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe
from horatio.rules.store import read_troupe_rules

router = APIRouter(prefix="/rules", tags=["rules"])


class CategoryOut(BaseModel):
    key: str
    name: str
    group: str
    rated: bool
    max_rating: int | None


class TraitOut(BaseModel):
    category: str
    name: str
    description: str | None
    page_reference: str | None
    # A merit or flaw is always bought at this rating.
    fixed_rating: int | None
    # Text from a house rule for this trait in the troupe asked about.
    house_rule: str | None
    # For a clan: its in-clan disciplines.
    in_clan: list[str] | None


class CatalogueOut(BaseModel):
    splat: str
    name: str
    categories: list[CategoryOut]
    traits: list[TraitOut]


@router.get("/{splat}")
def catalogue(
    splat: str,
    db: DbSession,
    user: CurrentUser,
    category: str | None = None,
    troupe_id: uuid.UUID | None = None,
) -> CatalogueOut:
    """The rule set's categories and traits, with any house-rule text from `troupe_id`."""
    if troupe_id is not None and db.get(Troupe, troupe_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    try:
        rules = read_troupe_rules(db, splat, troupe_id)
    except NoResultFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No rules for {splat!r}.") from None
    house_text = {(r.category, r.trait): r.text for r in rules.house_rules if r.trait and r.text}
    return CatalogueOut(
        splat=rules.splat,
        name=rules.rule_set.name,
        categories=[
            CategoryOut(
                key=c.key, name=c.name, group=c.group, rated=c.rated, max_rating=c.max_rating
            )
            for c in rules.rule_set.categories.values()
        ],
        traits=[
            TraitOut(
                category=t.category,
                name=t.name,
                description=t.description,
                page_reference=t.page_reference,
                fixed_rating=t.properties.get("rating"),
                house_rule=house_text.get((t.category, t.name)),
                in_clan=t.properties.get("in_clan"),
            )
            for t in sorted(rules.rule_set.traits.values(), key=lambda t: (t.category, t.name))
            if category is None or t.category == category
        ],
    )

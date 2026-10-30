"""Character creation: the picks a new character places, and finishing creation."""

import uuid
from collections.abc import Iterable

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import clan_merits, creation, sheets
from horatio.api.sheets import TraitRefOut, players_character
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character
from horatio.permissions import visible_character
from horatio.rules.splats import clan_choice

router = APIRouter(prefix="/characters/{character_id}/creation", tags=["creation"])


class PickedTrait(BaseModel):
    name: str
    detail: str
    # The pick's rating, or the points it used.
    pick: int
    # False when the pick no longer meets its pool's restriction: a starting dot on
    # a discipline that is no longer in-clan. It is kept, but must move to finish.
    fits: bool = True
    # What leaves it without a free dot, if that is why it does not fit (Inept).
    because: list[TraitRefOut] = []
    # The traits that make this trait free without the pick (Personal Cult for Herd), so
    # the pick can go elsewhere. Empty when the pick is still worth its dots.
    freed_by: list[TraitRefOut] = []


class WithoutDot(BaseModel):
    """A trait of a restricted pool that takes no pick, though it may be in-clan."""

    name: str
    because: list[TraitRefOut]


class PoolOut(BaseModel):
    category: str
    category_name: str
    # The picks' rating; 0 for a budget of points.
    rating: int
    kind: str  # picks | points
    allowed: int
    used: int
    remaining: int
    # A fact each trait must have to take a pick here, such as "in_clan".
    restriction: str | None
    # With a restriction, the traits that meet it now (the in-clan disciplines).
    options: list[str] | None = None
    # Traits that take no pick here, and why: Inept's discipline, or the extra in-clan
    # discipline of a merit (no free dot, p. 248). Some are among `options`.
    without_dot: list[WithoutDot] = []
    # For a rating the rules no longer give picks at (allowed 0, with picks still on
    # it): the traits held that took it away, such as Thin Blooded.
    because: list[TraitRefOut] = []
    traits: list[PickedTrait]


class GivenOut(BaseModel):
    """A trait held without a creation pick, because a merit gives it: it cannot take one."""

    category: str
    name: str
    detail: str
    rating: int
    because: list[TraitRefOut]


class PathStart(BaseModel):
    """A Morality that starts lower because a Path merit was bought in creation."""

    category: str
    # The Path, and the merit that converted Humanity to it.
    name: str
    rating: int
    because: list[TraitRefOut]
    page: str | None = None


class StepNeed(BaseModel):
    # The category whose step must meet it, such as "backgrounds".
    step: str
    message: str


class BudgetChange(BaseModel):
    """What changes a category's starting picks: the merits and flaws held that its
    creation rules depend on (Thin Blooded, for the starting disciplines)."""

    category: str
    because: list[TraitRefOut]


class ClanMeritOut(BaseModel):
    """A merit the clan needs, from the merit points: a bloodline or rarity merit."""

    name: str
    points: int
    # Why the clan needs it, and the page saying so.
    why: str
    page: str | None = None
    # What the player chose with it, such as a Koldun's other path.
    detail: str = ""


class ShortfallOut(BaseModel):
    """Restricted picks with fewer traits to go on than there are picks, and why: "Only
    2 in-clan disciplines for 3 starting picks: …"."""

    category: str
    restriction: str
    picks: int
    options: list[str]
    message: str


class ClanChoiceOut(BaseModel):
    """An in-clan discipline the clan leaves to its player (Angelis Ater: Potence,
    Presence or Obfuscate), kept as the clan's detail."""

    clan: str
    choices: list[str]
    chosen: str | None
    page: str | None


class CreationOut(BaseModel):
    complete: bool
    pools: list[PoolOut]
    # The merits the clan needs, held from the merit points: not among the merit pool's
    # picks (`traits`), though their points are in its `used`.
    clan_merits: list[ClanMeritOut] = []
    # Whether the setting says how rare the clan is, so the rarity merits come with
    # the clan rather than being picked.
    rarity_known: bool = False
    # Paths whose Morality starts lower than Humanity's 5, for the merits bought now.
    path_starts: list[PathStart] = []
    budget_changes: list[BudgetChange] = []
    # Traits in the categories that take picks which merits give, with no pick of their own.
    given: list[GivenOut] = []
    # What the sheet must have before the wizard moves on from a step.
    needs: list[StepNeed]
    # Restricted picks that cannot all be placed as things stand, and why.
    shortfalls: list[ShortfallOut] = []
    # The clan's in-clan choice, for a clan that leaves one to its player.
    clan_choice: ClanChoiceOut | None = None


class Pick(BaseModel):
    category: str
    name: str
    detail: str = Field(default="", max_length=200)
    # The pick to use; ignored for merits and flaws, which use their point value.
    rating: int = Field(default=1, ge=1)


class CategoryPick(BaseModel):
    name: str
    detail: str = Field(default="", max_length=200)
    # Ignored for merits and flaws, which use their point value.
    rating: int = Field(default=1, ge=1)


class CategoryPicks(BaseModel):
    picks: list[CategoryPick]


class Unpick(BaseModel):
    category: str
    name: str
    detail: str = ""


def refs(found: Iterable[tuple[str, str]]) -> list[TraitRefOut]:
    return [TraitRefOut(category=c, name=n) for c, n in dict.fromkeys(found)]


def creation_out(db: DbSession, character: Character) -> CreationOut:
    catalogue = creation.rules_for(db, character).rule_set.categories
    fits = creation.fitting(db, character)
    clan = clan_merits.held(db, character)
    details = {
        r.definition.name: r.trait.detail
        for r in sheets.sheet_rows(db, character)
        if r.category.key == "merits" and r.definition.name in clan.names
    }
    freed = creation.freed_picks(db, character)
    needs = [
        StepNeed(step=v.check.step, message=v.message)
        for v in sheets.sheet_violations(db, character)
        if v.check.step is not None and v.check.strength in ("refuse", "complete")
    ]

    def pool_out(p: creation.Pool) -> PoolOut:
        return PoolOut(
            category=p.category,
            category_name=catalogue[p.category].name,
            rating=p.rating,
            kind=p.kind,
            allowed=p.allowed,
            used=p.used,
            remaining=p.remaining,
            restriction=p.restriction,
            options=creation.options(db, character, p, fits),
            without_dot=[
                WithoutDot(name=name, because=refs(by))
                for name, by in creation.without_dot(db, character, p, fits).items()
            ],
            because=refs(p.because),
            traits=[
                PickedTrait(
                    name=r.definition.name,
                    detail=r.trait.detail,
                    pick=r.trait.creation_pick or 0,
                    fits=fits(p, r.definition.name, r.trait.detail),
                    because=refs(fits.without_dot(p, r.definition.name, r.trait.detail))
                    if p.restriction
                    else [],
                    freed_by=refs(freed.get(r.key, [])),
                )
                for r in p.traits
                if not (p.category == "merits" and r.definition.name in clan.names)
            ],
        )

    placed = creation.pools_with_strays(db, character)
    rules = creation.rules_for(db, character)
    choice = clan_choice(rules, [r.as_rules_trait() for r in creation.sheet_rows(db, character)])
    return CreationOut(
        shortfalls=[
            ShortfallOut(
                category=s.category,
                restriction=s.restriction,
                picks=s.picks,
                options=s.options,
                message=s.message,
            )
            for s in creation.shortfalls(db, character)
        ],
        clan_choice=ClanChoiceOut(
            clan=choice.clan, choices=list(choice.choices), chosen=choice.chosen, page=choice.page
        )
        if choice is not None
        else None,
        complete=character.creation_completed_at is not None,
        needs=list({(n.step, n.message): n for n in needs}.values()),
        pools=[pool_out(p) for p in sorted(placed, key=lambda p: (p.category, -p.rating))],
        clan_merits=[
            ClanMeritOut(
                name=m.name, points=m.points, why=m.why, page=m.page, detail=details[m.name]
            )
            for m in clan.merits
        ],
        rarity_known=clan.rarity_known,
        budget_changes=[
            BudgetChange(category=category, because=refs(because))
            for category, because in creation.budget_changes(db, character).items()
        ],
        given=[
            GivenOut(
                category=g.category,
                name=g.name,
                detail=g.detail,
                rating=g.rating,
                because=refs(g.because),
            )
            for g in creation.given_traits(
                db, character, sorted({p.category for p in placed if p.kind == "picks"})
            )
        ],
        path_starts=[
            PathStart(
                category=s.category,
                name=s.name,
                rating=s.rating,
                because=refs([s.because]),
                page=s.page,
            )
            for s in creation.path_starts(db, character)
        ],
    )


@router.get("")
def read_creation(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CreationOut:
    return creation_out(db, visible_character(db, user, character_id))


@router.put("/picks")
def place_pick(
    character_id: uuid.UUID, body: Pick, db: DbSession, user: CurrentUser
) -> CreationOut:
    character = players_character(db, user, character_id)
    with sheets.checked(db, character, user):
        creation.place_pick(db, user, character, body.category, body.name, body.detail, body.rating)
    db.commit()
    return creation_out(db, character)


@router.put("/categories/{category}")
def set_category_picks(
    character_id: uuid.UUID, category: str, body: CategoryPicks, db: DbSession, user: CurrentUser
) -> CreationOut:
    """Replace every creation pick in one category at once: one step of the wizard."""
    character = players_character(db, user, character_id)
    with sheets.checked(db, character, user):
        creation.set_category_picks(
            db,
            user,
            character,
            category,
            [creation.PickSpec(name=p.name, rating=p.rating, detail=p.detail) for p in body.picks],
        )
    db.commit()
    return creation_out(db, character)


@router.post("/picks/remove")
def remove_pick(
    character_id: uuid.UUID, body: Unpick, db: DbSession, user: CurrentUser
) -> CreationOut:
    character = players_character(db, user, character_id)
    # Taking a pick back takes what it granted with it (a Path merit's Morality).
    with sheets.checked(db, character, user):
        creation.remove_pick(db, user, character, body.category, body.name, body.detail)
    db.commit()
    return creation_out(db, character)


@router.post("/complete")
def complete(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CreationOut:
    character = players_character(db, user, character_id)
    creation.complete(db, user, character)
    db.commit()
    return creation_out(db, character)

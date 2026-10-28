"""A cart of sheet changes, spent together: all of them, or none.

A player gathers raises, lowers, new traits, swaps and creation picks on the
Sheet tab, and spends them in one go. Each change is made by the same code as
making it alone (`sheets.set_trait`, `sheets.change_choice`, the creation
picks), in order, as if the earlier ones had been made, so it costs the same
either way and keeps its own XP entry. A refused change is rolled back to its
own savepoint and the rest are still tried, so every refusal is found at once;
the caller then keeps all of them or none.

What a change costs, and whether it can be made at all (the XP, the troupe's
limits, traits chosen only during creation), is judged as it is made. The
sheet's checks are judged once, on the sheet the whole cart ends with: a cart
may add a technique before raising the discipline it needs.

Changing Generation before a home troupe accepts the character reprices what
was bought since creation (horatio.repricing): the line's cost includes it,
and says which purchases it repriced.

A line can be asked as an exception (horatio.trait_exceptions): the checks its
trait breaks on the finished sheet are set aside for it rather than refusing
it, and it waits on the home troupe's staff; asked free, it costs nothing.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import creation, free_choices, repricing, sheets, trait_exceptions
from horatio.models import Approval, Character, CharacterTrait, User
from horatio.rules.model import FreeChoice, SheetTrait
from horatio.sheets import TraitKey
from horatio.trait_exceptions import Ask


@dataclass(frozen=True)
class SetRating:
    """Add a trait, change its rating, or (at 0) remove it, as `PUT /traits`."""

    category: str
    name: str
    detail: str
    rating: int | None
    # The rating the cart was made from: refused if the sheet has moved on since.
    from_rating: int | None = None
    teacher: str = ""
    # Asked of the home troupe's staff as an exception to the rules it breaks.
    exception: Ask | None = None
    # For a merit that gives free traits the player chooses: their choices, made with it.
    picks: tuple[FreeChoice, ...] = ()


@dataclass(frozen=True)
class Swap:
    """Swap a focus (or another swappable choice) for another, as `POST /traits/change`."""

    category: str
    from_name: str
    to_name: str


@dataclass(frozen=True)
class Pick:
    """Place a creation pick."""

    category: str
    name: str
    detail: str
    rating: int


@dataclass(frozen=True)
class Unpick:
    """Take a creation pick back."""

    category: str
    name: str
    detail: str


Change = SetRating | Swap | Pick | Unpick


@dataclass(frozen=True)
class Outcome:
    # XP the change spends (negative: refunds). For a refused change, what it
    # would have cost where that can be told, else None.
    cost: int | None
    # Why it was refused; None if it went through.
    refused: str | None = None
    # It went through but waits on the home troupe, like a discipline dot.
    needs_approval: bool = False
    # Asked as an exception: the checks it breaks, set aside if staff approve.
    breaks: tuple[str, ...] = ()
    # Earlier purchases it repriced, in its cost.
    repriced: tuple[repricing.Repriced, ...] = ()
    # A power a merit opened past a check: "Hard as Steel: 20 XP".
    because: str | None = None


def planned(sheet: Sequence[SheetTrait], changes: Sequence[Change]) -> list[SheetTrait]:
    """The sheet as the changes would leave it, worked out without making them, for
    asking what the character could take next. Only the ratings and swaps are
    followed: not what the changes cost, whether they would be refused, or what a
    new merit's grants would give. Taking a creation pick back is left out, as the
    pick's dots may be bought ones too."""
    traits = list(sheet)

    def at(category: str, name: str, detail: str | None = None) -> int | None:
        return next(
            (
                i
                for i, t in enumerate(traits)
                if t.category == category
                and t.name == name
                and (detail is None or t.detail == detail)
            ),
            None,
        )

    for change in changes:
        if isinstance(change, SetRating | Pick):
            i = at(change.category, change.name, change.detail)
            if isinstance(change, SetRating) and change.rating == 0:
                if i is not None:
                    del traits[i]
            elif i is None:
                traits.append(
                    SheetTrait(
                        category=change.category,
                        name=change.name,
                        rating=change.rating,
                        detail=change.detail,
                    )
                )
            elif change.rating is not None:
                held = traits[i]
                rating = change.rating
                if isinstance(change, Pick):
                    rating = max(rating, held.rating or 0)
                traits[i] = replace(held, rating=rating, free_rating=min(held.free_rating, rating))
        elif isinstance(change, Swap):
            i = at(change.category, change.from_name)
            if i is not None:
                traits[i] = replace(traits[i], name=change.to_name)
    return traits


def held_rating(db: Session, character: Character, change: SetRating) -> int:
    definition, _ = sheets.find_definition(db, character, change.category, change.name)
    rating = db.scalar(
        select(CharacterTrait.rating).where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == definition.id,
            CharacterTrait.detail == change.detail,
        )
    )
    return rating or 0


def make(db: Session, user: User, character: Character, change: Change) -> sheets.Change | None:
    """Make one change, exactly as its own endpoint does; one asked as an exception
    as the player cannot alone."""
    if isinstance(change, SetRating):
        asked = change.exception
        if asked is not None:
            trait_exceptions.can_ask(character)
            if change.rating is None or change.rating <= held_rating(db, character, change):
                raise sheets.unprocessable("An exception is for adding a trait or raising one.")
        if change.from_rating is not None:
            now = held_rating(db, character, change)
            if now != change.from_rating:
                raise sheets.conflict(
                    f"{change.name} is at {now} now, not {change.from_rating}: "
                    "the sheet has changed since this went in the cart."
                )
        with sheets.checked(db, character, user, rules=False):
            made = sheets.set_trait(
                db,
                user,
                character,
                change.category,
                change.name,
                change.detail,
                change.rating,
                teacher=change.teacher,
                free=asked.reason if asked and asked.free else None,
                by_exception="asked" if asked else None,
            )
            if change.picks and change.rating:
                free_choices.set_choices(
                    db, character, change.category, change.name, change.detail, change.picks
                )
            return made
    elif isinstance(change, Swap):
        with sheets.checked(db, character, user, rules=False):
            sheets.change_choice(
                db, user, character, change.category, change.from_name, change.to_name
            )
    elif isinstance(change, Pick):
        with sheets.checked(db, character, user, rules=False):
            creation.place_pick(
                db, user, character, change.category, change.name, change.detail, change.rating
            )
    else:
        creation.remove_pick(db, user, character, change.category, change.name, change.detail)
    return None


def would_cost(db: Session, character: Character, change: Change) -> int | None:
    """What a refused change would have cost, where that can be told."""
    try:
        if isinstance(change, SetRating):
            quote, _ = sheets.quote_change(
                db, character, change.category, change.name, change.detail, change.rating
            )
            return quote.cost if quote else 0
        if isinstance(change, Swap):
            _, category = sheets.find_definition(db, character, change.category, change.from_name)
            return category.change_cost
    except HTTPException:
        return None
    return 0


def waiting(db: Session, character: Character) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.character_id == character.id,
                Approval.status == "pending",
                Approval.kind.in_(sheets.HELD_KINDS),
            )
        )
        or 0
    )


@dataclass(frozen=True)
class Step:
    """What one change did to the sheet's traits."""

    # Traits it added.
    brought: frozenset[TraitKey] = frozenset()
    # Traits it added, took away or changed the rating of.
    touched: frozenset[TraitKey] = frozenset()


def held_traits(db: Session, character: Character) -> dict[TraitKey, int | None]:
    return {r.key: r.trait.rating for r in sheets.sheet_rows(db, character)}


def step(before: dict[TraitKey, int | None], after: dict[TraitKey, int | None]) -> Step:
    return Step(
        brought=frozenset(after.keys() - before.keys()),
        touched=frozenset(
            key
            for key in before.keys() | after.keys()
            if key not in before or key not in after or before[key] != after[key]
        ),
    )


def culprit(problem: sheets.Problem, steps: Sequence[Step]) -> int:
    """The change a problem with the finished sheet is put down to: the last to
    bring in the trait it is about, else the last to touch that trait, else the
    last to touch what the broken check looks at, else the last to change anything."""

    def about(key: TraitKey) -> bool:
        return key[0] == problem.category and (
            problem.name is None or key[1:] == (problem.name, problem.detail)
        )

    def looked_at(key: TraitKey) -> bool:
        return bool({(key[0], key[1]), (key[0], None)} & problem.looks_at)

    tests: list[Callable[[Step], bool]] = [
        lambda s: any(about(k) for k in s.brought),
        lambda s: any(about(k) for k in s.touched),
        lambda s: any(looked_at(k) for k in s.touched),
        lambda s: bool(s.touched),
    ]
    for test in tests:
        found = [i for i, s in enumerate(steps) if test(s)]
        if found:
            return found[-1]
    return len(steps) - 1


def apply_changes(
    db: Session, user: User, character: Character, changes: Sequence[Change]
) -> list[Outcome]:
    """Make each change in turn, each as if the ones before it had been made.
    A refused change is undone and the rest still tried. Then the sheet they end
    with is checked against the one they started from, and each check it breaks
    refuses the change it is put down to. Nothing is committed: the caller keeps
    the lot, or rolls it back if any was refused."""
    start = sheets.sheet_state(db, character)
    outcomes: list[Outcome] = []
    steps: list[Step] = []
    # What each line given free would have cost.
    normal_costs: dict[int, int | None] = {}
    for i, change in enumerate(changes):
        balance = sheets.xp_balance(db, character)
        held = waiting(db, character)
        traits_before = held_traits(db, character)
        savepoint = db.begin_nested()
        try:
            made = make(db, user, character, change)
            db.flush()
        except HTTPException as error:
            savepoint.rollback()
            db.expire_all()
            refused = str(error.detail)
            outcomes.append(Outcome(cost=would_cost(db, character, change), refused=refused))
            steps.append(Step())
            continue
        savepoint.commit()
        if made is not None:
            normal_costs[i] = made.normal_cost if made.quote is None else made.quote.cost
        outcomes.append(
            Outcome(
                cost=balance - sheets.xp_balance(db, character),
                needs_approval=waiting(db, character) > held,
                repriced=made.repriced if made is not None else (),
                because=made.quote.opening.because
                if made is not None and made.quote is not None and made.quote.opening is not None
                else None,
            )
        )
        steps.append(step(traits_before, held_traits(db, character)))
    if character.kind != "pc":
        return outcomes
    asking = {
        (c.category, c.name, c.detail): i
        for i, c in enumerate(changes)
        if isinstance(c, SetRating) and c.exception and outcomes[i].refused is None
    }
    judged = sheets.broken_since(db, user, character, start, creation_only=False, excepting=asking)
    problems: dict[int, list[sheets.Problem]] = {}
    for problem in judged.refused:
        problems.setdefault(culprit(problem, steps), []).append(problem)
    for i, found in problems.items():
        reasons = [outcomes[i].refused, sheets.refusal(found)]
        outcomes[i] = replace(outcomes[i], refused=" ".join(r for r in reasons if r))
    for problem in judged.reviewed:
        i = culprit(problem, steps)
        outcomes[i] = replace(outcomes[i], needs_approval=True)
    for key, i in asking.items():
        asked = changes[i]
        assert isinstance(asked, SetRating) and asked.exception is not None
        broken = judged.excepted.get(key, [])
        if trait_exceptions.ask(
            db, user, character, key, asked.exception, broken, start, normal_costs.get(i)
        ):
            outcomes[i] = replace(
                outcomes[i],
                needs_approval=True,
                breaks=tuple(c["message"] for c in trait_exceptions.checks_of(broken)),
            )
    return outcomes

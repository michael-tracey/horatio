"""Trying a house merit or flaw on a sheet before saving it: "A character with this
would…". Its blocks (horatio.rules.house_effects) are run against a sample sheet,
a new character's or one of the troupe's own, by the troupe's rules with the merit
as staff are making it and without it; what differs is what it does there: free
dots, maximums, prices, in-clan disciplines and checks; the Play View's pools, its
switch and its uses a game; and its downtime actions and feeding. Nothing is saved."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import house_traits, reference, sheets
from horatio.feeding import tracked
from horatio.models import Character, HouseTrait, Troupe
from horatio.rules.allowance import allowance
from horatio.rules.checks import Context, violations
from horatio.rules.feeding import HERD, basis
from horatio.rules.grants import Effects, GrantData, effects, raised_by
from horatio.rules.house_effects import EXTRA_IN_CLAN, Compiled, either, plural
from horatio.rules.model import FreeChoice, RuleSetData, SheetTrait, TroupeRules
from horatio.rules.pricing import PricingError, fixed_rating, purchase_cost
from horatio.rules.splats import SPLATS
from horatio.sheets import conflict

# How many traits a block is tried on, at most.
SHOWN = 6


@dataclass(frozen=True)
class CheckLine:
    text: str
    met: bool
    strength: str


@dataclass(frozen=True)
class Preview:
    # Who it was tried on: "a new character", or the character's name.
    sample: str
    # What the player was taken to choose, where the merit lets them: "Herd".
    choosing: str
    summary: str
    changes: list[str]
    checks: list[CheckLine]
    # The blocks that cannot be used, and why: (index, message).
    problems: list[tuple[int, str]]
    # The characters it can be tried on.
    samples: list[Character]


def samples(db: Session, troupe: Troupe, splat: str) -> list[Character]:
    """The troupe's own characters of the splat: home, being built for it, its NPCs."""
    return list(
        db.scalars(
            select(Character)
            .where(
                Character.splat == splat,
                Character.status == "active",
                or_(
                    Character.home_troupe_id == troupe.id,
                    (Character.building_troupe_id == troupe.id)
                    & Character.home_troupe_id.is_(None),
                ),
            )
            .order_by(Character.name)
        )
    )


def preview(
    db: Session,
    troupe: Troupe,
    spec: house_traits.Spec,
    house: HouseTrait | None,
    character: Character | None,
) -> Preview:
    trial = house_traits.trial(db, troupe, spec, house)
    draft, compiled = trial.draft, trial.compiled
    merit = (draft.category, draft.name)
    if character is not None:
        if sheets.rules_troupe(character) != troupe.id or character.splat != spec.splat:
            raise conflict(f"{character.name} is not one of {troupe.name}'s {spec.splat}s.")
        rows = sheets.sheet_rows(db, character)
        held = next(
            (
                r.trait
                for r in rows
                if house is not None and r.definition.id == house.trait_definition_id
            ),
            None,
        )
        sheet = [
            r.as_rules_trait()
            for r in rows
            if house is None or r.definition.id != house.trait_definition_id
        ]
        detail = held.detail if held is not None else ""
        label = character.name
    else:
        sheet = [
            SheetTrait(t.category, t.name, t.rating, t.rating or 0)
            for t in trial.with_it.starting_traits()
        ]
        detail, label = "", "a new character"

    # What the player would choose, where the merit lets them: what the sample chose,
    # else the first on the list.
    picks: list[FreeChoice] = []
    for grant in compiled.grants:
        options = list(grant.target.get("choose") or [])
        if not options:
            continue
        if grant.kind == "free_choices":
            assert grant.picks is not None
            places = grant.picks["places"]
            picks += [
                FreeChoice(grant=grant.key, name=n, amount=a)
                for n, a in zip(options, places, strict=False)
            ]
        elif detail not in options:
            detail = options[0]
    choosing = either([*([detail] if detail else []), *(p.name for p in picks)], "and")
    with_it = [
        *sheet,
        SheetTrait(
            draft.category,
            draft.name,
            fixed_rating(trial.with_it, sheet, *merit) or draft.points,
            0,
            detail,
            choices=tuple(picks),
        ),
    ]
    before = effects(trial.without.rule_set.grants, sheet, trial.without.rule_set)
    after = effects(trial.with_it.rule_set.grants, with_it, trial.with_it.rule_set)
    # The sheets as they would be held, with what their grants give.
    was = granted(trial.without, sheet, before)
    now = granted(trial.with_it, with_it, after)

    changes = (
        dots_given(was, now, [k for k, givers in after.givers.items() if merit in givers])
        + maximums(trial.with_it, before, after, compiled.grants)
        + prices(trial, [t for _, t in was.values()], [t for _, t in now.values()], compiled.grants)
        + in_clan(trial, sheet, compiled.in_clan)
    )
    with_it = [t for _, t in now.values()]
    held_before = [t for _, t in was.values()]
    changes += at_a_game(trial, held_before, with_it, compiled) + between_games(
        trial, held_before, with_it, compiled, feeding_tracked=tracked(troupe)
    )
    native = frozenset(SPLATS[spec.splat].in_clan(trial.with_it, with_it))
    context = Context(
        accepted=character is not None and character.home_troupe_id is not None,
        finished=character is not None and character.creation_completed_at is not None,
        npc=character is not None and character.kind == "npc",
        in_clan=native,
        native=native,
        kinds=trial.with_it.rule_set.kinds,
        tags=trial.with_it.rule_set.tags,
    )
    broken = {v.check.key for v in violations(compiled.checks, with_it, context)}
    return Preview(
        sample=label,
        choosing=choosing,
        summary=draft.summary,
        changes=changes,
        checks=[CheckLine(c.message, c.key not in broken, c.strength) for c in compiled.checks],
        problems=[(p.index, p.message) for p in compiled.problems],
        samples=samples(db, troupe, spec.splat),
    )


def named(category: str, name: str, detail: str) -> str:
    shown = f"{name}: {detail}" if detail else name
    return f"{shown} health levels" if category == "health_levels" else shown


Key = tuple[str, str, str]


def granted(
    rules: TroupeRules, sheet: Sequence[SheetTrait], found: Effects
) -> dict[Key, tuple[int, SheetTrait]]:
    """Each trait as horatio.sheets.apply_grants would hold it under these grants,
    with how many dots bought there the grants would make free (and refund)."""
    held: dict[Key, tuple[int, SheetTrait]] = {
        (t.category, t.name, t.detail): (0, t) for t in sheet
    }
    keys = (
        set(found.added)
        | set(found.free_up_to)
        | {k for k, (_, t) in held.items() if t.granted_rating}
    )
    for key in keys:
        trait = held[key][1] if key in held else SheetTrait(key[0], key[1], 0, 0, key[2])
        base_rating = (trait.rating or 0) - trait.granted_rating
        base_free = trait.free_rating - trait.granted_rating
        free_up_to = found.free_up_to.get(key, 0)
        # A merit is given whole, at its value.
        whole = fixed_rating(rules, sheet, key[0], key[1]) if free_up_to else None
        free_up_to = whole if whole is not None else free_up_to
        given = found.added.get(key, 0) + max(0, free_up_to - base_free)
        bought = max(0, min(base_rating, free_up_to) - base_free)
        held[key] = (
            bought,
            replace(
                trait,
                rating=max(0, base_rating - bought + given),
                free_rating=max(0, base_free + given),
                granted_rating=given,
            ),
        )
    return held


def dots_given(
    was: dict[Key, tuple[int, SheetTrait]],
    now: dict[Key, tuple[int, SheetTrait]],
    keys: Sequence[Key],
) -> list[str]:
    """The dots its grants give, and take away."""
    found: list[str] = []
    for key in keys:
        bought_before, before = was.get(key, (0, SheetTrait(key[0], key[1], 0, 0, key[2])))
        bought, after = now[key]
        rating, free = after.rating or 0, after.free_rating
        line = f"{named(*key)}: {before.rating or 0} → {rating}"
        if key[0] in ("merits", "flaws"):
            line = f"{named(*key)}: given free"
        elif free and rating > 0:
            line += (
                f", {free} of them free"
                if free < rating
                else (", all free" if rating > 1 else ", free")
            )
        if bought > bought_before:
            line += f"; the {bought} already bought there would be refunded"
        found.append(line + ".")
    return found


def maximums(
    rules: TroupeRules, before: Effects, after: Effects, grants: Sequence[GrantData]
) -> list[str]:
    found: list[str] = []
    for grant in grants:
        if grant.kind != "raise_max":
            continue
        target = grant.target
        category = rules.rule_set.categories[target["category"]]
        usual = category.usual_max or category.max_rating
        if usual is None:
            continue
        detail = target.get("detail") or ""
        for name in target.get("names") or [None]:
            was = usual + raised_by(before, category.key, name or "", detail)
            now = usual + raised_by(after, category.key, name or "", detail)
            what = named(category.key, name, detail) if name else f"All {category.name.lower()}"
            found.append(f"{what}: up to {now} (otherwise {was}).")
    return found


def prices(
    trial: house_traits.Trial,
    sheet: Sequence[SheetTrait],
    with_it: Sequence[SheetTrait],
    grants: Sequence[GrantData],
) -> list[str]:
    """The next dot's price of each trait its blocks price, with it and without."""
    rule_set = trial.with_it.rule_set
    found: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for grant in grants:
        if grant.kind not in ("cost_percent", "price_in_clan", "price_out_of_clan"):
            continue
        target = grant.target
        category, detail = target["category"], target.get("detail") or ""
        names = list(target.get("names") or [])
        if not names:
            # A whole category: tried on what the sheet holds of it, else on its first.
            names = [t.name for t in sheet if t.category == category] or [
                n for c, n in sorted(rule_set.traits) if c == category
            ][:1]
        for name in names[:SHOWN]:
            key = (category, name, detail)
            if key in seen:
                continue
            seen.add(key)
            held = next(
                (t for t in sheet if (t.category, t.name, t.detail) == key),
                SheetTrait(category, name, 0, 0, detail),
            )
            was = next_dot(trial.without, sheet, held)
            now = next_dot(trial.with_it, with_it, held)
            line = f"{named(category, name, detail)}: dot {(held.rating or 0) + 1} costs {now}"
            found.append(
                line + (f" (otherwise {was})." if now != was else ", the same as without it.")
            )
    return found


def next_dot(rules: TroupeRules, sheet: Sequence[SheetTrait], held: SheetTrait) -> str:
    try:
        cost = purchase_cost(rules, sheet, held, (held.rating or 0) + 1).cost
    except PricingError:
        return "nothing: it cannot be bought"
    return f"{cost} XP"


def in_clan(
    trial: house_traits.Trial, sheet: Sequence[SheetTrait], names: Sequence[str]
) -> list[str]:
    if not names:
        return []
    splat = SPLATS[trial.with_it.splat]
    now = sorted(set(splat.in_clan(trial.without, sheet)))
    chosen = [t.name for t in sheet if t.category == EXTRA_IN_CLAN]
    held = f"In-clan now: {', '.join(now)}" if now else "No in-clan disciplines yet"
    extra = f" (with {', '.join(chosen)} already added)" if chosen else ""
    return [f"{held}{extra}; one more could be chosen from {either(list(names))}."]


def pools_of(
    rule_set: RuleSetData, sheet: Sequence[SheetTrait]
) -> tuple[dict[str, reference.TestPool], reference.Worked]:
    """The Play View's pools for the sheet, by key, and what changes them."""
    made = reference.Sheet.of(sheet, rule_set)
    worked = reference.work_out(made, reference.technique_bases(rule_set))
    found = reference.pools(made, worked.effects, worked.hurts, worked.switches)
    return {p.key: p for p in found}, worked


def switched_total(pool: reference.TestPool, key: str) -> int:
    """The pool's total with one switch on, as the Play View works it out
    (frontend/src/pages/play/pools.ts)."""
    now = [s for s in pool.switched if s.switch == key]
    total = pool.total + sum(s.value for s in now if not s.attribute)
    for part in pool.parts:
        changes = [s for s in now if s.attribute == part.label]
        if not changes:
            continue
        value = part.value + sum(c.value for c in changes)
        for c in changes:
            if c.most is not None:
                value = min(value, c.most)
        total += max(0, value) - part.value
    return total


def at_a_game(
    trial: house_traits.Trial,
    sheet: Sequence[SheetTrait],
    with_it: Sequence[SheetTrait],
    compiled: Compiled,
) -> list[str]:
    """What it changes on the Play View: its pools, its switch, its uses a game."""
    properties = compiled.properties
    if not properties:
        return []
    before, was = pools_of(trial.without.rule_set, sheet)
    after, worked = pools_of(trial.with_it.rule_set, with_it)
    found: list[str] = []
    for key, pool in after.items():
        old = before.get(key)
        if old is None:
            continue
        also = " (and Willpower)" if pool.adds_willpower else ""
        if pool.total != old.total:
            found.append(f"{pool.name}: {old.total} → {pool.total}{also}.")
        had = {v.when for v in old.variants}
        for variant in pool.variants:
            if variant.when not in had:
                when = variant.when[:1].lower() + variant.when[1:]
                found.append(f"{pool.name}: {variant.total} {when}{also}.")
    # A skill's change a pool above already shows is not said again.
    notes = set(reference.other_notes(was.effects, before.keys()))
    found += [
        f"{n}." for n in reference.other_notes(worked.effects, after.keys()) if n not in notes
    ]
    active = properties.get("active")
    switch = next((s for s in worked.switches if active and s.key == active["key"]), None)
    if switch is not None:
        found.append(f"A switch on the Play View, {switch.name}: {', '.join(switch.changes)}.")
        on = [
            f"{p.name} {p.total} → {now}"
            for p in after.values()
            if (now := switched_total(p, switch.key)) != p.total
        ]
        if on:
            found.append(f"With it on: {', '.join(on)}.")
    uses = properties.get("uses_per_game")
    if uses:
        found.append(f"{plural(uses, 'use')} a game, under Uses this game on the Play View.")
    return found


def between_games(
    trial: house_traits.Trial,
    sheet: Sequence[SheetTrait],
    with_it: Sequence[SheetTrait],
    compiled: Compiled,
    *,
    feeding_tracked: bool = True,
) -> list[str]:
    """What it changes in a downtime: actions of each kind, and feeding, if the troupe
    tracks it."""
    found: list[str] = []
    if compiled.allowance_rules:
        was, _ = allowance(trial.without, sheet)
        now, _ = allowance(trial.with_it, with_it)
        kinds = trial.with_it.action_kinds()
        for kind in dict.fromkeys(r.action_kind for r in compiled.allowance_rules):
            name = kinds[kind].name
            found.append(f"{name}s each downtime: {was.get(kind, 0)} → {now.get(kind, 0)}.")
    if compiled.feeding_modifiers and not feeding_tracked:
        found.append("Nothing when feeding: this troupe doesn't track feeding.")
    elif compiled.feeding_modifiers:
        before, after = basis(trial.without, sheet), basis(trial.with_it, with_it)
        if after["clan"] is None and not after["modifiers"]:
            found.append("Nothing when feeding: this sheet does not feed between games.")
            return found
        modifier = compiled.feeding_modifiers[0]
        if modifier.amount:
            more = "more" if modifier.amount > 0 else "fewer"
            actions = plural(modifier.amount, "feeding action").replace(" ", f" {more} ", 1)
            found.append(f"Feeding: {actions} needed each downtime.")
        herd = max((t.rating or 0 for t in with_it if (t.category, t.name) == HERD), default=0)
        factor = 1
        for m in before["modifiers"]:
            factor *= m["herd_factor"]
        if modifier.herd_factor != 1:
            stands, otherwise = herd * factor * modifier.herd_factor, herd * factor
            found.append(
                f"Herd {herd} would stand in for {stands} feeding actions (otherwise {otherwise})."
            )
        if modifier.always_half:
            found.append("No feeding would bring them above half Blood.")
    return found


def sample_character(db: Session, character_id: uuid.UUID | None) -> Character | None:
    if character_id is None:
        return None
    character = db.get(Character, character_id)
    if character is None:
        raise conflict("No such character.")
    return character

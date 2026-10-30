"""Quest requirements, structured so Horatio can check them against sheets (MET: VTM
Vol. II Issue 1, pp. 106-108; CONTEXT.md: Quest Requirement).

A requirement is one or more alternatives, any one of which meets it ("Medicine 3
or Science (Biology)"). Each alternative is one of:

- **trait**: a skill, attribute focus, background, merit, flaw, discipline, power,
  technique or ritual by name, at a rating, optionally with a specialisation
  ("Lore: Abyss", "Science (Biology)");
- **aspect**: a clan, bloodline or sect ("the support of an Anarch");
- **an expenditure**, used up when it meets the requirement:
  - **influence**: an Elite or Underworld action at a level, optionally in an area,
    which goes in the troupe's influence log;
  - **background**: background dots, recorded on the quest (Horatio does not track
    a background's monthly use);
  - **status**: a fleeting status trait, spent for good as the status rules spend
    one (horatio.play_status);
  - **pool**: Willpower or Blood, which comes off on the Play View;
  - **action**: a downtime action, owed to the next cycle (horatio.downtimes);
  - **item**: lending an item, recorded on the quest;
- **text**: words for what Horatio cannot check ("Access to Miles' journal").

Nothing here knows about quests beyond a purpose for the log, so a location's
requirements to acquire it can use the same alternatives.

`meets` says whether a sheet meets an alternative now (None when Horatio cannot
tell); `spend` uses up an expenditure for one character and says what it spent;
`give_back` undoes that.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy.orm import Session

from horatio import downtimes, influence, influence_log, play, play_status, reference, sect_status
from horatio.models import Character, HeldStatus, InfluenceEntry, OwedAction, Troupe, User
from horatio.sheets import SheetRow, conflict, lock_character, rules_for, sheet_rows

# The trait kinds a requirement can name, by the rule set's category keys. "focus"
# is any attribute focus; "power" a discipline power by name (horatio.reference).
TRAIT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "skills": ("skills",),
    "focus": ("focus_physicals", "focus_mentals", "focus_socials"),
    "backgrounds": ("backgrounds",),
    "merits": ("merits",),
    "flaws": ("flaws",),
    "disciplines": ("disciplines",),
    "power": (),
    "techniques": ("techniques",),
    "rituals": ("rituals", "sabbat_rituals"),
}
POOL_NAMES = {"willpower": "Willpower", "blood": "Blood"}


class TraitNeed(BaseModel):
    kind: Literal["trait"] = "trait"
    category: Literal[
        "skills",
        "focus",
        "backgrounds",
        "merits",
        "flaws",
        "disciplines",
        "power",
        "techniques",
        "rituals",
    ]
    name: str = Field(min_length=1, max_length=200)
    rating: int = Field(default=1, ge=0, le=10)
    specialization: str = Field(default="", max_length=200)


class AspectNeed(BaseModel):
    kind: Literal["aspect"] = "aspect"
    aspect: Literal["clan", "bloodline", "sect"]
    name: str = Field(min_length=1, max_length=200)


class InfluenceSpend(BaseModel):
    kind: Literal["influence"] = "influence"
    type: influence.InfluenceType
    level: int = Field(ge=1, le=10)
    area: str = Field(default="", max_length=200)


class BackgroundSpend(BaseModel):
    kind: Literal["background"] = "background"
    name: str = Field(min_length=1, max_length=200)
    dots: int = Field(ge=1, le=10)


class StatusSpend(BaseModel):
    kind: Literal["status"] = "status"
    # A fleeting status by name, or any one when empty.
    name: str = Field(default="", max_length=200)


class PoolSpend(BaseModel):
    kind: Literal["pool"] = "pool"
    pool: Literal["willpower", "blood"]
    amount: int = Field(ge=1, le=20)


class ActionSpend(BaseModel):
    kind: Literal["action"] = "action"
    # The action kind, such as general.
    action_kind: str = Field(default="general", max_length=100)


class ItemSpend(BaseModel):
    kind: Literal["item"] = "item"
    item: str = Field(min_length=1, max_length=200)


class TextNeed(BaseModel):
    kind: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=500)


Option = Annotated[
    TraitNeed
    | AspectNeed
    | InfluenceSpend
    | BackgroundSpend
    | StatusSpend
    | PoolSpend
    | ActionSpend
    | ItemSpend
    | TextNeed,
    Field(discriminator="kind"),
]
OPTIONS: TypeAdapter[list[Option]] = TypeAdapter(list[Option])
EXPENDITURES = frozenset({"influence", "background", "status", "pool", "action", "item"})


def parse(raw: Sequence[dict[str, Any]]) -> list[Option]:
    return OPTIONS.validate_python(list(raw))


def dump(options: Sequence[Option]) -> list[dict[str, Any]]:
    return [o.model_dump() for o in options]


def expends(option: Option) -> bool:
    return option.kind in EXPENDITURES


# --- words ---------------------------------------------------------------------------------


def label(option: Option) -> str:
    """As the troupe writes it: "Medicine 3", "Science (Biology)", "Expend Elite 6
    (High Society)"."""
    match option:
        case TraitNeed():
            special = f" ({option.specialization})" if option.specialization else ""
            rating = f" {option.rating}" if option.rating > 1 or not special else ""
            return f"{option.name}{special}{rating}"
        case AspectNeed():
            return f"{option.name} ({option.aspect})"
        case InfluenceSpend():
            area = f" ({option.area})" if option.area else ""
            return f"Expend {influence.TYPE_NAMES[option.type]} {option.level}{area}"
        case BackgroundSpend():
            return f"Expend {option.name} {option.dots}"
        case StatusSpend():
            return f"Expend {option.name} status" if option.name else "Expend a status trait"
        case PoolSpend():
            return f"Expend {option.amount} {POOL_NAMES[option.pool]}"
        case ActionSpend():
            kind = option.action_kind.replace("_", " ")
            return "Expend a downtime action" if kind == "general" else f"Expend a {kind} action"
        case ItemSpend():
            return f"Lend {option.item}"
        case TextNeed():
            return option.text


def requirement_label(options: Sequence[Option]) -> str:
    return " or ".join(label(o) for o in options)


# --- checking ------------------------------------------------------------------------------


def same(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def rating_of(rows: Sequence[SheetRow], categories: Sequence[str], name: str) -> int:
    return max(
        (
            r.trait.rating or 0
            for r in rows
            if r.category.key in categories and same(r.definition.name, name)
        ),
        default=0,
    )


def specialised(
    db: Session, character: Character, rows: Sequence[SheetRow], category: str, name: str, area: str
) -> bool:
    """Whether the character has `area` as a specialisation or field of the trait: its
    own detail ("Science: Biology"), or a trait in a category that specialises it
    (Lore's subjects, an Influence's areas), named or written in."""
    if any(
        r.category.key == category and same(r.definition.name, name) and same(r.trait.detail, area)
        for r in rows
    ):
        return True
    rule_set = rules_for(db, character).rule_set
    kinds = {
        c.key
        for c in rule_set.categories.values()
        if c.specializes
        and c.specializes.get("category") == category
        and same(c.specializes.get("name", ""), name)
    }
    return any(
        r.category.key in kinds and (same(r.definition.name, area) or same(r.trait.detail, area))
        for r in rows
    )


def power_level(name: str) -> tuple[str, int] | None:
    """A discipline power's discipline and dot, from the powers catalogue."""
    for discipline, powers in reference.catalogue().powers.items():
        for power in powers:
            if same(power["name"], name):
                return discipline, int(power["level"])
    return None


def meets_trait(
    db: Session, character: Character, rows: Sequence[SheetRow], need: TraitNeed
) -> bool:
    if need.category == "power":
        found = power_level(need.name)
        return found is not None and rating_of(rows, ("disciplines",), found[0]) >= found[1]
    categories = TRAIT_CATEGORIES[need.category]
    held = [r for r in rows if r.category.key in categories and same(r.definition.name, need.name)]
    if not held:
        return False
    # An unrated trait (a merit with no dots) counts as held at 1.
    if max(r.trait.rating or 0 for r in held) < need.rating and need.rating > 1:
        return False
    if not need.specialization:
        return True
    return any(
        specialised(db, character, rows, r.category.key, r.definition.name, need.specialization)
        for r in held
    )


def meets_aspect(rows: Sequence[SheetRow], need: AspectNeed) -> bool:
    if need.aspect == "sect":
        return any(r.category.key == "sect" and same(r.definition.name, need.name) for r in rows)
    for r in rows:
        if r.category.key != "clan":
            continue
        clan, _, bloodline = r.definition.name.partition(":")
        if need.aspect == "clan" and (same(clan, need.name) or same(r.definition.name, need.name)):
            return True
        if need.aspect == "bloodline" and bloodline and same(bloodline, need.name):
            return True
    return False


def influence_reach(
    db: Session, character: Character, rows: Sequence[SheetRow], need: InfluenceSpend
) -> bool:
    """Whether the character can take an action at this level (MET: VtM core, p. 512):
    its rating at least the level, or one less with a specialisation of the type
    (the area named, if there is one)."""
    rating = rating_of(rows, ("backgrounds",), influence.TRAITS[need.type])
    kind = influence.SPECIALIZATIONS[need.type]
    if need.area:
        special = any(
            r.category.key == kind
            and (same(r.definition.name, need.area) or same(r.trait.detail, need.area))
            for r in rows
        )
    else:
        special = any(r.category.key == kind for r in rows)
    return rating >= need.level or (special and rating + 1 >= need.level)


def fleeting(db: Session, character: Character, name: str) -> list[sect_status.Held]:
    """The fleeting status the character holds that could be spent: by name, or any."""
    return [
        h
        for h in sect_status.held(db, character)
        if h.type == "Fleeting" and (not name or same(h.name, name))
    ]


def pool_now(db: Session, character: Character, pool: str) -> int:
    """Willpower or Blood on the Play View now, or as the next game starts it."""
    game = play.current_game(db, character)
    if game is not None and pool in game.state:
        return int(game.state[pool])
    return int(play.limits(db, character, game).start()[pool])


def meets(db: Session, character: Character, option: Option) -> bool | None:
    """Whether the character's sheet meets the alternative now; None when Horatio
    cannot tell (words, an item to lend, a downtime action)."""
    rows = sheet_rows(db, character)
    match option:
        case TraitNeed():
            return meets_trait(db, character, rows, option)
        case AspectNeed():
            return meets_aspect(rows, option)
        case InfluenceSpend():
            return influence_reach(db, character, rows, option)
        case BackgroundSpend():
            return rating_of(rows, ("backgrounds",), option.name) >= option.dots
        case StatusSpend():
            return bool(fleeting(db, character, option.name))
        case PoolSpend():
            return pool_now(db, character, option.pool) >= option.amount
        case ActionSpend() | ItemSpend() | TextNeed():
            return None


# --- spending ------------------------------------------------------------------------------


def now() -> datetime:
    return datetime.now(UTC)


def spend(
    db: Session,
    actor: User,
    troupe: Troupe,
    character: Character,
    option: Option,
    *,
    purpose: str,
    cycle_id: uuid.UUID | None,
) -> dict[str, Any] | None:
    """Use up an expenditure, as `character`'s, and say what was spent so it can be
    given back; None for an alternative that spends nothing. Refused when the
    character cannot spend it."""
    match option:
        case InfluenceSpend():
            rules = influence_log.troupe_rules(db, troupe.id)
            action = influence.at_level(rules, option.type, option.level)
            entry = influence_log.add_entry(
                db,
                actor,
                troupe,
                influence_log.Details(
                    influence_type=option.type,
                    happened_at=now(),
                    character_id=character.id,
                    specialization=option.area,
                    action_key=action.key if action else None,
                    purpose=purpose,
                    needs_details=action is None,
                    cycle_id=cycle_id,
                ),
                source="quest",
            )
            return {"influence_entry_id": str(entry.id), "entry": influence_log.short_id(entry)}
        case PoolSpend():
            lock_character(db, character.id)
            if pool_now(db, character, option.pool) < option.amount:
                raise conflict(
                    f"{character.name} has not {option.amount} {POOL_NAMES[option.pool]} to spend."
                )
            tap = uuid.uuid4()
            play.record(
                db,
                character,
                actor,
                [
                    play.Tap(
                        id=tap,
                        happened_at=now(),
                        kind="change",
                        tracker=option.pool,
                        amount=-option.amount,
                        note=purpose,
                    )
                ],
            )
            return {"tap": str(tap)}
        case StatusSpend():
            held = fleeting(db, character, option.name)
            if not held:
                wanted = option.name or "fleeting status"
                raise conflict(f"{character.name} holds no {wanted} to spend.")
            row = db.get_one(HeldStatus, held[0].id)
            kept = play_status.record_of(row)
            sect_status.remove(db, actor, character, troupe, row.id, reason=purpose, how="spent")
            return {"status": kept}
        case ActionSpend():
            debt = OwedAction(
                character_id=character.id,
                troupe_id=troupe.id,
                action_kind=option.action_kind,
                amount=1,
                reason=purpose,
                owed_by=actor.id,
            )
            db.add(debt)
            db.flush()
            current = downtimes.current_participation(db, character)
            if current is not None and current[0].troupe_id == troupe.id:
                downtimes.settle_owed_actions(db, current[1], current[0])
            return {"owed_action_id": str(debt.id)}
        case BackgroundSpend() | ItemSpend():
            # Recorded on the quest alone.
            return {"recorded": True}
        case TraitNeed() | AspectNeed() | TextNeed():
            return None


def give_back(db: Session, actor: User, character: Character | None, spent: dict[str, Any]) -> None:
    """Undo what `spend` spent, as far as it still can be."""
    if entry_id := spent.get("influence_entry_id"):
        entry = db.get(InfluenceEntry, uuid.UUID(entry_id))
        if entry is not None:
            influence_log.delete_entry(db, actor, entry)
    if (tap := spent.get("tap")) and character is not None:
        lock_character(db, character.id)
        play.record(
            db,
            character,
            actor,
            [play.Tap(id=uuid.uuid4(), happened_at=now(), kind="undo", undoes=uuid.UUID(tap))],
        )
    if (record := spent.get("status")) and character is not None:
        play_status.give_back(db, character, actor, record)
    if debt_id := spent.get("owed_action_id"):
        debt = db.get(OwedAction, uuid.UUID(debt_id))
        if debt is not None:
            db.delete(debt)
            db.flush()

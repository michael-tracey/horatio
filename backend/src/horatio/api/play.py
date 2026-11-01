"""The Play View: a living sheet for a game, where blood, Willpower, health and
limited uses are spent tap by tap (horatio.play). The character's player and
the staff who can see the sheet use it alike; each tap says who made it."""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import (
    audit,
    domitors,
    embrace,
    equipment,
    house_traits,
    influence_log,
    play,
    play_influence,
    play_status,
    reference,
    retainers,
    sect_status,
    sheets,
)
from horatio.api.downtimes import staff_troupe
from horatio.api.equipment import EquipmentModifierOut, modifier_out
from horatio.api.influence import InfluenceStandingOut, standing_out
from horatio.api.lines_veils import LinesVeils, lines_veils_of
from horatio.api.npcs import PanelsOut, StockNpcOut, stock_out
from horatio.api.play_status import PlayStatusOut, StatusChoiceIn, play_status_out
from horatio.api.retainers import IdentityOut, RetainerOut, identities_out, listed
from horatio.api.roster import roster
from horatio.api.sect_status import StatusIn
from horatio.auth.deps import CurrentUser, DbSession
from horatio.influence import InfluenceType
from horatio.models import (
    Character,
    InfluenceEntry,
    PlayCounter,
    PlayEvent,
    PlayGame,
    PoolModifier,
    Troupe,
    User,
)
from horatio.permissions import (
    TroupeAction,
    can_see_lines_veils,
    require_troupe_action,
    visible_character,
)
from horatio.pool_modifiers import ModifierOut, modifiers_out
from horatio.rules.feeding import clan_family
from horatio.rules.npc_kinds import kind_name

router = APIRouter(tags=["play"])

# Shown in the rest of the sheet; health and Willpower are trackers, and
# specialties go in brackets after their trait. The clan, archetype and sect are
# listed for the page's subheader, which shows them instead of the Sheet tab.
NOT_LISTED = frozenset({"health_levels", "willpower_sources"})


class Tracker(BaseModel):
    value: int
    most: int
    # Where a game starts it.
    start: int


class HealthLevel(BaseModel):
    name: str
    boxes: int


class Health(BaseModel):
    levels: list[HealthLevel]
    # Boxes marked, in the order they were: "normal" or "aggravated".
    marks: list[str]
    # A Stamina focus spares a character the Incapacitated penalty (p. 285).
    stamina_focus: bool


class Morality(BaseModel):
    name: str
    value: int
    rating: int


class TemporaryDerangement(BaseModel):
    # Its tracker in taps: "derangement:<id>".
    key: str
    name: str
    source: str
    # Held now; one removed is kept for the old logs.
    held: bool


class Derangements(Tracker):
    """Derangement traits and the derangements behind them, which Reset leaves as
    they are (horatio.play). The Play View shows them for a character with the
    Derangement flaw or a temporary derangement held, and while any are marked."""

    # The fewest the character can have: 1 for a Malkavian.
    least: int
    # The Derangement flaws on the sheet, by their detail.
    flaws: list[str]
    # Those added on the Play View, oldest first.
    temporary: list[TemporaryDerangement]


class TemporaryDerangementIn(BaseModel):
    """A temporary derangement a tap adds."""

    name: str = Field(min_length=1, max_length=80)
    # Where it came from: "Voice of Madness", a quest's consequence.
    source: str = Field(default="", max_length=120)


class ItemTapIn(BaseModel):
    """Giving or discarding an item ("item:<id>", −1; horatio.equipment)."""

    # The character it goes to; None discards it.
    to_character_id: uuid.UUID | None = None
    # As the device's log names them until the server has the tap; the server
    # names them from its own records.
    item_name: str = Field(default="", max_length=200)
    to_name: str = Field(default="", max_length=200)


class ExpendableOut(BaseModel):
    key: str
    name: str
    detail: str
    # The sheet's category ("Backgrounds", "Merits"), or "Counters" for the player's own.
    group: str
    uses: int
    left: int
    counter_id: uuid.UUID | None
    # Influences: its type. Spending a use logs it in the troupe's influence log.
    influence: InfluenceType | None = None
    # Influence spent at earlier games that no downtime cycle has taken off yet:
    # `uses` is already that much lower, as the month has one pool.
    owed: int = 0


class RetainerTrackOut(BaseModel):
    """One Retainer's health levels and (a ghoul's) Blood at this game, tapped as
    "<key>/health" and "<key>/blood" (horatio.play)."""

    key: str
    name: str
    health: Tracker
    blood: Tracker | None


class InfluenceSpendOut(BaseModel):
    """What an influence spend logged, for the game's log."""

    entry_id: uuid.UUID
    # The entry's short id in the troupe's influence log: E12, UW7.
    short_id: str
    type: InfluenceType
    specialization: str
    action_key: str | None
    # "5: No Party Crashers"; None while it needs details.
    action: str | None
    purpose: str
    times: int
    needs_details: bool
    # Staff have changed it in the troupe's log since it was spent.
    changed_by_staff: bool


class LogEntryOut(BaseModel):
    # The id the device gave the tap.
    id: uuid.UUID
    kind: str
    tracker: str
    amount: int
    damage: str | None
    before: int | None
    after: int | None
    text: str
    note: str
    happened_at: datetime
    actor_name: str
    # Made by someone other than the character's player.
    by_staff: bool
    undone: bool
    # For an undo, the tap it undid.
    undoes: uuid.UUID | None
    # Influence spent: what the troupe's influence log has for it.
    influence: InfluenceSpendOut | None = None


class PowerOut(reference.Switch):
    """A form or power the character has, and whether it is on in this game."""

    on: bool


class PlayItemOut(BaseModel):
    """An item the character holds, to equip at a game (issue #306)."""

    id: uuid.UUID
    name: str
    kind: str
    # Hands it takes, for a weapon.
    hands: int | None
    # What its qualities do to the pools while it is equipped.
    modifiers: list[EquipmentModifierOut]


class GameOut(BaseModel):
    id: uuid.UUID
    number: int
    started_at: datetime
    ended_at: datetime | None
    ended_by: str | None
    taps: int
    notes: int


class VitaeOut(BaseModel):
    """A ghoul's Blood beside its vitae, which is `blood` (MET: VtM core p. 297): `pool`
    in all, the rest human Blood, which cannot be spent. Vitae refills only by
    drinking it ("drank" taps); without a drink for `days` days, the ghoul ages 10
    years a day."""

    pool: int
    human: int
    # Human Blood as the game started.
    human_start: int
    last_drank_at: datetime | None
    days: int


class PlayTrait(BaseModel):
    category: str
    category_name: str
    group: str
    name: str
    detail: str
    rating: int | None
    # Its specialties, from the categories that specialise it.
    specialties: list[str]
    # What it does and the book page, from the rules, as the sheet's catalogue has them.
    description: str | None = None
    page_reference: str | None = None
    # The player's note on it: what a custom archetype means for the character.
    note: str = ""
    # For a clan: its in-clan disciplines.
    in_clan: list[str] | None = None
    # A troupe's own merit or flaw: "House merit of Night Court", shown with a ★.
    house: str | None = None
    # What its effects do, in words: shown under its description.
    house_summary: str | None = None


class PlayView(BaseModel):
    character_id: uuid.UUID
    character_name: str
    player_name: str
    kind: str
    # An NPC's form: "sheeted", or "stock" for a Stock NPC, whose Play View is its
    # own, simpler one (issue #215). None for a PC.
    npc_form: Literal["sheeted", "stock"] | None = None
    # A Stock NPC's stat block, with its kind's rules; None for anyone else.
    stock: StockNpcOut | None = None
    # A sheeted NPC's kind and its name (a custom kind's own), for the badge and
    # rules card; None for a PC.
    npc_kind: str | None = None
    npc_kind_name: str | None = None
    # The panels this character has: a mortal or a werewolf has no Beast, Humanity,
    # Generation or frenzy (horatio.rules.npc_kinds.Panels). A PC has them all.
    panels: PanelsOut = PanelsOut(
        beast=True, frenzy=True, morality=True, generation=True, feed=True
    )
    # What the character is (horatio.rules.splats.Splat).
    splat: str = "vampire"
    clan: str | None
    sect: str | None
    # The Generation background's rating, and the generation it gives: 12 for the
    # 12th (None without a dot, or thin-blooded).
    generation: int
    generation_number: int | None = None
    blood_per_turn: int
    # What `blood` is: Blood, a ghoul's Vitae, or a Stock NPC's kind's resource (Rage).
    blood_name: str = "Blood"
    # The Herd background's rating: feeding at a game takes 5 minutes for that
    # much blood, rather than 15 for 2 (MET: VtM core, p. 102).
    herd: int = 0
    blood: Tracker
    # A ghoul's human Blood; its `blood` is its vitae. None for a vampire.
    vitae: VitaeOut | None = None
    # The most Blood with nothing switched on (Blood of Potency raises it).
    blood_usual: int = 0
    # Blood started at half: the character fed short last downtime.
    half_blood: bool = False
    willpower: Tracker
    health: Health
    morality: Morality | None
    beast: Tracker
    derangements: Derangements
    expendables: list[ExpendableOut]
    # Each Retainer's health and Blood (its pool and the rest are in the reference).
    retainers: list[RetainerTrackOut] = []
    # Forms and powers in use (issue #200): those the sheet has, on or off. The
    # health tracker gains the wound levels of those on, after the sheet's own in
    # each category; `blood_per_turn` and `blood_usual` are without them.
    powers: list[PowerOut] = []
    # The items it holds, and those equipped, in the order they were (issue #306):
    # like what is switched on, kept from game to game.
    equipment: list[PlayItemOut] = []
    equipped: list[uuid.UUID] = []
    # What the character can do with each type of influence it has, for the
    # details of a spend. Empty when there is no troupe to log spends in.
    influence: list[InfluenceStandingOut] = []
    # Its sect status at the game (horatio.play_status); None for a character with
    # none, as its sect has no status rules or it has no sect.
    status: PlayStatusOut | None = None
    # The game now; None before the character's first tap.
    game: GameOut | None
    # The game's log, newest first.
    log: list[LogEntryOut]


class InfluenceDetailsIn(BaseModel):
    """What an influence spend was for (horatio.play_influence)."""

    # The action's key in the troupe's rules, such as "no_party_crashers".
    action: str = Field(min_length=1, max_length=80)
    # One of the character's own specialisations of the type, or none.
    specialization: str = Field(default="", max_length=120)
    purpose: str = Field(default="", max_length=300)

    def details(self) -> play_influence.Details:
        return play_influence.Details(
            action=self.action, specialization=self.specialization, purpose=self.purpose
        )


class TapIn(BaseModel):
    """One tap, as the device made it."""

    # Made on the device, so a tap sent twice is recorded once.
    id: uuid.UUID
    happened_at: datetime
    # The game it was made in; by default the game now.
    game_id: uuid.UUID | None = None
    kind: Literal["change", "note", "undo"]
    tracker: str = Field(default="", max_length=200)
    amount: int = Field(default=0, ge=-50, le=50)
    damage: Literal["normal", "aggravated"] | None = None
    note: str = Field(default="", max_length=300)
    undoes: uuid.UUID | None = None
    # Spending Influences: the action's details. Left out when the player skips
    # them; the spend is logged all the same, as needing details.
    influence: InfluenceDetailsIn | None = None
    # Adding a temporary derangement ("derangement:<id>", +1) for the first time:
    # its name and where it came from.
    derangement: TemporaryDerangementIn | None = None
    # Giving or discarding an item ("item:<id>", −1).
    equipment: ItemTapIn | None = None

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.kind == "change":
            if not play.known_tracker(self.tracker) or self.amount == 0:
                raise ValueError("A change names what changed and by how much.")
            if self.tracker.startswith(equipment.ITEM) and self.amount != -1:
                raise ValueError("An item is given or discarded once.")
            if self.tracker == "health" and self.damage is None:
                raise ValueError("Health changes say whether the damage is normal or aggravated.")
        if self.kind == "note" and not self.note.strip():
            raise ValueError("A note needs some words.")
        if self.kind == "undo" and self.undoes is None:
            raise ValueError("An undo names the tap it undoes.")
        return self


class Taps(BaseModel):
    taps: list[TapIn] = Field(max_length=500)


class ResetIn(BaseModel):
    # The game the person meant to end. If someone has already reset it, nothing
    # is reset twice.
    game_id: uuid.UUID | None = None


class CounterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    uses: int = Field(ge=1, le=99)


# Which pools a modifier changes: every pool, every attack, every defence, the
# pools made on an attribute, or one pool by its key.
POOLS_PATTERN = r"^(all|attack|defense|Physical|Social|Mental|pool:[\w' :-]+)$"
Pools = Annotated[str, StringConstraints(pattern=POOLS_PATTERN)]


class ModifierIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    amount: int = Field(ge=-9, le=9)
    pools: Pools
    when: str = Field(default="", max_length=80)
    on: bool = True

    @model_validator(mode="after")
    def not_nothing(self) -> Self:
        if self.amount == 0:
            raise ValueError("A modifier needs an amount other than 0.")
        return self


class ModifierChange(BaseModel):
    """Whatever of a modifier is changing; the rest stays."""

    label: str | None = Field(default=None, min_length=1, max_length=80)
    amount: int | None = Field(default=None, ge=-9, le=9)
    pools: Pools | None = None
    when: str | None = Field(default=None, max_length=80)
    on: bool | None = None

    @model_validator(mode="after")
    def not_nothing(self) -> Self:
        if self.amount == 0:
            raise ValueError("A modifier needs an amount other than 0.")
        return self


class TroupePlayEntry(BaseModel):
    character_id: uuid.UUID
    character_name: str
    player_name: str
    kind: str
    home: bool
    game_number: int | None
    taps: int
    last_tap_at: datetime | None
    blood: Tracker
    # A ghoul's human Blood beside its vitae (`blood`); None for a vampire.
    human_blood: int | None = None
    willpower: Tracker
    health_marked: int
    health_boxes: int
    # The player's lines and veils, as the roster shows them to staff.
    lines_veils: LinesVeils | None = None


class TroupeReset(BaseModel):
    # Characters whose game was ended; those with no taps had nothing to reset.
    reset: int


def names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return {user_id: name for user_id, name in rows}


def game_out(db: Session, game: PlayGame, events: list[PlayEvent]) -> GameOut:
    return GameOut(
        id=game.id,
        number=game.number,
        started_at=game.started_at,
        ended_at=game.ended_at,
        ended_by=names(db, {game.ended_by_id}).get(game.ended_by_id) if game.ended_by_id else None,
        taps=sum(1 for e in events if e.kind == "change"),
        notes=sum(1 for e in events if e.note),
    )


def log_out(
    db: Session, character: Character, limits: play.Limits, events: list[PlayEvent]
) -> list[LogEntryOut]:
    """The taps newest first, each as it changed things when it was made."""
    by_id = {e.id: e for e in events}
    undone = {e.undoes_id for e in events if e.kind == "undo"}
    actors = names(db, {e.actor_id for e in events})
    spends = spends_out(db, play_influence.entries(db, by_id))
    # What switching a form or power also did: "out of flight form".
    said = play.replay(limits, events).said

    def target(event: PlayEvent) -> PlayEvent | None:
        return by_id.get(event.undoes_id) if event.undoes_id else None

    return [
        LogEntryOut(
            id=event.client_id,
            kind=event.kind,
            tracker=event.tracker,
            amount=event.amount,
            damage=event.damage,
            before=event.before,
            after=event.after,
            text=spend.text
            if (spend := spends.get(event.id))
            else play.describe(
                event,
                limits,
                by_id.get(event.undoes_id) if event.undoes_id else None,
                said.get(event.id, ()),
            ),
            note=event.note,
            happened_at=event.happened_at,
            actor_name=actors.get(event.actor_id, "Someone"),
            by_staff=not (character.kind == "pc" and event.actor_id == character.player_id),
            undone=event.id in undone,
            undoes=undid.client_id if (undid := target(event)) else None,
            influence=spend.out if (spend := spends.get(event.id)) else None,
        )
        for event in reversed(play.in_order(events))
    ]


class Spend(BaseModel):
    text: str
    out: InfluenceSpendOut


def spends_out(db: Session, entries: dict[uuid.UUID, InfluenceEntry]) -> dict[uuid.UUID, Spend]:
    """Each influence spend's log entry, by its tap's id, and how the log reads it."""
    staff = play_influence.changed_by_staff(db, entries.values())
    rules = {t: influence_log.troupe_rules(db, t) for t in {e.troupe_id for e in entries.values()}}
    found: dict[uuid.UUID, Spend] = {}
    for event_id, entry in entries.items():
        action = (
            None
            if entry.action_key is None
            else influence_log.action_label(rules[entry.troupe_id], entry)
        )
        found[event_id] = Spend(
            text=play_influence.text(entry, action),
            out=InfluenceSpendOut(
                entry_id=entry.id,
                short_id=influence_log.short_id(entry),
                type=entry.type,  # type: ignore[arg-type]  # checked by the database
                specialization=entry.specialization,
                action_key=entry.action_key,
                action=action,
                purpose=entry.purpose,
                times=entry.times,
                needs_details=entry.needs_details,
                changed_by_staff=entry.id in staff,
            ),
        )
    return found


def sheet_traits(db: Session, character: Character) -> list[PlayTrait]:
    rule_set = sheets.rules_for(db, character).rule_set
    rows = sheets.sheet_rows(db, character)
    specialties: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        parent = rule_set.categories.get(row.category.key)
        if parent is not None and parent.specializes:
            key = (parent.specializes["category"], parent.specializes["name"])
            specialties.setdefault(key, []).append(row.trait.detail or row.definition.name)
    house = house_traits.marks(db, [r.definition.id for r in rows if r.definition.troupe_id])
    return [
        PlayTrait(
            category=row.category.key,
            category_name=row.category.name,
            group=rule_set.categories[row.category.key].group,
            name=row.definition.name,
            detail=row.trait.detail,
            rating=row.trait.rating,
            specialties=specialties.get((row.category.key, row.definition.name), []),
            description=row.definition.description,
            page_reference=house[row.definition.id].page
            if row.definition.id in house
            else row.definition.page_reference,
            note=row.trait.note,
            in_clan=row.definition.properties.get("in_clan"),
            house=house[row.definition.id].label if row.definition.id in house else None,
            house_summary=house[row.definition.id].summary or None
            if row.definition.id in house
            else None,
        )
        for row in rows
        if row.category.key in rule_set.categories
        and row.category.key not in NOT_LISTED
        and not rule_set.categories[row.category.key].specializes
    ]


def vitae_out(
    db: Session, character: Character, limits: play.Limits, state: dict[str, Any]
) -> VitaeOut | None:
    if limits.vitae is None:
        return None
    return VitaeOut(
        pool=limits.vitae.pool,
        human=state.get("human", limits.human_start()),
        human_start=limits.human_start(),
        last_drank_at=play.last_drank(db, character),
        days=limits.vitae.days,
    )


def play_view(db: Session, character: Character) -> PlayView:
    game = play.current_game(db, character)
    limits = play.limits(db, character, game)
    events = play.game_events(db, game) if game else []
    state = play.replay(limits, events).state
    rows = sheets.sheet_rows(db, character)

    def one(category: str) -> str | None:
        return next((r.definition.name for r in rows if r.category.key == category), None)

    return PlayView(
        character_id=character.id,
        character_name=character.name,
        player_name=(
            db.get_one(User, character.player_id).display_name if character.kind == "pc" else "NPC"
        ),
        kind=character.kind,
        npc_form=character.npc_form,  # type: ignore[arg-type]  # checked by the database
        stock=stock_out(db, character) if character.npc_form == "stock" else None,
        npc_kind=character.npc_kind,
        npc_kind_name=kind_name(character.npc_kind, character.npc_custom_kind),
        panels=PanelsOut(**asdict(limits.panels)),
        splat=character.splat,
        clan=one("clan"),
        sect=one("sect"),
        generation=limits.generation,
        generation_number=embrace.generation_of(rows) if limits.generation else None,
        blood_per_turn=limits.blood_per_turn,
        blood_name=limits.blood_name,
        herd=max(
            (
                r.trait.rating or 0
                for r in rows
                if r.category.key == "backgrounds" and r.definition.name == "Herd"
            ),
            default=0,
        ),
        blood=Tracker(
            value=state["blood"], most=limits.blood_most(state["on"]), start=limits.starting_blood
        ),
        vitae=vitae_out(db, character, limits, state),
        blood_usual=limits.blood,
        half_blood=limits.half_blood,
        willpower=Tracker(
            value=state["willpower"], most=limits.willpower, start=limits.starting_willpower()
        ),
        health=Health(
            levels=[HealthLevel(name=n, boxes=b) for n, b in limits.health],
            marks=state["health"],
            stamina_focus=any(
                r.category.key == "focus_physicals" and r.definition.name == "Stamina" for r in rows
            ),
        ),
        morality=Morality(
            name=limits.morality_name, value=state["morality"], rating=limits.morality
        )
        if limits.morality_name
        else None,
        beast=Tracker(value=state["beast"], most=play.BEAST_TRAITS, start=limits.beast_start),
        derangements=Derangements(
            value=state["derangements"],
            most=play.DERANGEMENT_TRAITS,
            start=limits.derangements,
            least=limits.derangements_least,
            flaws=list(limits.flaws),
            temporary=[
                TemporaryDerangement(
                    key=t.key, name=t.name, source=t.source, held=bool(state["held"].get(t.key))
                )
                for t in limits.temporary
            ],
        ),
        expendables=[
            ExpendableOut(
                key=e.key,
                name=e.name,
                detail=e.detail,
                group=e.group,
                uses=e.uses,
                left=state["uses"].get(e.key, e.uses),
                counter_id=e.counter_id,
                influence=e.influence,  # type: ignore[arg-type]  # from horatio.influence.TYPES
                owed=e.owed,
            )
            for e in limits.expendables
        ],
        retainers=[
            RetainerTrackOut(
                key=r.key,
                name=r.name,
                health=Tracker(
                    value=state["uses"].get(f"{r.key}/health", r.health),
                    most=r.health,
                    start=r.health,
                ),
                blood=Tracker(
                    value=state["uses"].get(f"{r.key}/blood", r.blood), most=r.blood, start=r.blood
                )
                if r.blood
                else None,
            )
            for r in limits.retainers
        ],
        powers=[PowerOut(**s.model_dump(), on=s.key in state["on"]) for s in limits.switches],
        equipment=[
            PlayItemOut(
                id=uuid.UUID(i.id),
                name=i.name,
                kind=i.kind,
                hands=i.hands,
                modifiers=[modifier_out(m) for m in i.modifiers],
            )
            for i in limits.items
        ],
        equipped=[uuid.UUID(key) for key, _ in limits.still_equipped(state["equipped"])],
        influence=[standing_out(s) for s in play_influence.standings(db, character)],
        status=play_status_out(db, character, game, events),
        game=game_out(db, game, events) if game else None,
        log=log_out(db, character, limits, events),
    )


@router.get("/characters/{character_id}/play")
def read_play(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PlayView:
    """The character's trackers and limited uses at the game now, and its log."""
    return play_view(db, visible_character(db, user, character_id))


class DomitorLine(BaseModel):
    """A ghoul's domitor, and the clan weakness it plays (MET: VtM core p. 297)."""

    name: str
    clan: str | None
    # Its domitor's clan weakness, for roleplay only.
    weakness: str | None


class PlayReference(reference.Reference):
    """The Play View's Sheet and Pools tabs: everything there is to look up at a
    game, which changes only between games, so the page loads it once."""

    traits: list[PlayTrait]
    retainers: list[RetainerOut]
    identities: list[IdentityOut] = []
    # A ghoul's domitor; None for a vampire, or a ghoul not yet bound to one.
    domitor: DomitorLine | None = None
    # A PC's player's lines and veils, for the staff running its game; None for its
    # player, who knows their own, and for an NPC (horatio.lines_veils).
    lines_veils: LinesVeils | None = None


def domitor_line(db: Session, character: Character) -> DomitorLine | None:
    info = domitors.domitor_info(db, character) if domitors.has_domitor(character) else None
    if info is None:
        return None
    family = clan_family(info.clan) if info.clan else None
    return DomitorLine(
        name=info.name,
        clan=info.clan,
        weakness=f"A milder form of the {family} weakness, for roleplay only, with none of its"
        " rules effects (MET: VtM core p. 297)."
        if family
        else None,
    )


@router.get("/characters/{character_id}/play/reference")
def read_reference(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PlayReference:
    character = visible_character(db, user, character_id)
    found = reference.reference(
        sheets.sheet_rows(db, character),
        sheets.rules_for(db, character).rule_set,
        play.limits(db, character).blood_per_turn,
    )
    return PlayReference(
        **found.model_dump(),
        traits=sheet_traits(db, character),
        retainers=listed(db, retainers.read(db, character), user),
        identities=identities_out(db, character),
        domitor=domitor_line(db, character),
        lines_veils=staff_lines_veils(db, user, character),
    )


def staff_lines_veils(db: Session, user: User, character: Character) -> LinesVeils | None:
    if character.kind != "pc" or character.player_id == user.id:
        return None
    player = db.get_one(User, character.player_id)
    return lines_veils_of(player) if can_see_lines_veils(db, user, player) else None


@router.get("/characters/{character_id}/play/modifiers")
def read_modifiers(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[ModifierOut]:
    """The player's own modifiers to the character's test pools, on or off."""
    return modifiers_out(db, visible_character(db, user, character_id))


@router.post("/characters/{character_id}/play/modifiers")
def add_modifier(
    character_id: uuid.UUID, body: ModifierIn, db: DbSession, user: CurrentUser
) -> list[ModifierOut]:
    """Note a modifier. The player and the staff who can see the sheet may, as for taps."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    db.add(
        PoolModifier(
            character_id=character.id,
            label=body.label.strip(),
            amount=body.amount,
            pools=body.pools,
            when=body.when.strip(),
            on=body.on,
            created_by_id=user.id,
        )
    )
    audit.record(
        db,
        user,
        "play.modifier_added",
        character_id=character.id,
        label=body.label,
        amount=body.amount,
        pools=body.pools,
    )
    db.commit()
    return modifiers_out(db, character)


def own_modifier(db: Session, character: Character, modifier_id: uuid.UUID) -> PoolModifier:
    modifier = db.get(PoolModifier, modifier_id)
    if modifier is None or modifier.character_id != character.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such modifier.")
    return modifier


@router.patch("/characters/{character_id}/play/modifiers/{modifier_id}")
def change_modifier(
    character_id: uuid.UUID,
    modifier_id: uuid.UUID,
    body: ModifierChange,
    db: DbSession,
    user: CurrentUser,
) -> list[ModifierOut]:
    """Switch a modifier on or off, or edit it."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    modifier = own_modifier(db, character, modifier_id)
    changes = body.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(modifier, field, value.strip() if isinstance(value, str) else value)
    audit.record(
        db,
        user,
        "play.modifier_changed",
        character_id=character.id,
        label=modifier.label,
        **changes,
    )
    db.commit()
    return modifiers_out(db, character)


@router.delete("/characters/{character_id}/play/modifiers/{modifier_id}")
def remove_modifier(
    character_id: uuid.UUID, modifier_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[ModifierOut]:
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    modifier = own_modifier(db, character, modifier_id)
    audit.record(db, user, "play.modifier_removed", character_id=character.id, label=modifier.label)
    db.delete(modifier)
    db.commit()
    return modifiers_out(db, character)


@router.post("/characters/{character_id}/play/taps")
def record_taps(character_id: uuid.UUID, body: Taps, db: DbSession, user: CurrentUser) -> PlayView:
    """Record taps, perhaps made offline a while ago, in the order they happened."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    play.record(
        db,
        character,
        user,
        [
            play.Tap(
                id=t.id,
                happened_at=t.happened_at,
                kind=t.kind,
                game_id=t.game_id,
                tracker=t.tracker,
                amount=t.amount,
                damage=t.damage,
                note=t.note,
                undoes=t.undoes,
                influence=t.influence.details() if t.influence else None,
                derangement=(t.derangement.name, t.derangement.source) if t.derangement else None,
                given_to=t.equipment.to_character_id if t.equipment else None,
            )
            for t in body.taps
        ],
    )
    db.commit()
    return play_view(db, character)


@router.put("/characters/{character_id}/play/status/choice")
def choose_status(
    character_id: uuid.UUID, body: StatusChoiceIn, db: DbSession, user: CurrentUser
) -> PlayView:
    """The character's choices for its game (horatio.play_status): its source of
    abiding status, a title's status, a title's holder absent. Its player makes each
    once, and it is locked for the game; staff change them."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    staff = sect_status.staff_in(db, user, character, play_status.troupe_of(db, character))
    if not (staff or sect_status.is_player(user, character)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only its player, or staff, choose a character's status."
        )
    play_status.choose(
        db,
        user,
        character,
        play.start_game(db, character),
        staff=staff,
        source=body.source,
        chosen=body.chosen,
        absent=body.absent,
    )
    db.commit()
    return play_view(db, character)


@router.post("/characters/{character_id}/play/status")
def add_status_at_game(
    character_id: uuid.UUID, body: StatusIn, db: DbSession, user: CurrentUser
) -> PlayView:
    """Give the character a fleeting or negative status at its game, naming its
    patron, as the game's troupe's Status on sheets setting allows. It is logged
    against the game."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    game = play.start_game(db, character)
    play_status.begin(db, character, game)
    sect_status.add(
        db,
        user,
        character,
        play_status.troupe_of(db, character),
        name=body.name,
        patron_id=body.patron_id,
        patron_text=body.patron_text,
        place=body.place,
        given_on=body.given_on,
        story=body.story,
        reason=body.reason,
        give_up=body.give_up,
        override=body.override,
        game_id=game.id,
    )
    db.commit()
    return play_view(db, character)


@router.post("/characters/{character_id}/play/reset")
def reset_play(
    character_id: uuid.UUID, body: ResetIn, db: DbSession, user: CurrentUser
) -> PlayView:
    """Reset for the next game: the game ends, kept with its log, and every tracker
    goes back where the sheet starts it, but for Derangement traits, which stay."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    game = play.current_game(db, character)
    if game is not None and (body.game_id is None or body.game_id == game.id):
        play.reset(db, character, user, troupe_id=None)
        db.commit()
    return play_view(db, character)


@router.get("/characters/{character_id}/play/games")
def list_games(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[GameOut]:
    """Games already over, newest first."""
    character = visible_character(db, user, character_id)
    games = db.scalars(
        select(PlayGame)
        .where(PlayGame.character_id == character.id, PlayGame.ended_at.is_not(None))
        .order_by(PlayGame.number.desc())
    )
    return [game_out(db, g, play.game_events(db, g)) for g in games]


class GameLog(BaseModel):
    game: GameOut
    log: list[LogEntryOut]


@router.get("/characters/{character_id}/play/games/{game_id}")
def read_game(
    character_id: uuid.UUID, game_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> GameLog:
    """One game's log, newest first, such as a past game's for the next downtime."""
    character = visible_character(db, user, character_id)
    game = db.get(PlayGame, game_id)
    if game is None or game.character_id != character.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such game.")
    events = play.game_events(db, game)
    return GameLog(
        game=game_out(db, game, events),
        log=log_out(db, character, play.limits(db, character, game), events),
    )


@router.put("/characters/{character_id}/play/taps/{tap_id}/influence")
def give_influence_details(
    character_id: uuid.UUID,
    tap_id: uuid.UUID,
    body: InfluenceDetailsIn,
    db: DbSession,
    user: CurrentUser,
) -> PlayView:
    """Add or change what an influence spend was for, from the game's log. Anyone
    who can see the sheet can until the game ends; after that, only the staff who
    keep the troupe's influence log."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    found = db.execute(
        select(PlayEvent, PlayGame)
        .join(PlayGame, PlayEvent.game_id == PlayGame.id)
        .where(PlayEvent.client_id == tap_id, PlayGame.character_id == character.id)
    ).one_or_none()
    entry = play_influence.entries(db, [found[0].id]).get(found[0].id) if found else None
    if found is None or entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No influence was spent with that tap.")
    if found[1].ended_at is not None:
        require_troupe_action(
            db, user, db.get_one(Troupe, entry.troupe_id), TroupeAction.MANAGE_INFLUENCE_LOG
        )
    play_influence.give_details(db, user, character, entry, body.details())
    db.commit()
    return play_view(db, character)


@router.post("/characters/{character_id}/play/counters")
def add_counter(
    character_id: uuid.UUID, body: CounterIn, db: DbSession, user: CurrentUser
) -> PlayView:
    """A counter of the player's own, such as "Fetish charges: 3"."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    db.add(
        PlayCounter(
            character_id=character.id, name=body.name.strip(), uses=body.uses, created_by_id=user.id
        )
    )
    audit.record(
        db, user, "play.counter_added", character_id=character.id, name=body.name, uses=body.uses
    )
    db.commit()
    return play_view(db, character)


@router.delete("/characters/{character_id}/play/counters/{counter_id}")
def remove_counter(
    character_id: uuid.UUID, counter_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> PlayView:
    """Take a counter off the Play View; old logs still name it."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    counter = db.get(PlayCounter, counter_id)
    if counter is None or counter.character_id != character.id or counter.removed_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such counter.")
    counter.removed_at = datetime.now(UTC)
    counter.removed_by_id = user.id
    audit.record(db, user, "play.counter_removed", character_id=character.id, name=counter.name)
    db.commit()
    return play_view(db, character)


@router.get("/troupes/{troupe_id}/play")
def troupe_play(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[TroupePlayEntry]:
    """Every character in the troupe at the game now, in the roster's order."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    found: list[TroupePlayEntry] = []
    for entry in roster(troupe_id, db, user):
        character = db.get_one(Character, entry.character_id)
        game = play.current_game(db, character)
        limits = play.limits(db, character, game)
        events = play.game_events(db, game) if game else []
        state = play.replay(limits, events).state
        found.append(
            TroupePlayEntry(
                character_id=character.id,
                character_name=character.name,
                player_name=entry.player_name,
                kind=character.kind,
                home=entry.home,
                game_number=game.number if game else None,
                taps=sum(1 for e in events if e.kind == "change"),
                last_tap_at=max((e.happened_at for e in events), default=None),
                blood=Tracker(
                    value=state["blood"],
                    most=limits.blood_most(state["on"]),
                    start=limits.starting_blood,
                ),
                human_blood=state["human"] if limits.vitae else None,
                willpower=Tracker(
                    value=state["willpower"],
                    most=limits.willpower,
                    start=limits.starting_willpower(),
                ),
                health_marked=len(state["health"]),
                health_boxes=len(limits.boxes(state["on"])),
                lines_veils=entry.lines_veils,
            )
        )
    return found


@router.post("/troupes/{troupe_id}/play/reset")
def reset_troupe(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TroupeReset:
    """Reset every character in the troupe for the next game, after one."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RESET_GAMES)
    count = 0
    for entry in roster(troupe_id, db, user):
        character = sheets.lock_character(db, entry.character_id)
        count += play.reset(db, character, user, troupe_id=troupe.id)
    audit.record(db, user, "play.troupe_reset", troupe_id=troupe.id, count=count)
    db.commit()
    return TroupeReset(reset=count)

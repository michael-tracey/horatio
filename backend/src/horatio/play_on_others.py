"""A power used on another character in the troupe (issue #823): its effect reaches
that character's Play View.

**Who.** Only a character of the user's home troupe: its player characters at home
there, and the NPCs that hold a title there, the court's public figures, as the
Status tab's others are (horatio.play_others). A character visiting from another
troupe, or one of another troupe, can't be picked.

**How it travels.** Using a power on someone else is a tap on the user's own Play
View: its cost is an ordinary tap, and the use itself a note naming whom and what
(`Use`), so it waits with the user's other taps while offline and goes once, by its
id, when the signal returns. The note keeps what it did there (PlayEvent.on_other),
so the log reads it and Undo takes it back. What it can't do (the character has
left the troupe, there is no damage to heal) is kept as its reason, and the note
changes nothing; the user's taps are never refused for another character's sake.

**What it does there.**
- A switch used on another (`target` "other" or "any": Fleshcraft reshaping a
  willing person, core p. 168) starts an effect on them, kept until undone
  (horatio.play_effects), with what was picked. The target can't refuse a power
  that worked: it counts on their Play View at once, though they haven't the power.
  They **acknowledge** it, or **dispute** it to the troupe's staff with a note. The
  one who used it, and staff, can end it; the target asks through a dispute.
- A use that heals (`target` "other" on a use: Corpore Sano, core p. 143; King's
  Blessing, p. 144) is taps on the target's own game, made by the user, so their log
  shows who healed them and Undo on the user's side takes them back.

**Telling them.** The target's player (for an NPC, whoever runs it) gets a bell
notice, and the Play View shows it on its next refresh (every 15 seconds): pulled,
not pushed. The user hears when it is acknowledged or disputed; staff hear of a
dispute.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, closing, play, play_effects, reference, sheets
from horatio.models import (
    Character,
    CharacterTitle,
    PlayEffect,
    PlayEvent,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.notifications import notify
from horatio.sheets import conflict


@dataclass(frozen=True)
class Use:
    """A power used on another character, as the user's tap names it."""

    character_id: uuid.UUID
    # The power, as the user's reference names it: "Fleshcraft", "Corpore Sano".
    power: str
    # A switch with `target` "other" or "any", by its key: an effect kept until undone.
    switch: str | None = None
    # What was picked for it, of its own options.
    options: tuple[str, ...] = field(default_factory=tuple[str, ...])
    # Or a use's label, for one that changes the target's trackers ("Heal 1 normal").
    use: str | None = None


# --- Who --------------------------------------------------------------------------


def troupe_of(db: Session, character: Character) -> Troupe | None:
    return play.home_troupe(db, character)


def targets(db: Session, source: Character) -> list[Character]:
    """The characters the user can use a power on: its home troupe's player
    characters at home there and its titled NPCs, by name."""
    troupe = troupe_of(db, source)
    if troupe is None:
        return []
    titled = set(
        db.scalars(select(CharacterTitle.character_id).where(CharacterTitle.troupe_id == troupe.id))
    )
    members = db.scalars(
        select(Character)
        .join(TroupeMembership, TroupeMembership.character_id == Character.id)
        .where(
            TroupeMembership.troupe_id == troupe.id,
            TroupeMembership.left_at.is_(None),
            Character.status == "active",
            Character.id != source.id,
        )
        .order_by(Character.name, Character.id)
    )
    return [
        c
        for c in dict.fromkeys(members)
        if (c.kind == "pc" and c.home_troupe_id == troupe.id)
        or (c.kind == "npc" and c.npc_form == "sheeted" and c.id in titled)
    ]


def target_of(db: Session, source: Character, character_id: uuid.UUID) -> Character:
    """The character a power is used on, which must be one the user can pick."""
    found = next((c for c in targets(db, source) if c.id == character_id), None)
    if found is None:
        raise conflict("Only a character of your home troupe can be picked.")
    return found


def link(character: Character) -> str:
    return f"/play/characters/{character.id}"


def tell(
    db: Session, character: Character, kind: str, summary: str, *, to: Sequence[uuid.UUID] = ()
) -> None:
    """A bell notice about a character's Play View: to its player (for an NPC, whoever
    runs it), or to `to`."""
    troupe = troupe_of(db, character)
    notify(
        db,
        to or [character.player_id],
        kind,
        summary,
        link(character),
        troupe_id=troupe.id if troupe is not None else None,
        character_id=character.id,
    )


# --- Doing it ------------------------------------------------------------------


def option_text(options: Sequence[str]) -> str:
    return f" ({', '.join(options)})" if options else ""


def apply(
    db: Session, source: Character, actor: User, event: PlayEvent, use: Use
) -> dict[str, Any]:
    """Do what a power used on another character does, from the user's tap: what the
    tap keeps for its log line and Undo, or why it was refused."""
    other = db.get(Character, use.character_id)
    kept: dict[str, Any] = {
        "character_id": str(use.character_id),
        "name": other.name if other is not None else "another character",
        "power": use.power,
    }
    try:
        target = target_of(db, source, use.character_id)
        target = sheets.lock_character(db, target.id)
        if use.switch is not None:
            return {**kept, **start(db, source, target, actor, event, use)}
        if use.use is not None:
            return {**kept, **heal(db, source, target, actor, event, use)}
        raise conflict("Say what the power does.")
    except HTTPException as refused:
        return {**kept, "refused": str(refused.detail)}


def start(
    db: Session, source: Character, target: Character, actor: User, event: PlayEvent, use: Use
) -> dict[str, Any]:
    """Start the effect a switch used on another character leaves on them, replacing
    the one of that power on them now: a character carries one application at a time
    (core p. 168)."""
    switch = play.limits(db, source).switch(use.switch or "")
    if switch is None or switch.target == "self" or not switch.kept:
        raise conflict(f"{source.name} can't use that on another character.")
    picks = switch.picks
    # What can be picked for another: not an option for yourself only (issue #813).
    offered = {o.name: o for o in picks.options if o.target != "self"} if picks else {}
    options = list(dict.fromkeys(use.options))
    if any(o not in offered for o in options):
        raise conflict("That can't be picked for it.")
    if picks is not None and offered and not 1 <= len(options) <= picks.count:
        many = "one" if picks.count == 1 else f"up to {picks.count}"
        raise conflict(f"Pick {many} of what it does.")
    # Two amounts of one option are one modification picked twice, which the
    # Manipulation focus doesn't allow (core p. 169).
    bases = [offered[o].base or o for o in options]
    if len(set(bases)) < len(bases):
        raise conflict("The same modification can't be picked twice.")
    # The target's own traits can rule an option out: Tzimisce: Scar Tissue's body
    # takes no beneficial Bonecraft alteration (Vol. 2 p. 278).
    takes = {s.key for s in reference.switch_for(switch.key, play.sheet_of(db, target))}
    barred = [o for o in options if offered[o].key not in takes]
    if barred:
        raise conflict(f"{target.name}'s body can't take {', '.join(barred)}.")
    last = play_effects.active(db, target.id, switch.key)
    if last is not None:
        play_effects.end(db, last, actor, "replaced", switch.name, event=event)
    effect = PlayEffect(
        character_id=target.id,
        source_character_id=source.id,
        source_name=source.name,
        key=switch.key,
        options=options,
        client_id=event.client_id,
        event_id=event.id,
        started_at=event.happened_at,
        started_by_id=actor.id,
        replaced_id=last.id if last is not None else None,
    )
    db.add(effect)
    db.flush()
    audit.record(
        db,
        actor,
        "play.effect_started",
        character_id=target.id,
        power=switch.name + option_text(options),
        replaced=last is not None,
        source=source.name,
    )
    refresh(db, target)
    tell(
        db,
        target,
        "play.effect_on_you",
        f"{source.name} used {switch.name}{option_text(options)} on {target.name}.",
    )
    return {"effect_id": str(effect.id), "switch": switch.name, "options": options}


def damage_now(db: Session, target: Character) -> tuple[int, int]:
    """The target's damage marked now: normal, aggravated."""
    game = play.current_game(db, target)
    if game is None:
        return 0, 0
    marks: list[str] = play.replay(play.limits(db, target, game), play.game_events(db, game)).state[
        "health"
    ]
    aggravated = marks.count("aggravated")
    return len(marks) - aggravated, aggravated


def heals(use: reference.PowerUse, normal: int, aggravated: int) -> list[tuple[str, int]]:
    """The damage a use heals on the target now, by kind: the worst first."""
    if use.heal is None:
        return []
    n = use.heal.amount
    found: list[tuple[str, int]] = []
    if use.heal.damage == "normal":
        found = [("normal", min(n, normal))]
    elif use.heal.damage == "aggravated":
        found = [("aggravated", min(n, aggravated))]
    elif use.heal.damage == "worst":
        worst = min(n, aggravated)
        found = [("aggravated", worst), ("normal", min(n - worst, normal))]
    elif use.heal.damage == "all":
        found = [("aggravated", aggravated), ("normal", normal)]
    return [(kind, k) for kind, k in found if k > 0]


def heal(
    db: Session, source: Character, target: Character, actor: User, event: PlayEvent, use: Use
) -> dict[str, Any]:
    """Heal the target, as taps on their own game made by the user."""
    rows = sheets.sheet_rows(db, source)
    sheet = reference.Sheet.read(rows, sheets.rules_for(db, source).rule_set)
    found = next(
        (
            u.use
            for u in reference.uses_on_others(sheet)
            if u.power == use.power and u.use.label == use.use
        ),
        None,
    )
    if found is None:
        raise conflict(f"{source.name} can't use that on another character.")
    normal, aggravated = damage_now(db, target)
    healing = heals(found, normal, aggravated)
    if not healing:
        raise conflict(f"{target.name} has no damage it heals.")
    taps = [
        play.Tap(
            id=uuid.uuid4(),
            happened_at=event.happened_at,
            kind="change",
            tracker="health",
            amount=-k,
            damage=kind,
            note=f"{source.name}'s {use.power}",
        )
        for kind, k in healing
    ]
    play.record(db, target, actor, taps)
    did = ", ".join(f"{k} {kind}" for kind, k in healing)
    audit.record(
        db,
        actor,
        "play.used_on_other",
        character_id=target.id,
        power=use.power,
        did=f"healed {did}",
        source=source.name,
    )
    tell(
        db,
        target,
        "play.used_on_you",
        f"{source.name} used {use.power} on {target.name}: healed {did}.",
    )
    return {"use": found.label, "taps": [str(t.id) for t in taps], "did": f"healed {did}"}


def refresh(db: Session, character: Character) -> None:
    """Replay the character's game now, so an effect started or ended counts."""
    game = play.current_game(db, character)
    if game is not None:
        play.refresh(db, game, play.limits(db, character, game))


# --- Undoing it -----------------------------------------------------------------


def undo(db: Session, source: Character, actor: User, tap: PlayEvent) -> dict[str, Any] | None:
    """Undo a power used on another character: the effect it started ends (and the
    one it replaced comes back), or the taps it made on their game are undone. None
    if all was taken back; else why some couldn't be."""
    kept = tap.on_other or {}
    if "refused" in kept:
        return None
    target = db.get(Character, uuid.UUID(kept["character_id"]))
    if target is None:
        return {"refused": f"{kept.get('name', 'That character')} is gone."}
    target = sheets.lock_character(db, target.id)
    if "effect_id" in kept:
        effect = db.get(PlayEffect, uuid.UUID(kept["effect_id"]))
        if effect is None or effect.state != "active" or effect.event_id != tap.id:
            return None
        name = kept.get("switch", effect.key)
        play_effects.end(db, effect, actor, "undone", name)
        if effect.replaced_id is not None:
            replaced = db.get(PlayEffect, effect.replaced_id)
            if replaced is not None and replaced.ended_how == "replaced":
                play_effects.bring_back(db, replaced)
        refresh(db, target)
        tell(
            db,
            target,
            "play.effect_ended_on_you",
            f"{source.name} took back {name} on {target.name}.",
        )
        return None
    undoes = [
        play.Tap(id=uuid.uuid4(), happened_at=datetime.now(UTC), kind="undo", undoes=uuid.UUID(t))
        for t in kept.get("taps", [])
    ]
    try:
        play.record(db, target, actor, undoes)
    except HTTPException as refused:
        return {"refused": str(refused.detail)}
    tell(
        db,
        target,
        "play.used_on_you",
        f"{source.name} took back {kept.get('power', 'a power')} on {target.name}.",
    )
    return None


def text(kept: dict[str, Any]) -> str:
    """The tap as the user's log reads it: "Used Fleshcraft: reshaped (Alien beauty) on
    Bram", "Used Corpore Sano on Bram: healed 1 normal"."""
    name = kept.get("name", "another character")
    what = kept.get("switch") or kept.get("power", "a power")
    if "refused" in kept:
        return f"Couldn't use {what} on {name}: {kept['refused']}"
    if "did" in kept:
        return f"Used {what} on {name}: {kept['did']}"
    return f"Used {what}{option_text(kept.get('options', []))} on {name}"


# --- Answering it ---------------------------------------------------------------


def from_other(db: Session, character: Character, effect_id: uuid.UUID) -> PlayEffect:
    """An effect on the character from another's power, still on."""
    effect = play_effects.one(db, character, effect_id)
    if effect.source_character_id == character.id or effect.state != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such effect from another character.")
    return effect


def switch_name(db: Session, character: Character, effect: PlayEffect) -> str:
    found = play.limits(db, character).switch(effect.key)
    return (found.name if found is not None else effect.key) + option_text(effect.options)


def source_of(db: Session, effect: PlayEffect) -> Character | None:
    if effect.source_character_id is None:
        return None
    return db.get(Character, effect.source_character_id)


def acknowledge(db: Session, character: Character, actor: User, effect_id: uuid.UUID) -> None:
    """The target acknowledges an effect another's power left on them."""
    effect = from_other(db, character, effect_id)
    if effect.acknowledged_at is not None:
        return
    effect.acknowledged_at = datetime.now(UTC)
    name = switch_name(db, character, effect)
    audit.record(db, actor, "play.effect_acknowledged", character_id=character.id, power=name)
    source = source_of(db, effect)
    if source is not None:
        tell(
            db,
            source,
            "play.effect_acknowledged",
            f"{character.name} acknowledged {name}, used on them by {source.name}.",
        )


def dispute(
    db: Session, character: Character, actor: User, effect_id: uuid.UUID, note: str
) -> None:
    """The target disputes an effect to the troupe's staff, with a note. It stays on
    until whoever used it, or staff, end it."""
    effect = from_other(db, character, effect_id)
    note = note.strip()
    if not note:
        raise sheets.unprocessable("Say why, for the storytellers.")
    effect.disputed_at = datetime.now(UTC)
    effect.dispute_note = note
    name = switch_name(db, character, effect)
    source = source_of(db, effect)
    by = source.name if source is not None else effect.source_name
    audit.record(
        db, actor, "play.effect_disputed", character_id=character.id, power=name, note=note
    )
    troupe = troupe_of(db, character)
    summary = f"{character.name} disputed {name}, used on them by {by}: {note}"
    if troupe is not None:
        notify(
            db,
            closing.staff_ids(db, troupe),
            "play.effect_disputed",
            summary,
            f"/troupes/{troupe.id}/play",
            troupe_id=troupe.id,
            character_id=character.id,
        )
    if source is not None:
        tell(db, source, "play.effect_disputed", summary)


def made_by(db: Session, source: Character) -> list[PlayEffect]:
    """The effects the user's powers have left on others, still on, oldest first."""
    return list(
        db.scalars(
            select(PlayEffect)
            .where(
                PlayEffect.source_character_id == source.id,
                PlayEffect.character_id != source.id,
                PlayEffect.state == "active",
            )
            .order_by(PlayEffect.started_at, PlayEffect.id)
        )
    )


def end_made(db: Session, source: Character, actor: User, effect_id: uuid.UUID) -> None:
    """Whoever used a power on another ends what it left there."""
    effect = db.get(PlayEffect, effect_id)
    if (
        effect is None
        or effect.source_character_id != source.id
        or effect.character_id == source.id
        or effect.state != "active"
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such effect of yours on another.")
    target = sheets.lock_character(db, effect.character_id)
    name = switch_name(db, target, effect)
    play_effects.end(db, effect, actor, "source", name)
    refresh(db, target)
    tell(db, target, "play.effect_ended_on_you", f"{source.name} ended {name} on {target.name}.")


def ended_by_staff(db: Session, character: Character, effect: PlayEffect, name: str) -> None:
    """Tell the target that staff ended an effect another's power left on them."""
    if effect.source_character_id != character.id:
        tell(db, character, "play.effect_ended_on_you", f"Staff ended {name} on {character.name}.")

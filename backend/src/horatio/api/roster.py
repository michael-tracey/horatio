"""A troupe's characters and log, for its storytellers and assistant storytellers."""

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select

from horatio import character_filter, pictures, social_age, titles
from horatio.api.downtimes import staff_troupe
from horatio.api.printing import PrintedSheet, print_sheet
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Approval, AuditEvent, Character, RuleSet, TroupeMembership, User
from horatio.permissions import TroupeAction
from horatio.rules.model import RuleSetData
from horatio.rules.store import read_troupe_rules

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["roster"])


class RosterEntry(BaseModel):
    character_id: uuid.UUID
    character_name: str
    player_name: str
    # None for an NPC, whose player_name is "NPC".
    player_id: uuid.UUID | None
    player_handle: str | None
    kind: str  # pc | npc
    # The player has retired the character.
    retired: bool
    titles: list[str]
    # Where its picture is (horatio.pictures), or None.
    picture: str | None
    # From the sheet as it stands (horatio.social_age).
    clan: str | None
    # Neonate, Ancilla or Elder.
    social_age: str
    # The troupe holds the character's sheet; otherwise the character visits.
    home: bool
    # Waiting for this troupe to accept it as home.
    waiting: bool
    # Discipline dots waiting on this troupe.
    disciplines_waiting: int
    joined_at: datetime


class LogEntry(BaseModel):
    id: uuid.UUID
    at: datetime
    action: str
    message: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    character_id: uuid.UUID | None
    character_name: str | None
    # A PC's player, named in the message unless they are the one who did it.
    player_id: uuid.UUID | None
    player_name: str | None
    data: dict[str, Any]


@router.get("/characters")
def roster(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[RosterEntry]:
    """Every character in the troupe now: those whose home it is first, then visitors."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    rows = list(
        db.execute(
            select(TroupeMembership, Character, User)
            .join(Character, TroupeMembership.character_id == Character.id)
            .join(User, Character.player_id == User.id)
            .where(TroupeMembership.troupe_id == troupe_id, TroupeMembership.left_at.is_(None))
        )
    )
    standing = social_age.standings(db, [c.id for _, c, _ in rows])
    pending = list(
        db.execute(
            select(Approval.character_id, Approval.kind).where(
                Approval.troupe_id == troupe_id, Approval.status == "pending"
            )
        )
    )
    entries = [
        RosterEntry(
            character_id=c.id,
            character_name=c.name,
            player_name=player.display_name if c.kind == "pc" else "NPC",
            player_id=player.id if c.kind == "pc" else None,
            player_handle=player.handle if c.kind == "pc" else None,
            kind=c.kind,
            retired=c.status == "retired",
            titles=titles.held(db, troupe_id, c.id),
            picture=pictures.picture_url(c.id, c.picture_id),
            clan=standing[c.id].clan,
            social_age=standing[c.id].age,
            home=c.home_troupe_id == troupe_id,
            waiting=(c.id, "home_troupe_change") in pending,
            disciplines_waiting=sum(1 for p in pending if p == (c.id, "discipline")),
            joined_at=m.joined_at,
        )
        for m, c, player in rows
    ]
    return sorted(entries, key=lambda e: (not e.home, e.character_name.lower()))


class FilterCondition(BaseModel):
    """One condition of a character filter; see horatio.character_filter."""

    model_config = ConfigDict(extra="forbid")

    what: str
    which: str | None = None
    op: str
    value: int | str | list[str] | None = None


class FilterGroup(BaseModel):
    """Conditions and groups, all or any of which must hold."""

    model_config = ConfigDict(extra="forbid")

    match: Literal["all", "any"] = "all"
    items: list["FilterGroup | FilterCondition"]


class FilterMatch(BaseModel):
    character_id: uuid.UUID
    # The number each condition compared, keyed "trait:skills/Occult", "xp:earned"…
    values: dict[str, int]


def troupe_catalogue(db: DbSession, troupe_id: uuid.UUID) -> RuleSetData:
    """Every category and trait a character in the troupe can have, for a filter to
    name: the Vampire rule set's, with those only another splat has, such as a
    ghoul's Domitor's In-Clan Disciplines. Any splat counts, as an NPC can be a
    ghoul whatever splats the troupe's player characters may be."""
    rules = read_troupe_rules(db, "vampire", troupe_id).rule_set
    categories, traits = dict(rules.categories), dict(rules.traits)
    for splat in sorted(set(db.scalars(select(RuleSet.splat))) - {"vampire"}):
        other = read_troupe_rules(db, splat, troupe_id).rule_set
        categories = {**other.categories, **categories}
        traits = {**other.traits, **traits}
    return replace(rules, categories=categories, traits=traits)


@router.post("/characters/search")
def search_characters(
    troupe_id: uuid.UUID, body: FilterGroup, db: DbSession, user: CurrentUser
) -> list[FilterMatch]:
    """The troupe's characters whose sheets match the filter, in the roster's order."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    characters = [db.get_one(Character, e.character_id) for e in roster(troupe_id, db, user)]
    rules = troupe_catalogue(db, troupe_id)
    try:
        found = character_filter.search(db, troupe_id, characters, body.model_dump(), rules)
    except character_filter.FilterError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return [FilterMatch(character_id=c, values=v) for c, v in found]


@router.get("/print")
def print_characters(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    characters: Annotated[list[uuid.UUID] | None, Query()] = None,
) -> list[PrintedSheet]:
    """Printed sheets, headed for this troupe: the characters named, in that order, or
    every character in the troupe now, in the roster's order."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    members = [e.character_id for e in roster(troupe_id, db, user)]
    wanted = characters or members
    if not set(wanted) <= set(members):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Not all of those characters are in this troupe."
        )
    return [print_sheet(db, db.get_one(Character, c), troupe_id) for c in wanted]


# What each logged action reads as. `{character}` and `{actor}` are filled in.
MESSAGES: dict[str, str] = {
    "troupe.join": "{character} joined the troupe.",
    "troupe.leave": "{character} left the troupe.",
    "character.deleted": "{character} was deleted by its player.",
    "approval.request": "{actor} asked for {character} to be approved.",
    "approval.request.discipline": "{actor} bought {name} {rating} for {character}; pending.",
    "approval.request.review": "{actor} bought {name} {rating} for {character}; for review.",
    "approval.approved.review": "{actor} approved {character}'s {name} {rating}.",
    "approval.declined.review": "{actor} declined {character}'s {name} {rating}; refunded.",
    "approval.withdrawn.review": "{actor} withdrew {character}'s {name} {rating}; refunded.",
    "approval.approved.discipline": "{actor} approved {character}'s {name} {rating}.",
    "approval.declined.discipline": "{actor} declined {character}'s {name} {rating}; refunded.",
    "approval.withdrawn.discipline": "{actor} withdrew {character}'s {name} {rating}; refunded.",
    "approval.request.exception": "{actor} asked for {name} {rating} for {character} by"
    " exception: {reason}",
    "approval.approved.exception": "{actor} approved {character}'s {name} {rating} by exception.",
    "approval.declined.exception": "{actor} declined {character}'s {name} {rating} by exception;"
    " refunded.",
    "approval.withdrawn.exception": "{actor} withdrew {character}'s {name} {rating}; refunded.",
    "approval.request.diablerie": "{actor} says {character} committed diablerie on {committed_on}.",
    "approval.approved.diablerie": "{actor} approved {character}'s diablerie.",
    "approval.declined.diablerie": "{actor} declined {character}'s diablerie.",
    "approval.withdrawn.diablerie": "{actor} withdrew {character}'s diablerie.",
    "approval.request.home_troupe_change": "{actor} asked to make this {character}'s home.",
    "approval.approved.home_troupe_change": "{actor} accepted {character}; this is its home.",
    "approval.approved": "{actor} approved {character}.",
    "approval.declined": "{actor} declined {character}'s request.",
    "approval.withdrawn": "{actor} withdrew {character}'s request.",
    # From before characters had one home troupe; kept so old log entries read.
    "standing.draft": "{actor} sent {character} back to draft: {reason}",
    "home_troupe.moved_away": "{character} moved its home troupe elsewhere.",
    "xp.award": "{actor} awarded {character} {amount} XP: {reason}",
    "xp.self_entered": "{actor} added {amount} XP to {character} themselves: {reason}",
    "xp.joining": "{actor} settled {character}'s XP on joining: {topped_up} topped up,"
    " {extra} extra, {self_entered_removed} self-entered and {above_ceiling_removed} above"
    " the ceiling taken away.",
    "troupe.starting_xp": "{actor} set the troupe's starting XP to {starting_xp}.",
    "troupe.xp_range_game": "{actor} added a game's {amount} XP to the floor and ceiling.",
    "troupe.xp_range_downtime": "{actor} added a downtime's {amount} XP to the ceiling.",
    "troupe.xp_range_set": "{actor} set the XP floor to {floor} and the ceiling to {ceiling}:"
    " {reason}",
    "staff.assigned": "{actor} made {member} {role}.",
    "staff.removed": "{actor} removed {member} from the staff.",
    "troupe.lead_appointed": "{actor} appointed {member} lead storyteller.",
    "troupe.renamed": "{actor} renamed the troupe to {name}.",
    "troupe.archived": "{actor} archived the troupe.",
    "troupe.profile_changed": "{actor} changed the troupe's profile.",
    "troupe.public": "{actor} made the troupe's profile {state}.",
    "troupe.game_added": "{actor} added a game to the troupe's schedule.",
    "troupe.game_removed": "{actor} took a game off the troupe's schedule.",
    "troupe.portrait_uploaded": "{actor} gave the troupe a portrait.",
    "troupe.portrait_replaced": "{actor} gave the troupe a new portrait.",
    "troupe.portrait_cropped": "{actor} moved the crop of the troupe's portrait.",
    "troupe.portrait_removed": "{actor} removed the troupe's portrait.",
    "troupe.banner_uploaded": "{actor} gave the troupe a banner.",
    "troupe.banner_removed": "{actor} removed the troupe's banner.",
    "downtime.cycle_created": "{actor} created a downtime cycle.",
    "downtime.cycle_opened": "{actor} opened a downtime cycle ({participants} taking part).",
    "downtime.cycle_closed": "{actor} closed a downtime cycle.",
    "downtime.submitted": "{character} submitted a downtime.",
    "downtime.delivered": "{actor} delivered {count} downtime results.",
    "connector.changed": "{actor} turned the {connector} connector {state}.",
    "connector.discord_connected": "{actor} connected the Discord server {server}.",
    "connector.discord_disconnected": "{actor} disconnected the Discord server {server}.",
    "delivery.retried": "{actor} retried {character}'s {channel} delivery.",
    "delivery.marked_sent": "{actor} marked {character}'s {channel} delivery as sent by hand.",
    "downtime.participant_added": "{actor} added {character} to a downtime cycle.",
    "downtime.participant_removed": "{actor} removed {character} from a downtime cycle.",
    "downtime.allowance_adjusted": "{actor} adjusted {character}'s actions: {reason}",
    "downtime.feeding_difficulty_set": "{actor} set {clan} feeding to {amount} this cycle:"
    " {reason}",
    "downtime.feeding_adjusted": "{actor} adjusted {character}'s feeding by {delta}: {reason}",
    "downtime.feeding_answered": "{actor} answered {character}'s feeding: {result}.",
    "npc.created": "{actor} made an NPC, {character}.",
    "npc.made_sheeted": "{actor} made the Stock NPC {character} a full sheet (a {npc_kind}"
    " rated {rating}; specializations: {specializations}; left off the sheet: {left_out})."
    " Its notes: {notes}",
    "npc.deleted": "{actor} deleted the NPC {character}.",
    "title.given": "{actor} gave {character} the title {title}.",
    "title.taken": "{actor} took the title {title} from {character}.",
    "title.added": "{actor} added the title {title} to the troupe.",
    "title.removed_from_troupe": "{actor} removed the title {title} from the troupe.",
    "status.added": "{actor} gave {character} the {type} status {status}, from {patron}{because}.",
    "status.removed": "{actor} removed {character}'s {status} (from {patron}){because}.",
    "status.spent": "{actor} spent {character}'s {status} (from {patron}){because}.",
    "status.given_up": "{actor} gave up {character}'s {status} (from {patron}) unspent, to take"
    " {instead}.",
    "status.expired": "{character}'s {status} (from {patron}) ended.",
    "status.cleared": "{actor} made {character} {sect}, so it lost the status it held: {statuses}.",
    "status.resolved": "{actor} took {status} off {character}: nothing gives it now{because}.",
    "status.ban_marked": "{actor} marked the status ban “{ban}” for {character}: {mark}{because}.",
    "troupe.status_by": "{actor} set Status on sheets: {setting}.",
    "troupe.badges": "{actor} set what badges print: {titles}, {status}.",
    "scene.created": "{actor} made the scene {name}.",
    "scene.renamed": "{actor} renamed the scene {old} to {name}.",
    "scene.removed": "{actor} removed the scene {name}.",
    "scene.cleared": "{actor} removed the scenes not used since {since}: {count}.",
    "troupe.sects_limited": "{actor} set which sects may join: {sects}.",
    "troupe.splats_limited": "{actor} set which splats may join: {splats}.",
    "house.check": "{actor} set the rule {check} to {strength}.",
    "house.cost_added": "{actor} priced {what} at {price}.",
    "house.cost_changed": "{actor} changed the price of {what} to {price}.",
    "house.creation_set": "{actor} set the troupe's starting {category}: {text}.",
    "house.creation_reset": "{actor} put the starting {category} back to the rule set's: {text}.",
    "house.allowance_added": "{actor} set the troupe's downtime actions for {who}: {amount}.",
    "house.allowance_changed": "{actor} set the troupe's downtime actions for {who}: {amount}.",
    "house.allowance_removed": "{actor} removed the troupe's actions for {who} ({amount}).",
    "house.cost_removed": "{actor} removed the troupe's price for {what} ({price}).",
    "house.trait_added": "{actor} made a {what}, {name} ({points} points, {availability}).",
    "house.trait_changed": "{actor} changed the {what} {name} ({fields}) for the {holders}"
    " characters holding it.",
    "house.trait_archived": "{actor} archived the {what} {name}; those who hold it keep it.",
    "house.trait_restored": "{actor} brought back the {what} {name}.",
    "house.trait_deleted": "{actor} deleted the {what} {name}.",
    "house.trait_applied": "{actor} gave {character} the {what} {name} ({how}): {reason}",
    "house.trait_removed": "{actor} took the {what} {name} off {character}: {reason}",
    "troupe.specializations": "{actor} set the troupe's {kind}: {count} options.",
    "sheet.primary_path": "{actor} named {path} {character}'s primary path of {discipline}.",
    "sheet.detail": "{actor} set {character}'s {name} detail to {detail}.",
    "sheet.choose": "{actor} chose {name} as {character}'s {category}.",
    "sheet.free_choices": "{actor} chose {picks} free traits for {name} on {character}.",
    "sheet.change": "{actor} changed {character}'s {category}: {from_name} → {name} ({cost} XP).",
    "sheet.diablerie": "{actor} recorded {character}'s diablerie of {committed_on}: Generation"
    " {generation}, techniques lost: {techniques}, Humanity lowered {humanity}, Beast traits"
    " {beast}, flaw: {flaw}.",
    "house.diablerie_flaws": "{actor} set what diablerie does to Lesser Generation and Thin"
    " Blooded: it {setting}.",
    "sheet.give": "{actor} gave {character} {name} {rating} by exception ({cost} XP): {reason}",
    "creation.pick": "{actor} picked {name} {rating} for {character}.",
    "creation.unpick": "{actor} took back {character}'s creation pick of {name}.",
    "creation.set_category": "{actor} set {character}'s starting {category}: {picks}.",
    "creation.complete": "{actor} finished creating {character}.",
    "account.reset_link": "{actor} made a password reset link for {member}.",
    "account.reset_sent": "{actor} emailed {member} their reset link.",
    "account.reset_sent.self": "Horatio emailed {member} the reset link they asked for.",
    "account.reset_email_failed": "Horatio could not email {member} a reset link: {error}",
    "account.reset_requested": "{actor} asked for a password reset link.",
    "account.reset_requested.unknown": "Someone asked for a reset link for {email}; "
    "no account uses it.",
    "account.reset_cancelled": "{actor} cancelled {member}'s reset link.",
    "account.password_reset": "{actor} set a new password with a reset link.",
    "account.handle_changed": "{actor} changed their handle from {from_handle} to {handle}.",
    "character.renamed": "{actor} renamed {from_name} to {character}.",
    "character.domitor": "{actor} made {domitor} {character}'s domitor, of {clan}; discipline"
    " dots {disciplines}.",
    "embrace.step": "{actor} Embraced {character}, {step}: {summary} ({xp} XP).",
    "embrace.vampire": "{actor} Embraced {character}: {sire}'s childe, a vampire of {clan},"
    " {generation} generation, with {debt} XP of debt.",
    "embrace.died": "{actor} recorded that {character} died in the Embrace; it is retired. {note}",
    "xp.debt_added": "{actor} added {amount} XP of debt to {character}, now owing {debt}: {reason}",
    "xp.debt_forgiven": "{actor} forgave {amount} XP of {character}'s debt, now owing {debt}:"
    " {reason}",
    "picture.uploaded": "{actor} gave {character} a picture.",
    "picture.replaced": "{actor} gave {character} a new picture.",
    "picture.cropped": "{actor} moved the crop of {character}'s picture.",
    "picture.removed": "{actor} removed {character}'s picture.",
    "retainer.added": "{actor} listed {name} ({dots}) as one of {character}'s Retainers.",
    "retainer.changed": "{actor} changed {was} to {name} ({dots}) among {character}'s Retainers.",
    "retainer.removed": "{actor} took {name} off {character}'s Retainers.",
    "retainer.lost": "{actor} marked {name}, one of {character}'s Retainers, as {how}.",
    "retainer.restored": "{actor} marked {name}, one of {character}'s Retainers, as serving again.",
    "retainer.linked": "{actor} linked {name}, one of {character}'s Retainers, to an NPC.",
    "retainer.unlinked": "{actor} unlinked {name}, one of {character}'s Retainers, from its NPC.",
    "identity.accepted": "{actor} noted {character}'s identity {name} as Accepted by {by}.",
    "identity.unaccepted": "{actor} noted {character}'s identity {name} as Accepted by no one.",
    "character.visible_note": "{actor} set what others see on {character}'s badge: {note}",
    "clan_logo.uploaded": "{actor} uploaded a logo for {clan}.",
    "clan_logo.removed": "{actor} removed the logo for {clan}.",
    "play.reset": "{actor} reset {character} for the next game (game {game} kept).",
    "play.troupe_reset": "{actor} reset {count} characters for the next game.",
    "play.counter_added": "{actor} added a counter to {character}'s Play View: {name} ({uses}).",
    "play.counter_removed": "{actor} removed the counter {name} from {character}'s Play View.",
    "house.starting_blood": "{actor} set the blood characters start a game with: {blood}.",
    "influence.blocked": "{actor} blocked {entry} in the influence log: {who}, {what} "
    "(now {blocks}).",
    "influence.unblocked": "{actor} took a block off {entry} in the influence log: {who}, "
    "{what} (now {blocks}).",
    "house.influence_lookback": "{actor} set how far back influence lookups look: {days} days.",
    "influence.logged": "{actor} logged {entry} in the influence log: {who}, {what}.",
    "influence.repeated": "{actor} logged {who}'s {what} again in {entry} ({times} times).",
    "influence.unrepeated": "{actor} took one of {who}'s {what} off {entry} ({times} left).",
    "influence.changed": "{actor} changed {entry} in the influence log: {fields}.",
    "influence.deleted": "{actor} deleted {entry} from the influence log: {who}, {what}.",
    "influence.merged": "{actor} merged {merged} into {entry} in the influence log"
    " ({times} times).",
    "influence.resolved": "{actor} resolved {entry}: {who}, {what}.",
    "influence.block_recorded": "{actor} recorded an influence block: {what}.",
    "influence.effect_removed": "{actor} took back an influence effect: {what}.",
    "influence.detailed_at_game": "{actor} gave the details of {entry} at a game: {who}, {what}.",
    "shared_background.created": "{actor} set up {shared}, a shared {background}.",
    "shared_background.changed": "{actor} changed the shared background {shared}: {fields}.",
    "shared_background.deleted": "{actor} deleted the shared background {shared} and its log.",
    "shared_background.logged.contribution": "{actor} logged {character} putting {dots} into"
    " {shared}.",
    "shared_background.logged.withdrawal": "{actor} logged {character} taking {dots} out of"
    " {shared}.",
    "shared_background.logged.use": "{actor} logged {character} drawing on {shared}.",
    "shared_background.unlogged.contribution": "{actor} took {character} putting {dots} into"
    " {shared} off its log.",
    "shared_background.unlogged.withdrawal": "{actor} took {character} taking {dots} out of"
    " {shared} off its log.",
    "shared_background.unlogged.use": "{actor} took {character}'s use of {shared} off its log.",
}


def purchase_message(data: dict[str, Any]) -> str:
    name = data["name"] + (f": {data['detail']}" if data.get("detail") else "")
    name = name.replace("{", "{{").replace("}", "}}")
    before, after, cost = data["from_rating"] or 0, data["to_rating"], data["cost"]
    if after == 0:
        change = f"removed {{character}}'s {name}"
    elif before == 0:
        change = f"bought {name} {after} for {{character}}"
    else:
        verb = "raised" if after > before else "lowered"
        change = f"{verb} {{character}}'s {name} from {before} to {after}"
    price = f" ({cost} XP)" if cost > 0 else f" ({-cost} XP back)" if cost < 0 else ""
    if data.get("free"):
        price = " (free by exception)"
    return f"{{actor}} {change}{price}."


def message(
    action: str,
    actor: str | None,
    character: str | None,
    data: dict[str, Any],
    *,
    player: str | None = None,
    by_player: bool = False,
) -> str:
    """The event as a sentence. A PC is followed by its player, "Agnes (Jane)", unless
    the player is named already as the one who did it."""
    values = {**data, "actor": actor or "Someone", "character": character or "A character"}
    if isinstance(values.get("category"), str):
        values["category"] = values["category"].replace("_", " ")
    # A reason given, as the end of a sentence: " (the Prince's order)".
    values["because"] = f" ({data['reason']})" if data.get("reason") else ""
    if isinstance(values.get("picks"), dict):
        picks: dict[str, Any] = values["picks"]
        values["picks"] = ", ".join(f"{n} {r}" for n, r in picks.items()) or "none"
    try:
        if action == "sheet.purchase":
            template = purchase_message(data)
        else:
            template = MESSAGES.get(
                f"{action}.{data.get('kind')}",
                MESSAGES.get(action, action.replace("_", " ").replace(".", ": ")),
            )
        if player is not None and not (by_player and "{actor}" in template):
            values["character"] = f"{values['character']} ({player})"
        return template.format(**values)
    except (KeyError, IndexError, TypeError):
        return action.replace("_", " ").replace(".", ": ")


@router.get("/log")
def log(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    before: datetime | None = None,
    limit: int = 100,
) -> list[LogEntry]:
    """What has happened in the troupe, newest first."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_LOG)
    query = (
        select(AuditEvent, User.display_name)
        .outerjoin(User, AuditEvent.actor_id == User.id)
        .where(AuditEvent.troupe_id == troupe_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(min(max(limit, 1), 500))
    )
    if before is not None:
        query = query.where(AuditEvent.created_at < before)
    return log_entries(db, query)


def log_entries(db: DbSession, query: Select[AuditEvent, str]) -> list[LogEntry]:
    """Read the events `query` selects, with their actors' names, as log entries."""
    events = [(event, actor) for event, actor in db.execute(query)]
    character_ids = {e.character_id for e, _ in events} - {None}
    # Each PC's player as they are named now, not when the event happened.
    players: dict[uuid.UUID | None, tuple[uuid.UUID, str]] = {
        c: (p, name)
        for c, p, name in db.execute(
            select(Character.id, User.id, User.display_name)
            .join(User, Character.player_id == User.id)
            .where(Character.id.in_(character_ids), Character.kind == "pc")
        )
    }
    entries: list[LogEntry] = []
    for event, actor in events:
        name = event.data.get("character_name")
        player_id, player = players.get(event.character_id, (None, None))
        entries.append(
            LogEntry(
                id=event.id,
                at=event.created_at,
                action=event.action,
                message=message(
                    event.action,
                    actor,
                    name,
                    event.data,
                    player=player,
                    by_player=player_id is not None and event.actor_id == player_id,
                ),
                actor_id=event.actor_id,
                actor_name=actor,
                character_id=event.character_id,
                character_name=name,
                player_id=player_id,
                player_name=player,
                data=event.data,
            )
        )
    return entries

"""Giving a sheeted NPC to a player (issue #481), for a troupe moving its characters
into Horatio: it loads them as NPCs (the Yorick import), then gives each to its
player as that person signs up, directly or through a claim link.

The NPC becomes the player's PC, at home in the same troupe and already accepted:
its sheet as it stands is frozen as the accepted sheet, so later changes go
through the troupe's approvals and free changes as any new character's do. Its
NPC-only fields go (kind, form, its own Who's Who listing); its name, picture,
pronouns, sheet, titles, status, equipment, backstory and history stay. Retainers
staff linked to it are unlinked, with a line in their owner's log.

Its XP must balance as a PC's does. Each trait's paid dots are written as a
purchase at what the troupe's costs say they cost, and its merits and flaws taken
as creation picks what they cost or gave in creation (horatio.creation_xp), and one
"Imported" award gives that much, so it starts with nothing unspent. XP the player
had banked elsewhere is its own award, with its reason. A trait the troupe's costs don't price (a
ghoul's starting discipline dots, or one the troupe doesn't allow) is kept as free
dots. Neither award is checked against the troupe's XP floor and ceiling: that is
only done when a character asks to make a troupe its home, and this one already
has.

Only sheeted vampires and ghouls can be given: a Stock NPC has no sheet to play,
and players play vampires and ghouls. Only the custodian and the troupe's lead
storyteller and storytellers give one.

A claim link is a one-off secret for one NPC, valid for 30 days, which staff send
to the person; whoever opens it and claims is given the NPC. As with password
resets and email changes, the link holds a random token and the database only its
hash. An NPC has at most one link: making another replaces it, and it goes once
used, cancelled or the NPC is given another way.

Giving cannot be undone by turning the PC back into an NPC. A mistake in who it
went to is put right by the custodian moving it to the right player
(horatio.character_moves).
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio import audit, creation_xp, npc_picks, play
from horatio.auth.sessions import hash_token
from horatio.config import get_settings
from horatio.models import Character, NpcClaim, Retainer, Troupe, User, XpEntry
from horatio.notifications import notify
from horatio.rules.pricing import PricingError, Quote, trait_cost
from horatio.sheets import (
    SheetRow,
    conflict,
    freeze_sheet,
    lock_character,
    rules_for,
    sheet_rows,
    unprocessable,
)

# The kinds of NPC a player can be given: those the rule sets players build in.
PLAYABLE_KINDS = ("vampire", "ghoul")
CLAIM_DAYS = 30
CARRIED_MAX = 10000


def npc_refusal(npc: Character) -> str | None:
    """Why this character can't be given to anyone, or None if it can."""
    if npc.kind != "npc":
        return f"{npc.name} is already a player's character."
    if npc.npc_form != "sheeted":
        return f"{npc.name} is a Stock NPC, with no full sheet to play. Make it a full sheet first."
    if npc.npc_kind not in PLAYABLE_KINDS:
        return f"{npc.name} isn't a vampire or a ghoul, so it can't be a player's character."
    if npc.creation_completed_at is None:
        return f"{npc.name} is still being built. Finish building it first."
    if npc.status == "retired":
        return f"{npc.name} is retired."
    return None


def refusal(db: Session, npc: Character, to_player: User) -> str | None:
    """Why the NPC can't be given to `to_player` now, or None if it can."""
    why = npc_refusal(npc)
    if why is not None:
        return why
    if to_player.merged_into_id is not None:
        return f"@{to_player.handle}'s account was merged into another."
    game = play.current_game(db, npc)
    if game is not None and play.game_events(db, game):
        return (
            f"{npc.name} is in a game on the Play View. End it first with Reset for"
            " next game, so the game isn't split between two people."
        )
    return None


@dataclass(frozen=True)
class Priced:
    """One rated trait, and what its paid dots cost at the troupe's prices: None for
    one they don't price, kept as free dots."""

    row: SheetRow
    quote: Quote | None


def priced(db: Session, npc: Character) -> list[Priced]:
    rules = rules_for(db, npc)
    rows = sheet_rows(db, npc)
    sheet = [r.as_rules_trait() for r in rows]
    found: list[Priced] = []
    for row in rows:
        if not row.category.rated or not row.trait.rating:
            continue
        try:
            found.append(Priced(row, trait_cost(rules, sheet, row.as_rules_trait())))
        except PricingError:
            found.append(Priced(row, None))
    return found


def label(row: SheetRow) -> str:
    """ "Retainers: Bocephus", as the XP history names a trait."""
    name = row.definition.name
    return f"{name}: {row.trait.detail}" if row.trait.detail else name


@dataclass(frozen=True)
class Preview:
    """What giving the NPC to `to_player` would do."""

    npc: Character
    troupe: Troupe
    to_player: User | None
    # What its sheet costs at the troupe's prices: the "Imported" award.
    xp: int
    # Traits the troupe's costs don't price, kept as free dots.
    free: list[str]
    # Retainers linked to it, as (whose, the Retainer's name), to be unlinked.
    retainers: list[tuple[str, str]]
    refusal: str | None


def preview(db: Session, npc: Character, to_player: User | None) -> Preview:
    troupe = db.get_one(Troupe, npc.owner_troupe_id or npc.home_troupe_id)
    found: list[Priced] = []
    creation = 0
    if npc.kind == "npc":
        # Priced as giving would price it, with its picks fitted, but left as it was.
        savepoint = db.begin_nested()
        npc_picks.fit(db, npc)
        found = priced(db, npc)
        creation = -sum(line.amount for line in creation_xp.due(db, npc))
        savepoint.rollback()
    linked = db.execute(
        select(Character.name, Retainer.name)
        .join(Character, Character.id == Retainer.character_id)
        .where(Retainer.npc_id == npc.id)
        .order_by(Character.name, Retainer.name)
    )
    return Preview(
        npc=npc,
        troupe=troupe,
        to_player=to_player,
        xp=sum(p.quote.cost for p in found if p.quote is not None) + creation,
        free=[label(p.row) for p in found if p.quote is None],
        retainers=[(owner, name) for owner, name in linked],
        refusal=refusal(db, npc, to_player) if to_player is not None else npc_refusal(npc),
    )


def checked_carry(carried_xp: int, carried_reason: str) -> tuple[int, str]:
    if not 0 <= carried_xp <= CARRIED_MAX:
        raise unprocessable(f"Unspent XP to carry over must be 0 to {CARRIED_MAX}.")
    return carried_xp, carried_reason.strip() if carried_xp else ""


def give(
    db: Session,
    actor: User,
    npc: Character,
    to_player: User,
    carried_xp: int = 0,
    carried_reason: str = "",
    *,
    claimed: bool = False,
) -> None:
    """Make the NPC `to_player`'s PC, at home and accepted in its troupe, as `actor`
    (staff, or the claimer if `claimed`), with any XP carried over. Callers check
    that `actor` may."""
    carried_xp, carried_reason = checked_carry(carried_xp, carried_reason)
    npc = lock_character(db, npc.id)
    why = refusal(db, npc, to_player)
    if why is not None:
        raise conflict(why)
    troupe = db.get_one(Troupe, npc.owner_troupe_id)
    name = npc.name
    # Fitted picks as the sheet now stands, so its creation dots are free (#527).
    npc_picks.fit(db, npc)

    # The XP: each trait's paid dots bought at the troupe's prices, and one award
    # for the lot, so nothing is left unspent.
    total = 0
    for p in priced(db, npc):
        trait = p.row.trait
        assert trait.rating is not None
        if p.quote is None:
            trait.free_rating = trait.rating
            continue
        if not p.quote.cost:
            continue
        total += p.quote.cost
        db.add(
            XpEntry(
                character_id=npc.id,
                kind="purchase",
                amount=-p.quote.cost,
                reason=f"{label(p.row)} {trait.free_rating} → {trait.rating}, as an NPC",
                entered_by=actor.id,
                trait_definition_id=p.row.definition.id,
                detail=trait.detail or None,
                from_rating=trait.free_rating,
                to_rating=trait.rating,
                cost_basis=p.quote.rule.describe(),
            )
        )
    # Its merits and flaws taken as creation picks, as a player character's (#657).
    taken = creation_xp.due(db, npc)
    creation_xp.write(db, npc, taken, actor.id)
    npc.merits_flaws_xp = True
    total -= sum(line.amount for line in taken)
    if total > 0:
        db.add(
            XpEntry(
                character_id=npc.id,
                kind="award",
                amount=total,
                reason=f"Imported: what {name}'s sheet cost at {troupe.name}'s prices",
                entered_by=actor.id,
            )
        )
    if carried_xp:
        db.add(
            XpEntry(
                character_id=npc.id,
                kind="award",
                amount=carried_xp,
                reason="Unspent XP carried over"
                + (f": {carried_reason}" if carried_reason else ""),
                entered_by=actor.id,
            )
        )

    npc.kind = "pc"
    npc.player_id = to_player.id
    npc.owner_troupe_id = None
    npc.npc_kind = None
    npc.npc_form = None
    npc.npc_custom_kind = None
    npc.on_whos_who = False
    # Its picks are its own now, as a wizard-built character's are, and so are the
    # places its merits give (#566).
    npc_picks.hand_over_places(db, npc)
    npc.fits_picks = False
    npc.home_troupe_id = troupe.id
    npc.building_troupe_id = None
    db.execute(delete(NpcClaim).where(NpcClaim.character_id == npc.id))
    db.flush()
    # The sheet as its home troupe accepts it: the floor for lowering ratings, and
    # the start of its free changes, if the troupe gives them.
    freeze_sheet(db, actor, npc, troupe.id)

    for retainer in db.scalars(select(Retainer).where(Retainer.npc_id == npc.id)):
        owner = db.get_one(Character, retainer.character_id)
        retainer.npc_id = None
        audit.record(
            db,
            actor,
            "retainer.npc_given",
            troupe_id=owner.home_troupe_id or owner.owner_troupe_id,
            character_id=owner.id,
            name=retainer.name,
            npc=name,
            to_handle=to_player.handle,
        )
    db.flush()

    carried = (
        f" and {carried_xp} XP carried over" + (f" ({carried_reason})" if carried_reason else "")
        if carried_xp
        else ""
    )
    audit.record(
        db,
        actor,
        "npc.claimed" if claimed else "npc.given",
        troupe_id=troupe.id,
        character_id=npc.id,
        to_player_id=to_player.id,
        to_handle=to_player.handle,
        xp=total,
        carried_xp=carried_xp,
        carried=carried,
    )
    if not claimed:
        notify(
            db,
            [to_player.id],
            "npc.given",
            f"{name} is yours now: {troupe.name} gave it to you, at home there and accepted",
            f"/characters/{npc.id}",
            troupe_id=troupe.id,
            character_id=npc.id,
        )


# --- claim links -------------------------------------------------------------------


def claim_url(token: str) -> str:
    return f"{get_settings().public_url.rstrip('/')}/claim/{token}"


def live_claim(db: Session, npc: Character) -> NpcClaim | None:
    """The NPC's unused, unexpired claim link, if it has one."""
    return db.scalar(
        select(NpcClaim).where(
            NpcClaim.character_id == npc.id, NpcClaim.expires_at > datetime.now(UTC)
        )
    )


def make_claim(
    db: Session, staff: User, npc: Character, carried_xp: int = 0, carried_reason: str = ""
) -> tuple[str, datetime]:
    """A new claim link for the NPC, replacing any it had: its token and when it
    expires."""
    carried_xp, carried_reason = checked_carry(carried_xp, carried_reason)
    why = npc_refusal(npc)
    if why is not None:
        raise conflict(why)
    replaced = db.scalar(select(NpcClaim.id).where(NpcClaim.character_id == npc.id)) is not None
    db.execute(delete(NpcClaim).where(NpcClaim.character_id == npc.id))
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=CLAIM_DAYS)
    db.add(
        NpcClaim(
            character_id=npc.id,
            token_hash=hash_token(token),
            expires_at=expires_at,
            created_by_id=staff.id,
            carried_xp=carried_xp,
            carried_reason=carried_reason,
        )
    )
    db.flush()
    audit.record(
        db,
        staff,
        "npc.claim_link_remade" if replaced else "npc.claim_link_made",
        troupe_id=npc.owner_troupe_id,
        character_id=npc.id,
    )
    return token, expires_at


def cancel_claim(db: Session, staff: User, npc: Character) -> bool:
    """Cancel the NPC's claim link. Whether there was a live one to cancel."""
    live = live_claim(db, npc) is not None
    db.execute(delete(NpcClaim).where(NpcClaim.character_id == npc.id))
    db.flush()
    if live:
        audit.record(
            db,
            staff,
            "npc.claim_link_cancelled",
            troupe_id=npc.owner_troupe_id,
            character_id=npc.id,
        )
    return live


def claim_for(db: Session, token: str) -> NpcClaim | None:
    """The live claim link with this token, or None."""
    return db.scalar(
        select(NpcClaim).where(
            NpcClaim.token_hash == hash_token(token), NpcClaim.expires_at > datetime.now(UTC)
        )
    )


def claim(db: Session, user: User, token: str) -> Character:
    """`user` claims the NPC the link is for: it is given to them, as staff giving it
    would, and whoever made the link is told."""
    found = claim_for(db, token)
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This claim link has expired or been used. Ask the troupe for a new one.",
        )
    npc = db.get_one(Character, found.character_id)
    made_by, troupe_id = found.created_by_id, npc.owner_troupe_id
    give(db, user, npc, user, found.carried_xp, found.carried_reason, claimed=True)
    if made_by != user.id:
        notify(
            db,
            [made_by],
            "npc.claimed",
            f"@{user.handle} claimed {npc.name} with your claim link",
            f"/characters/{npc.id}",
            troupe_id=troupe_id,
            character_id=npc.id,
        )
    return npc

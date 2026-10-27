"""Moving a character from one player to another: the custodian's tool (#271).

A character belongs to its player through `characters.player_id`. Everything else
about it hangs off the character: its sheet and accepted sheets, XP, downtimes,
home troupe and visits, titles, status, Play View games, retainers and log. So a
move sets that one column and changes nothing else. Columns naming who did
something are history, and keep the old player. The player's own things (profile,
pronouns, notification settings) stay with the person.

Requests the old player made that are still waiting stay open: the new player is
the character's player now, so they see them and can withdraw them. A Play View
game under way refuses the move, so one game is not split between two people.

Undoing a move is another move, back. Merging two accounts (#272) moves each
character with `move`.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, play
from horatio.models import Approval, Character, Troupe, User
from horatio.notifications import approval_items, notify
from horatio.permissions import Role, troupe_role
from horatio.renames import troupes_of
from horatio.sheets import conflict, lock_character, unprocessable


@dataclass(frozen=True)
class Preview:
    """What moving the character to `to_player` would do."""

    character: Character
    from_player: User
    to_player: User
    # Its running troupes now: its home troupe, if it has one, and those it visits.
    home: Troupe | None
    visiting: list[Troupe]
    # Its requests waiting on a troupe, each as (what it asks, the troupe), which
    # stay open for the new player.
    open_requests: list[tuple[str, Troupe]]
    # The new player's role on the staff of each of its troupes they are on.
    staff_roles: list[tuple[Troupe, Role]]
    # Why it cannot be moved now, if it cannot.
    refusal: str | None


def refusal(db: Session, character: Character, to_player: User) -> str | None:
    """Why the character cannot be moved to `to_player` now, or None if it can."""
    if character.kind != "pc":
        return (
            f"{character.name} is an NPC: it belongs to its troupe, not a player,"
            " so it can't be moved."
        )
    if character.player_id == to_player.id:
        return f"{character.name} already belongs to @{to_player.handle}."
    game = play.current_game(db, character)
    if game is not None and play.game_events(db, game):
        return (
            f"{character.name} is in a game on the Play View. End it first with"
            " Reset for next game, so the game isn't split between two people."
        )
    return None


def preview(db: Session, character: Character, to_player: User) -> Preview:
    troupes = troupes_of(db, character)
    home = next((t for t in troupes if t.id == character.home_troupe_id), None)
    waiting = list(
        db.scalars(
            select(Approval)
            .where(Approval.character_id == character.id, Approval.status == "pending")
            .order_by(Approval.created_at)
        )
    )
    asked = {
        t.id: t
        for t in db.scalars(select(Troupe).where(Troupe.id.in_(a.troupe_id for a in waiting)))
    }
    items = approval_items(db, asked, [(a, character) for a in waiting])
    roles = [(t, troupe_role(db, to_player, t)) for t in troupes]
    return Preview(
        character=character,
        from_player=db.get_one(User, character.player_id),
        to_player=to_player,
        home=home,
        visiting=[t for t in troupes if t is not home],
        open_requests=[
            (item.summary, asked[a.troupe_id]) for item, a in zip(items, waiting, strict=True)
        ],
        staff_roles=[(t, role) for t, role in roles if role is not None],
        refusal=refusal(db, character, to_player),
    )


def move(
    db: Session,
    actor: User,
    character: Character,
    to_player: User,
    reason: str,
    *,
    tell: bool = True,
) -> None:
    """Give the character to `to_player`, as the custodian `actor`, for `reason`.
    Logged in each of its troupes (or once, if it is in none), and, if `tell`, the
    old and new players and its home troupe's lead storyteller are told. Callers
    check that `actor` is the custodian."""
    reason = reason.strip()
    if not reason:
        raise unprocessable("Give a reason for the move.")
    character = lock_character(db, character.id)
    why = refusal(db, character, to_player)
    if why is not None:
        raise conflict(why)
    from_player = db.get_one(User, character.player_id)
    character.player_id = to_player.id
    db.flush()

    troupes = troupes_of(db, character)
    for troupe_id in [t.id for t in troupes] or [None]:
        audit.record(
            db,
            actor,
            "character.moved",
            troupe_id=troupe_id,
            character_id=character.id,
            from_player_id=from_player.id,
            from_handle=from_player.handle,
            to_player_id=to_player.id,
            to_handle=to_player.handle,
            reason=reason,
        )
    if not tell:
        return

    name, link = character.name, f"/characters/{character.id}"
    home = next((t for t in troupes if t.id == character.home_troupe_id), None)
    told = {actor.id}
    # The old player can no longer open the character, so theirs goes to their vault.
    messages = [
        (
            from_player.id,
            f"The custodian moved {name} to @{to_player.handle}: {reason}",
            "/characters",
        ),
        (
            to_player.id,
            f"The custodian moved {name} to you from @{from_player.handle}: {reason}",
            link,
        ),
    ]
    if home is not None:
        messages.append(
            (
                home.lead_user_id,
                f"The custodian moved {name} from @{from_player.handle} to"
                f" @{to_player.handle}: {reason}",
                link,
            )
        )
    for user_id, summary, where in messages:
        if user_id in told:
            continue
        notify(
            db,
            [user_id],
            "character.moved",
            summary,
            where,
            troupe_id=home.id if home else None,
            character_id=None if user_id == from_player.id else character.id,
        )
        told.add(user_id)

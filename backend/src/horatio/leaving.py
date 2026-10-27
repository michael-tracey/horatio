"""Why a character left (issue #268). Retiring one (CONTEXT.md: Retired Character)
gives a reason, with an optional note for its log:

- Final Death;
- Off-field: alive, but away from the domain;
- Inactive: its player stopped playing it, which says nothing in game.

The reason is in-game information. A character with one can be listed under "No
longer with us" on the Who's Who of each troupe it was in (horatio.whos_who), as
its player chooses when retiring it, and its player or its home troupe's running
staff can change both later (horatio.permissions.can_change_leaving). A character
retired before reasons were kept has none, and is not listed until it is given one.
"""

from typing import Literal

from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, User
from horatio.renames import troupes_of

Reason = Literal["final_death", "off_field", "inactive"]

# How each reason reads, on the character and on the Who's Who.
REASONS: dict[str, str] = {
    "final_death": "Final Death",
    "off_field": "Off-field",
    "inactive": "Inactive",
}


def reason_name(reason: str | None) -> str | None:
    return REASONS.get(reason) if reason else None


def log(db: Session, user: User, action: str, character: Character, note: str) -> None:
    """Record why it left in the log of each troupe it is in, or its own if none."""
    for troupe_id in [t.id for t in troupes_of(db, character)] or [None]:
        audit.record(
            db,
            user,
            action,
            troupe_id=troupe_id,
            character_id=character.id,
            why=reason_name(character.left_reason) or "no reason given",
            listing="listed under No longer with us" if character.left_listed else "not listed",
            note=note.strip() or "No note.",
        )


def retire(
    db: Session, user: User, character: Character, reason: Reason | None, note: str, listed: bool
) -> None:
    """Retire the character, for `reason`: listed on the Who's Who if `listed`, which
    needs a reason."""
    character.status = "retired"
    character.left_reason = reason
    character.left_listed = listed and reason is not None
    log(db, user, "character.retired", character, note)


def change(
    db: Session, user: User, character: Character, reason: Reason, note: str, listed: bool
) -> None:
    """Change why a retired character left, or whether the Who's Who lists it."""
    if (character.left_reason, character.left_listed) == (reason, listed) and not note.strip():
        return
    character.left_reason = reason
    character.left_listed = listed
    log(db, user, "character.leaving", character, note)

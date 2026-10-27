"""Pronouns (issue #265): a character's, set by its player (or an NPC's, by its
troupe's staff), and a player's own, on their profile. Both are optional free text,
such as "she/her", "they/them" or "any"; the app suggests the usual ones. An empty
field shows nothing.

A character's pronouns show on its page, the troupe's Characters tab and Who's Who,
and the Play View's Others at this game; a troupe's badges print them if it chooses
(Troupe.badge_pronouns). A player's show beside their name wherever other players
see it, in every troupe, and are never printed on a badge.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, User

MAX_PRONOUNS = 40


def clean(text: str | None) -> str | None:
    """The pronouns as they are to be kept: trimmed, or None for none."""
    text = " ".join((text or "").split())
    if len(text) > MAX_PRONOUNS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Keep pronouns to {MAX_PRONOUNS} characters.",
        )
    return text or None


def set_character(db: Session, user: User, character: Character, text: str | None) -> None:
    """Set the character's pronouns. Callers check that `user` may change it."""
    pronouns = clean(text)
    if pronouns == character.pronouns:
        return
    character.pronouns = pronouns
    audit.record(
        db,
        user,
        "character.pronouns",
        troupe_id=character.owner_troupe_id or character.home_troupe_id,
        character_id=character.id,
        pronouns=pronouns or "none",
    )

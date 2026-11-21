"""What happens when a player links their own Discord account (#857).

Linking records the Discord account's id on the player (`users.discord_user_id`),
verified by Discord itself, where `users.discord_handle` is only what they typed.
Anything that waited on a typed handle being confirmed can stop waiting then.

Managed character channels (#855) keep staff confirmations of typed-handle
matches: linking resolves the player's pending and confirmed ones in favour of the
verified account, and marks their characters waiting on a match ready to make
(horatio.discord_channels.linked).

Since #1128 a linked Discord account also signs in, and an `auth_identities` row
with provider "discord" names it as well: `keep_identity` keeps that row in step
with `discord_user_id` whenever either changes.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio import discord_channels
from horatio.models import AuthIdentity, User


def account_linked(db: Session, user: User) -> None:
    """Called in the same transaction as a player's Discord account is linked: the
    verified account takes over any typed-handle match a troupe kept for them."""
    discord_channels.linked(db, user)


def holder_of(db: Session, discord_id: str) -> User | None:
    """The Horatio account a Discord account is linked to, merged or not: the one
    whose `discord_user_id` it is, or, failing that, one not linked to any other
    whose identity row names it."""
    holder = db.scalars(select(User).where(User.discord_user_id == discord_id)).first()
    if holder is not None:
        return holder
    return db.scalars(
        select(User)
        .join(AuthIdentity, AuthIdentity.user_id == User.id)
        .where(
            AuthIdentity.provider == "discord",
            AuthIdentity.subject == discord_id,
            User.discord_user_id.is_(None),
        )
    ).first()


def keep_identity(db: Session, user: User) -> None:
    """Make the Discord identity rows agree with the person's `discord_user_id`: one
    for it, if they have one, theirs and no one else's, and none for any other."""
    linked = user.discord_user_id
    discord_rows = AuthIdentity.provider == "discord"
    stale = delete(AuthIdentity).where(discord_rows, AuthIdentity.user_id == user.id)
    if linked is not None:
        stale = stale.where(AuthIdentity.subject != linked)
        # `discord_user_id` is unique, so a row naming it for anyone else is out of date.
        db.execute(
            delete(AuthIdentity).where(
                discord_rows, AuthIdentity.subject == linked, AuthIdentity.user_id != user.id
            )
        )
    db.execute(stale)
    if linked is None:
        return
    has = db.scalars(
        select(AuthIdentity.id).where(discord_rows, AuthIdentity.subject == linked)
    ).first()
    if has is None:
        db.add(AuthIdentity(user_id=user.id, provider="discord", subject=linked))
        db.flush()

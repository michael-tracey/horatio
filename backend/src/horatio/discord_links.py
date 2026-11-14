"""What happens when a player links their own Discord account (#857).

Linking records the Discord account's id on the player (`users.discord_user_id`),
verified by Discord itself, where `users.discord_handle` is only what they typed.
Anything that waited on a typed handle being confirmed can stop waiting then.

Managed character channels (#855) keep staff confirmations of typed-handle
matches: linking resolves the player's pending and confirmed ones in favour of the
verified account, and marks their characters waiting on a match ready to make
(horatio.discord_channels.linked).
"""

from sqlalchemy.orm import Session

from horatio import discord_channels
from horatio.models import User


def account_linked(db: Session, user: User) -> None:
    """Called in the same transaction as a player's Discord account is linked: the
    verified account takes over any typed-handle match a troupe kept for them."""
    discord_channels.linked(db, user)

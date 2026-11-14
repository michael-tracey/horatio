"""What happens when a player links their own Discord account (#857).

Linking records the Discord account's id on the player (`users.discord_user_id`),
verified by Discord itself, where `users.discord_handle` is only what they typed.
Anything that waited on a typed handle being confirmed can stop waiting then.

Managed character channels (#855) keep staff confirmations of typed-handle
matches: `account_linked` is where that ticket resolves the player's pending ones.
Until then it does nothing.
"""

from sqlalchemy.orm import Session

from horatio.models import User


def account_linked(db: Session, user: User) -> None:
    """Called in the same transaction as a player's Discord account is linked.
    #855 resolves that player's pending typed-handle confirmations here."""
    return None

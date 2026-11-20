from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class AuthAttempt(Record):
    """A sign-in or sign-up tried, counted against the limits (horatio.auth.attempts).
    Kept a day at most."""

    __tablename__ = "auth_attempts"
    __table_args__ = (
        # Forgetting those over a day old.
        Index("ix_auth_attempts_created_at", "created_at"),
        Index("ix_auth_attempts_action_ip_created_at", "action", "ip_address", "created_at"),
        Index(
            "ix_auth_attempts_action_identity_ip_created_at",
            "action",
            "identity_hash",
            "ip_address",
            "created_at",
        ),
    )

    # sign_in or sign_up.
    action: Mapped[str] = mapped_column(String(32))
    # A sign-in's login, hashed (attempts.login_key): never what was typed.
    identity_hash: Mapped[str | None] = mapped_column(String(64))
    # Where it came from (attempts.source): an IP address, or an IPv6 /64.
    ip_address: Mapped[str | None] = mapped_column(String(64))

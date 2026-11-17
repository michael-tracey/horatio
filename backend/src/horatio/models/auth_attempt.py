from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class AuthAttempt(Record):
    """A short-lived login or signup attempt used for shared request throttles."""

    __tablename__ = "auth_attempts"
    __table_args__ = (
        Index("ix_auth_attempts_action_created_at", "action", "created_at"),
        Index("ix_auth_attempts_action_ip_created_at", "action", "ip_address", "created_at"),
        Index(
            "ix_auth_attempts_action_identity_ip_created_at",
            "action",
            "identity_hash",
            "ip_address",
            "created_at",
        ),
    )

    action: Mapped[str] = mapped_column(String(32))
    # Login identifiers are hashed before they reach this table. IP addresses are
    # retained only for the one-day throttling window.
    identity_hash: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))

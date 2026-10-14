import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Imported, Record


class User(Imported, Record):
    """A person who signs in: a player, staff member or custodian."""

    __tablename__ = "users"
    __table_args__ = (
        # Emails are unique regardless of case.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    email: Mapped[str]
    display_name: Mapped[str]
    # Null for people who only sign in through Discord or Google.
    password_hash: Mapped[str | None]
    is_custodian: Mapped[bool] = mapped_column(default=False, server_default="false")
    discord_user_id: Mapped[str | None] = mapped_column(unique=True)


class AuthIdentity(Record):
    """A sign-in provider account linked to a user."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject"),
        CheckConstraint("provider in ('discord', 'google')", name="provider"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str]
    subject: Mapped[str]


class Session(Record):
    """A server-side sign-in session; the cookie holds the token, the table its hash."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

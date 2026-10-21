import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
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
    # The player's profile, which anyone signed in can see (CONTEXT.md: Profile).
    bio: Mapped[str | None] = mapped_column(Text)
    # Social media: [{"label": "Bluesky", "url": "https://bsky.app/profile/..."}].
    links: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # The Discord username the player gives, such as "mrcarbuncle". Not checked
    # against Discord; `discord_user_id` is the account they sign in with.
    discord_handle: Mapped[str | None]
    # Their settings (horatio.preferences): only those they have changed, so a
    # default can change later for everyone who kept it.
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


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


class PasswordReset(Record):
    """A one-time link the custodian makes for someone locked out. The link holds
    the token, the table its hash. Used or replaced, the row is deleted."""

    __tablename__ = "password_resets"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

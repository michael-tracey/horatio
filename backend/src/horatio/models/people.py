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
        # Emails are unique regardless of case, among accounts not merged into
        # another: a merged account keeps its email for the record, freed for use.
        Index(
            "uq_users_email_lower",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("merged_into_id is null"),
        ),
        # So are handles. A merged account's handle is held for good by the account
        # it was merged into, as a former handle (horatio.account_merges).
        Index(
            "uq_users_handle_lower",
            text("lower(handle)"),
            unique=True,
            postgresql_where=text("merged_into_id is null"),
        ),
    )

    email: Mapped[str]
    display_name: Mapped[str]
    # How others find and see them, instead of their email (horatio.handles),
    # kept as they typed it.
    handle: Mapped[str]
    # When they last changed their handle, which they can do once in 30 days.
    handle_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    # Their pronouns, shown beside their name to other players (horatio.pronouns).
    pronouns: Mapped[str | None]
    # Their settings (horatio.preferences): only those they have changed, so a
    # default can change later for everyone who kept it.
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Signs the unsubscribe links in their notification emails
    # (horatio.notification_emails). A new key cancels every link sent so far.
    unsubscribe_key: Mapped[uuid.UUID] = mapped_column(server_default=text("gen_random_uuid()"))
    # The account this one was merged into by the custodian, the same person signed
    # up twice (horatio.account_merges): closed, kept only as the record of what
    # it did.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FormerHandle(Record):
    """A handle someone changed from, held for them for a while: no one else can
    take it, and finding people by it still finds them (horatio.handles)."""

    __tablename__ = "former_handles"
    __table_args__ = (Index("ix_former_handles_handle_lower", text("lower(handle)")),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    handle: Mapped[str]
    held_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class Suspension(Record):
    """The custodian suspending someone's account (horatio.suspensions): signed out
    and kept out until it is lifted, by hand or when `ends_at` passes. Kept once
    lifted, so every suspension stays on record."""

    __tablename__ = "suspensions"
    __table_args__ = (
        # At most one not yet lifted for each person.
        Index(
            "uq_suspensions_live_user_id",
            "user_id",
            unique=True,
            postgresql_where=text("lifted_at is null"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # Why, for the custodian only: never shown to the person.
    reason: Mapped[str] = mapped_column(Text)
    # When it ends by itself; None until it is lifted by hand.
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # When it was lifted: by hand (with who and why), or at `ends_at` with neither.
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lift_reason: Mapped[str | None] = mapped_column(Text)

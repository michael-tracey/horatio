"""Two-step sign-in (#1057): the second steps people set up, and sign-ins waiting on
one (horatio.auth.two_step)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class AuthenticatorApp(Record):
    """The authenticator app someone set up: the secret it shares with Horatio, from
    which both make a six-digit code every 30 seconds (TOTP). One per person."""

    __tablename__ = "authenticator_apps"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    # The secret, encrypted with the server's HORATIO_TOTP_KEY (horatio.auth.two_step),
    # so the database alone doesn't give it away.
    secret: Mapped[bytes] = mapped_column(LargeBinary)
    # When they gave a first code from it, which turns it on. Until then it is being
    # set up, and signs no one in.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The 30-second step of the last code it signed in with, so no code works twice.
    last_step: Mapped[int | None] = mapped_column(BigInteger)


class RecoveryCode(Record):
    """A one-time code for signing in without the second step someone has lost. Only
    its hash is kept; used, it is spent."""

    __tablename__ = "recovery_codes"
    __table_args__ = (UniqueConstraint("user_id", "code_hash"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Passkey(Record):
    """A passkey someone set up (WebAuthn): a key their device or password manager
    keeps, which signs Horatio's challenge. Horatio keeps only its public half."""

    __tablename__ = "passkeys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    # The authenticator's count of signatures, which only goes up: one going back
    # means the key was copied.
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    # How the browser can reach it ("internal", "hybrid", "usb"...), as it said.
    transports: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    # As the person named it, such as "Phone".
    name: Mapped[str]
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SecondStepSignIn(Record):
    """A sign-in whose password was right, waiting on its second step: no session yet.
    A cookie holds its token, the table its hash. Gone once signed in, or after a few
    wrong codes, and good for 10 minutes."""

    __tablename__ = "second_step_sign_ins"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # The login they gave with their password, hashed (horatio.auth.attempts), so its
    # tries count as signed in once this one is; None after a reset link.
    login_hash: Mapped[str | None] = mapped_column(String(64))
    # The challenge a passkey must sign for it, while one is asked for.
    challenge: Mapped[bytes | None] = mapped_column(LargeBinary)
    failures: Mapped[int] = mapped_column(default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

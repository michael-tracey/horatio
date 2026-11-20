"""Two-step sign-in (#1057): after the password, a second step, from an authenticator
app (TOTP) or a passkey, with one-time recovery codes for when it's lost.

**Signing in.** Someone with a second step who gives the right password gets no
session: they get a sign-in waiting on its second step (`SecondStepSignIn`), named by
a cookie of its own, good for 10 minutes and for 5 wrong codes. Only the second step
starts the session. A reset link sets a new password the same way: it never signs
anyone with a second step in by itself. Wrong codes count against limits of their
own, from where they come and at the account from anywhere (horatio.auth.attempts),
and each try and each turn away is in the audit log.

**Codes.** An authenticator app's code is good for its 30 seconds and the steps
either side, for a phone's clock that is a little out, and works once: the step of
the last code used is kept. Its secret is kept encrypted with the server's key
(`totp_key`, AES-GCM, bound to the person), so a copy of the database alone can't
make codes. Recovery codes are random, 10 at a time; only their hashes are kept,
and each works once.

**Who must have one.** The custodian (`two_step_for_custodians`), and the staff of a
troupe whose lead storyteller asks it of them. Until someone who must has one, every
request of theirs is refused but those that set one up, and the app sends them to do
that first (`two_step_first`). The custodian resets the second steps of anyone who
has lost theirs, as a notice; on the server, `python -m horatio.auth.two_step reset
EMAIL` does it for the custodian.
"""

import base64
import hashlib
import hmac
import secrets
import sys
import time
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import pyotp
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, HTTPException, Request, status
from pyotp.totp import TOTP
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.orm import Session

from horatio.audit import record
from horatio.auth.sessions import hash_token, user_for_token
from horatio.config import get_settings
from horatio.db import get_session, get_sessionmaker
from horatio.models import (
    AuthenticatorApp,
    Passkey,
    RecoveryCode,
    SecondStepSignIn,
    User,
)

ISSUER = "Horatio"
# A sign-in waiting on its second step: how long, and how many wrong codes, it lasts.
SIGN_IN_FOR = timedelta(minutes=10)
WRONG_CODES = 5
COOKIE = "horatio_second_step"
RECOVERY_CODES = 10
# Letters and digits that can't be mistaken for each other.
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
RECOVERY_LENGTH = 10

NEEDED = "Set up two-step sign-in first: you need it to go on."
NO_KEY = "Authenticator apps can't be set up on this server yet. Ask the custodian."


def now() -> float:
    """The current time, in seconds; tests replace this."""
    return time.time()


# --- the key -------------------------------------------------------------------------------


def new_key() -> str:
    """A new key for HORATIO_TOTP_KEY: 32 random bytes, base64url."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def _cipher() -> AESGCM | None:
    raw = get_settings().totp_key
    if not raw:
        return None
    try:
        key = base64.urlsafe_b64decode(raw.strip())
    except ValueError:
        return None
    return AESGCM(key) if len(key) == 32 else None


def apps_available() -> bool:
    """Whether authenticator apps can be set up here: the server has a good key."""
    return _cipher() is not None


def _bound_to(user_id: uuid.UUID) -> bytes:
    return b"horatio authenticator app " + user_id.bytes


def encrypt(user_id: uuid.UUID, secret: str) -> bytes:
    cipher = _cipher()
    if cipher is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_KEY)
    nonce = secrets.token_bytes(12)
    return nonce + cipher.encrypt(nonce, secret.encode(), _bound_to(user_id))


def decrypt(user_id: uuid.UUID, sealed: bytes) -> str | None:
    """The secret, or None if this server's key didn't seal it."""
    cipher = _cipher()
    if cipher is None:
        return None
    try:
        return cipher.decrypt(sealed[:12], sealed[12:], _bound_to(user_id)).decode()
    except InvalidTag:
        return None


# --- what someone has ----------------------------------------------------------------------


def app_for(db: Session, user: User) -> AuthenticatorApp | None:
    """Their authenticator app, set up or being set up."""
    return db.scalar(select(AuthenticatorApp).where(AuthenticatorApp.user_id == user.id))


def has_app(db: Session, user: User) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    AuthenticatorApp.user_id == user.id, AuthenticatorApp.confirmed_at.is_not(None)
                )
            )
        )
    )


def passkey_count(db: Session, user: User) -> int:
    return db.scalar(select(func.count()).where(Passkey.user_id == user.id)) or 0


def second_steps(db: Session, user: User) -> int:
    """How many second steps they have: their authenticator app, and each passkey."""
    return int(has_app(db, user)) + passkey_count(db, user)


def has_second_step(db: Session, user: User) -> bool:
    """Whether a password alone no longer signs them in."""
    return has_app(db, user) or passkey_count(db, user) > 0


def with_second_step(db: Session, user_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Which of `user_ids` have a second step."""
    ids = list(set(user_ids))
    if not ids:
        return set()
    apps = select(AuthenticatorApp.user_id).where(
        AuthenticatorApp.user_id.in_(ids), AuthenticatorApp.confirmed_at.is_not(None)
    )
    keys = select(Passkey.user_id).where(Passkey.user_id.in_(ids))
    return set(db.scalars(apps.union(keys)))


def recovery_codes_left(db: Session, user: User) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
            )
        )
        or 0
    )


def required_by(db: Session, user: User) -> list[str]:
    """Why they must have a second step: "the custodian", for the custodian. Empty if
    they needn't."""
    why: list[str] = []
    if user.is_custodian and get_settings().two_step_for_custodians:
        why.append("the custodian")
    return why


def needed(db: Session, user: User) -> bool:
    """Whether they must set up a second step before anything else: they must have
    one, have none, and this server has a way to set one up."""
    return bool(required_by(db, user)) and apps_available() and not has_second_step(db, user)


# --- authenticator apps --------------------------------------------------------------------


def otpauth_uri(user: User, secret: str) -> str:
    """What the app scans: "otpauth://totp/Horatio:agnes?secret=...&issuer=Horatio"."""
    return TOTP(secret).provisioning_uri(name=f"@{user.handle}", issuer_name=ISSUER)


def start_app(db: Session, user: User) -> str:
    """Start setting up an authenticator app, in place of any being set up: the new
    secret, base32."""
    if has_app(db, user):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You have an authenticator app set up. Turn it off first to set up another.",
        )
    secret = pyotp.random_base32()
    db.execute(delete(AuthenticatorApp).where(AuthenticatorApp.user_id == user.id))
    db.add(AuthenticatorApp(user_id=user.id, secret=encrypt(user.id, secret)))
    db.flush()
    return secret


def matching_step(secret: str, code: str, after: int | None) -> int | None:
    """The 30-second step `code` belongs to, if it is right for now or a step either
    side and later than `after`."""
    totp = TOTP(secret)
    current = totp.timecode(int(now()))
    for step in (current - 1, current, current + 1):
        if after is not None and step <= after:
            continue
        if hmac.compare_digest(totp.generate_otp(step), code):
            return step
    return None


def digits(code: str) -> str:
    return "".join(code.split())


def is_app_code(code: str) -> bool:
    """Whether `code` looks like an authenticator app's: six digits."""
    code = digits(code)
    return len(code) == 6 and code.isascii() and code.isdigit()


def check_app(db: Session, user: User, code: str, *, setting_up: bool = False) -> bool:
    """Whether `code` is right for their app (the one being set up, if `setting_up`),
    using it up if so. Taken under a row lock, so one code can't sign in twice at once."""
    app = db.scalar(
        select(AuthenticatorApp).where(AuthenticatorApp.user_id == user.id).with_for_update()
    )
    if app is None or (app.confirmed_at is None) != setting_up or not is_app_code(code):
        return False
    secret = decrypt(user.id, app.secret)
    if secret is None:
        return False
    step = matching_step(secret, digits(code), app.last_step)
    if step is None:
        return False
    app.last_step = step
    if setting_up:
        app.confirmed_at = datetime.now(UTC)
    db.flush()
    return True


def remove_app(db: Session, user: User) -> None:
    db.execute(delete(AuthenticatorApp).where(AuthenticatorApp.user_id == user.id))
    db.flush()


# --- recovery codes ------------------------------------------------------------------------


def _normal(code: str) -> str:
    return "".join(c for c in code.lower() if c.isalnum())


def hash_code(user_id: uuid.UUID, code: str) -> str:
    """A recovery code's hash. The codes are random enough that a fast hash is safe;
    the account is in it, so one hash can't be tried against everyone's."""
    return hashlib.sha256(f"{user_id}:{_normal(code)}".encode()).hexdigest()


def new_recovery_codes(db: Session, user: User) -> list[str]:
    """Ten new codes in place of any they had, shown once: "abcde-fghjk"."""
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    codes: list[str] = []
    for _ in range(RECOVERY_CODES):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_LENGTH))
        codes.append(f"{raw[:5]}-{raw[5:]}")
        db.add(RecoveryCode(user_id=user.id, code_hash=hash_code(user.id, raw)))
    db.flush()
    return codes


def use_recovery_code(db: Session, user: User, code: str) -> bool:
    """Whether `code` is one of their recovery codes not yet used; if so it is used now.
    One statement, so two requests can't both use it."""
    if len(_normal(code)) != RECOVERY_LENGTH:
        return False
    used = db.execute(
        update(RecoveryCode)
        .where(
            RecoveryCode.user_id == user.id,
            RecoveryCode.code_hash == hash_code(user.id, code),
            RecoveryCode.used_at.is_(None),
        )
        .values(used_at=func.now())
        .returning(RecoveryCode.id)
    ).first()
    return used is not None


def forget_all(db: Session, user: User) -> None:
    """Every second step they have, their recovery codes, and sign-ins waiting on one:
    after the custodian resets them, or when they turn off the last one."""
    for model in (AuthenticatorApp, Passkey, RecoveryCode, SecondStepSignIn):
        db.execute(delete(model).where(model.user_id == user.id))
    db.flush()


def methods(db: Session, user: User) -> list[str]:
    """The second steps they can sign in with now: "app", "passkey", "recovery_code"."""
    found: list[str] = []
    if has_app(db, user):
        found.append("app")
    if passkey_count(db, user):
        found.append("passkey")
    if recovery_codes_left(db, user):
        found.append("recovery_code")
    return found


# --- sign-ins waiting on their second step -------------------------------------------------


def begin(db: Session, user: User, login_hash: str | None) -> str:
    """A sign-in for `user` waiting on its second step: the token for its cookie."""
    db.execute(delete(SecondStepSignIn).where(SecondStepSignIn.expires_at <= func.now()))
    token = secrets.token_urlsafe(32)
    db.add(
        SecondStepSignIn(
            user_id=user.id,
            token_hash=hash_token(token),
            login_hash=login_hash,
            expires_at=datetime.now(UTC) + SIGN_IN_FOR,
        )
    )
    db.flush()
    return token


def waiting(db: Session, token: str | None) -> SecondStepSignIn | None:
    """The sign-in a cookie's token names, if it is still waiting, locked for this
    request: never a merged account's."""
    if not token:
        return None
    return db.scalar(
        select(SecondStepSignIn)
        .join(User, SecondStepSignIn.user_id == User.id)
        .where(
            SecondStepSignIn.token_hash == hash_token(token),
            SecondStepSignIn.expires_at > func.now(),
            User.merged_into_id.is_(None),
        )
        .with_for_update(of=SecondStepSignIn)
    )


def wrong(db: Session, signing_in: SecondStepSignIn) -> bool:
    """Count a wrong code against the sign-in; whether that was its last."""
    signing_in.failures += 1
    if signing_in.failures >= WRONG_CODES:
        db.delete(signing_in)
        db.flush()
        return True
    db.flush()
    return False


# --- refusing everything else until it's set up --------------------------------------------

# Routes someone who must set up a second step may still use: setting it up, and
# what any page needs to know who they are or to sign out.
ALLOWED_FIRST: set[Callable[..., Any]] = set()


def allowed_first[F: Callable[..., Any]](endpoint: F) -> F:
    ALLOWED_FIRST.add(endpoint)
    return endpoint


def two_step_first(request: Request, db: Annotated[Session, Depends(get_session)]) -> None:
    """For every API route: refuse someone signed in who must set up a second step and
    hasn't, but for the routes that set it up. Their own sign-in, even while the
    custodian views as someone."""
    route = request.scope.get("route")
    if getattr(route, "endpoint", None) in ALLOWED_FIRST:
        return
    token = request.cookies.get(get_settings().session_cookie_name)
    user = user_for_token(db, token) if token else None
    if user is not None and needed(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, NEEDED)


# --- on the server -------------------------------------------------------------------------

USAGE = (
    "usage: python -m horatio.auth.two_step          print a new HORATIO_TOTP_KEY\n"
    "       python -m horatio.auth.two_step reset EMAIL   reset someone's second steps"
)


def reset_on_server(email: str) -> int:
    """For the custodian who has lost their own second step, with no other custodian
    to reset it: run on the server, recorded as a notice by Horatio itself."""
    with get_sessionmaker()() as db, db.begin():
        user = db.scalar(
            select(User).where(
                func.lower(User.email) == email.lower(), User.merged_into_id.is_(None)
            )
        )
        if user is None:
            print(f"No account with email {email}.", file=sys.stderr)
            return 1
        forget_all(db, user)
        record(
            db,
            None,
            "account.two_step_reset",
            member=user.display_name,
            user_id=user.id,
            kind="server",
        )
    print(f"{email} has no second step now, and can sign in with their password.")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(f"HORATIO_TOTP_KEY={new_key()}")
        return 0
    if len(argv) == 2 and argv[0] == "reset":
        return reset_on_server(argv[1])
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

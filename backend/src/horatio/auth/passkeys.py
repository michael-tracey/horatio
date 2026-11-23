"""Passkeys as a second step (#1057), with py_webauthn: a key someone's phone, computer
or password manager keeps, which signs a fresh challenge from Horatio. Horatio keeps
only the public half, so a copy of the database gives nothing away.

A passkey belongs to one site, its relying party: Horatio's host (`webauthn_rp_id`,
from `public_url` unless set), signed for its origin (`webauthn_origin`, likewise).
Each challenge works once: adding a passkey keeps its challenge with the sign-in
session adding it, and signing in keeps it with the sign-in waiting on its second
step. A passkey's count of signatures only goes up; one that goes back was copied,
and is refused.

A passkey can also sign in alone, with no password (#1098). The browser then offers
whichever passkeys it keeps for Horatio, so only discoverable ones (kept with the
account they belong to) can, and the device must check the person's face, finger or
PIN, which makes it both steps at once. Its challenge waits on the server, in
`passkey_sign_ins`, named by a cookie: it works once, for 5 minutes.
"""

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from horatio.auth.sessions import hash_token
from horatio.config import get_settings
from horatio.models import Passkey, PasskeySignIn, SecondStepSignIn, User
from horatio.models import Session as SignInSession

NAME = "Horatio"


def relying_party() -> tuple[str, str]:
    """The site passkeys belong to, and the origin they're signed for."""
    settings = get_settings()
    url = urlsplit(settings.public_url)
    rp_id = settings.webauthn_rp_id or url.hostname or "localhost"
    origin = settings.webauthn_origin or f"{url.scheme}://{url.netloc}"
    return rp_id, origin.rstrip("/")


def available() -> bool:
    """Whether browsers will make passkeys for this site: over https, or on localhost."""
    rp_id, origin = relying_party()
    return origin.startswith("https://") or rp_id == "localhost"


def _transports(names: list[Any]) -> list[AuthenticatorTransport]:
    known = {t.value: t for t in AuthenticatorTransport}
    return [known[n] for n in names if isinstance(n, str) and n in known]


def mine(db: Session, user: User) -> list[Passkey]:
    return list(
        db.scalars(
            select(Passkey)
            .where(Passkey.user_id == user.id)
            .order_by(Passkey.created_at, Passkey.id)
        )
    )


def _descriptors(
    db: Session, user: User, *, discoverable_only: bool = False
) -> list[PublicKeyCredentialDescriptor]:
    return [
        PublicKeyCredentialDescriptor(id=p.credential_id, transports=_transports(p.transports))
        for p in mine(db, user)
        if p.discoverable or not discoverable_only
    ]


def adding_options(
    db: Session, session: SignInSession, user: User, *, alone: bool = False
) -> dict[str, Any]:
    """What the browser needs to make a new passkey for `user`, as JSON; its challenge
    is kept with the sign-in session making it. Discoverable where the device can, so
    it can sign in alone, and the browser is asked to say whether it is (credProps).
    A device holding one that may not be discoverable may make a new one in its place.
    With `alone`, for one replacing such a passkey (#1110), the device must make one
    that signs in alone, discoverable and checking the person's face, finger or PIN,
    or make none."""
    rp_id, _ = relying_party()
    required = ResidentKeyRequirement.REQUIRED if alone else ResidentKeyRequirement.PREFERRED
    verified = (
        UserVerificationRequirement.REQUIRED if alone else UserVerificationRequirement.PREFERRED
    )
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=NAME,
        user_id=user.id.bytes,
        user_name=f"@{user.handle}",
        user_display_name=user.display_name,
        exclude_credentials=_descriptors(db, user, discoverable_only=True),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=required, user_verification=verified
        ),
    )
    session.passkey_challenge = options.challenge
    db.flush()
    made: dict[str, Any] = json.loads(options_to_json(options))
    made["extensions"] = {"credProps": True}
    return made


def _discoverable(credential: dict[str, Any]) -> bool | None:
    """Whether the browser said the passkey it made is discoverable; None if it didn't."""
    results = credential.get("clientExtensionResults")
    props = results.get("credProps") if isinstance(results, dict) else None
    rk = props.get("rk") if isinstance(props, dict) else None
    return rk if isinstance(rk, bool) else None


def add(
    db: Session,
    session: SignInSession,
    user: User,
    credential: dict[str, Any],
    name: str,
    *,
    alone: bool = False,
) -> Passkey:
    """Keep the passkey the browser made, once its answer checks out. With `alone`
    (adding_options' own), it must sign in alone: the person verified, and not one the
    browser says isn't discoverable. One the browser says nothing of is, as the device
    was told to make it so or make none."""
    challenge = session.passkey_challenge
    session.passkey_challenge = None
    if challenge is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Start adding a passkey again.")
    rp_id, origin = relying_party()
    try:
        made = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=alone,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That passkey couldn't be added. Try again."
        ) from error
    if db.scalar(select(Passkey).where(Passkey.credential_id == made.credential_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That passkey is set up already.")
    discoverable = _discoverable(credential)
    if alone and discoverable is False:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "This device can't keep a passkey that signs you in alone.",
        )
    transports = credential.get("response", {}).get("transports", [])
    if not isinstance(transports, list):
        transports = []
    passkey = Passkey(
        user_id=user.id,
        credential_id=made.credential_id,
        public_key=made.credential_public_key,
        sign_count=made.sign_count,
        transports=[t.value for t in _transports(transports)],
        name=name.strip() or "Passkey",
        discoverable=True if alone else discoverable,
    )
    db.add(passkey)
    db.flush()
    return passkey


def sign_in_options(db: Session, waiting: SecondStepSignIn, user: User) -> dict[str, Any]:
    """What the browser needs to sign with one of `user`'s passkeys, as JSON; its
    challenge is kept with the sign-in waiting on it."""
    rp_id, _ = relying_party()
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=_descriptors(db, user),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    waiting.challenge = options.challenge
    db.flush()
    return json.loads(options_to_json(options))


def check(db: Session, waiting: SecondStepSignIn, user: User, credential: dict[str, Any]) -> bool:
    """Whether `credential` is one of `user`'s passkeys signing the sign-in's challenge.
    The challenge is used up either way."""
    challenge = waiting.challenge
    waiting.challenge = None
    db.flush()
    return signs(db, user, challenge, credential)


def asking_options(db: Session, session: SignInSession, user: User) -> dict[str, Any]:
    """What the browser needs to sign with one of `user`'s passkeys again, signed in, as
    JSON: for switching on custodian access (horatio.api.custodian_access). Its
    challenge is kept with the sign-in session, as one for a passkey being added is."""
    rp_id, _ = relying_party()
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=_descriptors(db, user),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    session.passkey_challenge = options.challenge
    db.flush()
    return json.loads(options_to_json(options))


def check_asked(
    db: Session, session: SignInSession, user: User, credential: dict[str, Any]
) -> bool:
    """Whether `credential` is one of `user`'s passkeys signing `asking_options`'
    challenge. The challenge is used up either way."""
    challenge = session.passkey_challenge
    session.passkey_challenge = None
    db.flush()
    return signs(db, user, challenge, credential)


def signs(db: Session, user: User, challenge: bytes | None, credential: dict[str, Any]) -> bool:
    """Whether `credential` is one of `user`'s passkeys signing `challenge`."""
    raw = credential.get("rawId") or credential.get("id")
    if challenge is None or not isinstance(raw, str):
        return False
    try:
        credential_id = base64url_to_bytes(raw)
    except ValueError:
        return False
    passkey = db.scalar(
        select(Passkey)
        .where(Passkey.user_id == user.id, Passkey.credential_id == credential_id)
        .with_for_update()
    )
    if passkey is None:
        return False
    return _signed(db, passkey, challenge, credential, verified=False)


def _signed(
    db: Session, passkey: Passkey, challenge: bytes, credential: dict[str, Any], *, verified: bool
) -> bool:
    """Whether `credential` is `passkey` signing `challenge`, with the person verified
    (face, finger or PIN) if `verified`. If so, its count and last use are kept."""
    rp_id, origin = relying_party()
    try:
        signed = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=verified,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError):
        return False
    passkey.sign_count = signed.new_sign_count
    passkey.last_used_at = datetime.now(UTC)
    db.flush()
    return True


# --- signing in with a passkey alone (#1098) ------------------------------------------------

COOKIE = "horatio_passkey_sign_in"
CHALLENGE_FOR = timedelta(minutes=5)
# How many may wait from one place at once, while sign-ins are limited: each sign-in
# page opened there asks for one, and a whole troupe may sign in together on a venue's
# Wi-Fi. Only so the table can't be filled without end.
WAITING_FROM_ONE_PLACE = 200


def alone_options(db: Session, ip: str | None) -> tuple[str, dict[str, Any]]:
    """What the browser needs to sign in with a passkey alone, as JSON, naming no
    account, so the browser offers any of its passkeys for Horatio; and the token for
    the cookie naming its challenge, kept here. 429 if too many wait from `ip`."""
    db.execute(delete(PasskeySignIn).where(PasskeySignIn.expires_at <= func.now()))
    from_there = PasskeySignIn.ip_address == ip if ip else PasskeySignIn.ip_address.is_(None)
    waiting = db.scalar(select(func.count()).where(from_there)) or 0
    if get_settings().auth_limits and waiting >= WAITING_FROM_ONE_PLACE:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many sign-ins from here. Try again later."
        )
    rp_id, _ = relying_party()
    options = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED
    )
    token = secrets.token_urlsafe(32)
    db.add(
        PasskeySignIn(
            token_hash=hash_token(token),
            challenge=options.challenge,
            ip_address=ip,
            expires_at=datetime.now(UTC) + CHALLENGE_FOR,
        )
    )
    db.flush()
    return token, json.loads(options_to_json(options))


def take_challenge(db: Session, token: str | None) -> bytes | None:
    """The challenge the cookie's token names, if it hasn't timed out: used up, so it
    works once, whether the answer is right or not."""
    if not token:
        return None
    return db.scalar(
        delete(PasskeySignIn)
        .where(PasskeySignIn.token_hash == hash_token(token), PasskeySignIn.expires_at > func.now())
        .returning(PasskeySignIn.challenge)
    )


def named(db: Session, credential: dict[str, Any]) -> Passkey | None:
    """The passkey a browser's answer names, locked for this request: never one of a
    merged account's."""
    raw = credential.get("rawId") or credential.get("id")
    if not isinstance(raw, str):
        return None
    try:
        credential_id = base64url_to_bytes(raw)
    except ValueError:
        return None
    return db.scalar(
        select(Passkey)
        .join(User, Passkey.user_id == User.id)
        .where(Passkey.credential_id == credential_id, User.merged_into_id.is_(None))
        .with_for_update(of=Passkey)
    )


def check_alone(
    db: Session, passkey: Passkey, challenge: bytes, credential: dict[str, Any]
) -> bool:
    """Whether `credential` is `passkey` signing `challenge` by itself: for the account
    it was made for (the user handle the device keeps with it), and with the person
    verified. A passkey that does this is discoverable, if that wasn't known."""
    response = credential.get("response")
    handle = response.get("userHandle") if isinstance(response, dict) else None
    try:
        theirs = isinstance(handle, str) and base64url_to_bytes(handle) == passkey.user_id.bytes
    except ValueError:
        theirs = False
    if not theirs or not _signed(db, passkey, challenge, credential, verified=True):
        return False
    passkey.discoverable = True
    db.flush()
    return True

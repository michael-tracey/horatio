"""Passkeys as a second step (#1057), with py_webauthn: a key someone's phone, computer
or password manager keeps, which signs a fresh challenge from Horatio. Horatio keeps
only the public half, so a copy of the database gives nothing away.

A passkey belongs to one site, its relying party: Horatio's host (`webauthn_rp_id`,
from `public_url` unless set), signed for its origin (`webauthn_origin`, likewise).
Each challenge works once: adding a passkey keeps its challenge with the sign-in
session adding it, and signing in keeps it with the sign-in waiting on its second
step. A passkey's count of signatures only goes up; one that goes back was copied,
and is refused.
"""

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException, status
from sqlalchemy import select
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

from horatio.config import get_settings
from horatio.models import Passkey, SecondStepSignIn, User
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
        db.scalars(select(Passkey).where(Passkey.user_id == user.id).order_by(Passkey.created_at))
    )


def _descriptors(db: Session, user: User) -> list[PublicKeyCredentialDescriptor]:
    return [
        PublicKeyCredentialDescriptor(id=p.credential_id, transports=_transports(p.transports))
        for p in mine(db, user)
    ]


def adding_options(db: Session, session: SignInSession, user: User) -> dict[str, Any]:
    """What the browser needs to make a new passkey for `user`, as JSON; its challenge
    is kept with the sign-in session making it."""
    rp_id, _ = relying_party()
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=NAME,
        user_id=user.id.bytes,
        user_name=f"@{user.handle}",
        user_display_name=user.display_name,
        exclude_credentials=_descriptors(db, user),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    session.passkey_challenge = options.challenge
    db.flush()
    return json.loads(options_to_json(options))


def add(
    db: Session, session: SignInSession, user: User, credential: dict[str, Any], name: str
) -> Passkey:
    """Keep the passkey the browser made, once its answer checks out."""
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
        )
    except (WebAuthnException, ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That passkey couldn't be added. Try again."
        ) from error
    if db.scalar(select(Passkey).where(Passkey.credential_id == made.credential_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That passkey is set up already.")
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
    rp_id, origin = relying_party()
    try:
        signed = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError):
        return False
    passkey.sign_count = signed.new_sign_count
    passkey.last_used_at = datetime.now(UTC)
    db.flush()
    return True

"""Push notifications to people's phones (#1054), as the web sends them: through the
push service of each browser (Google's for Chrome on Android, Apple's for a Home
Screen app on an iPhone, Mozilla's for Firefox).

A person turns push on per device, on Account › Notifications: the browser
subscribes with its push service, and Horatio keeps that subscription as a
`PushDevice`. Turning it off there, or signing out there, forgets it. Which topics
come by push is their choice on the same page (`push_<topic>`,
horatio.notification_choices), the same on every device.

`queue` keeps a `PushNotice` for each device of each person who has that kind come
by push, in the same transaction as what happened, as horatio.notification_emails
does for email. The delivery worker (horatio.delivery) calls `send_due`, which
sends what is due, each notice locked while it goes. A push carries no more than
the bell shows: the troupe, the line and the link, which a tap opens. It is
encrypted to the browser's keys (RFC 8291, with `http_ece`) and signed with the
server's key (VAPID, RFC 8292, with `py_vapid`): web-push-libs' own pieces, which
their pywebpush wraps around the `requests` library; Horatio sends with httpx, as it
does for Discord. A device its push service says is gone (404, 410) is forgotten; a
refusal worth trying again is tried later, a few times, and otherwise dropped: the
bell still has it.

The server's key comes from its settings (HORATIO_VAPID_PRIVATE_KEY), never the
database. Without one, push isn't available: nothing is queued, and the page says
so. `python -m horatio.web_push` makes a key.
"""

import base64
import json
import logging
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

import http_ece
import httpx
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio import delivery, notification_choices, suspensions
from horatio.config import get_settings
from horatio.models import PushDevice, PushNotice, Troupe, User

log = logging.getLogger(__name__)

# Tests swap this for a fake push service.
transport: httpx.BaseTransport | None = None

# How long a push service keeps a push for a device that's off or out of signal.
KEEP_FOR = timedelta(hours=12)
# How many times a push is tried before it is dropped.
MAX_ATTEMPTS = 4
# The longest line a push carries; a push holds 4 KB at most, encrypted.
LONGEST = 1000

# The push services browsers subscribe with. Horatio sends only to these, so an
# address sent in as a device's can't make it post anywhere else.
PUSH_SERVICES = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)


def configured() -> bool:
    """Whether this server can send push notifications: it has its key."""
    return bool(get_settings().vapid_private_key)


@lru_cache(maxsize=2)
def _vapid(key: str) -> Vapid:
    # Lenient on the subject, so a server on http://localhost can try it.
    vapid = Vapid.from_string(key)
    vapid.conf = {"no-strict": True}
    return vapid


def vapid() -> Vapid:
    key = get_settings().vapid_private_key
    if not key:
        raise RuntimeError("Push notifications aren't set up: HORATIO_VAPID_PRIVATE_KEY.")
    return _vapid(key.strip())


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def public_key() -> str | None:
    """The server's public key, which a browser subscribes with (its
    `applicationServerKey`); None while push isn't set up."""
    if not configured():
        return None
    key: ec.EllipticCurvePrivateKey = vapid().private_key
    point = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return b64url(point)


def subject() -> str:
    settings = get_settings()
    return settings.vapid_subject or settings.public_url.rstrip("/")


def new_key() -> str:
    """A new private key for HORATIO_VAPID_PRIVATE_KEY: a P-256 key, base64url."""
    key = ec.generate_private_key(ec.SECP256R1())
    return b64url(key.private_numbers().private_value.to_bytes(32, "big"))


# --- devices ---------------------------------------------------------------------------


def known_service(endpoint: str) -> bool:
    """Whether `endpoint` is at one of the push services browsers use, over https."""
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(
        host == s or host.endswith(f".{s}") for s in PUSH_SERVICES
    )


def device_name(user_agent: str | None) -> str:
    """What a device is, from its browser's User-Agent, for the person's list:
    "Chrome on Android", "iPhone"."""
    agent = user_agent or ""
    where = next(
        (
            name
            for token, name in (
                ("iPhone", "iPhone"),
                ("iPad", "iPad"),
                ("Android", "Android"),
                ("CrOS", "Chromebook"),
                ("Macintosh", "Mac"),
                ("Windows", "Windows"),
                ("Linux", "Linux"),
            )
            if token in agent
        ),
        None,
    )
    browser = next(
        (
            name
            for token, name in (
                ("Edg", "Edge"),
                ("SamsungBrowser", "Samsung Internet"),
                ("OPR/", "Opera"),
                ("Firefox/", "Firefox"),
                ("FxiOS", "Firefox"),
                ("CriOS", "Chrome"),
                ("Chrome/", "Chrome"),
                ("Safari/", "Safari"),
            )
            if token in agent
        ),
        None,
    )
    if where and browser:
        return f"{browser} on {where}"
    return where or browser or "A device"


class BadDevice(ValueError):
    """A subscription Horatio can't send to: not at a push service, or its keys wrong."""


def turn_on(
    db: Session, user: User, endpoint: str, p256dh: str, auth: str, user_agent: str | None
) -> PushDevice:
    """Keep this device's subscription for `user`. A device someone else turned on
    before, on the same browser, becomes theirs."""
    if not known_service(endpoint):
        raise BadDevice("That isn't a push service Horatio sends to.")
    try:
        key, secret = unb64url(p256dh), unb64url(auth)
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), key)
    except ValueError as error:
        raise BadDevice("The browser's keys for this device aren't right.") from error
    if len(secret) != 16:
        raise BadDevice("The browser's keys for this device aren't right.")
    device = db.scalar(select(PushDevice).where(PushDevice.endpoint == endpoint))
    if device is not None and device.user_id != user.id:
        # Another account's, signed out without forgetting it: nothing of theirs goes.
        db.execute(delete(PushNotice).where(PushNotice.device_id == device.id))
    if device is None:
        device = PushDevice(user_id=user.id, endpoint=endpoint, p256dh="", auth="", name="")
        db.add(device)
    device.user_id = user.id
    device.p256dh = p256dh
    device.auth = auth
    device.name = device_name(user_agent)
    db.flush()
    return device


def devices_of(db: Session, user: User) -> list[PushDevice]:
    return list(
        db.scalars(
            select(PushDevice)
            .where(PushDevice.user_id == user.id)
            .order_by(PushDevice.created_at, PushDevice.id)
        )
    )


def turn_off(db: Session, user: User, device_id: uuid.UUID) -> bool:
    """Forget one of the person's devices, and what waits to go to it. Whether it was
    theirs."""
    gone = db.execute(
        delete(PushDevice).where(PushDevice.id == device_id, PushDevice.user_id == user.id)
    )
    return bool(getattr(gone, "rowcount", 0))


# --- sending ---------------------------------------------------------------------------


def queue(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    kind: str,
    summary: str,
    link: str,
    *,
    troupe_id: uuid.UUID | None = None,
) -> None:
    """Keep the notification to push to each device of each of `user_ids` who has
    this kind come by push. Nothing is kept while push isn't set up."""
    topic = notification_choices.topic_for(kind)
    ids = list(dict.fromkeys(user_ids))
    if "push" not in topic.routes or not ids or not configured():
        return
    people = db.scalars(
        select(User).where(
            User.id.in_(ids),
            User.id.in_(select(PushDevice.user_id)),
            ~suspensions.suspended_user(),
        )
    )
    wanting = [u.id for u in people if notification_choices.chosen(u, topic, "push")]
    if not wanting:
        return
    troupe = db.get_one(Troupe, troupe_id).name if troupe_id is not None else None
    at = delivery.now()
    for device_id in db.scalars(select(PushDevice.id).where(PushDevice.user_id.in_(wanting))):
        db.add(
            PushNotice(
                device_id=device_id,
                topic=topic.name,
                troupe=troupe,
                summary=summary,
                link=link,
                due_at=at,
            )
        )
    db.flush()


def payload(notice: PushNotice) -> bytes:
    """What the push carries, as the bell shows it: the troupe, the line, the link.
    The service worker (frontend/public/push-sw.js) shows it, and opens the link."""
    summary = notice.summary
    if len(summary) > LONGEST:
        summary = summary[: LONGEST - 1].rstrip() + "…"
    return json.dumps(
        {"title": notice.troupe or "Horatio", "body": summary, "link": notice.link},
        ensure_ascii=False,
    ).encode()


def encrypt(device: PushDevice, data: bytes) -> bytes:
    """`data` encrypted to the device's browser alone (aes128gcm, RFC 8291)."""
    return http_ece.encrypt(
        data,
        private_key=ec.generate_private_key(ec.SECP256R1()),
        dh=unb64url(device.p256dh),
        auth_secret=unb64url(device.auth),
        version="aes128gcm",
    )


def headers(endpoint: str) -> dict[str, str]:
    """The headers of a push to `endpoint`: signed with the server's key, for its
    push service."""
    parts = urlsplit(endpoint)
    signed = vapid().sign({"aud": f"{parts.scheme}://{parts.netloc}", "sub": subject()})
    return {
        **signed,
        "TTL": str(int(KEEP_FOR.total_seconds())),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        # At a game: wake the phone for it.
        "Urgency": "high",
    }


Outcome = Literal["sent", "gone", "again", "refused"]


def send_one(http: httpx.Client, device: PushDevice, notice: PushNotice) -> Outcome:
    """Push one notice to its device, and say how it went."""
    try:
        answer = http.post(
            device.endpoint,
            content=encrypt(device, payload(notice)),
            headers=headers(device.endpoint),
        )
    except httpx.TransportError as error:
        log.info("pushing to %s: %s", device.id, error)
        return "again"
    if answer.is_success:
        return "sent"
    if answer.status_code in (404, 410):
        return "gone"
    if answer.status_code == 429 or answer.status_code >= 500:
        return "again"
    log.warning("push to %s refused: %s %s", device.id, answer.status_code, answer.text[:200])
    return "refused"


def wanted(db: Session, device: PushDevice, notice: PushNotice, at: datetime) -> bool:
    """Whether the notice should still go: the person still has its topic come by
    push, isn't suspended, and it isn't too old to be news."""
    topic = notification_choices.BY_NAME.get(notice.topic)
    user = db.get(User, device.user_id)
    return (
        topic is not None
        and user is not None
        and notice.created_at > at - KEEP_FOR
        and notification_choices.chosen(user, topic, "push")
        and suspensions.current(db, user.id) is None
    )


def send_due(db: Session, at: datetime | None = None, limit: int = 100) -> int:
    """Send the pushes that are due, each in a transaction of its own, locked so two
    workers never send one twice. Returns how many were tried."""
    if not configured():
        return 0
    at = at or delivery.now()
    tried = 0
    with httpx.Client(transport=transport, timeout=15) as http:
        while tried < limit:
            found = db.execute(
                select(PushNotice, PushDevice)
                .join(PushDevice, PushDevice.id == PushNotice.device_id)
                .where(PushNotice.due_at <= at)
                .order_by(PushNotice.due_at, PushNotice.id)
                .limit(1)
                .with_for_update(of=PushNotice, skip_locked=True)
            ).first()
            if found is None:
                break
            notice, device = found
            if not wanted(db, device, notice, at):
                db.delete(notice)
                db.commit()
                continue
            tried += 1
            outcome = send_one(http, device, notice)
            if outcome == "gone":
                # The browser unsubscribed, or the person removed the app: forget it.
                db.execute(delete(PushDevice).where(PushDevice.id == device.id))
            elif outcome == "again" and notice.attempts + 1 < MAX_ATTEMPTS:
                notice.attempts += 1
                notice.due_at = at + delivery.backoff(notice.attempts)
            else:
                db.delete(notice)
            db.commit()
    return tried


if __name__ == "__main__":
    print(f"HORATIO_VAPID_PRIVATE_KEY={new_key()}")

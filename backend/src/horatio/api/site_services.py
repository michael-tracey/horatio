"""Mail and Discord on Custodian › Site (#833, #834): whether each is set up, what it
uses, what the custodian can change, a test, and what failed lately.

The credentials (the mail server's password, Discord's client secret and bot token)
are the server's environment, set in `deploy/production.env` and applied by a
redeploy. They are never kept in the database, never shown and never returned:
only whether each is set. The mail username is shown with most of it hidden.
"""

import smtplib
import socket
import ssl
import uuid
from datetime import datetime
from email.utils import formataddr
from typing import Literal

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import mail_sender, posts
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.config import get_settings
from horatio.connectors import SendError, discord, email
from horatio.models import (
    AuditEvent,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    EmailNotice,
    Post,
    Quest,
    ServerSetting,
    Submission,
    Troupe,
    TroupeConnector,
    User,
)
from horatio.notification_emails import GAVE_UP
from horatio.permissions import require_custodian

router = APIRouter(prefix="/site", tags=["site"])

# How many recent failures each card lists.
FAILURES = 20
# Where the credentials are, for each card to say.
WHERE = "deploy/production.env"


class SiteFailure(BaseModel):
    # A delivery's id (for retrying it), or another row's.
    id: uuid.UUID
    # results, quest, post or notifications.
    kind: Literal["results", "quest", "post", "notifications"]
    # "failed": given up, until someone retries; "retrying": Horatio will try again.
    state: Literal["failed", "retrying"]
    at: datetime
    reason: str
    attempts: int
    troupe_id: uuid.UUID | None
    troupe_name: str | None
    # What it was: "Downtime results for Ann", "News: The Fall", "3 notifications to Bo".
    about: str
    # Where it is in the app, to look at it or retry it there.
    link: str | None
    # How to retry it from the card: a delivery, a post, or not here.
    retry: Literal["delivery", "post"] | None
    post_id: uuid.UUID | None


class SiteMailOut(BaseModel):
    on: bool
    # Why mail is off, naming the settings missing.
    off_reason: str | None
    host: str | None
    port: int
    security: Literal["ssl", "starttls", "none"]
    # A word about the security setting, when something is off.
    security_note: str | None
    # The username, mostly hidden; None when there is none.
    username: str | None
    password_set: bool
    # The server's HORATIO_MAIL_FROM.
    server_from: str | None
    # What the custodian set over it (None: the server's).
    from_name: str | None
    from_address: str | None
    reply_to: str | None
    # Who emails come from now, as the From line reads.
    sends_from: str | None
    where: str
    failures: list[SiteFailure]


class MailIn(BaseModel):
    from_name: str | None = None
    from_address: str | None = None
    reply_to: str | None = None


class MailTestOut(BaseModel):
    ok: bool
    to: str
    # Why it failed, in plain words, and what the server said.
    reason: str | None = None
    detail: str | None = None


class ConnectedTroupe(BaseModel):
    troupe_id: uuid.UUID
    troupe_name: str
    archived: bool
    server: str | None
    # How many characters have a channel for their results.
    characters: int
    test_channel: bool
    # The kinds of post with a channel chosen: news, announcements.
    posts: list[str]


class SiteDiscordOut(BaseModel):
    on: bool
    # The settings missing, by name.
    missing: list[str]
    client_id: str | None
    client_secret_set: bool
    bot_token_set: bool
    # To register in Discord's developer portal, under OAuth2.
    redirect: str
    # Adds the bot to a server by hand; None without a client ID.
    invite: str | None
    where: str
    troupes: list[ConnectedTroupe]
    failures: list[SiteFailure]


class BotOut(BaseModel):
    ok: bool
    name: str | None = None
    id: str | None = None
    servers: int | None = None
    more: bool = False
    reason: str | None = None
    detail: str | None = None


# --- mail -------------------------------------------------------------------------


def masked(username: str) -> str:
    """A username with most of it hidden: "ho•••@example.org", or "ap•••"."""
    local, at, domain = username.partition("@")
    shown = local[:2] if len(local) > 3 else local[:1]
    return f"{shown}•••{at}{domain}"


def security() -> tuple[Literal["ssl", "starttls", "none"], str | None]:
    settings = get_settings()
    if settings.smtp_ssl:
        note = (
            "SSL is on, so STARTTLS is not used; turn one off to be clear."
            if settings.smtp_starttls
            else None
        )
        if note is None and settings.smtp_port != 465:
            note = f"SSL usually goes with port 465, not {settings.smtp_port}."
        return "ssl", note
    if settings.smtp_starttls:
        note = None
        if settings.smtp_port == 465:
            note = "Port 465 usually needs SSL (HORATIO_SMTP_SSL=true), not STARTTLS."
        return "starttls", note
    return "none", "Neither STARTTLS nor SSL is on: mail and the password go unencrypted."


def mail_off() -> str | None:
    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("HORATIO_SMTP_HOST", settings.smtp_host),
            ("HORATIO_MAIL_FROM", settings.mail_from),
        )
        if not value
    ]
    if not missing:
        return None
    return f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set."


def delivery_failures(db: Session, channel: str) -> list[SiteFailure]:
    """Results, quests' news and posts sent on `channel` that failed, or are waiting
    to try again after failing, newest first."""
    rows = db.scalars(
        select(Delivery)
        .where(
            Delivery.channel == channel,
            Delivery.last_error.is_not(None),
            or_(Delivery.status == "failed", Delivery.status == "pending"),
        )
        .order_by(Delivery.updated_at.desc(), Delivery.id.desc())
        .limit(FAILURES)
    ).all()
    out: list[SiteFailure] = []
    for d in rows:
        state: Literal["failed", "retrying"] = "failed" if d.status == "failed" else "retrying"
        base = {
            "id": d.id,
            "state": state,
            "at": d.updated_at,
            "reason": d.last_error or "",
            "attempts": d.attempts,
        }
        if d.post_id is not None:
            post = db.get(Post, d.post_id)
            troupe = db.get(Troupe, post.troupe_id) if post else None
            kind = posts.KINDS[post.kind].noun.capitalize() if post else "Post"
            out.append(
                SiteFailure(
                    **base,
                    kind="post",
                    troupe_id=troupe.id if troupe else None,
                    troupe_name=troupe.name if troupe else None,
                    about=f"{kind}: {post.title}" if post else kind,
                    link=posts.link(post) if post else None,
                    retry="post" if post and d.status == "failed" else None,
                    post_id=post.id if post else None,
                )
            )
        elif d.quest_id is not None:
            quest = db.get(Quest, d.quest_id)
            troupe = db.get(Troupe, quest.troupe_id) if quest else None
            out.append(
                SiteFailure(
                    **base,
                    kind="quest",
                    troupe_id=troupe.id if troupe else None,
                    troupe_name=troupe.name if troupe else None,
                    about=d.subject or "A quest's news",
                    link=f"/troupes/{troupe.id}/quests/{quest.id}" if troupe and quest else None,
                    retry="delivery" if d.status == "failed" else None,
                    post_id=None,
                )
            )
        else:
            found = db.execute(
                select(DowntimeCycle, Troupe)
                .join(CycleParticipant, CycleParticipant.cycle_id == DowntimeCycle.id)
                .join(Submission, Submission.participant_id == CycleParticipant.id)
                .join(Troupe, Troupe.id == DowntimeCycle.troupe_id)
                .where(Submission.id == d.submission_id)
            ).first()
            cycle, troupe = found if found else (None, None)
            out.append(
                SiteFailure(
                    **base,
                    kind="results",
                    troupe_id=troupe.id if troupe else None,
                    troupe_name=troupe.name if troupe else None,
                    about=d.subject or "Downtime results",
                    link=f"/troupes/{troupe.id}/downtimes/{cycle.id}/delivery"
                    if troupe and cycle
                    else None,
                    retry="delivery" if d.status == "failed" else None,
                    post_id=None,
                )
            )
    return out


def notification_failures(db: Session) -> list[SiteFailure]:
    """Notification emails waiting to try again, and those Horatio gave up on."""
    out: list[SiteFailure] = []
    waiting = db.execute(
        select(EmailNotice, User)
        .join(User, User.id == EmailNotice.user_id)
        .where(EmailNotice.last_error.is_not(None))
        .order_by(EmailNotice.updated_at.desc(), EmailNotice.id.desc())
        .limit(FAILURES)
    ).all()
    for notice, user in waiting:
        out.append(
            SiteFailure(
                id=notice.id,
                kind="notifications",
                state="retrying",
                at=notice.updated_at,
                reason=notice.last_error or "",
                attempts=notice.attempts,
                troupe_id=None,
                troupe_name=notice.troupe,
                about=f"Notifications to {user.display_name}",
                link=None,
                retry=None,
                post_id=None,
            )
        )
    gave_up = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.action == GAVE_UP)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(FAILURES)
    ).all()
    for event in gave_up:
        count = int(event.data.get("count") or 1)
        out.append(
            SiteFailure(
                id=event.id,
                kind="notifications",
                state="failed",
                at=event.created_at,
                reason=str(event.data.get("error") or ""),
                attempts=0,
                troupe_id=None,
                troupe_name=None,
                about=f"{count} notification{'' if count == 1 else 's'} to"
                f" {event.data.get('member') or 'someone'}",
                link=None,
                retry=None,
                post_id=None,
            )
        )
    return out


def newest(failures: list[SiteFailure]) -> list[SiteFailure]:
    return sorted(failures, key=lambda f: (f.at, str(f.id)), reverse=True)[:FAILURES]


def mail_out(db: Session) -> SiteMailOut:
    settings = get_settings()
    chosen = mail_sender.kept(db)
    server_from = settings.mail_from or None
    sends_from = mail_sender.sender(db).from_ or None
    kind, note = security()
    return SiteMailOut(
        on=email.configured(),
        off_reason=mail_off(),
        host=settings.smtp_host,
        port=settings.smtp_port,
        security=kind,
        security_note=note,
        username=masked(settings.smtp_username) if settings.smtp_username else None,
        password_set=bool(settings.smtp_password),
        server_from=server_from,
        from_name=chosen.get("from_name"),
        from_address=chosen.get("from_address"),
        reply_to=chosen.get("reply_to"),
        sends_from=sends_from if email.configured() else None,
        where=WHERE,
        failures=newest([*delivery_failures(db, "email"), *notification_failures(db)]),
    )


def checked_address(value: str | None, what: str) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return validate_email(text, check_deliverability=False).normalized
    except EmailNotValidError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{what} is not an email address: {error}"
        ) from None


def checked_name(value: str | None) -> str | None:
    text = " ".join((value or "").split())
    if len(text) > 100:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Keep the From name to 100 characters."
        )
    return text or None


@router.get("/mail")
def mail(db: DbSession, user: CurrentUser) -> SiteMailOut:
    require_custodian(user)
    return mail_out(db)


@router.put("/mail")
def set_mail(body: MailIn, db: DbSession, user: CurrentUser) -> SiteMailOut:
    """Who Horatio's emails come from: a From name and address over the server's,
    and a default Reply-To. Blank puts back the server's."""
    require_custodian(user)
    chosen = {
        "from_name": checked_name(body.from_name),
        "from_address": checked_address(body.from_address, "The From address"),
        "reply_to": checked_address(body.reply_to, "The Reply-To address"),
    }
    kept = {k: v for k, v in chosen.items() if v}
    before = mail_sender.kept(db)
    row = db.get(ServerSetting, mail_sender.KEY)
    if row is None:
        db.add(ServerSetting(key=mail_sender.KEY, value=kept))
    else:
        row.value = kept
    db.flush()
    if before != kept:
        after = mail_sender.sender(db)
        record(
            db,
            user,
            "mail.sender_set",
            sends_from=after.from_ or "the server's address",
            reply_to=after.reply_to or "the From address",
        )
    db.commit()
    return mail_out(db)


def mail_problem(error: SendError) -> tuple[str, str | None]:
    """A mail failure in plain words, naming the setting to look at, and what the
    server or the network said."""
    cause = error.__cause__
    detail = str(cause) if cause is not None else None
    if isinstance(cause, smtplib.SMTPAuthenticationError):
        return (
            "The mail server refused Horatio's sign-in. Check HORATIO_SMTP_USERNAME and"
            " HORATIO_SMTP_PASSWORD.",
            detail,
        )
    if isinstance(cause, socket.gaierror):
        return "Horatio couldn't find the mail server. Check HORATIO_SMTP_HOST.", detail
    if isinstance(cause, ssl.SSLError | smtplib.SMTPNotSupportedError):
        return (
            "The secure connection failed. Use port 587 with STARTTLS, or 465 with SSL.",
            detail,
        )
    if isinstance(cause, TimeoutError):
        return (
            "The mail server didn't answer in time. Check HORATIO_SMTP_HOST and HORATIO_SMTP_PORT.",
            detail,
        )
    if isinstance(cause, ConnectionRefusedError):
        return "The mail server refused the connection. Check HORATIO_SMTP_PORT.", detail
    if isinstance(cause, smtplib.SMTPSenderRefused):
        return (
            "The mail server won't send from this From address. Use one your mail provider allows.",
            detail,
        )
    return error.reason, detail


@router.post("/mail/test")
def test_mail(db: DbSession, user: CurrentUser) -> MailTestOut:
    """Send a test email to the custodian's own address, now."""
    require_custodian(user)
    if (off := mail_off()) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mail is off: {off}")
    sender = mail_sender.sender(db)
    mail = email.new_message(
        formataddr((user.display_name, user.email)), "A test email from Horatio", sender
    )
    mail.set_content(
        f"Hello {user.display_name},\n\nThis is a test from Custodian › Site in Horatio. "
        f"If you're reading it, Horatio's mail works, from {sender.from_}.\n\n-- \n"
        f"Sent by Horatio, {get_settings().public_url.rstrip('/')}\n"
    )
    try:
        email.deliver(mail)
    except SendError as error:
        reason, detail = mail_problem(error)
        record(db, user, "mail.test_failed", error=reason)
        db.commit()
        return MailTestOut(ok=False, to=user.email, reason=reason, detail=detail)
    record(db, user, "mail.test_sent", to=user.email)
    db.commit()
    return MailTestOut(ok=True, to=user.email)


# --- Discord ------------------------------------------------------------------------


def discord_out(db: Session) -> SiteDiscordOut:
    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("HORATIO_DISCORD_CLIENT_ID", settings.discord_client_id),
            ("HORATIO_DISCORD_CLIENT_SECRET", settings.discord_client_secret),
            ("HORATIO_DISCORD_BOT_TOKEN", settings.discord_bot_token),
        )
        if not value
    ]
    connected = db.execute(
        select(TroupeConnector, Troupe)
        .join(Troupe, Troupe.id == TroupeConnector.troupe_id)
        .where(TroupeConnector.kind == "discord")
        .order_by(Troupe.name, Troupe.id)
    ).all()
    troupes = [
        ConnectedTroupe(
            troupe_id=troupe.id,
            troupe_name=troupe.name,
            archived=troupe.archived_at is not None,
            server=row.settings.get("guild_name") or None,
            characters=len([c for c in (row.settings.get("channels") or {}).values() if c]),
            test_channel=bool(row.settings.get("test_channel")),
            posts=sorted(k for k, v in (row.settings.get("post_channels") or {}).items() if v),
        )
        for row, troupe in connected
        if row.settings.get("guild_id")
    ]
    return SiteDiscordOut(
        on=discord.configured(),
        missing=missing,
        client_id=settings.discord_client_id,
        client_secret_set=bool(settings.discord_client_secret),
        bot_token_set=bool(settings.discord_bot_token),
        redirect=discord.redirect_uri(),
        invite=discord.bot_invite_url() if settings.discord_client_id else None,
        where=WHERE,
        troupes=troupes,
        failures=newest(delivery_failures(db, "discord")),
    )


@router.get("/discord")
def discord_status(db: DbSession, user: CurrentUser) -> SiteDiscordOut:
    require_custodian(user)
    return discord_out(db)


@router.post("/discord/check")
def check_bot(user: CurrentUser) -> BotOut:
    """Ask Discord who the bot is, with the server's token."""
    require_custodian(user)
    if not get_settings().discord_bot_token:
        raise HTTPException(status.HTTP_409_CONFLICT, "HORATIO_DISCORD_BOT_TOKEN is not set.")
    try:
        bot = discord.whoami()
    except SendError as error:
        reason = error.reason
        if reason == "Discord refused Horatio's bot token.":
            reason = f"{reason} Check HORATIO_DISCORD_BOT_TOKEN."
        cause = error.__cause__
        detail = str(cause) if cause is not None else None
        return BotOut(ok=False, reason=reason, detail=detail)
    return BotOut(ok=True, name=bot.name, id=bot.id, servers=bot.servers, more=bot.more)

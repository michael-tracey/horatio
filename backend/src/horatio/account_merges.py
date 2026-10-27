"""Merging two accounts of the same person: the custodian's tool (#272).

Someone who signed up twice, once with Google and once with an email say, has two
accounts. The custodian picks which one stays, and merges the other into it:

- its PCs move to the staying account, each by `character_moves.move`, so each
  is logged as a move;
- its staff roles go too. Where both are on one troupe's staff, the higher role
  is kept; where it led a troupe, the staying account leads it now;
- its sign-in links (Google, Discord), and its password if the staying account
  has none;
- its notification settings, and its profile's bio, links and Discord username,
  each only where the staying account has none of its own;
- its bell messages, the scenes it made, the responses assigned to it and not yet
  written, and its troupe requests still waiting;
- its handle, and the former handles it still holds, become the staying
  account's former handles, its own held for good, so links and searches still
  find the person.

Then it is closed: signed out everywhere, unable to sign in, and left out of
every list and search. It keeps its email for the record, freed for anyone to
use, and its name now reads "Jane (merged into @jane)", so wherever history
names it, it says so. Nothing it did is rewritten: past actions keep it as who
did them.

A merge cannot be undone with a button. Its audit record lists everything that
moved, so the custodian could reverse it by hand, a character move at a time.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import formataddr

from sqlalchemy import ColumnElement, delete, func, select, update
from sqlalchemy.orm import Session

from horatio import audit, character_moves
from horatio.config import get_settings
from horatio.connectors import SendError, email
from horatio.models import (
    AuthIdentity,
    Character,
    EmailNotice,
    FormerHandle,
    Notification,
    PasswordReset,
    Response,
    Scene,
    Troupe,
    TroupeRequest,
    TroupeStaff,
    User,
)
from horatio.models import Session as SignInSession
from horatio.models.base import Record
from horatio.notifications import notify
from horatio.preferences import Preferences
from horatio.renames import troupes_of
from horatio.sheets import conflict, unprocessable

# How long a merged account's handle is held for the account it was merged into.
FOR_GOOD = datetime(9999, 12, 31, tzinfo=UTC)

RANK = {"narrator": 1, "assistant_storyteller": 2, "storyteller": 3, "lead_storyteller": 4}
ROLE_NAMES = {
    "narrator": "narrator",
    "assistant_storyteller": "assistant storyteller",
    "storyteller": "storyteller",
    "lead_storyteller": "lead storyteller",
}
NOTIFICATION_SETTINGS = {name for name in Preferences.model_fields if name.startswith("email_")}
# The profile's own parts that move where the staying account has none, by name.
PROFILE = (("bio", "bio"), ("links", "links"), ("discord_handle", "Discord username"))
PROVIDERS = {"discord": "Discord", "google": "Google"}


def merged_name(name: str, handle: str) -> str:
    """How a merged account is named from now on, wherever history names it."""
    return f"{name} (merged into @{handle})"


@dataclass(frozen=True)
class StaffMove:
    """A role the merged account holds on a troupe's staff, and what the staying
    account holds there after the merge."""

    troupe: Troupe
    role: str
    # The staying account's role there before the merge, if any: a clash.
    had: str | None
    keeps: str

    def summary(self, keep: User) -> str:
        moved = f"its {ROLE_NAMES[self.role]} role"
        if self.had is None:
            return moved
        if self.keeps == self.had:
            return f"{moved} (@{keep.handle} stays its {ROLE_NAMES[self.had]})"
        return (
            f"{moved} (@{keep.handle}, its {ROLE_NAMES[self.had]}, is now its"
            f" {ROLE_NAMES[self.keeps]})"
        )


@dataclass(frozen=True)
class Preview:
    """What merging `other` into `keep` would do."""

    keep: User
    other: User
    # Its PCs, with each one's running troupes, home first.
    characters: list[tuple[Character, list[Troupe]]]
    staff: list[StaffMove]
    # What it signs in with that moves: "Google", "Discord", "password".
    sign_in: list[str]
    # Its settings and profile that move, where the staying account has none.
    settings: list[str]
    # The handles that will find the staying account: its own, then those it holds.
    handles: list[str]
    # The rest that moves, each as a phrase: "2 messages in the bell".
    others: list[str]
    # Why the merge cannot be made now, if it cannot.
    refusals: list[str]

    def by_troupe(self) -> dict[Troupe, list[str]]:
        """What moves in each troupe it touches, as phrases."""
        moved: dict[Troupe, list[str]] = {}
        for character, troupes in self.characters:
            for troupe in troupes:
                moved.setdefault(troupe, []).append(character.name)
        for staff in self.staff:
            moved.setdefault(staff.troupe, []).append(staff.summary(self.keep))
        return moved

    def summary(self) -> str:
        """Everything that moves, as one phrase."""
        parts = [c.name for c, _ in self.characters]
        parts += [f"{s.summary(self.keep)} in {s.troupe.name}" for s in self.staff]
        parts += [f"{how} sign-in" for how in self.sign_in]
        parts += self.settings
        parts.append(
            "the handle"
            + ("s " if len(self.handles) > 1 else " ")
            + ", ".join(f"@{h}" for h in self.handles)
        )
        parts += self.others
        return "; ".join(parts)


def _takes(keep: User, other: User, field: str) -> bool:
    """Whether the staying account takes the other's `field`, having none of its own."""
    return bool(getattr(other, field)) and not getattr(keep, field)


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _staff(db: Session, keep: User, other: User) -> list[StaffMove]:
    held: dict[Troupe, str] = {
        t: "lead_storyteller"
        for t in db.scalars(select(Troupe).where(Troupe.lead_user_id == other.id))
    }
    for troupe, role in db.execute(
        select(Troupe, TroupeStaff.role)
        .join(TroupeStaff, TroupeStaff.troupe_id == Troupe.id)
        .where(TroupeStaff.user_id == other.id)
    ):
        held[troupe] = role
    moves: list[StaffMove] = []
    for troupe, role in sorted(held.items(), key=lambda held: held[0].name.lower()):
        had = (
            "lead_storyteller"
            if troupe.lead_user_id == keep.id
            else db.scalar(
                select(TroupeStaff.role).where(
                    TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == keep.id
                )
            )
        )
        keeps = role if had is None or RANK[role] > RANK[had] else had
        moves.append(StaffMove(troupe, role, had, keeps))
    return moves


def _count(db: Session, model: type[Record], *where: ColumnElement[bool]) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def preview(db: Session, keep: User, other: User) -> Preview:
    refusals: list[str] = []
    if keep.id == other.id:
        refusals.append("Pick two different people: that is the same account twice.")
    if other.is_custodian:
        refusals.append(
            f"@{other.handle} is a custodian, so that account can't be closed. Keep it instead."
        )
    pcs = list(
        db.scalars(
            select(Character)
            .where(Character.player_id == other.id, Character.kind == "pc")
            .order_by(Character.status, func.lower(Character.name))
        )
    )
    characters = [(c, troupes_of(db, c)) for c in pcs]
    if keep.id != other.id:
        refusals += [why for c in pcs if (why := character_moves.refusal(db, c, keep)) is not None]

    sign_in = [
        PROVIDERS[provider]
        for provider in db.scalars(
            select(AuthIdentity.provider)
            .where(AuthIdentity.user_id == other.id)
            .order_by(AuthIdentity.provider)
        )
    ]
    if other.discord_user_id and not keep.discord_user_id and "Discord" not in sign_in:
        sign_in.append("Discord")
    if other.password_hash and not keep.password_hash:
        sign_in.append("password")

    settings: list[str] = []
    if NOTIFICATION_SETTINGS & set(other.preferences or {}) and not (
        NOTIFICATION_SETTINGS & set(keep.preferences or {})
    ):
        settings.append("notification settings")
    settings += [name for field, name in PROFILE if _takes(keep, other, field)]

    held = list(
        db.scalars(
            select(FormerHandle.handle)
            .where(FormerHandle.user_id == other.id, FormerHandle.held_until > func.now())
            .order_by(FormerHandle.created_at)
        )
    )
    others = [
        plural(n, one, many)
        for n, one, many in (
            (
                _count(db, Notification, Notification.user_id == other.id),
                "message in the bell",
                "messages in the bell",
            ),
            (_count(db, Scene, Scene.created_by_id == other.id), "scene", "scenes"),
            (
                _count(
                    db,
                    Response,
                    Response.assigned_to_user_id == other.id,
                    Response.status == "assigned",
                ),
                "response assigned to it",
                "responses assigned to it",
            ),
            (
                _count(
                    db,
                    TroupeRequest,
                    TroupeRequest.requester_id == other.id,
                    TroupeRequest.status == "pending",
                ),
                "troupe request waiting",
                "troupe requests waiting",
            ),
        )
        if n
    ]
    return Preview(
        keep=keep,
        other=other,
        characters=characters,
        staff=_staff(db, keep, other),
        sign_in=sign_in,
        settings=settings,
        handles=[other.handle, *held],
        others=others,
        refusals=refusals,
    )


def staying(db: Session, user: User) -> User:
    """The account `user` was merged into, following one merge after another; or
    `user`, if it was never merged."""
    seen = {user.id}
    while user.merged_into_id is not None and user.merged_into_id not in seen:
        user = db.get_one(User, user.merged_into_id)
        seen.add(user.id)
    return user


def merge(db: Session, actor: User, keep: User, other: User, reason: str) -> Preview:
    """Merge `other` into `keep`, as the custodian `actor`, for `reason`, and close
    it. Logged in the audit log and in each troupe it touches; the person is told
    in the bell and at both addresses, and those troupes' lead storytellers in the
    bell. Callers check that `actor` is the custodian."""
    reason = reason.strip()
    if not reason:
        raise unprocessable("Give a reason for the merge.")
    # Both locked, so two merges of one account never run at once.
    db.execute(
        select(User.id).where(User.id.in_([keep.id, other.id])).order_by(User.id).with_for_update()
    )
    db.refresh(keep)
    db.refresh(other)
    if keep.merged_into_id is not None or other.merged_into_id is not None:
        raise conflict("One of these accounts has been merged already.")
    found = preview(db, keep, other)
    if found.refusals:
        raise conflict(" ".join(found.refusals))
    name, now = other.display_name, datetime.now(UTC)

    for character, _ in found.characters:
        character_moves.move(db, actor, character, keep, f"accounts merged ({reason})", tell=False)

    for staff in found.staff:
        troupe = staff.troupe
        if staff.role == "lead_storyteller":
            troupe.lead_user_id = keep.id
            # The lead is not listed among the staff.
            db.execute(
                delete(TroupeStaff).where(
                    TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == keep.id
                )
            )
            continue
        if staff.had is None:
            db.execute(
                update(TroupeStaff)
                .where(TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == other.id)
                .values(user_id=keep.id)
            )
            continue
        db.execute(
            delete(TroupeStaff).where(
                TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == other.id
            )
        )
        if staff.had != "lead_storyteller":
            db.execute(
                update(TroupeStaff)
                .where(TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == keep.id)
                .values(role=staff.keeps)
            )
    db.execute(update(Troupe).where(Troupe.contact_id == other.id).values(contact_id=keep.id))

    db.execute(update(AuthIdentity).where(AuthIdentity.user_id == other.id).values(user_id=keep.id))
    if other.discord_user_id and not keep.discord_user_id:
        discord, other.discord_user_id = other.discord_user_id, None
        db.flush()
        keep.discord_user_id = discord
    if other.password_hash and not keep.password_hash:
        keep.password_hash = other.password_hash
    other.password_hash = None

    if "notification settings" in found.settings:
        keep.preferences = {
            **(keep.preferences or {}),
            **{k: v for k, v in other.preferences.items() if k in NOTIFICATION_SETTINGS},
        }
    for field, _ in PROFILE:
        if _takes(keep, other, field):
            setattr(keep, field, getattr(other, field))

    db.execute(update(Notification).where(Notification.user_id == other.id).values(user_id=keep.id))
    db.execute(update(EmailNotice).where(EmailNotice.user_id == other.id).values(user_id=keep.id))
    db.execute(update(Scene).where(Scene.created_by_id == other.id).values(created_by_id=keep.id))
    db.execute(
        update(Response)
        .where(Response.assigned_to_user_id == other.id, Response.status == "assigned")
        .values(assigned_to_user_id=keep.id)
    )
    db.execute(
        update(TroupeRequest)
        .where(TroupeRequest.requester_id == other.id, TroupeRequest.status == "pending")
        .values(requester_id=keep.id)
    )

    db.execute(update(FormerHandle).where(FormerHandle.user_id == other.id).values(user_id=keep.id))
    db.add(FormerHandle(user_id=keep.id, handle=other.handle, held_until=FOR_GOOD))

    # Closed: signed out everywhere, its reset link gone.
    db.execute(
        update(SignInSession)
        .where(SignInSession.user_id == other.id, SignInSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == other.id))
    other.merged_into_id = keep.id
    other.merged_at = now
    other.display_name = merged_name(name, keep.handle)
    db.flush()

    about = {
        "kept_id": keep.id,
        "kept_handle": keep.handle,
        "merged_id": other.id,
        "merged_handle": found.handles[0],
        "merged_name": name,
        "reason": reason,
    }
    by_troupe = found.by_troupe()
    audit.record(
        db,
        actor,
        "account.merged",
        **about,
        moved=found.summary(),
        merged_email=other.email,
        characters=[str(c.id) for c, _ in found.characters],
        staff=[
            {
                "troupe_id": str(s.troupe.id),
                "troupe": s.troupe.name,
                "role": s.role,
                "had": s.had,
                "keeps": s.keeps,
            }
            for s in found.staff
        ],
        sign_in=found.sign_in,
        settings=found.settings,
        handles=found.handles,
        others=found.others,
    )
    for troupe, moved in by_troupe.items():
        audit.record(
            db, actor, "account.merged", troupe_id=troupe.id, **about, moved=", ".join(moved)
        )

    notify(
        db,
        [keep.id],
        "account.merged",
        f"The custodian merged your account @{found.handles[0]} into this one,"
        f" @{keep.handle}: {reason}",
        "/characters",
    )
    told = {actor.id, keep.id, other.id}
    for troupe, moved in by_troupe.items():
        if troupe.archived_at is not None or troupe.lead_user_id in told:
            continue
        notify(
            db,
            [troupe.lead_user_id],
            "account.merged",
            f"The custodian merged @{found.handles[0]} into @{keep.handle}, the same person,"
            f" moving {', '.join(moved)}: {reason}",
            f"/troupes/{troupe.id}",
            troupe_id=troupe.id,
        )
    _email(db, actor, keep, found, other.email, reason)
    return found


def email_text(actor: User, keep: User, found: Preview, merged_email: str, reason: str) -> str:
    merged = found.handles[0]
    return (
        f"Hello {keep.display_name},\n\n"
        f"{actor.display_name}, Horatio's custodian, has merged your account @{merged}"
        f" ({merged_email}) into your account @{keep.handle} ({keep.email}), as the same"
        f" person: {reason}\n\n"
        f"From now on, sign in as @{keep.handle}. @{merged} can no longer sign in, and"
        f" anyone looking for @{merged} finds @{keep.handle}.\n\n"
        f"Moved to @{keep.handle}: {found.summary()}.\n\n"
        f"-- \nSent by Horatio, {get_settings().public_url.rstrip('/')}\n"
    )


def _email(
    db: Session, actor: User, keep: User, found: Preview, merged_email: str, reason: str
) -> None:
    """Tell the person at both their addresses, if Horatio can send email. A refusal
    is logged; the merge stands."""
    if not email.configured():
        return
    text = email_text(actor, keep, found, merged_email, reason)
    for address in dict.fromkeys([keep.email, merged_email], None):
        mail = email.new_message(
            formataddr((keep.display_name, address)), "Your Horatio accounts are now one"
        )
        mail.set_content(text)
        try:
            email.deliver(mail)
        except SendError as error:
            audit.record(
                db,
                actor,
                "account.merge_email_failed",
                kept_id=keep.id,
                kept_handle=keep.handle,
                to=address,
                error=str(error),
            )

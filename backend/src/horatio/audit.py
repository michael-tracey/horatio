"""Writing the audit log, and the level of each action in it (#1062).

Every action has a level, set here and nowhere else: `DEBUG` and `NOTICE` name
theirs, and every other action is `info`.

- **debug**: routine events, many a day, such as signing in. Recorded only while
  the custodian asks for them (Custodian › Site), and never shown in a troupe's,
  a character's or a location's log: only in the custodian's search.
- **info**: most changes, shown in the logs as ever.
- **notice**: kept forever. What features read back from the log as their
  history (title history, the chronicle, a location's log, the People tab's
  cards...), and what accounts, security and the custodian's own work need.

Debug and info events are deleted once older than the custodian's retention for
their level (horatio.audit_retention); notice ones never are. An action a feature
reads as history must be notice: `tests/test_audit_levels.py` checks every reader.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from horatio.models import AuditEvent, Character, ServerSetting, User

QUIET = "horatio.audit_quiet"

Level = Literal["debug", "info", "notice"]
LEVELS: tuple[Level, ...] = ("debug", "info", "notice")

# Routine, and many: recorded only while the custodian records debug events.
DEBUG: frozenset[str] = frozenset(
    {
        "account.signed_in",
        "account.sign_in_failed",
        "account.signed_out",
        "account.signed_up",
        # A character started visiting a troupe.
        "troupe.join",
    }
)

# Kept forever, never purged.
NOTICE: frozenset[str] = frozenset(
    {
        # --- read back as history by a feature (tests/test_audit_levels.py) ---
        # Title history and status over time (horatio.title_history).
        "status.added",
        "status.spent",
        "status.removed",
        "status.expired",
        "status.given_up",
        "status.lost",
        "status.cleared",
        # Which influence entries staff changed (horatio.play_influence).
        "influence.changed",
        "influence.merged",
        # The chronicle (horatio.chronicle).
        "npc.copied_from_character",
        "character.retired",
        # Archived troupes, and settling them (horatio.closing).
        "troupe.settled",
        "troupe.archived",
        # NPCs given to players (horatio.troupe_fit).
        "npc.given",
        "npc.claimed",
        # A character's old names, for imports (horatio.import_boons, import_influence_log).
        "character.renamed",
        # Reminders sent in a downtime cycle (horatio.downtimes).
        "downtime.reminded",
        # Notification emails given up on (Custodian › Site's Mail card).
        "mail.gave_up",
        # A location's own log (horatio.locations.describe).
        "location.added",
        "location.changed",
        "location.forfeit",
        "location.negative_removed",
        "location.out_of_code",
        "location.over_limit",
        "location.quest_built",
        "location.quest_completed",
        "location.removed",
        # --- accounts and security: the People tab's cards read most of these ---
        "account.discord_linked",
        "account.discord_link_refused",
        "account.discord_unlinked",
        "account.email_change_started",
        "account.email_change_resent",
        "account.email_change_email_failed",
        "account.email_change_notice_failed",
        "account.email_change_cancelled",
        "account.email_changed",
        "account.handle_changed",
        "account.merged",
        "account.merge_email_failed",
        "account.password_changed",
        "account.password_reset",
        "account.reset_cancelled",
        "account.reset_email_failed",
        "account.reset_link",
        "account.reset_requested",
        "account.reset_sent",
        "account.suspended",
        "account.suspension_email_failed",
        "account.suspension_lifted",
        "account.view_as",
        "account.view_as_ended",
        # --- the custodian's work, and what stays with a troupe for good ---
        "character.deleted",
        "npc.deleted",
        "character.moved",
        "troupe.reopened",
        "troupe.lead_appointed",
        "staff.assigned",
        "staff.removed",
        "troupe_request.made",
        "troupe_request.approved",
        "troupe_request.declined",
        "troupe_request.withdrawn",
        "backup.made",
        "backup.downloaded",
        "audit.exported",
        "audit.settings_changed",
        "appearance.loading_animation",
        "mail.sender_set",
        "mail.design_set",
        "mail.header_uploaded",
        "mail.header_removed",
        "clan_logo.uploaded",
        "clan_logo.removed",
        "crypt_templates.uploaded",
        "crypt_templates.removed",
    }
)


def level(action: str) -> Level:
    """The action's level: debug, info or notice."""
    if action in NOTICE:
        return "notice"
    if action in DEBUG:
        return "debug"
    return "info"


def at_least(least: Level) -> tuple[Level, ...]:
    """The levels from `least` up: at_least("info") is info and notice."""
    return LEVELS[LEVELS.index(least) :]


# --- what the custodian chooses (Custodian › Site) -----------------------------------------

SETTINGS = "audit_log"
# The least level recorded can be debug, or info to skip debug events. Info and
# notice are always recorded: the logs and features need them.
RECORDABLE: tuple[Level, ...] = ("debug", "info")


@dataclass(frozen=True)
class LogSettings:
    record: Level = "info"
    # Days debug and info events are kept; None for forever. Notice is kept forever.
    keep_debug: int | None = 30
    keep_info: int | None = 365

    def days(self, of: Level) -> int | None:
        """Days events of this level are kept; None for forever."""
        return {"debug": self.keep_debug, "info": self.keep_info}.get(of)


def settings(db: Session) -> LogSettings:
    """What the custodian chose, or the defaults. Read afresh each time, so a change
    takes effect at once."""
    row = db.get(ServerSetting, SETTINGS)
    value = row.value if row is not None and isinstance(row.value, dict) else {}
    default = LogSettings()
    record = value.get("record")
    return LogSettings(
        record=record if record in RECORDABLE else default.record,
        keep_debug=value.get("keep_debug", default.keep_debug),
        keep_info=value.get("keep_info", default.keep_info),
    )


def save_settings(db: Session, chosen: LogSettings) -> None:
    value = {
        "record": chosen.record,
        "keep_debug": chosen.keep_debug,
        "keep_info": chosen.keep_info,
    }
    row = db.get(ServerSetting, SETTINGS)
    if row is None:
        db.add(ServerSetting(key=SETTINGS, value=value))
    else:
        row.value = value


def recorded(db: Session, of: Level) -> bool:
    """Whether events of this level are recorded now. Only a level below info,
    which the custodian may switch off, asks the database."""
    if LEVELS.index(of) >= LEVELS.index("info"):
        return True
    return LEVELS.index(of) >= LEVELS.index(settings(db).record)


# --- writing -------------------------------------------------------------------------------


@contextmanager
def quiet(db: Session) -> Iterator[None]:
    """Record nothing in this session while inside: for one change made of many,
    which records one entry of its own for the whole (horatio.troupe_settings_share)."""
    db.info[QUIET] = True
    try:
        yield
    finally:
        db.info.pop(QUIET, None)


def record(
    db: Session,
    actor: User | None,
    action: str,
    *,
    troupe_id: uuid.UUID | None = None,
    character_id: uuid.UUID | None = None,
    **data: Any,
) -> None:
    """Record that `actor` (None: Horatio itself) did `action`, unless its level is
    one the custodian doesn't record."""
    if db.info.get(QUIET):
        return
    of = level(action)
    if not recorded(db, of):
        return
    if character_id is not None and "character_name" not in data:
        # Kept with the event, so the log still reads after a character is deleted.
        character = db.get(Character, character_id)
        if character is not None:
            data["character_name"] = character.name
    db.add(
        AuditEvent(
            actor_id=actor.id if actor else None,
            troupe_id=troupe_id,
            character_id=character_id,
            action=action,
            level=of,
            data={k: str(v) if isinstance(v, uuid.UUID) else v for k, v in data.items()},
        )
    )

"""The custodian's search of the audit log, across every troupe, and the log's
settings: whether debug events are recorded, and how long each level is kept
(horatio.audit, horatio.audit_retention). The search only reads: nothing here
changes or removes what the log holds."""

import csv
import io
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, Select, Text, and_, false, func, literal_column, or_, select
from sqlalchemy import tuple_ as row
from sqlalchemy.orm import aliased

from horatio import audit, audit_retention, handles
from horatio.api.roster import MESSAGES, LogEntry, log_entries
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import AuditEvent, Character, Troupe, User
from horatio.permissions import require_custodian

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditGroup(StrEnum):
    APPROVALS = "approvals"
    XP = "xp"
    SHEETS = "sheets"
    CREATION = "creation"
    STATUS = "status"
    TITLES = "titles"
    DOWNTIMES = "downtimes"
    INFLUENCE = "influence"
    PLAY = "play"
    NPCS = "npcs"
    EQUIPMENT = "equipment"
    STAFF = "staff"
    HOUSE_RULES = "house_rules"
    TROUPES = "troupes"
    ACCOUNTS = "accounts"
    SYSTEM = "system"


# Each group's name, and the starts of the actions in it. An action can be in more
# than one: a troupe's XP range is the troupe's and XP's.
GROUPS: dict[AuditGroup, tuple[str, tuple[str, ...]]] = {
    AuditGroup.APPROVALS: (
        "Approvals",
        ("approval.", "standing.", "home_troupe.", "backstory."),
    ),
    AuditGroup.XP: (
        "XP",
        (
            "xp.",
            "troupe.starting_xp",
            "troupe.new_character_incentive",
            "troupe.xp_",
            "downtime.completion_xp",
        ),
    ),
    AuditGroup.SHEETS: (
        "Sheets",
        ("sheet.", "character.", "picture.", "identity.", "retainer.", "embrace.", "bond."),
    ),
    AuditGroup.CREATION: ("Character creation", ("creation.",)),
    AuditGroup.STATUS: (
        "Status",
        (
            "status.",
            "troupe.status_by",
            "troupe.status_at_checkin",
            "boon.",
            "house.boons",
            "house.boon_players",
            "house.boons_judge_ban",
        ),
    ),
    AuditGroup.TITLES: ("Titles", ("title.", "troupe.titles_by")),
    AuditGroup.DOWNTIMES: (
        "Downtimes",
        (
            "downtime.",
            "response.",
            "delivery.",
            "quest.",
            "project.",
            "nomination.",
            "remembrance.",
            "house.player_nominations",
            "house.remembrances",
        ),
    ),
    AuditGroup.INFLUENCE: (
        "Influence",
        ("influence.", "shared_background.", "house.influence_lookback"),
    ),
    AuditGroup.PLAY: ("Play", ("play.", "scene.")),
    AuditGroup.NPCS: ("NPCs", ("npc.",)),
    AuditGroup.EQUIPMENT: ("Equipment", ("equipment.",)),
    AuditGroup.STAFF: ("Staff", ("staff.", "troupe.lead_appointed")),
    AuditGroup.HOUSE_RULES: (
        "House rules",
        ("house.", "troupe.specializations", "troupe.sects_limited", "troupe.splats_limited"),
    ),
    AuditGroup.TROUPES: (
        "Troupes",
        ("troupe.", "troupe_request.", "connector.", "location.", "post.", "agency."),
    ),
    AuditGroup.ACCOUNTS: ("Accounts", ("account.",)),
    AuditGroup.SYSTEM: (
        "System",
        (
            "backup.",
            "clan_logo.",
            "audit.",
            "yorick_import.",
            "dark_pack.",
            "vtes_symbols.",
            "crypt_templates.",
            "appearance.",
            "site.",
            "mail.",
        ),
    ),
}

# A purchase's wording is put together from its numbers (roster.purchase_message);
# these are all the words it can have.
PURCHASE_WORDING = (
    "{actor} bought, raised, lowered or removed {character}'s {name} from {before} to"
    " {after} ({cost} XP) ({cost} XP back) (free by exception)."
)
# Each wording, without the parts filled in, for searching the words around them.
WORDING: dict[str, str] = {
    key: re.sub(r"\{[^}]*\}", " ", template).lower()
    for key, template in {**MESSAGES, "sheet.purchase": PURCHASE_WORDING}.items()
}

PAGE = 50
EXPORT_BATCH = 1000


class AuditLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    NOTICE = "notice"


class AuditEntry(LogEntry):
    troupe_id: uuid.UUID | None
    troupe_name: str | None
    level: AuditLevel


class AuditPage(BaseModel):
    entries: list[AuditEntry]
    # Pass as `before` for the next, older page; None when this is the last.
    next: str | None


class AuditGroupOut(BaseModel):
    key: AuditGroup
    label: str


class AuditTroupe(BaseModel):
    id: uuid.UUID
    name: str
    archived: bool


class AuditFilters(BaseModel):
    groups: list[AuditGroupOut]
    # Archived ones too: their history is kept.
    troupes: list[AuditTroupe]


class AuditCharacter(BaseModel):
    id: uuid.UUID
    name: str
    kind: str  # pc | npc
    player_name: str | None
    # Its home troupe, or for an NPC the troupe that keeps it.
    troupe_name: str | None
    retired: bool


def words_match(words: list[str]) -> ColumnElement[bool]:
    """Every word is somewhere in the event as it reads: in the wording around the
    names, in what is filled in (names, reasons, ratings), or in who did it or whose
    character it was."""
    actor = aliased(User)
    player = aliased(User)
    values = func.jsonb_path_query_array(AuditEvent.data, literal_column("'$.*'::jsonpath")).cast(
        Text
    )
    # An action with no wording of its own reads as its name: "backup: made".
    plain = func.replace(func.replace(AuditEvent.action, "_", " "), ".", ": ")
    conditions: list[ColumnElement[bool]] = []
    for word in words:
        keys = [key for key, wording in WORDING.items() if word.lower() in wording]
        # "approval.request.discipline" is an approval.request of that kind.
        kinds = [tuple(key.rsplit(".", 1)) for key in keys if key.count(".") > 1]
        conditions.append(
            or_(
                values.icontains(word, autoescape=True),
                select(actor.id)
                .where(
                    actor.id == AuditEvent.actor_id,
                    or_(
                        actor.display_name.icontains(word, autoescape=True),
                        actor.handle.icontains(word, autoescape=True),
                    ),
                )
                .exists(),
                # The PC's player, named after it: "Agnes (Jane)".
                select(Character.id)
                .join(player, Character.player_id == player.id)
                .where(
                    Character.id == AuditEvent.character_id,
                    Character.kind == "pc",
                    player.display_name.icontains(word, autoescape=True),
                )
                .exists(),
                AuditEvent.action.in_(keys) if keys else false(),
                row(AuditEvent.action, AuditEvent.data["kind"].astext).in_(kinds)
                if kinds
                else false(),
                and_(AuditEvent.action.not_in(WORDING), plain.icontains(word, autoescape=True)),
            )
        )
    return and_(*conditions)


def search(
    db: DbSession,
    *,
    person: str | None,
    character_id: uuid.UUID | None,
    troupe_id: uuid.UUID | None,
    group: AuditGroup | None,
    level: AuditLevel | None,
    since: datetime | None,
    until: datetime | None,
    q: str,
) -> Select[AuditEvent, str]:
    """The events the filters find, newest first."""
    query = (
        select(AuditEvent, User.display_name)
        .outerjoin(User, AuditEvent.actor_id == User.id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    )
    if person and person.strip():
        actor = handles.holder(db, person)
        if actor is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Nobody has the handle {person.strip().removeprefix('@')}.",
            )
        query = query.where(AuditEvent.actor_id == actor.id)
    if character_id is not None:
        query = query.where(AuditEvent.character_id == character_id)
    if troupe_id is not None:
        query = query.where(AuditEvent.troupe_id == troupe_id)
    if group is not None:
        _, starts = GROUPS[group]
        query = query.where(
            or_(*(AuditEvent.action.startswith(s, autoescape=True) for s in starts))
        )
    if level is not None:
        query = query.where(AuditEvent.level.in_(audit.at_least(level.value)))
    if since is not None:
        query = query.where(AuditEvent.created_at >= since)
    if until is not None:
        query = query.where(AuditEvent.created_at < until)
    if words := q.split():
        query = query.where(words_match(words))
    return query


def cursor(entry: LogEntry) -> str:
    return f"{entry.at.isoformat()}~{entry.id}"


def older_than(query: Select[AuditEvent, str], before: str) -> Select[AuditEvent, str]:
    try:
        at, _, event_id = before.partition("~")
        after = (datetime.fromisoformat(at), uuid.UUID(event_id))
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That is not a page of this search."
        ) from None
    return query.where(row(AuditEvent.created_at, AuditEvent.id) < after)


def with_troupes(db: DbSession, entries: list[LogEntry]) -> list[AuditEntry]:
    """The entries with their troupes, and their levels."""
    found = {
        event_id: (troupe_id, name, level)
        for event_id, troupe_id, name, level in db.execute(
            select(AuditEvent.id, Troupe.id, Troupe.name, AuditEvent.level)
            .outerjoin(Troupe, AuditEvent.troupe_id == Troupe.id)
            .where(AuditEvent.id.in_([e.id for e in entries]))
        )
    }
    return [
        AuditEntry(
            **entry.model_dump(),
            troupe_id=found[entry.id][0],
            troupe_name=found[entry.id][1],
            level=AuditLevel(found[entry.id][2]),
        )
        for entry in entries
    ]


Person = Annotated[str | None, Query(description="Who did it: their handle.")]
Least = Annotated[
    AuditLevel | None, Query(description="The least level: info finds info and notice.")
]
Since = Annotated[datetime | None, Query(description="From this moment on.")]
Until = Annotated[datetime | None, Query(description="Before this moment.")]


@router.get("")
def search_log(
    db: DbSession,
    user: CurrentUser,
    person: Person = None,
    character_id: uuid.UUID | None = None,
    troupe_id: uuid.UUID | None = None,
    group: AuditGroup | None = None,
    level: Least = None,
    since: Since = None,
    until: Until = None,
    q: str = "",
    before: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = PAGE,
) -> AuditPage:
    """For the custodian: every event in the log, in every troupe and outside them,
    that the filters find, newest first, a page at a time. `q` is words that must all
    be in the event as it reads."""
    require_custodian(user)
    query = search(
        db,
        person=person,
        character_id=character_id,
        troupe_id=troupe_id,
        group=group,
        level=level,
        since=since,
        until=until,
        q=q,
    )
    if before:
        query = older_than(query, before)
    entries = log_entries(db, query.limit(limit + 1))
    return AuditPage(
        entries=with_troupes(db, entries[:limit]),
        next=cursor(entries[limit - 1]) if len(entries) > limit else None,
    )


def safe(value: object) -> str:
    """A cell a spreadsheet will not run as a formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get(
    "/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
def export_log(
    db: DbSession,
    user: CurrentUser,
    person: Person = None,
    character_id: uuid.UUID | None = None,
    troupe_id: uuid.UUID | None = None,
    group: AuditGroup | None = None,
    level: Least = None,
    since: Since = None,
    until: Until = None,
    q: str = "",
) -> Response:
    """For the custodian: everything the same filters find, newest first, as a CSV.
    The export itself goes in the log."""
    require_custodian(user)
    query = search(
        db,
        person=person,
        character_id=character_id,
        troupe_id=troupe_id,
        group=group,
        level=level,
        since=since,
        until=until,
        q=q,
    )

    def everything() -> Iterator[AuditEntry]:
        page = query
        while entries := log_entries(db, page.limit(EXPORT_BATCH)):
            yield from with_troupes(db, entries)
            if len(entries) < EXPORT_BATCH:
                return
            page = older_than(query, cursor(entries[-1]))

    out = io.StringIO()
    # The mark tells spreadsheets the file is UTF-8.
    out.write("﻿")
    writer = csv.writer(out)
    writer.writerow(
        ["When (UTC)", "Who", "Troupe", "Character", "Player", "Action", "Level", "What"]
    )
    count = 0
    for e in everything():
        count += 1
        writer.writerow(
            [
                e.at.astimezone(UTC).isoformat(timespec="seconds"),
                safe(e.actor_name or "Horatio"),
                safe(e.troupe_name),
                safe(e.character_name),
                safe(e.player_name),
                e.action,
                e.level.value,
                safe(e.message),
            ]
        )
    audit.record(db, user, "audit.exported", count=count)
    db.commit()
    day = datetime.now(UTC).date().isoformat()
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="horatio-audit-{day}.csv"'},
    )


@router.get("/filters")
def filters(db: DbSession, user: CurrentUser) -> AuditFilters:
    """For the custodian: the groups of actions and the troupes to search by."""
    require_custodian(user)
    return AuditFilters(
        groups=[AuditGroupOut(key=key, label=label) for key, (label, _) in GROUPS.items()],
        troupes=[
            AuditTroupe(id=t.id, name=t.name, archived=t.archived_at is not None)
            for t in db.scalars(select(Troupe).order_by(func.lower(Troupe.name)))
        ],
    )


@router.get("/characters")
def characters(
    db: DbSession,
    user: CurrentUser,
    q: str = "",
    character_id: uuid.UUID | None = None,
) -> list[AuditCharacter]:
    """For the custodian: characters to search the log by, whosever and wherever they
    are, retired ones too: up to 20 with `q` in their name, or just `character_id`."""
    require_custodian(user)
    player = aliased(User)
    troupe = aliased(Troupe)
    query = (
        select(Character, player.display_name, troupe.name)
        .join(player, Character.player_id == player.id)
        .outerjoin(
            troupe, troupe.id == func.coalesce(Character.home_troupe_id, Character.owner_troupe_id)
        )
        .order_by(func.lower(Character.name), Character.id)
        .limit(20)
    )
    if character_id is not None:
        query = query.where(Character.id == character_id)
    elif q.strip():
        query = query.where(Character.name.icontains(q.strip(), autoescape=True))
    return [
        AuditCharacter(
            id=c.id,
            name=c.name,
            kind=c.kind,
            player_name=player_name if c.kind == "pc" else None,
            troupe_name=troupe_name,
            retired=c.status == "retired",
        )
        for c, player_name, troupe_name in db.execute(query)
    ]


# --- the log's settings ----------------------------------------------------------------------

# Days a level can be kept, at least and at most; None keeps it forever.
KeepDays = Annotated[int | None, Field(ge=1, le=3650)]


class AuditPurgeOut(BaseModel):
    at: datetime
    # How many it deleted, of each level.
    debug: int
    info: int
    # False while it has more to delete, minutes later.
    finished: bool


class AuditSettingsOut(BaseModel):
    # The least level recorded: debug records everything; info skips debug events.
    record: Literal["debug", "info"]
    # Days debug and info events are kept; None for forever. Notice is kept forever.
    keep_debug: int | None
    keep_info: int | None
    # Whether sign-in events keep the client's IP address (#1066).
    sign_in_ips: bool
    last_purge: AuditPurgeOut | None


class AuditSettingsIn(BaseModel):
    record: Literal["debug", "info"]
    keep_debug: KeepDays
    keep_info: KeepDays
    sign_in_ips: bool


def kept_for(days: int | None) -> str:
    return "forever" if days is None else f"{days} day{'' if days == 1 else 's'}"


def settings_out(db: DbSession) -> AuditSettingsOut:
    chosen = audit.settings(db)
    last = audit_retention.last(db)
    record = "debug" if chosen.record == "debug" else "info"
    return AuditSettingsOut(
        record=record,
        keep_debug=chosen.keep_debug,
        keep_info=chosen.keep_info,
        sign_in_ips=chosen.sign_in_ips,
        last_purge=AuditPurgeOut(
            at=last.at,
            debug=last.deleted.get("debug", 0),
            info=last.deleted.get("info", 0),
            finished=last.finished,
        )
        if last is not None
        else None,
    )


@router.get("/settings")
def log_settings(db: DbSession, user: CurrentUser) -> AuditSettingsOut:
    """For the custodian: what the log records, how long it keeps each level, whether
    sign-in events keep IP addresses, and what the last purge deleted."""
    require_custodian(user)
    return settings_out(db)


@router.put("/settings")
def change_log_settings(
    body: AuditSettingsIn, db: DbSession, user: CurrentUser
) -> AuditSettingsOut:
    """For the custodian: change what the log records and how long it keeps each
    level. It takes effect at once, and goes in the log itself."""
    require_custodian(user)
    before = audit.settings(db)
    after = audit.LogSettings(
        record=body.record,
        keep_debug=body.keep_debug,
        keep_info=body.keep_info,
        sign_in_ips=body.sign_in_ips,
    )
    changes: list[str] = []
    if after.record != before.record:
        changes.append(
            "debug events recorded" if after.record == "debug" else "debug events not recorded"
        )
    for of in ("debug", "info"):
        if after.days(of) != before.days(of):
            changes.append(
                f"{of} events kept {kept_for(after.days(of))} (was {kept_for(before.days(of))})"
            )
    if after.sign_in_ips != before.sign_in_ips:
        changes.append(
            "IP addresses recorded with sign-in events"
            if after.sign_in_ips
            else "IP addresses not recorded with sign-in events"
        )
    if changes:
        audit.save_settings(db, after)
        audit.record(db, user, "audit.settings_changed", changes="; ".join(changes))
        db.commit()
    return settings_out(db)

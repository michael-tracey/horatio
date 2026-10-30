"""The custodian's search of the audit log, across every troupe. It only reads:
nothing here changes or removes what the log holds."""

import csv
import io
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, Text, and_, false, func, literal_column, or_, select
from sqlalchemy import tuple_ as row
from sqlalchemy.orm import aliased

from horatio import audit, handles
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
    AuditGroup.APPROVALS: ("Approvals", ("approval.", "standing.", "home_troupe.")),
    AuditGroup.XP: ("XP", ("xp.", "troupe.starting_xp", "troupe.xp_", "downtime.completion_xp")),
    AuditGroup.SHEETS: (
        "Sheets",
        ("sheet.", "character.", "picture.", "identity.", "retainer.", "embrace."),
    ),
    AuditGroup.CREATION: ("Character creation", ("creation.",)),
    AuditGroup.STATUS: ("Status", ("status.", "troupe.status_by")),
    AuditGroup.TITLES: ("Titles", ("title.", "troupe.titles_by")),
    AuditGroup.DOWNTIMES: ("Downtimes", ("downtime.", "response.", "delivery.", "quest.")),
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
    AuditGroup.TROUPES: ("Troupes", ("troupe.", "troupe_request.", "connector.", "location.")),
    AuditGroup.ACCOUNTS: ("Accounts", ("account.",)),
    AuditGroup.SYSTEM: ("System", ("backup.", "clan_logo.", "audit.")),
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


class AuditEntry(LogEntry):
    troupe_id: uuid.UUID | None
    troupe_name: str | None


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
    troupes = {
        event_id: (troupe_id, name)
        for event_id, troupe_id, name in db.execute(
            select(AuditEvent.id, Troupe.id, Troupe.name)
            .join(Troupe, AuditEvent.troupe_id == Troupe.id)
            .where(AuditEvent.id.in_([e.id for e in entries]))
        )
    }
    return [
        AuditEntry(
            **entry.model_dump(),
            troupe_id=troupes.get(entry.id, (None, None))[0],
            troupe_name=troupes.get(entry.id, (None, None))[1],
        )
        for entry in entries
    ]


Person = Annotated[str | None, Query(description="Who did it: their handle.")]
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
    writer.writerow(["When (UTC)", "Who", "Troupe", "Character", "Player", "Action", "What"])
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

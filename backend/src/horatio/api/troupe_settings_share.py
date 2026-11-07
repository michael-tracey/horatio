"""Sharing a troupe's settings (horatio.troupe_settings_share), under Customise › Share
settings: its running staff export them; its storytellers review a file, or another
troupe they run, against it, and import what they tick."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from horatio import troupe_settings_share as share
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe
from horatio.permissions import TroupeAction

router = APIRouter(prefix="/troupes/{troupe_id}/settings-share", tags=["share settings"])


async def capped(request: Request) -> None:
    """Refuse a document over the size cap before reading it."""
    if len(await request.body()) > share.MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, "That file is too large to be a troupe's settings."
        )


class ShareSectionOut(BaseModel):
    key: share.SectionKey
    label: str
    # The group it is in: "Troupe settings", whose page has several; None for its own tab.
    group: str | None
    count: int


class ShareExportOut(BaseModel):
    # What the file holds.
    document: share.SettingsDocument
    # Its sections, in order, with how many items each has: the checklist.
    sections: list[ShareSectionOut]


class ShareEditableOut(BaseModel):
    field: str
    label: str
    multiline: bool
    # A list, edited one entry per line.
    lines: bool


class ShareReviewItemOut(BaseModel):
    # Where it is in the document: `document.sections[section][index]`.
    section: share.SectionKey
    index: int
    label: str
    # new | changes (with what it is now, and would be) | same (nothing to do) | cannot.
    status: share.Status
    reason: str | None
    before: str | None
    after: str | None
    # Its fields with free text, which can be edited before importing.
    editable: list[ShareEditableOut]


class ShareReviewSectionOut(BaseModel):
    key: share.SectionKey
    label: str
    group: str | None
    items: list[ShareReviewItemOut]


class ShareReviewOut(BaseModel):
    # The troupe the document came from.
    troupe: str
    # Only the sections the document has items in.
    sections: list[ShareReviewSectionOut]
    warnings: list[str]


class ShareReviewIn(share.Strict):
    document: share.SettingsDocument


class SharePickIn(share.Strict):
    section: share.SectionKey
    index: int = Field(ge=0)


class ShareImportIn(share.Strict):
    # The document as reviewed, with any text edited.
    document: share.SettingsDocument
    # The items ticked.
    items: list[SharePickIn] = Field(max_length=10000)
    # Where it came from, for the log: the file's name, or a troupe its importer runs.
    file_name: str | None = Field(default=None, max_length=200)
    from_troupe_id: uuid.UUID | None = None


class ShareImportedSectionOut(BaseModel):
    key: share.SectionKey
    label: str
    added: int
    changed: int


class ShareImportOut(BaseModel):
    added: int
    changed: int
    sections: list[ShareImportedSectionOut]


def sections_out(document: share.SettingsDocument) -> list[ShareSectionOut]:
    return [
        ShareSectionOut(key=key, label=label, group=group, count=len(share.items(document, key)))
        for key, (label, group) in share.SECTIONS.items()
    ]


@router.get("")
def export_settings(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ShareExportOut:
    """The troupe's settings that differ from Horatio's default, by section. Its running
    staff may export them, to a file or to another troupe they run."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    document = share.export(db, troupe)
    return ShareExportOut(document=document, sections=sections_out(document))


def importing(db: DbSession, user: CurrentUser, troupe_id: uuid.UUID) -> Troupe:
    """A troupe its storyteller may import settings into: never an archived one."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    if troupe.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This troupe is archived.")
    return troupe


@router.post("/review", dependencies=[Depends(capped)])
def review_settings(
    troupe_id: uuid.UUID, body: ShareReviewIn, db: DbSession, user: CurrentUser
) -> ShareReviewOut:
    """Each item of a document against this troupe: new, changing what it has (with
    before and after), the same as it has, or not importable here (with why). Nothing
    is saved."""
    troupe = importing(db, user, troupe_id)
    found = share.review(db, troupe, body.document)
    sections = [
        ShareReviewSectionOut(
            key=key,
            label=label,
            group=group,
            items=[item_out(r) for r in found.items if r.section == key],
        )
        for key, (label, group) in share.SECTIONS.items()
    ]
    return ShareReviewOut(
        troupe=found.troupe, sections=[s for s in sections if s.items], warnings=found.warnings
    )


def item_out(found: share.Reviewed) -> ShareReviewItemOut:
    return ShareReviewItemOut(
        section=found.section,
        index=found.index,
        label=found.label,
        status=found.status,
        reason=found.reason,
        before=found.before,
        after=found.after,
        editable=[
            ShareEditableOut(field=e.field, label=e.label, multiline=e.multiline, lines=e.lines)
            for e in found.editable
        ],
    )


@router.post("/apply", dependencies=[Depends(capped)])
def apply_settings(
    troupe_id: uuid.UUID, body: ShareImportIn, db: DbSession, user: CurrentUser
) -> ShareImportOut:
    """Import the ticked items, all or none, merging: what matches is changed, the rest
    added, and nothing else in the troupe is touched. Copying from another troupe needs
    its importer to run that one too."""
    troupe = importing(db, user, troupe_id)
    source: str = body.file_name or body.document.troupe or "a file"
    if body.from_troupe_id is not None:
        source = staff_troupe(
            db, user, body.from_troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS
        ).name
    picks = [share.Pick(p.section, p.index) for p in body.items]
    applied = share.apply(db, user, troupe, body.document, picks, source)
    db.commit()
    return ShareImportOut(
        added=sum(applied.added.values()),
        changed=sum(applied.changed.values()),
        sections=[
            ShareImportedSectionOut(
                key=key,
                label=label,
                added=applied.added.get(key, 0),
                changed=applied.changed.get(key, 0),
            )
            for key, (label, _) in share.SECTIONS.items()
            if applied.added.get(key) or applied.changed.get(key)
        ],
    )

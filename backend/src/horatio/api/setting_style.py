"""A troupe's Setting Style Document (horatio.setting_style): its running staff write
the subtitle, teaser, scope, themes, moods and storyteller notes under Troupe
settings, and the rest is built from the troupe's own settings
(horatio.api.setting_document). Anyone signed in reads it, as the book makes the
document a handout, and anyone at all when its storytellers show it on a public
profile."""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.orm import Session

from horatio import audit, setting_style
from horatio.api.downtimes import staff_troupe
from horatio.api.setting_document import GeneratedOut, generated_out
from horatio.api.troupe_profiles import Profile, viewable
from horatio.api.written_rules import readable
from horatio.auth.deps import CurrentUser, DbSession, MaybeUser
from horatio.models import ChronicleMotif, Troupe, User
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.setting_style import Kind, SettingError

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["setting style"])
presets_router = APIRouter(tags=["setting style"])

Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]
Markdown = Annotated[str, Field(max_length=20000)]


class SettingTextIn(BaseModel):
    subtitle: Annotated[Trimmed, Field(max_length=200)] = ""
    # Markdown, the chronicle's in-world teaser.
    teaser: Annotated[Trimmed, Field(max_length=20000)] = ""
    # The scope's power and agency (MET: VTM p. 330), a few words or lines each.
    power: Annotated[Trimmed, Field(max_length=2000)] = ""
    agency: Annotated[Trimmed, Field(max_length=2000)] = ""


class SettingEntryWords(BaseModel):
    # A theme's or mood's name; ignored for a note.
    name: Annotated[Trimmed, Field(max_length=100)] = ""
    # Markdown: a theme's questions, a mood's feel, or the note itself.
    description: Markdown = ""


class SettingEntryIn(SettingEntryWords):
    kind: Kind
    # The book sample it starts from, for a theme or mood (GET /setting-presets).
    book_key: str | None = None


class SettingOrderIn(BaseModel):
    kind: Kind
    # Every entry of the kind, once each, in the new order.
    ids: list[uuid.UUID]


class SettingEntryOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    name: str
    description: str
    # The book sample it was started from, and that sample's page.
    book_key: str | None
    page: int | None


class SettingPublicIn(BaseModel):
    public: bool


class SettingOut(BaseModel):
    # The troupe's name, for a reader with no troupe page around it (the profile, print).
    troupe: str
    # The chronicle's name and city, as the profile has them: the document's title,
    # and the locale of its scope.
    chronicle: str
    locale: str
    subtitle: str
    teaser: str
    power: str
    agency: str
    # Each in the order staff put it.
    themes: list[SettingEntryOut]
    moods: list[SettingEntryOut]
    notes: list[SettingEntryOut]
    # The parts built from the troupe's own settings (#771).
    generated: GeneratedOut
    # Whether the troupe's profile shows it too.
    public: bool
    # Whether the viewer may write it, and may show it on the profile or not.
    can_edit: bool
    can_publish: bool = False


class SettingPresetOut(BaseModel):
    kind: Kind
    key: str
    name: str
    page: int
    description: str


def entry_out(motif: ChronicleMotif) -> SettingEntryOut:
    kind = setting_style.kind_of(motif)
    sample = setting_style.preset(kind, motif.book_key) if motif.book_key else None
    return SettingEntryOut(
        id=motif.id,
        kind=kind,
        name=motif.name,
        description=motif.description,
        book_key=motif.book_key,
        page=sample.page if sample else None,
    )


def can_do(db: Session, user: User | None, troupe: Troupe, action: TroupeAction) -> bool:
    return (
        user is not None
        and (troupe.archived_at is None or user.is_custodian)
        and allows(troupe_role(db, user, troupe), action, is_custodian=user.is_custodian)
    )


def can_write(db: Session, user: User | None, troupe: Troupe) -> bool:
    return can_do(db, user, troupe, TroupeAction.WRITE_SETTING)


def setting_out(db: Session, user: User | None, troupe: Troupe) -> SettingOut:
    profile = Profile.model_validate(troupe.profile)
    entries = [entry_out(m) for m in setting_style.listed(db, troupe.id)]
    return SettingOut(
        troupe=troupe.name,
        chronicle=profile.setting.chronicle,
        locale=profile.setting.city,
        subtitle=troupe.setting_subtitle,
        teaser=troupe.setting_teaser,
        power=troupe.setting_power,
        agency=troupe.setting_agency,
        themes=[e for e in entries if e.kind == "theme"],
        moods=[e for e in entries if e.kind == "mood"],
        notes=[e for e in entries if e.kind == "note"],
        generated=generated_out(db, troupe),
        public=troupe.setting_public,
        can_edit=can_write(db, user, troupe),
        can_publish=can_do(db, user, troupe, TroupeAction.EDIT_PROFILE),
    )


def writable(db: Session, user: User, troupe_id: uuid.UUID) -> Troupe:
    return staff_troupe(db, user, troupe_id, TroupeAction.WRITE_SETTING)


def troupe_entry(db: Session, troupe: Troupe, entry_id: uuid.UUID) -> ChronicleMotif:
    motif = db.get(ChronicleMotif, entry_id)
    if motif is None or motif.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry.")
    return motif


def refused(error: SettingError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


def words_of(body: SettingEntryWords) -> setting_style.Words:
    return setting_style.Words(name=body.name, description=body.description.strip())


@presets_router.get("/setting-presets")
def read_setting_presets(user: CurrentUser) -> list[SettingPresetOut]:
    """The book's sample themes (p. 325) and moods (pp. 325-326), to start an entry
    from: their descriptions are in our own words."""
    return [
        SettingPresetOut(
            kind=p.kind, key=p.key, name=p.name, page=p.page, description=p.description
        )
        for p in setting_style.presets()
    ]


@router.get("/setting")
def read_setting(troupe_id: uuid.UUID, db: DbSession, user: MaybeUser) -> SettingOut:
    """The troupe's Setting Style Document: what its staff write, and what its own
    settings give. Anyone signed in may read it, as it is the chronicle's handout for
    players; anyone at all when its profile is public and shows it."""
    if user is not None:
        return setting_out(db, user, readable(db, user, troupe_id))
    troupe = viewable(db, None, troupe_id)
    if not troupe.setting_public:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return setting_out(db, None, troupe)


@router.put("/setting/public")
def show_setting_on_profile(
    troupe_id: uuid.UUID, body: SettingPublicIn, db: DbSession, user: CurrentUser
) -> SettingOut:
    """Show the document on the troupe's profile too, or not: off unless its
    storytellers switch it on. A public profile shows it to anyone at all."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.EDIT_PROFILE)
    if body.public != troupe.setting_public:
        troupe.setting_public = body.public
        audit.record(
            db,
            user,
            "troupe.setting_public",
            troupe_id=troupe.id,
            state="shows its setting" if body.public else "no longer shows its setting",
        )
    db.commit()
    return setting_out(db, user, troupe)


@router.put("/setting")
def write_setting_text(
    troupe_id: uuid.UUID, body: SettingTextIn, db: DbSession, user: CurrentUser
) -> SettingOut:
    """The subtitle, teaser, power and agency, all at once."""
    troupe = writable(db, user, troupe_id)
    setting_style.write_text(
        db,
        user,
        troupe,
        setting_style.Text(
            subtitle=body.subtitle, teaser=body.teaser, power=body.power, agency=body.agency
        ),
    )
    db.commit()
    return setting_out(db, user, troupe)


@router.post("/setting/entries", status_code=status.HTTP_201_CREATED)
def add_setting_entry(
    troupe_id: uuid.UUID, body: SettingEntryIn, db: DbSession, user: CurrentUser
) -> SettingOut:
    """Add a theme, mood or storyteller note, last in its list."""
    troupe = writable(db, user, troupe_id)
    try:
        setting_style.add(db, user, troupe, body.kind, words_of(body), body.book_key)
    except SettingError as error:
        raise refused(error) from None
    db.commit()
    return setting_out(db, user, troupe)


@router.put("/setting/entries/{entry_id}")
def change_setting_entry(
    troupe_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: SettingEntryWords,
    db: DbSession,
    user: CurrentUser,
) -> SettingOut:
    """Change an entry's name and description; a note's text."""
    troupe = writable(db, user, troupe_id)
    motif = troupe_entry(db, troupe, entry_id)
    try:
        setting_style.change(db, user, troupe, motif, words_of(body))
    except SettingError as error:
        raise refused(error) from None
    db.commit()
    return setting_out(db, user, troupe)


@router.delete("/setting/entries/{entry_id}")
def remove_setting_entry(
    troupe_id: uuid.UUID, entry_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> SettingOut:
    troupe = writable(db, user, troupe_id)
    setting_style.remove(db, user, troupe, troupe_entry(db, troupe, entry_id))
    db.commit()
    return setting_out(db, user, troupe)


@router.put("/setting/order")
def order_setting_entries(
    troupe_id: uuid.UUID, body: SettingOrderIn, db: DbSession, user: CurrentUser
) -> SettingOut:
    """Put the themes, the moods or the notes in a new order."""
    troupe = writable(db, user, troupe_id)
    try:
        setting_style.reorder(db, user, troupe, body.kind, body.ids)
    except SettingError as error:
        raise refused(error) from None
    db.commit()
    return setting_out(db, user, troupe)

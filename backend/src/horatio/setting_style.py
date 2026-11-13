"""A troupe's Setting Style Document (issues #770, #773): the short handout the book
has a chronicle give its players (MET: VTM ch. 8, pp. 331-336), with its title,
themes, moods, scope, teaser and storyteller notes.

Here are the parts staff write themselves. The chronicle's title is the profile's
chronicle name, with a subtitle under it ("A City Under Siege"); the teaser is the
in-world text, separate from the troupe's description (the listing's blurb). The
scope (pp. 329-330) is its locale, which is the profile's city, and a few words each
on the power and agency of its characters. Themes and moods (pp. 324-326) are each an
entry of their own, as are the storyteller notes; staff start a theme or mood from
one of the book's samples or write their own, and put each list in the order they
like. The whole document is player-facing: the book makes it a handout.
"""

import tomllib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import Literal, cast, get_args

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import ChronicleMotif, Troupe, User
from horatio.rules.files import DATA_DIR
from horatio.titles import and_list

PRESETS_FILE = DATA_DIR / "bns_met_vampire_setting.toml"

Kind = Literal["theme", "mood", "note"]
KINDS: tuple[Kind, ...] = get_args(Kind)
# How each kind reads in the log.
NOUNS: dict[Kind, str] = {"theme": "theme", "mood": "mood", "note": "storyteller note"}


@dataclass(frozen=True)
class Preset:
    """One of the book's sample themes or moods, its description in our words."""

    kind: Kind
    key: str
    name: str
    page: int
    description: str


@cache
def presets() -> tuple[Preset, ...]:
    """The book's sample themes, then its moods, in the book's order."""
    raw = tomllib.loads(PRESETS_FILE.read_text())
    found: list[Preset] = []
    tables: tuple[tuple[Kind, str], ...] = (("theme", "themes"), ("mood", "moods"))
    for kind, table in tables:
        for entry in raw[table]:
            found.append(
                Preset(kind, entry["key"], entry["name"], entry["page"], entry["description"])
            )
    return tuple(found)


def preset(kind: Kind, key: str) -> Preset | None:
    return next((p for p in presets() if p.kind == kind and p.key == key), None)


def listed(db: Session, troupe_id: uuid.UUID) -> list[ChronicleMotif]:
    """The troupe's entries, each kind in the order staff put it."""
    return list(
        db.scalars(
            select(ChronicleMotif)
            .where(ChronicleMotif.troupe_id == troupe_id)
            .order_by(ChronicleMotif.kind, ChronicleMotif.position, ChronicleMotif.id)
        )
    )


def kind_of(motif: ChronicleMotif) -> Kind:
    return cast(Kind, motif.kind)


def of_kind(db: Session, troupe_id: uuid.UUID, kind: Kind) -> list[ChronicleMotif]:
    return [m for m in listed(db, troupe_id) if m.kind == kind]


def label(motif: ChronicleMotif) -> str:
    """How an entry reads in the log: its name, or a note's first words."""
    if motif.name:
        return motif.name
    words = " ".join(motif.description.split())
    return words if len(words) <= 60 else f"{words[:57]}…"


class SettingError(ValueError):
    """Something staff asked for that the document can't hold."""


@dataclass(frozen=True)
class Words:
    """An entry as staff write it, trimmed."""

    name: str
    description: str


def check_words(kind: Kind, words: Words) -> None:
    if kind == "note":
        if not words.description.strip():
            raise SettingError("Write the note.")
    elif not words.name:
        raise SettingError(f"Give the {kind} a name.")


def add(
    db: Session, user: User, troupe: Troupe, kind: Kind, words: Words, book_key: str | None
) -> ChronicleMotif:
    """Add an entry, last in its list. One started from a book sample keeps its key,
    and the troupe has each sample once."""
    if book_key is not None:
        if kind == "note" or preset(kind, book_key) is None:
            raise SettingError(f"The book has no {kind} {book_key!r}.")
        if any(m.book_key == book_key for m in of_kind(db, troupe.id, kind)):
            raise SettingError(f"The troupe already has the book's {kind} {book_key!r}.")
    check_words(kind, words)
    last = db.scalar(
        select(func.max(ChronicleMotif.position)).where(
            ChronicleMotif.troupe_id == troupe.id, ChronicleMotif.kind == kind
        )
    )
    motif = ChronicleMotif(
        troupe_id=troupe.id,
        kind=kind,
        name="" if kind == "note" else words.name,
        description=words.description,
        book_key=book_key,
        position=(last or 0) + 1,
    )
    db.add(motif)
    db.flush()
    audit.record(
        db,
        user,
        "troupe.setting_entry_added",
        troupe_id=troupe.id,
        kind=NOUNS[kind],
        name=label(motif),
    )
    return motif


def change(db: Session, user: User, troupe: Troupe, motif: ChronicleMotif, words: Words) -> None:
    kind = kind_of(motif)
    check_words(kind, words)
    if kind != "note":
        motif.name = words.name
    motif.description = words.description
    db.flush()
    audit.record(
        db,
        user,
        "troupe.setting_entry_changed",
        troupe_id=troupe.id,
        kind=NOUNS[kind],
        name=label(motif),
    )


def reorder(db: Session, user: User, troupe: Troupe, kind: Kind, ids: Sequence[uuid.UUID]) -> None:
    """Put the kind's entries in the order given, which must name each once."""
    found = of_kind(db, troupe.id, kind)
    by_id = {m.id: m for m in found}
    if len(ids) != len(found) or set(ids) != set(by_id):
        raise SettingError(f"Give every {NOUNS[kind]} once, in its new order.")
    if [m.id for m in found] == list(ids):
        return
    for n, motif_id in enumerate(ids, start=1):
        by_id[motif_id].position = n
    db.flush()
    audit.record(
        db,
        user,
        "troupe.setting_entries_ordered",
        troupe_id=troupe.id,
        kind=f"{NOUNS[kind]}s",
        names=", ".join(label(by_id[i]) for i in ids),
    )


def remove(db: Session, user: User, troupe: Troupe, motif: ChronicleMotif) -> None:
    kind = kind_of(motif)
    db.delete(motif)
    db.flush()
    audit.record(
        db,
        user,
        "troupe.setting_entry_removed",
        troupe_id=troupe.id,
        kind=NOUNS[kind],
        name=label(motif),
    )


@dataclass(frozen=True)
class Text:
    """The document's text of its own, trimmed."""

    subtitle: str
    teaser: str
    power: str
    agency: str


TEXT_PARTS = ("subtitle", "teaser", "power", "agency")


def text_of(troupe: Troupe) -> Text:
    return Text(
        subtitle=troupe.setting_subtitle,
        teaser=troupe.setting_teaser,
        power=troupe.setting_power,
        agency=troupe.setting_agency,
    )


def write_text(db: Session, user: User, troupe: Troupe, text: Text) -> None:
    """Save the subtitle, teaser, power and agency; the log says which changed."""
    was = text_of(troupe)
    changed = [name for name in TEXT_PARTS if getattr(was, name) != getattr(text, name)]
    if not changed:
        return
    troupe.setting_subtitle = text.subtitle
    troupe.setting_teaser = text.teaser
    troupe.setting_power = text.power
    troupe.setting_agency = text.agency
    db.flush()
    audit.record(
        db,
        user,
        "troupe.setting_text",
        troupe_id=troupe.id,
        parts=and_list(changed),
    )

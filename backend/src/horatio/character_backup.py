"""Backing up a character (issue #567): exporting it as a file, and importing one.

**The document** is what Export downloads and Import reads, as the settings share's
is (horatio.troupe_settings_share): a format and its version, the Horatio and rule
set versions it was made against, the troupe it came from, and the character. It
never holds an id: traits are named by category, name and detail; a line of the XP
history names the one it corrects by its place in the history; a person (in a
troupe's bulk export only) by handle, and by email only if staff ask for it.

It holds the character's identity, its sheet trait by trait with its free dots,
creation picks and merit choices (so nothing is guessed again by fitting), the XP
history line by line with what was paid for each trait, its backstory, and its
picture. Equipment, Retainers (with Alternate Identities) and titles and status are
optional sections, chosen at export. Downtime history is not in this version.

What is never in it: staff notes of any kind (an item's, an approval's, a
diablerie's victim), the backstory's feedback thread, other characters' data (a
Retainer's or a domitor's link, a status's patron, beyond the names the sheet
shows) and the troupe's own logs. A file can be handed to its player as it is.

**Reading** checks the format and its version: an older one is upgraded, a newer one
refused, saying so.

**Importing** makes a new character from a document, in one transaction. Each trait
is found by name in the rules it will play by and set as the file has it, free dots
and picks too, as the Yorick import sets an NPC's (horatio.import_yorick_print): the
sheet's checks then flag anything it breaks, as on any sheet. Its backstory and
Retainers go through the same saves as by hand. Each part is tried on its own, so a
part that can't come in (a trait this troupe's rule set lacks, a house merit it
doesn't have) is left out and says why, and the rest comes in. Reviewing is the
same import, rolled back: what it shows is exactly what importing would do.

A player's import is a new character in their vault, not yet in any troupe, built
by the troupe they choose (or the plain rule set). Its XP history comes with it:
each line earned elsewhere as self-entered XP, which the troupe it asks to make its
home keeps or removes (horatio.xp_range), and what it paid for each trait as that
trait's purchase, so the home troupe change sets it against the troupe's prices
(horatio.reconciliation). Nothing is repriced on the way in. Equipment, titles and
status are shown, not imported: a home troupe's storytellers give those.
"""

import base64
import binascii
import re
import unicodedata
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from fastapi import HTTPException
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from horatio import audit, backstories, domitors, equipment, pictures, reconciliation, retainers
from horatio.models import (
    AlternateIdentity,
    Backstory,
    Character,
    CharacterTitle,
    CharacterTrait,
    HeldStatus,
    ReconciliationItem,
    RuleSet,
    StockNpc,
    TraitCategory,
    TraitDefinition,
    Troupe,
    User,
    XpEntry,
)
from horatio.npc_gifts import PLAYABLE_KINDS
from horatio.rules.pricing import PricingError, trait_cost
from horatio.rules.splats import SPLATS
from horatio.sheets import (
    EARNED_KINDS,
    earned_and_spent,
    find_definition,
    house_refusal,
    replace_choice,
    rules_for,
    sheet_rows,
    sync_fixed_ratings,
    unprocessable,
)

FORMAT = "horatio-character"
FORMAT_VERSION = 1
# The most a document may be, as a request: its picture is in it.
MAX_BYTES = 16 * 1024 * 1024
# The file a single character is exported as, after its name.
SUFFIX = ".horatio-character.json"

Section = Literal["equipment", "retainers", "titles"]
SECTIONS: dict[Section, str] = {
    "equipment": "Equipment",
    "retainers": "Retainers and Alternate Identities",
    "titles": "Titles and status",
}

Name = Annotated[str, Field(max_length=200)]
Text = Annotated[str, Field(max_length=10_000)]
XpKind = Literal[
    "award",
    "purchase",
    "settlement",
    "fee",
    "correction",
    "self_entered",
    "cap",
    "reprice",
    "debt",
    "lost",
    "creation",
]


class Strict(BaseModel):
    """Refuses keys it doesn't know: the file is untrusted."""

    model_config = ConfigDict(extra="forbid")


# --- the document ------------------------------------------------------------------------


class BackupTraitRef(Strict):
    category: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    detail: Name = ""


class BackupTrait(BackupTraitRef):
    """One trait on the sheet, with where its dots came from."""

    rating: int | None = Field(default=None, ge=0, le=100)
    # Dots it has without paying XP: from creation, or given by another trait.
    free_rating: int = Field(default=0, ge=0, le=100)
    # The part of the rating other traits give (Rugged's health level); negative for
    # a flaw that takes dots away.
    granted_rating: int = Field(default=0, ge=-100, le=100)
    # The creation pick placed on it, and on an NPC whose picks are fitted, how.
    creation_pick: int | None = Field(default=None, ge=0, le=100)
    pick_by: Literal["fit", "staff", "off"] | None = None
    # On such an NPC, the free dots a merit it holds gives this trait (Ventrue
    # Royalty's places, a Path merit's conversion), the grant's key, and how it was
    # placed, as `pick_by` says.
    grant_place: int | None = Field(default=None, ge=0, le=100)
    place_grant: Annotated[str, Field(max_length=200)] | None = None
    place_by: Literal["fit", "staff", "off"] | None = None
    note: Text = ""
    # A merit's free choices, and what was chosen with a discipline's powers.
    choices: list[dict[str, JsonValue]] = Field(default=[], max_length=50)
    power_choices: dict[str, dict[str, str]] = Field(default={}, max_length=100)
    # A house merit or flaw of the troupe the file came from.
    house: bool = False
    # XP it paid for the trait there, net of refunds, repricing and settlements.
    paid: int = Field(default=0, ge=-10_000, le=10_000)

    @model_validator(mode="after")
    def dots_add_up(self) -> "BackupTrait":
        if self.rating is None:
            if self.free_rating or self.creation_pick is not None:
                raise ValueError(f"{self.name} has no rating, so it can have no free dots")
        elif self.free_rating > self.rating:
            raise ValueError(f"{self.name} has more free dots than its rating")
        if self.creation_pick is not None and self.creation_pick > self.free_rating:
            raise ValueError(f"{self.name}'s creation pick is more than its free dots")
        if self.pick_by == "off" and self.creation_pick is not None:
            raise ValueError(f"{self.name}'s pick was taken off, yet it has one")
        if self.pick_by in ("fit", "staff") and self.creation_pick is None:
            raise ValueError(f"{self.name}'s pick was placed, yet it has none")
        if self.grant_place is not None and self.grant_place > self.free_rating:
            raise ValueError(f"{self.name}'s granted place is more than its free dots")
        placed = self.grant_place is not None and self.place_grant is not None
        unplaced = self.grant_place is None and self.place_grant is None
        if not (
            (self.place_by is None and unplaced)
            or (self.place_by == "off" and unplaced)
            or (self.place_by in ("fit", "staff") and placed)
        ):
            raise ValueError(f"{self.name}'s granted place doesn't add up")
        return self

    def key(self) -> tuple[str, str, str]:
        return (self.category, self.name, self.detail)

    def label(self) -> str:
        return f"{self.name}: {self.detail}" if self.detail else self.name


class BackupXpLine(Strict):
    """One line of the XP history, as it was written."""

    kind: XpKind
    amount: int = Field(ge=-100_000, le=100_000)
    reason: Annotated[str, Field(max_length=2000)] = ""
    on: date
    trait: BackupTraitRef | None = None
    from_rating: int | None = None
    to_rating: int | None = None
    # The line it corrects (or reprices), by its place in the history from 0.
    corrects: int | None = Field(default=None, ge=0)


class BackupCrop(Strict):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    size: float = Field(gt=0, le=1)


class BackupPicture(Strict):
    """The character's picture, whole, and where its portrait sits in it: in the
    file itself (`data`, base64), or beside it in a bulk export's pictures/."""

    data: str | None = None
    file: Annotated[str, Field(max_length=300)] | None = None
    crop: BackupCrop | None = None


class BackupIdentity(Strict):
    name: str = Field(min_length=1, max_length=200)
    splat: str = Field(min_length=1, max_length=20)
    kind: Literal["pc", "npc"] = "pc"
    # An NPC's kind and form (horatio.rules.npc_kinds), and a custom kind as staff set it.
    npc_kind: Annotated[str, Field(max_length=50)] | None = None
    npc_form: Literal["sheeted", "stock"] | None = None
    npc_custom_kind: dict[str, JsonValue] | None = None
    pronouns: Annotated[str, Field(max_length=200)] | None = None
    # Retired characters can be exported, with why they left.
    retired: bool = False
    left_reason: Literal["final_death", "off_field", "inactive"] | None = None
    # A ghoul's domitor, by name only.
    domitor: Name = ""
    primary_paths: dict[str, str] = Field(default={}, max_length=20)
    card_text: Text = ""
    card_flavour: Text = ""
    # An NPC built without the wizard, whose creation picks are fitted to its sheet
    # (horatio.npc_picks), and one staff list on the Who's Who with no title.
    fits_picks: bool = False
    on_whos_who: bool = False


class BackupStock(Strict):
    """What a Stock NPC has in place of a sheet: its rating and specializations."""

    rating: int = Field(ge=1, le=20)
    specializations: list[dict[str, str]] = Field(default=[], max_length=100)


class BackupPlayer(Strict):
    """Whose character it is, in a troupe's bulk export: to match it on import."""

    handle: Name = ""
    email: Name | None = None
    name: Name = ""


class BackupEquipment(Strict):
    name: Name
    kind: str = Field(max_length=50)
    grade: Literal["cheap", "standard", "special"]
    qualities: list[dict[str, str]] = Field(default=[], max_length=50)
    crafted: bool = False
    archaic: bool = False
    effects: list[dict[str, str]] = Field(default=[], max_length=50)
    description: Text = ""
    # The troupe that made it special, by name.
    special_by: Name | None = None


class BackupRetainer(Strict):
    name: Name
    dots: int = Field(ge=1, le=10)
    description: Text = ""
    from_merit: Name = ""
    lost: Literal["released", "killed"] | None = None
    lost_on: date | None = None
    ghoul: bool = False
    specialties: list[str] = Field(default=[], max_length=10)
    discipline: Name = ""


class BackupAlternateIdentity(Strict):
    name: Name
    accepted_by: Name = ""


class BackupTitle(Strict):
    troupe: Name
    name: Name
    active: bool = False


class BackupStatus(Strict):
    name: Name
    patron: Name = ""
    place: Name = ""
    given_on: date
    story: Text = ""


class CharacterDocument(Strict):
    """A character, as Export writes it and Import reads it."""

    format: Literal["horatio-character"] = FORMAT
    version: Literal[1] = FORMAT_VERSION
    horatio: str = Field(default="", max_length=50)
    # The version of the rule set its sheet is built on.
    rule_set: int | None = None
    # The troupe it came from: its home troupe, or an NPC's own; empty for none.
    troupe: Name = ""
    exported_on: date | None = None
    # The optional sections chosen at export.
    sections: list[Section] = []
    player: BackupPlayer | None = None
    character: BackupIdentity
    stock: BackupStock | None = None
    picture: BackupPicture | None = None
    traits: list[BackupTrait] = Field(default=[], max_length=1000)
    xp: list[BackupXpLine] = Field(default=[], max_length=20_000)
    backstory: Annotated[str, Field(max_length=backstories.MAX_LENGTH)] = ""
    equipment: list[BackupEquipment] = Field(default=[], max_length=500)
    retainers: list[BackupRetainer] = Field(default=[], max_length=retainers.MAX_LISTED)
    identities: list[BackupAlternateIdentity] = Field(default=[], max_length=50)
    titles: list[BackupTitle] = Field(default=[], max_length=100)
    status: list[BackupStatus] = Field(default=[], max_length=500)

    @model_validator(mode="after")
    def corrections_come_after(self) -> "CharacterDocument":
        for n, line in enumerate(self.xp):
            if line.corrects is not None and line.corrects >= n:
                raise ValueError(f"XP line {n + 1} corrects one that isn't before it")
        return self


# --- reading -----------------------------------------------------------------------------

# Upgrades from older versions, each to the next: none yet, as this is the first.
UPGRADES: dict[int, Any] = {}


def read(raw: Any) -> CharacterDocument:
    """The document a file holds, upgraded to this version. Refused, saying why, if it
    isn't a character from Horatio, or is from a newer one."""
    found = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    if found.get("format") != FORMAT:
        raise unprocessable(
            "That file isn't a Horatio character: choose a .json file exported from Horatio."
        )
    number = found.get("version")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise unprocessable("That file has no format version Horatio knows.")
    if number > FORMAT_VERSION:
        raise unprocessable(
            f"That file is from a newer Horatio (character format version {number}); this one"
            f" reads up to version {FORMAT_VERSION}. Import it into a Horatio as new as the one"
            " that made it."
        )
    while number < FORMAT_VERSION:
        found = UPGRADES[number](found)
        number += 1
    try:
        return CharacterDocument.model_validate(found)
    except ValidationError as error:
        first = error.errors()[0]
        where = " › ".join(str(p) for p in first["loc"])
        raise unprocessable(f"That file can't be read: {where}: {first['msg']}") from error


# --- exporting ---------------------------------------------------------------------------


def horatio_version() -> str:
    try:
        return version("horatio")
    except PackageNotFoundError:
        return ""


def slug(name: str) -> str:
    """A name fit for a file: "Agnes de Vries" is "agnes-de-vries"."""
    found = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return found[:60].strip("-") or "character"


def name_part(name: str) -> str:
    """A character's name as a file name has it: accents folded to their plain letter,
    then spaces, other letters and anything unsafe in a file name dropped, case kept.
    "Agnes de Vries" is "AgnesdeVries"; a name with nothing left is "character"."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9_-]", "", folded)[:60] or "character"


def file_stem(name: str, on: date) -> str:
    """A backup's files are named for the character and the day it was exported:
    "AgnesdeVries-2026-11-09", then ".horatio-character.json" or ".html"."""
    return f"{name_part(name)}-{on.isoformat()}"


# A backstory's marks around the sections a set of the troupe's questions built: they
# name the set by its id, which means nothing anywhere else.
QUESTION_MARK = re.compile(r"^<!-- /?questions:[0-9a-f-]+ -->\n?", re.MULTILINE)


def backstory_text(db: Session, character: Character) -> str:
    """The backstory as last submitted (never the draft), without the marks of the
    troupe's question sets."""
    found = db.scalar(select(Backstory).where(Backstory.character_id == character.id))
    return QUESTION_MARK.sub("", found.text) if found is not None else ""


def traits_of(db: Session, character: Character) -> list[BackupTrait]:
    paid = reconciliation.paid_for(db, character)
    return [
        BackupTrait(
            category=row.category.key,
            name=row.definition.name,
            detail=row.trait.detail,
            rating=row.trait.rating,
            free_rating=row.trait.free_rating,
            granted_rating=row.trait.granted_rating,
            creation_pick=row.trait.creation_pick,
            pick_by=cast(Any, row.trait.pick_by),
            grant_place=row.trait.grant_place,
            place_grant=row.trait.place_grant,
            place_by=cast(Any, row.trait.place_by),
            note=row.trait.note,
            choices=row.trait.choices,
            power_choices=row.trait.power_choices,
            house=row.definition.troupe_id is not None,
            paid=paid.get((row.definition.id, row.trait.detail), 0),
        )
        for row in sheet_rows(db, character)
    ]


def xp_of(db: Session, character: Character) -> list[BackupXpLine]:
    """The XP history in order, each line naming its trait (a settlement, the one
    its difference was about) and the line it corrects, by place."""
    settled = aliased(ReconciliationItem)
    settled_trait = aliased(TraitDefinition)
    settled_category = aliased(TraitCategory)
    rows = list(
        db.execute(
            select(
                XpEntry,
                TraitDefinition.name,
                TraitCategory.key,
                settled_trait.name,
                settled_category.key,
                settled.detail,
            )
            .outerjoin(TraitDefinition, XpEntry.trait_definition_id == TraitDefinition.id)
            .outerjoin(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .outerjoin(settled, XpEntry.reconciliation_item_id == settled.id)
            .outerjoin(settled_trait, settled.trait_definition_id == settled_trait.id)
            .outerjoin(settled_category, settled_trait.category_id == settled_category.id)
            .where(XpEntry.character_id == character.id)
            .order_by(XpEntry.id)
        )
    )
    place = {entry.id: n for n, (entry, *_) in enumerate(rows)}
    lines: list[BackupXpLine] = []
    for entry, name, category, settled_name, settled_key, settled_detail in rows:
        trait = None
        if name is not None and category is not None:
            trait = BackupTraitRef(category=category, name=name, detail=entry.detail or "")
        elif settled_name is not None and settled_key is not None:
            trait = BackupTraitRef(
                category=settled_key, name=settled_name, detail=settled_detail or ""
            )
        lines.append(
            BackupXpLine(
                kind=cast(XpKind, entry.kind),
                amount=entry.amount,
                reason=entry.reason,
                on=entry.entered_on,
                trait=trait,
                from_rating=entry.from_rating,
                to_rating=entry.to_rating,
                corrects=place.get(entry.corrects_id) if entry.corrects_id else None,
            )
        )
    return lines


def picture_of(
    character: Character, root: Path | None, *, embed: bool, file: str | None
) -> BackupPicture | None:
    """The whole picture as kept: in the document, or named as a file beside it."""
    if character.picture_id is None or root is None:
        return None
    path = pictures.picture_file(root, character.id, character.picture_id, "full.webp")
    if path is None:
        return None
    crop = BackupCrop(**character.picture_crop) if character.picture_crop else None
    if embed:
        return BackupPicture(data=base64.b64encode(path.read_bytes()).decode(), crop=crop)
    return BackupPicture(file=file, crop=crop)


def stock_of(db: Session, character: Character) -> BackupStock | None:
    """A Stock NPC's rating and specializations; never staff's notes on it."""
    found = db.scalar(select(StockNpc).where(StockNpc.character_id == character.id))
    if found is None:
        return None
    return BackupStock(rating=found.rating, specializations=found.specializations)


def equipment_of(db: Session, character: Character) -> list[BackupEquipment]:
    names = dict(db.execute(select(Troupe.id, Troupe.name)).all())
    return [
        BackupEquipment(
            name=item.name,
            kind=item.kind,
            grade=cast(Any, item.grade),
            qualities=item.qualities,
            crafted=item.crafted,
            archaic=item.archaic,
            effects=item.effects,
            description=item.description,
            special_by=names.get(item.special_troupe_id) if item.special_troupe_id else None,
        )
        for item in equipment.items_of(db, character)
    ]


def retainers_of(db: Session, character: Character) -> list[BackupRetainer]:
    return [
        BackupRetainer(
            name=r.name,
            dots=r.dots,
            description=r.description,
            from_merit=r.from_merit,
            lost=cast(Any, r.lost),
            lost_on=r.lost_on,
            ghoul=r.ghoul,
            specialties=r.specialties,
            discipline=r.discipline,
        )
        for r in retainers.rows(db, character)
    ]


def identities_of(db: Session, character: Character) -> list[BackupAlternateIdentity]:
    return [
        BackupAlternateIdentity(name=r.name, accepted_by=r.accepted_by)
        for r in db.scalars(
            select(AlternateIdentity)
            .where(AlternateIdentity.character_id == character.id)
            .order_by(AlternateIdentity.name)
        )
    ]


def titles_of(db: Session, character: Character) -> list[BackupTitle]:
    return [
        BackupTitle(troupe=troupe, name=title.name, active=title.active)
        for title, troupe in db.execute(
            select(CharacterTitle, Troupe.name)
            .join(Troupe, Troupe.id == CharacterTitle.troupe_id)
            .where(CharacterTitle.character_id == character.id)
            .order_by(Troupe.name, CharacterTitle.name)
        )
    ]


def status_of(db: Session, character: Character) -> list[BackupStatus]:
    """Fleeting and negative status held, with its patron by name only."""
    return [
        BackupStatus(
            name=s.name,
            patron=" ".join(p for p in (s.patron_title, s.patron_name or s.patron_text) if p),
            place=s.place,
            given_on=s.given_on,
            story=s.story,
        )
        for s in db.scalars(
            select(HeldStatus)
            .where(HeldStatus.character_id == character.id)
            .order_by(HeldStatus.given_on, HeldStatus.id)
        )
    ]


def export(
    db: Session,
    character: Character,
    sections: Iterable[Section] = (),
    *,
    root: Path | None = None,
    picture_file: str | None = None,
    player: BackupPlayer | None = None,
) -> CharacterDocument:
    """The character as a document, with the optional `sections` chosen. Its picture is
    in it, or with `picture_file`, named as that file beside it."""
    chosen: list[Section] = [s for s in SECTIONS if s in set(sections)]
    troupe_id = character.owner_troupe_id or character.home_troupe_id
    troupe = db.get(Troupe, troupe_id) if troupe_id else None
    domitor = domitors.domitor_info(db, character) if domitors.has_domitor(character) else None
    return CharacterDocument(
        horatio=horatio_version(),
        rule_set=db.scalar(select(RuleSet.version).where(RuleSet.splat == character.splat)),
        troupe=troupe.name if troupe else "",
        exported_on=date.today(),
        sections=chosen,
        player=player,
        character=BackupIdentity(
            name=character.name,
            splat=character.splat,
            kind=cast(Any, character.kind),
            npc_kind=character.npc_kind,
            npc_form=cast(Any, character.npc_form),
            npc_custom_kind=character.npc_custom_kind,
            pronouns=character.pronouns,
            retired=character.status == "retired",
            left_reason=cast(Any, character.left_reason),
            domitor=domitor.name if domitor else "",
            primary_paths=character.primary_paths,
            card_text=character.card_text,
            card_flavour=character.card_flavour,
            fits_picks=character.fits_picks,
            on_whos_who=character.on_whos_who,
        ),
        stock=stock_of(db, character),
        picture=picture_of(character, root, embed=picture_file is None, file=picture_file),
        traits=traits_of(db, character),
        xp=xp_of(db, character),
        backstory=backstory_text(db, character),
        equipment=equipment_of(db, character) if "equipment" in chosen else [],
        retainers=retainers_of(db, character) if "retainers" in chosen else [],
        identities=identities_of(db, character) if "retainers" in chosen else [],
        titles=titles_of(db, character) if "titles" in chosen else [],
        status=status_of(db, character) if "titles" in chosen else [],
    )


# --- the XP in a document -----------------------------------------------------------------


@dataclass(frozen=True)
class XpFigures:
    """What the file's history comes to, and what its sheet costs here."""

    earned: int
    spent: int
    lost: int
    # XP paid for the traits on its sheet where it came from, and what they cost at the
    # prices it will play by here; and the traits those prices don't cover.
    sheet_there: int
    sheet_here: int
    unpriced: list[str] = field(default_factory=list[str])

    @property
    def unspent(self) -> int:
        return self.earned - self.spent - self.lost


def kinds_corrected(lines: Sequence[BackupXpLine]) -> list[str | None]:
    """The kind of the line each line corrects, or None."""
    return [
        lines[line.corrects].kind
        if line.corrects is not None and line.corrects < len(lines)
        else None
        for line in lines
    ]


def history_totals(lines: Sequence[BackupXpLine]) -> tuple[int, int, int]:
    """Earned, spent and lost, as horatio.sheets.earned_and_spent counts them."""
    return earned_and_spent(
        (line.kind, line.amount, corrected)
        for line, corrected in zip(lines, kinds_corrected(lines), strict=True)
    )


def earned_lines(lines: Sequence[BackupXpLine]) -> list[tuple[BackupXpLine, int]]:
    """Each line of XP earned, with what it gives after the corrections to it."""
    corrected = kinds_corrected(lines)
    gives: dict[int, int] = {}
    for n, line in enumerate(lines):
        if line.kind in EARNED_KINDS and line.kind != "correction":
            gives[n] = gives.get(n, 0) + line.amount
        elif line.kind == "correction" and corrected[n] not in ("purchase", "creation"):
            target = line.corrects if line.corrects is not None else n
            gives[target] = gives.get(target, 0) + line.amount
    return [(lines[n], amount) for n, amount in sorted(gives.items())]


# --- importing ---------------------------------------------------------------------------

Status = Literal["new", "differs", "cannot", "info"]
Part = Literal["character", "sheet", "xp", "retainers", "equipment", "titles", "status"]
PARTS: dict[Part, str] = {
    "character": "Character",
    "sheet": "Sheet",
    "xp": "XP",
    "retainers": "Retainers and Alternate Identities",
    "equipment": "Equipment",
    "titles": "Titles",
    "status": "Status",
}


@dataclass(frozen=True)
class Reviewed:
    part: Part
    label: str
    status: Status
    reason: str | None = None
    before: str | None = None
    after: str | None = None


@dataclass
class Imported:
    """What importing a document did, or would do."""

    character: Character
    items: list[Reviewed] = field(default_factory=list[Reviewed])
    xp: XpFigures | None = None
    # The XP it comes in with as self-entered, for its home troupe to keep or remove.
    self_entered: int = 0
    warnings: list[str] = field(default_factory=list[str])
    # Picture files written, to be removed again if the import doesn't go through.
    written: list[Path] = field(default_factory=list[Path])


def detail_of(error: HTTPException) -> str:
    return str(error.detail)


@contextmanager
def tried(db: Session, found: Imported, part: Part, label: str) -> Iterator[None]:
    """Try one part in a savepoint: a refusal leaves it out, saying why."""
    savepoint = db.begin_nested()
    try:
        yield
    except HTTPException as error:
        if error.status_code >= 500:
            raise
        savepoint.rollback()
        found.items.append(Reviewed(part, label, "cannot", reason=detail_of(error)))
        return
    except (ValueError, LookupError, IntegrityError) as error:
        savepoint.rollback()
        found.items.append(Reviewed(part, label, "cannot", reason=f"It can't be held: {error}"))
        return
    savepoint.commit()


def playable_refusal(document: CharacterDocument) -> str | None:
    """Why a player can't import this as their character, or None."""
    who = document.character
    if who.kind == "npc" and (who.npc_form != "sheeted" or who.npc_kind not in PLAYABLE_KINDS):
        return (
            f"{who.name} is an NPC that isn't a sheeted vampire or ghoul, so it can't be a"
            " player's character."
        )
    return None


def categories_of(db: Session, splat: str) -> dict[str, TraitCategory]:
    return {
        c.key: c
        for c in db.scalars(
            select(TraitCategory)
            .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
            .where(RuleSet.splat == splat)
        )
    }


def ordered(
    categories: Mapping[str, TraitCategory], traits: Sequence[BackupTrait]
) -> list[BackupTrait]:
    """Unrated choices first, those another needs (a sect, for a faction) before it."""

    def rank(item: BackupTrait) -> tuple[int, int]:
        category = categories.get(item.category)
        if category is None:
            return (3, 0)
        if not category.rated:
            return (0 if category.requires is None else 1, category.position)
        return (2, 0)

    return sorted(traits, key=rank)


def put(db: Session, character: Character, item: BackupTrait, troupe_name: str) -> None:
    """One trait on the new sheet, as the file has it: its free dots and picks too."""
    try:
        definition, category = find_definition(db, character, item.category, item.name)
    except HTTPException as error:
        if item.house:
            where = f"of {troupe_name}" if troupe_name else "of the troupe it came from"
            raise unprocessable(
                f"A house {'flaw' if item.category == 'flaws' else 'merit'} {where}: the"
                " troupe it's built for here has none by that name."
            ) from error
        raise
    if not category.rated:
        trait = replace_choice(db, character, definition, category, item.detail)
        trait.note = item.note
        db.flush()
        return
    refused = house_refusal(
        rules_for(db, character), category.key, definition.name, staff=character.kind == "npc"
    )
    if refused is not None:
        raise unprocessable(refused)
    if category.max_rating is not None and (item.rating or 0) > category.max_rating:
        raise unprocessable(f"{category.name} go no higher than {category.max_rating}.")
    held = {(r.definition.id, r.trait.detail) for r in sheet_rows(db, character)}
    if (definition.id, item.detail) in held:
        raise unprocessable(f"{item.label()} is in the file twice.")
    db.add(
        CharacterTrait(
            character_id=character.id,
            trait_definition_id=definition.id,
            detail=item.detail,
            rating=item.rating,
            free_rating=item.free_rating,
            granted_rating=item.granted_rating,
            creation_pick=item.creation_pick,
            # How a pick or a grant's place came to be is kept on an NPC whose picks
            # are fitted alone (horatio.npc_picks).
            pick_by=item.pick_by if character.fits_picks else None,
            grant_place=item.grant_place if character.fits_picks else None,
            place_grant=item.place_grant if character.fits_picks else None,
            place_by=item.place_by if character.fits_picks else None,
            note=item.note,
            choices=item.choices,
            power_choices=item.power_choices,
        )
    )
    db.flush()


def dots_text(rating: int | None, free: int) -> str:
    if rating is None:
        return "held"
    return f"{rating} ({free} free)" if free else str(rating)


def compare_sheet(db: Session, character: Character, document: CharacterDocument) -> list[Reviewed]:
    """The sheet as it came in against the file: each trait new, held otherwise than
    the file has it here (a merit at this troupe's value), or added by the rules."""
    rows = {r.key: r for r in sheet_rows(db, character)}
    found: list[Reviewed] = []
    in_file: set[tuple[str, str, str]] = set()
    for item in document.traits:
        in_file.add(item.key())
        row = rows.get(item.key())
        if row is None:
            continue
        before = dots_text(item.rating, item.free_rating)
        after = dots_text(row.trait.rating, row.trait.free_rating)
        label = f"{row.category.name}: {item.label()}"
        if before != after:
            found.append(Reviewed("sheet", label, "differs", before=before, after=after))
        else:
            found.append(Reviewed("sheet", label, "new", after=after))
    for key, row in rows.items():
        if key not in in_file:
            label = f"{row.category.name}: {row.definition.name}"
            found.append(
                Reviewed(
                    "sheet",
                    label,
                    "new",
                    reason="Added by the rules here.",
                    after=dots_text(row.trait.rating, row.trait.free_rating),
                )
            )
    return found


def priced_here(db: Session, character: Character) -> tuple[int, list[str]]:
    """What the sheet's paid dots cost at the prices it plays by, and the traits
    those prices don't cover."""
    rules = rules_for(db, character)
    rows = sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
    total = 0
    unpriced: list[str] = []
    for row in rows:
        if not row.category.rated or not row.trait.rating:
            continue
        try:
            total += trait_cost(rules, sheet, row.as_rules_trait()).cost
        except PricingError:
            unpriced.append(row.definition.name)
    return total, unpriced


def imported_from(where: str, reason: str) -> str:
    return f"Imported from {where}: {reason}" if reason else f"Imported from {where}"


def write_xp(
    db: Session,
    user: User,
    character: Character,
    document: CharacterDocument,
    imported: set[tuple[str, str, str]],
) -> int:
    """The file's XP history as this character's: each line earned there as
    self-entered XP, dated as it was; each trait on the sheet bought for what was
    paid for it there; fees, debt and lost XP as they were; and the rest of what was
    spent (corrections, traits no longer held, merits and flaws taken in creation) as
    one line. XP paid for a trait that couldn't come in stays unspent. The
    self-entered XP it comes to."""
    where = document.troupe or "a file"
    lines = document.xp
    self_entered = 0
    for line, gives in earned_lines(lines):
        if not gives:
            continue
        self_entered += gives
        db.add(
            XpEntry(
                character_id=character.id,
                kind="self_entered",
                amount=gives,
                reason=imported_from(where, line.reason),
                entered_on=line.on,
                entered_by=user.id,
            )
        )
    for line in lines:
        if line.kind in ("fee", "debt", "lost"):
            db.add(
                XpEntry(
                    character_id=character.id,
                    kind=line.kind,
                    amount=line.amount,
                    reason=imported_from(where, line.reason),
                    entered_on=line.on,
                    entered_by=user.id,
                )
            )
    rows = {r.key: r for r in sheet_rows(db, character)}
    for item in document.traits:
        row = rows.get(item.key())
        if row is None or item.key() not in imported or not item.paid:
            continue
        db.add(
            XpEntry(
                character_id=character.id,
                kind="purchase",
                amount=-item.paid,
                reason=f"{item.label()} {row.trait.free_rating} → {row.trait.rating},"
                f" as paid in {where}",
                entered_by=user.id,
                trait_definition_id=row.definition.id,
                detail=row.trait.detail or None,
                from_rating=row.trait.free_rating,
                to_rating=row.trait.rating or 0,
                cost_basis={"imported": where},
            )
        )
    _, spent, _ = history_totals(lines)
    fees = -sum(line.amount for line in lines if line.kind in ("fee", "debt"))
    rest = spent - fees - sum(i.paid for i in document.traits)
    if rest:
        db.add(
            XpEntry(
                character_id=character.id,
                kind="fee",
                amount=-rest,
                reason=imported_from(
                    where,
                    "the rest of the XP spent there, on traits no longer held and corrections",
                ),
                entered_by=user.id,
            )
        )
    db.flush()
    return self_entered


def picture_bytes(document: CharacterDocument, files: Mapping[str, bytes]) -> bytes | None:
    found = document.picture
    if found is None:
        return None
    if found.data is not None:
        try:
            return base64.b64decode(found.data, validate=True)
        except (binascii.Error, ValueError) as error:
            raise unprocessable("Its picture can't be read.") from error
    if found.file is not None:
        if found.file not in files:
            raise unprocessable(f"Its picture, {found.file}, isn't with the file.")
        return files[found.file]
    return None


def attach_picture(
    found: Imported,
    document: CharacterDocument,
    root: Path | None,
    files: Mapping[str, bytes],
    *,
    write: bool,
) -> None:
    """The file's picture as the character's, cropped as it was."""
    try:
        data = picture_bytes(document, files)
    except HTTPException as error:
        found.items.append(Reviewed("character", "Picture", "cannot", reason=detail_of(error)))
        return
    if data is None:
        return
    try:
        image: Image.Image = pictures.read_image(data)
    except pictures.PictureError as error:
        found.items.append(Reviewed("character", "Picture", "cannot", reason=str(error)))
        return
    if root is None:
        found.items.append(
            Reviewed("character", "Picture", "cannot", reason="Pictures are not set up here.")
        )
        return
    found.items.append(Reviewed("character", "Picture", "new"))
    if not write:
        return
    crop = document.picture.crop if document.picture else None
    character = found.character
    new = uuid.uuid4()
    directory = pictures.picture_dir(root, character.id, new)
    found.written.append(directory)
    chosen = pictures.Crop(crop.x, crop.y, crop.size) if crop else None
    pictures.write_picture(directory, image, chosen)
    box = pictures.square_box(image.width, image.height, chosen)
    character.picture_id = new
    character.picture_crop = {
        "x": box[0] / image.width,
        "y": box[1] / image.height,
        "size": (box[2] - box[0]) / image.width,
    }
    character.picture_by = found.character.player_id
    character.picture_at = datetime.now(UTC)


def import_retainers(db: Session, user: User, found: Imported, document: CharacterDocument) -> None:
    """The Retainers, through the same save as their list on the sheet, all or none."""
    if not document.retainers:
        return
    label = ", ".join(r.name for r in document.retainers)
    drafts = [
        retainers.Draft(
            id=None,
            name=r.name,
            dots=r.dots,
            description=r.description,
            from_merit=r.from_merit,
            lost=r.lost,
            lost_on=r.lost_on,
            npc_id=None,
            ghoul=r.ghoul,
            specialties=list(r.specialties),
            discipline=r.discipline,
        )
        for r in document.retainers
    ]
    with tried(db, found, "retainers", label):
        retainers.replace(db, user, found.character, drafts, link=False)
        found.items.append(Reviewed("retainers", label, "new"))


def shown_only(found: Imported, document: CharacterDocument, *, staff: bool = False) -> None:
    """What a home troupe's storytellers give, shown and never imported. For `staff`
    importing their troupe's own, it says where to give it."""
    given = (
        "Give it from the troupe's equipment."
        if staff
        else "Its home troupe's storytellers give equipment: ask them for it."
    )
    for item in document.equipment:
        found.items.append(Reviewed("equipment", item.name, "info", reason=given))
    for identity in document.identities:
        if identity.accepted_by:
            found.items.append(
                Reviewed(
                    "retainers",
                    f"Alternate Identity: {identity.name}",
                    "info",
                    reason=f"Accepted by {identity.accepted_by} where it came from; its home"
                    " troupe's storytellers record that here.",
                )
            )
    for title in document.titles:
        found.items.append(
            Reviewed(
                "titles",
                f"{title.name} ({title.troupe})",
                "info",
                reason="A title means nothing outside its troupe: choose one in the troupe.",
            )
        )
    for held in document.status:
        found.items.append(
            Reviewed(
                "status",
                held.name,
                "info",
                reason="Shown only: status is given in play.",
            )
        )


def splat_of(splat: str) -> Any:
    found = SPLATS.get(splat)
    if found is None:
        raise unprocessable(f"This Horatio has no rules for {splat!r} characters.")
    return found


def whence(document: CharacterDocument) -> str:
    """Where and when the file was made: "exported from Night Court on 2026-11-09"."""
    found = f"exported from {document.troupe}" if document.troupe else "exported outside any troupe"
    return found + (f" on {document.exported_on}" if document.exported_on else "")


def import_character(
    db: Session,
    user: User,
    document: CharacterDocument,
    troupe: Troupe | None,
    *,
    root: Path | None,
    files: Mapping[str, bytes] | None = None,
    write_pictures: bool = True,
) -> Imported:
    """A new character of `user`'s from the document, in their vault and built for
    `troupe` (or the plain rule set), its creation finished. Callers commit, or roll
    back for a review."""
    refused = playable_refusal(document)
    if refused is not None:
        raise unprocessable(refused)
    who = document.character
    if db.scalar(select(RuleSet.id).where(RuleSet.splat == who.splat)) is None:
        raise unprocessable(f"This Horatio has no rules for {who.splat!r} characters.")
    character = Character(
        player_id=user.id,
        splat=who.splat,
        name=who.name,
        building_troupe_id=troupe.id if troupe else None,
        pronouns=who.pronouns,
        primary_paths=dict(who.primary_paths),
        domitor_name=who.domitor if splat_of(who.splat).has_domitor else "",
        card_text=who.card_text,
        card_flavour=who.card_flavour,
        creation_completed_at=datetime.now(UTC),
        # What its merits and flaws cost or gave in creation comes in with the rest
        # of what it spent there, not as creation lines (horatio.creation_xp).
        merits_flaws_xp=False,
    )
    db.add(character)
    db.flush()
    found = Imported(character)
    found.items.append(Reviewed("character", who.name, "new", after=splat_of(who.splat).label))

    imported: set[tuple[str, str, str]] = set()
    categories = categories_of(db, who.splat)
    for item in ordered(categories, document.traits):
        known = categories.get(item.category)
        label = f"{known.name if known else item.category}: {item.label()}"
        before = len(found.items)
        with tried(db, found, "sheet", label):
            put(db, character, item, document.troupe)
        if len(found.items) == before:
            imported.add(item.key())
    # A merit or flaw is held at its value under the rules it plays by here.
    sync_fixed_ratings(db, character)
    cannot = [i for i in found.items if i.status == "cannot"]
    found.items = [*found.items[:1], *compare_sheet(db, character, document), *cannot]

    found.self_entered = write_xp(db, user, character, document, imported)
    earned, spent, lost = history_totals(document.xp)
    here, unpriced = priced_here(db, character)
    found.xp = XpFigures(
        earned=earned,
        spent=spent,
        lost=lost,
        sheet_there=sum(i.paid for i in document.traits),
        sheet_here=here,
        unpriced=unpriced,
    )
    if document.xp:
        found.items.append(
            Reviewed(
                "xp",
                f"{len(document.xp)} lines of XP history",
                "new",
                reason="XP earned there comes in as self-entered: the troupe that accepts"
                " the character keeps or removes it.",
            )
        )

    if document.backstory.strip():
        with tried(db, found, "character", "Backstory"):
            backstories.save(db, user, character, document.backstory, 0)
            found.items.append(Reviewed("character", "Backstory", "new"))
    import_retainers(db, user, found, document)
    attach_picture(found, document, root, files or {}, write=write_pictures)
    shown_only(found, document)
    if who.retired:
        found.warnings.append(
            f"{who.name} was retired where it came from; it comes in as a character you play."
        )
    db.flush()
    audit.record(
        db,
        user,
        "character.imported",
        character_id=character.id,
        source=document.troupe,
        whence=whence(document),
        left_out=sum(1 for i in found.items if i.status == "cannot"),
    )
    return found


def review(
    db: Session,
    user: User,
    document: CharacterDocument,
    troupe: Troupe | None,
    *,
    root: Path | None,
) -> Imported:
    """What importing would do, with nothing saved."""
    savepoint = db.begin_nested()
    try:
        found = import_character(db, user, document, troupe, root=root, write_pictures=False)
    finally:
        savepoint.rollback()
    return found

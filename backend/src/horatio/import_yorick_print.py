"""Import a troupe's characters from Yorick's Print Characters page as sheeted NPCs
of the troupe (#482), for staff to give each to its player as they sign up (#481).
The custodian runs it in the app (horatio.yorick_imports, #518): this is the import
itself, and its report.

Each printed character (horatio.yorick_print) is matched to Horatio's names
(horatio.yorick_names, with the table in yorick_names.toml and the troupe's own over
it) and made a sheeted NPC of the troupe, its traits set straight from the printout
as staff set an NPC's. Rule checks do not stop it: what the sheet breaks is flagged
on it as on any sheet, and listed in the report. Its portrait is attached, where the
list shows one. It keeps its Yorick id as its `legacy_id` (or, with none, a stable
hash of its printed name), and the log says it was imported.

**Importing it again** updates the characters it made before, matched on
`legacy_id`, rather than making them twice: their name and every trait the printout
gives are set again. Nothing else is taken off, so what staff added by hand stays, and
a picture staff changed is kept. A character given to its player since is left alone.

**A character here under a printed name** (the troupe's NPCs and its players'
characters, ignoring case and spacing), not linked to it by its Yorick id, is
reported, and the printed character waits for the custodian's choice (`decisions`,
by Yorick id): `overwrite` that one, which must be a sheeted NPC of the troupe, as
an import again would; `skip` it; or import it as a `new` NPC beside it. Until then
it is not imported.

The whole import is one transaction; a dry run is rolled back. No XP is written: a
character's XP is set when it is given to its player (#481).
"""

import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import audit, npc_picks, npcs, pictures, sheets
from horatio.models import Character, CharacterTrait, Troupe, TroupeMembership, User
from horatio.rules.pricing import fixed_rating
from horatio.rules.store import read_troupe_rules
from horatio.specializations import troupe_options
from horatio.yorick_names import Catalogue, Mapped, Mapper, Trait, catalogue_of
from horatio.yorick_print import PrintedCharacter

SPLAT = "vampire"
# Unrated choices first: a faction needs its sect, a merit's value can depend on the
# clan. Then the rest as printed.
FIRST = ("clan", "sect", "faction", "archetype")


# --- one character ------------------------------------------------------------------------


CHOICES = ("overwrite", "skip", "new")


@dataclass
class Match:
    """A character here under a printed character's name."""

    character_id: str
    name: str
    # "an NPC of the troupe", "@jane's character"
    whose: str
    # Only a sheeted NPC of the troupe can be overwritten: a player's sheet changes
    # through the troupe's approvals, and a Stock NPC has no sheet.
    overwritable: bool
    # Its own Yorick id, where it was imported from another printed character.
    legacy_id: str | None = None


def same_name(name: str) -> str:
    return " ".join(name.split()).casefold()


@dataclass
class Result:
    """What became of one printed character."""

    printed: PrintedCharacter
    mapped: Mapped
    # made | updated | overwritten | skipped | undecided | failed
    outcome: str = "made"
    # Why it was skipped, or what went wrong.
    skipped_because: str = ""
    character_id: str | None = None
    # Traits matched but refused on the sheet, with why ("Only a Sabbat character has
    # a Faction.").
    refused: list[tuple[str, str]] = field(default_factory=list)
    # Merits and flaws printed at another value than Horatio holds them at here.
    revalued: list[tuple[str, int, int]] = field(default_factory=list)
    # The checks the sheet breaks, as their messages.
    problems: list[str] = field(default_factory=list)
    xp: int = 0
    # Traits the troupe's rules give no price for, with why.
    unpriced: list[tuple[str, str]] = field(default_factory=list)
    portrait: str = "none"
    # Characters here under its name, not linked to it by its Yorick id.
    matches: list[Match] = field(default_factory=list)
    # What the custodian chose for it, if they have.
    choice: str | None = None

    @property
    def clean(self) -> bool:
        return not (self.mapped.unmatched or self.refused)


def catalogue_for(db: Session, troupe: Troupe) -> Catalogue:
    rules = read_troupe_rules(db, SPLAT, troupe.id)
    return catalogue_of(rules.rule_set, troupe_options(db, troupe.id))


def put(db: Session, npc: Character, trait: Trait) -> None:
    """Set one trait on the NPC as the printout has it, as staff set an NPC's rating
    directly (horatio.npcs.set_rating), but keeping what the printout holds that a
    usual sheet would not, such as two focuses for one attribute: the sheet's checks
    flag it instead."""
    definition, category = sheets.find_definition(db, npc, trait.category, trait.name)
    if not category.rated:
        sheets.replace_choice(db, npc, definition, category, trait.detail)
        db.flush()
        return
    rows = sheets.sheet_rows(db, npc)
    if category.key == "paths":
        # One Morality: the printed one takes Humanity's place.
        for row in rows:
            other = row.category.key == "paths" and row.definition.id != definition.id
            if other and not row.trait.granted_rating:
                db.delete(row.trait)
    held = next(
        (
            r.trait
            for r in rows
            if r.definition.id == definition.id and r.trait.detail == trait.detail
        ),
        None,
    )
    if held is None:
        held = CharacterTrait(
            character_id=npc.id, trait_definition_id=definition.id, detail=trait.detail
        )
        db.add(held)
    rating = trait.rating
    if rating is None:
        # Printed with no rating: a ritual is held at its level, a technique at 1.
        rating = sheets.held_at(db, npc, category.key, definition.name) or 1
    npc_picks.set_straight(held, rating)
    held.note = trait.note
    db.flush()


def hold_fixed_values(db: Session, npc: Character, result: Result) -> None:
    """Merits and flaws are held at their value here (a troupe's price for one is its
    value): one printed at another is held at Horatio's, and listed."""
    rules = sheets.rules_for(db, npc)
    rows = sheets.sheet_rows(db, npc)
    sheet = [r.as_rules_trait() for r in rows]
    for row in rows:
        value = fixed_rating(rules, sheet, row.category.key, row.definition.name)
        if value is None or not row.trait.rating or row.trait.rating == value:
            continue
        result.revalued.append((row.definition.name, row.trait.rating, value))
        npc_picks.set_straight(row.trait, value)
    db.flush()


def name_primary_paths(db: Session, npc: Character) -> None:
    """Yorick prints no primary path. Where the clan's own path (if any) is not the
    highest the character holds of a discipline, its highest is named primary: no
    other path can go above the primary (MET: VTM p. 187). A tie at the top is left
    for staff."""
    ratings = {r.definition.name: r.trait.rating or 0 for r in sheets.sheet_rows(db, npc)}
    named = dict(npc.primary_paths)
    for primary in sheets.primary_paths(db, npc):
        top = primary.options[0]
        tied = [p for p in primary.options if ratings[p] == ratings[top]]
        current = ratings.get(primary.path or "", 0)
        if len(tied) == 1 and ratings[top] > current and top != primary.default:
            named[primary.discipline] = top
    if named != npc.primary_paths:
        npc.primary_paths = named
        db.flush()


def order(traits: Sequence[Trait]) -> list[Trait]:
    first = {category: n for n, category in enumerate(FIRST)}
    return sorted(traits, key=lambda t: first.get(t.category, len(FIRST)))


class Importer:
    def __init__(
        self,
        db: Session,
        troupe: Troupe,
        staff: User,
        mapper: Mapper,
        page_dir: Path,
        *,
        pictures_root: Path | None,
        dry_run: bool = False,
        decisions: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self.db = db
        self.troupe = troupe
        self.staff = staff
        self.mapper = mapper
        self.page_dir = page_dir
        self.pictures_root = pictures_root
        self.dry_run = dry_run
        self.decisions = decisions or {}
        # Characters here, by their name as compared, from before the import.
        self.here: dict[str, list[Match]] = {}
        # Those overwritten in this import: each by one printed character only.
        self.overwritten: set[uuid.UUID] = set()
        # Picture folders written, removed again if the import does not go through.
        self.written: list[Path] = []

    def existing(self, ids: Sequence[str]) -> dict[str, Character]:
        found = self.db.scalars(select(Character).where(Character.legacy_id.in_(ids)))
        return {c.legacy_id: c for c in found if c.legacy_id is not None}

    def characters_here(self) -> dict[str, list[Match]]:
        """The troupe's characters still active, by name: its NPCs, those at home in
        it, those built for it, and those visiting it."""
        visiting = select(TroupeMembership.character_id).where(
            TroupeMembership.troupe_id == self.troupe.id, TroupeMembership.left_at.is_(None)
        )
        rows = self.db.execute(
            select(Character, User.handle)
            .join(User, User.id == Character.player_id)
            .where(
                Character.status == "active",
                or_(
                    Character.owner_troupe_id == self.troupe.id,
                    Character.home_troupe_id == self.troupe.id,
                    Character.building_troupe_id == self.troupe.id,
                    Character.id.in_(visiting),
                ),
            )
            .order_by(Character.name, Character.id)
        )
        found: dict[str, list[Match]] = defaultdict(list)
        for character, handle in rows:
            npc = character.kind == "npc"
            if npc and character.owner_troupe_id != self.troupe.id:
                continue
            sheeted = npc and character.npc_form == "sheeted" and character.splat == SPLAT
            if not npc:
                whose = f"@{handle}'s character"
            elif character.npc_form == "stock":
                whose = "a Stock NPC of the troupe"
            else:
                whose = "an NPC of the troupe"
            found[same_name(character.name)].append(
                Match(str(character.id), character.name, whose, sheeted, character.legacy_id)
            )
        return found

    def run(
        self,
        printed: Sequence[PrintedCharacter],
        progress: Callable[[int, int], None] | None = None,
    ) -> list[Result]:
        before = self.existing([p.legacy_id for p in printed])
        self.here = self.characters_here()
        results: list[Result] = []
        for done, character in enumerate(printed):
            if progress is not None:
                progress(done, len(printed))
            savepoint = self.db.begin_nested()
            try:
                results.append(self.one(character, before.get(character.legacy_id)))
            except Exception as error:
                # Kept going, so a dry run reports every character; a real run with
                # one that failed saves nothing.
                savepoint.rollback()
                failed = Result(character, self.mapper.character(character), "failed")
                failed.skipped_because = f"{type(error).__name__}: {error}"
                results.append(failed)
                continue
            savepoint.commit()
        if progress is not None:
            progress(len(printed), len(printed))
        return results

    def choose(self, printed: PrintedCharacter, result: Result) -> Character | None:
        """For a printed character with no NPC of its own yet: the character to
        overwrite, if the custodian chose one, or None. Sets the outcome where it is
        not to be imported."""
        result.matches = [
            m
            for m in self.here.get(same_name(printed.name), [])
            if m.legacy_id != printed.legacy_id
        ]
        if not result.matches:
            return None
        decision = self.decisions.get(printed.legacy_id) or {}
        choice = decision.get("choice")
        target = next(
            (m for m in result.matches if m.character_id == decision.get("character_id")), None
        )
        if choice == "overwrite" and (
            target is None
            or not target.overwritable
            or uuid.UUID(target.character_id) in self.overwritten
        ):
            # The character chosen has gone, can no longer be overwritten, or another
            # printed character has overwritten it already.
            choice = None
        result.choice = choice
        if choice == "skip":
            result.outcome = "skipped"
            result.skipped_because = "you chose to skip it, as a character here has its name"
        elif choice is None or choice not in CHOICES:
            result.outcome = "undecided"
            result.skipped_because = (
                "a character here has its name: choose to overwrite it, skip it, or import it"
                " as a new NPC"
            )
        elif choice == "overwrite" and target is not None:
            return self.db.get_one(Character, uuid.UUID(target.character_id))
        return None

    def one(self, printed: PrintedCharacter, npc: Character | None) -> Result:
        result = Result(printed, self.mapper.character(printed))
        if npc is None:
            npc = self.choose(printed, result)
            if result.outcome in ("skipped", "undecided"):
                return result
            if npc is not None:
                result.outcome = "overwritten"
                self.overwritten.add(npc.id)
                npc.legacy_id = printed.legacy_id
                npc.name = printed.name
        elif npc.kind != "npc" or npc.owner_troupe_id != self.troupe.id:
            result.outcome = "skipped"
            result.skipped_because = (
                "it has been given to its player"
                if npc.kind != "npc"
                else "an NPC of another troupe has its Yorick id"
            )
            result.character_id = str(npc.id)
            return result
        else:
            result.outcome = "updated"
            npc.name = printed.name
        if npc is None:
            npc = npcs.create_npc(
                self.db, self.staff, self.troupe, SPLAT, printed.name, wizard=False
            )
            npc.legacy_id = printed.legacy_id
        # Yorick doesn't print which dots were creation picks: they are fitted to the
        # sheet once it is in, around any staff placed by hand (#527).
        npc.fits_picks = True
        self.db.flush()
        npc_picks.unfit(self.db, npc)
        result.character_id = str(npc.id)

        converts_before = sheets.sheet_effects(self.db, npc).converts
        for trait in order(result.mapped.traits):
            savepoint = self.db.begin_nested()
            try:
                put(self.db, npc, trait)
            except HTTPException as error:
                savepoint.rollback()
                result.refused.append((trait.source, str(error.detail)))
                continue
            savepoint.commit()
        hold_fixed_values(self.db, npc, result)
        name_primary_paths(self.db, npc)
        # What the sheet's merits and flaws give (Rugged's health levels), as when
        # staff set an NPC's ratings (horatio.sheets.checked).
        sheets.apply_grants(self.db, self.staff, npc, converts_before)
        npc_picks.fit(self.db, npc)

        result.problems = list(
            dict.fromkeys(v.message for v in sheets.sheet_violations(self.db, npc))
        )
        result.xp, lines = npcs.tally(self.db, npc)
        result.unpriced = [(line.name, line.note) for line in lines if line.cost is None]
        result.portrait = self.portrait(printed, npc)
        audit.record(
            self.db,
            self.staff,
            {"made": "npc.imported", "overwritten": "npc.imported_over"}.get(
                result.outcome, "npc.reimported"
            ),
            troupe_id=self.troupe.id,
            character_id=npc.id,
            legacy_id=printed.legacy_id,
            label=printed.label or "none",
            unmatched=len(result.mapped.unmatched) + len(result.refused),
        )
        return result

    def portrait(self, printed: PrintedCharacter, npc: Character) -> str:
        """Attach the printed character's portrait, unless the NPC has a picture."""
        if printed.portrait is None:
            return "none"
        if npc.picture_id is not None:
            return "kept the one it has"
        path = self.page_dir / printed.portrait
        try:
            image = pictures.read_image(path.read_bytes())
        except (OSError, pictures.PictureError) as error:
            return f"not attached: {error}"
        if self.dry_run:
            return "to be attached"
        if self.pictures_root is None:
            return "not attached: pictures are not set up here (HORATIO_UPLOAD_DIR)"
        new = uuid.uuid4()
        directory = pictures.picture_dir(self.pictures_root, npc.id, new)
        self.written.append(directory)
        pictures.write_picture(directory, image, None)
        box = pictures.square_box(image.width, image.height, None)
        npc.picture_id = new
        npc.picture_crop = {
            "x": box[0] / image.width,
            "y": box[1] / image.height,
            "size": (box[2] - box[0]) / image.width,
        }
        npc.picture_by = self.staff.id
        npc.picture_at = datetime.now(UTC)
        self.db.flush()
        return "attached"

    def undo_pictures(self) -> None:
        for directory in self.written:
            pictures.remove(directory)


# --- the report ---------------------------------------------------------------------------


def plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def summary(
    results: Sequence[Result],
    dry_run: bool,
    left_out: Mapping[str, str] | None = None,
    by_hand: Collection[str] = (),
) -> list[str]:
    """The import as a whole, and every printed line it could not match. `left_out` is
    why the table leaves each heading to staff; `by_hand`, the printed lines ("Merits:
    Arcane (1)") staff will put right by hand, listed apart."""
    outcomes = Counter(r.outcome for r in results)
    unmatched = [u for r in results for u in r.mapped.unmatched if u.source not in by_hand]
    handed = [u for r in results for u in r.mapped.unmatched if u.source in by_hand]
    refused = [(s, why) for r in results for s, why in r.refused]
    lines = [
        f"{plural(len(results), 'character')} read from the page: "
        f"{outcomes['made']} {'to be made' if dry_run else 'made'}, "
        f"{outcomes['updated']} {'to be updated' if dry_run else 'updated'}, "
        f"{outcomes['overwritten']} {'to be overwritten' if dry_run else 'overwritten'}, "
        f"{outcomes['skipped']} skipped, {outcomes['undecided']} waiting for a choice, "
        f"{outcomes['failed']} failed.",
        f"{sum(r.clean for r in results)} import cleanly; "
        f"{plural(len(unmatched), 'printed line')} matched nothing "
        f"({len({(u.heading, u.text) for u in unmatched})} different)"
        + (f", {len(handed)} more left for staff to put right by hand" if handed else "")
        + f", and {plural(len(refused), 'trait')} could not be put on a sheet.",
        f"{sum(bool(r.problems) for r in results)} sheets break a rule check "
        f"({plural(sum(len(r.problems) for r in results), 'check')} in all); "
        f"{sum(bool(r.revalued) for r in results)} hold a merit or flaw at another value.",
        f"{sum(r.portrait in ('attached', 'to be attached') for r in results)} portraits "
        f"{'to be attached' if dry_run else 'attached'}.",
        f"{sum(r.xp for r in results)} XP in all at the troupe's prices "
        f"(none of it written: XP is set when a character is given to its player).",
    ]
    left = Counter(item.split(":")[0] for r in results for item in r.mapped.left_out)
    if left:
        lines += ["", "Left to staff, as printed in each character's report:"]
        for heading, count in sorted(left.items()):
            why = (left_out or {}).get(heading, "")
            lines.append(f"  {heading}: {plural(count, 'line')}" + (f". {why}" if why else ""))
    waiting = [r for r in results if r.outcome == "undecided"]
    if waiting:
        lines += ["", "Waiting for a choice, as a character here has its name:"]
        for r in waiting:
            lines.append(f"  {r.printed.name}: " + "; ".join(m.whose for m in r.matches))
    if handed:
        lines += ["", "Left for staff to put right by hand:"]
        for source, count in sorted(Counter(u.source for u in handed).items()):
            lines.append(f"  {source}" + (f" x{count}" if count > 1 else ""))
    if unmatched or refused:
        lines += ["", "Printed lines that matched nothing, by heading:"]
        grouped: dict[str, Counter[str]] = defaultdict(Counter)
        for u in unmatched:
            grouped[u.heading][f"{u.text} ({u.reason})"] += 1
        for heading in sorted(grouped):
            lines.append(f"  {heading}:")
            for text, count in sorted(grouped[heading].items()):
                lines.append(f"    {text}" + (f" x{count}" if count > 1 else ""))
        if refused:
            lines.append("  Matched, but could not be put on a sheet:")
            for (source, why), count in sorted(Counter(refused).items()):
                lines.append(f"    {source}: {why}" + (f" x{count}" if count > 1 else ""))
    return lines


def character_report(result: Result) -> list[str]:
    printed = result.printed
    head = f"== {printed.name} (Yorick id {printed.legacy_id}"
    head += f"; labelled {printed.label})" if printed.label else ")"
    lines = [head]
    if result.matches:
        lines.append("Here under its name:")
        lines += [f"  {m.name}, {m.whose}" for m in result.matches]
    if result.outcome in ("skipped", "undecided"):
        return [*lines, f"Not imported: {result.skipped_because}."]
    if result.outcome == "failed":
        return [*lines, f"Failed: {result.skipped_because}"]
    mapped = result.mapped
    done = {"made": "Made", "updated": "Updated", "overwritten": "Overwrote the NPC here"}
    lines.append(
        f"{done[result.outcome]}: "
        f"{plural(len(mapped.traits) - len(result.refused), 'trait')} imported"
        + (" cleanly." if result.clean else ".")
    )
    sections: list[tuple[str, list[str]]] = [
        ("Matched nothing", [f"{u.source} ({u.reason})" for u in mapped.unmatched]),
        ("Could not be put on the sheet", [f"{s}: {why}" for s, why in result.refused]),
        (
            "Held at Horatio's value",
            [f"{name}: printed {was}, held at {now}" for name, was, now in result.revalued],
        ),
        ("Read as several", mapped.split),
        ("Rule checks the sheet breaks", result.problems),
        ("No price in this troupe", [f"{name}: {why}" for name, why in result.unpriced]),
        ("Left to staff", mapped.left_out),
    ]
    for title, items in sections:
        if items:
            lines.append(f"{title}:")
            lines += [f"  {item}" for item in items]
    lines.append(f"XP at the troupe's prices: {result.xp}")
    lines.append(f"Portrait: {result.portrait}")
    if printed.extended_text:
        lines.append("Its extended print text is not imported (see characters.json).")
    return lines


def report_text(
    results: Sequence[Result],
    dry_run: bool,
    left_out: Mapping[str, str],
    by_hand: Collection[str] = (),
) -> str:
    """The report: the summary, then each character's."""
    text = summary(results, dry_run, left_out, by_hand)
    for result in results:
        text += ["", *character_report(result)]
    return "\n".join(text) + "\n"


def record_of(result: Result) -> dict[str, Any]:
    """One character as read and as matched, for the report's JSON."""
    r = result
    return {
        "printed": asdict(r.printed),
        "outcome": r.outcome,
        "skipped_because": r.skipped_because,
        "character_id": r.character_id,
        "matches": [asdict(m) for m in r.matches],
        "choice": r.choice,
        "traits": [asdict(t) for t in r.mapped.traits],
        "unmatched": [asdict(u) for u in r.mapped.unmatched],
        "refused": r.refused,
        "revalued": r.revalued,
        "left_out": r.mapped.left_out,
        "split": r.mapped.split,
        "problems": r.problems,
        "xp": r.xp,
        "unpriced": r.unpriced,
        "portrait": r.portrait,
    }

"""Importing a troupe's characters from Yorick's Print Characters page (#482), from a
made-up page in its format (tests/fixtures/yorick_print.html)."""

import json
import shutil
import uuid
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Connection, func, select
from sqlalchemy.orm import Session

from horatio import backups, import_yorick_print, sheets
from horatio.config import get_settings
from horatio.models import AuditEvent, Character, CharacterTrait, User
from horatio.models import Troupe as TroupeRecord
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.specializations import set_troupe_options
from horatio.yorick_names import (
    Catalogue,
    Mapper,
    Table,
    catalogue_of,
    read_table,
    spelling_renames,
)
from horatio.yorick_print import (
    CannotRead,
    Line,
    PrintedCharacter,
    read_file,
    read_line,
    read_page,
)
from tests.api_helpers import Troupe

FIXTURE = Path(__file__).parent / "fixtures" / "yorick_print.html"
PAGE = "Print Troupe Characters.html"
PORTRAIT = "Print Troupe Characters_files/0a1b2c3d4e5f_thumbnail_128_bqmm.jpg"


@pytest.fixture
def page(tmp_path: Path) -> Path:
    """The page saved with its _files folder, as a browser saves it."""
    folder = tmp_path / "saved"
    (folder / PORTRAIT).parent.mkdir(parents=True)
    shutil.copy(FIXTURE, folder / PAGE)
    Image.new("RGB", (128, 128), (120, 20, 30)).save(folder / PORTRAIT, "JPEG")
    return folder / PAGE


@cache
def table() -> Table:
    return read_table(renames=spelling_renames())


@cache
def book_catalogue() -> Catalogue:
    return catalogue_of(load_rule_set(DATA_DIR / "bns_met_vampire.toml"))


def mapper(catalogue: Catalogue | None = None) -> Mapper:
    return Mapper(table(), catalogue or book_catalogue())


def character(name: str) -> PrintedCharacter:
    return next(c for c in read_file(FIXTURE) if c.name == name)


def traits(printed: PrintedCharacter, catalogue: Catalogue | None = None) -> dict[str, str]:
    """Each trait as "category: name [detail] rating (note)", by where it was printed."""
    found: dict[str, str] = {}
    for t in mapper(catalogue).character(printed).traits:
        text = f"{t.category}: {t.name}" + (f" [{t.detail}]" if t.detail else "")
        text += f" {t.rating}" if t.rating is not None else ""
        text += f" ({t.note})" if t.note else ""
        found[t.source] = text
    return found


# --- reading the page ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "points", "read"),
    [
        ("Haven x3", False, Line("Haven x3", "Haven", 3, "")),
        (
            "Influences x4: The Elite",
            False,
            Line("Influences x4: The Elite", "Influences", 4, "The Elite"),
        ),
        (
            "Custom x1: Social Media",
            False,
            Line("Custom x1: Social Media", "Custom", 1, "Social Media"),
        ),
        ("Displacement Aura", False, Line("Displacement Aura", "Displacement Aura")),
        ("Arcane (1)", True, Line("Arcane (1)", "Arcane", 1, "")),
        (
            "Thaumaturgical Expertise (1, Path of Conjuring)",
            True,
            Line("Thaumaturgical Expertise (1, Path of Conjuring)", "Thaumaturgical Expertise", 1,
                 "Path of Conjuring"),
        ),
        (
            "Addiction (Hallucinogen) (2)",
            True,
            Line("Addiction (Hallucinogen) (2)", "Addiction (Hallucinogen)", 2, ""),
        ),
        (
            "Derangement (2, Destruction (when crossed))",
            True,
            Line("Derangement (2, Destruction (when crossed))", "Derangement", 2,
                 "Destruction (when crossed)"),
        ),
    ],
)  # fmt: skip
def test_a_printed_line_is_a_name_a_rating_and_a_detail(
    text: str, points: bool, read: Line
) -> None:
    assert read_line(text, points=points) == read


def test_each_printed_sheet_is_read_with_its_id_and_portrait_from_the_list() -> None:
    agnes, thaddeus, mystery = read_file(FIXTURE)

    assert (agnes.legacy_id, agnes.name, agnes.label) == ("aGnEsWr3n1", "Agnes Wren", "")
    assert agnes.portrait == PORTRAIT
    assert agnes.identity == {
        "Clan": "Tremere",
        "Archetype": "Curious",
        "Antecedence": "Primary",
        "Sect": "Camarilla",
        "Title": "Primogen",
    }
    assert {k: (a.rating, a.focuses) for k, a in agnes.attributes.items()} == {
        "Physical": (3, "Dexterity"),
        "Social": (5, "Charisma"),
        "Mental": (7, "Intelligence Wits: (Versatile)"),
    }
    assert agnes.morality == ("Humanity", 4)
    assert [s.text for s in agnes.skills][:2] == ["Academics x2: Business", "Crafts x1: Painting"]
    assert [line.text for line in agnes.sections["Influences: The Elite"]] == [
        "Custom x1: Social Media",
        "Organized Crime x1",
    ]
    assert agnes.sections["Merits"][0].detail == "The Path of Conjuring"
    assert agnes.extended_text == "Initiative: 9\nKeeps her notes in Latin."

    # The label in brackets is not part of the name; a skull in the list is no portrait.
    assert (thaddeus.legacy_id, thaddeus.name, thaddeus.label) == (
        "Th4ddAshby",
        "Thaddeus Ashby",
        "On Hold",
    )
    assert thaddeus.portrait is None
    # One the list does not show has a stable id of its own.
    assert mystery.legacy_id.startswith("print-")
    assert read_file(FIXTURE)[2].legacy_id == mystery.legacy_id


def test_two_characters_printed_under_one_name_have_ids_of_their_own() -> None:
    twice = FIXTURE.read_text().replace(">[On Hold] Thaddeus Ashby</h1>", ">Agnes Wren</h1>")

    first, second, _ = read_page(twice)

    # The list's one Agnes Wren could be either, so neither takes its id or portrait.
    assert first.legacy_id.startswith("print-") and second.legacy_id.startswith("print-")
    assert first.legacy_id != second.legacy_id
    assert first.portrait is None


def test_a_page_without_printed_sheets_is_refused() -> None:
    with pytest.raises(CannotRead, match="no printed sheets"):
        read_page("<html><body><p>Log in</p></body></html>")


# --- matching names ----------------------------------------------------------------


def test_the_spelling_migrations_are_read_for_old_names() -> None:
    renames = spelling_renames()
    assert ("flaws", "Intolerant", "Intolerance") in renames
    assert ("merits", "Thaumaturgical Expertise", "Thaumaturgic Expertise") in renames
    assert ("elder_disciplines", "Potence: Relentess Fury", "Potence: Relentless Fury") in renames


def test_a_sheet_is_matched_to_horatios_names() -> None:
    found = traits(character("Agnes Wren"))

    assert found["Clan: Tremere"] == "clan: Tremere"
    assert found["Morality: Humanity"] == "paths: Humanity 4"
    # Two focuses, and the merit that gives the second kept as a note.
    assert found["Mental: Intelligence Wits: (Versatile)"] == "focus_mentals: Wits 1 (Versatile)"
    # A skill held once per field keeps it as its detail; another's is a note.
    assert found["Skills: Crafts x1: Painting"] == "skills: Crafts [Painting] 1"
    assert found["Skills: Academics x2: Business"] == "skills: Academics 2 (Business)"
    assert found["Backgrounds: Influences x2: The Elite"] == "backgrounds: Influences: The Elite 2"
    assert (
        found["Backgrounds: Influences x1: The Underworld (Occult)"]
        == "backgrounds: Influences: The Underworld 1 (Occult)"
    )
    assert found["Backgrounds: Retainers x1: Drive"] == "backgrounds: Retainers [Drive] 1"
    assert found["Haven: Security x1: Free From Skill"] == (
        "haven_specializations: Security 1 (Free From Skill)"
    )
    # A path is found however it is written, and so is the path a merit is for.
    assert found["Disciplines: Thaumaturgy x1: The Path of Conjuring"] == (
        "disciplines: Thaumaturgy: Path of Conjuring 1"
    )
    assert found["Merits: Thaumaturgical Expertise (1, The Path of Conjuring)"] == (
        "merits: Thaumaturgic Expertise [Thaumaturgy: Path of Conjuring] 1"
    )
    assert found["Merits: Acute Sense (1, Hearing)"] == "merits: Acute Sense [Hearing] 1"
    # Renamed to match the books (#410), and a ritual held at its level.
    assert found["Rituals: Thaumaturgy: Thaumaturgical Metabolism"] == (
        "rituals: Thaumaturgy: Thaumaturgic Metabolism"
    )
    assert found["Flaws: Intolerant (1, Sabbat)"] == "flaws: Intolerance 1 (Sabbat)"
    assert found["Flaws: Derangement (2, Obsession)"] == "flaws: Derangement [Obsession] 2"
    assert found["Flaws: Tremere (1, Pedantic)"] == "flaws: Tremere: Pedantic 1"
    assert found["Contacts: Custom x1: Old Tom, a fence of curios"] == (
        "contacts_specializations: Custom [Old Tom, a fence of curios] 1"
    )
    assert found["Lores: Custom: Fae"] == "lore_specializations: Custom [Fae] 1"


def test_influence_areas_are_matched_however_yorick_wrote_them() -> None:
    found = traits(character("Agnes Wren"))
    assert found["Influences: The Elite: Custom x1: Social Media"] == (
        "influence_elite_specializations: Social Media 1"
    )
    # An old area's name, and a spelling of the table's.
    assert found["Influences: The Elite: Organized Crime x1"] == (
        "influence_elite_specializations: Criminal Organizations 1"
    )
    assert found["Influences: The Underworld: Custom x1: Science-Medical"] == (
        "influence_underworld_specializations: Science/Medical 1"
    )


def test_what_matches_nothing_is_kept_aside_with_why() -> None:
    mapped = mapper().character(character("Agnes Wren"))

    assert [(u.source, u.reason) for u in mapped.unmatched] == [
        ("Backgrounds: Influences x1", "no such background"),
        ("Influences: The Underworld: Police x1", "no such Influence area: Police"),
        ("Rituals: Thaumaturgy: Whispers of the Moon", "no such ritual"),
    ]
    assert mapped.left_out == [
        "Antecedence: Primary",
        "Title: Primogen",
        "Status: Acknowledged (1)",
    ]
    # One line, two languages.
    assert mapped.split == ["Languages: Custom: French, Korean"]
    languages = [
        (t.name, t.detail) for t in mapped.traits if t.category == "linguistics_specializations"
    ]
    assert languages == [("Latin", ""), ("French", ""), ("Custom", "Korean")]


def test_a_clans_flaw_and_bloodline_take_their_detail_into_the_name() -> None:
    found = traits(character("Thaddeus Ashby"))
    assert found["Merits: Bloodline (2, Coyote)"] == "merits: Bloodline: Coyote 2"
    assert found["Flaws: Gangrel (1, Rat in a Cage)"] == "flaws: Gangrel: Rat in a Cage 1"
    # A name followed by more than the catalogue's: the rest is a note.
    assert found["Flaws: Malkavian (1, Feeding Fetish, Only from a wine glass)"] == (
        "flaws: Malkavian: Feeding Fetish 1 (Only from a wine glass)"
    )
    assert found["Elder Disciplines: Potence: Relentess Fury"] == (
        "elder_disciplines: Potence: Relentless Fury"
    )
    assert found["Disciplines: Fortitude x2: Resilience"] == "disciplines: Fortitude 2 (Resilience)"


@pytest.mark.parametrize(
    ("written", "path"),
    [
        ("Path of Conjuring", "Thaumaturgy: Path of Conjuring"),
        ("The path of conjuring ", "Thaumaturgy: Path of Conjuring"),
        ("Green", "Thaumaturgy: Green Path"),
        ("The Lure of Flame", "Thaumaturgy: Lure of Flames"),
        ("Weather Control", "Thaumaturgy: Path of Weather Mastery"),
        ("Path of Neptune’s Might", "Thaumaturgy: Path of Neptune's Might"),
        ("Path of Ash", "Necromancy: Ash Path"),
        ("Soul Binding", "Necromancy: Path of Soul Bonding"),
        ("Path of Nowhere", None),
    ],
)
def test_paths_written_several_ways(written: str, path: str | None) -> None:
    assert mapper().path(written) == path


def test_a_troupes_own_list_of_areas_is_all_that_matches(tmp_path: Path) -> None:
    listed = Catalogue(
        **{
            **book_catalogue().__dict__,
            "lists": {"influence_elite_specializations": ["Social Media", "The Docks"]},
        }
    )
    mapped = mapper(listed).character(character("Agnes Wren"))
    elite = [t.name for t in mapped.traits if t.category == "influence_elite_specializations"]
    assert elite == ["Social Media"]
    assert (
        "Influences: The Elite: Organized Crime x1",
        "not on the troupe's list: Organized Crime",
    ) in [(u.source, u.reason) for u in mapped.unmatched]


def test_a_troupes_own_table_adds_to_the_names(tmp_path: Path) -> None:
    more = tmp_path / "ours.toml"
    more.write_text(
        '[values.influence_elite_specializations]\n"Police" = "Law Enforcement"\n'
        '[names.rituals]\n"Thaumaturgy: Whispers of the Moon" = "Thaumaturgy: Scry"\n'
    )
    ours = Mapper(read_table([more], renames=spelling_renames()), book_catalogue())
    mapped = ours.character(character("Agnes Wren"))
    underworld = [
        t.name for t in mapped.traits if t.category == "influence_underworld_specializations"
    ]
    assert underworld == ["Science/Medical", "Law Enforcement"]
    assert ("rituals", "Thaumaturgy: Scry") in [(t.category, t.name) for t in mapped.traits]
    assert [u.source for u in mapped.unmatched] == ["Backgrounds: Influences x1"]


# --- the import -------------------------------------------------------------------------


FAKE_PG_DUMP = """#!/bin/sh
echo "create table t (x int);"
"""


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def command_session(connection: Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    """The command's own session, inside the test's transaction."""
    monkeypatch.setattr(
        import_yorick_print,
        "get_sessionmaker",
        lambda: lambda: Session(bind=connection, join_transaction_mode="create_savepoint"),
    )


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Backups made by a stand-in for pg_dump, and pictures, in scratch directories."""
    directory = tmp_path / "backups"
    directory.mkdir()
    fake = tmp_path / "pg_dump"
    fake.write_text(FAKE_PG_DUMP)
    fake.chmod(0o755)
    monkeypatch.setattr(get_settings(), "backup_dir", str(directory))
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(backups, "PG_DUMP", str(fake))
    return directory


def imported(session: Session) -> dict[str, Character]:
    found = session.scalars(select(Character).where(Character.legacy_id.is_not(None)))
    return {c.name: c for c in found}


def sheet(session: Session, character: Character) -> dict[tuple[str, str, str], int | None]:
    return {r.key: r.trait.rating for r in sheets.sheet_rows(session, character)}


def run(page: Path, *args: str, out: Path | None = None) -> int:
    return import_yorick_print.main(
        [
            str(page),
            "--troupe",
            "Lords of the Night",
            "--out",
            str(out or page.parent / "out"),
            *args,
        ]
    )


@pytest.mark.usefixtures("command_session")
def test_a_dry_run_reports_every_character_and_saves_nothing(
    troupe: Troupe, session: Session, page: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session.commit()  # the troupe, where the command's session can see it

    assert run(page, "--dry-run") == 0

    out = capsys.readouterr().out
    assert session.scalar(select(func.count()).select_from(Character)) == 0
    assert "3 characters read from the page: 3 to be made, 0 to be updated" in out
    assert "1 import cleanly" in out
    assert "    Police x1 (no such Influence area: Police)" in out
    assert "  Title: 1 line. Titles are given in the troupe" in out
    assert "    Faction: Loyalist: Only a Sabbat character has a Faction." in out
    assert out.endswith("Dry run: nothing was saved.\n")

    report = (page.parent / "out" / "report.txt").read_text()
    agnes = report[report.index("== Agnes Wren") : report.index("== Thaddeus Ashby")]
    assert "Matched nothing:\n  Backgrounds: Influences x1 (no such background)" in agnes
    assert "Rule checks the sheet breaks:" in agnes
    assert "XP at the troupe's prices: " in agnes
    assert "Portrait: to be attached" in agnes
    assert "Left to staff:\n  Antecedence: Primary\n  Title: Primogen" in agnes
    thaddeus = report[report.index("== Thaddeus Ashby") :]
    assert "(Yorick id Th4ddAshby; labelled On Hold)" in thaddeus
    assert "Held at Horatio's value:\n  Talisman: printed 2, held at 3" in thaddeus

    records = json.loads((page.parent / "out" / "characters.json").read_text())
    assert [r["printed"]["name"] for r in records] == [
        "Agnes Wren",
        "Thaddeus Ashby",
        "Mystery Woman",
    ]
    assert records[0]["xp"] > 0


@pytest.mark.usefixtures("command_session")
def test_the_import_makes_sheeted_npcs_with_their_portraits_after_a_backup(
    troupe: Troupe,
    session: Session,
    page: Path,
    kept: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session.commit()

    assert run(page) == 0, capsys.readouterr()

    assert [b.name for b in backups.list_backups(kept)] != []
    found = imported(session)
    assert sorted(found) == ["Agnes Wren", "Mystery Woman", "Thaddeus Ashby"]
    agnes = found["Agnes Wren"]
    lords = session.get_one(TroupeRecord, uuid.UUID(troupe.id))
    assert (agnes.kind, agnes.npc_form, agnes.npc_kind) == ("npc", "sheeted", "vampire")
    assert agnes.owner_troupe_id == lords.id and agnes.player_id == lords.lead_user_id
    assert agnes.legacy_id == "aGnEsWr3n1"
    assert (found["Mystery Woman"].legacy_id or "").startswith("print-")

    held = sheet(session, agnes)
    assert held[("clan", "Tremere", "")] is None
    assert held[("attributes", "Mental", "")] == 7
    assert held[("paths", "Humanity", "")] == 4
    assert held[("disciplines", "Thaumaturgy: Path of Blood", "")] == 3
    assert held[("merits", "Thaumaturgic Expertise", "Thaumaturgy: Path of Conjuring")] == 1
    assert held[("focus_mentals", "Intelligence", "")] == held[("focus_mentals", "Wits", "")] == 1
    # A ritual at its level, a merit at its value here.
    assert held[("rituals", "Thaumaturgy: Thaumaturgic Metabolism", "")] == 3
    assert sheet(session, found["Thaddeus Ashby"])[("merits", "Talisman", "")] == 3
    # Refused on the sheet: a faction is for the Sabbat only.
    assert ("faction", "Loyalist", "") not in sheet(session, found["Thaddeus Ashby"])

    # Its portrait, as an upload would be kept, and none for one without.
    assert agnes.picture_id is not None
    assert any((tmp_path / "uploads").rglob("128.webp"))
    assert found["Thaddeus Ashby"].picture_id is None

    logged = session.scalars(select(AuditEvent).where(AuditEvent.action == "npc.imported")).all()
    assert sorted(e.data["legacy_id"] for e in logged) == sorted(
        c.legacy_id or "" for c in found.values()
    )
    assert {e.data["label"] for e in logged} == {"none", "On Hold"}
    # No XP is written: that waits until the character is given to its player.
    assert sheets.xp_balance(session, agnes) == 0


@pytest.mark.usefixtures("command_session")
def test_running_it_again_updates_rather_than_duplicating(
    troupe: Troupe, session: Session, page: Path, kept: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session.commit()
    assert run(page) == 0
    first = imported(session)
    agnes = first["Agnes Wren"]
    picture = agnes.picture_id
    # Staff add a trait by hand, and give one character to its player.
    resources, _ = sheets.find_definition(session, agnes, "backgrounds", "Resources")
    session.add(CharacterTrait(character_id=agnes.id, trait_definition_id=resources.id, rating=2))
    mystery = first["Mystery Woman"]
    mystery.kind, mystery.owner_troupe_id = "pc", None
    mystery.npc_kind = mystery.npc_form = None
    agnes.name = "Agnes"
    session.commit()
    capsys.readouterr()

    # Backups are named to the second, and the first run's was made a moment ago.
    assert run(page, "--no-backup") == 0

    out = capsys.readouterr().out
    assert "0 made, 2 updated, 1 skipped, 0 failed." in out
    again = imported(session)
    assert session.scalar(select(func.count()).select_from(Character)) == 3
    assert again["Agnes Wren"].id == agnes.id
    assert again["Agnes Wren"].picture_id == picture
    assert sheet(session, agnes)[("backgrounds", "Resources", "")] == 2
    assert session.scalar(select(func.count()).where(AuditEvent.action == "npc.reimported")) == 2
    report = (page.parent / "out" / "report.txt").read_text()
    assert "Skipped: it has been given to its player." in report


@pytest.mark.usefixtures("command_session", "troupe")
def test_without_backups_it_imports_only_when_told_to(
    session: Session, page: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session.commit()

    assert run(page) == 1
    assert "Backups are not set up here" in capsys.readouterr().err
    assert imported(session) == {}

    assert run(page, "--no-backup") == 0
    assert len(imported(session)) == 3


@pytest.mark.usefixtures("command_session")
def test_the_import_is_made_by_the_staff_member_named(
    troupe: Troupe, session: Session, page: Path, kept: Path
) -> None:
    session.commit()

    assert run(page, "--as", troupe.storyteller.handle) == 0

    storyteller = session.scalars(
        select(User).where(User.handle == troupe.storyteller.handle)
    ).one()
    assert {c.player_id for c in imported(session).values()} == {storyteller.id}


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--troupe", "Nobody"], "No troupe has the id or name 'Nobody'."),
        (["--troupe", "Lords of the Night", "--as", "nobody"], "No one has the handle 'nobody'."),
    ],
)
@pytest.mark.usefixtures("command_session", "troupe")
def test_the_command_says_what_is_wrong(
    session: Session,
    page: Path,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    message: str,
) -> None:
    session.commit()
    assert import_yorick_print.main([str(page), "--dry-run", *args]) != 0
    assert message in capsys.readouterr().err


def test_a_troupes_lists_come_from_its_settings(troupe: Troupe, session: Session) -> None:
    lords = session.get_one(TroupeRecord, uuid.UUID(troupe.id))
    lead = session.get_one(User, lords.lead_user_id)
    set_troupe_options(session, lead, lords, "influence_elite_specializations", ["The Docks"])

    catalogue = import_yorick_print.catalogue_for(session, lords)

    assert catalogue.lists == {"influence_elite_specializations": ["The Docks"]}
    assert ("merits", "Thaumaturgic Expertise") in catalogue.path_detailed
    assert ("merits", "Angelic Visage") in catalogue.detailed

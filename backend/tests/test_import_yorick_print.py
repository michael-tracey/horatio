"""Importing a troupe's characters from Yorick's Print Characters page (#482), from a
made-up page in its format (tests/fixtures/yorick_print.html)."""

import shutil
import uuid
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from horatio import import_yorick_print
from horatio.models import Troupe as TroupeRecord
from horatio.models import User
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


def test_an_unmatched_line_says_where_a_name_would_match_it() -> None:
    unmatched = mapper().character(character("Agnes Wren")).unmatched

    assert [(u.table, u.category, u.key) for u in unmatched] == [
        ("names", "backgrounds", "Influences"),
        ("values", "influence_underworld_specializations", "Police"),
        ("names", "rituals", "Thaumaturgy: Whispers of the Moon"),
    ]


def test_a_troupes_own_table_can_come_from_the_database_too() -> None:
    ours = Mapper(
        read_table(
            renames=spelling_renames(),
            more=[{"values": {"influence_elite_specializations": {"Police": "Law Enforcement"}}}],
        ),
        book_catalogue(),
    )

    mapped = ours.character(character("Agnes Wren"))

    assert "Police x1" not in [u.text for u in mapped.unmatched]


# --- the troupe's catalogue -------------------------------------------------------------------


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def test_a_troupes_lists_come_from_its_settings(troupe: Troupe, session: Session) -> None:
    lords = session.get_one(TroupeRecord, uuid.UUID(troupe.id))
    lead = session.get_one(User, lords.lead_user_id)
    set_troupe_options(session, lead, lords, "influence_elite_specializations", ["The Docks"])

    catalogue = import_yorick_print.catalogue_for(session, lords)

    assert catalogue.lists == {"influence_elite_specializations": ["The Docks"]}
    assert ("merits", "Thaumaturgic Expertise") in catalogue.path_detailed
    assert ("merits", "Angelic Visage") in catalogue.detailed

"""Importing the influence log from the old spreadsheet (#132), from made-up rows in
the sheet's own formats."""

import csv
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, func, select
from sqlalchemy.orm import Session

from horatio import import_influence_log
from horatio.import_influence_log import (
    Row,
    import_log,
    parse_date,
    read_rows,
    read_source,
    times_taken,
)
from horatio.influence_log import short_id
from horatio.models import AuditEvent, InfluenceEntry
from horatio.models import Troupe as TroupeRecord
from tests.api_helpers import Troupe
from tests.test_api_downtimes import member_character

NEW_YORK = ZoneInfo("America/New_York")
HEADINGS = [
    "Date",
    "Age",
    "Character",
    "Specialization",
    "Action",
    "Details",
    "Any blocks?",
    "Output",
]

ELITE = [
    ["November 2024", 23, "Agnes Wren", "News Media", "2: Gossip and Insider Trading",
     "To hear what the papers say about the mayor", "", "- 11/2024, ..."],
    ["", 4, "", "", "", "", "", ""],
    ["June 7 2025", 16, "  agnes   WREN ", "Finance", "5: No Party Crashers",
     "To keep the Brujah out of the gala (this action is logged 3 times)", 10, ""],
    ["July 5", 15, "Old Tom", "Police", "Attack",
     "To strike at the mayor's friends (this action is logged twice", "", ""],
    [],
    ["June 6, 2026", 4, "Old Tom", "Police", "4: Smooth Over",
     "To smooth over the confession (there are three entries of this).", "2", ""],
    ["Someday", 1, "Old Tom", "", "Block", "", "", ""],
]  # fmt: skip
UNDERWORLD = [
    ["February 1 2025", 20, "Bartholomew", "Transportation", "5: Lockdown",
     "To secure the docks (This is logged 5 times)", "", ""],
    ["March 3 2025", 19, "Bartholomew", "Street Gangs", "9: An Offer You Can't Refuse",
     "To make the gang an offer (this is logged twice)", "", ""],
    ["April 2 2025", 18, "Bartholomew", "Street Gangs", "Block", "", "", ""],
    ["May 1 2025", 17, "Bartholomew", "Street Gangs", "Wish Upon a Star", "Who knows", "", ""],
    ["May 2 2025", 17, "Mystery Woman", "Street Gangs", "2: Word on the Street",
     "To learn who runs the docks", "", ""],
]  # fmt: skip


def rows(table: Sequence[Sequence[Any]]) -> list[Row]:
    """The rows under the heading, numbered as in the sheet."""
    return [
        Row(n, dict(zip([h.casefold() for h in HEADINGS], values, strict=False)))
        for n, values in enumerate(table, start=2)
    ]


def write_csv(folder: Path, name: str, table: Sequence[Sequence[Any]]) -> None:
    with (folder / name).open("w", newline="") as file:
        csv.writer(file).writerows([HEADINGS, *table])


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """The two tabs as Google names them on download."""
    write_csv(tmp_path, "LotsLarp - Elite Infl..csv", ELITE)
    write_csv(tmp_path, "UW Infl.csv", UNDERWORLD)
    return tmp_path


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def record(troupe: Troupe) -> TroupeRecord:
    return troupe.session.get_one(TroupeRecord, uuid.UUID(troupe.id))


def alias(troupe: Troupe, character_id: str, name: str) -> None:
    taken = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "backgrounds", "name": "Alternate Identity", "detail": name, "rating": 1},
    )
    assert taken.status_code == 200, taken.text


def entries(session: Session) -> dict[str, InfluenceEntry]:
    return {e.reference or "": e for e in session.scalars(select(InfluenceEntry))}


# --- reading rows -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "read"),
    [
        ("November 2024", (11, 1, 2024)),
        ("June 7 2025", (6, 7, 2025)),
        ("June 6, 2026", (6, 6, 2026)),
        ("February 1 2025", (2, 1, 2025)),
        ("July 5", (7, 5, None)),
        ("Sept 3rd", (9, 3, None)),
        ("6/7/2025", (6, 7, 2025)),
        (datetime(2025, 6, 7), (6, 7, 2025)),
    ],
)
def test_the_sheets_date_formats_are_read(written: Any, read: tuple[int, int, int | None]) -> None:
    found = parse_date(written)
    assert found is not None
    assert (found.month, found.day, found.year) == read


@pytest.mark.parametrize("written", ["Someday", "2025", "June", ""])
def test_what_is_not_a_date_is_not_read(written: str) -> None:
    assert parse_date(written) is None


@pytest.mark.parametrize(
    ("details", "purpose", "times"),
    [
        ("To hide the body (this action is logged 3 times)", "To hide the body", 3),
        ("To hide the body (this action is logged twice)", "To hide the body", 2),
        ("To hide the body (this action is logged thrice)", "To hide the body", 3),
        ("To hide the body (This is logged 5 times)", "To hide the body", 5),
        ("To hide the body (this is logged twice)", "To hide the body", 2),
        ("To hide the body (there are three entries of this).", "To hide the body.", 3),
        ("To hide the body (this action is logged twice", "To hide the body", 2),
        ("To hide the body (in the river)", "To hide the body (in the river)", 1),
    ],
)
def test_a_logged_n_times_note_sets_the_times_taken(details: str, purpose: str, times: int) -> None:
    assert times_taken(details) == (purpose, times)


def test_a_date_with_no_year_takes_it_from_the_rows_around_it() -> None:
    choices = []
    table = [
        ["December 20, 2024", 1, "Agnes", "", "Attack", "", "", ""],
        ["January 3", 1, "Agnes", "", "Attack", "", "", ""],
        ["December 30", 1, "Agnes", "", "Attack", "", "", ""],
    ]
    lines, skipped = read_rows("elite", rows(table), choices)
    assert [line.day for line in lines] == [
        date(2024, 12, 20),
        date(2025, 1, 3),
        date(2024, 12, 30),
    ]
    assert skipped == []

    # Before any year, from the first date after it.
    lines, _ = read_rows("elite", rows([table[2], ["January 5 2026", 1, "Agnes"]]), choices)
    assert [line.day for line in lines] == [date(2025, 12, 30), date(2026, 1, 5)]


# --- importing --------------------------------------------------------------------------


def test_each_row_with_a_date_becomes_an_entry(
    troupe: Troupe, session: Session, source: Path
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes Wren")

    report = import_log(session, record(troupe), read_source(source), NEW_YORK)

    found = entries(session)
    assert sorted(found) == ["E2", "E4", "E5", "E7", "UW2", "UW3", "UW4", "UW5", "UW6"]
    first = found["E2"]
    assert (short_id(first), first.type, first.source) == ("E2", "elite", "import")
    assert first.happened_at == datetime(2024, 11, 1, 4, 0, tzinfo=UTC)  # midnight in New York
    assert (str(first.character_id), first.name) == (agnes, "Agnes Wren")
    assert (first.specialization, first.action_key, first.times, first.blocks) == (
        "News Media",
        "gossip_and_insider_trading",
        1,
        0,
    )
    assert first.purpose == "To hear what the papers say about the mayor"
    assert first.logged_by is None

    # Matched ignoring case and spacing; "logged 3 times"; blocks as given.
    gala = found["E4"]
    assert (str(gala.character_id), gala.action_key, gala.times, gala.blocks) == (
        agnes,
        "no_party_crashers",
        3,
        10,
    )
    assert gala.purpose == "To keep the Brujah out of the gala"

    # "July 5" falls between June 2025 and June 2026, nearest June 2025.
    attack = found["E5"]
    assert attack.happened_at.astimezone(NEW_YORK).date() == date(2025, 7, 5)
    assert (attack.character_id, attack.name, attack.action_key, attack.times) == (
        None,
        "Old Tom",
        "attack",
        2,
    )
    assert attack.purpose == "To strike at the mayor's friends"
    assert (found["E7"].times, found["E7"].blocks) == (3, 2)

    docks = found["UW2"]
    assert (docks.action_key, docks.times, docks.blocks) == ("lockdown", 5, 0)
    assert found["UW3"].action_key == "an_offer_you_cant_refuse"
    assert found["UW4"].action_key == "block"
    # An action the rules don't have is kept for staff to finish.
    unknown = found["UW5"]
    assert (unknown.action_key, unknown.needs_details) == (None, True)

    elite, underworld = report.tabs
    assert (elite.rows, elite.added, len(elite.skipped)) == (6, 4, 2)
    assert [(s.reference, s.reason) for s in elite.skipped] == [
        ("E3", "only an age"),
        ("E8", "can't read the date 'Someday'"),
    ]
    assert (underworld.rows, underworld.added, underworld.skipped) == (5, 5, [])
    assert underworld.unknown_actions == [("UW5", "Wish Upon a Star")]
    assert report.unmatched == {"Old Tom": 2, "Bartholomew": 4, "Mystery Woman": 1}


def test_an_imported_row_keeps_its_number_unless_it_is_taken(
    troupe: Troupe, session: Session, source: Path
) -> None:
    taken = import_log(session, record(troupe), read_source(source), NEW_YORK)
    assert taken.tabs[0].added == 4
    first = entries(session)["E2"]
    first.reference = "something else"
    session.flush()

    import_log(session, record(troupe), read_source(source), NEW_YORK)

    again = entries(session)["E2"]
    assert again.id != first.id
    assert short_id(again) == "E8"  # E2 is taken, and E7 is the highest
    assert first.number == 2


def test_running_it_again_changes_nothing_then_links_new_characters(
    troupe: Troupe, session: Session, source: Path
) -> None:
    import_log(session, record(troupe), read_source(source), NEW_YORK)
    count = session.scalar(select(func.count()).select_from(AuditEvent))

    again = import_log(session, record(troupe), read_source(source), NEW_YORK)

    assert [(t.added, t.updated, t.unchanged) for t in again.tabs] == [(0, 0, 4), (0, 0, 5)]
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == count
    assert len(entries(session)) == 9

    # Tom joins the troupe, and is renamed; Bart's Alternate Identity is Bartholomew.
    tom = member_character(troupe, troupe.player, "Old Tom")
    renamed = troupe.player.client.patch(f"/characters/{tom}", json={"name": "Thomas"})
    assert renamed.status_code == 200, renamed.text
    bart = member_character(troupe, troupe.player, "Bart")
    alias(troupe, bart, "Bartholomew")

    linked = import_log(session, record(troupe), read_source(source), NEW_YORK)

    assert [(t.added, t.updated, t.linked) for t in linked.tabs] == [(0, 2, 2), (0, 4, 4)]
    found = entries(session)
    assert {str(found[r].character_id) for r in ("E5", "E7")} == {tom}
    assert {str(found[f"UW{n}"].character_id) for n in range(2, 6)} == {bart}
    assert linked.unmatched == {"Agnes Wren": 1, "agnes WREN": 1, "Mystery Woman": 1}


def test_an_entry_keeps_what_staff_gave_it_where_the_sheet_has_nothing(
    troupe: Troupe, session: Session, source: Path
) -> None:
    import_log(session, record(troupe), read_source(source), NEW_YORK)
    agnes = member_character(troupe, troupe.player, "Agnes Wren")
    unknown = entries(session)["UW5"]
    unknown.action_key, unknown.needs_details = "pulling_strings", False
    unknown.character_id = uuid.UUID(agnes)
    session.flush()

    report = import_log(session, record(troupe), read_source(source), NEW_YORK)

    again = entries(session)["UW5"]
    assert (again.action_key, again.needs_details, str(again.character_id)) == (
        "pulling_strings",
        False,
        agnes,
    )
    assert report.tabs[1].unknown_actions == []


def test_a_name_more_than_one_character_goes_by_is_kept_as_text(
    troupe: Troupe, session: Session, source: Path
) -> None:
    member_character(troupe, troupe.player, "Agnes Wren")
    maud = member_character(troupe, troupe.player, "Maud")
    alias(troupe, maud, "Agnes  Wren")

    report = import_log(session, record(troupe), read_source(source), NEW_YORK)

    assert entries(session)["E2"].character_id is None
    assert report.ambiguous == {"Agnes Wren": 1, "agnes WREN": 1}


def test_the_spreadsheet_can_be_given_as_xlsx(
    troupe: Troupe, session: Session, tmp_path: Path
) -> None:
    book = openpyxl.Workbook()
    elite = book.active
    assert elite is not None
    elite.title = "Elite Infl."
    for values in [HEADINGS, *ELITE[:1], [datetime(2025, 6, 7), 16, "Old Tom", "", "Attack"]]:
        elite.append(values)
    underworld = book.create_sheet("UW Infl.")
    for values in [HEADINGS, *UNDERWORLD[:1]]:
        underworld.append(values)
    path = tmp_path / "LotsLarp.xlsx"
    book.save(path)

    report = import_log(session, record(troupe), read_source(path), NEW_YORK)

    assert [t.added for t in report.tabs] == [2, 1]
    found = entries(session)
    assert found["E3"].happened_at == datetime(2025, 6, 7, 4, 0, tzinfo=UTC)
    assert found["UW2"].times == 5


def test_a_source_without_both_tabs_is_refused(tmp_path: Path) -> None:
    write_csv(tmp_path, "Elite Infl.csv", ELITE)
    with pytest.raises(import_influence_log.CannotImport, match="UW Infl."):
        read_source(tmp_path)


# --- the command ------------------------------------------------------------------------


@pytest.fixture
def command_session(connection: Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    """The command's own session, inside the test's transaction."""
    monkeypatch.setattr(
        import_influence_log,
        "get_sessionmaker",
        lambda: lambda: Session(bind=connection, join_transaction_mode="create_savepoint"),
    )


@pytest.mark.usefixtures("command_session")
def test_a_dry_run_reports_and_saves_nothing(
    troupe: Troupe, session: Session, source: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session.commit()  # the troupe, where the command's session can see it

    code = import_influence_log.main([str(source), "--troupe", "lords of the night", "--dry-run"])

    out = capsys.readouterr().out
    assert code == 0, out
    assert session.scalar(select(func.count()).select_from(InfluenceEntry)) == 0
    assert "Elite Infl.: 6 rows; 4 entries added" in out
    assert "Skipped 1 row with only an age: E3" in out
    assert "Needs details UW5: 'Wish Upon a Star' is not one of the actions" in out
    assert "  Old Tom (2 entries)" in out
    assert out.endswith("Dry run: nothing was saved.\n")


@pytest.mark.usefixtures("command_session")
def test_the_command_saves_the_entries(
    troupe: Troupe, session: Session, source: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session.commit()

    code = import_influence_log.main(
        [str(source), "--troupe", troupe.id, "--timezone", "Europe/London"]
    )

    assert code == 0, capsys.readouterr()
    first = entries(session)["E2"]
    assert first.happened_at == datetime(2024, 11, 1, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--troupe", "Nobody"], "No troupe has the id or name 'Nobody'."),
        (["--troupe", "Lords of the Night", "--timezone", "Mars/Olympus"], "no time zone"),
    ],
)
@pytest.mark.usefixtures("command_session", "troupe")
def test_the_command_says_what_is_wrong(
    session: Session,
    source: Path,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    message: str,
) -> None:
    session.commit()
    assert import_influence_log.main([str(source), *args]) != 0
    assert message in capsys.readouterr().err

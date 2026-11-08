"""The custodian's import from Yorick, in the app (#518), from a made-up page in the
Print Characters format (tests/fixtures/yorick_print.html), never the real one."""

import io
import uuid
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Connection, func, select
from sqlalchemy.orm import Session

from horatio import backups, sheets, yorick_imports
from horatio.config import get_settings
from horatio.models import AuditEvent, Character, CharacterTrait, User, YorickImport
from tests.api_helpers import Person, Troupe, new_character

FIXTURE = Path(__file__).parent / "fixtures" / "yorick_print.html"
PAGE = "Print Troupe Characters.html"
PORTRAIT = "Print Troupe Characters_files/0a1b2c3d4e5f_thumbnail_128_bqmm.jpg"
FAKE_PG_DUMP = """#!/bin/sh
echo "create table t (x int);"
"""


def portrait() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (128, 128), (120, 20, 30)).save(out, "JPEG")
    return out.getvalue()


def zipped(files: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


def saved_page() -> bytes:
    """The page and its _files folder, zipped as a custodian would, with a stylesheet
    and script the browser saved too."""
    return zipped(
        {
            f"saved/{PAGE}": FIXTURE.read_bytes(),
            f"saved/{PORTRAIT}": portrait(),
            "saved/Print Troupe Characters_files/site.css": b"body {}",
            "saved/Print Troupe Characters_files/app.js": b"alert(1)",
        }
    )


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    found = Troupe(client_for, session)
    session.commit()
    return found


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, connection: Connection) -> Path:
    """Uploads and backups in scratch directories, backups by a stand-in for pg_dump,
    and each job run straight away in a session of its own inside the test's."""
    directory = tmp_path / "backups"
    directory.mkdir()
    fake = tmp_path / "pg_dump"
    fake.write_text(FAKE_PG_DUMP)
    fake.chmod(0o755)
    monkeypatch.setattr(get_settings(), "backup_dir", str(directory))
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(backups, "PG_DUMP", str(fake))
    monkeypatch.setattr(yorick_imports, "launch", lambda work: work())
    monkeypatch.setattr(
        yorick_imports,
        "open_session",
        lambda: Session(bind=connection, join_transaction_mode="create_savepoint"),
    )
    return tmp_path


def upload(person: Person, troupe: Troupe, data: bytes, name: str = "saved.zip") -> Any:
    return person.client.post(
        f"/yorick-imports/{troupe.id}/page", files={"file": (name, data, "application/zip")}
    )


def uploaded(troupe: Troupe) -> dict[str, Any]:
    response = upload(troupe.custodian, troupe, saved_page())
    assert response.status_code == 200, response.text
    return response.json()


def report(troupe: Troupe) -> dict[str, Any]:
    response = troupe.custodian.client.get(f"/yorick-imports/{troupe.id}/report")
    assert response.status_code == 200, response.text
    return response.json()


def by_name(found: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in found["characters"]}


def imported(session: Session) -> dict[str, Character]:
    session.expire_all()
    found = session.scalars(select(Character).where(Character.legacy_id.is_not(None)))
    return {c.name: c for c in found}


def import_now(troupe: Troupe, **body: Any) -> dict[str, Any]:
    response = troupe.custodian.client.post(f"/yorick-imports/{troupe.id}/import", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def dry_run(troupe: Troupe) -> dict[str, Any]:
    response = troupe.custodian.client.post(f"/yorick-imports/{troupe.id}/dry-run")
    assert response.status_code == 200, response.text
    return response.json()


# --- who ----------------------------------------------------------------------------------


@pytest.mark.usefixtures("kept")
def test_only_the_custodian_can_reach_it(troupe: Troupe) -> None:
    uploaded(troupe)
    for person in (troupe.lead, troupe.storyteller, troupe.assistant, troupe.player):
        for response in (
            person.client.get("/yorick-imports"),
            person.client.get(f"/yorick-imports/{troupe.id}"),
            person.client.get(f"/yorick-imports/{troupe.id}/report"),
            person.client.get(f"/yorick-imports/{troupe.id}/report.txt"),
            person.client.get(f"/yorick-imports/{troupe.id}/characters.json"),
            upload(person, troupe, saved_page()),
            person.client.post(f"/yorick-imports/{troupe.id}/dry-run"),
            person.client.post(f"/yorick-imports/{troupe.id}/import", json={}),
            person.client.delete(f"/yorick-imports/{troupe.id}/page"),
        ):
            assert response.status_code == 403, (person.handle, response.request.url)


# --- the dry run --------------------------------------------------------------------------


def test_an_upload_is_checked_with_a_dry_run_that_saves_nothing(
    troupe: Troupe, session: Session, kept: Path
) -> None:
    state = uploaded(troupe)

    assert state["page"]["name"] == f"saved/{PAGE}"
    assert state["job"] is None and state["error"] is None
    assert state["report_kind"] == "dry_run" and not state["report_stale"]
    assert state["cannot_import"] is None
    # The page and its portraits are kept, and nothing else the browser saved.
    folder = kept / "uploads" / "yorick-imports" / troupe.id / "saved"
    assert (folder / PAGE).is_file() and (folder / PORTRAIT).is_file()
    assert not (folder / "Print Troupe Characters_files" / "app.js").exists()
    assert imported(session) == {}

    found = report(troupe)
    assert found["summary"][0].startswith("3 characters read from the page: 3 to be made")
    agnes = by_name(found)["Agnes Wren"]
    assert agnes["outcome"] == "made" and agnes["portrait"] == "to be attached"
    assert {(u["source"], u["part"], u["category"], u["key"]) for u in agnes["unmatched"]} >= {
        (
            "Influences: The Underworld: Police x1",
            "values",
            "influence_underworld_specializations",
            "Police",
        )
    }
    assert by_name(found)["Thaddeus Ashby"]["refused"] == [
        "Faction: Loyalist: Only a Sabbat character has a Faction."
    ]

    text = troupe.custodian.client.get(f"/yorick-imports/{troupe.id}/report.txt")
    assert text.status_code == 200 and "== Agnes Wren" in text.text
    records = troupe.custodian.client.get(f"/yorick-imports/{troupe.id}/characters.json").json()
    assert [r["printed"]["name"] for r in records] == [
        "Agnes Wren",
        "Thaddeus Ashby",
        "Mystery Woman",
    ]
    actions = session.scalars(
        select(AuditEvent.action).where(AuditEvent.action.startswith("yorick_import."))
    ).all()
    assert sorted(actions) == [
        "yorick_import.downloaded",
        "yorick_import.downloaded",
        "yorick_import.uploaded",
    ]


@pytest.mark.usefixtures("kept")
def test_the_page_alone_comes_without_portraits(troupe: Troupe) -> None:
    response = upload(troupe.custodian, troupe, FIXTURE.read_bytes(), PAGE)

    assert response.status_code == 200, response.text
    assert response.json()["page"]["name"] == PAGE
    assert by_name(report(troupe))["Agnes Wren"]["portrait"].startswith("not attached")


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("notes.txt", b"hello", "Upload the page saved from Yorick"),
        ("page.html", b"<html><body>Hi</body></html>", "not Yorick's Print Characters page"),
        ("saved.zip", b"PK\x03\x04 not really", "can't be opened"),
        ("saved.zip", zipped({"x/notes.txt": b"hi"}), "no saved page"),
        ("saved.zip", zipped({"a.html": b"<html/>", "b.html": b"<html/>"}), "more than one page"),
        ("saved.zip", zipped({"../evil.html": b"<html/>"}), "outside its folder"),
        ("saved.zip", zipped({"/etc/evil.html": b"<html/>"}), "outside its folder"),
    ],
)
def test_what_is_not_a_saved_page_is_refused(
    troupe: Troupe, kept: Path, name: str, data: bytes, message: str
) -> None:
    response = upload(troupe.custodian, troupe, data, name)

    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert not (kept / "evil.html").exists()
    assert troupe.custodian.client.get(f"/yorick-imports/{troupe.id}").json()["page"] is None


@pytest.mark.usefixtures("troupe")
def test_without_uploads_nothing_can_be_uploaded(troupe: Troupe) -> None:
    state = troupe.custodian.client.get(f"/yorick-imports/{troupe.id}").json()
    assert state["uploads_available"] is False

    response = upload(troupe.custodian, troupe, saved_page())

    assert response.status_code == 422
    assert response.json()["detail"] == "Uploads are not set up here."


# --- names --------------------------------------------------------------------------------


@pytest.mark.usefixtures("kept")
def test_an_unmatched_line_is_given_its_name_and_the_dry_run_run_again(troupe: Troupe) -> None:
    uploaded(troupe)
    client = troupe.custodian.client
    options = client.get(
        f"/yorick-imports/{troupe.id}/options",
        params={"part": "values", "category": "influence_underworld_specializations"},
    ).json()
    assert "Law Enforcement" in options and "Custom" not in options

    refused = client.put(
        f"/yorick-imports/{troupe.id}/names",
        json={
            "part": "values",
            "category": "influence_underworld_specializations",
            "yorick": "Police",
            "horatio": "Nothing Like It",
        },
    )
    assert refused.status_code == 422

    state = client.put(
        f"/yorick-imports/{troupe.id}/names",
        json={
            "part": "values",
            "category": "influence_underworld_specializations",
            "yorick": "Police",
            "horatio": "Law Enforcement",
        },
    ).json()
    assert state["names"] == [
        {
            "part": "values",
            "category": "influence_underworld_specializations",
            "yorick": "Police",
            "horatio": "Law Enforcement",
        }
    ]
    assert state["report_stale"] is True
    assert state["cannot_import"].startswith("Names or choices have changed")

    state = dry_run(troupe)

    assert state["report_stale"] is False and state["cannot_import"] is None
    agnes = by_name(report(troupe))["Agnes Wren"]
    assert "Police x1" not in [u["text"] for u in agnes["unmatched"]]

    # Taken out again, it is unmatched again.
    client.put(
        f"/yorick-imports/{troupe.id}/names",
        json={
            "part": "values",
            "category": "influence_underworld_specializations",
            "yorick": "Police",
            "horatio": None,
        },
    )
    dry_run(troupe)
    agnes = by_name(report(troupe))["Agnes Wren"]
    assert "Police x1" in [u["text"] for u in agnes["unmatched"]]


@pytest.mark.usefixtures("kept")
def test_a_line_left_for_staff_is_counted_apart(troupe: Troupe) -> None:
    uploaded(troupe)
    client = troupe.custodian.client

    state = client.put(
        f"/yorick-imports/{troupe.id}/by-hand",
        json={"source": "Backgrounds: Influences x1", "by_hand": True},
    ).json()

    assert state["by_hand"] == ["Backgrounds: Influences x1"]
    # Marking a line changes nothing the import does.
    assert state["report_stale"] is False
    dry_run(troupe)
    assert "1 more left for staff to put right by hand" in report(troupe)["summary"][1]


@pytest.mark.usefixtures("kept")
def test_a_table_written_for_the_command_line_can_be_added(troupe: Troupe) -> None:
    table = (
        '[names.rituals]\n"Thaumaturgy: Whispers of the Moon" = "Thaumaturgy: Scry"\n'
        '[values.influence_underworld_specializations]\n"Police" = "Law Enforcement"\n'
        '[paths]\n"Blood Path" = "Thaumaturgy: Path of Blood"\n'
    )

    response = troupe.custodian.client.post(
        f"/yorick-imports/{troupe.id}/names/file",
        files={"file": ("ours.toml", table.encode(), "application/toml")},
    )

    assert response.json() == {"added": 3}
    state = troupe.custodian.client.get(f"/yorick-imports/{troupe.id}").json()
    assert {(n["part"], n["yorick"]) for n in state["names"]} == {
        ("names", "Thaumaturgy: Whispers of the Moon"),
        ("values", "Police"),
        ("paths", "Blood Path"),
    }
    bad = troupe.custodian.client.post(
        f"/yorick-imports/{troupe.id}/names/file",
        files={"file": ("ours.toml", b"[names", "application/toml")},
    )
    assert bad.status_code == 422


# --- the import ---------------------------------------------------------------------------


def test_the_import_makes_sheeted_npcs_after_a_backup_and_deletes_the_page(
    troupe: Troupe, session: Session, kept: Path
) -> None:
    uploaded(troupe)

    state = import_now(troupe)

    assert state["job"] is None and state["error"] is None
    assert state["report_kind"] == "import"
    assert state["page"] is None
    assert state["cannot_import"] == "Upload the page first."
    assert not (kept / "uploads" / "yorick-imports" / troupe.id).exists()
    assert backups.list_backups(kept / "backups") != []
    found = imported(session)
    assert sorted(found) == ["Agnes Wren", "Mystery Woman", "Thaddeus Ashby"]
    agnes = found["Agnes Wren"]
    assert (agnes.kind, agnes.npc_form, agnes.legacy_id) == ("npc", "sheeted", "aGnEsWr3n1")
    assert str(agnes.owner_troupe_id) == troupe.id
    assert agnes.picture_id is not None
    assert sheets.xp_balance(session, agnes) == 0
    # Yorick doesn't print which dots were creation picks, so they are fitted (#527).
    assert agnes.fits_picks
    fitted = [r.trait for r in sheets.sheet_rows(session, agnes) if r.trait.creation_pick]
    assert fitted and {t.pick_by for t in fitted} == {"fit"}
    assert report(troupe)["summary"][0].startswith("3 characters read from the page: 3 made")
    event = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "yorick_import.imported")
    ).one()
    assert event.data["made"] == 3 and event.data["backup"].endswith("-manual.sql.gz")


@pytest.mark.usefixtures("kept")
def test_it_imports_only_after_a_dry_run_with_nothing_changed(troupe: Troupe) -> None:
    client = troupe.custodian.client
    assert client.post(f"/yorick-imports/{troupe.id}/import", json={}).status_code == 409

    uploaded(troupe)
    client.put(
        f"/yorick-imports/{troupe.id}/names",
        json={
            "part": "names",
            "category": "rituals",
            "yorick": "X",
            "horatio": "Thaumaturgy: Scry",
        },
    )
    response = client.post(f"/yorick-imports/{troupe.id}/import", json={})

    assert response.status_code == 409
    assert response.json()["detail"].startswith("Names or choices have changed")


def test_importing_again_updates_the_npcs_it_made(
    troupe: Troupe, session: Session, kept: Path
) -> None:
    uploaded(troupe)
    import_now(troupe)
    first = imported(session)
    agnes = first["Agnes Wren"]
    resources, _ = sheets.find_definition(session, agnes, "backgrounds", "Resources")
    session.add(CharacterTrait(character_id=agnes.id, trait_definition_id=resources.id, rating=2))
    mystery = first["Mystery Woman"]
    mystery.kind, mystery.owner_troupe_id = "pc", None
    mystery.npc_kind = mystery.npc_form = None
    session.commit()

    # Months later, a new page; backups are named to the second.
    get_settings().backup_dir = None
    uploaded(troupe)
    state = import_now(troupe, without_backup=True)

    assert state["error"] is None
    again = imported(session)
    assert again["Agnes Wren"].id == agnes.id
    assert session.scalar(select(func.count()).select_from(Character)) == 3
    held = {r.key: r.trait.rating for r in sheets.sheet_rows(session, again["Agnes Wren"])}
    assert held[("backgrounds", "Resources", "")] == 2
    outcomes = {c["name"]: c["outcome"] for c in report(troupe)["characters"]}
    assert outcomes == {
        "Agnes Wren": "updated",
        "Thaddeus Ashby": "updated",
        "Mystery Woman": "skipped",
    }


@pytest.mark.usefixtures("kept")
def test_without_backups_it_imports_only_when_told_to(troupe: Troupe, session: Session) -> None:
    get_settings().backup_dir = None
    state = uploaded(troupe)
    assert state["backups_available"] is False

    response = troupe.custodian.client.post(f"/yorick-imports/{troupe.id}/import", json={})
    assert response.status_code == 409
    assert "Backups are not set up here" in response.json()["detail"]
    assert imported(session) == {}

    import_now(troupe, without_backup=True)
    assert len(imported(session)) == 3


@pytest.mark.usefixtures("kept")
def test_the_npcs_are_made_by_the_staff_member_chosen(troupe: Troupe, session: Session) -> None:
    client = troupe.custodian.client
    assistant = session.scalars(select(User).where(User.handle == troupe.assistant.handle)).one()
    refused = client.put(f"/yorick-imports/{troupe.id}/staff", json={"user_id": str(assistant.id)})
    assert refused.status_code == 422

    storyteller = session.scalars(
        select(User).where(User.handle == troupe.storyteller.handle)
    ).one()
    state = client.put(
        f"/yorick-imports/{troupe.id}/staff", json={"user_id": str(storyteller.id)}
    ).json()
    assert state["staff_id"] == str(storyteller.id)
    assert [s["lead"] for s in state["staff"]] == [True, False]

    uploaded(troupe)
    import_now(troupe)

    assert {c.player_id for c in imported(session).values()} == {storyteller.id}


# --- characters here under a printed name ---------------------------------------------------


def test_a_character_here_under_a_printed_name_waits_for_a_choice(
    troupe: Troupe, session: Session, kept: Path
) -> None:
    client = troupe.custodian.client
    made = troupe.lead.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "agnes  wren"})
    assert made.status_code == 201, made.text
    npc_id = made.json()["id"]
    pc_id = new_character(troupe, troupe.player, "Thaddeus Ashby")
    session.get_one(Character, uuid.UUID(pc_id)).building_troupe_id = uuid.UUID(troupe.id)
    session.commit()

    state = uploaded(troupe)

    assert state["undecided"] == 2
    assert state["cannot_import"].startswith("2 printed characters share a name")
    found = by_name(report(troupe))
    assert found["Agnes Wren"]["outcome"] == "undecided"
    assert found["Agnes Wren"]["matches"] == [
        {
            "character_id": npc_id,
            "name": "agnes  wren",
            "whose": "an NPC of the troupe",
            "overwritable": True,
        }
    ]
    assert found["Thaddeus Ashby"]["matches"][0]["whose"] == f"@{troupe.player.handle}'s character"
    assert found["Thaddeus Ashby"]["matches"][0]["overwritable"] is False
    assert any("Waiting for a choice" in line for line in report(troupe)["summary"])

    # A player's character can't be overwritten: it changes through approvals.
    refused = client.put(
        f"/yorick-imports/{troupe.id}/decisions/Th4ddAshby",
        json={"choice": "overwrite", "character_id": pc_id},
    )
    assert refused.status_code == 422
    client.put(f"/yorick-imports/{troupe.id}/decisions/Th4ddAshby", json={"choice": "skip"})
    state = client.put(
        f"/yorick-imports/{troupe.id}/decisions/aGnEsWr3n1",
        json={"choice": "overwrite", "character_id": npc_id},
    ).json()
    assert state["report_stale"] is True
    assert {d["legacy_id"]: d["choice"] for d in state["decisions"]} == {
        "aGnEsWr3n1": "overwrite",
        "Th4ddAshby": "skip",
    }

    state = dry_run(troupe)
    assert state["undecided"] == 0 and state["cannot_import"] is None
    found = by_name(report(troupe))
    assert found["Agnes Wren"]["outcome"] == "overwritten"
    assert found["Thaddeus Ashby"]["outcome"] == "skipped"

    import_now(troupe)

    session.expire_all()
    npc = session.get_one(Character, uuid.UUID(npc_id))
    assert (npc.name, npc.legacy_id) == ("Agnes Wren", "aGnEsWr3n1")
    held = {r.key: r.trait.rating for r in sheets.sheet_rows(session, npc)}
    assert held[("attributes", "Mental", "")] == 7
    assert session.get_one(Character, uuid.UUID(pc_id)).legacy_id is None
    assert sorted(imported(session)) == ["Agnes Wren", "Mystery Woman"]
    assert session.scalar(select(func.count()).where(AuditEvent.action == "npc.imported_over")) == 1


def test_a_character_imported_beside_one_of_the_same_name(
    troupe: Troupe, session: Session, kept: Path
) -> None:
    made = troupe.lead.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Mystery Woman"})
    npc_id = made.json()["id"]
    session.commit()
    uploaded(troupe)
    legacy = by_name(report(troupe))["Mystery Woman"]["legacy_id"]

    troupe.custodian.client.put(
        f"/yorick-imports/{troupe.id}/decisions/{legacy}", json={"choice": "new"}
    )
    dry_run(troupe)
    import_now(troupe)

    names = session.scalars(select(Character.name).where(Character.name == "Mystery Woman"))
    assert len(names.all()) == 2
    assert session.get_one(Character, uuid.UUID(npc_id)).legacy_id is None


@pytest.mark.usefixtures("kept")
def test_a_choice_is_only_for_a_printed_character_sharing_a_name(troupe: Troupe) -> None:
    uploaded(troupe)

    response = troupe.custodian.client.put(
        f"/yorick-imports/{troupe.id}/decisions/aGnEsWr3n1", json={"choice": "skip"}
    )

    assert response.status_code == 404


# --- keeping the page no longer than needed ------------------------------------------------


def test_the_page_and_report_can_be_deleted(troupe: Troupe, session: Session, kept: Path) -> None:
    uploaded(troupe)
    troupe.custodian.client.put(
        f"/yorick-imports/{troupe.id}/by-hand",
        json={"source": "Backgrounds: Influences x1", "by_hand": True},
    )

    state = troupe.custodian.client.delete(f"/yorick-imports/{troupe.id}/page").json()

    assert state["page"] is None and state["report_kind"] is None
    # What the troupe has worked out stays for the next upload.
    assert state["by_hand"] == ["Backgrounds: Influences x1"]
    assert not (kept / "uploads" / "yorick-imports" / troupe.id).exists()
    assert troupe.custodian.client.get(f"/yorick-imports/{troupe.id}/report").status_code == 404
    assert (
        session.scalar(select(func.count()).where(AuditEvent.action == "yorick_import.deleted"))
        == 1
    )


def test_a_page_and_report_are_deleted_after_thirty_days(
    troupe: Troupe, session: Session, kept: Path
) -> None:
    uploaded(troupe)

    assert yorick_imports.expire_due(session, datetime.now(UTC) + timedelta(days=29)) == 0
    assert yorick_imports.expire_due(session, datetime.now(UTC) + timedelta(days=31)) == 1

    record = session.scalars(select(YorickImport)).one()
    assert record.page_name is None and record.report is None
    assert not (kept / "uploads" / "yorick-imports" / troupe.id).exists()


@pytest.mark.usefixtures("kept")
def test_a_job_lost_in_a_restart_is_reported(troupe: Troupe, session: Session) -> None:
    uploaded(troupe)
    record = session.scalars(select(YorickImport)).one()
    record.job, record.job_at = "import", datetime.now(UTC)
    session.commit()

    state = troupe.custodian.client.get(f"/yorick-imports/{troupe.id}").json()

    assert state["job"] is None
    assert state["error"] == "The import stopped when the server restarted; nothing was saved."


@pytest.mark.usefixtures("kept")
def test_one_job_at_a_time(troupe: Troupe, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[Callable[[], None]] = []
    monkeypatch.setattr(yorick_imports, "launch", started.append)
    uploaded(troupe)
    state = troupe.custodian.client.get(f"/yorick-imports/{troupe.id}").json()
    assert state["job"]["kind"] == "dry_run"
    assert state["cannot_import"] == "A dry run or import is running."

    for response in (
        troupe.custodian.client.post(f"/yorick-imports/{troupe.id}/dry-run"),
        upload(troupe.custodian, troupe, saved_page()),
        troupe.custodian.client.delete(f"/yorick-imports/{troupe.id}/page"),
    ):
        assert response.status_code == 409

    started[0]()
    state = troupe.custodian.client.get(f"/yorick-imports/{troupe.id}").json()
    assert state["job"] is None and state["report_kind"] == "dry_run"


@pytest.mark.usefixtures("kept")
def test_the_troupes_under_way_are_listed(troupe: Troupe) -> None:
    assert troupe.custodian.client.get("/yorick-imports").json() == []
    uploaded(troupe)

    listed = troupe.custodian.client.get("/yorick-imports").json()

    assert [(i["troupe_name"], i["report_kind"], i["running"]) for i in listed] == [
        ("Lords of the Night", "dry_run", False)
    ]

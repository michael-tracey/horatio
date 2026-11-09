"""Backing up characters (issue #567): exporting one, or many as a .zip, and importing
one as a new character, reviewed first."""

import io
import json
import uuid
import zipfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.character_backup import file_stem, name_part
from horatio.models import BackstoryFeedback, Diablerie
from horatio.rules.model import CostRuleData
from horatio.rules.store import add_house_rule
from tests.api_helpers import Person, Troupe, finish, new_character, sign_up
from tests.test_api_creation import pick
from tests.test_api_home_troupe import buy, request_home
from tests.test_api_pictures import kept, photo, upload  # noqa: F401
from tests.test_api_troupe_equipment import DAGGER, given

# Balances here are about what comes across, not banking creation XP.
pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def heir(client_for: Callable[[], TestClient]) -> Person:
    """Someone else, who imports a character from a file they were given."""
    return sign_up(client_for, "heir")


def built(troupe: Troupe, player: Person, name: str = "Agnes") -> str:
    """A Brujah with creation picks placed and XP spent, and a backstory."""
    character_id = new_character(troupe, player, name, finished=False, clan="Brujah")
    placed = pick(player, character_id, "skills", "Brawl", 4)
    assert placed.status_code == 200, placed.text
    finish(troupe, character_id)
    buy(player, character_id, "disciplines", "Celerity", 2)
    buy(player, character_id, "skills", "Occult", 1)
    saved = player.client.put(
        f"/characters/{character_id}/backstory",
        json={"text": "## Before\n\nShe kept the lighthouse.", "version": 0},
    )
    assert saved.status_code == 200, saved.text
    return character_id


def exported(person: Person, character_id: str, *sections: str) -> dict[str, Any]:
    response = person.client.get(
        f"/characters/{character_id}/backup", params={"sections": list(sections)}
    )
    assert response.status_code == 200, response.text
    return response.json()


def review(person: Person, document: dict[str, Any], troupe_id: str | None = None) -> Any:
    return person.client.post(
        "/characters/import/review", json={"document": document, "troupe_id": troupe_id}
    )


def reviewed(person: Person, document: dict[str, Any], troupe_id: str | None = None) -> Any:
    response = review(person, document, troupe_id)
    assert response.status_code == 200, response.text
    return response.json()


def imported(person: Person, document: dict[str, Any], troupe_id: str | None = None) -> str:
    response = person.client.post(
        "/characters/import",
        json={"document": document, "troupe_id": troupe_id, "file_name": "agnes.json"},
    )
    assert response.status_code == 201, response.text
    character_id: str = response.json()["character_id"]
    return character_id


def sheet(person: Person, character_id: str) -> list[tuple[Any, ...]]:
    traits = person.client.get(f"/characters/{character_id}/sheet").json()["traits"]
    return sorted(
        (t["category"], t["name"], t["detail"], t["rating"], t["free_rating"]) for t in traits
    )


def xp(person: Person, character_id: str) -> list[dict[str, Any]]:
    response = person.client.get(f"/characters/{character_id}/xp")
    assert response.status_code == 200, response.text
    return response.json()


def items(found: dict[str, Any], status: str) -> list[str]:
    return [i["label"] for p in found["parts"] for i in p["items"] if i["status"] == status]


# --- file names ---------------------------------------------------------------------------


def test_a_backup_is_named_for_the_character_and_the_day() -> None:
    assert file_stem("Agnes de Vries", date(2026, 11, 9)) == "AgnesdeVries-2026-11-09"


@pytest.mark.parametrize(
    ("name", "part"),
    [
        ("Agnes de Vries", "AgnesdeVries"),
        ("Zoë Brontë-Ågren", "ZoeBronte-Agren"),
        ("Ślęża Łódź", "Slezaodz"),
        ("Ναταλία", "character"),
        ("伊藤 光", "character"),
        ('O\'Brien, "Red" / Jr.?', "OBrienRedJr"),
        ("con:sole*<>|", "console"),
        ("   ", "character"),
    ],
)
def test_a_names_file_part_folds_accents_and_drops_the_rest(name: str, part: str) -> None:
    assert name_part(name) == part


# --- exporting ----------------------------------------------------------------------------


def test_a_character_exports_with_its_sheet_free_dots_history_and_backstory(
    troupe: Troupe,
) -> None:
    agnes = built(troupe, troupe.player)

    document = exported(troupe.player, agnes)

    assert (document["format"], document["version"]) == ("horatio-character", 1)
    assert document["character"]["name"] == "Agnes"
    brawl = next(t for t in document["traits"] if t["name"] == "Brawl")
    assert (brawl["rating"], brawl["free_rating"], brawl["creation_pick"]) == (4, 4, 4)
    celerity = next(t for t in document["traits"] if t["name"] == "Celerity")
    assert (celerity["rating"], celerity["free_rating"]) == (2, 0)
    assert celerity["paid"] > 0
    purchases = [line for line in document["xp"] if line["kind"] == "purchase"]
    assert {line["trait"]["name"] for line in purchases} == {"Celerity", "Occult"}
    assert document["backstory"] == "## Before\n\nShe kept the lighthouse."
    # No ids anywhere: traits and lines are named.
    text = json.dumps(document)
    assert agnes not in text
    assert "_id" not in text


def test_the_optional_sections_come_only_when_chosen(troupe: Troupe) -> None:
    from tests.test_api_downtimes import member_character

    agnes = member_character(troupe, troupe.player, "Agnes")
    given(troupe, agnes, **DAGGER)

    assert exported(troupe.player, agnes)["equipment"] == []
    document = exported(troupe.player, agnes, "equipment")
    assert [i["name"] for i in document["equipment"]] == ["Silver Dagger"]
    assert document["sections"] == ["equipment"]


def test_a_players_export_holds_no_staff_notes(troupe: Troupe) -> None:
    from tests.test_api_downtimes import member_character

    agnes = member_character(troupe, troupe.player, "Agnes")
    given(troupe, agnes, **DAGGER, staff_note="STAFF-ONLY-ITEM")
    character_id = uuid.UUID(agnes)
    troupe.session.add(
        Diablerie(
            character_id=character_id,
            troupe_id=uuid.UUID(troupe.id),
            committed_on=date(2026, 10, 1),
            victim="STAFF-ONLY-VICTIM",
            note="STAFF-ONLY-DIABLERIE",
            requested_by=uuid.UUID(troupe.lead.id),
        )
    )
    troupe.session.add(
        BackstoryFeedback(
            character_id=character_id,
            troupe_id=uuid.UUID(troupe.id),
            author_id=uuid.UUID(troupe.lead.id),
            kind="feedback",
            body="STAFF-ONLY-FEEDBACK",
        )
    )
    troupe.session.flush()
    # Another player's character in the same troupe stays out of it.
    other = sign_up(troupe.client_for, "other")
    new_character(troupe, other, "Bartholomew")

    document = exported(troupe.player, agnes, "equipment", "retainers", "titles")
    sheet_page = troupe.player.client.get(f"/characters/{agnes}/backup/sheet")
    everything = troupe.player.client.get("/character-backups", params={"sections": ["equipment"]})

    assert sheet_page.status_code == 200
    assert everything.status_code == 200
    with zipfile.ZipFile(io.BytesIO(everything.content)) as archive:
        zipped = " ".join(archive.read(n).decode() for n in archive.namelist())
    for text in (json.dumps(document), sheet_page.text, zipped):
        assert "STAFF-ONLY" not in text
        assert "Bartholomew" not in text
        assert troupe.lead.email not in text
    assert [i["name"] for i in document["equipment"]] == ["Silver Dagger"]


def test_only_its_player_exports_a_character(troupe: Troupe, heir: Person) -> None:
    agnes = built(troupe, troupe.player)

    assert heir.client.get(f"/characters/{agnes}/backup").status_code == 404
    assert heir.client.get(f"/characters/{agnes}/backup/sheet").status_code == 404


def test_a_retired_character_can_still_be_exported(troupe: Troupe) -> None:
    agnes = built(troupe, troupe.player)
    retired = troupe.player.client.post(
        f"/characters/{agnes}/retire", json={"reason": "final_death", "listed": True}
    )
    assert retired.status_code == 200, retired.text

    document = exported(troupe.player, agnes)

    assert document["character"]["retired"] is True
    assert document["character"]["left_reason"] == "final_death"


def test_the_printable_sheet_is_an_html_file(troupe: Troupe) -> None:
    agnes = built(troupe, troupe.player)

    response = troupe.player.client.get(f"/characters/{agnes}/backup/sheet")

    assert response.headers["content-type"].startswith("text/html")
    assert f'filename="Agnes-{date.today()}.html"' in response.headers["content-disposition"]
    assert "<h1>Agnes</h1>" in response.text
    assert "Celerity" in response.text


def test_export_all_is_a_zip_of_the_players_characters(troupe: Troupe) -> None:
    built(troupe, troupe.player, "Agnes")
    built(troupe, troupe.player, "Agnes")
    new_character(troupe, troupe.storyteller, "Not theirs")

    response = troupe.player.client.get("/character-backups")

    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = sorted(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
    on = date.today()
    assert names == [
        f"characters/Agnes-{on}-2.horatio-character.json",
        f"characters/Agnes-{on}.horatio-character.json",
        "manifest.json",
        f"sheets/Agnes-{on}-2.html",
        f"sheets/Agnes-{on}.html",
    ]
    assert manifest["format"] == "horatio-character-backup"
    assert [c["name"] for c in manifest["characters"]] == ["Agnes", "Agnes"]


def test_a_troupe_exports_its_own_characters_and_npcs(troupe: Troupe) -> None:
    from tests.test_api_downtimes import member_character
    from tests.test_api_npc_gifts import built as npc

    member_character(troupe, troupe.player, "Agnes")
    npc(troupe, "Lucien")
    # A character only visiting stays with its home troupe.
    visitor = new_character(troupe, troupe.stranger, "Visitor")
    troupe.stranger.client.post(f"/characters/{visitor}/troupes", json={"troupe_id": troupe.id})
    path = f"/troupes/{troupe.id}/character-backups"

    response = troupe.assistant.client.get(path)

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        agnes = json.loads(archive.read(f"characters/Agnes-{date.today()}.horatio-character.json"))
        lucien = json.loads(archive.read(f"npcs/Lucien-{date.today()}.horatio-character.json"))
    assert manifest["troupe"] == "Lords of the Night"
    assert [(c["name"], c["kind"]) for c in manifest["characters"]] == [
        ("Lucien", "npc"),
        ("Agnes", "pc"),
    ]
    # Handles only, unless storytellers ask for emails.
    assert agnes["player"] == {"handle": troupe.player.handle, "email": None, "name": "player"}
    assert lucien["character"]["npc_kind"] == "vampire"
    assert manifest["emails"] is False

    pcs = troupe.assistant.client.get(path, params={"which": "pcs"})
    with zipfile.ZipFile(io.BytesIO(pcs.content)) as archive:
        assert [c["name"] for c in json.loads(archive.read("manifest.json"))["characters"]] == [
            "Agnes"
        ]

    assert troupe.assistant.client.get(path, params={"emails": True}).status_code == 403
    with_emails = troupe.storyteller.client.get(path, params={"emails": True})
    with zipfile.ZipFile(io.BytesIO(with_emails.content)) as archive:
        agnes = json.loads(archive.read(f"characters/Agnes-{date.today()}.horatio-character.json"))
    assert agnes["player"]["email"] == troupe.player.email

    assert troupe.narrator.client.get(path).status_code == 403
    assert troupe.player.client.get(path).status_code == 403
    selected = troupe.assistant.client.get(path, params={"characters": [visitor]})
    assert selected.status_code == 404


# --- importing ----------------------------------------------------------------------------


def test_a_round_trip_gives_the_same_sheet_free_dots_history_and_backstory(
    troupe: Troupe, heir: Person
) -> None:
    agnes = built(troupe, troupe.player)
    document = exported(troupe.player, agnes)

    found = reviewed(heir, document)
    copy = imported(heir, document)

    assert items(found, "cannot") == []
    assert items(found, "differs") == []
    assert sheet(heir, copy) == sheet(troupe.player, agnes)
    assert exported(heir, copy)["traits"] == document["traits"]
    # Its XP balances as it did, the XP earned now self-entered for a troupe to decide on.
    before, after = xp(troupe.player, agnes), xp(heir, copy)
    assert sum(e["amount"] for e in after) == sum(e["amount"] for e in before)
    earned = sum(e["amount"] for e in before if e["kind"] in ("award", "self_entered"))
    assert sum(e["amount"] for e in after if e["kind"] == "self_entered") == earned
    assert found["xp"]["self_entered"] == earned
    assert found["xp"]["sheet_there"] == found["xp"]["sheet_here"]
    paid = {e["trait"]: -e["amount"] for e in after if e["kind"] == "purchase"}
    assert paid == {
        t["name"]: t["paid"] for t in document["traits"] if t["paid"] and t["category"] != "clan"
    }
    assert heir.client.get(f"/characters/{copy}/backstory").json()["text"] == document["backstory"]
    character = heir.client.get(f"/characters/{copy}").json()
    assert (character["player_id"], character["home_troupe_id"]) == (heir.id, None)
    assert character["creation_complete"] is True
    # The review saved nothing; the import made one character.
    assert [c["name"] for c in heir.client.get("/characters").json()] == ["Agnes"]


def test_a_troupe_with_other_prices_sees_both_and_nothing_is_repriced(
    troupe: Troupe, heir: Person
) -> None:
    agnes = built(troupe, troupe.player)
    document = exported(troupe.player, agnes)
    add_house_rule(
        troupe.session,
        uuid.UUID(troupe.id),
        "vampire",
        CostRuleData("skills", "per_dot", rate=5, condition={"generation": 1}),
    )

    found = reviewed(heir, document, troupe.id)
    copy = imported(heir, document, troupe.id)

    assert found["troupe"] == "Lords of the Night"
    assert found["xp"]["sheet_here"] > found["xp"]["sheet_there"]
    occult = next(t for t in document["traits"] if t["name"] == "Occult")
    entries = xp(heir, copy)
    assert [-e["amount"] for e in entries if e["trait"] == "Occult"] == [occult["paid"]]
    # Asking the troupe to make it home sets what was paid against its prices.
    settled = [{"category": "skills", "name": "Occult", "settlement": "keep_price"}]
    asked = request_home(heir, copy, troupe.id, settled)
    assert asked.status_code == 201, asked.text
    queue = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()
    asking = next(a for a in queue if a["character_id"] == copy)
    assert asking["xp"]["self_entered"] == found["xp"]["self_entered"]
    differences = {r["trait"]: r for r in asking["reconciliation"]}
    assert differences["Occult"]["old_cost"] == occult["paid"]
    assert differences["Occult"]["new_cost"] == 5


def test_a_trait_this_troupe_lacks_cant_be_imported_and_says_why(
    troupe: Troupe, heir: Person
) -> None:
    agnes = built(troupe, troupe.player)
    document = exported(troupe.player, agnes)
    document["traits"].append({"category": "merits", "name": "Lucky Hat", "rating": 1, "paid": 1})
    document["traits"].append(
        {"category": "merits", "name": "Court Favourite", "rating": 2, "house": True}
    )
    document["troupe"] = "Night Court"

    found = reviewed(heir, document)
    copy = imported(heir, document)

    cannot = {
        i["label"]: i["reason"]
        for p in found["parts"]
        for i in p["items"]
        if i["status"] == "cannot"
    }
    assert cannot["Merits: Lucky Hat"] == "There is no merits trait called 'Lucky Hat'."
    assert cannot["Merits: Court Favourite"].startswith("A house merit of Night Court")
    assert "Lucky Hat" not in [t[1] for t in sheet(heir, copy)]
    # What it cost there comes back unspent.
    before = sum(e["amount"] for e in xp(troupe.player, agnes))
    assert sum(e["amount"] for e in xp(heir, copy)) == before + 1


def test_a_file_from_a_newer_horatio_is_refused(troupe: Troupe, heir: Person) -> None:
    document = exported(troupe.player, built(troupe, troupe.player))
    document["version"] = 2

    response = review(heir, document)

    assert response.status_code == 422
    assert "newer Horatio" in response.json()["detail"]


def test_something_else_is_refused(heir: Person) -> None:
    response = review(heir, {"format": "horatio-troupe-settings", "version": 1})

    assert response.status_code == 422
    assert response.json()["detail"].startswith("That file isn't a Horatio character")


def test_free_dots_cant_pass_the_rating(troupe: Troupe, heir: Person) -> None:
    document = exported(troupe.player, built(troupe, troupe.player))
    document["traits"][0]["free_rating"] = 99

    response = review(heir, document)

    assert response.status_code == 422
    assert "can't be read" in response.json()["detail"]


def test_its_self_entered_xp_is_kept_or_removed_as_it_joins(troupe: Troupe, heir: Person) -> None:
    agnes = built(troupe, troupe.player)
    copy = imported(heir, exported(troupe.player, agnes))
    asked = request_home(heir, copy, troupe.id)
    assert asked.status_code == 201, asked.text

    removed = troupe.lead.client.post(
        f"/approvals/{asked.json()['id']}/approve",
        json={"xp": {"self_entered": "remove"}, "note": ""},
    )

    assert removed.status_code == 200, removed.text
    entries = xp(heir, copy)
    gives = sum(
        e["corrected_to"] if e["corrected_to"] is not None else e["amount"]
        for e in entries
        if e["kind"] == "self_entered"
    )
    assert gives == 0


def test_the_import_is_in_its_log(troupe: Troupe, heir: Person) -> None:
    copy = imported(heir, exported(troupe.player, built(troupe, troupe.player)))

    log = heir.client.get(f"/characters/{copy}/log")

    assert log.status_code == 200, log.text
    assert [e["message"] for e in log.json() if e["action"] == "character.imported"] == [
        f"heir imported Agnes from a backup file exported outside any troupe on {date.today()};"
        " parts left out: 0."
    ]


def test_its_picture_comes_with_it(
    troupe: Troupe,
    heir: Person,
    kept: Path,  # noqa: F811
) -> None:
    agnes = built(troupe, troupe.player)
    uploaded = upload(troupe.player, agnes, photo((300, 200)), x=0.1, y=0.0, size=0.5)
    assert uploaded.status_code == 200, uploaded.text
    document = exported(troupe.player, agnes)
    assert document["picture"]["data"]

    copy = imported(heir, document)

    picture = heir.client.get(f"/characters/{copy}/picture").json()
    assert picture["picture"] is not None
    assert picture["crop"] == pytest.approx(document["picture"]["crop"], abs=0.01)
    everything = troupe.player.client.get("/character-backups")
    with zipfile.ZipFile(io.BytesIO(everything.content)) as archive:
        assert f"pictures/Agnes-{date.today()}.webp" in archive.namelist()
        inside = json.loads(archive.read(f"characters/Agnes-{date.today()}.horatio-character.json"))
    assert inside["picture"]["file"] == f"pictures/Agnes-{date.today()}.webp"
    assert inside["picture"]["data"] is None


def test_a_stock_npc_cant_become_a_players_character(troupe: Troupe, heir: Person) -> None:
    document = exported(troupe.player, built(troupe, troupe.player))
    document["character"].update(kind="npc", npc_kind="vampire", npc_form="stock")

    response = review(heir, document)

    assert response.status_code == 422
    assert "can't be a player's character" in response.json()["detail"]

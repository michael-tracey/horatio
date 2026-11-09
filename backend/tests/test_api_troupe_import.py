"""Importing characters by the batch (issue #567): a troupe's staff bring in a troupe's
export, matching player characters to their players, and a player imports the .zip
of their characters."""

import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, backstory_optional, sign_up
from tests.test_api_character_backup import built, exported, sheet
from tests.test_api_downtimes import member_character
from tests.test_api_npc_gifts import built as npc
from tests.test_api_pictures import kept, photo, upload  # noqa: F401

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def other(troupe: Troupe, session: Session) -> str:
    """A second troupe, led by the first's storyteller, to import into."""
    made = troupe.custodian.client.post(
        "/troupes", json={"name": "Court of Echoes", "lead_handle": troupe.storyteller.handle}
    )
    assert made.status_code == 201, made.text
    troupe_id: str = made.json()["id"]
    backstory_optional(session, troupe_id)
    return troupe_id


def troupe_zip(troupe: Troupe, **params: Any) -> bytes:
    response = troupe.storyteller.client.get(
        f"/troupes/{troupe.id}/character-backups", params=params
    )
    assert response.status_code == 200, response.text
    return response.content


def rezip(content: bytes, change: Callable[[str, dict[str, Any]], None]) -> bytes:
    """The zip with each character file changed by `change`."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name.endswith(".horatio-character.json"):
                document = json.loads(data)
                change(name, document)
                data = json.dumps(document).encode()
            target.writestr(name, data)
    return out.getvalue()


def post(
    person: Person,
    path: str,
    content: bytes,
    name: str = "backup.zip",
    **form: Any,
) -> Any:
    data = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in form.items()}
    return person.client.post(
        path, files=[("files", (name, content, "application/zip"))], data=data
    )


def keyed(content: bytes, by_name: dict[str, Any]) -> dict[str, Any]:
    """What staff chose, by each file's key in the zip rather than its character's name."""
    keys: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for name in archive.namelist():
            try:
                keys[json.loads(archive.read(name))["character"]["name"]] = name
            except (ValueError, KeyError, TypeError):
                continue
    return {keys[name]: decision for name, decision in by_name.items()}


def review(person: Person, troupe_id: str, content: bytes, **decisions: Any) -> dict[str, Any]:
    response = post(
        person,
        f"/troupes/{troupe_id}/character-imports/review",
        content,
        decisions=keyed(content, decisions),
    )
    assert response.status_code == 200, response.text
    return response.json()


def run(person: Person, troupe_id: str, content: bytes, **decisions: Any) -> Any:
    return post(
        person,
        f"/troupes/{troupe_id}/character-imports",
        content,
        decisions=keyed(content, decisions),
    )


def by_name(found: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["name"]: e for e in found["entries"]}


def characters_of(person: Person, troupe_id: str) -> list[tuple[str, str]]:
    roster = person.client.get(f"/troupes/{troupe_id}/characters")
    assert roster.status_code == 200, roster.text
    return sorted((e["character_name"], e["kind"]) for e in roster.json())


def test_a_troupes_export_comes_into_another_troupe(troupe: Troupe, other: str) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    lucien = npc(troupe, "Lucien")
    content = troupe_zip(troupe)

    found = review(troupe.storyteller, other, content)

    entries = by_name(found)
    assert found["can_give"] is True
    assert entries["Lucien"]["outcome"] == "new"
    assert entries["Lucien"]["kind"] == "npc"
    # Matched by the handle in the file, and given to them at once.
    assert entries["Agnes"]["outcome"] == "given"
    assert entries["Agnes"]["matched_by"] == "handle"
    assert entries["Agnes"]["player"]["handle"] == troupe.player.handle
    assert entries["Agnes"]["file_player"] == f"@{troupe.player.handle} (player)"
    assert entries["Agnes"]["review"]["parts"]
    # The review saved nothing.
    assert characters_of(troupe.storyteller, other) == []

    done = run(troupe.storyteller, other, content, Agnes={})
    assert done.status_code == 201, done.text
    entries = by_name(done.json())
    copy = entries["Agnes"]["character_id"]
    character = troupe.player.client.get(f"/characters/{copy}").json()
    assert (character["player_id"], character["home_troupe_id"]) == (troupe.player.id, other)
    assert character["kind"] == "pc"
    assert sheet(troupe.player, copy) == sheet(troupe.player, agnes)
    new_npc = entries["Lucien"]["character_id"]
    assert sheet(troupe.storyteller, new_npc) == sheet(troupe.storyteller, lucien)
    assert characters_of(troupe.storyteller, other) == [("Agnes", "pc"), ("Lucien", "npc")]
    log = troupe.storyteller.client.get(f"/troupes/{other}/log").json()
    assert any(e["action"] == "npc.imported_from_backup" and "Lucien" in e["message"] for e in log)


def test_unspent_xp_carries_over_only_as_staff_choose(troupe: Troupe, other: str) -> None:
    member_character(troupe, troupe.player, "Agnes")

    def banked(_: str, document: dict[str, Any]) -> None:
        document["xp"].append(
            {"kind": "award", "amount": 12, "reason": "Game night", "on": "2026-10-01"}
        )

    before = by_name(review(troupe.storyteller, other, troupe_zip(troupe)))["Agnes"]["unspent"]
    content = rezip(troupe_zip(troupe), banked)
    found = by_name(review(troupe.storyteller, other, content))
    assert (found["Agnes"]["unspent"], found["Agnes"]["carried_xp"]) == (before + 12, 0)

    done = run(troupe.storyteller, other, content, Agnes={"carried_xp": 10})
    assert done.status_code == 201, done.text
    copy = by_name(done.json())["Agnes"]["character_id"]
    lines = troupe.player.client.get(f"/characters/{copy}/xp").json()
    carried = [e for e in lines if e["reason"].startswith("Unspent XP carried over")]
    assert [e["amount"] for e in carried] == [10]


def test_a_player_is_found_by_email_and_staff_can_choose_another(
    troupe: Troupe, other: str, client_for: Callable[[], TestClient]
) -> None:
    member_character(troupe, troupe.player, "Agnes")
    member_character(troupe, troupe.stranger, "Bertrand")
    newcomer = sign_up(client_for, "newcomer")

    def renamed(_: str, document: dict[str, Any]) -> None:
        # Another Horatio's handles: only the email finds Agnes's player here.
        if document["character"]["name"] == "Agnes":
            document["player"]["handle"] = "someone_else_entirely"
        else:
            document["player"] = {"handle": "nobody_by_this_name", "email": None, "name": ""}

    content = rezip(troupe_zip(troupe, emails=True), renamed)
    found = by_name(review(troupe.storyteller, other, content))
    assert (found["Agnes"]["outcome"], found["Agnes"]["matched_by"]) == ("given", "email")
    # Found by neither, it is held as an NPC to give later.
    assert (found["Bertrand"]["outcome"], found["Bertrand"]["player"]) == ("held", None)

    chosen = by_name(
        review(
            troupe.storyteller,
            other,
            content,
            Agnes={"player": ""},
            Bertrand={"player": newcomer.handle},
        )
    )
    assert chosen["Agnes"]["outcome"] == "held"
    assert (chosen["Bertrand"]["outcome"], chosen["Bertrand"]["matched_by"]) == (
        "given",
        "chosen",
    )
    unknown = by_name(review(troupe.storyteller, other, content, Agnes={"player": "no_such_one"}))
    assert unknown["Agnes"]["outcome"] == "cannot"
    assert unknown["Agnes"]["problem"] == "Nobody has the handle no_such_one."


def test_a_character_with_the_name_of_one_here_waits_for_staff_to_choose(
    troupe: Troupe,
) -> None:
    lucien = npc(troupe, "Lucien")
    content = troupe_zip(troupe, which="npcs")

    found = by_name(review(troupe.storyteller, troupe.id, content))
    assert found["Lucien"]["outcome"] == "undecided"
    assert found["Lucien"]["duplicate"]["character_id"] == lucien
    assert found["Lucien"]["can_replace"] is True
    refused = run(troupe.storyteller, troupe.id, content)
    assert refused.status_code == 409
    assert "Lucien" in refused.json()["detail"]

    assert by_name(review(troupe.storyteller, troupe.id, content, Lucien={"choice": "skip"}))[
        "Lucien"
    ]["outcome"] == ("skipped")

    # Replaced, the NPC stays itself, its sheet as the file has it.
    changed = troupe.storyteller.client.put(
        f"/characters/{lucien}/npc/ratings",
        json={"category": "skills", "name": "Occult", "rating": 3},
    )
    assert changed.status_code == 200, changed.text
    done = run(troupe.storyteller, troupe.id, content, Lucien={"choice": "replace"})
    assert done.status_code == 201, done.text
    assert by_name(done.json())["Lucien"]["outcome"] == "replaced"
    assert by_name(done.json())["Lucien"]["character_id"] == lucien
    assert "Occult" not in [t[1] for t in sheet(troupe.storyteller, lucien)]

    copied = run(troupe.storyteller, troupe.id, content, Lucien={"choice": "copy"})
    assert copied.status_code == 201, copied.text
    assert characters_of(troupe.storyteller, troupe.id) == [("Lucien", "npc"), ("Lucien", "npc")]


def test_a_players_character_here_is_never_replaced(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    content = troupe_zip(troupe, which="pcs")

    found = by_name(review(troupe.storyteller, troupe.id, content))
    assert found["Agnes"]["duplicate"]["character_id"] == agnes
    assert found["Agnes"]["can_replace"] is False
    # Asked to, it still waits to be skipped or copied.
    replace = by_name(review(troupe.storyteller, troupe.id, content, Agnes={"choice": "replace"}))
    assert replace["Agnes"]["outcome"] == "undecided"


def test_assistants_hold_every_player_character(troupe: Troupe, other: str) -> None:
    member_character(troupe, troupe.player, "Agnes")
    content = troupe_zip(troupe, which="pcs")

    found = review(troupe.assistant, troupe.id, content, Agnes={"choice": "copy"})
    assert found["can_give"] is False
    assert by_name(found)["Agnes"]["outcome"] == "held"
    asked = post(
        troupe.assistant,
        f"/troupes/{troupe.id}/character-imports/review",
        content,
        decisions=keyed(content, {"Agnes": {"player": troupe.player.handle}}),
    )
    assert asked.status_code == 403
    assert (
        post(troupe.narrator, f"/troupes/{troupe.id}/character-imports/review", content).status_code
        == 403
    )
    assert (
        post(troupe.player, f"/troupes/{other}/character-imports/review", content).status_code
        == 403
    )


def test_a_retired_character_comes_in_retired(troupe: Troupe, other: str) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    retired = troupe.player.client.post(
        f"/characters/{agnes}/retire", json={"reason": "final_death", "note": "", "listed": False}
    )
    assert retired.status_code == 200, retired.text
    content = troupe_zip(troupe, which="pcs")

    done = run(troupe.storyteller, other, content)

    assert done.status_code == 201, done.text
    entry = by_name(done.json())["Agnes"]
    assert (entry["outcome"], entry["retired"]) == ("given", True)
    character = troupe.player.client.get(f"/characters/{entry['character_id']}").json()
    assert character["status"] == "retired"


def test_a_file_that_cant_be_read_is_listed_and_the_rest_come_in(
    troupe: Troupe, other: str
) -> None:
    npc(troupe, "Lucien")
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(troupe_zip(troupe)), "r") as source,
        zipfile.ZipFile(out, "w") as target,
    ):
        for name in source.namelist():
            target.writestr(name, source.read(name))
        target.writestr("npcs/Broken.horatio-character.json", "{not json")
        target.writestr(
            "npcs/Future.horatio-character.json",
            json.dumps({"format": "horatio-character", "version": 99}),
        )
    found = review(troupe.storyteller, other, out.getvalue())
    problems = {e["key"]: e["problem"] for e in found["entries"] if e["outcome"] == "cannot"}
    assert set(problems) == {
        "npcs/Broken.horatio-character.json",
        "npcs/Future.horatio-character.json",
    }
    assert "newer Horatio" in problems["npcs/Future.horatio-character.json"]
    assert [e["outcome"] for e in found["entries"] if e["name"] == "Lucien"] == ["new"]

    outside = io.BytesIO()
    with zipfile.ZipFile(outside, "w") as target:
        target.writestr("../evil.horatio-character.json", "{}")
    response = post(
        troupe.storyteller, f"/troupes/{other}/character-imports/review", outside.getvalue()
    )
    assert response.status_code == 422
    assert "outside its folder" in response.json()["detail"]


# --- a player's .zip ----------------------------------------------------------------------


def test_a_player_imports_the_zip_of_all_their_characters(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    heir = sign_up(client_for, "heir")
    agnes = built(troupe, troupe.player, "Agnes")
    built(troupe, troupe.player, "Bertrand")
    everything = troupe.player.client.get("/character-backups")
    assert everything.status_code == 200, everything.text

    found = post(heir, "/characters/import/bundle/review", everything.content)
    assert found.status_code == 200, found.text
    entries = {e["name"]: e for e in found.json()["entries"]}
    assert {n: e["outcome"] for n, e in entries.items()} == {"Agnes": "new", "Bertrand": "new"}
    assert heir.client.get("/characters").json() == []

    only = [entries["Agnes"]["key"]]
    done = post(heir, "/characters/import/bundle", everything.content, only=only)
    assert done.status_code == 201, done.text
    outcomes = {e["name"]: e["outcome"] for e in done.json()["entries"]}
    assert outcomes == {"Agnes": "new", "Bertrand": "skipped"}
    mine = heir.client.get("/characters").json()
    assert [c["name"] for c in mine] == ["Agnes"]
    assert sheet(heir, mine[0]["id"]) == sheet(troupe.player, agnes)
    # One file on its own goes too.
    single = json.dumps(exported(troupe.player, agnes)).encode()
    alone = post(heir, "/characters/import/bundle/review", single, name="Agnes.json")
    assert [e["outcome"] for e in alone.json()["entries"]] == ["new"]


def test_each_picture_in_the_zip_comes_with_its_character(
    troupe: Troupe,
    client_for: Callable[[], TestClient],
    kept: Path,  # noqa: F811
) -> None:
    heir = sign_up(client_for, "heir")
    agnes = built(troupe, troupe.player, "Agnes")
    uploaded = upload(troupe.player, agnes, photo((300, 200)), x=0.1, y=0.0, size=0.5)
    assert uploaded.status_code == 200, uploaded.text
    everything = troupe.player.client.get("/character-backups").content

    done = post(heir, "/characters/import/bundle", everything)

    assert done.status_code == 201, done.text
    copy = done.json()["entries"][0]["character_id"]
    assert heir.client.get(f"/characters/{copy}/picture").json()["picture"] is not None

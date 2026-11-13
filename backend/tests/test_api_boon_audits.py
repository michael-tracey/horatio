"""Audits of a character's boons (#690): who makes one (staff, the Harpy with the full
ledger, a Lesser Harpy allowed to), what it holds and leaves out, that it never
changes after it is made, giving it to a player character whose player reads it,
who sees which, and departures shown only as the court knows them (MET: VTM p. 379)."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_boon_harpy import ok
from tests.test_api_boon_talons import Talons
from tests.test_api_boons import named


class Audits(Talons):
    @property
    def audits(self) -> str:
        return f"/troupes/{self.troupe.id}/boon-audits"

    def make(self, character: str, by: Person | None = None, given_to: str | None = None) -> Any:
        return (by or self.troupe.storyteller).client.post(
            self.audits, json={"character_id": character, "given_to_id": given_to}
        )

    def give(self, audit: dict[str, Any], character: str, by: Person | None = None) -> Any:  # type: ignore[override]  # an audit, not a talon
        return (by or self.troupe.storyteller).client.post(
            f"{self.audits}/{audit['id']}/give", json={"character_id": character}
        )

    def read(self, audit: dict[str, Any], by: Person) -> Any:
        return by.client.get(f"/boon-audits/{audit['id']}")

    def retire(self, character: str, player: Person, reason: str, listed: bool) -> None:
        ok(
            player.client.post(
                f"/characters/{character}/retire",
                json={"reason": reason, "note": "", "listed": listed},
            )
        )


@pytest.fixture
def court(client_for: Callable[[], TestClient], session: Session) -> Audits:
    return Audits(Troupe(client_for, session))


def talon_with_audits(court: Audits, **can: bool) -> None:
    ok(court.setting(True))
    # Only the Harpy gives access (#689).
    ok(
        court.harpy_player.client.put(
            f"/troupes/{court.troupe.id}/boon-talons/{court.iris}", json=can
        )
    )


# --- what it holds -------------------------------------------------------------------------


def test_an_audit_lists_what_they_owe_and_are_owed_and_leaves_out_what_staff_alone_see(
    court: Audits,
) -> None:
    court.one(court.agnes, court.bram, kind="major", reason="Discretion", staff_note="Hush.")
    court.one(court.agnes, named("Lucien"), conditions="Notify if traded")
    owed = court.one(court.bram, court.agnes, kind="trivial")
    ok(court.act(owed, "settle", how="called_in", note="At Elysium"))
    court.one(court.vidal, court.agnes, kind="blood")
    voided = court.one(court.agnes, court.vidal)
    ok(court.act(voided, "void", note="Entered twice"))

    made = ok(court.make(court.agnes), 201)

    assert (made["name"], made["standing"], made["made_by"]) == (
        "Agnes",
        "active",
        "The troupe's staff",
    )
    # Standing boons only are counted and weighed (major 3 + minor 1; blood 5).
    assert (made["owes_count"], made["owes_weight"]) == (2, 4.0)
    assert (made["owed_count"], made["owed_weight"]) == (1, 5.0)
    owes = {(line["other"], line["kind"], line["status"]) for line in made["owes"]}
    assert owes == {("Bram", "major", "standing"), ("Lucien", "minor", "standing")}
    settled = [line for line in made["owed"] if line["status"] == "settled"]
    assert [(s["other"], s["settled_how"]) for s in settled] == [("Bram", "called_in")]
    assert any(line["conditions"] == "Notify if traded" for line in made["owes"])
    # No void boon, no staff note, no log.
    assert "Hush." not in str(made)
    assert len(made["owes"]) == 2
    assert "storyteller audited Agnes's boons." in court.messages()


def test_an_audit_stays_as_it_was_when_the_ledger_changes(court: Audits) -> None:
    boon = court.one(court.agnes, court.bram, reason="Discretion")
    made = ok(court.make(court.agnes), 201)

    ok(court.edit(boon, reason="Something else", note="Fixed"))
    ok(court.act(boon, "settle", how="forgiven", note=""))
    court.one(court.agnes, court.bram, kind="life")

    again = ok(court.read(made, court.troupe.storyteller))
    assert [(line["reason"], line["status"]) for line in again["owes"]] == [
        ("Discretion", "standing")
    ]
    assert again["owes_count"] == 1
    fresh = ok(court.make(court.agnes), 201)
    assert fresh["owes_count"] == 1
    assert {line["status"] for line in fresh["owes"]} == {"settled", "standing"}


# --- standing as the court knows it --------------------------------------------------------


def test_departures_show_only_as_the_whos_who_lists_them(court: Audits) -> None:
    court.one(court.agnes, court.bram)
    court.one(court.agnes, court.hugo)
    court.one(court.agnes, court.iris)
    # Bram off-field and listed; Hugo's player stopped (inactive), listed; Iris dead
    # but not listed: as far as the court knows, still about.
    court.retire(court.bram, court.other, "off_field", listed=True)
    court.retire(court.hugo, court.hugo_player, "inactive", listed=True)
    court.retire(court.iris, court.iris_player, "final_death", listed=False)

    made = ok(court.make(court.agnes), 201)

    status = {line["other"]: line["status"] for line in made["owes"]}
    assert status == {"Bram": "departed", "Hugo": "departed", "Iris": "standing"}
    hugo = ok(court.make(court.hugo), 201)
    assert hugo["standing"] == "gone"  # never "inactive"
    assert ok(court.make(court.bram), 201)["standing"] == "off_field"
    assert ok(court.make(court.iris), 201)["standing"] == "active"


def test_an_audit_of_a_retired_character_agrees_with_the_harpy_s_standings(
    court: Audits,
) -> None:
    # One rule (horatio.court_knows, #749): an audit shows each departure as the
    # Harpy's standings do, and never says "inactive".
    court.one(court.bram, court.agnes)
    court.one(court.hugo, court.agnes)
    court.one(court.iris, court.agnes)
    court.retire(court.bram, court.other, "off_field", listed=True)
    court.retire(court.hugo, court.hugo_player, "inactive", listed=True)
    court.retire(court.iris, court.iris_player, "final_death", listed=False)
    ok(
        court.troupe.storyteller.client.put(
            f"/troupes/{court.troupe.id}/boon-harpy", json={"access": "full", "standings": True}
        )
    )
    harpy = court.harpy_player

    audits = {
        name: ok(court.make(character, by=harpy), 201)
        for name, character in (("Bram", court.bram), ("Hugo", court.hugo), ("Iris", court.iris))
    }
    standings = ok(
        harpy.client.get(f"/troupes/{court.troupe.id}/boon-standings", params={"scope": "everyone"})
    )
    theirs = {c["who"]["name"]: c["who"]["standing"] for c in standings["characters"]}

    # The audit's "gone" is the standings' "retired": listed, with no reason told.
    said = {"gone": "retired"}
    assert {n: said.get(a["standing"], a["standing"]) for n, a in audits.items()} == {
        n: theirs[n] for n in audits
    }
    assert {n: a["standing"] for n, a in audits.items()} == {
        "Bram": "off_field",
        "Hugo": "gone",
        "Iris": "active",
    }
    agnes = ok(court.make(court.agnes, by=harpy), 201)
    assert {line["other"]: line["status"] for line in agnes["owed"]} == {
        "Bram": "departed",
        "Hugo": "departed",
        "Iris": "standing",
    }
    assert "inactive" not in json.dumps([*audits.values(), agnes])


# --- who makes one -------------------------------------------------------------------------


def test_staff_the_harpy_with_the_full_ledger_and_lesser_harpies_allowed_to_make_audits(
    court: Audits,
) -> None:
    for person in (court.troupe.player, court.other):
        assert court.make(court.agnes, by=person).status_code in (403, 404)
    # The Harpy below the full ledger can't.
    ok(court.access("submissions"))
    assert court.make(court.agnes, by=court.harpy_player).status_code in (403, 404)
    ok(court.access("full"))
    by_harpy = ok(court.make(court.agnes, by=court.harpy_player), 201)
    assert by_harpy["made_by"] == "Hestia"
    assert "harpy-688 as Hestia audited Agnes's boons." in court.messages()
    # A Lesser Harpy only with the audit permission.
    talon_with_audits(court, can_add=True)
    assert court.make(court.agnes, by=court.iris_player).status_code in (403, 404)
    talon_with_audits(court, can_audit=True)
    assert ok(court.make(court.agnes, by=court.iris_player), 201)["made_by"] == "Iris"
    # Not a character outside the troupe's ledger.
    assert court.make(court.troupe.id, by=court.harpy_player).status_code == 404


def test_the_harpy_sees_audits_made_in_play_and_staff_see_them_all(court: Audits) -> None:
    by_staff = ok(court.make(court.agnes), 201)
    by_harpy = ok(court.make(court.bram, by=court.harpy_player), 201)

    staff = ok(court.troupe.storyteller.client.get(court.audits))
    harpy = ok(court.harpy_player.client.get(court.audits))

    assert {a["id"] for a in staff["audits"]} == {by_staff["id"], by_harpy["id"]}
    assert [a["id"] for a in harpy["audits"]] == [by_harpy["id"]]
    assert court.read(by_staff, court.harpy_player).status_code == 404
    assert harpy["can_audit"] is True
    assert {"Agnes", "Bram"} <= {s["name"] for s in harpy["subjects"]}
    assert "Vidal" not in {r["name"] for r in harpy["recipients"]}


# --- giving one ----------------------------------------------------------------------------


def test_the_harpy_gives_an_audit_to_a_character_whose_player_reads_it(court: Audits) -> None:
    made = ok(court.make(court.bram, by=court.harpy_player), 201)
    assert made["can_give"] is True
    player = court.troupe.player
    assert ok(player.client.get(f"/characters/{court.agnes}/boon-audits")) == []
    assert court.read(made, player).status_code == 404

    given = ok(court.give(made, court.agnes, by=court.harpy_player))

    assert (given["given_to"], given["can_give"]) == ("Agnes", False)
    mine = ok(player.client.get(f"/characters/{court.agnes}/boon-audits"))
    assert [(a["id"], a["name"], a["made_by"]) for a in mine] == [(made["id"], "Bram", "Hestia")]
    assert ok(court.read(made, player))["name"] == "Bram"
    told = ok(player.client.get("/notifications"))["items"]
    [word] = [n for n in told if n["kind"] == "boon.audit"]
    assert word["summary"].startswith("Hestia gave Agnes an audit of Bram's boons")
    assert word["link"] == f"/print/boon-audits/{made['id']}"
    assert "harpy-688 as Hestia gave Agnes an audit of Bram's boons." in court.messages()
    # Bram's own player doesn't read it; nor is it given twice.
    assert court.read(made, court.other).status_code == 404
    assert court.give(made, court.bram, by=court.harpy_player).status_code == 422


def test_only_whoever_made_it_gives_it_and_only_to_a_player_character_in_play(
    court: Audits,
) -> None:
    talon_with_audits(court, can_audit=True)
    made = ok(court.make(court.agnes, by=court.harpy_player), 201)

    assert court.give(made, court.bram, by=court.iris_player).status_code == 422
    assert court.give(made, court.vidal, by=court.harpy_player).status_code == 422
    court.retire(court.hugo, court.hugo_player, "off_field", listed=False)
    assert court.give(made, court.hugo, by=court.harpy_player).status_code == 422
    # Made and given at once.
    at_once = ok(court.make(court.agnes, by=court.iris_player, given_to=court.bram), 201)
    assert at_once["given_to"] == "Bram"


def test_switched_off_there_are_no_audits_to_read(court: Audits) -> None:
    made = ok(court.make(court.bram, given_to=court.agnes), 201)
    ok(court.switch(False))

    assert court.read(made, court.troupe.player).status_code == 404
    assert ok(court.troupe.player.client.get(f"/characters/{court.agnes}/boon-audits")) == []

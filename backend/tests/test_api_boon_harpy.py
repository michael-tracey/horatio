"""The Harpy and the boon ledger (#688): the troupe's setting (none, receives
submissions, the full ledger), the Harpy reviewing and keeping the ledger as their
character, never seeing an edit's changes, a staff note, who entered a boon or why a
character retired, word of each boon players report, and access ending with the title
(MET: VTM p. 379)."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_boon_standings import at_home
from tests.test_api_boons import Ledger, named, row


class Court(Ledger):
    """The Ledger's troupe, with Hestia, its Harpy, played by a fourth player."""

    def __init__(self, troupe: Troupe) -> None:
        super().__init__(troupe)
        self.harpy_player = sign_up(troupe.client_for, "harpy-688")
        self.hestia = at_home(troupe, self.harpy_player, "Hestia", "Toreador")
        self.give_title(self.hestia, ["Harpy"])

    def give_title(self, character: str, titles: list[str]) -> None:
        given = self.troupe.storyteller.client.put(
            f"/troupes/{self.troupe.id}/characters/{character}/titles", json={"titles": titles}
        )
        assert given.status_code == 200, given.text

    def access(self, level: str, by: Person | None = None) -> Any:
        return (by or self.troupe.storyteller).client.put(
            f"/troupes/{self.troupe.id}/boon-harpy", json={"access": level}
        )

    @property
    def queue(self) -> str:
        return f"/troupes/{self.troupe.id}/boon-review"


@pytest.fixture
def court(client_for: Callable[[], TestClient], session: Session) -> Court:
    return Court(Troupe(client_for, session))


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def hold(court: Court) -> None:
    ok(
        court.troupe.storyteller.client.put(
            f"/troupes/{court.troupe.id}/boon-review", json={"hold": True}
        )
    )


def report(court: Court, character: str, player: Person, other: str) -> Any:
    return ok(
        player.client.post(
            f"/characters/{character}/play-boons",
            json={
                "other": {"character_id": other},
                "direction": "owes",
                "kind": "minor",
                "made_on": "2026-10-03",
                "reason": "Discretion",
            },
        ),
        201,
    )


# --- the setting --------------------------------------------------------------------------


def test_the_harpy_has_no_access_until_storytellers_give_it(court: Court) -> None:
    harpy = court.harpy_player
    assert harpy.client.get(court.path).status_code == 404
    assert harpy.client.get(court.queue).status_code == 404
    shown = ok(harpy.client.get(f"/troupes/{court.troupe.id}"))
    assert shown["boon_harpy"] == "none"
    for person in (court.troupe.assistant, court.troupe.player, harpy):
        assert court.access("full", by=person).status_code == 403

    changed = ok(court.access("submissions"))

    assert changed["boon_harpy"] == "submissions"
    assert (
        "storyteller gave the Harpy the review queue, and word of each boon players report."
        in court.messages()
    )
    assert court.access("everything").status_code == 422
    shared = ok(court.troupe.lead.client.get(f"/troupes/{court.troupe.id}/settings-share"))
    assert "boon_harpy" in json.dumps(shared["document"])


# --- receives submissions -----------------------------------------------------------------


def test_with_submissions_the_harpy_reviews_as_their_character(court: Court) -> None:
    ok(court.access("submissions"))
    hold(court)
    harpy = court.harpy_player
    report(court, court.agnes, court.troupe.player, court.bram)

    standing = court.one(court.bram, court.agnes)
    found = ok(harpy.client.get(court.queue))
    queue = found["boons"]
    assert [(b["debtor"]["name"], b["state"]) for b in queue] == [("Agnes", "pending")]
    assert "Vidal" not in {c["name"] for c in found["characters"]}
    # They open the boons in the queue, and no others.
    assert ok(court.get(queue[0], by=harpy))["events"][0]["kind"] == "submitted"
    assert court.get(standing, by=harpy).status_code == 404
    # The ledger itself stays staff's.
    assert harpy.client.get(court.path).status_code == 404
    assert court.register(row(court.agnes, court.bram), by=harpy).status_code == 404

    accepted = ok(harpy.client.post(f"{court.path}/{queue[0]['id']}/accept", json={"note": ""}))

    assert accepted["state"] == "registered"
    line = accepted["events"][-1]
    assert (line["kind"], line["as_character"], line["by"]) == ("accepted", "Hestia", None)
    # Staff see who did it out of game too.
    staff = ok(court.get(accepted, by=court.troupe.storyteller))
    assert staff["events"][-1]["by"] == "harpy-688"
    assert staff["events"][-1]["as_character"] == "Hestia"


def test_the_harpy_s_player_is_told_of_each_boon_players_report(court: Court) -> None:
    ok(court.access("submissions"))
    hold(court)
    report(court, court.agnes, court.troupe.player, court.bram)

    told = ok(court.harpy_player.client.get("/notifications"))["items"]
    [word] = [n for n in told if n["kind"] == "boon.reported"]
    assert word["summary"] == (
        "Agnes reported a minor boon to the ledger: Agnes owes Bram (3 Oct 2026). It waits for"
        " review."
    )
    assert word["link"] == f"/play/characters/{court.hestia}/ledger"
    # Nobody else is told, and the Harpy isn't told of their own report.
    others = ok(court.other.client.get("/notifications"))["items"]
    assert not any(n["kind"] == "boon.reported" for n in others)
    report(court, court.hestia, court.harpy_player, court.agnes)
    again = ok(court.harpy_player.client.get("/notifications"))["items"]
    assert len([n for n in again if n["kind"] == "boon.reported"]) == 1


def test_the_play_view_shows_the_harpy_their_ledger(court: Court) -> None:
    mine = ok(court.harpy_player.client.get(f"/characters/{court.hestia}/play-boons"))
    assert mine["harpy"] == []

    ok(court.access("full"))
    hold(court)
    report(court, court.agnes, court.troupe.player, court.bram)

    mine = ok(court.harpy_player.client.get(f"/characters/{court.hestia}/play-boons"))
    assert mine["harpy"] == [
        {
            "troupe_id": court.troupe.id,
            "troupe_name": mine["troupe_name"],
            "access": "full",
            "to_review": 1,
        }
    ]
    ledgers = ok(court.harpy_player.client.get(f"/characters/{court.hestia}/harpy-ledgers"))
    assert [ledger["access"] for ledger in ledgers] == ["full"]
    theirs = ok(court.troupe.player.client.get(f"/characters/{court.agnes}/play-boons"))
    assert theirs["harpy"] == []


# --- the full ledger ----------------------------------------------------------------------


def test_with_the_full_ledger_the_harpy_keeps_it_as_their_character(court: Court) -> None:
    ok(court.access("full"))
    harpy = court.harpy_player

    made = court.register(row(court.agnes, court.bram, reason="Information"), by=harpy)
    assert made.status_code == 201, made.text
    boon = made.json()[0]
    assert boon["submitted_by"] is None
    first = ok(court.get(boon, by=harpy))["events"][0]
    assert (first["kind"], first["as_character"], first["by"]) == ("registered", "Hestia", None)

    edited = court.edit(boon, by=harpy, reason="Secrecy", note="Misheard")
    assert edited.status_code == 200, edited.text
    line = edited.json()["events"][-1]
    # The Harpy sees the edit, when and their note, never what it changed.
    assert (line["kind"], line["note"], line["changes"]) == ("edited", "Misheard", None)
    staff = ok(court.get(boon))["events"][-1]
    assert staff["changes"] == [{"field": "reason", "before": "Information", "after": "Secrecy"}]
    assert staff["as_character"] == "Hestia"

    traded = court.act(boon, "trade", by=harpy, creditor=named("Grove"), note="")
    assert traded.status_code == 200, traded.text
    settled = court.act(boon, "settle", by=harpy, how="called_in", note="At Elysium")
    assert settled.status_code == 200, settled.text
    assert settled.json()["events"][-1]["as_character"] == "Hestia"
    settled_line = "harpy-688 marked Agnes's minor boon to Grove settled"
    assert any(settled_line in m for m in court.messages())
    listed = court.ledger("settled", by=harpy)
    assert [b["id"] for b in listed["boons"]] == [boon["id"]]


def test_the_harpy_never_sees_or_writes_a_staff_note(court: Court) -> None:
    ok(court.access("full"))
    harpy = court.harpy_player
    boon = court.one(court.agnes, court.bram, staff_note="Plot hook: Bram is lying")

    seen = ok(court.get(boon, by=harpy))
    assert seen["staff_note"] == ""
    assert all(b["staff_note"] == "" for b in court.ledger(by=harpy)["boons"])
    assert court.edit(boon, by=harpy, staff_note="Mine", note="Note").status_code == 403
    refused = court.register(row(court.agnes, court.bram, staff_note="Mine"), by=harpy)
    assert refused.status_code == 403
    # An edit of anything else leaves the staff note as it was.
    ok(court.edit(boon, by=harpy, reason="Secrecy", note="Corrected"))
    assert ok(court.get(boon))["staff_note"] == "Plot hook: Bram is lying"


def test_the_harpy_names_only_characters_players_may_know(court: Court) -> None:
    ok(court.access("full"))
    harpy = court.harpy_player
    choices = {c["name"] for c in court.ledger(by=harpy)["characters"]}
    assert {"Agnes", "Bram", "Hestia"} <= choices
    assert "Vidal" not in choices
    hidden = court.register(row(court.agnes, court.vidal), by=harpy)
    assert hidden.status_code == 422
    assert "by name" in hidden.json()["detail"]

    # Once staff put the NPC in the ledger, the Harpy may name him too.
    court.one(court.vidal, court.bram)

    assert "Vidal" in {c["name"] for c in court.ledger(by=harpy)["characters"]}
    made = court.register(row(court.agnes, court.vidal), by=harpy)
    assert made.status_code == 201, made.text


def test_the_harpy_sees_that_a_character_left_but_not_why(court: Court) -> None:
    ok(court.access("full"))
    boon = court.one(court.bram, court.agnes)
    retired = court.other.client.post(
        f"/characters/{court.bram}/retire",
        json={"reason": "final_death", "note": "", "listed": False},
    )
    assert retired.status_code == 200, retired.text

    theirs = ok(court.get(boon, by=court.harpy_player))
    staff = ok(court.get(boon))

    assert theirs["debtor"]["standing"] == "retired"
    assert staff["debtor"]["standing"] == "final_death"
    assert theirs["departed"] is True
    assert court.ledger("departed", by=court.harpy_player)["counts"]["departed"] == 1


# --- the title ----------------------------------------------------------------------------


def test_access_goes_with_the_title_and_each_holder_has_it(court: Court) -> None:
    ok(court.access("full"))
    harpy = court.harpy_player
    assert harpy.client.get(court.path).status_code == 200
    # A second Harpy, under the title's other name, has it too.
    second = sign_up(court.troupe.client_for, "harpy-688-b")
    selene = at_home(court.troupe, second, "Selene", "Ventrue")
    court.give_title(selene, ["Master Harpy"])
    assert second.client.get(court.path).status_code == 200

    court.give_title(court.hestia, [])

    assert harpy.client.get(court.path).status_code == 404
    assert harpy.client.get(court.queue).status_code == 404
    mine = ok(harpy.client.get(f"/characters/{court.hestia}/play-boons"))
    assert mine["harpy"] == []
    assert second.client.get(court.path).status_code == 200


def test_a_harpy_who_retires_loses_access(court: Court) -> None:
    ok(court.access("full"))
    retired = court.harpy_player.client.post(
        f"/characters/{court.hestia}/retire",
        json={"reason": "off_field", "note": "", "listed": False},
    )
    assert retired.status_code == 200, retired.text

    assert court.harpy_player.client.get(court.path).status_code == 404


def test_with_the_ledger_off_the_harpy_sees_nothing(court: Court) -> None:
    ok(court.access("full"))
    ok(court.switch(False))

    assert court.harpy_player.client.get(court.path).status_code == 404
    assert court.harpy_player.client.get(court.queue).status_code == 404
    mine = court.harpy_player.client.get(f"/characters/{court.hestia}/harpy-ledgers")
    assert ok(mine) == []


def test_staff_still_see_everything_with_a_harpy_at_work(court: Court) -> None:
    ok(court.access("full"))
    boon = court.one(court.agnes, court.bram, staff_note="Secret")
    court.edit(boon, by=court.harpy_player, reason="Changed", note="Fixed")

    seen = ok(court.get(boon, by=court.troupe.assistant))

    assert seen["staff_note"] == "Secret"
    assert seen["submitted_by"] == "storyteller"
    assert seen["events"][-1]["changes"] is not None

"""Boonbreakers (#717; MET: VTM pp. 397-398): declaring one makes every open boon owed
to or by them void and gives them Disgraced for as long as the mark stands; appeals
for mercy, and mercy lifting the mark, restoring the boons its lifter chooses. And a
great boon formally ignored costs its debtor status (p. 395), which staff or the Harpy
take, or don't, by hand."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import HeldStatus
from tests.api_helpers import Troupe, sign_up
from tests.test_api_boon_harpy import Court, ok
from tests.test_api_boon_standings import at_home
from tests.test_api_sect_status import logged, play_games, remove, status


class Breakers(Court):
    """The Harpy's court, with Cosima, a Camarilla character of a fifth player, who
    will refuse to pay."""

    def __init__(self, troupe: Troupe) -> None:
        super().__init__(troupe)
        self.cosima_player = sign_up(troupe.client_for, "cosima-717")
        self.cosima = at_home(troupe, self.cosima_player, "Cosima", "Ventrue")

    @property
    def marks(self) -> str:
        return f"/troupes/{self.troupe.id}/boonbreakers"

    def declare(self, character: str, note: str = "Refused to repay", by: Any = None, **body: Any):
        return (by or self.troupe.storyteller).client.post(
            self.marks, json={"character_id": character, "note": note, **body}
        )

    def appeal(self, mark: dict[str, Any], by: Any = None, **body: Any) -> Any:
        return (by or self.troupe.storyteller).client.post(
            f"{self.marks}/{mark['id']}/appeals", json=body
        )

    def boon(self, boon: dict[str, Any]) -> Any:
        return ok(self.get(boon))


@pytest.fixture
def breakers(client_for: Callable[[], TestClient], session: Session) -> Breakers:
    return Breakers(Troupe(client_for, session))


def held_names(breakers: Breakers) -> list[str]:
    return [h["name"] for h in status(breakers.troupe.storyteller, breakers.cosima)["held"]]


# --- declaring ----------------------------------------------------------------------------


def test_declaring_voids_their_open_boons_both_ways_and_gives_disgraced(
    breakers: Breakers,
) -> None:
    owes = breakers.one(breakers.cosima, breakers.agnes)
    owed = breakers.one(breakers.bram, breakers.cosima, kind="major")
    settled = breakers.one(breakers.cosima, breakers.vidal)
    ok(breakers.act(settled, "settle", how="called_in", note="Paid"))
    other = breakers.one(breakers.agnes, breakers.bram)

    shown = ok(
        breakers.troupe.storyteller.client.get(
            f"{breakers.marks}/preview", params={"character_id": breakers.cosima}
        )
    )
    assert (shown["owed_by"], shown["owed_to"]) == (1, 1)
    assert {b["id"] for b in shown["boons"]} == {owes["id"], owed["id"]}

    mark = ok(breakers.declare(breakers.cosima, refused_boon_id=owes["id"]), 201)

    assert mark["character"]["name"] == "Cosima"
    assert mark["character"]["boonbreaker"] is True
    assert mark["disgraced"] is True
    assert mark["refused"]["id"] == owes["id"]
    assert {b["id"] for b in mark["voided"]} == {owes["id"], owed["id"]}
    for boon in (owes, owed):
        found = breakers.boon(boon)
        assert found["state"] == "void"
        assert found["events"][-1]["kind"] == "voided"
        assert "declared a Boonbreaker (p. 397): Refused to repay" in found["events"][-1]["note"]
    assert breakers.boon(settled)["state"] == "settled"
    assert breakers.boon(other)["state"] == "registered"
    # The mark shows wherever the ledger names them.
    listed = breakers.ledger("all")["boons"]
    sides = [b["debtor"] for b in listed] + [b["creditor"] for b in listed]
    assert {s["boonbreaker"] for s in sides if s["name"] == "Cosima"} == {True}
    assert {s["boonbreaker"] for s in sides if s["name"] != "Cosima"} == {False}
    # Disgraced, held while the mark stands.
    [disgraced] = [
        h
        for h in status(breakers.troupe.storyteller, breakers.cosima)["held"]
        if h["name"] == "Disgraced"
    ]
    assert disgraced["ending"]["text"] == "While a Boonbreaker (p. 397)."
    assert disgraced["ending"]["boonbreaker"] is True
    assert disgraced["can_remove"] is False
    assert any(
        "declared Cosima (cosima-717) a Boonbreaker: 2 of their boons made void, and gave them" in m
        for m in breakers.messages()
    )
    [declared] = logged(breakers.troupe.session, breakers.cosima, "boon.boonbreaker")
    assert declared["voided"] == 2
    # Once is enough.
    assert breakers.declare(breakers.cosima).status_code == 409


def test_a_declaration_needs_a_note_and_a_boon_they_owe(breakers: Breakers) -> None:
    owed = breakers.one(breakers.bram, breakers.cosima)
    assert breakers.declare(breakers.cosima, note="  ").status_code == 422
    refused = breakers.declare(breakers.cosima, refused_boon_id=owed["id"])
    assert refused.status_code == 422
    assert "Name a boon Cosima owes" in refused.text
    for person in (breakers.troupe.player, breakers.harpy_player, breakers.cosima_player):
        assert breakers.declare(breakers.bram, by=person).status_code in (403, 404)


def test_disgraced_lasts_while_the_mark_stands_and_staff_can_t_remove_it(
    breakers: Breakers,
) -> None:
    ok(breakers.declare(breakers.cosima), 201)
    [disgraced] = [
        h
        for h in status(breakers.troupe.storyteller, breakers.cosima)["held"]
        if h["name"] == "Disgraced"
    ]
    row_ = breakers.troupe.session.get_one(HeldStatus, uuid.UUID(disgraced["id"]))
    row_.given_on = datetime.now(UTC).date() - timedelta(days=90)
    row_.created_at = datetime.now(UTC) - timedelta(days=90)
    play_games(breakers.troupe.session, breakers.cosima, 4)

    assert "Disgraced" in held_names(breakers)
    took = remove(breakers.troupe.storyteller, breakers.cosima, disgraced["id"], "Served time")
    assert took.status_code == 409
    assert "ends when the mark is lifted" in took.text


# --- mercy --------------------------------------------------------------------------------


def test_appeals_are_recorded_and_mercy_restores_the_boons_chosen(breakers: Breakers) -> None:
    first = breakers.one(breakers.cosima, breakers.agnes)
    second = breakers.one(breakers.bram, breakers.cosima)
    mark = ok(breakers.declare(breakers.cosima), 201)

    refused = ok(
        breakers.appeal(mark, to="court", outcome="refused", against=4, note="Upheld 9 to 4")
    )
    assert refused["lifted_at"] is None
    [appeal] = refused["appeals"]
    assert (appeal["to"], appeal["outcome"], appeal["against"]) == ("court", "refused", 4)
    assert "six more months for each of the 4 votes against (p. 398)" in appeal["follows"]
    assert breakers.appeal(mark, to="court", outcome="refused", against=14).status_code == 422
    assert breakers.appeal(mark, to="harpy", outcome="refused", against=2).status_code == 422
    assert "Disgraced" in held_names(breakers)

    lifted = ok(
        breakers.appeal(
            mark, to="harpy", outcome="granted", note="She paid in full", restore=[first["id"]]
        )
    )

    assert lifted["lifted_at"] is not None
    assert lifted["character"]["boonbreaker"] is False
    assert lifted["disgraced"] is False
    assert lifted["restored"] == [first["id"]]
    assert "Disgraced" not in held_names(breakers)
    restored = breakers.boon(first)
    assert restored["state"] == "registered"
    assert "Restored on mercy for Cosima" in restored["events"][-1]["note"]
    assert breakers.boon(second)["state"] == "void"
    assert breakers.appeal(mark, to="harpy", outcome="granted").status_code == 409
    # They can be declared again, a new mark.
    assert breakers.declare(breakers.cosima).status_code == 201


def test_mercy_restores_only_boons_the_declaration_voided(breakers: Breakers) -> None:
    mark = ok(breakers.declare(breakers.cosima), 201)
    unrelated = breakers.one(breakers.agnes, breakers.bram)
    gone = breakers.appeal(mark, to="harpy", outcome="granted", restore=[unrelated["id"]])
    assert gone.status_code == 422


def test_a_court_overturning_the_mark_says_the_term_falls_on_the_harpy(
    breakers: Breakers,
) -> None:
    mark = ok(breakers.declare(breakers.cosima), 201)
    lifted = ok(breakers.appeal(mark, to="court", outcome="granted", against=2))
    assert lifted["lifted_at"] is not None
    assert "falls on the Harpy who gave it (p. 398)" in lifted["appeals"][0]["follows"]
    listed = ok(breakers.troupe.storyteller.client.get(breakers.marks))["marks"]
    assert [m["lifted_at"] is not None for m in listed] == [True]


# --- the Harpy ----------------------------------------------------------------------------


def test_the_harpy_with_the_full_ledger_declares_as_their_character(breakers: Breakers) -> None:
    owes = breakers.one(breakers.cosima, breakers.agnes)
    harpy = breakers.harpy_player
    ok(breakers.access("submissions"))
    assert breakers.declare(breakers.cosima, by=harpy).status_code == 403
    ok(breakers.access("full"))

    mark = ok(breakers.declare(breakers.cosima, by=harpy), 201)

    assert mark["declared_as"] == "Hestia"
    voided = ok(breakers.get(owes, by=harpy))["events"][-1]
    assert (voided["kind"], voided["as_character"], voided["by"]) == ("voided", "Hestia", None)
    [disgraced] = [
        h
        for h in status(breakers.troupe.storyteller, breakers.cosima)["held"]
        if h["name"] == "Disgraced"
    ]
    assert "Hestia" in disgraced["patron"]["words"]
    assert breakers.declare(breakers.hestia).status_code == 201  # staff may
    assert ok(harpy.client.get(breakers.marks))["marks"][0]["character"]["name"] == "Hestia"


def test_players_see_the_mark_on_the_other_side_and_their_own(breakers: Breakers) -> None:
    ok(
        breakers.troupe.storyteller.client.put(
            f"/troupes/{breakers.troupe.id}/boon-players", json={"see": "owed", "settle": False}
        )
    )
    ok(breakers.declare(breakers.cosima), 201)
    breakers.one(breakers.cosima, breakers.agnes)

    agnes = ok(breakers.troupe.player.client.get(f"/characters/{breakers.agnes}/play-boons"))
    assert [(b["other"], b["other_boonbreaker"]) for b in agnes["owed"]] == [("Cosima", True)]
    assert agnes["boonbreaker"] is False
    cosima = ok(breakers.cosima_player.client.get(f"/characters/{breakers.cosima}/play-boons"))
    assert cosima["boonbreaker"] is True


# --- ignoring a great boon ----------------------------------------------------------------


@pytest.mark.parametrize(("kind", "due"), [("major", True), ("life", True), ("minor", False)])
def test_ignoring_a_great_boon_waits_for_staff_to_take_status(
    breakers: Breakers, kind: str, due: bool
) -> None:
    boon = breakers.one(breakers.agnes, breakers.bram, kind=kind)
    settled = ok(breakers.act(boon, "settle", how="ignored", note="Brushed off"))
    assert settled["status_loss"] == ("due" if due else None)
    path = f"{breakers.path}/{boon['id']}/status-loss"
    if not due:
        refused = breakers.troupe.storyteller.client.post(path, json={"taken": True})
        assert refused.status_code == 409
        return

    answered = ok(
        breakers.troupe.storyteller.client.post(path, json={"taken": True, "note": "Took Noble"})
    )

    assert answered["status_loss"] == "taken"
    assert breakers.troupe.storyteller.client.post(path, json={"taken": False}).status_code == 409
    assert any("status taken" in m for m in breakers.messages())
    reopened = ok(breakers.act(boon, "reopen", note="Not ignored after all"))
    assert reopened["status_loss"] is None


def test_calling_in_a_major_boon_costs_nothing(breakers: Breakers) -> None:
    boon = breakers.one(breakers.agnes, breakers.bram, kind="major")
    assert ok(breakers.act(boon, "settle", how="called_in"))["status_loss"] is None

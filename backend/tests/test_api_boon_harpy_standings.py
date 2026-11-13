"""The Harpy reading the boon standings and statistics (#749): a troupe option, off by
default and only with the full ledger; and the Harpy learning who has left only as the
court knows it (horatio.court_knows): gone only if the troupe's Who's Who lists it,
and why only when that says something in game. Inactive, which says only that a
player stopped, is never shown. Lesser Harpies (#689) follow the Harpy's view. Staff
keep the full view."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_boon_harpy import Court, ok
from tests.test_api_boon_talons import Talons
from tests.test_api_boons import row
from tests.test_api_downtimes import member_character


class Gone(Court):
    """The Court, with Cosima and Dario at home too, and boons each owes Agnes; Bram,
    Cosima and Dario then retire three ways."""

    def __init__(self, troupe: Troupe) -> None:
        super().__init__(troupe)
        self.cosima = member_character(troupe, self.other, "Cosima")
        self.dario = member_character(troupe, troupe.player, "Dario")
        made = self.register(
            row(self.bram, self.agnes),
            row(self.cosima, self.agnes, kind="major"),
            row(self.dario, self.agnes),
        )
        assert made.status_code == 201, made.text

    def retire(self, player: Person, character: str, reason: str, listed: bool) -> None:
        done = player.client.post(
            f"/characters/{character}/retire",
            json={"reason": reason, "note": "", "listed": listed},
        )
        assert done.status_code == 200, done.text

    def leave_three_ways(self) -> None:
        # Bram's player stopped, and listed him: the court knows he's gone, not why.
        self.retire(self.other, self.bram, "inactive", listed=True)
        # Cosima met Final Death, unlisted: the court hasn't heard.
        self.retire(self.other, self.cosima, "final_death", listed=False)
        # Dario went off-field, listed: the court knows, and why.
        self.retire(self.troupe.player, self.dario, "off_field", listed=True)

    def standings(self, by: Person | None = None, **query: Any) -> Any:
        return (by or self.troupe.storyteller).client.get(
            f"/troupes/{self.troupe.id}/boon-standings", params=query
        )

    def statistics(self, by: Person | None = None, **query: Any) -> Any:
        return (by or self.troupe.storyteller).client.get(
            f"/troupes/{self.troupe.id}/boon-statistics", params=query
        )

    def option(self, access: str, standings: bool | None, by: Person | None = None) -> Any:
        body: dict[str, Any] = {"access": access}
        if standings is not None:
            body["standings"] = standings
        return (by or self.troupe.storyteller).client.put(
            f"/troupes/{self.troupe.id}/boon-harpy", json=body
        )


@pytest.fixture
def gone(client_for: Callable[[], TestClient], session: Session) -> Gone:
    return Gone(Troupe(client_for, session))


@pytest.fixture
def talons(client_for: Callable[[], TestClient], session: Session) -> Talons:
    return Talons(Troupe(client_for, session))


def standing_of(found: list[dict[str, Any]]) -> dict[str, str | None]:
    return {f["who"]["name"]: f["who"]["standing"] for f in found}


def test_the_harpy_reads_the_standings_only_where_the_troupe_allows_it(gone: Gone) -> None:
    harpy = gone.harpy_player
    ok(gone.access("full"))
    # Off by default: the full ledger alone doesn't open the standings.
    assert (
        ok(gone.troupe.storyteller.client.get(f"/troupes/{gone.troupe.id}"))["boon_harpy_standings"]
        is False
    )
    assert gone.standings(by=harpy).status_code == 403
    assert gone.statistics(by=harpy).status_code == 403
    assert (
        ok(harpy.client.get(f"/characters/{gone.hestia}/harpy-ledgers"))[0]["sees_standings"]
        is False
    )
    for person in (gone.troupe.assistant, gone.troupe.player, harpy):
        assert gone.option("full", True, by=person).status_code == 403

    changed = ok(gone.option("full", True))

    assert changed["boon_harpy_standings"] is True
    assert "storyteller let the Harpy read the boon standings and statistics." in gone.messages()
    assert ok(gone.standings(by=harpy))["totals"]["open"] == 3
    assert ok(gone.statistics(by=harpy))["nodes"]
    assert (
        ok(harpy.client.get(f"/characters/{gone.hestia}/harpy-ledgers"))[0]["sees_standings"]
        is True
    )
    # Weights and the games boons are registered at stay the staff's.
    assert (
        harpy.client.put(
            f"/troupes/{gone.troupe.id}/boon-weights",
            json={"trivial": 1, "minor": 1, "major": 1, "blood": 1, "life": 1},
        ).status_code
        == 403
    )
    assert harpy.client.get(f"/troupes/{gone.troupe.id}/boon-games").status_code == 403
    # Only with the full ledger: the review queue alone doesn't open them.
    ok(gone.option("submissions", None))
    assert gone.standings(by=harpy).status_code == 403
    assert (
        ok(harpy.client.get(f"/characters/{gone.hestia}/harpy-ledgers"))[0]["sees_standings"]
        is False
    )
    # Players never read them.
    assert gone.standings(by=gone.troupe.player).status_code == 403
    shared = ok(gone.troupe.lead.client.get(f"/troupes/{gone.troupe.id}/settings-share"))
    assert "boon_harpy_standings" in json.dumps(shared["document"])
    ok(gone.option("full", False))
    assert "storyteller kept from the Harpy the boon standings and statistics." in gone.messages()


def test_the_harpy_sees_who_left_only_as_the_court_knows_it(gone: Gone) -> None:
    ok(gone.option("full", True))
    gone.leave_three_ways()
    harpy = gone.harpy_player

    theirs = standing_of(ok(gone.standings(by=harpy, scope="everyone"))["characters"])
    staff = standing_of(ok(gone.standings(scope="everyone"))["characters"])

    # Listed Inactive: gone, but never "inactive"; unlisted Final Death: at court.
    assert theirs == {
        "Agnes": "active",
        "Bram": "retired",
        "Cosima": "active",
        "Dario": "off_field",
    }
    assert staff == {
        "Agnes": "active",
        "Bram": "inactive",
        "Cosima": "final_death",
        "Dario": "off_field",
    }
    # "Active" leaves out the boons of those the court knows are gone: Bram's and Dario's.
    active = ok(gone.standings(by=harpy))
    assert {c["who"]["name"] for c in active["characters"]} == {"Agnes", "Cosima"}
    # The statistics go by the same rule, and say "inactive" nowhere.
    nodes = ok(gone.statistics(by=harpy, scope="everyone"))["nodes"]
    assert standing_of(nodes) == theirs
    assert "inactive" not in json.dumps(ok(gone.statistics(by=harpy, scope="everyone")))
    assert "inactive" not in json.dumps(ok(gone.standings(by=harpy, scope="everyone")))


def test_the_harpy_s_ledger_shows_departures_as_the_court_knows_them(gone: Gone) -> None:
    ok(gone.access("full"))
    gone.leave_three_ways()
    harpy = gone.harpy_player

    theirs = gone.ledger("departed", by=harpy)
    staff = gone.ledger("departed")

    assert sorted(b["debtor"]["name"] for b in theirs["boons"]) == ["Bram", "Dario"]
    assert {b["debtor"]["standing"] for b in theirs["boons"]} == {"retired", "off_field"}
    # Staff see Cosima's Final Death; Bram's player stopping says nothing in game.
    assert sorted(b["debtor"]["name"] for b in staff["boons"]) == ["Cosima", "Dario"]
    assert {b["debtor"]["name"]: b["debtor"]["standing"] for b in gone.ledger("all")["boons"]} == {
        "Bram": "inactive",
        "Cosima": "final_death",
        "Dario": "off_field",
    }
    # Cosima is at court, as far as the Harpy knows.
    open_ones = gone.ledger("open", by=harpy)["boons"]
    assert [b["debtor"]["name"] for b in open_ones] == ["Cosima"]
    assert open_ones[0]["departed"] is False
    assert "inactive" not in json.dumps(gone.ledger("all", by=harpy))


def test_a_lesser_harpy_follows_the_harpy_s_view(talons: Talons) -> None:
    # Iris, a Lesser Harpy who may only see the ledger, reads what the Harpy reads.
    ok(talons.setting(True))
    ok(talons.give(talons.iris, add=False, edit=False, audit=False))
    made = talons.register(row(talons.bram, talons.agnes))
    assert made.status_code == 201, made.text
    retired = talons.other.client.post(
        f"/characters/{talons.bram}/retire",
        json={"reason": "inactive", "note": "", "listed": True},
    )
    assert retired.status_code == 200, retired.text
    iris = talons.iris_player
    standings = f"/troupes/{talons.troupe.id}/boon-standings"
    assert iris.client.get(standings).status_code == 403
    assert talons.ledgers(talons.iris, iris)[0]["sees_standings"] is False

    ok(
        talons.troupe.storyteller.client.put(
            f"/troupes/{talons.troupe.id}/boon-harpy", json={"access": "full", "standings": True}
        )
    )

    assert talons.ledgers(talons.iris, iris)[0]["sees_standings"] is True
    theirs = ok(iris.client.get(standings, params={"scope": "everyone"}))
    assert standing_of(theirs["characters"])["Bram"] == "retired"
    departed = talons.ledger("departed", by=iris)["boons"]
    assert [b["debtor"]["standing"] for b in departed] == ["retired"]
    assert "inactive" not in json.dumps(theirs)

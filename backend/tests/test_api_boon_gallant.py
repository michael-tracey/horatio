"""Gallant for repaying a boon (#693; MET: VTM pp. 402, 405): when a boon is settled
as called in, the ledger offers Gallant for its debtor if its creditor has Social
Nobility, or if it was a great boon repaid to someone of significance. Never
automatic: staff, or a Social Nobility creditor's player, give it or decline it,
once; the boon's log keeps the answer."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_sect_status import entitle, held, logged, member, put_trait, status


class Court:
    """Agnes (the player's) is owed boons by Bram (another player's); both Camarilla,
    at home in a troupe that keeps a boon ledger, shows creditors their boons and
    lets them mark them settled."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.other = sign_up(troupe.client_for, "bramplayer")
        self.agnes = member(troupe, "Agnes")
        self.bram = member(troupe, "Bram", player=self.other)
        ok(troupe.storyteller.client.put(f"/troupes/{troupe.id}/boon-ledger", json={"on": True}))
        ok(
            troupe.storyteller.client.put(
                f"/troupes/{troupe.id}/boon-players", json={"see": "owed", "settle": True}
            )
        )

    @property
    def path(self) -> str:
        return f"/troupes/{self.troupe.id}/boons"

    def boon(self, kind: str = "minor", debtor: str | None = None, creditor: str | None = None):
        made = self.troupe.storyteller.client.post(
            self.path,
            json={
                "boons": [
                    {
                        "debtor": {"character_id": debtor or self.bram},
                        "creditor": {"character_id": creditor or self.agnes},
                        "kind": kind,
                        "made_on": "2026-10-03",
                        "reason": "Safe passage",
                    }
                ],
                "note": "",
            },
        )
        assert made.status_code == 201, made.text
        return made.json()[0]

    def settle(self, boon: dict[str, Any], how: str = "called_in") -> Any:
        return ok(
            self.troupe.storyteller.client.post(
                f"{self.path}/{boon['id']}/settle", json={"how": how, "note": ""}
            )
        )

    def get(self, boon: dict[str, Any]) -> Any:
        return ok(self.troupe.storyteller.client.get(f"{self.path}/{boon['id']}"))

    def answer(self, boon: dict[str, Any], give: bool, by: Person | None = None, note: str = ""):
        return (by or self.troupe.storyteller).client.post(
            f"{self.path}/{boon['id']}/gallant", json={"give": give, "note": note}
        )

    def tab_owed(self, by: Person | None = None) -> list[dict[str, Any]]:
        shown = ok((by or self.troupe.player).client.get(f"/characters/{self.agnes}/play-boons"))
        return shown["owed"]

    def play_answer(self, boon: dict[str, Any], give: bool, by: Person | None = None) -> Any:
        return (by or self.troupe.player).client.post(
            f"/characters/{self.agnes}/play-boons/{boon['id']}/gallant",
            json={"give": give, "note": ""},
        )


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


@pytest.fixture
def court(client_for: Callable[[], TestClient], session: Session) -> Court:
    return Court(Troupe(client_for, session))


def noble(court: Court) -> None:
    put_trait(court.troupe.session, court.agnes, "merits", "Social Nobility", 3)


def test_a_creditor_with_social_nobility_is_offered_gallant_and_gives_it(court: Court) -> None:
    noble(court)
    boon = court.boon()
    # Standing, nothing is offered.
    assert court.get(boon)["gallant"] is None

    court.settle(boon)

    # Staff see the offer on the boon; the creditor's player sees it in the Play View.
    assert court.get(boon)["gallant"] == {
        "debtor": "Bram",
        "creditor": "Agnes",
        "reasons": ["nobility"],
    }
    [owed] = court.tab_owed()
    assert owed["gallant"]["reasons"] == ["nobility"]
    # Only the creditor's side: the debtor's player isn't offered anything.
    debtor_tab = ok(court.other.client.get(f"/characters/{court.bram}/play-boons"))
    assert all(b["gallant"] is None for b in debtor_tab["owes"])
    refused = court.other.client.post(
        f"/characters/{court.bram}/play-boons/{boon['id']}/gallant",
        json={"give": True, "note": ""},
    )
    assert refused.status_code == 403

    shown = ok(court.play_answer(boon, True))

    # Bram holds Gallant, from Agnes, saying why.
    assert held(court.other, court.bram) == ["Gallant"]
    [gallant] = status(court.other, court.bram)["held"]
    assert gallant["patron"]["words"].startswith("Agnes")
    assert "Repaid a Minor boon to Agnes" in gallant["story"]
    # Answered once: the offer is gone, and the boon's log says so, done as Agnes.
    assert shown["owed"][0]["gallant"] is None
    found = court.get(boon)
    assert found["gallant"] is None
    last = found["events"][-1]
    assert (last["kind"], last["as_character"]) == ("gallant_given", "Agnes")
    assert court.play_answer(boon, True).status_code == 409
    assert logged(court.troupe.session, court.bram, "status.added")[0]["status"] == "Gallant"
    log = [
        e["message"] for e in court.troupe.lead.client.get(f"/troupes/{court.troupe.id}/log").json()
    ]
    assert any("gave Bram Gallant for repaying their minor boon to Agnes" in m for m in log)


def test_only_a_boon_called_in_and_only_with_a_reason(court: Court) -> None:
    noble(court)
    forgiven = court.boon()
    court.settle(forgiven, "forgiven")
    assert court.get(forgiven)["gallant"] is None

    # No Social Nobility, a minor boon: nothing to offer.
    plain = court.boon(debtor=court.agnes, creditor=court.bram)
    court.settle(plain)
    assert court.get(plain)["gallant"] is None
    assert court.answer(plain, True).status_code == 409


def test_a_great_boon_repaid_to_a_prince_is_suggested_to_staff_only(court: Court) -> None:
    entitle(court.troupe, court.agnes, "Prince")
    minor = court.boon("major")
    court.settle(minor)
    # A major boon isn't a great one (p. 402: blood or life).
    assert court.get(minor)["gallant"] is None

    life = court.boon("life")
    court.settle(life)
    assert court.get(life)["gallant"]["reasons"] == ["great"]
    # Without Social Nobility, the creditor's player isn't the one to give it.
    owed = {b["id"]: b for b in court.tab_owed()}
    assert owed[life["id"]]["gallant"] is None
    assert court.play_answer(life, True).status_code == 403

    # Staff decline it, with a note; the offer is answered.
    declined = ok(court.answer(life, False, note="Not publicly enough"))
    assert declined["gallant"] is None
    assert declined["events"][-1]["kind"] == "gallant_declined"
    assert held(court.other, court.bram) == []

    # Reopened and called in again, it's offered again.
    ok(
        court.troupe.storyteller.client.post(
            f"{court.path}/{life['id']}/reopen", json={"note": "Not repaid after all"}
        )
    )
    court.settle(life)
    assert court.get(life)["gallant"]["reasons"] == ["great"]
    given = ok(court.answer(life, True))
    assert given["gallant"] is None
    assert held(court.other, court.bram) == ["Gallant"]


def test_an_elder_counts_as_someone_of_significance(court: Court) -> None:
    put_trait(court.troupe.session, court.agnes, "backgrounds", "Generation", 3)
    blood = court.boon("blood")
    court.settle(blood)
    assert court.get(blood)["gallant"]["reasons"] == ["great"]


def test_a_harpy_with_the_full_ledger_answers_as_their_character(court: Court) -> None:
    harpy_player = sign_up(court.troupe.client_for, "harpy-693")
    hestia = member(court.troupe, "Hestia", player=harpy_player)
    entitle(court.troupe, hestia, "Harpy")
    entitle(court.troupe, court.agnes, "Prince")
    life = court.boon("life")
    court.settle(life)
    path = f"{court.path}/{life['id']}"

    # Reaching only the review queue, the Harpy neither sees the boon nor answers.
    ok(
        court.troupe.storyteller.client.put(
            f"/troupes/{court.troupe.id}/boon-harpy", json={"access": "submissions"}
        )
    )
    assert court.answer(life, True, by=harpy_player).status_code != 200

    ok(
        court.troupe.storyteller.client.put(
            f"/troupes/{court.troupe.id}/boon-harpy", json={"access": "full"}
        )
    )
    assert ok(harpy_player.client.get(path))["gallant"]["reasons"] == ["great"]
    given = ok(court.answer(life, True, by=harpy_player))

    assert given["gallant"] is None
    last = given["events"][-1]
    assert (last["kind"], last["as_character"]) == ("gallant_given", "Hestia")
    assert held(court.other, court.bram) == ["Gallant"]


def test_where_only_staff_change_status_staff_answer(court: Court) -> None:
    noble(court)
    ok(
        court.troupe.storyteller.client.patch(
            f"/troupes/{court.troupe.id}", json={"status_by": "staff"}
        )
    )
    boon = court.boon()
    court.settle(boon)

    assert court.tab_owed()[0]["gallant"] is None
    assert court.play_answer(boon, True).status_code == 403
    assert court.get(boon)["gallant"]["reasons"] == ["nobility"]
    ok(court.answer(boon, True, note="As Agnes asked"))
    assert held(court.other, court.bram) == ["Gallant"]


def test_no_offer_for_a_debtor_outside_the_camarilla(court: Court) -> None:
    noble(court)
    anarch = member(court.troupe, "Rook", sect="Anarch", player=court.other)
    boon = court.boon(debtor=anarch)
    court.settle(boon)
    assert court.get(boon)["gallant"] is None


def test_staff_who_dont_run_the_ledger_cant_answer(court: Court) -> None:
    noble(court)
    boon = court.boon()
    court.settle(boon)
    assert court.answer(boon, True, by=court.troupe.narrator).status_code == 403
    assert court.answer(boon, True, by=court.troupe.player).status_code == 403

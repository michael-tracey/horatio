"""Status the book ties to boons (#694; MET: VTM p. 316): a Disgraced creditor's boons
need not be repaid, an apology's boon puts a slip under Warned or Disgraced right, and
spending Praised claims help from someone not already in the character's debt."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_sect_status import add, held_id, member, npc, remove


class Court:
    """Agnes (the player's), Bram and Cosima (another player's) are Camarilla PCs at
    home in a troupe keeping a boon ledger, which shows players both sides; Vidal is
    its Camarilla NPC, and Ilse a Sabbat PC."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.other = sign_up(troupe.client_for, "other")
        self.agnes = member(troupe, "Agnes")
        self.bram = member(troupe, "Bram", player=self.other)
        self.cosima = member(troupe, "Cosima", player=self.other)
        self.ilse = member(troupe, "Ilse", sect="Sabbat", player=self.other)
        self.vidal = npc(troupe, "Vidal", "Camarilla")
        st = troupe.storyteller.client
        assert st.put(f"/troupes/{troupe.id}/boon-ledger", json={"on": True}).status_code == 200
        shown = st.put(f"/troupes/{troupe.id}/boon-players", json={"see": "owed", "settle": False})
        assert shown.status_code == 200, shown.text

    def boon(self, debtor: str, creditor: str, kind: str = "minor") -> dict[str, Any]:
        made = self.troupe.storyteller.client.post(
            f"/troupes/{self.troupe.id}/boons",
            json={
                "boons": [
                    {
                        "debtor": {"character_id": debtor},
                        "creditor": {"character_id": creditor},
                        "kind": kind,
                        "made_on": "2026-10-03",
                        "reason": "Information",
                    }
                ],
                "note": "",
            },
        )
        assert made.status_code == 201, made.text
        return made.json()[0]

    def ledger(self) -> dict[str, dict[str, Any]]:
        listed = self.troupe.storyteller.client.get(
            f"/troupes/{self.troupe.id}/boons", params={"view": "all"}
        )
        assert listed.status_code == 200, listed.text
        return {b["id"]: b for b in listed.json()["boons"]}

    def apology(self, by: Person, character: str, held: str, **body: Any) -> Any:
        body.setdefault("wronged", {"name": "Prince Varga"})
        body.setdefault("made_on", "2026-10-10")
        return by.client.post(
            f"/characters/{character}/apology-boon", json={"held_id": held, **body}
        )

    def claims(self, by: Person, character: str) -> list[str]:
        found = by.client.get(f"/characters/{character}/praised-claims")
        assert found.status_code == 200, found.text
        return [c["name"] for c in found.json()["characters"]]


@pytest.fixture
def court(client_for: Callable[[], TestClient], session: Session) -> Court:
    return Court(Troupe(client_for, session))


def test_a_disgraced_creditors_standing_boons_need_not_be_repaid(court: Court) -> None:
    st = court.troupe.storyteller
    owed = court.boon(court.agnes, court.bram)
    settled = court.boon(court.agnes, court.bram)
    court.troupe.storyteller.client.post(
        f"/troupes/{court.troupe.id}/boons/{settled['id']}/settle", json={"how": "called_in"}
    )
    theirs = court.boon(court.bram, court.agnes)
    assert add(st, court.bram, "Disgraced", reason="Broke the Masquerade").status_code == 200

    ledger = court.ledger()
    assert ledger[owed["id"]]["creditor_disgraced"] is True
    assert ledger[settled["id"]]["creditor_disgraced"] is False
    assert ledger[theirs["id"]]["creditor_disgraced"] is False
    one = st.client.get(f"/troupes/{court.troupe.id}/boons/{owed['id']}").json()
    assert one["creditor_disgraced"] is True
    # The debtor's player sees it on what Agnes owes; Bram's player on what he's owed.
    agnes = court.troupe.player.client.get(f"/characters/{court.agnes}/play-boons").json()
    assert [(b["other"], b["creditor_disgraced"]) for b in agnes["owes"]] == [
        ("Bram", True),
        ("Bram", False),
    ]
    assert [b["creditor_disgraced"] for b in agnes["owed"]] == [False]
    bram = court.other.client.get(f"/characters/{court.bram}/play-boons").json()
    assert [b["creditor_disgraced"] for b in bram["owed"] if b["state"] == "registered"] == [True]

    # Nothing was settled or changed, and the note goes when the status does.
    assert ledger[owed["id"]]["state"] == "registered"
    gone = remove(st, court.bram, held_id(st, court.bram, "Disgraced"), reason="Pardoned")
    assert gone.status_code == 200, gone.text
    assert court.ledger()[owed["id"]]["creditor_disgraced"] is False


def test_staff_register_the_boon_an_apology_owes_for_a_slip(court: Court) -> None:
    st = court.troupe.storyteller
    assert add(st, court.agnes, "Warned", reason="Spoke out of turn").status_code == 200
    assert add(st, court.bram, "Disgraced", reason="Broke the Masquerade").status_code == 200
    warned = held_id(st, court.agnes, "Warned")
    disgraced = held_id(st, court.bram, "Disgraced")

    choices = st.client.get(f"/characters/{court.agnes}/apology-boon")
    assert choices.status_code == 200, choices.text
    assert {c["name"] for c in choices.json()["characters"]} >= {"Bram", "Cosima", "Vidal"}

    minor = court.apology(st, court.agnes, warned)
    major = court.apology(
        st, court.bram, disgraced, wronged={"character_id": court.cosima}, reason="Insulted her"
    )

    assert minor.status_code == 201, minor.text
    assert major.status_code == 201, major.text
    first, second = minor.json(), major.json()
    assert (first["kind"], first["debtor"]["name"], first["creditor"]["name"]) == (
        "minor",
        "Agnes",
        "Prince Varga",
    )
    assert first["reason"] == "An apology for a slip while Warned"
    assert first["state"] == "registered"
    assert first["events"][0]["note"] == "Puts right a slip while Warned (p. 316)."
    assert (second["kind"], second["creditor"]["name"], second["reason"]) == (
        "major",
        "Cosima",
        "Insulted her",
    )


def test_an_apology_boon_is_only_for_warned_or_disgraced_and_only_staff(court: Court) -> None:
    st = court.troupe.storyteller
    assert add(court.troupe.player, court.agnes, "Praised").status_code == 200
    assert add(st, court.agnes, "Warned", reason="Spoke out of turn").status_code == 200
    praised = held_id(st, court.agnes, "Praised")
    warned = held_id(st, court.agnes, "Warned")

    assert court.apology(st, court.agnes, praised).status_code == 422
    for person in (court.troupe.player, court.troupe.narrator):
        refused = court.apology(person, court.agnes, warned)
        assert refused.status_code == 404, refused.text
        assert person.client.get(f"/characters/{court.agnes}/apology-boon").status_code == 404
    off = st.client.put(f"/troupes/{court.troupe.id}/boon-ledger", json={"on": False})
    assert off.status_code == 200
    assert court.apology(st, court.agnes, warned).status_code == 404


def test_praised_claims_help_from_the_accepted_not_already_in_debt(court: Court) -> None:
    # Bram owes Agnes a standing boon; Cosima's to her is settled.
    court.boon(court.bram, court.agnes)
    paid = court.boon(court.cosima, court.agnes)
    settled = court.troupe.storyteller.client.post(
        f"/troupes/{court.troupe.id}/boons/{paid['id']}/settle", json={"how": "called_in"}
    )
    assert settled.status_code == 200, settled.text

    # Her player sees player characters of her sect; Ilse is Sabbat.
    assert court.claims(court.troupe.player, court.agnes) == ["Cosima"]
    # Staff see the troupe's NPCs too.
    assert court.claims(court.troupe.storyteller, court.agnes) == ["Cosima", "Vidal"]
    found = court.troupe.player.client.get(f"/characters/{court.agnes}/praised-claims").json()
    assert found["sect"] == "Camarilla"
    # Another player can't ask about her.
    assert court.other.client.get(f"/characters/{court.agnes}/praised-claims").status_code in (
        403,
        404,
    )

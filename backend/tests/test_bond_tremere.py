"""Blood bonds follow the troupe's Tremere weakness (#1145; horatio.bonds): Volume 2's
holds a Tremere regnant's vampire thrall at one drink, ghouls as usual (Vol. 2, p. 22);
the core book's counts a Tremere thrall's first drink as two (MET: VTM p. 64). Telyav
play as their clan does. The thrall's player is told, and the log says so."""

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.bonds import CAPPED, DOUBLED, add_months, today, walk
from horatio.models import BloodBond, BondEntry
from horatio.models import Troupe as TroupeRow
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_bond_reports import Players, tonight
from tests.test_api_character_search import make_home


def homed(troupe: Troupe, player: Person, name: str, clan: str) -> str:
    character_id = new_character(troupe, player, name, clan=clan)
    make_home(troupe, player, character_id)
    return character_id


class Chantry(Players):
    """The bonds scene (Agnes, a vampire of no clan, is the player's; Bram the other
    player's), with Theodric, a Tremere of the other player's; Tatiana, a Telyav of the
    third player's; Etrius, a Tremere of the player's own; and Igor, a ghoul NPC."""

    def __init__(self, troupe: Troupe) -> None:
        super().__init__(troupe)
        self.theodric = homed(troupe, self.other, "Theodric", "Tremere")
        self.tatiana = homed(troupe, self.third, "Tatiana", "Tremere: Telyav")
        self.etrius = homed(troupe, troupe.player, "Etrius", "Tremere")
        self.igor = self.npc("Igor", npc_kind="ghoul")

    def core(self) -> None:
        chosen = self.troupe.storyteller.client.put(
            f"/troupes/{self.troupe.id}/clan-weaknesses", json={"core": ["Tremere"]}
        )
        assert chosen.status_code == 200, chosen.text

    def bond(self, bond_id: str) -> dict[str, Any]:
        return next(b for b in self.bonds() if b["id"] == bond_id)


@pytest.fixture
def chantry(
    client_for: Callable[[], TestClient],
    session: Session,
    ghoul_rules: None,  # for Igor
) -> Chantry:
    return Chantry(Troupe(client_for, session))


NIGHTS = ("2026-10-03", "2026-10-10", "2026-10-17")


def drink(kind: str, night: str, weakness: str = "", level: int | None = None) -> BondEntry:
    return BondEntry(
        id=uuid.uuid4(), kind=kind, night=date.fromisoformat(night), level=level, weakness=weakness
    )


# --- the level, from the drinks log ------------------------------------------------------


def test_a_capped_drink_binds_to_one_drink_and_no_further() -> None:
    first, second, third = (drink("drink", n, CAPPED) for n in NIGHTS)
    assert walk([first]) == (1, set())
    assert walk([first, second, third]) == (1, {second.id, third.id})
    # A bond already deeper, entered by staff, isn't raised by a capped drink.
    entered = drink("entered", "2026-10-01", level=2)
    assert walk([entered, first]) == (2, {first.id})


def test_a_doubled_drink_counts_two_only_as_the_first() -> None:
    first, second, third = (drink("drink", n, DOUBLED) for n in NIGHTS)
    assert walk([first]) == (2, {first.id})
    assert walk([first, second]) == (3, {first.id})
    # The same night counts once.
    again = drink("drink", NIGHTS[0], DOUBLED)
    assert walk([first, again]) == (2, {first.id})
    # Not first: the bond already stood at one drink.
    entered = drink("entered", "2026-10-01", level=1)
    assert walk([entered, third]) == (2, set())


# --- Volume 2's, the default ------------------------------------------------------------


def test_a_tremere_regnant_binds_a_vampire_only_to_the_first_drink(chantry: Chantry) -> None:
    c, t = chantry, chantry.troupe
    bond = c.drunk(c.agnes, c.theodric, *NIGHTS)

    shown = c.bond(bond["id"])
    assert shown["level"] == 1
    assert shown["weakness"] == (
        "Theodric is Tremere: in this troupe their blood binds Agnes only to the first drink"
        " (Vol. 2, p. 22)."
    )
    held = [e["weakness"] for e in shown["entries"]]
    assert held[0] == ""
    assert (
        held[1]
        == held[2]
        == (
            "Held at the first drink: a Tremere's blood binds another vampire no further here"
            " (Vol. 2, p. 22)."
        )
    )
    # A full bond never forms, so Agnes isn't immune to others.
    assert c.drink(c.agnes, c.bram).status_code == 201
    # The troupe's Bonds screen says which weakness it plays.
    listed = t.storyteller.client.get(c.path).json()
    assert listed["tremere"].startswith("This troupe plays Volume 2's Tremere weakness")

    # Agnes's player is told, for each drink it held, and so is the log.
    told = [n for n in c.notes(t.player) if "Theodric" in n]
    assert told[0] == (
        "Agnes drank Theodric's blood on 17 Oct 2026, but the bond stays at one drink: in"
        " this troupe a Tremere's blood binds another vampire only to the first drink"
        " (Vol. 2, p. 22)."
    )
    assert len(told) == 2
    logged = [m for m in c.messages() if "drinking Theodric's blood on 10 Oct" in m]
    assert logged[0].endswith(
        ": one drink (in this troupe a Tremere's blood binds another vampire only to the"
        " first drink, Vol. 2, p. 22)."
    )
    assert any("Theodric" in m for m in c.character_log(c.agnes, t.player))
    # The thrall's player sees the line on the sheet's card too.
    [card] = c.card(c.agnes, t.player).json()["bound_to"][:1]
    assert card["weakness"] == shown["weakness"]


def test_a_tremeres_ghoul_is_bound_as_usual(chantry: Chantry) -> None:
    c = chantry
    bond = c.drunk(c.igor, c.theodric, *NIGHTS)
    shown = c.bond(bond["id"])
    assert (shown["level"], shown["weakness"]) == (3, "")
    assert all(e["weakness"] == "" for e in shown["entries"])
    assert not any("Tremere" in m for m in c.messages() if "Igor drinking" in m)


def test_telyav_play_as_their_clan(chantry: Chantry) -> None:
    c = chantry
    bond = c.drunk(c.agnes, c.tatiana, *NIGHTS)
    assert c.bond(bond["id"])["level"] == 1
    # A thrall by name only could be a ghoul: Horatio leaves it be.
    named_bond = c.drunk({"name": "Renfield"}, c.tatiana, *NIGHTS)
    assert c.bond(named_bond["id"])["level"] == 3


def test_a_deeper_bond_to_a_tremere_drops_a_stage_a_month(
    chantry: Chantry, session: Session
) -> None:
    c = chantry
    entered = c.enter(c.agnes, c.theodric, level=3, night=today().isoformat())
    assert entered.status_code == 201, entered.text
    bond_id = entered.json()["id"]
    change = c.bond(bond_id)["next_change"]
    assert (change["kind"], change["to"], change["tremere"]) == ("drop", 2, True)
    assert change["on"] == add_months(today(), 1).isoformat()

    # Two months on, it has dropped twice, and a drink doesn't hold it up.
    back = timedelta(days=(today() - add_months(today(), -2)).days + 1)
    bond = session.get_one(BloodBond, uuid.UUID(bond_id))
    bond.created_at -= back
    for entry in session.scalars(select(BondEntry).where(BondEntry.bond_id == bond.id)):
        entry.night -= back
    troupe = session.get_one(TroupeRow, uuid.UUID(c.troupe.id))
    troupe.bond_clock_from -= back
    session.commit()
    assert c.drink(c.agnes, c.theodric, night=today().isoformat()).status_code == 201
    shown = c.bond(bond_id)
    assert shown["level"] == 1
    assert [e["level"] for e in shown["entries"] if e["kind"] == "dropped"] == [2, 1]
    assert any("Theodric dropped to one drink on" in m for m in c.messages())


def test_staff_see_the_line_on_a_reported_drink(chantry: Chantry) -> None:
    c, t = chantry, chantry.troupe
    assert c.set("players_report").status_code == 200
    assert c.reported(c.agnes, t.player, "thrall", c.theodric) == "staff"
    [asked] = c.queue()
    assert asked["bond"]["weakness"].startswith("Theodric is Tremere")


# --- the core book's ----------------------------------------------------------------------


def test_a_tremere_thralls_first_drink_counts_as_two(chantry: Chantry) -> None:
    c, t = chantry, chantry.troupe
    c.core()
    first = c.drink(c.etrius, c.bram, NIGHTS[0])
    assert first.status_code == 201, first.text
    shown = c.bond(first.json()["id"])
    assert shown["level"] == 2
    assert shown["weakness"] == (
        "Etrius is Tremere: in this troupe their first drink of a vampire's blood counts as"
        " two (MET: VTM p. 64)."
    )
    assert shown["entries"][0]["weakness"].startswith("Counted as two")
    assert c.notes(t.player)[0] == (
        "Etrius's first drink of Bram's blood counted as two: in this troupe a Tremere's"
        " first drink of another vampire's blood does (MET: VTM p. 64). The bond is at two"
        " drinks."
    )
    assert any(
        m.endswith(
            ": two drinks (in this troupe a Tremere's first drink of another vampire's blood"
            " counts as two, MET: VTM p. 64)."
        )
        for m in c.messages()
    )

    # A second binds them fully, which wipes away their lesser bonds and makes them immune.
    assert c.drink(c.etrius, c.cora, NIGHTS[0]).status_code == 201
    assert c.drink(c.etrius, c.bram, NIGHTS[1]).status_code == 201
    assert c.bond(first.json()["id"])["level"] == 3
    assert [b["status"] for b in c.bonds() if b["regnant"]["name"] == "Cora"] == ["ended"]
    assert c.drink(c.etrius, c.agnes, NIGHTS[2]).status_code == 409
    # Only the first drink was changed: no word of the second.
    assert sum("counted as two" in n for n in c.notes(t.player)) == 2


def test_the_core_books_changes_nothing_for_a_tremere_regnant_or_a_telyav_thrall(
    chantry: Chantry,
) -> None:
    c = chantry
    c.core()
    regnant = c.drunk(c.agnes, c.theodric, *NIGHTS)
    assert c.bond(regnant["id"])["level"] == 3
    telyav = c.drink(c.tatiana, c.bram, NIGHTS[0])
    assert c.bond(telyav.json()["id"])["level"] == 2


def test_a_drink_keeps_the_weakness_it_was_recorded_under(chantry: Chantry) -> None:
    c = chantry
    c.core()
    bond = c.drink(c.etrius, c.bram, NIGHTS[0]).json()
    back = c.troupe.storyteller.client.put(
        f"/troupes/{c.troupe.id}/clan-weaknesses", json={"core": []}
    )
    assert back.status_code == 200
    assert c.bond(bond["id"])["level"] == 2
    assert c.bond(bond["id"])["weakness"] == ""


def test_a_player_reporting_a_drink_hears_what_it_did(chantry: Chantry) -> None:
    c, t = chantry, chantry.troupe
    c.core()
    assert c.set("players_manage").status_code == 200
    made = c.report(c.etrius, t.player, "thrall", c.bram, tonight())
    assert made.status_code == 201, made.text
    assert made.json()["level"] == 2
    assert any("counted as two" in n for n in c.notes(t.player))

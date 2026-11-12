"""Blood bonds' player modes (#661): players report drinks for their own characters,
for staff to approve, or record them and confirm those recorded against them; who
may do what, the abuse checks, switching modes, and staff changing or taking out a
drink (MET: VTM p. 295; the Errata's p. 295)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_bonds import Scene, named, side


def tonight() -> str:
    return datetime.now(UTC).date().isoformat()


class Players(Scene):
    """The bonds scene, for reports: Agnes is the player's, Bram the other player's,
    Cora the third player's."""

    def report(
        self,
        mine: str,
        by: Person,
        side_: str,
        other: str | dict[str, Any],
        night: str | None = None,
        **body: Any,
    ) -> Any:
        return by.client.post(
            f"/characters/{mine}/bonds/reports",
            json={
                "troupe_id": self.troupe.id,
                "side": side_,
                "other": side(other),
                "night": night or tonight(),
                "source": "game",
                **body,
            },
        )

    def reported(self, mine: str, by: Person, side_: str, other: str | dict[str, Any]) -> str:
        made = self.report(mine, by, side_, other)
        assert made.status_code == 201, made.text
        return made.json()["outcome"]

    def card_reports(self, character: str, by: Person) -> list[dict[str, Any]]:
        card = self.card(character, by)
        assert card.status_code == 200, card.text
        return card.json()["reports"]

    def queue(self, by: Person | None = None, **query: str) -> list[dict[str, Any]]:
        listed = (by or self.troupe.storyteller).client.get(
            f"/troupes/{self.troupe.id}/approvals", params=query
        )
        assert listed.status_code == 200, listed.text
        return [a for a in listed.json() if a["kind"] == "bond_drink"]

    def screen_reports(self) -> list[dict[str, Any]]:
        listed = self.troupe.storyteller.client.get(self.path)
        assert listed.status_code == 200, listed.text
        return listed.json()["reports"]

    def notes(self, by: Person) -> list[str]:
        return [n["summary"] for n in by.client.get("/notifications").json()["items"]]


@pytest.fixture
def players(client_for: Callable[[], TestClient], session: Session) -> Players:
    return Players(Troupe(client_for, session))


# --- players report and staff approves ----------------------------------------------------


def test_a_reported_drink_waits_in_the_approvals_queue_until_staff_approve(
    players: Players,
) -> None:
    p, t = players, players.troupe
    assert p.set("players_report").status_code == 200

    assert p.reported(p.agnes, t.player, "thrall", p.bram) == "staff"

    # Nothing counts yet: no bond, and Bram's player hears nothing.
    assert p.bonds() == []
    assert p.card(p.agnes, t.player).json()["bound_to"] == []
    [mine] = p.card_reports(p.agnes, t.player)
    assert (mine["status"], mine["waiting_on"], mine["can_withdraw"]) == ("pending", "staff", True)
    assert p.card_reports(p.bram, p.other) == []
    assert p.card(p.bram, p.other).json()["bound_by"] == []
    # It waits in the troupe's approvals, and on the Bonds screen.
    [asked] = p.queue()
    assert asked["character_name"] == "Agnes"
    assert asked["bond"]["thrall"] == "Agnes"
    assert asked["bond"]["regnant"] == "Bram"
    assert asked["bond"]["refused"] is None
    assert [r["id"] for r in p.screen_reports()] == [mine["id"]]
    # Never in the sheet's own list of waiting requests, which others can see.
    sheet = t.storyteller.client.get(f"/characters/{p.agnes}/sheet").json()
    assert all(a["kind"] != "bond_drink" for a in sheet["pending_approvals"])

    approved = t.storyteller.client.post(f"/approvals/{asked['id']}/approve", json={})
    assert approved.status_code == 200, approved.text

    [bond] = p.bonds()
    assert (bond["thrall"]["name"], bond["regnant"]["name"], bond["level"]) == ("Agnes", "Bram", 1)
    assert bond["known_to_regnant"] is False
    assert p.card(p.agnes, t.player).json()["bound_to"][0]["name"] == "Bram"
    assert p.card(p.bram, p.other).json()["bound_by"] == []
    assert p.card_reports(p.agnes, t.player)[0]["status"] == "approved"
    assert any("approved Agnes drinking Bram's blood" in n for n in p.notes(t.player))
    assert p.queue() == []


def test_declining_tells_the_player_why(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_report")
    p.reported(p.agnes, t.player, "thrall", p.bram)
    [asked] = p.queue()

    declined = t.storyteller.client.post(
        f"/approvals/{asked['id']}/decline", json={"note": "Bram wasn't at that game."}
    )
    assert declined.status_code == 200, declined.text

    assert p.bonds() == []
    [mine] = p.card_reports(p.agnes, t.player)
    assert (mine["status"], mine["reason"]) == ("declined", "Bram wasn't at that game.")
    assert any("Bram wasn't at that game." in n for n in p.notes(t.player))


def test_a_drink_the_regnant_reported_is_known_to_them_once_approved(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_report")

    assert p.reported(p.bram, p.other, "regnant", p.agnes) == "staff"
    # Agnes's player isn't told of it while it waits.
    assert p.card_reports(p.agnes, t.player) == []
    [asked] = p.queue()
    assert asked["character_name"] == "Bram"
    t.storyteller.client.post(f"/approvals/{asked['id']}/approve", json={})

    [bond] = p.bonds()
    assert bond["known_to_regnant"] is True
    assert [b["name"] for b in p.card(p.bram, p.other).json()["bound_by"]] == ["Agnes"]
    assert [b["name"] for b in p.card(p.agnes, t.player).json()["bound_to"]] == ["Bram"]


def test_a_player_withdraws_a_drink_while_it_waits(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_report")
    p.reported(p.agnes, t.player, "thrall", p.bram)
    [mine] = p.card_reports(p.agnes, t.player)

    # Only the player who reported it.
    assert (
        p.other.client.post(
            f"/characters/{p.agnes}/bonds/reports/{mine['id']}/withdraw"
        ).status_code
        == 404
    )
    withdrawn = t.player.client.post(f"/characters/{p.agnes}/bonds/reports/{mine['id']}/withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "withdrawn"
    assert p.queue() == []
    assert p.queue(state="withdrawn")[0]["bond"]["regnant"] == "Bram"
    assert p.screen_reports() == []


# --- players manage ------------------------------------------------------------------------


def test_the_thrall_records_their_own_drink_at_once(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_manage")

    made = p.report(p.agnes, t.player, "thrall", p.bram)
    assert made.status_code == 201, made.text
    assert made.json() == {"outcome": "recorded", "level": 1}

    [bond] = p.bonds()
    assert (bond["level"], bond["known_to_regnant"]) == (1, False)
    assert bond["entries"][0]["recorded_by"] == "player"
    # Bram's player isn't told: the bond isn't known to the regnant.
    assert p.card(p.bram, p.other).json()["bound_by"] == []
    assert p.queue() == []


def test_a_drink_the_regnant_recorded_waits_for_the_thrall_to_confirm(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_manage")

    assert p.reported(p.bram, p.other, "regnant", p.agnes) == "thrall"

    assert p.bonds() == []
    assert p.queue() == []
    [asking] = p.card_reports(p.agnes, t.player)
    assert (asking["can_confirm"], asking["can_withdraw"]) == (True, False)
    assert asking["regnant"]["name"] == "Bram"
    assert any("Bram's player says Agnes drank their blood" in n for n in p.notes(t.player))
    [mine] = p.card_reports(p.bram, p.other)
    assert (mine["can_confirm"], mine["can_withdraw"]) == (False, True)
    # Nobody else can answer it: not Bram's player, nor a third player.
    for person, character in ((p.other, p.bram), (p.third, p.cora)):
        answered = person.client.post(
            f"/characters/{character}/bonds/reports/{asking['id']}/answer", json={"confirm": True}
        )
        assert answered.status_code in (404, 409), answered.text

    confirmed = t.player.client.post(
        f"/characters/{p.agnes}/bonds/reports/{asking['id']}/answer", json={"confirm": True}
    )
    assert confirmed.status_code == 200, confirmed.text

    [bond] = p.bonds()
    assert (bond["level"], bond["known_to_regnant"]) == (1, True)
    assert [b["name"] for b in p.card(p.bram, p.other).json()["bound_by"]] == ["Agnes"]
    assert any("thrall's player confirmed" in n for n in p.notes(p.other))


def test_the_thrall_declines_a_drink_they_didnt_take(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_manage")
    p.reported(p.bram, p.other, "regnant", p.agnes)
    [asking] = p.card_reports(p.agnes, t.player)

    declined = t.player.client.post(
        f"/characters/{p.agnes}/bonds/reports/{asking['id']}/answer",
        json={"confirm": False, "reason": "Agnes refused the cup."},
    )
    assert declined.status_code == 200, declined.text

    assert p.bonds() == []
    [mine] = p.card_reports(p.bram, p.other)
    assert (mine["status"], mine["reason"]) == ("declined", "Agnes refused the cup.")
    # Once decided, it's no longer the thrall's to answer.
    assert p.card_reports(p.agnes, t.player) == []


def test_a_regnants_drink_on_an_npc_or_a_name_goes_to_staff(players: Players) -> None:
    p = players
    p.set("players_manage")

    assert p.reported(p.bram, p.other, "regnant", named("A mortal at the bar")) == "staff"

    [asked] = p.queue()
    assert asked["bond"]["thrall"] == "A mortal at the bar"


def test_a_player_who_plays_both_sides_records_at_once(players: Players) -> None:
    p, t = players, players.troupe
    from tests.test_api_downtimes import member_character

    viktor = member_character(t, t.player, "Viktor")
    p.set("players_manage")

    made = p.report(viktor, t.player, "regnant", p.agnes)
    assert made.status_code == 201, made.text
    assert made.json()["outcome"] == "recorded"
    [bond] = p.bonds()
    assert bond["known_to_regnant"] is True


def test_staff_decide_a_drink_waiting_on_a_thrall_from_the_bonds_screen(
    players: Players,
) -> None:
    p, t = players, players.troupe
    p.set("players_manage")
    p.reported(p.bram, p.other, "regnant", p.agnes)
    [waiting] = p.screen_reports()

    decided = t.storyteller.client.post(
        f"{p.path}/reports/{waiting['id']}/decide", json={"approve": True}
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"
    assert p.bonds()[0]["level"] == 1
    # Players can't.
    assert (
        t.player.client.post(
            f"{p.path}/reports/{waiting['id']}/decide", json={"approve": True}
        ).status_code
        == 403
    )


# --- what players can't do -------------------------------------------------------------------


def test_players_report_only_their_own_characters_and_the_night_must_fit(
    players: Players,
) -> None:
    p, t = players, players.troupe
    p.set("players_manage")
    tomorrow = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()
    last_year = (datetime.now(UTC).date() - timedelta(days=365)).isoformat()

    # Someone else's character.
    assert p.report(p.bram, t.player, "thrall", p.agnes).status_code == 404
    assert p.report(p.agnes, p.other, "thrall", p.bram).status_code == 404
    # A night to come, or one before the character was made in Horatio.
    assert p.report(p.agnes, t.player, "thrall", p.bram, tomorrow).status_code == 422
    before = p.report(p.agnes, t.player, "thrall", p.bram, last_year)
    assert before.status_code == 422
    assert "before Agnes was made" in before.text
    # The other side is a player character in the troupe, or a name; never an NPC by id.
    assert p.report(p.agnes, t.player, "thrall", p.vidal).status_code == 422
    assert p.report(p.agnes, t.player, "thrall", p.agnes).status_code == 422
    # Told to staff is staff's own.
    assert p.report(p.agnes, t.player, "thrall", p.bram, source="staff").status_code == 422
    assert p.bonds() == []

    # Staff manages: players don't report.
    p.set("staff")
    assert p.card(p.agnes, t.player).json()["report_to"] == []
    assert p.report(p.agnes, t.player, "thrall", p.bram).status_code == 409


def test_a_full_bond_makes_the_thrall_immune_to_drinks_players_record(players: Players) -> None:
    p, t = players, players.troupe
    p.drunk(p.agnes, p.bram, "2026-10-03", "2026-10-10", "2026-10-17")
    p.set("players_manage")

    refused = p.report(p.agnes, t.player, "thrall", p.cora)
    assert refused.status_code == 409
    assert "full bond to Bram" in refused.text
    assert p.report(p.cora, p.third, "regnant", p.agnes).status_code == 409
    assert p.report(p.agnes, t.player, "thrall", named("Someone")).status_code == 409
    # Another drink from the regnant of the full bond is fine.
    assert p.reported(p.agnes, t.player, "thrall", p.bram) == "recorded"
    # Staff are held to it too, but can give a reason to record it anyway (#665).
    assert p.drink(p.agnes, p.cora, "2026-10-24").status_code == 409
    assert p.drink(p.agnes, p.cora, "2026-10-24", override="A ritual").status_code == 201


def test_the_form_offers_the_troupes_player_characters(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_report")

    [troupe] = p.card(p.agnes, t.player).json()["report_to"]
    assert troupe["setting"] == "players_report"
    assert sorted(c["name"] for c in troupe["characters"]) == ["Bram", "Cora"]
    # Only for its player.
    assert p.card(p.agnes, t.storyteller).json()["report_to"] == []


# --- switching modes -----------------------------------------------------------------------


def test_waiting_drinks_stay_when_the_mode_changes_and_off_hides_them(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_report")
    p.reported(p.agnes, t.player, "thrall", p.bram)

    p.set("staff")
    assert len(p.queue()) == 1
    assert p.card_reports(p.agnes, t.player)[0]["status"] == "pending"

    p.set("off")
    assert p.queue() == []
    assert p.card_reports(p.agnes, t.player) == []
    waiting = t.storyteller.client.get(f"/troupes/{t.id}/waiting").json()
    assert all(w["count"] == 0 for w in waiting if w["kind"] == "approvals")
    assert not any("drink of vampire blood" in n for n in p.notes(t.storyteller))

    p.set("players_report")
    [asked] = p.queue()
    approved = t.storyteller.client.post(f"/approvals/{asked['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert p.bonds()[0]["level"] == 1


# --- staff change or take out a drink --------------------------------------------------------


def test_staff_change_or_take_out_a_drink_a_player_recorded(players: Players) -> None:
    p, t = players, players.troupe
    p.set("players_manage")
    p.reported(p.agnes, t.player, "thrall", p.bram)
    [bond] = p.bonds()
    [drink] = bond["entries"]
    entry_path = f"{p.path}/{bond['id']}/entries/{drink['id']}"

    changed = t.storyteller.client.patch(entry_path, json={"night": "2026-10-03", "note": "Fixed"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["entries"][0]["night"] == "2026-10-03"
    # Not players.
    assert t.player.client.patch(entry_path, json={"night": "2026-10-03"}).status_code == 403
    assert t.player.client.post(f"{entry_path}/remove", json={"reason": "x"}).status_code == 403
    # A reason is needed to take it out.
    assert (
        t.storyteller.client.post(f"{entry_path}/remove", json={"reason": " "}).status_code == 422
    )

    removed = t.storyteller.client.post(
        f"{entry_path}/remove", json={"reason": "It didn't happen."}
    )
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"bond": None}
    assert p.bonds() == []
    assert any("It didn't happen." in m for m in p.messages())
    assert any("took the night of" in m for m in p.messages())

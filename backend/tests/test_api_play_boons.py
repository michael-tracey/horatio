"""The Play View's Boons tab (#686): a player reports a boon for their character; the
troupe says what its players see of the ledger (the form only, also what they owe, or
also what they're owed); and, where it lets them, a boon's creditor's player marks it
settled. The tab is there only while the troupe keeps a ledger."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_boons import Ledger, named, row


@pytest.fixture
def ledger(client_for: Callable[[], TestClient], session: Session) -> Ledger:
    return Ledger(Troupe(client_for, session))


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def players(ledger: Ledger, see: str, settle: bool = False, by: Person | None = None) -> Any:
    return (by or ledger.troupe.storyteller).client.put(
        f"/troupes/{ledger.troupe.id}/boon-players", json={"see": see, "settle": settle}
    )


def tab(ledger: Ledger, character: str, by: Person | None = None) -> Any:
    return ok((by or ledger.troupe.player).client.get(f"/characters/{character}/play-boons"))


def report(ledger: Ledger, character: str, by: Person | None = None, **body: Any) -> Any:
    return (by or ledger.troupe.player).client.post(
        f"/characters/{character}/play-boons",
        json={
            "other": {"character_id": ledger.bram},
            "direction": "owes",
            "kind": "minor",
            "made_on": "2026-10-03",
            "reason": "Information",
            **body,
        },
    )


def settle(ledger: Ledger, character: str, boon: str, by: Person | None = None, **body: Any):
    return (by or ledger.troupe.player).client.post(
        f"/characters/{character}/play-boons/{boon}/settle",
        json={"how": "called_in", "note": "", **body},
    )


def play_tabs(person: Person, character: str) -> list[str]:
    return ok(person.client.get(f"/characters/{character}/play"))["tabs"]


def test_the_tab_is_there_only_while_the_troupe_keeps_a_ledger(ledger: Ledger) -> None:
    assert "boons" in play_tabs(ledger.troupe.player, ledger.agnes)
    assert "boons" in play_tabs(ledger.troupe.storyteller, ledger.vidal)

    ok(ledger.switch(False))
    assert "boons" not in play_tabs(ledger.troupe.player, ledger.agnes)
    assert "boons" not in play_tabs(ledger.troupe.storyteller, ledger.vidal)
    gone = ledger.troupe.player.client.get(f"/characters/{ledger.agnes}/play-boons")
    assert gone.status_code == 404

    # With the ledger on, the troupe can still switch the tab off for its players.
    ok(ledger.switch(True))
    ok(
        ledger.troupe.storyteller.client.patch(
            f"/troupes/{ledger.troupe.id}", json={"play_tabs_off": ["boons"]}
        )
    )
    assert "boons" not in play_tabs(ledger.troupe.player, ledger.agnes)


def test_with_every_other_tab_off_and_no_ledger_there_is_no_play_view(ledger: Ledger) -> None:
    ok(ledger.switch(False))
    ok(
        ledger.troupe.storyteller.client.patch(
            f"/troupes/{ledger.troupe.id}",
            json={"play_tabs_off": ["sheet", "tracker", "pools", "status", "equipment", "throws"]},
        )
    )
    assert play_tabs(ledger.troupe.player, ledger.agnes) == []
    assert not ok(ledger.troupe.player.client.get(f"/characters/{ledger.agnes}"))["play_view"]

    # The ledger on, Boons is a tab, and the Play View is back.
    ok(ledger.switch(True))
    assert play_tabs(ledger.troupe.player, ledger.agnes) == ["boons"]


def test_by_default_players_see_only_the_form(ledger: Ledger) -> None:
    ledger.one(ledger.agnes, ledger.bram)
    ledger.one(ledger.bram, ledger.agnes)

    shown = tab(ledger, ledger.agnes)
    assert shown["see"] == "intake"
    assert shown["can_report"] is True
    assert shown["owes"] is None
    assert shown["owed"] is None
    # Other player characters in play to name; not Agnes herself, nor the NPC.
    assert [c["name"] for c in shown["characters"]] == ["Bram"]


def test_each_level_sends_only_what_players_may_see(ledger: Ledger) -> None:
    owes = ledger.one(ledger.agnes, ledger.bram, reason="A favour", staff_note="Watch this")
    owed = ledger.one(ledger.bram, ledger.agnes, kind="major")
    settled = ledger.one(ledger.agnes, named("The Moon"))
    ok(ledger.act(settled, "settle", how="forgiven", note="Let go"))
    void = ledger.one(ledger.agnes, ledger.bram)
    ok(ledger.act(void, "void", note="Entered twice"))

    ok(players(ledger, "owes"))
    shown = tab(ledger, ledger.agnes)
    assert shown["owed"] is None
    # Standing first, then settled; never void.
    assert [b["id"] for b in shown["owes"]] == [owes["id"], settled["id"]]
    first = shown["owes"][0]
    assert first["other"] == "Bram"
    assert first["reason"] == "A favour"
    assert first["can_settle"] is False
    # Nothing staff-only.
    assert "staff_note" not in first
    assert "events" not in first
    assert shown["owes"][1]["settled_how"] == "forgiven"
    assert shown["owes"][1]["settled_note"] == "Let go"

    ok(players(ledger, "owed"))
    shown = tab(ledger, ledger.agnes)
    assert [b["id"] for b in shown["owed"]] == [owed["id"]]
    assert shown["owed"][0]["other"] == "Bram"
    # Without the setting, nobody settles here.
    assert shown["owed"][0]["can_settle"] is False


def test_staff_on_a_pc_see_what_its_player_does_and_on_an_npc_everything(ledger: Ledger) -> None:
    ledger.one(ledger.vidal, ledger.agnes)
    assert tab(ledger, ledger.agnes, by=ledger.troupe.storyteller)["owes"] is None
    npc = tab(ledger, ledger.vidal, by=ledger.troupe.storyteller)
    assert [b["other"] for b in npc["owes"]] == ["Agnes"]
    assert npc["owed"] == []


def test_only_the_characters_player_and_staff_see_its_boons(ledger: Ledger) -> None:
    for person in (ledger.other, ledger.troupe.narrator):
        refused = person.client.get(f"/characters/{ledger.agnes}/play-boons")
        assert refused.status_code in (403, 404), refused.text
    refused = report(ledger, ledger.agnes, by=ledger.other)
    assert refused.status_code in (403, 404), refused.text


def test_a_player_reports_a_boon_either_way_as_their_character(ledger: Ledger) -> None:
    ok(report(ledger, ledger.agnes, count=2, conditions="Notify if traded"), 201)
    ok(report(ledger, ledger.agnes, direction="owed", other={"name": "The Moon"}), 201)

    found = ledger.ledger()["boons"]
    assert sorted((b["debtor"]["name"], b["creditor"]["name"]) for b in found) == [
        ("Agnes", "Bram"),
        ("Agnes", "Bram"),
        ("The Moon", "Agnes"),
    ]
    assert len({b["submitted_by"] for b in found}) == 1
    one = ok(ledger.get(found[0]))
    registered = one["events"][0]
    assert registered["kind"] == "registered"
    assert registered["as_character"] == "Agnes"
    assert registered["note"] == "Reported in the Play View."
    assert any("registered 2 minor boons" in m for m in ledger.messages())


def test_a_report_is_checked(ledger: Ledger) -> None:
    # Not to herself.
    refused = report(ledger, ledger.agnes, other={"character_id": ledger.agnes})
    assert refused.status_code == 422
    # An NPC is named by name, not picked.
    refused = report(ledger, ledger.agnes, other={"character_id": ledger.vidal})
    assert refused.status_code == 422
    # A count within reason.
    assert report(ledger, ledger.agnes, count=0).status_code == 422
    # Retired, Agnes reports nothing more.
    retired = ledger.troupe.player.client.post(
        f"/characters/{ledger.agnes}/retire",
        json={"reason": "off_field", "note": "", "listed": False},
    )
    assert retired.status_code == 200, retired.text
    assert report(ledger, ledger.agnes).status_code == 409
    assert tab(ledger, ledger.agnes)["can_report"] is False


def test_only_the_creditors_player_settles_where_the_troupe_lets_them(ledger: Ledger) -> None:
    owed = ledger.one(ledger.bram, ledger.agnes)
    owes = ledger.one(ledger.agnes, ledger.bram)

    # Not without the setting.
    ok(players(ledger, "owed"))
    assert settle(ledger, ledger.agnes, owed["id"]).status_code == 403
    # Nor with it unless players see what they're owed.
    ok(players(ledger, "owes", settle=True))
    assert settle(ledger, ledger.agnes, owed["id"]).status_code == 403

    ok(players(ledger, "owed", settle=True))
    shown = tab(ledger, ledger.agnes)
    assert shown["owed"][0]["can_settle"] is True
    assert shown["owes"][0]["can_settle"] is False
    # The debtor's player can't: not from Agnes's side, nor Bram's.
    assert settle(ledger, ledger.agnes, owes["id"]).status_code == 403
    assert settle(ledger, ledger.bram, owed["id"], by=ledger.other).status_code == 403
    # Formally ignoring is the debtor's doing, not the creditor's.
    assert settle(ledger, ledger.agnes, owed["id"], how="ignored").status_code == 422

    done = ok(settle(ledger, ledger.agnes, owed["id"], how="forgiven", note="For old times"))
    assert done["owed"][0]["state"] == "settled"
    assert done["owed"][0]["settled_how"] == "forgiven"
    line = ok(ledger.get(owed))["events"][-1]
    assert line["kind"] == "settled"
    assert line["as_character"] == "Agnes"
    assert line["note"] == "For old times"
    # Settled, it can't be settled again.
    assert settle(ledger, ledger.agnes, owed["id"]).status_code == 409


def test_only_storytellers_set_what_players_see_and_it_is_logged(ledger: Ledger) -> None:
    for person in (ledger.troupe.assistant, ledger.troupe.narrator, ledger.troupe.player):
        assert players(ledger, "owed", by=person).status_code == 403
    assert players(ledger, "everything").status_code == 422

    shown = ok(players(ledger, "owed", settle=True))
    assert shown["boon_players_see"] == "owed"
    assert shown["boon_players_settle"] is True
    assert (
        "storyteller set what players see of the boon ledger in the Play View: the form, and"
        " the boons their characters owe and are owed; they may mark a boon owed to them"
        " settled."
    ) in ledger.messages()
    # The same again isn't logged twice.
    ok(players(ledger, "owed", settle=True))
    assert sum("what players see of the boon ledger" in m for m in ledger.messages()) == 1


def test_the_settings_share_carries_what_players_see(ledger: Ledger) -> None:
    from tests.test_api_troupe_settings_share import apply, exported, second

    ok(players(ledger, "owes", settle=True))
    document = exported(ledger.troupe.storyteller, ledger.troupe.id)
    at_game = document["sections"]["at_game"]
    assert {"type": "setting", "key": "boon_players_see", "value": "owes"} in at_game
    assert {"type": "setting", "key": "boon_players_settle", "value": True} in at_game

    fresh = second(ledger.troupe)
    ok(apply(ledger.troupe.storyteller, fresh, document, from_troupe_id=ledger.troupe.id))
    copied = ok(ledger.troupe.storyteller.client.get(f"/troupes/{fresh}"))
    assert copied["boon_players_see"] == "owes"
    assert copied["boon_players_settle"] is True


def test_the_staff_ledger_still_registers_rows_as_staff(ledger: Ledger) -> None:
    ok(ledger.register(row(ledger.agnes, ledger.bram)), 201)
    found = ledger.ledger()["boons"][0]
    assert ok(ledger.get(found))["events"][0]["as_character"] is None

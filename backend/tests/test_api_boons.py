"""Boons (#685): the troupe's setting, staff registering boons (several at once), each
boon's own log with its edits' changes for storytellers and assistant storytellers
only, trading, passing on, settling, voiding and reopening, the ledger's views, and
the staff summary on a sheet (MET: VTM pp. 395-397)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.api.boons import event_out
from horatio.models import BoonEvent
from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_downtimes import member_character


class Ledger:
    """Agnes (the player's) and Bram (another player's) are at home in a troupe that
    keeps a boon ledger; Vidal is its NPC."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.other = sign_up(troupe.client_for, "other")
        self.agnes = member_character(troupe, troupe.player, "Agnes")
        self.bram = member_character(troupe, self.other, "Bram")
        made = troupe.lead.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Vidal"})
        assert made.status_code == 201, made.text
        self.vidal = made.json()["id"]
        switched = self.switch(True)
        assert switched.status_code == 200, switched.text

    @property
    def path(self) -> str:
        return f"/troupes/{self.troupe.id}/boons"

    def switch(self, on: bool, by: Person | None = None) -> Any:
        return (by or self.troupe.storyteller).client.put(
            f"/troupes/{self.troupe.id}/boon-ledger", json={"on": on}
        )

    def register(self, *rows: dict[str, Any], by: Person | None = None, note: str = "") -> Any:
        return (by or self.troupe.storyteller).client.post(
            self.path, json={"boons": list(rows), "note": note}
        )

    def one(self, debtor: Any, creditor: Any, by: Person | None = None, **terms: Any) -> Any:
        made = self.register(row(debtor, creditor, **terms), by=by)
        assert made.status_code == 201, made.text
        return made.json()[0]

    def ledger(self, view: str = "open", by: Person | None = None, **query: Any) -> Any:
        listed = (by or self.troupe.storyteller).client.get(
            self.path, params={"view": view, **query}
        )
        assert listed.status_code == 200, listed.text
        return listed.json()

    def act(self, boon: dict[str, Any], action: str, by: Person | None = None, **body: Any):
        return (by or self.troupe.storyteller).client.post(
            f"{self.path}/{boon['id']}/{action}", json=body
        )

    def edit(self, boon: dict[str, Any], by: Person | None = None, **body: Any) -> Any:
        return (by or self.troupe.storyteller).client.patch(f"{self.path}/{boon['id']}", json=body)

    def get(self, boon: dict[str, Any], by: Person | None = None) -> Any:
        return (by or self.troupe.storyteller).client.get(f"{self.path}/{boon['id']}")

    def messages(self) -> list[str]:
        log = self.troupe.lead.client.get(f"/troupes/{self.troupe.id}/log").json()
        return [e["message"] for e in log]


def who(party: str | dict[str, Any]) -> dict[str, Any]:
    """A character by id, or a name only."""
    return party if isinstance(party, dict) else {"character_id": party}


def row(debtor: Any, creditor: Any, **terms: Any) -> dict[str, Any]:
    return {
        "debtor": who(debtor),
        "creditor": who(creditor),
        "kind": "minor",
        "made_on": "2026-10-03",
        "reason": "Information",
        **terms,
    }


def named(name: str) -> dict[str, Any]:
    return {"name": name}


@pytest.fixture
def ledger(client_for: Callable[[], TestClient], session: Session) -> Ledger:
    return Ledger(Troupe(client_for, session))


# --- the setting --------------------------------------------------------------------------


def test_new_troupes_keep_no_ledger_and_storytellers_switch_it_on(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    troupe = Troupe(client_for, session)
    path = f"/troupes/{troupe.id}"
    assert troupe.lead.client.get(path).json()["boons"] is False
    assert troupe.storyteller.client.get(f"{path}/boons").status_code == 404
    for person in (troupe.assistant, troupe.narrator, troupe.player):
        refused = person.client.put(f"{path}/boon-ledger", json={"on": True})
        assert refused.status_code == 403, refused.text

    changed = troupe.storyteller.client.put(f"{path}/boon-ledger", json={"on": True})

    assert changed.status_code == 200, changed.text
    assert changed.json()["boons"] is True
    log = [e["message"] for e in troupe.lead.client.get(f"{path}/log").json()]
    assert "storyteller switched the boon ledger on." in log
    assert troupe.storyteller.client.get(f"{path}/boons").status_code == 200


def test_switched_off_the_ledger_and_its_log_are_hidden_but_kept(ledger: Ledger) -> None:
    ledger.one(ledger.agnes, ledger.bram)
    assert any("registered a minor boon" in m for m in ledger.messages())

    assert ledger.switch(False).status_code == 200

    assert ledger.troupe.storyteller.client.get(ledger.path).status_code == 404
    assert not any("boon" in m and "registered" in m for m in ledger.messages())
    card = ledger.troupe.lead.client.get(f"/characters/{ledger.agnes}/boons").json()
    assert card["troupes"] == []
    assert ledger.switch(True).status_code == 200
    assert len(ledger.ledger()["boons"]) == 1
    assert any("registered a minor boon" in m for m in ledger.messages())


# --- registering --------------------------------------------------------------------------


def test_staff_register_a_boon_with_its_terms(ledger: Ledger) -> None:
    made = ledger.one(
        ledger.agnes,
        ledger.bram,
        kind="major",
        made_on="1999-08-15",
        reason="Returning my clanmate",
        conditions="Notify if traded. No clan secrets.",
        notify_on_trade=True,
        staff_note="Agreed at Elysium",
        by=ledger.troupe.assistant,
    )

    assert (made["debtor"]["name"], made["creditor"]["name"]) == ("Agnes", "Bram")
    assert made["debtor"]["standing"] == "active"
    assert made["kind"] == "major"
    assert made["made_on"] == "1999-08-15"
    assert made["conditions"] == "Notify if traded. No clan secrets."
    assert made["notify_on_trade"] is True
    assert made["state"] == "registered"
    assert made["submitted_by"] == "assistant"
    full = ledger.get(made).json()
    assert [e["kind"] for e in full["events"]] == ["registered"]
    assert "assistant registered a major boon: Agnes owes Bram." in ledger.messages()


def test_a_whole_games_boons_at_once_each_row_as_many_times_as_its_count(ledger: Ledger) -> None:
    made = ledger.register(
        row(ledger.agnes, ledger.vidal, kind="minor", count=3, reason="Secret"),
        row(named("Elder of another domain"), ledger.agnes, kind="trivial"),
        note="Elysium, 3 October",
    )

    assert made.status_code == 201, made.text
    assert [(b["debtor"]["name"], b["creditor"]["name"], b["kind"]) for b in made.json()] == [
        ("Agnes", "Vidal", "minor"),
        ("Agnes", "Vidal", "minor"),
        ("Agnes", "Vidal", "minor"),
        ("Elder of another domain", "Agnes", "trivial"),
    ]
    named_only = made.json()[3]["debtor"]
    assert (named_only["character_id"], named_only["kind"], named_only["standing"]) == (
        None,
        None,
        None,
    )
    assert ledger.get(made.json()[0]).json()["events"][0]["note"] == "Elysium, 3 October"
    assert "storyteller registered 3 minor boons: Agnes owes Vidal (Elysium, 3 October)." in (
        ledger.messages()
    )


def test_a_row_that_cant_be_registered_stops_them_all(ledger: Ledger) -> None:
    elsewhere = new_character(ledger.troupe, ledger.troupe.stranger, "Ottilie")

    refused = ledger.register(
        row(ledger.agnes, ledger.bram),
        row(ledger.agnes, elsewhere),
    )

    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == "Row 2: The creditor isn't a character in this troupe."
    assert ledger.ledger()["boons"] == []
    own = ledger.register(row(ledger.agnes, ledger.agnes))
    assert own.status_code == 422
    assert own.json()["detail"] == "Agnes can't owe a boon to themself."
    case = ledger.register(row(named("Grove"), named("grove")))
    assert case.status_code == 422
    nobody = ledger.register(row({"name": " "}, ledger.bram))
    assert nobody.status_code == 422
    assert ledger.register(row(ledger.agnes, ledger.bram, count=21)).status_code == 422


def test_only_running_staff_keep_the_ledger(ledger: Ledger) -> None:
    boon = ledger.one(ledger.agnes, ledger.bram)
    for person in (ledger.troupe.narrator, ledger.troupe.player, ledger.other):
        assert person.client.get(ledger.path).status_code in (403, 404)
        assert ledger.register(row(ledger.agnes, ledger.bram), by=person).status_code in (403, 404)
        assert ledger.get(boon, by=person).status_code in (403, 404)
        assert ledger.act(boon, "settle", by=person, how="forgiven").status_code in (403, 404)
    assert ledger.get(boon, by=ledger.troupe.assistant).status_code == 200


# --- editing ------------------------------------------------------------------------------


def test_an_edit_needs_a_note_and_its_log_keeps_each_change(ledger: Ledger) -> None:
    boon = ledger.one(ledger.agnes, named("Grove"), reason="Info")
    assert ledger.edit(boon, reason="Information", note=" ").status_code == 422
    assert ledger.edit(boon, reason="Info", note="No change").status_code == 422

    edited = ledger.edit(
        boon,
        creditor=who(ledger.bram),
        kind="major",
        reason="Information on the Prince",
        note="Typed in wrong",
        by=ledger.troupe.assistant,
    )

    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert (body["creditor"]["name"], body["kind"], body["reason"]) == (
        "Bram",
        "major",
        "Information on the Prince",
    )
    line = body["events"][-1]
    assert (line["kind"], line["note"], line["by"]) == ("edited", "Typed in wrong", "assistant")
    assert {c["field"]: (c["before"], c["after"]) for c in line["changes"]} == {
        "creditor": ("Grove", "Bram"),
        "kind": ("Minor", "Major"),
        "reason": ("Info", "Information on the Prince"),
    }
    assert "assistant edited Agnes's major boon to Bram (Typed in wrong)." in ledger.messages()
    # The storyteller reads the changes too.
    seen = ledger.get(boon).json()["events"][-1]["changes"]
    assert seen is not None


def test_only_an_edits_changes_are_kept_from_those_who_dont_read_them(ledger: Ledger) -> None:
    """The Harpy (#688) will see a boon's log without its edits' changes: an edit says
    only that it was edited, when, and the note; a trade still says what it did."""
    at = datetime.now(UTC)
    edited = BoonEvent(
        id=uuid.uuid4(), kind="edited", note="Typo", changes={"reason": ["a", "b"]}, created_at=at
    )
    traded = BoonEvent(
        id=uuid.uuid4(), kind="traded", note="", changes={"creditor": ["A", "B"]}, created_at=at
    )

    hidden = event_out(edited, {}, {}, diffs=False)
    assert (hidden.kind, hidden.note, hidden.changes) == ("edited", "Typo", None)
    assert event_out(edited, {}, {}, diffs=True).changes is not None
    trade = event_out(traded, {}, {}, diffs=False).changes
    assert trade is not None
    assert [(c.field, c.before, c.after) for c in trade] == [("creditor", "A", "B")]


# --- trading and passing on ---------------------------------------------------------------


def test_a_trade_changes_the_creditor_keeps_the_history_and_tells_the_debtor(
    ledger: Ledger,
) -> None:
    boon = ledger.one(ledger.agnes, ledger.bram, notify_on_trade=True)

    traded = ledger.act(boon, "trade", creditor=who(ledger.vidal), note="For a favour")

    assert traded.status_code == 200, traded.text
    body = traded.json()
    assert body["creditor"]["name"] == "Vidal"
    assert body["state"] == "registered"
    line = body["events"][-1]
    assert (line["kind"], line["note"]) == ("traded", "For a favour")
    assert line["changes"] == [{"field": "creditor", "before": "Bram", "after": "Vidal"}]
    assert (
        "storyteller recorded Agnes's minor boon traded by Bram to Vidal (For a favour)."
        in ledger.messages()
    )
    told = ledger.troupe.player.client.get("/notifications").json()["items"]
    assert any(
        n["kind"] == "boon.traded"
        and n["summary"] == "Bram traded Agnes's minor boon (3 Oct 2026) to Vidal."
        for n in told
    )


def test_without_the_condition_the_debtor_isnt_told_and_a_trade_must_change_hands(
    ledger: Ledger,
) -> None:
    boon = ledger.one(ledger.agnes, ledger.bram)
    assert ledger.act(boon, "trade", creditor=who(ledger.bram)).status_code == 422
    assert ledger.act(boon, "trade", creditor=who(ledger.agnes)).status_code == 422

    assert ledger.act(boon, "trade", creditor=named("Grove")).status_code == 200

    told = ledger.troupe.player.client.get("/notifications").json()["items"]
    assert not any(n["kind"] == "boon.traded" for n in told)


def test_a_side_is_passed_on_to_another(ledger: Ledger) -> None:
    boon = ledger.one(named("Mercer"), ledger.bram)

    passed = ledger.act(
        boon, "pass-on", side="debtor", to=who(ledger.agnes), note="Mercer's broodmate"
    )

    assert passed.status_code == 200, passed.text
    assert passed.json()["debtor"]["name"] == "Agnes"
    assert passed.json()["events"][-1]["changes"] == [
        {"field": "debtor", "before": "Mercer", "after": "Agnes"}
    ]
    assert (
        "storyteller passed on Mercer's side (debtor) of a minor boon to Agnes"
        " (Mercer's broodmate)." in ledger.messages()
    )
    onto_other = ledger.act(boon, "pass-on", side="debtor", to=who(ledger.bram))
    assert onto_other.status_code == 422


# --- settling, voiding, reopening ---------------------------------------------------------


def test_settle_void_and_reopen(ledger: Ledger) -> None:
    boon = ledger.one(ledger.agnes, ledger.bram)

    settled = ledger.act(boon, "settle", how="called_in", note="Called in for influences")

    assert settled.status_code == 200, settled.text
    body = settled.json()
    assert (body["state"], body["settled_how"], body["closed_note"]) == (
        "settled",
        "called_in",
        "Called in for influences",
    )
    assert body["closed_at"] is not None
    assert (
        "storyteller marked Agnes's minor boon to Bram settled, called in"
        " (Called in for influences)." in ledger.messages()
    )
    assert ledger.act(boon, "settle", how="forgiven").status_code == 409
    assert ledger.act(boon, "trade", creditor=who(ledger.vidal)).status_code == 409
    assert ledger.act(boon, "reopen", note="").status_code == 422

    reopened = ledger.act(boon, "reopen", note="Settled by mistake").json()
    assert (reopened["state"], reopened["settled_how"], reopened["closed_at"]) == (
        "registered",
        None,
        None,
    )
    assert ledger.act(boon, "void", note=" ").status_code == 422
    voided = ledger.act(boon, "void", note="Entered twice").json()
    assert voided["state"] == "void"
    assert [e["kind"] for e in voided["events"]] == ["registered", "settled", "reopened", "voided"]
    assert voided["events"][-1]["changes"] == [
        {"field": "state", "before": "Standing", "after": "Void"}
    ]
    assert ledger.act(boon, "void", note="Again").status_code == 409


# --- the ledger's views -------------------------------------------------------------------


def test_the_ledger_shows_open_departed_settled_and_void_boons(ledger: Ledger) -> None:
    standing = ledger.one(ledger.agnes, ledger.vidal, made_on="2026-01-01")
    with_bram = ledger.one(ledger.bram, ledger.agnes, kind="major", made_on="2026-02-01")
    settled = ledger.one(ledger.agnes, named("Grove"), made_on="2026-03-01")
    ledger.act(settled, "settle", how="forgiven")
    voided = ledger.one(named("Grove"), ledger.agnes, made_on="2026-04-01")
    ledger.act(voided, "void", note="Never happened")
    retired = ledger.other.client.post(
        f"/characters/{ledger.bram}/retire",
        json={"reason": "final_death", "note": "", "listed": False},
    )
    assert retired.status_code == 200, retired.text

    opened = ledger.ledger("open")

    assert [b["id"] for b in opened["boons"]] == [standing["id"]]
    assert opened["counts"] == {
        "open": 1,
        "departed": 1,
        "settled": 1,
        "void": 1,
        "pending": 0,
        "all": 4,
    }
    gone = ledger.ledger("departed")["boons"]
    assert [b["id"] for b in gone] == [with_bram["id"]]
    assert gone[0]["departed"] is True
    assert gone[0]["debtor"]["standing"] == "final_death"
    assert [b["id"] for b in ledger.ledger("settled")["boons"]] == [settled["id"]]
    assert [b["id"] for b in ledger.ledger("void")["boons"]] == [voided["id"]]
    # Newest first.
    assert [b["made_on"] for b in ledger.ledger("all")["boons"]] == [
        "2026-04-01",
        "2026-03-01",
        "2026-02-01",
        "2026-01-01",
    ]
    # The retired character can still be named.
    names = {c["name"] for c in opened["characters"]}
    assert {"Agnes", "Bram", "Vidal"} <= names


def test_the_ledger_narrows_to_a_character_a_name_a_kind_or_nights(ledger: Ledger) -> None:
    ledger.one(ledger.agnes, ledger.bram, made_on="2026-01-01")
    ledger.one(ledger.bram, ledger.vidal, kind="major", made_on="2026-02-01")
    ledger.one(named("Grove"), ledger.vidal, kind="trivial", made_on="2026-03-01")

    def debtors(**query: Any) -> list[str]:
        return [b["debtor"]["name"] for b in ledger.ledger("all", **query)["boons"]]

    assert debtors(character_id=ledger.bram) == ["Bram", "Agnes"]
    assert debtors(name="grove") == ["Grove"]
    assert debtors(kind="major") == ["Bram"]
    assert debtors(made_from="2026-01-15", made_to="2026-02-15") == ["Bram"]
    assert ledger.ledger("open", character_id=ledger.agnes)["counts"]["all"] == 1


# --- on the sheet -------------------------------------------------------------------------


def test_staff_see_a_characters_standing_boons_by_kind_and_players_see_nothing(
    ledger: Ledger,
) -> None:
    ledger.one(ledger.agnes, ledger.bram, kind="major")
    ledger.one(ledger.agnes, ledger.vidal)
    ledger.one(ledger.agnes, ledger.vidal)
    ledger.one(ledger.bram, ledger.agnes, kind="trivial")
    gone = ledger.one(ledger.agnes, ledger.bram)
    ledger.act(gone, "settle", how="called_in")

    card = ledger.troupe.assistant.client.get(f"/characters/{ledger.agnes}/boons")

    assert card.status_code == 200, card.text
    [summary] = card.json()["troupes"]
    assert summary["troupe_id"] == ledger.troupe.id
    assert summary["owes"] == [{"kind": "minor", "count": 2}, {"kind": "major", "count": 1}]
    assert summary["owed"] == [{"kind": "trivial", "count": 1}]
    mine = ledger.troupe.player.client.get(f"/characters/{ledger.agnes}/boons")
    assert mine.json()["troupes"] == []
    narrator = ledger.troupe.narrator.client.get(f"/characters/{ledger.agnes}/boons")
    assert narrator.status_code in (200, 403, 404)
    if narrator.status_code == 200:
        assert narrator.json()["troupes"] == []

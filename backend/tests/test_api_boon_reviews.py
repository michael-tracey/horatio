"""Reviewing boons (#687): the troupe holds boons its players report for review, or
lets them stand at once; Horatio flags names that link to no character and likely
duplicates, and staff flag boons by hand; staff accept, reject (with a reason the
reporter sees) and clear flags; and a name is linked to a character on one boon or on
every boon naming it. Kinds that go straight in all the same (#993), and pending boons
kept out of the standings, the statistics, the exports and audits."""

import io
import json
from collections.abc import Callable
from typing import Any

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_boon_export import HEADER, rows
from tests.test_api_boons import Ledger, named, row, who


@pytest.fixture
def ledger(client_for: Callable[[], TestClient], session: Session) -> Ledger:
    return Ledger(Troupe(client_for, session))


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def hold(ledger: Ledger, on: bool, by: Person | None = None) -> Any:
    return (by or ledger.troupe.storyteller).client.put(
        f"/troupes/{ledger.troupe.id}/boon-review", json={"hold": on}
    )


def report(ledger: Ledger, character: str, by: Person | None = None, **body: Any) -> Any:
    return ok(
        (by or ledger.troupe.player).client.post(
            f"/characters/{character}/play-boons",
            json={
                "other": {"character_id": ledger.bram},
                "direction": "owes",
                "kind": "minor",
                "made_on": "2026-10-03",
                "reason": "Information",
                **body,
            },
        ),
        201,
    )


def queue(ledger: Ledger, by: Person | None = None) -> list[dict[str, Any]]:
    return ok(
        (by or ledger.troupe.storyteller).client.get(f"/troupes/{ledger.troupe.id}/boon-review")
    )["boons"]


def flags_of(boon: dict[str, Any]) -> list[str]:
    return [f["kind"] for f in boon["flags"]]


def test_by_default_a_report_stands_at_once(ledger: Ledger) -> None:
    report(ledger, ledger.agnes)
    assert [b["reason"] for b in ledger.ledger("open")["boons"]] == ["Information"]
    assert queue(ledger) == []
    assert "player reported" not in " ".join(ledger.messages())


def test_held_for_review_a_report_waits_and_staff_accept_it(ledger: Ledger) -> None:
    troupe = ok(hold(ledger, True))
    assert troupe["boon_review"] is True
    assert "storyteller set boons players report to wait for review." in ledger.messages()

    shown = report(ledger, ledger.agnes)
    assert [(r["state"], r["other"]) for r in shown["reports"]] == [("pending", "Bram")]
    assert ledger.ledger("open")["boons"] == []
    waiting = queue(ledger)
    assert [(b["state"], b["reason"]) for b in waiting] == [("pending", "Information")]
    assert any("reported a minor boon for review" in m for m in ledger.messages())

    accepted = ok(ledger.act(waiting[0], "accept", note="Checked with the Harpy"))
    assert accepted["state"] == "registered"
    assert [e["kind"] for e in accepted["events"]] == ["submitted", "accepted"]
    assert queue(ledger) == []
    assert [b["state"] for b in ledger.ledger("open")["boons"]] == ["registered"]
    # The player's report now says it is in the ledger (#993).
    reports = ok(ledger.troupe.player.client.get(f"/characters/{ledger.agnes}/play-boons"))[
        "reports"
    ]
    assert [(r["state"], r["other"]) for r in reports] == [("accepted", "Bram")]
    # And the player is told, as they would be of a rejection (#1054).
    told = ledger.troupe.player.client.get("/notifications").json()["items"]
    assert [(n["summary"], n["link"]) for n in told if n["kind"] == "boon.accepted"] == [
        (
            "The minor boon you reported (Agnes owes Bram, 3 Oct 2026) was accepted.",
            f"/play/characters/{ledger.agnes}?tab=boons",
        )
    ]


def test_staff_registrations_stand_at_once_even_when_held(ledger: Ledger) -> None:
    ok(hold(ledger, True))
    boon = ledger.one(ledger.agnes, ledger.bram)
    assert boon["state"] == "registered"


def test_only_staff_set_the_review_setting(ledger: Ledger) -> None:
    assert hold(ledger, True, by=ledger.troupe.player).status_code in (403, 404)


def test_a_rejection_tells_the_reporter_why(ledger: Ledger) -> None:
    ok(hold(ledger, True))
    report(ledger, ledger.agnes, reason="Directions")
    waiting = queue(ledger)[0]

    assert ledger.act(waiting, "reject", reason="  ").status_code == 422
    rejected = ok(ledger.act(waiting, "reject", reason="No such deal was struck"))
    assert rejected["state"] == "void"
    assert rejected["closed_note"] == "No such deal was struck"
    assert queue(ledger) == []

    told = ledger.troupe.player.client.get("/notifications").json()["items"]
    assert any(
        n["kind"] == "boon.rejected"
        and n["summary"]
        == "The minor boon you reported (Agnes owes Bram, 3 Oct 2026) wasn't accepted:"
        " No such deal was struck"
        for n in told
    )
    reports = ok(ledger.troupe.player.client.get(f"/characters/{ledger.agnes}/play-boons"))[
        "reports"
    ]
    assert [(r["state"], r["rejected_because"]) for r in reports] == [
        ("rejected", "No such deal was struck")
    ]
    # Only a boon waiting for review is accepted or rejected.
    assert ledger.act(waiting, "accept").status_code == 409
    standing = ledger.one(ledger.agnes, ledger.bram)
    assert ledger.act(standing, "reject", reason="No").status_code == 409


def test_a_name_that_links_to_no_character_is_flagged(ledger: Ledger) -> None:
    boon = ledger.one(ledger.agnes, named("The Moon"))
    found = queue(ledger)
    assert [b["id"] for b in found] == [boon["id"]]
    flag = found[0]["flags"][0]
    assert (flag["kind"], flag["side"]) == ("unmatched", "creditor")
    assert flag["detail"] == "No character in the troupe has this name."
    # The ledger's list marks it flagged, without its flags (#975).
    listed = ledger.ledger("open")["boons"]
    assert [(b["flagged"], b["flags"]) for b in listed] == [(True, None)]

    # A name that is a character's says so, to link it.
    ledger.one(named("vidal"), ledger.agnes)
    hinted = [b for b in queue(ledger) if b["debtor"]["name"] == "vidal"][0]
    assert hinted["flags"][0]["detail"] == "Vidal is a character in the troupe: link it?"

    # Clearing it takes the boon off the queue; it stays standing.
    cleared = ok(
        ledger.troupe.storyteller.client.post(
            f"/troupes/{ledger.troupe.id}/boon-flags/{flag['id']}/clear",
            json={"note": "Another domain's Moon"},
        )
    )
    assert cleared["flags"] == []
    assert cleared["flagged"] is False
    assert cleared["state"] == "registered"
    assert cleared["events"][-1]["kind"] == "flag_cleared"
    assert boon["id"] not in [b["id"] for b in queue(ledger)]
    assert [b["flagged"] for b in ledger.ledger("open")["boons"] if b["id"] == boon["id"]] == [
        False
    ]


def test_a_likely_duplicate_is_flagged_but_boons_entered_together_are_not(
    ledger: Ledger,
) -> None:
    first = ledger.one(ledger.agnes, ledger.bram, reason="Directions")
    # "×3" at once: alike on purpose.
    ok(ledger.register(row(ledger.agnes, ledger.bram, reason="Secret", count=3)), 201)
    assert queue(ledger) == []

    again = ledger.one(ledger.agnes, ledger.bram, reason=" directions ")
    found = queue(ledger)
    assert [b["id"] for b in found] == [again["id"]]
    flag = found[0]["flags"][0]
    assert flag["kind"] == "duplicate"
    assert flag["other_boon_id"] == first["id"]
    assert flag["detail"].startswith("Like Agnes's minor boon to Bram of 3 Oct 2026")

    # A different night isn't a duplicate, nor is a void boon's twin.
    ledger.one(ledger.agnes, ledger.bram, reason="Directions", made_on="2026-10-04")
    assert len(queue(ledger)) == 1
    ok(ledger.act(again, "void", note="Entered twice"))
    ok(ledger.act(first, "void", note="Both wrong"))
    ledger.one(ledger.agnes, ledger.bram, reason="Directions")
    assert [b["flags"] for b in queue(ledger) if b["state"] != "void"] == []


def test_a_held_report_with_flags_clears_them_when_accepted(ledger: Ledger) -> None:
    ok(hold(ledger, True))
    report(ledger, ledger.agnes, other={"name": "Mysterious stranger"}, direction="owed")
    waiting = queue(ledger)[0]
    assert flags_of(waiting) == ["unmatched"]
    accepted = ok(ledger.act(waiting, "accept"))
    assert accepted["flags"] == []
    assert queue(ledger) == []


def test_staff_flag_a_boon_by_hand_with_a_note(ledger: Ledger) -> None:
    boon = ledger.one(ledger.agnes, ledger.bram)
    assert ledger.act(boon, "flags", note="").status_code == 422
    flagged = ok(ledger.act(boon, "flags", note="Can boons force others to call theirs in?"), 201)
    assert [(f["kind"], f["note"], f["raised_by"]) for f in flagged["flags"]] == [
        ("hand", "Can boons force others to call theirs in?", "storyteller")
    ]
    assert flagged["events"][-1]["kind"] == "flagged"
    assert [b["id"] for b in queue(ledger)] == [boon["id"]]
    assert any("for review (Can boons force others" in m for m in ledger.messages())
    # Players can't flag, see the queue, or accept.
    assert ledger.act(boon, "flags", by=ledger.troupe.player, note="Mine").status_code == 404
    gone = ledger.troupe.player.client.get(f"/troupes/{ledger.troupe.id}/boon-review")
    assert gone.status_code == 404


def test_a_name_is_linked_on_one_boon_or_on_every_boon_naming_it(ledger: Ledger) -> None:
    one = ledger.one(named("The Hermit"), ledger.agnes)
    two = ledger.one(ledger.bram, named("the hermit"), reason="Shelter")
    three = ledger.one(named("The Hermit"), ledger.bram, reason="Herbs")
    other = ledger.one(named("Someone else"), ledger.agnes)

    linked = ok(
        ledger.act(one, "link", side="debtor", character_id=ledger.vidal, note="He's our NPC")
    )
    assert linked == {"linked": 1, "skipped": 0}
    got = ok(ledger.get(one))
    assert got["debtor"]["name"] == "Vidal"
    assert got["events"][-1]["changes"] == [
        {"field": "debtor", "before": "The Hermit", "after": "Vidal"}
    ]
    assert got["flags"] == []

    everywhere = ok(
        ledger.act(two, "link", side="creditor", character_id=ledger.vidal, everywhere=True)
    )
    assert everywhere == {"linked": 2, "skipped": 0}
    assert ok(ledger.get(two))["creditor"]["name"] == "Vidal"
    assert ok(ledger.get(three))["debtor"]["name"] == "Vidal"
    assert ok(ledger.get(other))["debtor"]["name"] == "Someone else"
    assert [b["id"] for b in queue(ledger)] == [other["id"]]
    assert any("linked the name the hermit to Vidal on 2 boons" in m for m in ledger.messages())

    # A character side can't be linked, nor a character outside the troupe.
    assert ledger.act(one, "link", side="debtor", character_id=ledger.bram).status_code == 422


def test_linking_skips_a_boon_where_the_character_is_the_other_side(ledger: Ledger) -> None:
    first = ledger.one(named("Shadow"), ledger.agnes)
    ledger.one(named("Shadow"), ledger.bram)
    result = ok(ledger.act(first, "link", side="debtor", character_id=ledger.bram, everywhere=True))
    assert result == {"linked": 1, "skipped": 1}


def test_review_needs_the_ledger_on(ledger: Ledger) -> None:
    ok(ledger.switch(False))
    gone = ledger.troupe.storyteller.client.get(f"/troupes/{ledger.troupe.id}/boon-review")
    assert gone.status_code == 404


def test_the_setting_is_shared_with_the_troupes_settings(ledger: Ledger) -> None:
    ok(hold(ledger, True))
    shared = ok(ledger.troupe.lead.client.get(f"/troupes/{ledger.troupe.id}/settings-share"))
    assert "boon_review" in json.dumps(shared["document"])


def test_staff_name_any_side_but_a_name_only_on_quick_entry_is_flagged(ledger: Ledger) -> None:
    ok(
        ledger.register(
            row(ledger.agnes, ledger.bram, reason="One"),
            row(named("Grove"), who(ledger.vidal), reason="Two"),
        ),
        201,
    )
    assert [flags_of(b) for b in queue(ledger)] == [["unmatched"]]


# --- approval by kind (#993) --------------------------------------------------------------


def kinds_go_in(ledger: Ledger, *kinds: str, by: Person | None = None) -> Any:
    return (by or ledger.troupe.storyteller).client.put(
        f"/troupes/{ledger.troupe.id}/boon-auto-accept", json={"kinds": list(kinds)}
    )


def reports_of(ledger: Ledger) -> list[dict[str, Any]]:
    return ok(ledger.troupe.player.client.get(f"/characters/{ledger.agnes}/play-boons"))["reports"]


def test_a_ticked_kind_goes_straight_in_and_any_other_waits(ledger: Ledger) -> None:
    ok(hold(ledger, True))
    review = ok(ledger.troupe.storyteller.client.get(f"/troupes/{ledger.troupe.id}/boon-review"))
    assert (review["held"], review["auto_accept"], review["sets_approval"]) == (True, [], True)

    assert ok(kinds_go_in(ledger, "trivial")) == {"held": True, "auto_accept": ["trivial"]}
    assert (
        "storyteller set which boons players report go straight into the ledger: trivial boons."
        in ledger.messages()
    )
    assert kinds_go_in(ledger, "huge").status_code == 422
    report(ledger, ledger.agnes, kind="trivial", reason="A favour")
    shown = report(ledger, ledger.agnes, kind="major", reason="A life debt")

    # The trivial boon is in the ledger, accepted by no one; the major one waits.
    assert [(b["kind"], b["state"]) for b in ledger.ledger("open")["boons"]] == [
        ("trivial", "registered")
    ]
    waiting = queue(ledger)
    assert [(b["kind"], b["state"], b["reported_as"]) for b in waiting] == [
        ("major", "pending", "Agnes")
    ]
    trivial = ledger.ledger("open")["boons"][0]
    lines = ok(ledger.get(trivial))["events"]
    assert [(e["kind"], e["note"], e["by"], e["as_character"]) for e in lines] == [
        ("submitted", "Reported in the Play View.", "player", "Agnes"),
        ("accepted", "Accepted automatically", None, None),
    ]
    assert "Accepted automatically: Agnes owes Bram a trivial boon." in ledger.messages()
    # The player is told which is which, and that staff approve: the troupe gives its
    # Harpy no access.
    assert [(r["kind"], r["state"]) for r in shown["reports"]] == [
        ("major", "pending"),
        ("trivial", "accepted"),
    ]
    assert shown["approver"] == "staff"
    # The troupe's settings say so too, and its settings share carries them.
    troupe = ok(ledger.troupe.lead.client.get(f"/troupes/{ledger.troupe.id}"))
    assert troupe["boon_auto_accept"] == ["trivial"]
    shared = ok(ledger.troupe.lead.client.get(f"/troupes/{ledger.troupe.id}/settings-share"))
    assert "boon_auto_accept" in json.dumps(shared["document"])


def test_with_reports_not_held_nothing_waits_whatever_the_kinds(ledger: Ledger) -> None:
    ok(kinds_go_in(ledger, "trivial"))
    report(ledger, ledger.agnes, kind="major")
    assert queue(ledger) == []
    assert [b["kind"] for b in ledger.ledger("open")["boons"]] == ["major"]
    # Nothing waited, so the report doesn't stay in the player's tab.
    assert reports_of(ledger) == []


def test_a_boon_that_goes_straight_in_is_still_flagged(ledger: Ledger) -> None:
    ok(hold(ledger, True))
    ok(kinds_go_in(ledger, "minor"))

    report(ledger, ledger.agnes, other={"name": "Mysterious Stranger"})

    [found] = queue(ledger)
    assert (found["state"], found["flagged"], flags_of(found)) == (
        "registered",
        True,
        ["unmatched"],
    )


def test_changing_the_kinds_never_touches_boons_already_waiting(ledger: Ledger) -> None:
    ok(hold(ledger, True))
    report(ledger, ledger.agnes)

    ok(kinds_go_in(ledger, "minor", "trivial"))

    assert [b["state"] for b in queue(ledger)] == ["pending"]
    assert ok(kinds_go_in(ledger))["auto_accept"] == []
    assert any(
        m.endswith("go straight into the ledger: none: every one waits.")
        for m in (ledger.messages())
    )


def test_only_those_who_run_the_queue_set_the_kinds(ledger: Ledger) -> None:
    for person in (ledger.troupe.player, ledger.other):
        assert kinds_go_in(ledger, "trivial", by=person).status_code in (403, 404)


def test_accept_all_shown_accepts_those_that_still_wait(ledger: Ledger) -> None:
    ok(hold(ledger, True))
    report(ledger, ledger.agnes, reason="First")
    report(ledger, ledger.agnes, reason="Second", kind="major")
    standing = ledger.one(ledger.bram, ledger.agnes)
    ids = [b["id"] for b in queue(ledger)]

    done = ok(
        ledger.troupe.storyteller.client.post(
            f"{ledger.path}/accept", json={"boon_ids": [*ids, standing["id"]], "note": "At court"}
        )
    )

    assert done == {"accepted": 2}
    assert queue(ledger) == []
    assert sorted(b["reason"] for b in ledger.ledger("open")["boons"]) == [
        "First",
        "Information",
        "Second",
    ]
    assert ok(ledger.get({"id": ids[0]}))["events"][-1]["note"] == "At court"
    # The player is told once for the two (#1054).
    told = ledger.troupe.player.client.get("/notifications").json()["items"]
    assert [n["summary"] for n in told if n["kind"] == "boon.accepted"] == [
        "The 2 boons you reported were accepted."
    ]
    assert (
        ledger.troupe.player.client.post(f"{ledger.path}/accept", json={"boon_ids": ids})
    ).status_code in (403, 404)


def test_pending_boons_are_absent_from_standings_statistics_exports_and_audits(
    ledger: Ledger,
) -> None:
    ok(hold(ledger, True))
    ledger.one(ledger.bram, ledger.agnes, kind="trivial", reason="Standing")
    report(ledger, ledger.agnes, kind="life", reason="Waiting", other={"name": "Lady Ash"})
    staff = ledger.troupe.storyteller.client
    assert [b["state"] for b in queue(ledger)] == ["pending"]

    # The ledger's open view, and its totals, count only the standing boon.
    assert [b["reason"] for b in ledger.ledger("open")["boons"]] == ["Standing"]
    # The standings: no one on the pending boon, nothing of its kind; only its count.
    standings = ok(staff.get(f"/troupes/{ledger.troupe.id}/boon-standings"))
    assert {c["who"]["name"] for c in standings["characters"]} == {"Agnes", "Bram"}
    assert {k["kind"]: k["count"] for k in standings["by_kind"]}["life"] == 0
    assert standings["totals"]["pending"] == 1
    # The statistics: the same.
    statistics = ok(staff.get(f"/troupes/{ledger.troupe.id}/boon-statistics"))
    assert {n["who"]["name"] for n in statistics["nodes"]} == {"Agnes", "Bram"}
    assert sum(line["registered"] for line in statistics["by_entered"]) == 1
    assert sum(line["registered"] for line in statistics["by_night"]) == 1
    # Exports: every view, the pending one too, and the workbook.
    for view in ("all", "pending"):
        exported = rows(
            staff.get(f"/troupes/{ledger.troupe.id}/boon-export", params={"view": view}), HEADER
        )
        assert [r["Reason"] for r in exported] == (["Standing"] if view == "all" else [])
    workbook = staff.get(f"/troupes/{ledger.troupe.id}/boon-workbook")
    assert workbook.status_code == 200, workbook.text
    book = openpyxl.load_workbook(io.BytesIO(workbook.content))
    cells = {str(c.value) for sheet in book.worksheets for line in sheet.iter_rows() for c in line}
    assert "Standing" in cells
    assert not {"Waiting", "Lady Ash"} & cells
    # An audit of Agnes holds only what stands.
    audit = ok(
        staff.post(f"/troupes/{ledger.troupe.id}/boon-audits", json={"character_id": ledger.agnes}),
        201,
    )
    assert (audit["owes"], [line["reason"] for line in audit["owed"]]) == ([], ["Standing"])

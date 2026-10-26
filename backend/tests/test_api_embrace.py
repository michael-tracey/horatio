"""A ghoul's Embrace (MET: VTM pp. 297–299) through the API: the home troupe's staff
convert a ghoul PC into a vampire of its sire's clan, step by step, or record that it
died; and the XP debt the conversion leaves, which the XP it earns pays off."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_cart import lines, rating, sheet, spend
from tests.test_api_generation_until_accepted import buy, give_xp, make_home
from tests.test_api_ghouls import BUILD, allow, complete, ghoul_of, place, typed

pytestmark = pytest.mark.usefixtures("ghoul_rules")

NIGHT = "2026-10-24"
MALKAVIAN = {"name": "Doctor Mirth", "clan": "Malkavian", "generation": 10}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def put(person: Person, character_id: str, category: str, name: str, to: int) -> None:
    bought = person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": to},
    )
    assert bought.status_code == 200, bought.text


def vivian(troupe: Troupe, *, merits: list[tuple[str, int]] | None = None) -> str:
    """The book's Vivian (p. 299): an Assamite Vizier's ghoul in the Camarilla, with
    Uncommon Clan and Code of Honor from creation, Auspex 3 and Quietus 2, every XP
    of her creation spent, and accepted by the troupe."""
    allow(troupe, ["vampire", "ghoul"])
    ghoul = ghoul_of(
        troupe.player,
        typed("The Vizier", "Assamite: Vizier"),
        name="Vivian",
        building_troupe_id=troupe.id,
    )
    taken = merits if merits is not None else [("Uncommon Clan", 2), ("Code of Honor", 2)]
    place(
        troupe.player,
        ghoul,
        [
            *BUILD,
            ("disciplines", "Auspex", 3),
            ("disciplines", "Quietus", 2),
            *[("merits", name, points) for name, points in taken],
        ],
    )
    assert complete(troupe.player, ghoul).status_code == 200
    # Her 30 creation XP, all spent: 7 dots of Mental and 3 of Social at 3 XP each.
    put(troupe.player, ghoul, "attributes", "Mental", 10)
    put(troupe.player, ghoul, "attributes", "Social", 8)
    make_home(troupe, ghoul)
    assert sheet(troupe.player, ghoul)["xp"]["balance"] == 0
    return ghoul


def choices(**body: Any) -> dict[str, Any]:
    return {"sire": MALKAVIAN, "clan_merits": [], **body}


def plan(person: Person, character_id: str, **body: Any) -> Any:
    return person.client.post(f"/characters/{character_id}/embrace/plan", json=choices(**body))


def embrace(person: Person, character_id: str, **body: Any) -> Any:
    return person.client.post(
        f"/characters/{character_id}/embrace",
        json={**choices(**body), "embraced_on": NIGHT},
    )


def steps(found: dict[str, Any]) -> dict[str, list[tuple[str, int]]]:
    return {s["key"]: [(line["text"], line["xp"]) for line in s["lines"]] for s in found["steps"]}


def ratings(person: Person, character_id: str, category: str) -> dict[str, int | None]:
    return {
        t["name"]: t["rating"]
        for t in sheet(person, character_id)["traits"]
        if t["category"] == category
    }


def xp_history(person: Person, character_id: str) -> list[dict[str, Any]]:
    return person.client.get(f"/characters/{character_id}/xp").json()


def award(troupe: Troupe, character_id: str, amount: int, reason: str = "Game") -> None:
    given = troupe.storyteller.client.post(
        f"/characters/{character_id}/xp", json={"amount": amount, "reason": reason}
    )
    assert given.status_code == 201, given.text


VIVIAN = {
    "two_dots": "Auspex",
    "remove": [{"category": "merits", "name": "Code of Honor"}],
    "buy_back": [{"name": "Quietus", "rating": 2}],
    "buy_back_into_debt": True,
    "weakness": "Her primary derangement: paranoia",
}


def test_vivian_is_embraced_as_the_book_has_it(troupe: Troupe) -> None:
    """The worked example on p. 299, step by step. The book sums its refunds (2 for
    Uncommon Clan, 2 for Code of Honor) to 3 rather than 4, so it ends with a debt of
    10 where its own steps come to 9: 4 back, 1 for Generation, 12 for Quietus."""
    ghoul = vivian(troupe)

    planned = plan(troupe.storyteller, ghoul, **VIVIAN)

    assert planned.status_code == 200, planned.text
    found = planned.json()
    assert found["refused"] is None, found["refused"]
    assert (found["generation"], found["generation_dots"], found["title"]) == (11, 1, "Neonate")
    assert (found["blood"], found["blood_per_turn"], found["attribute_bonus"]) == (10, 1, 1)
    by_step = steps(found)
    # Step one: not her domitor's childe, so Uncommon Clan comes off, refunded.
    assert by_step["clan"] == [("Uncommon Clan stripped, its XP refunded", 2)]
    # Step two: one dot of Generation, 1 XP as a Neonate.
    assert [xp for _, xp in by_step["generation"]] == [-1]
    # Step three: her 5 ghoul dots go; 2 in Auspex and 1 each in the other two.
    assert found["lost"] == [
        {"name": "Auspex", "rating": 3, "detail": ""},
        {"name": "Quietus", "rating": 2, "detail": ""},
    ]
    assert [(d["name"], d["rating"]) for d in found["disciplines"]] == [
        ("Auspex", 2),
        ("Dementation", 1),
        ("Obfuscate", 1),
    ]
    # Step four: a Neonate's skills and backgrounds cost what they did.
    assert [xp for _, xp in by_step["reprice"]] == [0]
    # Finishing touches: Code of Honor no longer suits her, 2 XP back.
    assert ("Code of Honor taken off, its XP refunded", 2) in by_step["finishing"]
    # Step six: 3 left over, then Quietus 2 out of clan for 12, into debt.
    assert by_step["debt"][:2] == [
        ("Refunds and saved XP pay the costs: 3 XP left over", 0),
        ("Quietus 0 → 2 bought back, no teacher needed", -12),
    ]
    assert (found["balance_before"], found["balance_after"], found["debt"]) == (0, -9, 9)

    done = embrace(troupe.storyteller, ghoul, **VIVIAN)

    assert done.status_code == 200, done.text
    character = troupe.player.client.get(f"/characters/{ghoul}").json()
    assert character["splat"] == "vampire"
    assert troupe.player.client.get(f"/characters/{ghoul}/domitor").json() is None
    assert ratings(troupe.player, ghoul, "clan") == {"Malkavian": None}
    assert ratings(troupe.player, ghoul, "disciplines") == {
        "Auspex": 2,
        "Dementation": 1,
        "Obfuscate": 1,
        "Quietus": 2,
    }
    assert ratings(troupe.player, ghoul, "backgrounds")["Generation"] == 1
    assert ratings(troupe.player, ghoul, "paths") == {"Humanity": 5}
    assert "Uncommon Clan" not in ratings(troupe.player, ghoul, "merits")
    assert sheet(troupe.player, ghoul)["xp"]["debt"] == 9

    # For the next few games, all she earns goes to the debt until it is paid.
    award(troupe, ghoul, 4)
    assert sheet(troupe.player, ghoul)["xp"]["debt"] == 5
    award(troupe, ghoul, 6)
    found_sheet = sheet(troupe.player, ghoul)
    assert (found_sheet["xp"]["debt"], found_sheet["xp"]["balance"]) == (0, 1)
    awards = [
        (e["amount"], e["to_debt"], e["debt"])
        for e in xp_history(troupe.player, ghoul)
        if e["kind"] == "award" and e["reason"] == "Game"
    ]
    assert awards == [(4, 4, 5), (6, 5, 0)]


def test_every_step_is_logged_and_the_player_told(troupe: Troupe) -> None:
    ghoul = vivian(troupe)

    assert embrace(troupe.storyteller, ghoul, **VIVIAN).status_code == 200

    messages = [e["message"] for e in troupe.player.client.get(f"/characters/{ghoul}/log").json()]
    embraced = "storyteller Embraced Vivian (player)"
    for step in ("Clan and rarity", "Generation", "Disciplines", "Finishing touches", "XP debt"):
        assert any(m.startswith(f"{embraced}, {step}:") for m in messages), step
    assert (
        "storyteller Embraced Vivian (player): Doctor Mirth's childe, a vampire of Malkavian,"
        " 11th generation, with 9 XP of debt." in messages
    )
    told = troupe.player.client.get("/notifications").json()["items"]
    assert any("Vivian was Embraced by Doctor Mirth" in n["summary"] for n in told)
    record = troupe.player.client.get(f"/characters/{ghoul}/embrace").json()
    assert [(e["result"], e["sire_name"], e["debt"]) for e in record["entries"]] == [
        ("vampire", "Doctor Mirth", 9)
    ]
    assert record["can_embrace"] is False


def test_the_cart_refuses_purchases_while_debt_remains(troupe: Troupe) -> None:
    ghoul = vivian(troupe)
    assert embrace(troupe.storyteller, ghoul, **VIVIAN).status_code == 200

    refused = lines(spend(troupe.player, ghoul, rating("skills", "Brawl", 5, from_rating=4)))

    assert refused[0][1] is not None
    assert "owes 9 XP of debt" in refused[0][1]
    # Once it is paid, it buys as any vampire.
    award(troupe, ghoul, 9 + 5)
    assert lines(spend(troupe.player, ghoul, rating("skills", "Brawl", 5, from_rating=4))) == [
        (5, None)
    ]


def test_lost_dots_can_be_bought_back_into_debt_from_the_cart(troupe: Troupe) -> None:
    ghoul = vivian(troupe)
    allowed = {**VIVIAN, "buy_back": []}
    assert embrace(troupe.storyteller, ghoul, **allowed).status_code == 200
    assert sheet(troupe.player, ghoul)["xp"]["debt"] == 0

    # Quietus was lost, and the Storyteller let it be bought back into debt.
    bought = lines(spend(troupe.player, ghoul, rating("disciplines", "Quietus", 2, from_rating=0)))
    assert bought == [(12, None)]
    assert sheet(troupe.player, ghoul)["xp"]["debt"] == 12 - 3
    # But only 2 dots, and nothing else.
    assert lines(spend(troupe.player, ghoul, rating("disciplines", "Auspex", 3, from_rating=2)))[0][
        1
    ]
    assert lines(spend(troupe.player, ghoul, rating("merits", "Lucky", 2, from_rating=0)))[0][1]


def test_without_the_storytellers_leave_lost_dots_take_what_is_left_over(troupe: Troupe) -> None:
    ghoul = vivian(troupe)

    found = plan(troupe.storyteller, ghoul, **{**VIVIAN, "buy_back_into_debt": False}).json()

    assert found["refused"] == (
        "Quietus 2 costs 12 XP, and 3 is left over: the Storyteller can let lost dots be"
        " bought back into XP debt (p. 298)."
    )
    one = plan(
        troupe.storyteller,
        ghoul,
        **{**VIVIAN, "buy_back_into_debt": False, "buy_back": [{"name": "Auspex", "rating": 3}]},
    ).json()
    # Auspex is in-clan for a Malkavian: 2 → 3 is 9 XP, more than the 3 left too.
    assert "Auspex 3 costs 9 XP" in one["refused"]
    too_many = plan(
        troupe.storyteller,
        ghoul,
        **{
            **VIVIAN,
            "buy_back": [{"name": "Quietus", "rating": 2}, {"name": "Auspex", "rating": 3}],
        },
    ).json()
    assert too_many["refused"] == "At most 2 lost discipline dots can be bought back."


def test_skills_and_backgrounds_bought_in_play_are_repriced(troupe: Troupe) -> None:
    ghoul = vivian(troupe, merits=[("Code of Honor", 2)])
    give_xp(troupe, ghoul, 20)
    # Bought in play, as a ghoul: Brawl 4 → 5 for 5 XP, Resources 0 → 1 for 1.
    buy(
        troupe.player,
        ghoul,
        rating("skills", "Brawl", 5, from_rating=4),
        rating("backgrounds", "Resources", 1, from_rating=0),
    )
    assert sheet(troupe.player, ghoul)["xp"]["balance"] == 14

    # A 9th generation sire: Vivian is 10th, Generation 2 with Lesser Generation.
    ancilla = {"sire": {**MALKAVIAN, "generation": 9}, "clan_merits": []}
    found = troupe.storyteller.client.post(f"/characters/{ghoul}/embrace/plan", json=ancilla).json()

    assert found["refused"] is None, found["refused"]
    assert (found["generation"], found["generation_dots"], found["lesser_flaw"]) == (
        10,
        2,
        "Lesser Generation 1",
    )
    by_step = steps(found)
    # Two times the level a dot, as for any other background: 2 + 4.
    assert [xp for _, xp in by_step["generation"]] == [-6, 0]
    # At ×2 now: Brawl 5 is 10 where it was 5; Resources 1 is 2.
    assert by_step["reprice"] == [
        ("Brawl 4 → 5, bought in play, repriced", -5),
        ("Resources 0 → 1, bought in play, repriced", -1),
    ]
    assert found["balance_after"] == 14 - 6 - 5 - 1
    done = troupe.storyteller.client.post(
        f"/characters/{ghoul}/embrace", json={**ancilla, "embraced_on": NIGHT}
    )
    assert done.status_code == 200, done.text
    assert ratings(troupe.player, ghoul, "flaws") == {"Lesser Generation 1": 1}
    repriced = [(e["reason"], e["amount"]) for e in xp_history(troupe.player, ghoul)]
    assert ("The Embrace, 10th generation: Brawl 4 → 5 repriced", -5) in repriced


def test_the_domitors_childe_keeps_its_clan_merits(troupe: Troupe) -> None:
    allow(troupe, ["vampire", "ghoul"])
    sire = new_character(troupe, troupe.player, "Old Vasquez", clan="Toreador")
    give_xp(troupe, sire, 10)
    put(troupe.player, sire, "backgrounds", "Generation", 2)
    make_home(troupe, sire)
    ghoul = ghoul_of(troupe.player, {"character_id": sire}, building_troupe_id=troupe.id)
    place(troupe.player, ghoul, [*BUILD, ("merits", "Rare Clan", 4)])
    assert complete(troupe.player, ghoul).status_code == 200
    make_home(troupe, ghoul)

    sires = troupe.storyteller.client.get(f"/characters/{ghoul}/embrace/sires").json()
    assert {"name": "Old Vasquez", "clan": "Toreador", "generation": 9}.items() <= next(
        s for s in sires if s["character_id"] == sire
    ).items()
    found = troupe.storyteller.client.post(
        f"/characters/{ghoul}/embrace/plan", json={"sire": {"character_id": sire}}
    ).json()

    assert found["refused"] is None, found["refused"]
    assert found["sire_is_domitor"] is True
    assert steps(found)["clan"] == [("Rare Clan stays: the sire was the domitor.", 0)]
    assert found["generation"] == 10


def test_over_the_merit_limit_merits_come_off_or_the_character_dies(troupe: Troupe) -> None:
    ghoul = vivian(troupe, merits=[("Code of Honor", 2), ("Clear Sighted", 3)])

    over = plan(troupe.storyteller, ghoul, clan_merits=["Rare Clan"]).json()
    assert over["refused"] == (
        "Merits come to 9 points, over the limit of 7: take merits off until they are within"
        " it (p. 297)."
    )
    assert over["dies"] is False
    assert {(r["name"], r["xp"]) for r in over["removable"]} >= {("Code of Honor", 2)}
    within = plan(
        troupe.storyteller,
        ghoul,
        clan_merits=["Rare Clan"],
        remove=[{"category": "merits", "name": "Code of Honor"}],
    ).json()
    assert within["refused"] is None, within["refused"]

    cannot = plan(
        troupe.storyteller, ghoul, clan_merits=["Restricted Clan", "Bloodline: Ananke"]
    ).json()
    assert cannot["dies"] is True
    assert "cannot conform, and dies in the Embrace" in cannot["refused"]


def test_a_caitiff_childe_chooses_its_three(troupe: Troupe) -> None:
    ghoul = vivian(troupe)
    caitiff = {"sire": {"name": "Nobody", "clan": "Caitiff", "generation": 11}}

    unchosen = troupe.storyteller.client.post(
        f"/characters/{ghoul}/embrace/plan", json=caitiff
    ).json()
    assert unchosen["refused"] == "Choose the Caitiff's three in-clan disciplines."
    chosen = troupe.storyteller.client.post(
        f"/characters/{ghoul}/embrace/plan",
        json={
            **caitiff,
            "caitiff_three": ["Auspex", "Fortitude", "Potence"],
            "two_dots": "Potence",
        },
    ).json()
    assert chosen["refused"] is None, chosen["refused"]
    assert [(d["name"], d["rating"]) for d in chosen["disciplines"]] == [
        ("Auspex", 1),
        ("Fortitude", 1),
        ("Potence", 2),
    ]


def test_a_sire_too_strong_or_too_weak_is_refused(troupe: Troupe) -> None:
    ghoul = vivian(troupe)

    weak = plan(troupe.storyteller, ghoul, sire={**MALKAVIAN, "generation": 13}).json()
    assert "thin-blooded" in weak["refused"]
    strong = plan(troupe.storyteller, ghoul, sire={**MALKAVIAN, "generation": 4}).json()
    assert "strongest a character can be" in strong["refused"]
    unknown = plan(troupe.storyteller, ghoul, sire={**MALKAVIAN, "clan": "Elves"}).json()
    assert unknown["refused"] == "Elves is not a clan or bloodline."


def test_it_dies_in_the_embrace(troupe: Troupe) -> None:
    ghoul = vivian(troupe)

    died = troupe.storyteller.client.post(
        f"/characters/{ghoul}/embrace/died",
        json={"embraced_on": NIGHT, "sire_name": "Doctor Mirth", "note": "Her heart gave out."},
    )

    assert died.status_code == 200, died.text
    character = troupe.player.client.get(f"/characters/{ghoul}").json()
    assert (character["status"], character["splat"]) == ("retired", "ghoul")
    messages = [e["message"] for e in troupe.player.client.get(f"/characters/{ghoul}/log").json()]
    assert (
        "storyteller recorded that Vivian (player) died in the Embrace; it is retired."
        " Her heart gave out." in messages
    )


def test_only_the_running_staff_embrace_a_ghoul(troupe: Troupe) -> None:
    ghoul = vivian(troupe)

    assert plan(troupe.player, ghoul).status_code == 403
    # A narrator never sees sheets.
    assert plan(troupe.narrator, ghoul).status_code == 404
    assert plan(troupe.stranger, ghoul).status_code == 404
    assert plan(troupe.assistant, ghoul).status_code == 200
    listed = troupe.player.client.get(f"/characters/{ghoul}/embrace").json()
    assert listed == {"entries": [], "can_embrace": False}
    assert troupe.lead.client.get(f"/characters/{ghoul}/embrace").json()["can_embrace"] is True
    vampire = new_character(troupe, troupe.player, "Already Dead", clan="Brujah")
    make_home(troupe, vampire)
    assert plan(troupe.storyteller, vampire).status_code == 409


# --- XP debt staff add or forgive ---------------------------------------------------


def debt(person: Person, character_id: str, change: str, amount: int, reason: str = "Why") -> Any:
    return person.client.post(
        f"/characters/{character_id}/xp/debt",
        json={"change": change, "amount": amount, "reason": reason},
    )


def test_staff_add_and_forgive_xp_debt(troupe: Troupe) -> None:
    ghoul = vivian(troupe)
    give_xp(troupe, ghoul, 3)

    added = debt(troupe.storyteller, ghoul, "add", 10, "Owed for a broken oath")
    # Its 3 unspent XP pay the first of it.
    assert added.status_code == 200, added.text
    assert added.json() == {"debt": 7, "can_change": True}
    assert debt(troupe.storyteller, ghoul, "forgive", 8).status_code == 409
    forgiven = debt(troupe.assistant, ghoul, "forgive", 2, "A kindness")
    assert forgiven.json()["debt"] == 5
    assert debt(troupe.player, ghoul, "add", 1).status_code == 403
    assert debt(troupe.narrator, ghoul, "add", 1).status_code == 404
    assert troupe.player.client.get(f"/characters/{ghoul}/xp/debt").json() == {
        "debt": 5,
        "can_change": False,
    }
    entries = [(e["kind"], e["amount"], e["reason"]) for e in xp_history(troupe.player, ghoul)]
    assert ("debt", -10, "Owed for a broken oath") in entries
    assert ("debt", 2, "A kindness") in entries
    found = sheet(troupe.player, ghoul)["xp"]
    # Debt added and forgiven is what was spent, not what was earned.
    assert (found["earned"], found["spent"], found["debt"]) == (33, 38, 5)
    messages = [e["message"] for e in troupe.player.client.get(f"/characters/{ghoul}/log").json()]
    assert (
        "storyteller added 10 XP of debt to Vivian (player), now owing 7:"
        " Owed for a broken oath" in messages
    )


def test_a_character_in_debt_buys_nothing_but_can_lower(troupe: Troupe) -> None:
    ghoul = vivian(troupe)
    give_xp(troupe, ghoul, 5)
    buy(troupe.player, ghoul, rating("skills", "Computer", 1, from_rating=0))
    assert debt(troupe.storyteller, ghoul, "add", 10).status_code == 200

    refused = lines(spend(troupe.player, ghoul, rating("skills", "Brawl", 5, from_rating=4)))
    assert "owes 6 XP of debt" in (refused[0][1] or "")
    # Taking back a dot bought since acceptance refunds it, which pays the debt.
    assert lines(spend(troupe.player, ghoul, rating("skills", "Computer", 0, from_rating=1))) == [
        (-1, None)
    ]
    assert sheet(troupe.player, ghoul)["xp"]["debt"] == 5

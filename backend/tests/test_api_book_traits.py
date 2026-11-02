"""A troupe's changes to book traits: a ban refuses the trait to the troupe's
characters, at creation and after, as a refusing check does; those who hold it keep
it, flagged; an exception still lets one character have it."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Character
from tests.api_helpers import Person, Troupe, finish, new_character
from tests.test_api_creation import pick
from tests.test_api_exceptions import give
from tests.test_api_renames import other_troupe, visit
from tests.test_api_sheets import buy, make_home_troupe_member, sheet

pytestmark = pytest.mark.usefixtures("without_bank")

LUCKY = "Lucky is banned in this troupe. Too swingy at our table."


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def change(troupe: Troupe, person: Person | None = None, **body: Any) -> Any:
    return (person or troupe.storyteller).client.put(
        f"/troupes/{troupe.id}/book-traits", json={"category": "merits", **body}
    )


def ban(troupe: Troupe, name: str = "Lucky", category: str = "merits", reason: str = "") -> None:
    response = change(troupe, category=category, name=name, banned=True, ban_reason=reason)
    assert response.status_code == 200, response.text


def homed(troupe: Troupe, name: str = "Agnes", clan: str | None = None) -> str:
    character_id = new_character(troupe, troupe.player, name, clan=clan)
    make_home_troupe_member(troupe.session, troupe, character_id)
    return character_id


def building(troupe: Troupe, name: str = "Bram") -> str:
    response = troupe.player.client.post(
        "/characters", json={"splat": "vampire", "name": name, "building_troupe_id": troupe.id}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def bought(troupe: Troupe, character_id: str, category: str, name: str, rating: int) -> None:
    """Buy a trait, approving at once what a home troupe is asked for."""
    response = buy(troupe.player, character_id, category, name, rating)
    assert response.status_code == 200, response.text
    for request in troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json():
        troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})


def problems(person: Person, character_id: str) -> list[str]:
    return [p["message"] for p in sheet(person, character_id)["problems"]]


def test_storytellers_ban_a_trait_and_players_read_it(troupe: Troupe) -> None:
    assert change(troupe, troupe.assistant, name="Lucky", banned=True).status_code == 403
    assert change(troupe, name="Juggling", banned=True).status_code == 404

    banned = change(troupe, name="Lucky", banned=True, ban_reason=" Too swingy at our table. ")

    assert banned.status_code == 200, banned.text
    assert {k: banned.json()[k] for k in ("name", "banned", "ban_reason", "page")} == {
        "name": "Lucky",
        "banned": True,
        "ban_reason": "Too swingy at our table.",
        "page": "252",
    }
    listed = troupe.assistant.client.get(f"/troupes/{troupe.id}/book-traits").json()
    assert [(c["name"], c["category_name"]) for c in listed["changes"]] == [("Lucky", "Merits")]
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/book-traits").status_code == 403
    read = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()
    assert [(b["name"], b["ban_reason"]) for b in read["book_traits"]] == [
        ("Lucky", "Too swingy at our table.")
    ]
    catalogue = troupe.player.client.get(f"/rules/vampire?troupe_id={troupe.id}").json()
    lucky = next(t for t in catalogue["traits"] if t["name"] == "Lucky")
    assert (lucky["changed"]["banned"], lucky["changed"]["ban_reason"]) == (
        True,
        "Too swingy at our table.",
    )
    plain = troupe.player.client.get("/rules/vampire").json()
    assert next(t for t in plain["traits"] if t["name"] == "Lucky")["changed"] is None
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller banned Lucky in the troupe (reason: Too swingy at our table.)." in log

    lifted = change(troupe, name="Lucky", banned=False)

    assert lifted.json()["banned"] is False
    listed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/book-traits").json()
    assert (listed["changes"], listed["holders"]) == ([], [])
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller lifted the troupe's ban on Lucky." in log


def test_a_banned_merit_cannot_be_bought_and_shows_why(troupe: Troupe) -> None:
    ban(troupe, reason="Too swingy at our table.")
    home = homed(troupe)
    elsewhere = new_character(troupe, troupe.player, "Cora")

    refused = buy(troupe.player, home, "merits", "Lucky", 2)

    assert refused.status_code == 409
    assert refused.json()["detail"] == LUCKY
    unavailable = troupe.player.client.get(
        f"/characters/{home}/unavailable", params={"category": "merits"}
    ).json()
    assert unavailable["Lucky"] == LUCKY
    # A character with no home troupe plays by the book.
    assert buy(troupe.player, elsewhere, "merits", "Lucky", 2).status_code == 200


def test_a_banned_merit_cannot_be_picked_at_creation(troupe: Troupe) -> None:
    ban(troupe)
    character_id = building(troupe)

    assert pick(troupe.player, character_id, "merits", "Lucky", 2).status_code == 409
    assert pick(troupe.player, character_id, "merits", "Acute Sense", 1).status_code == 200


def test_a_banned_clan_cannot_be_chosen_at_creation(troupe: Troupe) -> None:
    ban(troupe, "Brujah", "clan", "No Brujah in this city.")
    character_id = building(troupe)

    refused = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": "Brujah", "rating": None},
    )

    assert refused.status_code == 409
    assert refused.json()["detail"] == "Brujah is banned in this troupe. No Brujah in this city."
    unavailable = troupe.player.client.get(
        f"/characters/{character_id}/unavailable", params={"category": "clan"}
    ).json()
    assert unavailable["Brujah"].startswith("Brujah is banned")
    assert "Brujah: True Brujah" not in unavailable
    chosen = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": "Brujah: True Brujah", "rating": None},
    )
    assert chosen.status_code == 200, chosen.text


def test_those_who_hold_a_banned_trait_keep_it_flagged(troupe: Troupe) -> None:
    home = homed(troupe)
    bought(troupe, home, "merits", "Lucky", 2)
    being_built = building(troupe)
    finish(troupe, being_built)
    assert buy(troupe.player, being_built, "merits", "Lucky", 2).status_code == 200
    npc = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs", json={"name": "Odd One"}
    ).json()["id"]

    ban(troupe, reason="Too swingy at our table.")

    held = next(t for t in sheet(troupe.player, home)["traits"] if t["name"] == "Lucky")
    assert held["rating"] == 2
    assert LUCKY in problems(troupe.player, home)
    holders = troupe.storyteller.client.get(f"/troupes/{troupe.id}/book-traits").json()["holders"]
    assert [(h["character_name"], h["name"], h["excepted"]) for h in holders] == [
        ("Agnes", "Lucky", False),
        ("Bram", "Lucky", False),
    ]
    # Other changes to the sheet go on as before.
    assert buy(troupe.player, home, "merits", "Acute Sense", 1).status_code == 200
    # Staff building an NPC may use it: not even flagged.
    rated = troupe.storyteller.client.put(
        f"/characters/{npc}/npc/ratings", json={"category": "merits", "name": "Lucky", "rating": 2}
    )
    assert rated.status_code == 200, rated.text
    assert LUCKY not in problems(troupe.storyteller, npc)


def test_raising_a_banned_trait_already_held_is_refused(troupe: Troupe) -> None:
    home = homed(troupe)
    bought(troupe, home, "backgrounds", "Resources", 1)
    ban(troupe, "Resources", "backgrounds")

    assert buy(troupe.player, home, "backgrounds", "Resources", 2).status_code == 409
    assert buy(troupe.player, home, "backgrounds", "Allies", 1).status_code == 200


def test_an_exception_lets_one_character_have_a_banned_trait(troupe: Troupe) -> None:
    ban(troupe, reason="Too swingy at our table.")
    home = homed(troupe)

    given = give(
        troupe.storyteller, home, name="Lucky", rating=2, despite=True, reason="A plot reward"
    )

    assert given.status_code == 200, given.text
    assert LUCKY not in problems(troupe.player, home)
    [holder] = troupe.storyteller.client.get(f"/troupes/{troupe.id}/book-traits").json()["holders"]
    assert (holder["name"], holder["excepted"]) == ("Lucky", True)


def test_a_joining_character_holding_a_banned_trait_is_flagged(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    assert buy(troupe.player, character_id, "merits", "Lucky", 2).status_code == 200
    ban(troupe)

    asked = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )

    assert asked.status_code in (200, 201), asked.text
    [request] = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()
    assert request["banned"] == ["Lucky"]


# --- House wording ----------------------------------------------------------------------------

AWE = "Draws every eye; **one** target per turn here."


def test_storytellers_give_a_trait_house_wording_and_players_read_it(troupe: Troupe) -> None:
    body: dict[str, Any] = {"category": "disciplines", "name": "Presence", "wording": AWE}
    assert change(troupe, troupe.assistant, **body).status_code == 403

    worded = change(troupe, **body)

    assert worded.status_code == 200, worded.text
    assert (worded.json()["wording"], worded.json()["wording_mode"]) == (AWE, "added")
    catalogue = troupe.player.client.get(f"/rules/vampire?troupe_id={troupe.id}").json()
    presence = next(t for t in catalogue["traits"] if t["name"] == "Presence")
    assert presence["changed"] == {
        "banned": False,
        "ban_reason": "",
        "wording": AWE,
        "wording_mode": "added",
        "kind": None,
        "book_kind": None,
    }
    read = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()
    assert [(b["name"], b["wording"]) for b in read["book_traits"]] == [("Presence", AWE)]
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller set the troupe's wording for Presence, added to the book's." in log

    replaced = change(troupe, category="disciplines", name="Presence", wording_mode="replaces")
    assert (replaced.json()["wording"], replaced.json()["wording_mode"]) == (AWE, "replaces")
    # A ban and wording are kept together: removing the wording leaves the ban.
    change(troupe, category="disciplines", name="Presence", banned=True)
    removed = change(troupe, category="disciplines", name="Presence", wording="  ")
    assert (removed.json()["wording"], removed.json()["banned"]) == ("", True)
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller removed the troupe's wording for Presence." in log
    change(troupe, category="disciplines", name="Presence", banned=False)
    listed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/book-traits").json()
    assert (listed["changes"], listed["holders"]) == ([], [])


def test_house_wording_is_the_troupes_own_and_follows_the_home_troupe(troupe: Troupe) -> None:
    change(troupe, category="disciplines", name="Presence", wording=AWE)
    elsewhere = other_troupe(troupe)
    home = homed(troupe)
    bought(troupe, home, "disciplines", "Presence", 1)
    # A character at home elsewhere, visiting this troupe, reads its home troupe's.
    visitor = new_character(troupe, troupe.player, "Cora")
    assert buy(troupe.player, visitor, "disciplines", "Presence", 1).status_code == 200
    troupe.session.get_one(Character, uuid.UUID(visitor)).home_troupe_id = uuid.UUID(elsewhere)
    troupe.session.flush()
    visit(troupe.player, visitor, troupe.id)

    def play_wording(character_id: str) -> str:
        reference = troupe.player.client.get(f"/characters/{character_id}/play/reference").json()
        return next(t["wording"] for t in reference["traits"] if t["name"] == "Presence")

    assert play_wording(home) == AWE
    assert play_wording(visitor) == ""
    printed = troupe.player.client.get(f"/characters/{home}/print").json()
    assert [(w["name"], w["text"], w["mode"]) for w in printed["wording"]] == [
        ("Presence", AWE, "added")
    ]
    other = troupe.player.client.get(f"/rules/vampire?troupe_id={elsewhere}").json()
    assert next(t for t in other["traits"] if t["name"] == "Presence")["changed"] is None


# --- Category -------------------------------------------------------------------------------


def recategorise(troupe: Troupe, name: str, kind: str, category: str = "merits") -> Any:
    return change(troupe, category=category, name=name, kind=kind)


def catalogued(troupe: Troupe, name: str) -> dict[str, Any]:
    found = troupe.player.client.get(f"/rules/vampire?troupe_id={troupe.id}").json()
    return next(t for t in found["traits"] if t["name"] == name)


def test_a_sect_flaw_made_general_is_listed_and_taken_as_one(troupe: Troupe) -> None:
    assert recategorise(troupe, "Soul Shard", "Nonsense", "flaws").status_code == 422
    assert recategorise(troupe, "Presence", "General", "disciplines").status_code == 422
    assert catalogued(troupe, "Soul Shard")["kind"] == "Sabbat"

    made = recategorise(troupe, "Soul Shard", "General", "flaws")

    assert made.status_code == 200, made.text
    assert (made.json()["kind"], made.json()["book_kind"]) == ("General", "Sabbat")
    soul_shard = catalogued(troupe, "Soul Shard")
    assert soul_shard["kind"] == "General"
    assert (soul_shard["changed"]["kind"], soul_shard["changed"]["book_kind"]) == (
        "General",
        "Sabbat",
    )
    camarilla = homed(troupe, clan="Ventrue")
    troupe.player.client.put(
        f"/characters/{camarilla}/traits",
        json={"category": "sect", "name": "Camarilla", "rating": None},
    )
    bought(troupe, camarilla, "flaws", "Soul Shard", 3)
    held = [t["name"] for t in sheet(troupe.player, camarilla)["traits"]]
    assert "Soul Shard" in held
    read = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()
    assert [(b["name"], b["kind"], b["book_kind"]) for b in read["book_traits"]] == [
        ("Soul Shard", "General", "Sabbat")
    ]
    listed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/book-traits").json()
    assert "Sabbat" in listed["kinds"]["vampire"]["flaws"]
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller made Soul Shard General in the troupe (by the book: Sabbat)." in log

    # Its book category again is no change at all.
    assert recategorise(troupe, "Soul Shard", "", "flaws").json()["kind"] is None
    assert catalogued(troupe, "Soul Shard")["changed"] is None
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller put Soul Shard back in its book category, Sabbat." in log


def test_a_clan_merit_made_general_leaves_its_clan_requirement_behind(troupe: Troupe) -> None:
    brujah = homed(troupe, clan="Brujah")
    refused = buy(troupe.player, brujah, "merits", "Absent Sway", 3)
    assert refused.status_code == 409
    assert "only for Toreador" in refused.json()["detail"]

    assert recategorise(troupe, "Absent Sway", "General").status_code == 200

    absent_sway = catalogued(troupe, "Absent Sway")
    assert (absent_sway["kind"], absent_sway["requirement"]) == ("General", None)
    checks = troupe.storyteller.client.get(f"/troupes/{troupe.id}/checks").json()
    assert "merits/Absent Sway/requirement" not in [c["key"] for c in checks]
    bought(troupe, brujah, "merits", "Absent Sway", 3)
    # A Toreador takes it beside a clan merit of the same value: it is no clan merit here.
    toreador = homed(troupe, "Cora", clan="Toreador")
    bought(troupe, toreador, "merits", "Ephemeral Rhapsody", 3)
    bought(troupe, toreador, "merits", "Absent Sway", 3)
    held = [t["name"] for t in sheet(troupe.player, toreador)["traits"]]
    assert {"Absent Sway", "Ephemeral Rhapsody"} <= set(held)


def test_a_category_change_that_breaks_a_check_is_flagged_not_enforced(troupe: Troupe) -> None:
    toreador = homed(troupe, clan="Toreador")
    bought(troupe, toreador, "merits", "Absent Sway", 3)
    bought(troupe, toreador, "merits", "Iron Will", 3)

    # Iron Will made a clan merit clashes with Absent Sway, of the same value.
    assert recategorise(troupe, "Iron Will", "Clan").status_code == 200

    held = [t["name"] for t in sheet(troupe.player, toreador)["traits"]]
    assert {"Absent Sway", "Iron Will"} <= set(held)
    assert any("already a clan merit of this value" in p for p in problems(troupe.player, toreador))
    # Other changes to the sheet go on.
    bought(troupe, toreador, "merits", "Acute Sense", 1)

"""A character's Retainers and Alternate Identities: each bought on its own with
its own name and dots (MET: VTM pp. 98-99, 104), and the list of Retainers with
what is kept for each, who may link an NPC, and the log."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import retainers, sheets
from horatio.models import Character, CharacterTrait, Retainer, ScheduledGame, XpEntry
from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def accepted(troupe: Troupe) -> str:
    character_id = new_character(troupe, troupe.player)
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    return character_id


def give_retainers(troupe: Troupe, character_id: str, rating: int, name: str) -> None:
    response = troupe.storyteller.client.post(
        f"/characters/{character_id}/give",
        json={
            "category": "backgrounds",
            "name": "Retainers",
            "detail": name,
            "rating": rating,
            "free": True,
            "reason": "test",
        },
    )
    assert response.status_code == 200, response.text


def put(person: Person, character_id: str, rows: list[dict[str, Any]]) -> Any:
    return person.client.put(f"/characters/{character_id}/retainers", json={"retainers": rows})


def buy(person: Person, character_id: str, name: str, detail: str, rating: int) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "backgrounds", "name": name, "detail": detail, "rating": rating},
    )


def xp(person: Person, character_id: str) -> list[tuple[str, int]]:
    entries = person.client.get(f"/characters/{character_id}/xp").json()
    return [(e["reason"], e["amount"]) for e in entries if e["kind"] == "purchase"]


MARTA = {"name": "Marta, the driver", "dots": 3, "description": "Drives."}
PIKE = {"name": "Pike", "dots": 1}


def with_both(troupe: Troupe) -> str:
    """An accepted character with Marta (3) and Pike (1) bought as Retainers."""
    character_id = accepted(troupe)
    give_retainers(troupe, character_id, 3, "Marta, the driver")
    give_retainers(troupe, character_id, 1, "Pike")
    return character_id


def make_npc(troupe: Troupe, name: str = "Marta") -> str:
    response = troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": name})
    assert response.status_code == 201, response.text
    npc_id: str = response.json()["id"]
    return npc_id


EACH = pytest.mark.parametrize("name", ["Retainers", "Alternate Identity"])


@EACH
def test_each_is_bought_on_its_own_up_to_five_with_more_than_five_in_all(
    troupe: Troupe, name: str
) -> None:
    character_id = new_character(troupe, troupe.player)

    # Without Generation the rate is 1 x each new dot: 1 + 2 + 3 for each.
    for detail in ("Bocephus", "Dr. Ellen Marsh, coroner"):
        bought = buy(troupe.player, character_id, name, detail, 3)
        assert bought.status_code == 200, bought.text
        assert bought.json()["cost"] == 6
    raised = buy(troupe.player, character_id, name, "Bocephus", 5)
    assert raised.status_code == 200, raised.text
    # Dots 4 and 5 of Bocephus: 8 in all, not dots 7 and 8 of one rating.
    assert raised.json()["cost"] == 9

    held = [
        (t["detail"], t["rating"]) for t in raised.json()["sheet"]["traits"] if t["name"] == name
    ]
    assert held == [("Bocephus", 5), ("Dr. Ellen Marsh, coroner", 3)]
    refused = buy(troupe.player, character_id, name, "Bocephus", 6)
    assert refused.status_code == 422
    assert "cannot go above 5" in refused.json()["detail"]
    # The XP history says which one each dot was for.
    assert (f"{name}: Bocephus 3 → 5", -9) in xp(troupe.player, character_id)


@EACH
def test_each_needs_a_name(troupe: Troupe, name: str) -> None:
    character_id = new_character(troupe, troupe.player)

    refused = buy(troupe.player, character_id, name, "  ", 1)

    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("Name each ")


def test_creation_picks_name_each_one(troupe: Troupe) -> None:
    building = new_character(troupe, troupe.player, "Bertha", finished=False)
    url = f"/characters/{building}/creation/categories/backgrounds"

    unnamed = troupe.player.client.put(url, json={"picks": [{"name": "Retainers", "rating": 3}]})
    assert unnamed.status_code == 422
    saved = troupe.player.client.put(
        url,
        json={
            "picks": [
                {"name": "Retainers", "rating": 3, "detail": "Bocephus"},
                {"name": "Retainers", "rating": 2, "detail": "Marta"},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    picks = sorted(
        (t["detail"], t["pick"])
        for pool in saved.json()["pools"]
        if pool["category"] == "backgrounds"
        for t in pool["traits"]
    )
    assert picks == [("Bocephus", 3), ("Marta", 2)]


def test_one_held_without_a_name_stays_the_first_with_its_xp(
    troupe: Troupe, session: Session
) -> None:
    character_id = new_character(troupe, troupe.player)
    character = session.get_one(Character, uuid.UUID(character_id))
    # Bought as one rating before each Retainer had its own: 1 + 2 + 3.
    definition, _ = sheets.find_definition(session, character, "backgrounds", "Retainers")
    session.add(
        CharacterTrait(character_id=character.id, trait_definition_id=definition.id, rating=3)
    )
    session.add(
        XpEntry(
            character_id=character.id,
            kind="purchase",
            amount=-6,
            reason="Retainers 0 → 3",
            entered_by=character.player_id,
            trait_definition_id=definition.id,
            from_rating=0,
            to_rating=3,
            cost_basis={},
        )
    )
    session.flush()

    bought = buy(troupe.player, character_id, "Retainers", "Pike", 2)

    assert bought.status_code == 200, bought.text
    assert bought.json()["cost"] == 3
    assert sorted(xp(troupe.player, character_id)) == [
        ("Retainers 0 → 3", -6),
        ("Retainers: Pike 0 → 2", -3),
    ]
    body = troupe.player.client.get(f"/characters/{character_id}/retainers").json()
    assert body["rating"] == 5
    assert [(r["name"], r["dots"], r["bought"]) for r in body["retainers"]] == [
        ("", 3, True),
        ("Pike", 2, True),
    ]
    # Its dots go on as they were; it can be named.
    assert buy(troupe.player, character_id, "Retainers", "", 4).json()["cost"] == 4
    named = troupe.player.client.put(
        f"/characters/{character_id}/traits/detail",
        json={"category": "backgrounds", "name": "Retainers", "detail": "Bocephus"},
    )
    assert named.status_code == 200, named.text


def test_each_retainer_bought_is_listed_with_what_is_kept_for_it(troupe: Troupe) -> None:
    character_id = with_both(troupe)

    listed = troupe.player.client.get(f"/characters/{character_id}/retainers").json()
    assert listed["rating"] == 4
    assert [(r["name"], r["dots"], r["id"]) for r in listed["retainers"]] == [
        ("Marta, the driver", 3, None),
        ("Pike", 1, None),
    ]
    # The dots are the sheet's, whatever is sent.
    saved = put(troupe.player, character_id, [{**MARTA, "dots": 1}, PIKE])

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert [(r["name"], r["dots"], r["description"]) for r in body["retainers"]] == [
        ("Marta, the driver", 3, "Drives."),
        ("Pike", 1, ""),
    ]
    assert body["can_edit"] and not body["can_link"]
    # A Retainer not bought on the sheet cannot be added to the list.
    refused = put(troupe.player, character_id, [MARTA, {"name": "Rook", "dots": 2}])
    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("Buy Rook on the sheet first")


def test_what_is_kept_follows_a_rename_before_acceptance(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "Retainers", "Marta", 2)
    put(troupe.player, character_id, [{"name": "Marta", "dots": 2, "description": "Drives."}])

    troupe.player.client.put(
        f"/characters/{character_id}/traits/detail",
        json={"category": "backgrounds", "name": "Retainers", "detail": "Marta Voss"},
    )

    body = troupe.player.client.get(f"/characters/{character_id}/retainers").json()
    assert [(r["name"], r["description"]) for r in body["retainers"]] == [("Marta Voss", "Drives.")]


def test_each_retainer_has_a_name(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    for rows in ([{**PIKE, "name": "  "}], [PIKE, PIKE]):
        assert put(troupe.player, character_id, rows).status_code == 422


def test_one_listed_before_stays_until_removed(troupe: Troupe, session: Session) -> None:
    character_id = with_both(troupe)
    # Listed with dots of its own before Retainers were bought one by one.
    session.add(Retainer(character_id=uuid.UUID(character_id), name="Rook", dots=2, position=5))
    session.flush()

    body = troupe.player.client.get(f"/characters/{character_id}/retainers").json()
    rook = body["retainers"][2]
    assert (rook["name"], rook["dots"], rook["bought"]) == ("Rook", 2, False)
    kept = put(troupe.player, character_id, [MARTA, PIKE, {**rook, "dots": 6}])
    assert kept.status_code == 422
    kept = put(troupe.player, character_id, [MARTA, PIKE, {**rook, "description": "Old"}])
    assert kept.status_code == 200, kept.text
    assert put(troupe.player, character_id, [MARTA, PIKE]).json()["retainers"][2:] == []


def test_a_retainer_from_a_merit_is_not_part_of_the_background(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    ghost = {"name": "A wraith", "dots": 5, "from_merit": "Ghostly Retainer"}
    # Only a merit the character has.
    assert put(troupe.player, character_id, [ghost]).status_code == 409
    gave = troupe.storyteller.client.post(
        f"/characters/{character_id}/give",
        json={
            "category": "merits",
            "name": "Ghostly Retainer",
            "rating": 3,
            "free": True,
            "despite": True,
            "reason": "test",
        },
    )
    assert gave.status_code == 200, gave.text

    body = put(troupe.player, character_id, [MARTA, PIKE, ghost]).json()

    assert body["rating"] == 4
    assert [(r["name"], r["dots"], r["bought"]) for r in body["retainers"]][2:] == [
        ("A wraith", 5, False)
    ]
    assert body["retainers"][2]["from_merit"] == "Ghostly Retainer"
    # A merit's Retainer can go above 5.
    assert put(troupe.player, character_id, [{**ghost, "dots": 7}]).status_code == 200


def test_a_lost_retainer_stays_listed_with_its_date(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    row = {**PIKE, "lost": "killed", "lost_on": "2026-10-20"}

    body = put(troupe.player, character_id, [MARTA, row]).json()

    assert body["retainers"][1]["lost"] == "killed"
    assert body["retainers"][1]["lost_on"] == "2026-10-20"
    assert body["rating"] == 4


def test_only_staff_link_a_retainer_to_an_npc(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    npc_id = make_npc(troupe)
    listed = put(troupe.player, character_id, [MARTA]).json()["retainers"][0]

    # The player's attempt to link is ignored.
    body = put(troupe.player, character_id, [{**listed, "npc_id": npc_id}]).json()
    assert body["retainers"][0]["npc_id"] is None

    body = put(troupe.storyteller, character_id, [{**listed, "npc_id": npc_id}]).json()
    assert body["can_link"]
    assert body["retainers"][0]["npc_id"] == npc_id
    assert body["retainers"][0]["npc_name"] == "Marta"
    # The player edits on, and the link stays; they cannot see the NPC.
    body = put(troupe.player, character_id, [{**listed, "npc_id": None, "description": "x"}]).json()
    assert body["retainers"][0]["description"] == "x"
    assert body["retainers"][0]["npc_id"] is None
    again = troupe.storyteller.client.get(f"/characters/{character_id}/retainers").json()
    assert again["retainers"][0]["npc_id"] == npc_id


def test_a_retainer_can_be_linked_to_a_stock_npc(troupe: Troupe) -> None:
    # The book builds Retainers as Stock NPCs (p. 104).
    character_id = with_both(troupe)
    response = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs",
        json={"name": "Marta", "npc_kind": "mortal", "npc_form": "stock", "stock": {"rating": 3}},
    )
    assert response.status_code == 201, response.text
    npc_id = response.json()["id"]
    listed = put(troupe.player, character_id, [MARTA]).json()["retainers"][0]

    body = put(troupe.storyteller, character_id, [{**listed, "npc_id": npc_id}]).json()

    assert (body["retainers"][0]["npc_id"], body["retainers"][0]["npc_name"]) == (npc_id, "Marta")


def test_a_link_must_be_an_npc_of_the_home_troupe(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    other = new_character(troupe, troupe.player, "Beatrice")
    listed = put(troupe.player, character_id, [MARTA]).json()["retainers"][0]

    refused = put(troupe.storyteller, character_id, [{**listed, "npc_id": other}])

    assert refused.status_code == 409


def test_others_cannot_change_or_see_the_list(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    assert put(troupe.stranger, character_id, [PIKE]).status_code == 404
    assert put(troupe.narrator, character_id, [PIKE]).status_code == 404
    assert put(troupe.assistant, character_id, [PIKE]).status_code == 200


def test_changes_are_on_the_characters_log(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    listed = put(troupe.player, character_id, [MARTA, PIKE]).json()["retainers"]
    put(troupe.player, character_id, [{**listed[0], "description": "x", "lost": "released"}])

    log = troupe.player.client.get(f"/characters/{character_id}/log").json()
    actions = [e["action"] for e in log]

    assert actions.count("retainer.added") == 2
    assert "retainer.changed" in actions
    assert "retainer.lost" in actions
    assert "retainer.removed" in actions


def test_the_printed_sheet_and_play_reference_list_them(troupe: Troupe) -> None:
    character_id = with_both(troupe)
    put(troupe.player, character_id, [MARTA, PIKE])

    printed = troupe.player.client.get(f"/characters/{character_id}/print").json()
    reference = troupe.player.client.get(f"/characters/{character_id}/play/reference").json()

    assert [r["name"] for r in printed["retainers"]] == ["Marta, the driver", "Pike"]
    assert [r["dots"] for r in reference["retainers"]] == [3, 1]


def nosferatu_with_bocephus(troupe: Troupe) -> str:
    """A Nosferatu with Bocephus, a four-dot Retainer (the book's own, p. 105)."""
    character_id = new_character(troupe, troupe.player, clan="Nosferatu")
    assert buy(troupe.player, character_id, "Retainers", "Bocephus", 4).status_code == 200
    return character_id


BOCEPHUS = {
    "name": "Bocephus",
    "dots": 4,
    "ghoul": True,
    "specialties": ["Brawl", "Stealth", "Dodge"],
    "discipline": "Obfuscate",
}


def test_each_retainer_has_its_own_pool_specialties_and_powers(troupe: Troupe) -> None:
    character_id = nosferatu_with_bocephus(troupe)

    saved = put(troupe.player, character_id, [BOCEPHUS])

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert "Obfuscate" in body["disciplines"] and "Brawl" in body["skills"]
    bocephus = body["retainers"][0]
    assert (bocephus["pool"], bocephus["health"], bocephus["blood"]) == (8, 4, 5)
    assert bocephus["specialties"] == ["Brawl", "Stealth", "Dodge"]
    assert [p["level"] for p in bocephus["powers"]] == [1, 2, 3, 4]
    assert bocephus["tracker"] == "retainer:Bocephus"


def test_a_retainers_specialties_are_one_a_dot_and_a_discipline_only_for_a_ghoul(
    troupe: Troupe,
) -> None:
    character_id = nosferatu_with_bocephus(troupe)
    for wrong in (
        {"specialties": ["Brawl", "Stealth", "Dodge", "Melee"]},
        {"specialties": ["Brawl", "Brawl"]},
        {"specialties": ["Juggling"]},
        {"discipline": "Dominate"},
    ):
        refused = put(troupe.player, character_id, [{**BOCEPHUS, **wrong}])
        assert refused.status_code == 422, wrong

    # Not a ghoul: no discipline, no Blood.
    body = put(troupe.player, character_id, [{**BOCEPHUS, "ghoul": False}]).json()
    assert (body["retainers"][0]["discipline"], body["retainers"][0]["blood"]) == ("", 0)


def test_a_retainers_health_and_blood_are_tapped_at_a_game(troupe: Troupe) -> None:
    character_id = nosferatu_with_bocephus(troupe)
    put(troupe.player, character_id, [BOCEPHUS])
    taps = [
        {
            "id": str(uuid.uuid4()),
            "happened_at": f"2026-10-24T20:0{n}:00+00:00",
            "kind": "change",
            "tracker": f"retainer:Bocephus/{what}",
            "amount": -1,
        }
        for n, what in enumerate(("health", "blood", "blood"))
    ]

    response = troupe.player.client.post(
        f"/characters/{character_id}/play/taps", json={"taps": taps}
    )

    assert response.status_code == 200, response.text
    state = response.json()
    [tracked] = state["retainers"]
    assert tracked["name"] == "Bocephus"
    assert (tracked["health"]["value"], tracked["health"]["most"]) == (3, 4)
    assert (tracked["blood"]["value"], tracked["blood"]["most"]) == (3, 5)
    assert "Bocephus: Blood 4 → 3" in [e["text"] for e in state["log"]]


def test_each_identity_is_listed_with_its_rating_and_who_accepts_it(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    for name, dots in (("Dr. Ellen Marsh, coroner", 1), ("Father Kell", 4)):
        assert buy(troupe.player, character_id, "Alternate Identity", name, dots).status_code == 200
    url = f"/characters/{character_id}/identities"

    saved = troupe.player.client.put(
        url, json={"identities": [{"name": "Father Kell", "accepted_by": "the Sabbat"}]}
    )

    assert saved.status_code == 200, saved.text
    listed = saved.json()["identities"]
    assert [(i["name"], i["dots"], i["accepted_by"]) for i in listed] == [
        ("Dr. Ellen Marsh, coroner", 1, ""),
        ("Father Kell", 4, "the Sabbat"),
    ]
    assert listed[0]["line"].startswith("Shallow")
    assert listed[1]["line"].startswith("Built to infiltrate another clan or sect")
    refused = troupe.player.client.put(url, json={"identities": [{"name": "Nobody"}]})
    assert refused.status_code == 409
    assert troupe.stranger.client.get(url).status_code == 404
    for path in ("print", "play/reference"):
        found = troupe.player.client.get(f"/characters/{character_id}/{path}").json()
        assert [i["name"] for i in found["identities"]] == [
            "Dr. Ellen Marsh, coroner",
            "Father Kell",
        ]


def test_a_lost_retainer_is_back_after_two_weeks_or_one_game_a_dot_whichever_is_longer() -> None:
    lost = date(2026, 10, 3)
    fortnightly = [date(2026, 10, 3), date(2026, 10, 10), date(2026, 10, 24), date(2026, 11, 21)]

    # Two dots: four weeks, by which time two games have gone by.
    assert retainers.returns(lost, 2, fortnightly) == retainers.Return(
        date(2026, 10, 31), 2, date(2026, 10, 31)
    )
    # Three dots: six weeks are up on 14 November, but the third game is the 21st.
    assert retainers.returns(lost, 3, fortnightly).on == date(2026, 11, 22)
    # Four: the schedule doesn't have a fourth game yet.
    four = retainers.returns(lost, 4, fortnightly)
    assert (four.earliest, four.games, four.on) == (date(2026, 11, 28), 4, None)
    assert four.away(date(2027, 1, 1))
    # One dot with no games scheduled: still out, however long.
    assert retainers.returns(lost, 1, []).away(date(2027, 1, 1))


def test_a_lost_retainer_says_when_its_dots_come_back(troupe: Troupe, session: Session) -> None:
    character_id = with_both(troupe)
    lost_on = date.today() - timedelta(days=7)
    for days in (3, 10):
        ends = datetime.combine(lost_on + timedelta(days=days), time(23), tzinfo=UTC)
        session.add(
            ScheduledGame(
                troupe_id=uuid.UUID(troupe.id), starts_at=ends - timedelta(hours=5), ends_at=ends
            )
        )
    session.flush()

    body = put(
        troupe.player,
        character_id,
        [{**MARTA, "lost": "killed", "lost_on": lost_on.isoformat()}, PIKE],
    ).json()

    marta, pike = body["retainers"]
    # Three dots: six weeks, and three games, of which two are scheduled.
    assert marta["back_from"] == (lost_on + timedelta(weeks=6)).isoformat()
    assert (marta["back_games"], marta["back_on"], marta["away"]) == (3, None, True)
    assert (pike["back_on"], pike["away"]) == (None, False)

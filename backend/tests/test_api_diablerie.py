"""Diablerie (MET: VTM p. 306): the home troupe's staff record one, or a player asks;
Generation goes up one, free, techniques the new Generation cannot hold are refunded,
earlier buys keep their cost, Humanity or Beast traits follow, and the date shows."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import Character, CharacterTrait, TraitDefinition, XpEntry
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_cart import rating, sheet
from tests.test_api_generation_until_accepted import (
    balance,
    buy,
    generation,
    give_xp,
    history,
    make_home,
    neonate,
)
from tests.test_api_play import view

pytestmark = pytest.mark.usefixtures("without_bank")

NIGHT = "2026-10-24"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def record(person: Person, character_id: str, **body: Any):  # noqa: ANN201
    return person.client.post(
        f"/characters/{character_id}/diablerie", json={"committed_on": NIGHT, **body}
    )


def plan(person: Person, character_id: str, **query: Any):  # noqa: ANN201
    return person.client.get(f"/characters/{character_id}/diablerie/plan", params=query)


def traits(person: Person, character_id: str) -> dict[str, tuple[int | None, int]]:
    return {
        t["name"]: (t["rating"], t["free_rating"]) for t in sheet(person, character_id)["traits"]
    }


def accepted_neonate(troupe: Troupe, to: int = 2) -> str:
    """A Brujah built at Generation 1 and raised to `to` with XP, then accepted."""
    character_id = neonate(troupe)
    give_xp(troupe, character_id, 100)
    if to > 1:
        buy(troupe.player, character_id, generation(to, 1))
    make_home(troupe, character_id)
    return character_id


def put_trait(
    troupe: Troupe, character_id: str, category: str, name: str, rating: int, free: int = 0
) -> None:
    """A trait on the sheet without going through the rules, for set-up."""
    definition = troupe.session.scalars(
        select(TraitDefinition).where(TraitDefinition.name == name)
    ).first()
    assert definition is not None, name
    troupe.session.add(
        CharacterTrait(
            character_id=uuid.UUID(character_id),
            trait_definition_id=definition.id,
            rating=rating,
            free_rating=free,
        )
    )
    troupe.session.flush()


def test_a_storyteller_records_a_diablerie_and_adjusts_humanity(troupe: Troupe) -> None:
    character_id = accepted_neonate(troupe)
    xp = balance(troupe.player, character_id)
    before = traits(troupe.player, character_id)
    assert before["Generation"][0] == 2
    assert before["Humanity"] == (5, 5)

    filled = plan(troupe.storyteller, character_id).json()
    # The form fills in Humanity −1 for a character who follows Humanity.
    assert (filled["from_generation"], filled["to_generation"]) == (2, 3)
    assert (filled["humanity_lowered"], filled["beast_traits"]) == (1, 0)
    assert filled["techniques"] == [] and filled["refused"] is None

    done = record(
        troupe.storyteller,
        character_id,
        victim="Prince Marcus",
        note="At the Elysium fire",
        humanity_lowered=2,
    )

    assert done.status_code == 200, done.text
    after = traits(troupe.player, character_id)
    # Generation goes up one, as a free dot; Humanity falls with no XP back.
    assert after["Generation"] == (3, before["Generation"][1] + 1)
    assert after["Humanity"] == (3, 3)
    assert balance(troupe.player, character_id) == xp
    free = history(troupe.player, character_id, "purchase")[-1]
    assert free == ("Generation 2 → 3, free by exception: diablerie, 2 → 3", 0)
    # Not repriced: earlier buys keep their cost.
    assert history(troupe.player, character_id, "reprice") == []

    # The date shows, and who was diablerized is for staff only.
    listed = troupe.player.client.get(f"/characters/{character_id}/diablerie").json()
    [entry] = listed["entries"]
    assert (entry["committed_on"], entry["victim"], entry["note"]) == (
        NIGHT,
        None,
        "At the Elysium fire",
    )
    assert (listed["can_record"], listed["can_ask"]) == (False, True)
    seen = troupe.storyteller.client.get(f"/characters/{character_id}/diablerie").json()
    assert seen["entries"][0]["victim"] == "Prince Marcus"
    assert seen["can_record"] is True
    printed = troupe.player.client.get(f"/characters/{character_id}/print").json()
    assert printed["diablerie"] == [NIGHT]

    # The player is told.
    told = troupe.player.client.get("/notifications").json()["items"]
    assert any("diablerie of 24 Oct 2026" in n["summary"] for n in told), told


def test_a_technique_the_new_generation_cannot_hold_comes_off_with_its_xp(troupe: Troupe) -> None:
    character_id = neonate(troupe)
    give_xp(troupe, character_id, 30)
    buy(
        troupe.player,
        character_id,
        generation(2, 1),
        generation(3, 2),
        rating("disciplines", "Potence", 2, from_rating=1),
        rating("disciplines", "Presence", 2, from_rating=1),
        rating("techniques", "Fearful Blow", 1, from_rating=0),
    )
    make_home(troupe, character_id)
    xp = balance(troupe.player, character_id)
    kept = history(troupe.player, character_id, "purchase")

    found = plan(troupe.assistant, character_id).json()
    assert found["techniques"] == [
        {"name": "Fearful Blow", "detail": "", "rating": 1, "refund": 20}
    ]

    done = record(troupe.assistant, character_id)

    assert done.status_code == 200, done.text
    assert "Fearful Blow" not in traits(troupe.player, character_id)
    assert traits(troupe.player, character_id)["Generation"][0] == 4
    # One line gives it back, and the earlier purchases are as they were.
    assert balance(troupe.player, character_id) == xp + 20
    lines = history(troupe.player, character_id, "purchase")
    assert lines[: len(kept)] == kept
    assert [line for line in lines if "lost to diablerie" in line[0]] == [
        ("Fearful Blow 1 → 0 (lost to diablerie)", 20)
    ]
    assert history(troupe.player, character_id, "reprice") == []


def test_a_character_on_a_path_gets_beast_traits_at_its_next_game(troupe: Troupe) -> None:
    character_id = accepted_neonate(troupe)
    humanity = troupe.session.scalars(
        select(CharacterTrait)
        .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
        .where(
            CharacterTrait.character_id == uuid.UUID(character_id),
            TraitDefinition.name == "Humanity",
        )
    ).one()
    path = troupe.session.scalars(
        select(TraitDefinition).where(TraitDefinition.name == "Blood")
    ).first()
    assert path is not None
    humanity.trait_definition_id = path.id
    # The Path merit keeps the conversion from turning back.
    put_trait(troupe, character_id, "merits", "Path of Blood", 2, free=2)

    # The form fills in 4 Beast traits and no loss of Morality.
    filled = plan(troupe.storyteller, character_id).json()
    assert (filled["morality"], filled["on_path"]) == ("Blood", True)
    assert (filled["humanity_lowered"], filled["beast_traits"]) == (0, 4)
    assert view(troupe.player, character_id)["beast"]["value"] == 0

    assert record(troupe.storyteller, character_id).status_code == 200

    play = view(troupe.player, character_id)
    assert (play["beast"]["value"], play["beast"]["start"]) == (4, 4)
    assert traits(troupe.player, character_id)["Blood"] == (5, 5)
    # They begin the next game with it, and the one after starts clear.
    started = troupe.player.client.post(
        f"/characters/{character_id}/play/taps",
        json={
            "taps": [
                {
                    "id": str(uuid.uuid4()),
                    "happened_at": "2026-10-24T20:00:00+00:00",
                    "kind": "change",
                    "tracker": "blood",
                    "amount": -1,
                }
            ]
        },
    )
    assert started.status_code == 200, started.text
    assert started.json()["beast"]["value"] == 4
    again = troupe.player.client.post(f"/characters/{character_id}/play/reset", json={})
    assert again.json()["beast"]["value"] == 0


def test_staff_can_give_a_humanity_character_beast_traits_instead(troupe: Troupe) -> None:
    character_id = accepted_neonate(troupe)

    done = record(troupe.storyteller, character_id, humanity_lowered=0, beast_traits=2)

    assert done.status_code == 200, done.text
    assert traits(troupe.player, character_id)["Humanity"] == (5, 5)
    assert view(troupe.player, character_id)["beast"]["value"] == 2


def test_a_player_asks_and_a_storyteller_approves(troupe: Troupe) -> None:
    character_id = accepted_neonate(troupe)
    xp = balance(troupe.player, character_id)

    asked = troupe.player.client.post(
        f"/characters/{character_id}/diablerie/ask",
        json={"committed_on": NIGHT, "note": "Drank my sire"},
    )

    assert asked.status_code == 201, asked.text
    assert traits(troupe.player, character_id)["Generation"][0] == 2
    # One at a time.
    twice = troupe.player.client.post(
        f"/characters/{character_id}/diablerie/ask", json={"committed_on": NIGHT}
    )
    assert twice.status_code == 409
    [waiting] = troupe.lead.client.get(
        f"/troupes/{troupe.id}/approvals", params={"kind": "diablerie"}
    ).json()
    assert waiting["diablerie"]["committed_on"] == NIGHT
    assert waiting["diablerie"]["plan"]["to_generation"] == 3
    assert waiting["player_note"] == "Drank my sire"
    [task] = [
        i
        for i in troupe.lead.client.get("/notifications").json()["items"]
        if i["kind"] == "approval.diablerie"
    ]
    assert "committed diablerie" in task["summary"]

    approved = troupe.storyteller.client.post(
        f"/approvals/{waiting['id']}/approve",
        json={"diablerie": {"victim": "Sire", "humanity_lowered": 1}},
    )

    assert approved.status_code == 200, approved.text
    after = traits(troupe.player, character_id)
    assert (after["Generation"][0], after["Humanity"][0]) == (3, 4)
    assert balance(troupe.player, character_id) == xp
    seen = troupe.storyteller.client.get(f"/characters/{character_id}/diablerie").json()
    assert [(e["committed_on"], e["victim"]) for e in seen["entries"]] == [(NIGHT, "Sire")]
    assert seen["waiting"] is None


def test_declining_a_players_diablerie_changes_nothing(troupe: Troupe) -> None:
    character_id = accepted_neonate(troupe)
    before = sheet(troupe.player, character_id)["traits"]
    troupe.player.client.post(
        f"/characters/{character_id}/diablerie/ask", json={"committed_on": NIGHT}
    )
    [waiting] = troupe.lead.client.get(
        f"/troupes/{troupe.id}/approvals", params={"kind": "diablerie"}
    ).json()

    declined = troupe.lead.client.post(
        f"/approvals/{waiting['id']}/decline", json={"note": "Not on my watch"}
    )

    assert declined.status_code == 200, declined.text
    assert sheet(troupe.player, character_id)["traits"] == before
    listed = troupe.player.client.get(f"/characters/{character_id}/diablerie").json()
    assert listed["entries"] == [] and listed["can_ask"] is True
    told = troupe.player.client.get("/notifications").json()["items"]
    assert any("declined" in n["summary"] for n in told)


def test_a_player_can_take_back_a_request(troupe: Troupe) -> None:
    character_id = accepted_neonate(troupe)
    troupe.player.client.post(
        f"/characters/{character_id}/diablerie/ask", json={"committed_on": NIGHT}
    )

    withdrawn = troupe.player.client.delete(f"/characters/{character_id}/diablerie/ask")

    assert withdrawn.status_code == 204
    assert troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json() == []


def test_a_caitiff_at_2_goes_to_3(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, "Cait", clan="Caitiff")
    put_trait(troupe, character_id, "backgrounds", "Generation", 2, free=2)
    make_home(troupe, character_id)
    assert traits(troupe.player, character_id)["Generation"][0] == 2

    done = record(troupe.storyteller, character_id)

    assert done.status_code == 200, done.text
    assert traits(troupe.player, character_id)["Generation"][0] == 3
    # The sheet no longer flags Caitiff's limit: an exception covers it.
    problems = [p["message"] for p in sheet(troupe.player, character_id)["problems"]]
    assert not any("Caitiff cannot have more than 2" in m for m in problems)
    [exception] = sheet(troupe.player, character_id)["exceptions"]
    assert exception["name"] == "Caitiff"
    assert "Caitiff cannot have more than 2 dots of Generation" in exception["breaks"][0]


def test_generation_stops_at_its_most(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, "Elder", clan="Brujah")
    put_trait(troupe, character_id, "backgrounds", "Generation", 5, free=5)
    make_home(troupe, character_id)

    found = plan(troupe.storyteller, character_id).json()
    refused = record(troupe.storyteller, character_id)

    assert found["refused"] == "Generation is already at its most, 5."
    assert refused.status_code == 409
    assert refused.json()["detail"] == found["refused"]


def lesser(troupe: Troupe, setting: str) -> str:
    """A Brujah with Lesser Generation 1, which paid 4 XP, accepted into a troupe that
    plays diablerie as `setting`."""
    character_id = accepted_neonate(troupe, to=1)
    put_trait(troupe, character_id, "flaws", "Lesser Generation 1", 1)
    flaw = troupe.session.scalars(
        select(TraitDefinition).where(TraitDefinition.name == "Lesser Generation 1")
    ).one()
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="purchase",
            amount=4,
            reason="Lesser Generation 1 0 → 1",
            entered_by=uuid.UUID(troupe.player.id),
            trait_definition_id=flaw.id,
            from_rating=0,
            to_rating=1,
            cost_basis={},
        )
    )
    troupe.session.flush()
    changed = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/diablerie-flaws", json={"setting": setting}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["diablerie_flaws"] == setting
    return character_id


def test_only_a_storyteller_sets_what_diablerie_does_to_a_lesser_generation(
    troupe: Troupe,
) -> None:
    where = f"/troupes/{troupe.id}/diablerie-flaws"

    assert troupe.assistant.client.put(where, json={"setting": "remove"}).status_code == 403
    assert troupe.storyteller.client.put(where, json={"setting": "nonsense"}).status_code == 422
    # It starts by leaving the flaw.
    shown = troupe.player.client.get(f"/troupes/{troupe.id}").json()
    assert shown["diablerie_flaws"] == "leave"


def test_the_flaw_is_left_by_default_with_a_warning_in_the_plan(troupe: Troupe) -> None:
    character_id = lesser(troupe, "leave")
    xp = balance(troupe.player, character_id)

    found = plan(troupe.storyteller, character_id).json()
    assert found["flaw_setting"] == "leave"
    assert found["flaw"] == {
        "name": "Lesser Generation 1",
        "rating": 1,
        "setting": "leave",
        "gave": 4,
        "taken": 0,
    }
    assert record(troupe.storyteller, character_id).status_code == 200

    assert "Lesser Generation 1" in traits(troupe.player, character_id)
    assert balance(troupe.player, character_id) == xp


def test_the_flaw_and_its_xp_can_go(troupe: Troupe) -> None:
    character_id = lesser(troupe, "remove")
    xp = balance(troupe.player, character_id)

    found = plan(troupe.storyteller, character_id).json()
    assert (found["flaw"]["setting"], found["flaw"]["taken"]) == ("remove", 4)
    assert record(troupe.storyteller, character_id).status_code == 200

    assert "Lesser Generation 1" not in traits(troupe.player, character_id)
    assert balance(troupe.player, character_id) == xp - 4
    corrections = [
        e
        for e in troupe.player.client.get(f"/characters/{character_id}/xp").json()
        if e["kind"] == "correction"
    ]
    assert [(e["amount"], e["reason"]) for e in corrections] == [
        (-4, "Lesser Generation 1 removed by diablerie: the XP it gave taken back")
    ]


def test_the_flaw_can_go_and_its_xp_stay(troupe: Troupe) -> None:
    character_id = lesser(troupe, "keep_xp")
    xp = balance(troupe.player, character_id)

    assert record(troupe.storyteller, character_id).status_code == 200

    assert "Lesser Generation 1" not in traits(troupe.player, character_id)
    assert balance(troupe.player, character_id) == xp
    assert history(troupe.player, character_id, "correction") == []


def test_xp_is_taken_back_only_as_far_as_the_character_has_it(troupe: Troupe) -> None:
    character_id = lesser(troupe, "remove")
    spent = balance(troupe.player, character_id) - 1
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="fee",
            amount=-spent,
            reason="Spent",
            entered_by=uuid.UUID(troupe.player.id),
        )
    )
    troupe.session.flush()

    found = plan(troupe.storyteller, character_id).json()

    assert (found["flaw"]["gave"], found["flaw"]["taken"]) == (4, 1)


def test_a_narrator_cannot_record_or_approve_one(troupe: Troupe) -> None:
    character_id = accepted_neonate(troupe)

    # A narrator never sees a sheet at all.
    assert record(troupe.narrator, character_id).status_code == 404
    assert plan(troupe.narrator, character_id).status_code == 404
    assert record(troupe.player, character_id).status_code == 403
    assert record(troupe.stranger, character_id).status_code == 404
    troupe.player.client.post(
        f"/characters/{character_id}/diablerie/ask", json={"committed_on": NIGHT}
    )
    [waiting] = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()
    assert (
        troupe.narrator.client.post(f"/approvals/{waiting['id']}/approve", json={}).status_code
        == 403
    )
    assert traits(troupe.player, character_id)["Generation"][0] == 2


def test_a_character_without_a_home_troupe_has_no_diablerie(troupe: Troupe) -> None:
    character_id = neonate(troupe)

    asked = troupe.player.client.post(
        f"/characters/{character_id}/diablerie/ask", json={"committed_on": NIGHT}
    )

    assert asked.status_code == 409
    assert "a home troupe has accepted" in asked.json()["detail"]
    character = troupe.session.get_one(Character, uuid.UUID(character_id))
    assert character.home_troupe_id is None

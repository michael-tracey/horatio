"""A ghoul at a game and elsewhere a vampire is assumed (MET: VtM core pp. 296–297):
its Blood is part vitae and part human, it drinks vitae rather than feeding, and it
has no Beast, Generation or diablerie."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Character
from tests.api_helpers import Troupe, new_character
from tests.test_api_ghouls import allow, finished_ghoul, ghoul_of, pick, typed
from tests.test_api_play import reset, send, tap, texts, view
from tests.test_api_sheets import buy

pytestmark = pytest.mark.usefixtures("ghoul_rules")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def at_home(troupe: Troupe, character_id: str) -> None:
    """The character joins the troupe, which takes ghouls, and is accepted there."""
    allow(troupe, ["vampire", "ghoul"])
    joined = troupe.player.client.post(
        f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id}
    )
    assert joined.status_code == 201, joined.text
    troupe.session.get_one(Character, uuid.UUID(character_id)).home_troupe_id = uuid.UUID(troupe.id)
    troupe.session.flush()


@pytest.fixture
def renfield(troupe: Troupe) -> str:
    """A finished ghoul of a Toreador not in Horatio, at home in the troupe."""
    ghoul = finished_ghoul(troupe)
    at_home(troupe, ghoul)
    return ghoul


# --- the Play View ------------------------------------------------------------------------


def test_a_ghoul_has_five_vitae_and_five_human_blood(troupe: Troupe, renfield: str) -> None:
    state = view(troupe.player, renfield)

    assert state["splat"] == "ghoul"
    assert state["blood"] == {"value": 5, "most": 5, "start": 5}
    assert state["blood_per_turn"] == 1
    assert state["vitae"] == {
        "pool": 10,
        "human": 5,
        "human_start": 5,
        "last_drank_at": None,
        "days": 30,
    }
    # No Generation, Beast, Morality or Feed.
    assert state["generation"] == 0
    assert state["morality"] is None
    assert state["panels"] == {
        "beast": False,
        "frenzy": False,
        "morality": False,
        "generation": False,
        "feed": False,
    }


def test_vitae_is_spent_and_human_blood_is_not(troupe: Troupe, renfield: str) -> None:
    state = send(troupe.player, renfield, tap(at=1), tap(at=2))

    assert state["blood"]["value"] == 3
    # Spent vitae leaves the pool: it comes back as human Blood a day at a time.
    assert state["vitae"]["human"] == 5
    assert texts(state)[0] == "Vitae 4 → 3"
    # Human Blood is no tracker a tap can spend, and Beast traits are not tapped.
    refused = troupe.player.client.post(
        f"/characters/{renfield}/play/taps", json={"taps": [tap("human")]}
    )
    assert refused.status_code == 422
    state = send(troupe.player, renfield, tap("beast", 1, at=3))
    assert state["beast"]["value"] == 0
    assert texts(state)[0] == "Beast traits +1 (not on the sheet now)"
    # Never below none.
    state = send(troupe.player, renfield, *(tap(at=4 + i) for i in range(5)))
    assert state["blood"]["value"] == 0


def test_drinking_vitae_fills_up_to_five(troupe: Troupe, renfield: str) -> None:
    send(troupe.player, renfield, *(tap(at=i) for i in range(4)))

    state = send(troupe.player, renfield, tap("drank", 3, at=10))

    assert state["blood"]["value"] == 4
    # The pool had room, so no human Blood was turned to vitae.
    assert state["vitae"]["human"] == 5
    assert texts(state)[0] == "Drank 3 vitae: Vitae 1 → 4"
    assert state["vitae"]["last_drank_at"] is not None

    # Into a full pool, vitae takes the place of human Blood; never more than 5.
    send(troupe.player, renfield, tap("drank", 1, at=11))
    state = send(troupe.player, renfield, tap("drank", 5, at=12))
    assert state["blood"]["value"] == 5
    assert state["vitae"]["human"] == 5
    assert texts(state)[0] == "Drank 5 vitae: Vitae 5 → 5"


def test_vitae_carries_through_a_reset_and_human_blood_refills(
    troupe: Troupe, renfield: str
) -> None:
    send(troupe.player, renfield, tap(at=1), tap(at=2), tap(at=3))

    state = reset(troupe.player, renfield)

    # Vitae comes back only by drinking; the rest of the pool is human Blood again.
    assert state["blood"] == {"value": 2, "most": 5, "start": 2}
    assert state["vitae"]["human"] == 8
    assert state["vitae"]["human_start"] == 8

    # A late tap in the game already over moves where this one started.
    game = troupe.player.client.get(f"/characters/{renfield}/play/games").json()[0]
    state = send(troupe.player, renfield, tap("drank", 2, at=4, game_id=game["id"]))
    assert state["blood"]["start"] == 4


def test_when_a_ghoul_last_drank(troupe: Troupe, renfield: str) -> None:
    drink = tap("drank", 1, at=5)
    state = send(troupe.player, renfield, drink)
    assert state["vitae"]["last_drank_at"].startswith("2026-10-17T20:05")

    # An undone drink is no drink.
    undo = {
        "id": str(uuid.uuid4()),
        "happened_at": (datetime(2026, 10, 17, 20, 6, tzinfo=UTC)).isoformat(),
        "kind": "undo",
        "undoes": drink["id"],
    }
    state = send(troupe.player, renfield, undo)
    assert state["vitae"]["last_drank_at"] is None


def test_a_vampire_has_no_vitae_to_drink(troupe: Troupe, session: Session) -> None:
    vampire = new_character(troupe, troupe.player)

    state = send(troupe.player, vampire, tap("drank", 2))

    assert state["vitae"] is None
    assert state["panels"]["feed"] is True
    assert state["beast"] == {"value": 0, "most": 5, "start": 0}
    assert state["blood"]["value"] == 10


def test_a_malkavian_domitors_ghoul_has_no_derangement_trait(troupe: Troupe) -> None:
    ghoul = ghoul_of(troupe.player, typed("Anatole", "Malkavian"))

    state = view(troupe.player, ghoul)

    # A ghoul plays its domitor's weakness for roleplay only (p. 297).
    assert state["derangements"]["least"] == 0
    reference = troupe.player.client.get(f"/characters/{ghoul}/play/reference").json()
    assert reference["domitor"]["name"] == "Anatole"
    assert reference["domitor"]["clan"] == "Malkavian"
    assert "Malkavian weakness, for roleplay only" in reference["domitor"]["weakness"]


def test_the_scene_view_shows_a_ghouls_human_blood(troupe: Troupe, renfield: str) -> None:
    send(troupe.player, renfield, tap(at=1))
    vampire = new_character(troupe, troupe.player, "Agnes")
    at_home(troupe, vampire)

    found = {
        c["character_name"]: c
        for c in troupe.storyteller.client.get(f"/troupes/{troupe.id}/play").json()
    }

    assert found["Renfield"]["blood"]["value"] == 4
    assert found["Renfield"]["human_blood"] == 5
    assert found["Agnes"]["human_blood"] is None


# --- elsewhere ----------------------------------------------------------------------------


def test_a_ghoul_cannot_commit_diablerie(troupe: Troupe, renfield: str) -> None:
    found = troupe.storyteller.client.get(f"/characters/{renfield}/diablerie").json()
    assert found["can_record"] is False
    assert troupe.player.client.get(f"/characters/{renfield}/diablerie").json()["can_ask"] is False
    plan = troupe.storyteller.client.get(f"/characters/{renfield}/diablerie/plan")
    assert "A ghoul cannot commit diablerie." in plan.text


def test_the_roster_shows_a_ghoul_and_its_domitors_clan(troupe: Troupe, renfield: str) -> None:
    roster = troupe.storyteller.client.get(f"/troupes/{troupe.id}/characters")

    assert roster.status_code == 200, roster.text
    entry = next(e for e in roster.json() if e["character_name"] == "Renfield")
    # No Generation, so no social age: it is a ghoul.
    assert (entry["clan"], entry["social_age"]) == ("Toreador", "Ghoul")

    # A filter can name what only a ghoul's sheet has.
    search = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/characters/search",
        json={
            "match": "all",
            "items": [
                {"what": "count", "which": "domitor_in_clan_disciplines", "op": "gte", "value": 0}
            ],
        },
    )
    assert search.status_code == 200, search.text


def test_a_ghoul_has_no_bonus_above_ten_in_an_attribute(troupe: Troupe) -> None:
    ghoul = finished_ghoul(troupe)
    for rating in range(8, 11):
        bought = buy(troupe.player, ghoul, "attributes", "Physical", rating)
        assert bought.status_code == 200, bought.text

    # A vampire without Generation counts as Generation 1; a ghoul has none (p. 102).
    over = buy(troupe.player, ghoul, "attributes", "Physical", 11)
    assert over.status_code == 409, over.text
    assert "Attributes can go above 10" in over.text


def test_a_merit_for_neonates_is_not_a_ghouls(troupe: Troupe) -> None:
    ghoul = ghoul_of(troupe.player, typed())

    # Machiavellian Prodigy is for a Neonate or Ancilla; a ghoul is neither.
    refused = pick(troupe.player, ghoul, "merits", "Machiavellian Prodigy", 1)

    assert refused.status_code == 409, refused.text
    assert "only for Neonate or Ancilla characters" in refused.text


def test_a_ghoul_does_not_feed_in_downtimes(troupe: Troupe, renfield: str) -> None:
    from tests.test_api_downtimes import my_downtime, new_cycle, open_cycle

    cycle = open_cycle(troupe, new_cycle(troupe))

    assert my_downtime(troupe.player, renfield).json()["feeding"] is None
    staff = troupe.storyteller.client.get(f"/cycles/{cycle['id']}/feeding").json()
    assert staff["characters"] == []


def test_the_printed_sheet_has_vitae_and_human_blood(troupe: Troupe, renfield: str) -> None:
    sheet = troupe.player.client.get(f"/characters/{renfield}/print").json()

    assert sheet["blood"] == {"most": 5, "per_turn": 1, "pool": 10}
    assert sheet["domitor"] == "Lady Vasquez"

    vampire = new_character(troupe, troupe.player, "Agnes")
    printed = troupe.player.client.get(f"/characters/{vampire}/print").json()
    assert printed["blood"] == {"most": 10, "per_turn": 1, "pool": None}
    assert printed["domitor"] is None


# --- house rules for each splat -----------------------------------------------------------


def test_a_troupe_prices_ghouls_apart(troupe: Troupe) -> None:
    def costs(splat: str) -> Any:
        return troupe.storyteller.client.get(f"/troupes/{troupe.id}/costs?splat={splat}")

    # Only for a splat the troupe takes.
    assert costs("ghoul").status_code == 404
    allow(troupe, ["vampire", "ghoul"])
    ghoul = costs("ghoul").json()
    assert "domitor_in_clan_disciplines" not in [c["key"] for c in ghoul["categories"]]
    attributes = [c for c in ghoul["costs"] if c["category"] == "attributes"]
    assert [c["price_text"] for c in attributes] == ["3 XP per dot"]

    added = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/costs?splat=ghoul",
        json={"category": "attributes", "scheme": "per_dot", "rate": 2},
    )
    assert added.status_code == 201, added.text
    assert not [c for c in costs("vampire").json()["costs"] if c["house"]]
    assert [c["price_text"] for c in costs("ghoul").json()["costs"] if c["house"]] == [
        "2 XP per dot"
    ]
    log = troupe.storyteller.client.get(f"/troupes/{troupe.id}/log").json()
    assert any("Attributes for ghouls" in e["message"] for e in log)

    starting = troupe.storyteller.client.get(f"/troupes/{troupe.id}/creation?splat=ghoul")
    assert "disciplines" in [c["key"] for c in starting.json()]
    allowances = troupe.storyteller.client.get(f"/troupes/{troupe.id}/allowances?splat=ghoul")
    assert allowances.status_code == 200, allowances.text


def test_a_ghoul_drinks_rather_than_waits(troupe: Troupe, renfield: str) -> None:
    """The reminder's clock is the last drink: the Play View says when it was."""
    state = send(troupe.player, renfield, tap("drank", 1, at=-60 * 24 * 40))
    drank = datetime.fromisoformat(state["vitae"]["last_drank_at"])
    assert drank < datetime(2026, 10, 17, tzinfo=UTC) - timedelta(days=30)


def test_an_npc_ghouls_worth_counts_its_starting_dots(troupe: Troupe) -> None:
    from tests.test_api_npc_kinds import made

    npc = made(troupe, name="Bocephus", npc_kind="ghoul")["id"]
    staff = troupe.storyteller.client

    def rate(category: str, name: str, rating: int | None) -> None:
        response = staff.put(
            f"/characters/{npc}/npc/ratings",
            json={"category": category, "name": name, "rating": rating, "detail": ""},
        )
        assert response.status_code == 200, response.text

    rate("clan", "Nosferatu", None)
    rate("disciplines", "Potence", 3)
    rate("disciplines", "Obfuscate", 2)
    tally = staff.get(f"/characters/{npc}/npc/tally").json()

    # A ghoul's 5 discipline dots are its starting dots, which no XP buys (p. 296).
    disciplines = [line for line in tally["lines"] if line["category"] == "disciplines"]
    assert [(line["cost"], line["note"]) for line in disciplines] == [
        (0, "starting dots"),
        (0, "starting dots"),
    ]

    rate("disciplines", "Animalism", 1)
    tally = staff.get(f"/characters/{npc}/npc/tally").json()
    assert "not allowed in this troupe" in [line["note"] for line in tally["lines"]]


def test_staff_bind_an_npc_ghoul_to_its_domitor(troupe: Troupe) -> None:
    from tests.test_api_npc_kinds import made

    npc = made(troupe, name="Igor", npc_kind="ghoul")["id"]

    bound = troupe.storyteller.client.put(f"/characters/{npc}/domitor", json=typed())

    assert bound.status_code == 200, bound.text
    reference = troupe.storyteller.client.get(f"/characters/{npc}/play/reference").json()
    assert reference["domitor"]["clan"] == "Toreador"


def test_once_embraced_its_play_view_is_a_vampires(troupe: Troupe) -> None:
    """The Embrace (part 6) makes the ghoul a vampire: its vitae and human Blood
    give way to a vampire's Blood, and the Beast and Feed come back."""
    from tests.test_api_embrace import VIVIAN, embrace, vivian

    ghoul = vivian(troupe)
    send(troupe.player, ghoul, tap(at=1), tap("drank", 1, at=2))
    assert view(troupe.player, ghoul)["vitae"] is not None

    done = embrace(troupe.storyteller, ghoul, **VIVIAN)
    assert done.status_code == 200, done.text

    state = view(troupe.player, ghoul)
    assert state["splat"] == "vampire"
    assert state["vitae"] is None
    assert state["blood_name"] == "Blood"
    assert state["panels"]["beast"] and state["panels"]["feed"]
    assert troupe.player.client.get(f"/characters/{ghoul}/play/reference").json()["domitor"] is None
    printed = troupe.player.client.get(f"/characters/{ghoul}/print").json()
    assert printed["blood"]["pool"] is None
    assert printed["domitor"] is None

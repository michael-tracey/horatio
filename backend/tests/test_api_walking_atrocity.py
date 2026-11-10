"""Walking Atrocity (Vol. 2, p. 205, issue #603): a free bonus attribute dot for each
dot Morality is below 5, placed by the player; one more each time Morality drops,
one given up if it rises. The dots raise their attribute's maximum with them, up to
5 bonus dots in one attribute with Generation's."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitCategory, TraitDefinition
from tests.api_helpers import Troupe
from tests.test_api_free_choices import balance, given, pick
from tests.test_api_grants import ratings, sheet, take
from tests.test_api_powers import vampire
from tests.test_api_sheets import make_home_troupe_member

POWER = "Daimoinon: Walking Atrocity"
GRANT = "elder_disciplines/Daimoinon: Walking Atrocity/1"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def set_morality(session: Session, character_id: str, name: str, rating: int) -> None:
    """The character's Morality, as staff or a diablerie leave it: Humanity or a Path."""
    row = session.scalars(
        select(CharacterTrait)
        .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(
            CharacterTrait.character_id == uuid.UUID(character_id),
            TraitCategory.key == "paths",
        )
    ).one()
    row.trait_definition_id = session.scalars(
        select(TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(TraitCategory.key == "paths", TraitDefinition.name == name)
    ).one()
    row.rating = row.free_rating = rating
    session.flush()


def atrocity(troupe: Troupe, humanity: int = 5, generation: int = 3) -> str:
    """A Baali elder who has learned Walking Atrocity, at this Humanity."""
    character_id = vampire(
        troupe,
        "Baali",
        generation,
        ("disciplines", "Daimoinon", 5),
        ("elder_disciplines", POWER, 1),
    )
    set_morality(troupe.session, character_id, "Humanity", humanity)
    return character_id


def offer(troupe: Troupe, character_id: str) -> dict[str, Any]:
    power = next(t for t in sheet(troupe.player, character_id)["traits"] if t["name"] == POWER)
    [found] = power["free_choices"]
    return found


def place(troupe: Troupe, character_id: str, picks: list[dict[str, Any]]) -> Any:
    return troupe.player.client.put(
        f"/characters/{character_id}/traits/choices",
        json={"category": "elder_disciplines", "name": POWER, "picks": picks},
    )


def test_a_dot_to_place_for_each_dot_of_morality_below_5(troupe: Troupe) -> None:
    at_5 = atrocity(troupe)
    at_3 = atrocity(troupe, humanity=3)

    assert offer(troupe, at_5)["dots"] == 0
    assert offer(troupe, at_5)["complete"] is True
    shown = offer(troupe, at_3)
    assert (shown["dots"], shown["most"], shown["complete"], shown["locked"]) == (2, 5, False, None)
    assert shown["grant"] == GRANT
    assert [o["name"] for o in shown["options"]] == ["Mental", "Physical", "Social"]


def test_a_path_is_morality_too(troupe: Troupe) -> None:
    character_id = atrocity(troupe)
    set_morality(troupe.session, character_id, "Evil Revelations", 4)

    assert offer(troupe, character_id)["dots"] == 1


def test_the_placed_dots_are_free_and_say_where_they_came_from(troupe: Troupe) -> None:
    character_id = atrocity(troupe, humanity=3)
    take(troupe.player, character_id, "attributes", "Physical", 7)
    take(troupe.player, character_id, "attributes", "Social", 5)
    before = balance(troupe.player, character_id)

    placed = place(troupe, character_id, [pick(GRANT, "Physical", 2)])

    assert placed.status_code == 200, placed.text
    assert given(troupe.player, character_id, "attributes") == {"Physical": (9, 2, [POWER])}
    assert balance(troupe.player, character_id) == before
    assert offer(troupe, character_id)["complete"] is True


def test_no_more_dots_than_morality_gives(troupe: Troupe) -> None:
    character_id = atrocity(troupe, humanity=3)

    refused = place(troupe, character_id, [pick(GRANT, "Physical", 2), pick(GRANT, "Social", 1)])

    assert refused.status_code == 422
    assert "gives 2 dots to place now, not 3" in refused.json()["detail"]


def test_another_dot_each_time_morality_drops(troupe: Troupe) -> None:
    character_id = atrocity(troupe, humanity=3)
    make_home_troupe_member(troupe.session, troupe, character_id)
    assert place(troupe, character_id, [pick(GRANT, "Physical", 2)]).status_code == 200

    set_morality(troupe.session, character_id, "Humanity", 2)

    assert (offer(troupe, character_id)["dots"], offer(troupe, character_id)["complete"]) == (
        3,
        False,
    )
    # Accepted already, the new dot is still the player's to place.
    added = place(troupe, character_id, [pick(GRANT, "Physical", 2), pick(GRANT, "Social", 1)])
    assert added.status_code == 200, added.text
    assert {k: v[1] for k, v in given(troupe.player, character_id, "attributes").items()} == {
        "Physical": 2,
        "Social": 1,
    }


def test_placed_dots_stay_put_once_accepted(troupe: Troupe) -> None:
    character_id = atrocity(troupe, humanity=3)
    assert place(troupe, character_id, [pick(GRANT, "Physical", 2)]).status_code == 200
    # Before acceptance they move freely.
    moved = place(troupe, character_id, [pick(GRANT, "Mental", 1), pick(GRANT, "Social", 1)])
    assert moved.status_code == 200, moved.text
    make_home_troupe_member(troupe.session, troupe, character_id)

    refused = place(troupe, character_id, [pick(GRANT, "Physical", 2)])

    assert refused.status_code == 409
    assert "placed dots can't move once a home troupe has accepted" in refused.json()["detail"]
    assert "Physical" not in given(troupe.player, character_id, "attributes")


def test_a_dot_is_given_up_when_morality_rises(troupe: Troupe) -> None:
    character_id = atrocity(troupe, humanity=3)
    assert (
        place(troupe, character_id, [pick(GRANT, "Physical", 1), pick(GRANT, "Social", 1)])
    ).status_code == 200
    make_home_troupe_member(troupe.session, troupe, character_id)

    raised = take(troupe.player, character_id, "paths", "Humanity", 4)

    assert raised.status_code == 200, raised.text
    # One dot goes at once, the last placed; the player can choose which instead.
    assert {k: v[1] for k, v in given(troupe.player, character_id, "attributes").items()} == {
        "Physical": 1
    }
    shown = offer(troupe, character_id)
    assert (shown["dots"], shown["complete"]) == (1, False)
    kept = place(troupe, character_id, [pick(GRANT, "Social", 1)])
    assert kept.status_code == 200, kept.text
    assert {k: v[1] for k, v in given(troupe.player, character_id, "attributes").items()} == {
        "Social": 1
    }
    # The dot given up can't come back somewhere else.
    again = place(troupe, character_id, [pick(GRANT, "Mental", 1)])
    assert again.status_code == 409


def test_the_dots_raise_the_attribute_maximum_with_them(troupe: Troupe) -> None:
    # Generation 3: three points to raise a maximum, all of them used on Social.
    character_id = atrocity(troupe, humanity=2, generation=3)
    take(troupe.player, character_id, "attributes", "Physical", 10)
    assert take(troupe.player, character_id, "attributes", "Social", 13).status_code == 200

    assert place(troupe, character_id, [pick(GRANT, "Physical", 3)]).status_code == 200

    assert ratings(troupe.player, character_id, "attributes")["Physical"] == 13
    assert not [
        p for p in sheet(troupe.player, character_id)["problems"] if "above 10" in p["message"]
    ]
    # A dot bought above them still needs Generation, which Social has used.
    refused = take(troupe.player, character_id, "attributes", "Physical", 14)
    assert refused.status_code == 409
    assert "Generation rating" in refused.json()["detail"]


def test_no_more_than_5_bonus_dots_in_one_attribute(troupe: Troupe) -> None:
    character_id = atrocity(troupe, humanity=2, generation=3)
    take(troupe.player, character_id, "attributes", "Physical", 10)
    assert place(troupe, character_id, [pick(GRANT, "Physical", 3)]).status_code == 200
    # Two of Generation's three points on top: 15.
    assert take(troupe.player, character_id, "attributes", "Physical", 15).status_code == 200

    refused = take(troupe.player, character_id, "attributes", "Physical", 16)

    assert refused.status_code == 409
    assert "no more than 5 bonus dots" in refused.json()["detail"]


def test_losing_the_power_takes_the_dots_back(troupe: Troupe) -> None:
    character_id = atrocity(troupe, humanity=3)
    take(troupe.player, character_id, "attributes", "Mental", 3)
    assert place(troupe, character_id, [pick(GRANT, "Mental", 2)]).status_code == 200

    assert take(troupe.player, character_id, "elder_disciplines", POWER, 0).status_code == 200

    assert given(troupe.player, character_id, "attributes") == {}
    assert ratings(troupe.player, character_id, "attributes")["Mental"] == 3

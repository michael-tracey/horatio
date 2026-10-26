"""Creation rules from chapter 3: creation-only traits, Generation, out-of-clan
disciplines before acceptance, repeats, Caitiff (MET: VTM)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import XpEntry
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_creation import FULL_BUILD, creating, pick


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def take(
    person: Person,
    character_id: str,
    category: str,
    name: str,
    rating: int | None = 1,
    detail: str = "",
) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating, "detail": detail},
    )


def give_xp(troupe: Troupe, character_id: str, amount: int) -> None:
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="award",
            amount=amount,
            reason="Test",
            entered_by=uuid.UUID(troupe.custodian.id),
        )
    )
    troupe.session.flush()


def make_home(troupe: Troupe, character_id: str) -> None:
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})


def test_finishing_creation_needs_a_dot_of_generation(troupe: Troupe) -> None:
    character_id = creating(troupe)
    for category, name, rating in FULL_BUILD:
        if name == "Generation":
            name = "Allies"
        pick(troupe.player, character_id, category, name, rating)

    refused = troupe.player.client.post(f"/characters/{character_id}/creation/complete")

    assert refused.status_code == 409
    assert "at least 1 dot of Generation" in refused.json()["detail"]


def test_bloodline_is_creation_only(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Toreador")

    change = take(troupe.player, character_id, "merits", "Bloodline: Ishtarri", 2)

    assert change.status_code == 409
    assert "can only be chosen during character creation" in change.json()["detail"]


def test_generation_is_fixed_once_a_home_troupe_accepts_the_character(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Toreador")
    # Until then the build is still creation (test_api_generation_until_accepted).
    assert take(troupe.player, character_id, "backgrounds", "Generation", 1).status_code == 200
    make_home(troupe, character_id)

    change = take(troupe.player, character_id, "backgrounds", "Generation", 2)

    assert change.status_code == 409
    assert "once a home troupe has accepted the character" in change.json()["detail"]


def test_before_acceptance_out_of_clan_is_common_only_and_up_to_three(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Brujah")
    give_xp(troupe, character_id, 100)

    assert take(troupe.player, character_id, "disciplines", "Auspex", 3).status_code == 200
    refused = take(troupe.player, character_id, "disciplines", "Auspex", 4)
    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("Before a home troupe accepts the character")
    assert take(troupe.player, character_id, "disciplines", "Protean", 1).status_code == 409
    # In-clan disciplines are not limited.
    assert take(troupe.player, character_id, "disciplines", "Celerity", 4).status_code == 200

    make_home(troupe, character_id)

    # Afterwards the home troupe approves each dot instead.
    assert take(troupe.player, character_id, "disciplines", "Protean", 1).status_code == 200


def caitiff_build(troupe: Troupe, thin_blooded: bool) -> str:
    """A Caitiff through creation, with Auspex, Celerity and Potence in-clan."""
    character_id = creating(troupe, clan="Caitiff")
    for name in ("Auspex", "Celerity", "Potence"):
        chosen = take(troupe.player, character_id, "extra_in_clan_disciplines", name)
        assert chosen.status_code == 200, chosen.text
    if thin_blooded:
        assert pick(troupe.player, character_id, "flaws", "Thin Blooded").status_code == 200
    for category, name, rating in FULL_BUILD:
        if category == "disciplines":
            continue
        pick(troupe.player, character_id, category, name, rating)
    return character_id


def test_a_caitiff_chooses_in_clan_disciplines_while_creating(troupe: Troupe) -> None:
    character_id = caitiff_build(troupe, thin_blooded=False)
    for name, rating in (("Celerity", 2), ("Auspex", 1), ("Potence", 1)):
        assert pick(troupe.player, character_id, "disciplines", name, rating).status_code == 200

    finished = troupe.player.client.post(f"/characters/{character_id}/creation/complete")

    assert finished.status_code == 200, finished.text


def test_thin_blooded_start_with_one_dot_in_two_disciplines(troupe: Troupe) -> None:
    character_id = caitiff_build(troupe, thin_blooded=True)
    pools = troupe.player.client.get(f"/characters/{character_id}/creation").json()["pools"]

    assert [(p["rating"], p["allowed"]) for p in pools if p["category"] == "disciplines"] == [
        (1, 2)
    ]
    for name in ("Celerity", "Auspex"):
        assert pick(troupe.player, character_id, "disciplines", name, 1).status_code == 200
    finished = troupe.player.client.post(f"/characters/{character_id}/creation/complete")
    assert finished.status_code == 200, finished.text
    give_xp(troupe, character_id, 100)

    assert take(troupe.player, character_id, "disciplines", "Celerity", 4).status_code == 200
    refused = take(troupe.player, character_id, "disciplines", "Celerity", 5)
    assert refused.status_code == 409
    assert "Thin Blooded" in refused.json()["detail"]


def test_thin_blooded_vampires_are_caitiff(troupe: Troupe) -> None:
    character_id = creating(troupe)

    refused = pick(troupe.player, character_id, "flaws", "Thin Blooded")

    assert refused.status_code == 409
    assert "always Caitiff" in refused.json()["detail"]


def test_humanity_stops_at_six(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert take(troupe.player, character_id, "paths", "Humanity", 6).status_code == 200
    assert take(troupe.player, character_id, "paths", "Humanity", 7).status_code == 409


def test_traits_are_taken_once_unless_they_say_otherwise(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    take(troupe.player, character_id, "merits", "Acute Sense", 1, "Sight")
    assert take(troupe.player, character_id, "merits", "Acute Sense", 1, "Smell").status_code == 409
    take(troupe.player, character_id, "merits", "Skill Aptitude", 2, "Brawl")
    assert (
        take(troupe.player, character_id, "merits", "Skill Aptitude", 2, "Dodge").status_code == 200
    )
    for n, detail in enumerate(["Stealth", "Awareness", "Lore", "Occult"], 1):
        response = take(troupe.player, character_id, "flaws", "Cursed", 1, detail)
        assert response.status_code == (200 if n <= 3 else 409), detail


def test_caitiff_choose_three_common_in_clan_disciplines(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Caitiff")

    for name in ("Auspex", "Celerity", "Potence"):
        chosen = take(troupe.player, character_id, "extra_in_clan_disciplines", name)
        assert chosen.status_code == 200, (name, chosen.text)
    fourth = take(troupe.player, character_id, "extra_in_clan_disciplines", "Dominate")
    other = new_character(troupe, troupe.player, clan="Caitiff")
    uncommon = take(troupe.player, other, "extra_in_clan_disciplines", "Protean")

    assert (fourth.status_code, uncommon.status_code) == (409, 409)


def test_a_clan_does_not_take_extra_in_clan_disciplines_without_a_merit(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Brujah")

    refused = take(troupe.player, character_id, "extra_in_clan_disciplines", "Auspex")

    assert refused.status_code == 409


def test_unspent_creation_xp_past_five_is_lost_on_first_acceptance(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    take(troupe.player, character_id, "skills", "Brawl", 2)  # a Neonate pays 1 + 2
    assert (
        troupe.player.client.get(f"/characters/{character_id}/sheet").json()["xp"]["unbanked"] == 22
    )

    make_home(troupe, character_id)

    after = troupe.player.client.get(f"/characters/{character_id}/sheet").json()["xp"]
    assert (after["balance"], after["unbanked"]) == (5, 0)
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert (history[-1]["kind"], history[-1]["amount"]) == ("fee", -22)


def test_crafts_performance_and_science_need_a_field(troupe: Troupe) -> None:
    character_id = creating(troupe)
    for category, name, rating in FULL_BUILD:
        if name == "Melee":
            name = "Performance"
        pick(troupe.player, character_id, category, name, rating)

    refused = troupe.player.client.post(f"/characters/{character_id}/creation/complete")
    assert refused.status_code == 409
    assert "need a field" in refused.json()["detail"]

    troupe.player.client.put(
        f"/characters/{character_id}/creation/categories/skills",
        json={
            "picks": [
                {
                    "name": name,
                    "rating": rating,
                    "detail": "Singing" if name == "Performance" else "",
                }
                for category, name, rating in FULL_BUILD
                if category == "skills"
                for name in ["Performance" if name == "Melee" else name]
            ]
        },
    )
    assert (
        troupe.player.client.post(f"/characters/{character_id}/creation/complete").status_code
        == 200
    )

    unnamed = take(troupe.player, character_id, "skills", "Science", 1)
    assert unnamed.status_code == 409
    assert take(troupe.player, character_id, "skills", "Science", 1, "Biology").status_code == 200


def test_an_accepted_flaw_is_bought_off_for_twice_its_value(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    take(troupe.player, character_id, "flaws", "Dark Secret", 1)
    make_home(troupe, character_id)
    before = troupe.player.client.get(f"/characters/{character_id}/sheet").json()["xp"]["balance"]

    bought_off = take(troupe.player, character_id, "flaws", "Dark Secret", 0)

    assert bought_off.status_code == 200, bought_off.text
    assert bought_off.json()["cost"] == 2
    assert bought_off.json()["sheet"]["xp"]["balance"] == before - 2

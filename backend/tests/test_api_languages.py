"""A troupe chooses how many languages Linguistics gives: the book's one per dot, the
accelerated chart or its own, with Natural Linguist doubling it or not. Purchases,
the sheet and the House rules tab follow; characters already over are flagged."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitCategory, TraitDefinition
from tests.api_helpers import Troupe, finish

LANGUAGES = "linguistics_specializations"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def built_for(troupe: Troupe, name: str = "Agnes") -> str:
    """A character built for the troupe, so playing by its rules."""
    response = troupe.player.client.post(
        "/characters", json={"splat": "vampire", "name": name, "building_troupe_id": troupe.id}
    )
    assert response.status_code == 201, response.text
    character_id: str = response.json()["id"]
    finish(troupe, character_id)
    return character_id


def put(
    troupe: Troupe, character_id: str, category: str, name: str, rating: int = 1, detail: str = ""
) -> None:
    """A trait on the sheet without going through the rules, for set-up."""
    definition = troupe.session.scalars(
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(TraitCategory.key == category, TraitDefinition.name == name)
    ).first()
    assert definition is not None, name
    troupe.session.add(
        CharacterTrait(
            character_id=uuid.UUID(character_id),
            trait_definition_id=definition.id,
            rating=rating,
            detail=detail,
        )
    )
    troupe.session.flush()


def learn(troupe: Troupe, character_id: str, language: str) -> Any:
    return troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": LANGUAGES, "name": "Custom", "detail": language, "rating": 1},
    )


def choose(troupe: Troupe, **body: Any) -> Any:
    return troupe.storyteller.client.put(f"/troupes/{troupe.id}/languages", json=body)


def languages_kind(troupe: Troupe, character_id: str) -> dict[str, Any]:
    kinds = troupe.player.client.get(f"/characters/{character_id}/specializations").json()
    return next(k for k in kinds if k["category"] == LANGUAGES)


def test_the_book_gives_one_a_dot_until_staff_choose_the_accelerated_chart(troupe: Troupe) -> None:
    agnes = built_for(troupe)
    put(troupe, agnes, "skills", "Linguistics", 3)
    for language in ("Basque", "Welsh", "Breton"):
        assert learn(troupe, agnes, language).status_code == 200
    refused = learn(troupe, agnes, "Cornish")
    assert refused.status_code == 409
    assert "one Linguistics specialisation per dot" in refused.json()["detail"]
    read = troupe.storyteller.client.get(f"/troupes/{troupe.id}/languages").json()
    assert (read["mode"], read["natural_doubles"], read["table"][:5]) == (
        "book",
        True,
        [1, 2, 3, 4, 5],
    )
    assert read["max_rating"] == 10
    assert (
        troupe.assistant.client.put(
            f"/troupes/{troupe.id}/languages", json={"mode": "accelerated"}
        ).status_code
        == 403
    )

    chosen = choose(troupe, mode="accelerated")

    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["table"] == [1, 2, 4, 8, 16, 24, 32, 32, 32, 32]
    assert learn(troupe, agnes, "Cornish").status_code == 200
    refused = learn(troupe, agnes, "Manx")
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "This troupe's chart: 1, 2, 4, 8, 16, 24 and 32 languages at Linguistics 1 to 7,"
        " and 32 above. (House rule — Lords of the Night)"
    )
    # The sheet's Languages section counts against the chart.
    kind = languages_kind(troupe, agnes)
    assert (kind["counted"], kind["allowed"]) == (4, 4)
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert (
        "storyteller set how many languages Linguistics gives: 1, 2, 4, 8, 16, 24 and 32"
        " languages at Linguistics 1 to 7, and 32 above (the accelerated chart); Natural"
        " Linguist doubles it." in log
    )
    other = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()["other"]
    shown = next(o for o in other if o["name"] == "Languages from Linguistics")
    assert shown["table"] == [1, 2, 4, 8, 16, 24, 32]
    assert shown["book_text"].startswith("One per dot of Linguistics")


def test_natural_linguist_doubles_the_chart_unless_the_troupe_says_not(troupe: Troupe) -> None:
    agnes = built_for(troupe)
    put(troupe, agnes, "skills", "Linguistics", 2)
    put(troupe, agnes, "merits", "Natural Linguist")
    assert languages_kind(troupe, agnes)["allowed"] == 4

    choose(troupe, mode="accelerated")
    assert languages_kind(troupe, agnes)["allowed"] == 4

    choose(troupe, mode="accelerated", natural_doubles=False)
    assert languages_kind(troupe, agnes)["allowed"] == 2
    choose(troupe, mode="book", natural_doubles=False)
    assert languages_kind(troupe, agnes)["allowed"] == 2
    assert learn(troupe, agnes, "Basque").status_code == 200
    assert learn(troupe, agnes, "Welsh").status_code == 200
    refused = learn(troupe, agnes, "Breton")
    assert refused.status_code == 409
    assert "Natural Linguist gives no more languages here" in refused.json()["detail"]


def test_a_troupe_sets_its_own_chart(troupe: Troupe) -> None:
    agnes = built_for(troupe)
    put(troupe, agnes, "skills", "Linguistics", 2)
    assert choose(troupe, mode="custom").status_code == 422
    assert choose(troupe, mode="custom", custom=[3, 2]).status_code == 422
    assert choose(troupe, mode="custom", custom=[1] * 11).status_code == 422
    assert choose(troupe, mode="custom", custom=[1, 1000]).status_code == 422

    chosen = choose(troupe, mode="custom", custom=[2, 5, 6])

    assert chosen.status_code == 200, chosen.text
    assert (chosen.json()["custom"], chosen.json()["table"][:4]) == ([2, 5, 6], [2, 5, 6, 6])
    assert languages_kind(troupe, agnes)["allowed"] == 5
    # Going back to the book keeps the troupe's chart for later.
    back = choose(troupe, mode="book")
    assert (back.json()["custom"], back.json()["table"][1]) == ([2, 5, 6], 2)
    assert choose(troupe, mode="custom").json()["table"][1] == 5


def test_characters_over_a_smaller_chart_are_flagged_not_changed(troupe: Troupe) -> None:
    choose(troupe, mode="accelerated")
    agnes = built_for(troupe)
    built_for(troupe, "Bram")
    put(troupe, agnes, "skills", "Linguistics", 3)
    for language in ("Basque", "Welsh", "Breton", "Cornish"):
        assert learn(troupe, agnes, language).status_code == 200
    assert choose(troupe, mode="accelerated").json()["over"] == []

    smaller = choose(troupe, mode="book")

    assert [(o["name"], o["held"], o["allowed"]) for o in smaller.json()["over"]] == [
        ("Agnes", 4, 3)
    ]
    sheet = troupe.player.client.get(f"/characters/{agnes}/sheet").json()
    assert sum(1 for t in sheet["traits"] if t["category"] == LANGUAGES) == 4
    assert any(
        p["category"] == LANGUAGES and "one Linguistics specialisation per dot" in p["message"]
        for p in sheet["problems"]
    )
    kind = languages_kind(troupe, agnes)
    assert (kind["counted"], kind["allowed"]) == (4, 3)

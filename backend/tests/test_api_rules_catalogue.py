"""The rules catalogue as sent (issue #642): what a trait or category has comes
through, and what is still at its default (no house rule, no weakness, not derived)
is left out, which keeps the catalogue small."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.app import app
from tests.api_helpers import Troupe

pytestmark = pytest.mark.usefixtures("without_bank")

# Bytes. With every empty field sent, the catalogue was 589 KB and the rules browser
# 772 KB; without them, 254 KB and 428 KB (Nov 2026).
CATALOGUE_BUDGET = 300_000
BROWSER_BUDGET = 500_000


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def catalogue(troupe: Troupe) -> dict[str, Any]:
    response = troupe.player.client.get("/rules/vampire")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_catalogue_and_the_rules_browser_stay_small(troupe: Troupe) -> None:
    for params in ({}, {"troupe_id": troupe.id}):
        sent = troupe.player.client.get("/rules/vampire", params=params)
        assert len(sent.content) < CATALOGUE_BUDGET
        browsed = troupe.player.client.get("/rules/vampire/browse", params=params)
        assert len(browsed.content) < BROWSER_BUDGET


def test_a_trait_has_what_it_has_and_nothing_empty(troupe: Troupe) -> None:
    traits = {(t["category"], t["name"]): t for t in catalogue(troupe)["traits"]}

    performance = traits["skills", "Performance"]
    assert set(performance) == {
        "category",
        "name",
        "description",
        "page_reference",
        "attribute",
        "needs_field",
    }
    assert (performance["attribute"], performance["needs_field"]) == ("Social", True)
    assert "needs_field" not in traits["skills", "Brawl"]
    toreador = traits["clan", "Toreador"]
    assert toreador["in_clan"] == ["Auspex", "Celerity", "Presence"]
    assert toreador["weakness_page"] == "61"
    sway = traits["merits", "Absent Sway"]
    assert (sway["fixed_rating"], sway["kind"], sway["requirement"]) == (3, "Clan", "Toreador")
    assert sway["page_reference"] == "243"
    assert sway["description"]
    assert traits["merits", "Personal Cult"]["choices"] == ["Haven", "Herd", "Resources"]
    assert traits["backgrounds", "Retainers"]["instance"] == "Retainer"
    # A trait with nothing more to say is its name, its summary and its page.
    assert set(traits["archetype", "Architect"]) == {
        "category",
        "name",
        "description",
        "page_reference",
    }


def test_a_category_has_what_it_has_and_nothing_empty(troupe: Troupe) -> None:
    categories = {c["key"]: c for c in catalogue(troupe)["categories"]}

    assert categories["clan"] == {
        "key": "clan",
        "name": "Clan",
        "group": "Identity",
        "rated": False,
    }
    assert categories["faction"]["requires"] == {"category": "sect", "name": "Sabbat"}
    assert categories["skills"]["max_rating"] == 10
    assert categories["focus_physicals"]["change_cost"] == 10
    assert categories["health_levels"]["derived"] is True
    assert categories["lore_specializations"]["specializes"] == {
        "category": "skills",
        "name": "Lore",
    }
    assert categories["merits"]["points_limit"] == 7
    assert "derived" not in categories["skills"]


def test_the_schema_says_what_may_be_left_out() -> None:
    """The frontend's types come from the schema: a field left out must be optional
    there, with no default it would take as always present."""
    schemas = app.openapi()["components"]["schemas"]

    assert schemas["TraitOut"]["required"] == ["category", "name"]
    assert schemas["CategoryOut"]["required"] == ["key", "name", "group", "rated"]
    for name in ("TraitOut", "CategoryOut", "HouseOut", "TraitChangeOut", "RarityOut"):
        assert all("default" not in p for p in schemas[name]["properties"].values()), name

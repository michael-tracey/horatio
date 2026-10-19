"""One clan merit of each point value (MET: VTM Volume 2 Issue 1, p. 25), and the
unavailable list worked out as the wizard has it ticked."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.rules.checks import Context, violations
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import SheetTrait
from tests.api_helpers import Troupe, new_character

CLASH = (
    "{} is already a clan merit of this value; a character takes only one clan merit"
    " of each value. (Vol. 2 Issue 1, p. 25)"
)


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def take(troupe: Troupe, character_id: str, name: str, rating: int, detail: str = "") -> Any:
    return troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "merits", "name": name, "rating": rating, "detail": detail},
    )


def unavailable(troupe: Troupe, character_id: str, **params: Any) -> dict[str, str]:
    response = troupe.player.client.get(
        f"/characters/{character_id}/unavailable", params={"category": "merits", **params}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_second_clan_merit_of_the_same_value_is_refused(troupe: Troupe) -> None:
    tremere = new_character(troupe, troupe.player, clan="Tremere")
    assert take(troupe, tremere, "Talisman", 3).status_code == 200

    assert unavailable(troupe, tremere)["Spellslinger"] == CLASH.format("Talisman")
    refused = take(troupe, tremere, "Spellslinger", 3)
    assert refused.status_code == 409
    assert "Talisman is already a clan merit of this value" in refused.json()["detail"]
    # Another value, or a general merit of the same value, is fine.
    assert "Quick Caster" not in unavailable(troupe, tremere)
    assert take(troupe, tremere, "Quick Caster", 2).status_code == 200


def test_the_exceptions_the_books_allow(troupe: Troupe) -> None:
    tremere = new_character(troupe, troupe.player, clan="Tremere")

    # Ritual Master may be taken with Thaumaturgic Expertise (Vol. 2 Issue 1, p. 41).
    expertise = take(troupe, tremere, "Thaumaturgic Expertise", 1, "Thaumaturgy: Lure of Flames")
    assert expertise.status_code == 200, expertise.text
    assert "Ritual Master" not in unavailable(troupe, tremere)


def test_bloodline_merits_do_not_count() -> None:
    """Bloodline merits never stop another clan merit of their value (p. 25)."""
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    kinds = {k: t.properties["type"] for k, t in rules.traits.items() if "type" in t.properties}

    def merit(name: str) -> SheetTrait:
        rating = rules.trait_properties("merits", name)["rating"]
        return SheetTrait(category="merits", name=name, rating=rating, free_rating=0)

    def clashes(*names: str) -> list[str]:
        sheet = [SheetTrait(category="clan", name="Tremere", rating=None, free_rating=0)]
        found = violations(rules.checks, sheet + [merit(n) for n in names], Context(kinds=kinds))
        return [v.subject.name for v in found if "clan merit of this value" in v.message]

    assert clashes("Bloodline: Telyav", "Quick Caster") == []  # both 2 points
    assert clashes("Ritual Fluency", "Quick Caster") == ["Ritual Fluency", "Quick Caster"]


def test_the_wizard_sees_its_ticks_before_they_are_saved(troupe: Troupe) -> None:
    tremere = new_character(troupe, troupe.player, clan="Tremere", finished=False)

    ticked = unavailable(troupe, tremere, as_if="picks", picks=["Talisman"])
    assert ticked["Spellslinger"] == CLASH.format("Talisman")
    assert "Talisman" not in ticked  # what is ticked stays tickable
    # Untick it, and both are free again.
    assert "Spellslinger" not in unavailable(troupe, tremere, as_if="picks", picks=[])


def test_what_no_choice_could_allow(troupe: Troupe) -> None:
    tremere = new_character(troupe, troupe.player, clan="Tremere")
    take(troupe, tremere, "Talisman", 3)

    empty = unavailable(troupe, tremere, as_if="empty")
    assert "Spellslinger" not in empty  # barred only by Talisman
    assert "Absent Sway" in empty  # a Toreador merit, barred whatever is chosen

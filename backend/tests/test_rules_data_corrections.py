"""Three rules-data points from checking the catalogue against the V20 LARP SRD (#411):
Intense Vitality's price, Necromantic Prowess's clan, and Retain the Quick Blood's
prerequisites."""

from collections.abc import Callable, Sequence
from functools import cache

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.rules.checks import Context, violations
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.grants import grant_from_dict, options
from horatio.rules.model import RuleSetData, SheetTrait
from tests.api_helpers import Troupe, new_character
from tests.test_api_sheets import buy

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@cache
def rules() -> RuleSetData:
    return load_rule_set(DATA_DIR / "bns_met_vampire.toml")


def t(category: str, name: str, rating: int | None = 1, detail: str = "") -> SheetTrait:
    return SheetTrait(category=category, name=name, rating=rating, free_rating=0, detail=detail)


def broken(sheet: Sequence[SheetTrait], about: str) -> list[str]:
    """Messages of the checks the sheet breaks about the trait named `about`."""
    return [
        v.message for v in violations(rules().checks, sheet, Context()) if v.subject.name == about
    ]


def properties(category: str, name: str) -> dict[str, object]:
    return dict(rules().trait_properties(category, name))


# --- Intense Vitality ------------------------------------------------------------------


def test_intense_vitality_is_three_points_or_two_for_neonates_and_ancillae() -> None:
    """A 3-point merit that Neonates and Ancillae buy for 2 (p. 251): the catalogue has
    an entry for each price."""
    assert properties("merits", "Intense Vitality")["rating"] == 2
    assert properties("merits", "Intense Vitality (Elder)")["rating"] == 3

    for generation in (1, 2):
        neonate = [t("backgrounds", "Generation", generation), t("merits", "Intense Vitality", 2)]
        assert broken(neonate, "Intense Vitality") == []
    elder = [t("backgrounds", "Generation", 3), t("merits", "Intense Vitality", 2)]
    assert broken(elder, "Intense Vitality") == [
        "Intense Vitality is only for Neonate or Ancilla characters. (p. 251)"
    ]
    elder = [t("backgrounds", "Generation", 3), t("merits", "Intense Vitality (Elder)", 3)]
    assert broken(elder, "Intense Vitality (Elder)") == []


# --- Necromantic Prowess ---------------------------------------------------------------


def test_necromantic_prowess_is_a_nagaraja_merit_bought_for_one_path() -> None:
    assert properties("merits", "Necromantic Prowess") == {
        "rating": 1,
        "type": "Clan",
        "requirement": "Nagaraja",
        "requires_specialization": True,
    }
    prowess = t("merits", "Necromantic Prowess", 1, "Necromancy: Mortis Path")

    assert broken([t("clan", "Nagaraja", None), prowess], "Necromantic Prowess") == []
    assert broken([t("clan", "Giovanni", None), prowess], "Necromantic Prowess") == [
        "Necromantic Prowess is only for Nagaraja. (Vol. 2, p. 61)"
    ]


def test_the_specialisation_flag_is_its_own_property() -> None:
    """`requirement` says who a trait is for; whether it is bought once per field or
    name is `requires_specialization`, never a requirement."""
    requirements = {p.get("requirement") for p in (t.properties for t in rules().traits.values())}
    assert "requires_specialization" not in requirements
    flagged = {
        name
        for (category, name), trait in rules().traits.items()
        if category in ("merits", "flaws") and trait.properties.get("requires_specialization")
    }
    assert flagged == {
        "Derangement",
        "Eerie Presence",
        "Keeper of a Sacred Text",
        "Made",
        "Necromantic Prowess",
        "Necromantic Training",
        "Thaumaturgic Training",
    }


def test_a_merit_given_by_choice_still_asks_its_field() -> None:
    nagaraja = grant_from_dict(
        {
            "key": "test",
            "source": {"category": "merits", "name": "Lichborne"},
            "kind": "free_choices",
            "target": {
                "category": "merits",
                "pool": {"types": ["Clan"], "requirement": ["Nagaraja"]},
            },
            "amount": 0,
        }
    )

    found = {o.name: o.needs_detail for o in options(nagaraja, rules(), choosing=False)}

    assert found["Necromantic Prowess"] is True
    assert found["Lichborne"] is False


def test_piece_that_remains_never_gives_necromantic_prowess() -> None:
    """Now that it names its clan, it is a clan merit of another clan's; but it opens a
    path, which Piece That Remains does not give (Vol. 2 Issue 1, p. 46)."""
    [grant] = [g for g in rules().grants if g.source["name"] == "Piece That Remains"]

    found = {o.name for o in options(grant, rules(), [t("clan", "Brujah", None)])}

    assert "Lichborne" in found
    assert "Necromantic Prowess" not in found


def test_only_a_nagaraja_buys_necromantic_prowess(troupe: Troupe) -> None:
    catalogue = troupe.player.client.get("/rules/vampire").json()
    [prowess] = [t for t in catalogue["traits"] if t["name"] == "Necromantic Prowess"]
    assert prowess["requirement"] == "Nagaraja"
    crafts = next(t for t in catalogue["traits"] if t["name"] == "Crafts")
    assert (crafts["requirement"], crafts["needs_field"]) == (None, True)

    giovanni = new_character(troupe, troupe.player, "Agnes", clan="Giovanni")
    refused = buy(
        troupe.player,
        giovanni,
        "merits",
        "Necromantic Prowess",
        1,
        detail="Necromancy: Mortis Path",
    )
    assert refused.status_code == 409
    assert "Necromantic Prowess is only for Nagaraja." in refused.json()["detail"]

    nagaraja = new_character(troupe, troupe.player, "Bram", clan="Nagaraja")
    bought = buy(
        troupe.player,
        nagaraja,
        "merits",
        "Necromantic Prowess",
        1,
        detail="Necromancy: Mortis Path",
    )
    assert bought.status_code == 200, bought.text


# --- Retain the Quick Blood ------------------------------------------------------------


def test_retain_the_quick_blood_needs_quietus_2_and_celerity_2() -> None:
    technique = t("techniques", "Retain the Quick Blood")
    need = "Retain the Quick Blood needs Quietus 2 and Celerity 2. (p. 231)"

    for quietus, celerity in [(2, 1), (1, 2), (0, 0)]:
        sheet = [t("disciplines", "Quietus", quietus), t("disciplines", "Celerity", celerity)]
        assert broken([*sheet, technique], "Retain the Quick Blood") == [need]
    sheet = [t("disciplines", "Quietus", 2), t("disciplines", "Celerity", 2)]
    assert broken([*sheet, technique], "Retain the Quick Blood") == []

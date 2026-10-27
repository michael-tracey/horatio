"""Equipment qualities in the database and the API (issue #279): loaded per rule set
like traits, read back as the rules, and served with the check an editor asks."""

from collections.abc import Callable
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.equipment import EquipmentRefused, check, equipment_rules
from horatio.models import EquipmentQuality, EquipmentTemplate, RuleSet
from horatio.rules.equipment import ItemQuality
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.store import forget_rules, sync_rule_set
from tests.api_helpers import sign_up
from tests.test_equipment import QUALITIES

VAMPIRE = load_rule_set(DATA_DIR / "bns_met_vampire.toml")


@pytest.fixture
def client(client_for: Callable[[], TestClient]) -> TestClient:
    return sign_up(client_for, "armourer").client


def rows(session: Session, splat: str) -> list[EquipmentQuality]:
    return list(
        session.scalars(
            select(EquipmentQuality)
            .join(RuleSet, EquipmentQuality.rule_set_id == RuleSet.id)
            .where(RuleSet.splat == splat)
            .order_by(EquipmentQuality.position)
        )
    )


def test_the_table_holds_every_quality_with_its_properties(session: Session) -> None:
    found = rows(session, "vampire")
    assert sorted((r.kind, r.name) for r in found) == sorted(
        (kind, name) for kind, names in QUALITIES.items() for name in names
    )
    long_range = next(r for r in found if (r.kind, r.name) == ("ranged", "Long Range"))
    assert long_range.page == "518"
    assert long_range.properties == {
        "two_handed": True,
        "excludes": ["Spread"],
        "range": "half a mile",
    }
    assert "half a mile" in long_range.effect


def test_the_rules_read_back_from_the_database_are_the_files(session: Session) -> None:
    assert equipment_rules(session, "vampire") == VAMPIRE.equipment
    templates = session.scalars(select(EquipmentTemplate).order_by(EquipmentTemplate.position))
    laptop = next(t for t in templates if t.name == "Gaming Laptop")
    assert (laptop.kind, laptop.grade, laptop.troupe_id) == ("miscellaneous", "standard", None)
    assert laptop.qualities == [
        {"name": "Superior"},
        {"name": "Customized", "detail": "video games"},
    ]


@pytest.mark.usefixtures("ghoul_rules")
def test_the_ghoul_rule_set_loads_its_own_rows(session: Session) -> None:
    assert len(rows(session, "ghoul")) == len(rows(session, "vampire"))
    assert equipment_rules(session, "ghoul") == VAMPIRE.equipment


def test_a_quality_gone_from_the_files_is_retired_and_comes_back(session: Session) -> None:
    equipment = VAMPIRE.equipment
    fewer = {k: q for k, q in equipment.qualities.items() if k != ("melee", "Trip")}
    sync_rule_set(session, replace(VAMPIRE, equipment=replace(equipment, qualities=fewer)))
    trip = next(r for r in rows(session, "vampire") if r.name == "Trip")
    assert trip.retired
    assert ("melee", "Trip") not in equipment_rules(session, "vampire").qualities

    sync_rule_set(session, VAMPIRE)
    session.refresh(trip)
    assert not trip.retired
    forget_rules(session)
    assert equipment_rules(session, "vampire") == equipment


def test_the_shared_check_reads_the_database_rules(session: Session) -> None:
    rules = equipment_rules(session, "vampire")
    facts = check(rules, "ranged", [ItemQuality("Spread"), ItemQuality("Accurate")], "standard")
    assert (facts.hands, facts.shots) == (1, 6)
    with pytest.raises(EquipmentRefused, match="can't be Quick Draw"):
        check(rules, "ranged", [ItemQuality("Long Range"), ItemQuality("Quick Draw")], "standard")


def test_get_equipment(client: TestClient) -> None:
    response = client.get("/rules/vampire/equipment")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [k["key"] for k in body["kinds"]] == ["melee", "ranged", "protective", "miscellaneous"]
    ranged = body["kinds"][1]
    assert (ranged["name"], ranged["hands"], ranged["damage"], ranged["shots"]) == (
        "Ranged weapon",
        1,
        2,
        12,
    )
    assert (ranged["range"], ranged["page"]) == ("50 steps", "517")
    assert [(g["key"], g["max_qualities"]) for g in body["grades"]] == [
        ("cheap", 1),
        ("standard", 2),
        ("special", None),
    ]
    assert len(body["qualities"]) == sum(len(n) for n in QUALITIES.values())
    customized = next(q for q in body["qualities"] if q["name"] == "Customized")
    assert customized["kind"] == "miscellaneous"
    assert customized["needs_detail"] is True
    assert customized["detail_prompt"] == "the circumstance, such as hacking"
    shotgun = next(t for t in body["templates"] if t["name"] == "Shotgun")
    assert shotgun["qualities"] == [
        {"name": "Spread", "detail": ""},
        {"name": "Accurate", "detail": ""},
    ]
    assert shotgun["facts"] == {
        "hands": 1,
        "damage": 2,
        "shots": 6,
        "range": "50 steps",
        "aggravated_against": [],
    }


def test_get_equipment_of_no_rule_set(client: TestClient) -> None:
    assert client.get("/rules/mummy/equipment").status_code == 404


def test_post_check(client: TestClient) -> None:
    rifle = {
        "kind": "ranged",
        "grade": "standard",
        "qualities": [{"name": "Accurate"}, {"name": "Long Range"}],
    }
    response = client.post("/rules/vampire/equipment/check", json=rifle)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "hands": 2,
        "damage": 2,
        "shots": 12,
        "range": "half a mile",
        "aggravated_against": [],
        "problems": [],
    }

    broken = {**rifle, "qualities": [{"name": "Long Range"}, {"name": "Quick Draw"}]}
    response = client.post("/rules/vampire/equipment/check", json=broken)
    assert response.status_code == 200, response.text
    assert response.json()["problems"] == ["Long Range needs two hands, so it can't be Quick Draw."]

    crafted = {
        "kind": "melee",
        "grade": "cheap",
        "qualities": [{"name": "Staking"}, {"name": "Artisan"}],
        "crafted": True,
    }
    response = client.post("/rules/vampire/equipment/check", json=crafted)
    assert response.json()["problems"] == []


def test_signed_out_is_refused(client_for: Callable[[], TestClient]) -> None:
    assert client_for().get("/rules/vampire/equipment").status_code == 401

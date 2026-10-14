"""The check vocabulary, on plain sheets."""

import pytest

from horatio.rules.checks import CheckData, matches, violations
from horatio.rules.model import SheetTrait


def t(category: str, name: str, rating: int | None = 1, detail: str = "") -> SheetTrait:
    return SheetTrait(category=category, name=name, rating=rating, free_rating=0, detail=detail)


BRUJAH = t("clan", "Brujah", None)
TRUE_BRUJAH = t("clan", "Brujah: True Brujah", None)
SUBJECT = t("merits", "Calm Heart")


@pytest.mark.parametrize(
    ("condition", "sheet", "expected"),
    [
        ({"clan": ["Brujah"]}, [BRUJAH], True),
        ({"clan": ["Brujah"]}, [TRUE_BRUJAH], False),
        ({"clan_family": ["Brujah"]}, [TRUE_BRUJAH], True),
        (
            {"has": {"category": "skills", "name": "Lore", "rating": 4}},
            [t("skills", "Lore", 3)],
            False,
        ),
        (
            {"has": {"category": "skills", "name": "Lore", "rating": 4}},
            [t("skills", "Lore", 4)],
            True,
        ),
        (
            {"has": {"category": "skills", "name": "Science"}},
            [t("skills", "Science", 2, "Biology")],
            True,
        ),
        (
            {
                "has_all": [
                    {"category": "skills", "name": "Lore"},
                    {"category": "skills", "name": "Occult"},
                ]
            },
            [t("skills", "Lore")],
            False,
        ),
        ({"generation": {"gte": 3}}, [t("backgrounds", "Generation", 3)], True),
        ({"generation": 3}, [], False),
        ({"on_path": True}, [t("paths", "Humanity", 5)], False),
        ({"on_path": True}, [t("paths", "Night", 4)], True),
        (
            {"count": {"category": "merits", "name_prefix": "Path of", "gte": 2}},
            [t("merits", "Path of Night"), t("merits", "Path of Caine")],
            True,
        ),
        ({"any_of": [{"clan": ["Gangrel"]}, {"clan": ["Brujah"]}]}, [BRUJAH], True),
        ({"not": {"clan": ["Brujah"]}}, [BRUJAH], False),
    ],
)
def test_conditions(condition: dict, sheet: list[SheetTrait], expected: bool) -> None:  # type: ignore[type-arg]
    assert matches(condition, sheet, SUBJECT) is expected


def test_parent_is_the_discipline_an_elder_power_belongs_to() -> None:
    power = t("elder_disciplines", "Animalism: Crimson Fury")
    parent = {"parent": {"category": "disciplines", "rating": 5}}

    assert not matches(parent, [t("disciplines", "Animalism", 4)], power)
    assert matches(parent, [t("disciplines", "Animalism", 5)], power)


def test_a_check_is_broken_only_while_its_subject_is_held() -> None:
    check = CheckData(key="k", category="merits", name="Calm Heart", forbids={"clan": ["Brujah"]})

    assert violations([check], [BRUJAH]) == []
    assert [v.subject.name for v in violations([check], [BRUJAH, SUBJECT])] == ["Calm Heart"]
    assert violations([check], [BRUJAH, t("merits", "Calm Heart", 0)]) == []


def test_subjects_by_detail_and_prefix() -> None:
    hearing = CheckData(
        key="h",
        category="merits",
        name="Acute Sense",
        detail="Hearing",
        forbids={"clan": ["Brujah"]},
    )
    paths = CheckData(
        key="p", category="merits", name_prefix="Path of", forbids={"clan": ["Brujah"]}
    )

    assert violations([hearing], [BRUJAH, t("merits", "Acute Sense", 1, "Sight")]) == []
    assert len(violations([hearing], [BRUJAH, t("merits", "Acute Sense", 1, "Hearing")])) == 1
    assert len(violations([paths], [BRUJAH, t("merits", "Path of Night")])) == 1

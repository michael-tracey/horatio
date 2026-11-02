"""The check vocabulary, on plain sheets."""

import pytest

from horatio.rules.checks import CheckData, matches, violations
from horatio.rules.files import DATA_DIR, load_rule_set
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


def test_what_a_check_looks_at() -> None:
    technique = CheckData(
        key="t",
        category="techniques",
        name="Fearful Blow",
        requires={
            "has_all": [
                {"category": "disciplines", "name": "Potence", "rating": 2},
                {"category": "disciplines", "name": "Presence", "rating": 2},
            ]
        },
    )
    merit = CheckData(
        key="m",
        category="merits",
        forbids={"any_of": [{"clan": ["Brujah"]}, {"count": {"category": "flaws", "gt": 2}}]},
        requires={"generation": {"lte": 3}},
    )

    assert technique.looks_at == {("disciplines", "Potence"), ("disciplines", "Presence")}
    assert merit.looks_at == {("clan", None), ("flaws", None), ("backgrounds", "Generation")}


def attributes(generation: int, physical: int, social: int, mental: int) -> list[SheetTrait]:
    return [
        t("backgrounds", "Generation", generation),
        t("attributes", "Physical", physical),
        t("attributes", "Social", social),
        t("attributes", "Mental", mental),
    ]


def attribute_limit() -> CheckData:
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    return next(c for c in rules.checks if c.category == "attributes")


@pytest.mark.parametrize(
    ("sheet", "flagged"),
    [
        (attributes(1, 10, 10, 10), []),
        (attributes(1, 11, 10, 10), []),
        (attributes(1, 12, 10, 10), ["Physical"]),
        (attributes(1, 11, 11, 10), ["Physical", "Social"]),
        (attributes(3, 13, 10, 10), []),
        (attributes(3, 14, 10, 10), ["Physical"]),
        (attributes(3, 11, 12, 10), []),
        (attributes(3, 11, 11, 11), []),
        (attributes(3, 12, 12, 10), ["Physical", "Social"]),
        (attributes(5, 15, 10, 10), []),
        (attributes(5, 11, 11, 13), []),
        (attributes(5, 12, 12, 12), ["Physical", "Social", "Mental"]),
        # No Generation background reads as Generation 1.
        (attributes(1, 11, 10, 10)[1:], []),
        (attributes(1, 12, 10, 10)[1:], ["Physical"]),
    ],
)
def test_attributes_may_go_above_10_by_as_many_dots_as_generation(
    sheet: list[SheetTrait], flagged: list[str]
) -> None:
    found = violations([attribute_limit()], sheet)
    assert [v.subject.name for v in found] == flagged


SPELLS = {"count": {"category": "rituals"}, "dots": {"category": "disciplines"}}


@pytest.mark.parametrize(
    ("extra", "rituals", "dots", "expected"),
    [
        ({}, 2, 2, False),
        ({}, 3, 2, True),
        ({"per_dot": 2}, 4, 2, False),
        ({"per_dot": 2}, 5, 2, True),
        # A table: languages at one dot, two, three; the last carries on above.
        ({"table": [1, 2, 4]}, 4, 3, False),
        ({"table": [1, 2, 4]}, 5, 3, True),
        ({"table": [1, 2, 4]}, 4, 6, False),
        ({"table": [1, 2, 4]}, 5, 6, True),
        ({"table": [1, 2, 4]}, 1, 0, True),
        ({"table": [1, 2, 4]}, 2, 1, True),
    ],
)
def test_more_than_dots_counts_per_dot_or_by_a_table(
    extra: dict[str, object], rituals: int, dots: int, expected: bool
) -> None:
    sheet = [t("rituals", f"Ritual {n}") for n in range(rituals)]
    if dots:
        sheet.append(t("disciplines", "Thaumaturgy", dots))

    assert matches({"more_than_dots": {**SPELLS, **extra}}, sheet, sheet[0]) == expected


def test_dots_limit_is_how_many_a_check_allows_where_its_other_conditions_hold() -> None:
    from horatio.rules.checks import dots_limit

    plain = CheckData(
        key="a",
        category="rituals",
        forbids={"more_than_dots": {**SPELLS, "table": [1, 3]}, "not": {"clan": ["Tremere"]}},
    )
    sheet = [t("disciplines", "Thaumaturgy", 2)]

    assert dots_limit(plain, sheet) == ("rituals", 3)
    assert dots_limit(plain, [*sheet, t("clan", "Tremere", None)]) is None
    assert (
        dots_limit(CheckData(key="b", category="rituals", forbids={"clan": ["X"]}), sheet) is None
    )


def test_a_more_than_dots_table_must_list_whole_numbers() -> None:
    from horatio.rules.checks import validate_condition

    validate_condition({"more_than_dots": {**SPELLS, "table": [1, 2]}}, set())
    for table in ([], [1, "two"], [-1]):
        with pytest.raises(ValueError, match="table"):
            validate_condition({"more_than_dots": {**SPELLS, "table": table}}, set())

"""Technique prerequisites read one dot short in text copied from Volume 2 Issue 1
(#873): its font's third dot is a private-use character, so "Vicissitude ●●●" can come
out as "Vicissitude ll". These pin the techniques where that misreading would lower a
prerequisite, as checked against the printed pages."""

from functools import cache

from horatio.rules.checks import Context, violations
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import RuleSetData, SheetTrait


@cache
def rules() -> RuleSetData:
    return load_rule_set(DATA_DIR / "bns_met_vampire.toml")


def t(category: str, name: str, rating: int = 1) -> SheetTrait:
    return SheetTrait(category=category, name=name, rating=rating, free_rating=0, detail="")


def allowed(technique: str, disciplines: dict[str, int]) -> bool:
    sheet = [t("disciplines", name, rating) for name, rating in disciplines.items()]
    sheet.append(t("techniques", technique))
    return not [
        v for v in violations(rules().checks, sheet, Context()) if v.subject.name == technique
    ]


def test_bonecraft_prodigy_needs_vicissitude_3_and_fortitude_3() -> None:
    """Vol. 2 Issue 1 p. 61: Vicissitude ●●● and Fortitude ●●●."""
    assert allowed("Bonecraft Prodigy", {"Vicissitude": 3, "Fortitude": 3})
    assert not allowed("Bonecraft Prodigy", {"Vicissitude": 2, "Fortitude": 3})
    assert not allowed("Bonecraft Prodigy", {"Vicissitude": 3, "Fortitude": 2})


def test_abrupt_internment_needs_protean_3() -> None:
    """Vol. 2 Issue 1 p. 56: Protean ●●● and Fortitude ●."""
    assert allowed("Abrupt Internment", {"Protean": 3, "Fortitude": 1})
    assert not allowed("Abrupt Internment", {"Protean": 2, "Fortitude": 1})


def test_alchemical_attunement_needs_visceratika_3() -> None:
    """Vol. 2 Issue 1 p. 57: Visceratika ●●● and Fortitude ●."""
    assert allowed("Alchemical Attunement", {"Visceratika": 3, "Fortitude": 1})
    assert not allowed("Alchemical Attunement", {"Visceratika": 2, "Fortitude": 1})

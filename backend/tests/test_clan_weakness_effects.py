"""What clan weaknesses do (issue #1197): which a sheet carries, worked out in one place
(horatio.clan_weaknesses.carried), and what each changes and says on the Play View, in
feeding, checks and prices, labelled with the weakness it comes from."""

from dataclasses import replace
from functools import cache
from typing import Any

from horatio import clan_weaknesses
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import RuleSetData, SheetTrait
from tests.conftest import ghoul_rule_set

FREE = ("merits", "Golconda Seeker", 5, "No clan weakness")


@cache
def vampire() -> RuleSetData:
    return load_rule_set(DATA_DIR / "bns_met_vampire.toml")


def sheet(
    clan: str, *more: tuple[str, str, int | None, str] | tuple[str, str, int | None]
) -> list[SheetTrait]:
    """A sheet of the clan, at Humanity 5, with `more` (category, name, rating, detail?)."""
    traits = [SheetTrait("clan", clan), SheetTrait("paths", "Humanity", 5)]
    for t in more:
        traits.append(SheetTrait(t[0], t[1], t[2], detail=t[3] if len(t) > 3 else ""))  # type: ignore[misc]
    return traits


def carried(
    clan: str, *more: Any, rule_set: RuleSetData | None = None
) -> list[tuple[str, str | None]]:
    return [
        (c.clan, c.via) for c in clan_weaknesses.carried(rule_set or vampire(), sheet(clan, *more))
    ]


# --- which weaknesses a sheet carries ------------------------------------------------


def test_a_bloodline_has_its_own_its_clans_or_both() -> None:
    # Its own instead of its clan's (p. 61), and its clan's where it has none (Telyav).
    assert carried("Toreador: Ishtarri") == [("Toreador: Ishtarri", None)]
    assert carried("Tremere: Telyav") == [("Tremere", None)]
    assert carried("Tzimisce: Bratovitch") == [("Tzimisce: Bratovitch", None)]
    # Its own as well as its clan's (Vol. 2, p. 33; Vol. 2, p. 48).
    assert carried("Gangrel: Anda") == [("Gangrel: Anda", None), ("Gangrel", None)]
    assert carried("Nosferatu: Creeps") == [("Nosferatu: Creeps", None), ("Nosferatu", None)]
    # Both the Baali's and the Lasombra's (p. 72).
    assert carried("Baali: Angelis Ater") == [
        ("Baali: Angelis Ater", None),
        ("Baali", None),
        ("Lasombra", None),
    ]


def test_coldly_logical_adds_the_true_brujah_weakness() -> None:
    assert carried("Brujah", ("flaws", "Brujah: Coldly Logical", 1)) == [
        ("Brujah", None),
        ("Brujah: True Brujah", "Brujah: Coldly Logical"),
    ]


def test_a_golconda_seeker_who_took_freedom_carries_none_while_humane() -> None:
    assert carried("Salubri", FREE) == []
    assert clan_weaknesses.lifted(vampire(), sheet("Salubri", FREE))
    # Another benefit leaves it, and so does Humanity below 5 (pp. 249-250).
    assert carried("Salubri", ("merits", "Golconda Seeker", 5, "2 more Blood a turn")) == [
        ("Salubri", None)
    ]
    low = [t if t.category != "paths" else replace(t, rating=4) for t in sheet("Salubri", FREE)]
    assert [c.clan for c in clan_weaknesses.carried(vampire(), low)] == ["Salubri"]
    assert not clan_weaknesses.lifted(vampire(), low)
    # The merit offers the benefit as its detail.
    assert "No clan weakness" in vampire().trait_properties("merits", "Golconda Seeker")["choices"]


def test_a_ghoul_carries_none() -> None:
    assert carried("Salubri", rule_set=ghoul_rule_set()) == []

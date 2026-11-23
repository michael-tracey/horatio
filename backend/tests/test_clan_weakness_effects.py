"""What clan weaknesses do (issue #1197): which a sheet carries, worked out in one place
(horatio.clan_weaknesses.carried), and what each changes and says on the Play View, in
feeding, checks and prices, labelled with the weakness it comes from."""

from collections.abc import Callable
from dataclasses import replace
from functools import cache
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import clan_weaknesses
from horatio.reference import (
    Sheet,
    frenzy,
    pools,
    technique_bases,
    weakness_lines,
    work_out,
)
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import RuleSetData, SheetTrait
from tests.api_helpers import Troupe
from tests.conftest import ghoul_rule_set
from tests.test_api_troupe_settings_share import ok
from tests.test_clan_names import at_home

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


def test_the_brujah_play_the_troupes_book() -> None:
    (core,) = clan_weaknesses.carried(vampire(), sheet("Brujah"))
    assert (core.weakness.book, core.weakness.page, core.chosen) == ("core", "45", False)
    assert core.effects["pools"] == [{"pool": "frenzy", "difficulty": 2}]
    lash_out = replace(vampire(), weakness_books={"Brujah": "vol2", "Tremere": "vol2"})
    (vol2,) = clan_weaknesses.carried(lash_out, sheet("Brujah"))
    assert (vol2.weakness.book, vol2.weakness.page, vol2.chosen) == ("vol2", "Vol. 2, p. 121", True)
    assert vol2.effects["pools"][0]["beast"] == 2


# --- the Play View -------------------------------------------------------------------


def worked(traits: list[SheetTrait], rule_set: RuleSetData | None = None) -> tuple[Sheet, Any]:
    rule_set = rule_set or vampire()
    found = Sheet.of(traits, rule_set)
    return found, work_out(found, technique_bases(rule_set))


def test_brujah_frenzy_is_harder_or_counts_beast_traits_as_the_troupe_plays_it() -> None:
    brujah, done = worked(sheet("Brujah", ("attributes", "Mental", 3)))
    resist = frenzy(brujah, done.effects)
    assert [(p.label, p.value) for p in resist.against] == [("Brujah weakness", 2)]
    assert resist.beast == [] and resist.notes == []

    lash_out = replace(vampire(), weakness_books={"Brujah": "vol2"})
    brujah, done = worked(sheet("Brujah"), lash_out)
    resist = frenzy(brujah, done.effects)
    assert resist.against == []
    assert [(p.label, p.value) for p in resist.beast] == [("Brujah weakness", 2)]
    assert resist.notes[0].startswith("Brujah weakness: 2 more Beast traits for frenzy only")


def test_bratovitch_count_a_beast_trait_more_and_gangrel_grow_features() -> None:
    bratovitch, done = worked(sheet("Tzimisce: Bratovitch"))
    resist = frenzy(bratovitch, done.effects)
    assert [(p.label, p.value) for p in resist.beast] == [("Bratovitch weakness", 1)]
    # Said in the Frenzy panel, not under Also.
    assert "never for losing Morality" in resist.notes[0]

    anda, done = worked(sheet("Gangrel: Anda"))
    assert frenzy(anda, done.effects).notes == [
        "Gangrel weakness: each frenzy gives you another animal feature, until you next"
        " sleep for a day."
    ]


def test_an_assamite_switches_on_tasted_vampire_blood() -> None:
    assamite, done = worked(sheet("Assamite"))
    (tasted,) = [s for s in done.switches if s.key == "Tasted vampire blood"]
    assert (tasted.origin, tasted.page) == ("Assamite weakness", "p. 44")
    assert "Frenzy resisted as if with 2 Beast traits more" in tasted.changes
    assert any("diablerize" in n for n in tasted.notes)
    resist = frenzy(assamite, done.effects)
    assert resist.beast == []
    assert [(p.switch, p.label, p.value) for p in resist.switched_beast] == [
        ("Tasted vampire blood", "Assamite weakness", 2)
    ]
    # A Sorcerer has its own weakness instead (p. 45), so no switch.
    _, done = worked(sheet("Assamite: Sorcerer"))
    assert not any(s.key == "Tasted vampire blood" for s in done.switches)


def pool_of(found: list[Any], key: str) -> Any:
    return next(p for p in found if p.key == key)


def test_pool_penalties_name_the_weakness() -> None:
    traits = sheet(
        "Daughters of Cacophony",
        ("attributes", "Mental", 4),
        ("skills", "Investigation", 2),
    )
    daughter, done = worked(traits)
    investigation = pool_of(pools(daughter, done.effects), "skill:Investigation")
    assert [(p.label, p.value) for p in investigation.parts][-1] == (
        "Daughters of Cacophony weakness",
        -2,
    )
    assert investigation.total == 4 + 2 - 2

    gargoyle, done = worked(sheet("Gargoyles", ("attributes", "Mental", 3)))
    mental = pool_of(pools(gargoyle, done.effects), "defense:Mental")
    assert mental.total == 3
    assert [(v.when, v.total) for v in mental.variants] == [("Against Dominate", 1)]

    ishtarri, done = worked(sheet("Toreador: Ishtarri", ("attributes", "Social", 3)))
    social = pool_of(pools(ishtarri, done.effects), "defense:Social")
    assert [(v.when, v.total) for v in social.variants] == [
        ("Against Presence and other powers over emotion", 1)
    ]

    tzimisce, done = worked(sheet("Tzimisce", ("attributes", "Physical", 4)))
    brawl = pool_of(pools(tzimisce, done.effects), "attack:Brawl")
    assert [(v.when, v.total) for v in brawl.variants] == [
        ("For each day without your native soil (to -5)", 3)
    ]


def test_every_pool_reminders_and_notes() -> None:
    from horatio.reference import other_notes

    lhiannan, done = worked(sheet("Lhiannan"))
    assert (
        "Lhiannan weakness: -1 to every pool for each night in a city, until a night in the wild"
        in (other_notes(done.effects))
    )
    (line,) = weakness_lines(lhiannan)
    assert (line.name, line.page, line.book) == ("Lhiannan weakness", "Vol. 2, p. 53", None)
    assert "difficulties against you are 2 lower" in line.notes[0]

    _, done = worked(sheet("Nagaraja"))
    assert "Nagaraja weakness: -1 to every pool for each night without human flesh" in (
        other_notes(done.effects)
    )


def test_a_toreador_spends_willpower_to_look_away() -> None:
    toreador, _ = worked(sheet("Toreador"))
    (line,) = weakness_lines(toreador)
    (use,) = line.uses
    assert (use.label, use.spends, use.page) == ("Resist beauty", True, "p. 61")
    assert use.cost is not None and (use.cost.tracker, use.cost.amount) == ("willpower", 1)


def test_the_weakness_lines_say_which_book_and_what_brought_it() -> None:
    troupe = replace(vampire(), weakness_books={"Brujah": "core", "Tremere": "vol2"})
    brujah, _ = worked(sheet("Brujah", ("flaws", "Brujah: Coldly Logical", 1)), troupe)
    lines = weakness_lines(brujah)
    assert [(w.name, w.book, w.via) for w in lines] == [
        ("Brujah weakness", "Core book", None),
        ("True Brujah weakness", None, "Brujah: Coldly Logical"),
    ]
    # With no troupe there's no choice to name: it plays its default.
    brujah, _ = worked(sheet("Brujah"))
    assert [w.book for w in weakness_lines(brujah)] == [None]
    seeker, _ = worked(sheet("Toreador", FREE))
    assert weakness_lines(seeker) == [] and seeker.freed


# --- through the API ------------------------------------------------------------------


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def test_the_play_view_follows_the_troupes_brujah_choice(troupe: Troupe) -> None:
    character_id = at_home(troupe, "Tyler", "Brujah")

    def found() -> dict[str, Any]:
        return ok(troupe.player.client.get(f"/characters/{character_id}/play/reference"))

    shown = found()
    assert shown["frenzy"]["against"] == [{"label": "Brujah weakness", "value": 2}]
    assert [(w["name"], w["book"], w["page"]) for w in shown["weaknesses"]] == [
        ("Brujah weakness", "Core book", "45")
    ]
    ok(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/clan-weaknesses", json={"core": ["Tremere"]}
        )
    )
    shown = found()
    assert shown["frenzy"]["against"] == []
    assert shown["frenzy"]["beast"] == [{"label": "Brujah weakness", "value": 2}]
    assert shown["weaknesses"][0]["page"] == "Vol. 2, p. 121"

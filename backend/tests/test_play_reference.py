"""The Play View's quick game reference (issue #83): pools worked out from the
sheet, with disciplines, focuses, merits and flaws, and notes on powers."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitCategory, TraitDefinition
from horatio.reference import (
    Cost,
    Sheet,
    actives,
    catalogue,
    cost,
    damage_effects,
    effects,
    pools,
    work_out,
)
from horatio.rules.files import DATA_DIR, all_rule_set_files, load_rule_set
from tests.api_helpers import Troupe
from tests.test_api_character_search import member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def created(troupe: Troupe, name: str, *traits: tuple[str, str, int | None]) -> str:
    """A Brujah in the troupe with `traits` on its sheet."""
    character_id = member(troupe, troupe.player, name, "Brujah")
    for category, trait, rating in traits:
        definition = troupe.session.scalars(
            select(TraitDefinition)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(TraitCategory.key == category, TraitDefinition.name == trait)
        ).one()
        troupe.session.add(
            CharacterTrait(
                character_id=uuid.UUID(character_id),
                trait_definition_id=definition.id,
                rating=rating,
            )
        )
    troupe.session.flush()
    return character_id


def reference(troupe: Troupe, character_id: str) -> dict[str, Any]:
    response = troupe.player.client.get(f"/characters/{character_id}/play/reference")
    assert response.status_code == 200, response.text
    return response.json()


def pool(found: dict[str, Any], key: str) -> dict[str, Any]:
    return next(p for p in found["pools"] if p["key"] == key)


def variants(p: dict[str, Any]) -> dict[str, int]:
    return {v["when"]: v["total"] for v in p["variants"]}


def switched(p: dict[str, Any]) -> list[tuple[str, str, int]]:
    """What each switch adds to a pool while it is on."""
    return [(s["switch"], s["label"], s["value"]) for s in p["switched"]]


@pytest.fixture
def swift(troupe: Troupe) -> str:
    """Physical 6, Mental 4, Dexterity focus, Celerity 4 with a Celerity elder
    power and technique, Obfuscate 2, Slippery Customer, Fanatic and Quixotic."""
    return created(
        troupe,
        "Swift",
        ("attributes", "Physical", 6),
        ("attributes", "Social", 3),
        ("attributes", "Mental", 4),
        ("focus_physicals", "Dexterity", None),
        ("skills", "Dodge", 3),
        ("skills", "Brawl", 2),
        ("skills", "Stealth", 3),
        ("disciplines", "Celerity", 4),
        ("disciplines", "Dominate", 2),
        ("disciplines", "Obfuscate", 2),
        ("elder_disciplines", "Celerity: Quickness", None),
        ("techniques", "Instinctive Command", None),
        ("merits", "Slippery Customer", None),
        ("merits", "Fanatic", None),
        ("merits", "Quixotic", None),
    )


def test_initiative_with_and_without_celerity(troupe: Troupe, swift: str) -> None:
    initiative = pool(reference(troupe, swift), "initiative")

    assert initiative["total"] == 6  # Physical, the higher of Physical and Mental
    assert variants(initiative) == {"While Injured": 9, "While Incapacitated": 12}
    # With Celerity switched on, Alacrity: Celerity 4, its elder power and a
    # technique built on it.
    assert switched(initiative) == [("Celerity", "Alacrity", 6)]


def test_dodge_counts_merits_focus_and_celerity(troupe: Troupe, swift: str) -> None:
    dodge = pool(reference(troupe, swift), "dodge")

    assert [(p["label"], p["value"]) for p in dodge["parts"]] == [
        ("Physical", 6),
        ("Dodge", 3),
        ("Slippery Customer", 3),
    ]
    # With Celerity on, +2 with the Dexterity focus, +2 from Legerity.
    assert variants(dodge) == {}
    assert switched(dodge) == [("Celerity", "Celerity", 2), ("Celerity", "Legerity", 2)]
    assert any("+2 to one Dodge pool" in n for n in dodge["notes"])


def test_attacks_disciplines_and_defence(troupe: Troupe, swift: str) -> None:
    found = reference(troupe, swift)

    keys = [p["key"] for p in found["pools"]]
    assert "attack:Brawl" in keys and "attack:Melee" not in keys
    assert pool(found, "attack:Brawl")["total"] == 8
    obfuscate = pool(found, "discipline:Obfuscate")
    assert (obfuscate["total"], obfuscate["versus"]) == (7, "Mental + Willpower")
    mental = pool(found, "defense:Mental")
    # Current Willpower is added on the page, never below 3 with Quixotic.
    assert (mental["total"], mental["adds_willpower"], mental["willpower_floor"]) == (4, True, 3)
    # Celerity has no standard test pool.
    assert "discipline:Celerity" not in keys


def test_power_notes_follow_dots_and_focus(troupe: Troupe, swift: str) -> None:
    found = reference(troupe, swift)

    disciplines = {d["name"]: d for d in found["disciplines"]}
    celerity = disciplines["Celerity"]
    assert [p["name"] for p in celerity["powers"]] == [
        "Alacrity",
        "Swiftness",
        "Rapidity",
        "Legerity",
    ]
    assert celerity["focus"] == "+2 to Dodge pools while Celerity is active."
    assert [p["name"] for p in disciplines["Obfuscate"]["powers"]] == [
        "Conceal",
        "Unseen Presence",
    ]
    # Without the Intelligence or Wits focus, no focus notes.
    assert all(p["focus"] is None for p in disciplines["Obfuscate"]["powers"])
    assert {o["name"] for o in found["other_powers"]} == {
        "Celerity: Quickness",
        "Instinctive Command",
    }
    assert any(t["name"] == "Celerity" for t in found["traits"])


def test_powers_say_what_using_them_costs(troupe: Troupe, swift: str) -> None:
    """A Use button on the Pools tab (issue #370) needs the cost, and the switch
    using the power turns on."""
    disciplines = {d["name"]: d for d in reference(troupe, swift)["disciplines"]}
    celerity = disciplines["Celerity"]
    # Celerity is activated as a whole, for 1 Blood (core p. 121), and switched on.
    assert celerity["cost"] == {"tracker": "blood", "amount": 1}
    assert celerity["switches"] == ["Celerity"]
    assert all(p["cost"] is None for p in celerity["powers"])
    # Dominate's orders cost nothing; Obfuscate's powers neither.
    assert all(p["cost"] is None for p in disciplines["Dominate"]["powers"])
    assert disciplines["Obfuscate"]["cost"] is None


def test_a_cost_is_read_from_the_start_of_the_note_or_given() -> None:
    plain = Sheet()
    assert cost({"note": "1 Blood, standard action: an illusion."}, plain) == Cost(
        tracker="blood", amount=1
    )
    assert cost({"note": "3 Blood, a minute's touch: cure."}, plain) == Cost(
        tracker="blood", amount=3
    )
    assert cost({"note": "2 Willpower: hold on."}, plain) == Cost(tracker="willpower", amount=2)
    # A cost part way through the note is not plain enough for one tap.
    assert cost({"note": "Grapple, then 1 Blood: searing agony."}, plain) is None
    assert cost({"note": "Standard action: change how an object looks."}, plain) is None
    # A focus can make a power free (Eyes of the Beast with Perception, core p. 154).
    eyes = catalogue().power("Protean", "Eyes of the Beast")
    assert eyes is not None
    assert cost(eyes, plain) == Cost(tracker="blood", amount=1)
    assert cost(eyes, Sheet(focuses={"Perception"})) is None


def test_every_power_that_switches_on_has_a_plain_cost_or_none() -> None:
    """Most switches are bought with Blood: their notes say so plainly, so the
    Use button can spend it and switch them on together."""
    book = catalogue()
    costed = [p for ps in book.powers.values() for p in ps if cost(p, Sheet()) is not None]
    assert len(costed) > 100
    feral = book.power("Protean", "Feral Claws")
    assert feral is not None
    assert cost(feral, Sheet()) == Cost(tracker="blood", amount=1)
    assert [a["key"] for a in actives(feral)] == ["Feral Claws"]
    for entry in [*book.disciplines.values(), *(p for ps in book.powers.values() for p in ps)]:
        given = entry.get("cost")
        if given is not None:
            assert set(given) <= {"blood", "willpower", "unless_focus"}, entry["name"]


def test_traits_say_what_they_do(troupe: Troupe, swift: str) -> None:
    """Each trait comes with its description and page for the Sheet tab, and the
    clan with its in-clan disciplines for the subheader (issue #212)."""
    traits = {(t["category"], t["name"]): t for t in reference(troupe, swift)["traits"]}

    stealth = traits[("skills", "Stealth")]
    assert stealth["description"].startswith("Moving unseen and unheard")
    assert stealth["page_reference"] == "97"
    clan = traits[("clan", "Brujah")]
    assert (clan["group"], clan["rating"]) == ("Identity", None)
    assert clan["in_clan"] == ["Celerity", "Potence", "Presence"]
    assert traits[("skills", "Dodge")]["in_clan"] is None


def test_substitutes_and_replacements(troupe: Troupe) -> None:
    odd = created(
        troupe,
        "Odd",
        ("attributes", "Physical", 3),
        ("attributes", "Social", 7),
        ("attributes", "Mental", 5),
        ("focus_physicals", "Strength", None),
        ("skills", "Dodge", 1),
        ("skills", "Awareness", 4),
        ("skills", "Brawl", 2),
        ("disciplines", "Potence", 1),
        ("merits", "Rhythm of Battle", None),
        ("merits", "Preternatural Awareness", None),
        ("merits", "Tech Junkie", None),
        ("flaws", "Slow Reactions", None),
    )
    found = reference(troupe, odd)

    initiative = pool(found, "initiative")
    assert initiative["parts"][0] == {"label": "Social", "value": 7}  # Rhythm of Battle
    assert initiative["total"] == 2  # Slow Reactions
    dodge = pool(found, "dodge")
    assert dodge["parts"][1] == {"label": "Awareness (for Dodge)", "value": 4}
    # Potence with the Strength focus: +2 to Brawl and Melee.
    assert pool(found, "attack:Brawl")["total"] == 3 + 2 + 2
    assert "Tech Junkie: +2 to Computer" in found["notes"]


def test_flat_flaws_and_merits_change_the_pools_they_name(troupe: Troupe) -> None:
    squint = created(
        troupe,
        "Squint",
        ("attributes", "Physical", 5),
        ("attributes", "Social", 3),
        ("attributes", "Mental", 3),
        ("skills", "Firearms", 2),
        ("skills", "Athletics", 1),
        ("flaws", "One Eye", None),
        ("flaws", "Death Sight", None),
        ("flaws", "Hard of Hearing", None),
        ("flaws", "Short Fuse", None),
        ("merits", "Executioner", None),
    )
    found = reference(troupe, squint)

    firearms = pool(found, "attack:Firearms")
    assert {"label": "One Eye", "value": -5} in firearms["parts"]
    assert firearms["total"] == 5 + 2 - 5
    assert pool(found, "attack:Athletics")["total"] == 5 + 1 - 5
    assert "Death Sight: -2 to Investigation" in found["notes"]
    assert "Hard of Hearing: -2 to Awareness based on hearing" in found["notes"]
    assert "Executioner: +1 to Streetwise" in found["notes"]
    assert any(n.startswith("Short Fuse: counts 1 more Beast trait") for n in found["notes"])


def test_other_tests_are_attribute_and_skill(troupe: Troupe) -> None:
    """Each skill held but the Combat ones is an Other test (issue #371): the attribute
    it is listed under + the skill + what merits and flaws add, which is then not
    repeated under Also."""
    talker = created(
        troupe,
        "Talker",
        ("attributes", "Physical", 4),
        ("attributes", "Social", 6),
        ("attributes", "Mental", 3),
        ("skills", "Intimidation", 3),
        ("skills", "Investigation", 2),
        ("skills", "Brawl", 2),
        ("skills", "Athletics", 1),
        ("merits", "Executioner", None),
        ("flaws", "Hard of Hearing", None),
    )
    found = reference(troupe, talker)

    others = [p for p in found["pools"] if p["group"] == "Other tests"]
    assert [p["name"] for p in others] == ["Athletics", "Intimidation", "Investigation"]
    intimidation = pool(found, "skill:Intimidation")
    assert [(p["label"], p["value"]) for p in intimidation["parts"]] == [
        ("Social", 6),
        ("Intimidation", 3),
        ("Executioner", 1),
    ]
    assert intimidation["total"] == 10
    investigation = pool(found, "skill:Investigation")
    assert investigation["total"] == 3 + 2
    assert variants(investigation) == {"Based on hearing": 3}
    # Said under Also only for a skill with no test shown.
    assert "Executioner: +1 to Intimidation" not in found["notes"]
    assert "Executioner: +1 to Streetwise" in found["notes"]
    assert "Hard of Hearing: -2 to Investigation based on hearing" not in found["notes"]
    # The Blood rule is said once over Combat, not under each pool.
    assert not any("Spend Blood" in n for p in found["pools"] for n in p["notes"])


def test_a_skill_with_fields_has_a_test_for_each() -> None:
    sheet = Sheet(
        ratings={("attributes", "Mental"): 5},
        skills={("Crafts", "Painting"): (3, "Mental"), ("Crafts", "Carpentry"): (1, "Mental")},
    )
    found = {p.key: p for p in pools(sheet, [])}

    assert (found["skill:Crafts:Carpentry"].name, found["skill:Crafts:Carpentry"].total) == (
        "Crafts: Carpentry",
        6,
    )
    assert found["skill:Crafts:Painting"].total == 8


def test_another_tests_attribute_carries_every_switch_change() -> None:
    """The Play View may count another attribute, so an Other test carries what a
    form does to each, and the page counts the one in use."""
    sheet = Sheet(
        ratings={("attributes", "Physical"): 4, ("attributes", "Mental"): 4},
        disciplines={"Vicissitude": 4},
        skills={("Occult", ""): (2, "Mental")},
    )
    worked = work_out(sheet, {})
    occult = next(
        p
        for p in pools(sheet, worked.effects, worked.hurts, worked.switches)
        if p.key == "skill:Occult"
    )
    assert ("Mental", -3) in [(s.attribute, s.value) for s in occult.switched]


def test_frenzy_counts_mental_and_what_changes_it(troupe: Troupe) -> None:
    calm = created(
        troupe,
        "Calm",
        ("attributes", "Mental", 4),
        ("merits", "Calm Heart", None),
    )
    frenzy = reference(troupe, calm)["frenzy"]

    assert frenzy["parts"] == [
        {"label": "Mental", "value": 4},
        {"label": "Calm Heart", "value": 3},
    ]
    assert frenzy["beast"] == [{"label": "Calm Heart", "value": -2}]


def test_strangers_cannot_read_it(troupe: Troupe, swift: str) -> None:
    response = troupe.stranger.client.get(f"/characters/{swift}/play/reference")
    assert response.status_code in (403, 404)


def test_every_discipline_has_notes_for_each_dot() -> None:
    """The book's quick notes cover every discipline in the rule set, five
    powers each, and every pool effect names a pool the page knows."""
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    disciplines = {name for category, name in rule_set.traits if category == "disciplines"}
    book = catalogue()
    assert set(book.disciplines) == disciplines
    for name in disciplines:
        # A path no book we use describes has none (the Graveborne, Vol. 2, p. 62).
        levels = [] if book.disciplines[name].get("unwritten") else [1, 2, 3, 4, 5]
        assert [p["level"] for p in book.powers.get(name, [])] == levels, name
    known = ("initiative", "dodge", "attack", "defense", "discipline", "skill", "frenzy", "all")
    entries = [e for d in book.disciplines.values() for e in d.get("pools", [])] + [
        e for ps in book.powers.values() for p in ps for e in p.get("pools", [])
    ]
    entries += [e for t in rule_set.traits.values() for e in t.properties.get("pools", [])]
    assert entries
    assert all(e["pool"].split(":", 1)[0] in known for e in entries)


def test_the_power_notes_are_not_a_rule_set() -> None:
    assert all(not p.name.endswith("_powers.toml") for p in all_rule_set_files())


def attack_damage(disciplines: dict[str, int], **skills: int) -> dict[str, Any]:
    """Each attack pool's damage for a sheet with these skills and disciplines."""
    sheet = Sheet(
        ratings={("attributes", "Physical"): 3, **{("skills", k): v for k, v in skills.items()}},
        disciplines=disciplines,
    )
    found = pools(sheet, effects(sheet, {}), damage_effects(sheet))
    return {p.key: p.damage for p in found if p.damage}


def test_base_damage_follows_the_attack_type() -> None:
    found = attack_damage({}, Brawl=1, Melee=1, Firearms=1, Athletics=1)

    assert {k: (d.kind, d.total, d.exceptional, d.type) for k, d in found.items()} == {
        "attack:Brawl": ("unarmed", 1, 1, "normal"),
        "attack:Melee": ("melee", 1, 1, "normal"),
        "attack:Firearms": ("firearms", 2, 1, "normal"),
        "attack:Athletics": ("thrown", 1, 1, "normal"),
    }
    assert [(p.label, p.value) for p in found["attack:Firearms"].parts] == [("firearms", 2)]


def test_potence_adds_to_brawl_and_melee_only() -> None:
    def breakdown(potence: int) -> dict[str, tuple[int, int, list[tuple[str, int]]]]:
        found = attack_damage({"Potence": potence}, Brawl=1, Melee=2, Firearms=1, Athletics=1)
        return {
            k: (d.total, d.exceptional, [(p.label, p.value) for p in d.parts])
            for k, d in found.items()
        }

    # Prowess adds nothing to damage.
    assert breakdown(1)["attack:Brawl"] == (1, 1, [("unarmed", 1)])
    # Might: 2 damage (core p. 150), 3 on an exceptional success.
    assert breakdown(2)["attack:Melee"] == (2, 1, [("melee", 1), ("Might", 1)])
    assert breakdown(3)["attack:Brawl"][:2] == (2, 1)
    # Intensity: an exceptional success adds 2, so 4 (core p. 151).
    assert breakdown(4)["attack:Brawl"][:2] == (2, 2)
    # Puissance: 3 in all, with Might's point included; 5 on an exceptional success.
    puissance = breakdown(5)["attack:Brawl"]
    assert puissance == (3, 2, [("unarmed", 1), ("Might", 1), ("Puissance", 1)])
    # Firearms and thrown attacks are not Brawl or Melee.
    assert breakdown(5)["attack:Firearms"] == (2, 1, [("firearms", 2)])
    assert breakdown(5)["attack:Athletics"][0] == 1


def test_powers_switched_on_change_damage_only_while_on() -> None:
    claws = attack_damage({"Protean": 2}, Brawl=1)["attack:Brawl"]
    assert (claws.total, claws.type, claws.notes) == (1, "normal", [])
    assert [(s.switch, s.type) for s in claws.switched] == [("Feral Claws", "aggravated")]

    legerity = attack_damage({"Celerity": 4}, Firearms=1)["attack:Firearms"]
    assert (legerity.total, legerity.exceptional) == (2, 1)
    assert [(s.switch, s.exceptional) for s in legerity.switched] == [("Celerity", 1)]


def test_the_reference_sends_the_damage(troupe: Troupe, swift: str) -> None:
    brawl = pool(reference(troupe, swift), "attack:Brawl")["damage"]

    assert (brawl["kind"], brawl["total"], brawl["exceptional"], brawl["type"]) == (
        "unarmed",
        1,
        1,
        "normal",
    )
    assert pool(reference(troupe, swift), "dodge")["damage"] is None


def test_every_damage_entry_is_from_a_page_and_names_an_attack() -> None:
    book = catalogue()
    assert {a["skill"]: a["page"] for a in book.attacks.values()} == dict.fromkeys(
        ("Brawl", "Melee", "Athletics", "Firearms"), 279
    )
    entries = [e for d in book.disciplines.values() for e in d.get("damage", [])] + [
        e for ps in book.powers.values() for p in ps for e in p.get("damage", [])
    ]
    entries += [e for o in book.others.values() for e in o.get("damage", [])]
    assert entries
    for e in entries:
        assert e["page"] > 0
        assert set(e["attacks"]) <= set(book.attacks)
        assert e["type"] in ("normal", "aggravated") if "type" in e else True
        assert "note" in e if "when" in e else True


# --- Forms and powers in use (issue #200) -----------------------------------


def beast(**choices: str) -> Sheet:
    """Physical 5, Brawl 3, Dodge 2, Protean 4 and Celerity 2, with these choices
    made for Shape of the Beast."""
    return Sheet(
        ratings={
            ("attributes", "Physical"): 5,
            ("attributes", "Mental"): 3,
            ("attributes", "Social"): 2,
            ("skills", "Brawl"): 3,
            ("skills", "Dodge"): 2,
        },
        disciplines={"Protean": 4, "Celerity": 2},
        choices={"Protean": {"Shape of the Beast": choices}} if choices else {},
    )


def by_key(found: list[Any]) -> dict[str, Any]:
    return {f.key: f for f in found}


def test_shape_of_the_beast_has_two_forms_from_the_book() -> None:
    worked = work_out(beast(fight="bear", template="Huge"), {})
    found = by_key(worked.switches)

    assert {"flight form", "fight form", "Feral Claws", "Earth Meld", "Celerity"} <= set(found)
    fight = found["fight form"]
    assert fight.name == "Shape of the Beast: fight form (bear, Huge)"
    assert (fight.form, fight.origin, fight.page) == (True, "Protean 4", "p. 155")
    assert [(h.level, h.boxes) for h in fight.health] == [("Healthy", 2)]
    assert fight.changes == ["+2 Brawl attacks", "+2 Healthy", "Brawl damage aggravated"]
    # The bat keeps its default animal, and flying is a note.
    flight = found["flight form"]
    assert flight.name == "Shape of the Beast: flight form (bat)"
    assert flight.changes == ["+3 Dodge", "Physical counts as 3 at most for attacks"]
    assert flight.notes == ["Can fly at your normal speed."]
    # Feral Claws and Celerity are not forms, so they go with one.
    assert not found["Feral Claws"].form and not found["Celerity"].form


def test_a_template_changes_only_the_fight_form() -> None:
    plain = by_key(work_out(beast(), {}).switches)["fight form"]
    assert plain.name == "Shape of the Beast: fight form (wolf)"
    assert plain.health == []

    vicious = work_out(beast(template="Vicious"), {})
    brawl = next(
        p for p in pools(beast(), vicious.effects, vicious.hurts) if p.key == "attack:Brawl"
    )
    assert [(s.switch, s.value) for s in brawl.switched] == [("fight form", 2), ("fight form", 1)]

    agile = work_out(beast(template="Agile"), {})
    assert "+1 Dodge" in by_key(agile.switches)["fight form"].changes
    aquatic = by_key(work_out(beast(template="Aquatic"), {}).switches)["fight form"]
    assert any("Swim" in n for n in aquatic.notes)


def test_pools_say_what_each_switch_changes() -> None:
    sheet = beast(template="Huge")
    worked = work_out(sheet, {})
    found = {p.key: p for p in pools(sheet, worked.effects, worked.hurts, worked.switches)}

    brawl = found["attack:Brawl"]
    assert brawl.total == 8  # Physical 5 + Brawl 3, with nothing on
    assert [(s.switch, s.label, s.value, s.attribute, s.most) for s in brawl.switched] == [
        ("fight form", "Shape of the Beast", 2, None, None),
        ("flight form", "Physical (flight form)", 0, "Physical", 3),
    ]
    assert brawl.damage is not None
    assert {(s.switch, s.type) for s in brawl.damage.switched} == {
        ("Feral Claws", "aggravated"),
        ("fight form", "aggravated"),
    }
    assert [(s.switch, s.value) for s in found["dodge"].switched] == [("flight form", 3)]
    # Alacrity: Celerity's two powers.
    assert [(s.switch, s.value) for s in found["initiative"].switched] == [("Celerity", 2)]
    # The flight form's Physical is for attacks only.
    assert found["defense:Physical"].switched == []


def test_a_form_can_give_a_focus_and_change_attributes() -> None:
    sheet = Sheet(
        ratings={("attributes", "Physical"): 4, ("attributes", "Mental"): 4},
        disciplines={"Vicissitude": 4, "Potence": 1},
    )
    worked = work_out(sheet, {})
    horrid = by_key(worked.switches)["Horrid Form"]

    # Horrid Form gives the Strength focus, and Potence's focus adds +2 with it.
    assert "+2 Brawl attacks (Potence, Strength focus)" in horrid.changes
    assert "-3 Mental" in horrid.changes and horrid.form
    found = {p.key: p for p in pools(sheet, worked.effects, worked.hurts, worked.switches)}
    assert [(s.attribute, s.value) for s in found["defense:Mental"].switched] == [("Mental", -3)]


def test_every_when_in_the_powers_names_a_switch_and_every_switch_a_page() -> None:
    book = catalogue()
    entries = [*book.disciplines.values(), *(p for ps in book.powers.values() for p in ps)]
    entries += list(book.others.values())
    keys = [a["key"] for e in entries for a in actives(e)]
    assert len(keys) == len(set(keys)), "switch keys are unique"
    for e in entries:
        for when in [x.get("when") for x in [*e.get("pools", []), *e.get("damage", [])]]:
            assert when is None or when in book.switch_keys, (e["name"], when)
        for a in actives(e):
            assert a["page"] > 0 and a.get("book", "core") in ("core", "Vol. 2", "Vol. 2 Issue 1")
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    for category, name in book.others:
        assert (category, name) in rule_set.traits, name

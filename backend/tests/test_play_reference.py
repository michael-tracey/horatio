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
    TRACKED,
    Cost,
    Owner,
    Sheet,
    _switch,
    actives,
    catalogue,
    cost,
    damage_effects,
    disciplines,
    effects,
    forms_at_once,
    option_switches,
    other_powers,
    own_tests,
    pools,
    switch_for,
    uses,
    work_out,
)
from horatio.rules.files import DATA_DIR, all_rule_set_files, load_rule_set
from tests.api_helpers import Troupe
from tests.test_api_character_search import member
from tests.test_api_grants import AZHI_DAHAKA, luminary_tzimisce
from tests.test_catalogue_descriptions import PAGE


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


def test_ensnaring_force_is_listed_with_what_it_does(troupe: Troupe) -> None:
    """A technique from Vol. 2 (p. 75, #412): the Play View lists it with its note."""
    character_id = created(
        troupe,
        "Snare",
        ("disciplines", "Kineticism", 4),
        ("disciplines", "Celerity", 2),
        ("techniques", "Ensnaring Force", None),
    )

    found = {o["name"]: o for o in reference(troupe, character_id)["other_powers"]}

    assert found["Ensnaring Force"]["category_name"] == "Techniques"
    assert "Physical + Athletics" in found["Ensnaring Force"]["note"]


def test_powers_say_what_using_them_costs(troupe: Troupe, swift: str) -> None:
    """A Use button on the Pools tab (issue #370) needs the cost, and the switch
    using the power turns on."""
    disciplines = {d["name"]: d for d in reference(troupe, swift)["disciplines"]}
    celerity = disciplines["Celerity"]
    # Celerity is activated as a whole, for 1 Blood (core p. 121), and switched on.
    assert celerity["cost"] == {"tracker": "blood", "amount": 1, "most": None}
    assert celerity["switches"] == ["Celerity"]
    assert all(p["cost"] is None for p in celerity["powers"])
    # Dominate's orders cost nothing; Obfuscate's powers neither.
    assert all(p["cost"] is None for p in disciplines["Dominate"]["powers"])
    assert disciplines["Obfuscate"]["cost"] is None


def test_elder_powers_say_what_using_them_costs(troupe: Troupe, swift: str) -> None:
    """An elder power's Use button (issue #588) needs its cost and switch, from its
    [[others]] entry: Projectile is 1 Blood an attack (core p. 214)."""
    character_id = created(
        troupe,
        "Thrower",
        ("attributes", "Physical", 5),
        ("skills", "Firearms", 2),
        ("skills", "Athletics", 2),
        ("disciplines", "Celerity", 5),
        ("elder_disciplines", "Celerity: Projectile", None),
        ("techniques", "Instinctive Command", None),
    )

    found = reference(troupe, character_id)
    others = {o["name"]: o for o in found["other_powers"]}
    projectile = others["Celerity: Projectile"]
    assert projectile["category_name"] == "Elder Disciplines"
    assert projectile["cost"] == {"tracker": "blood", "amount": 1, "most": None}
    assert projectile["switches"] == ["Projectile"]
    # With no [[others]] entry, no cost and no switch.
    assert others["Instinctive Command"]["cost"] is None
    assert others["Instinctive Command"]["switches"] == []
    # While it is on: +3 to thrown and firearms attacks, and 1 more damage.
    for key in ("attack:Firearms", "attack:Athletics"):
        attack = pool(found, key)
        assert ("Projectile", "Projectile", 3) in switched(attack)
        assert ("Projectile", 1) in [
            (s["switch"], s["amount"]) for s in attack["damage"]["switched"]
        ]
    assert not [s for s in switched(pool(found, "attack:Brawl")) if s[0] == "Projectile"]
    # The swift character's Quickness has no cost or switch of its own.
    quickness = next(
        o for o in reference(troupe, swift)["other_powers"] if o["name"] == "Celerity: Quickness"
    )
    assert (quickness["cost"], quickness["switches"]) == (None, [])


def test_an_others_entry_needing_a_power_has_no_cost_or_switch_without_it() -> None:
    swarm = catalogue().others[("techniques", "Animal Swarm")]
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    held = Sheet(
        ratings={("techniques", "Animal Swarm"): 1},
        others=[("techniques", "Techniques", "Animal Swarm")],
    )
    assert [o.switches for o in other_powers(held, rule_set)] == [[]]
    held.disciplines["Protean"] = 4
    assert [o.switches for o in other_powers(held, rule_set)] == [
        [a["key"] for a in actives(swarm)]
    ]


def test_every_elder_and_luminary_power_says_what_it_does_and_where() -> None:
    """Each shows a line and its page on the Pools tab (issue #587): its description
    and page in the catalogue. One whose line starts with a plain cost has that cost
    from its [[others]] entry, for its Use button."""
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    book = catalogue()
    found = {
        key: trait
        for key, trait in rule_set.traits.items()
        if key[0] in ("elder_disciplines", "luminary_disciplines")
    }

    assert found
    unsaid = sorted(
        name
        for (_, name), trait in found.items()
        if not trait.description or not PAGE.fullmatch(trait.page_reference or "")
    )
    assert unsaid == []
    assert len({trait.description for trait in found.values()}) == len(found)
    for key, trait in found.items():
        said = cost({"note": trait.description}, Sheet())
        if said is not None:
            assert cost(book.others.get(key, {}), Sheet()) == said, key


def test_elder_powers_switch_on_what_they_change(troupe: Troupe) -> None:
    """Issue #587: Flick's switch adds +3 to Brawl (core p. 220), Force makes a Brawl
    hit 4 (core pp. 219-220), Breath of the Dragon's switch makes the thrown attack 4
    aggravated (core p. 223), and Psychic Assault has its line, page, cost and a
    switch for its test (issue #600)."""
    character_id = created(
        troupe,
        "Ancient",
        ("attributes", "Physical", 5),
        ("skills", "Brawl", 3),
        ("skills", "Athletics", 2),
        ("disciplines", "Potence", 5),
        ("elder_disciplines", "Potence: Flick", None),
        ("elder_disciplines", "Potence: Force", None),
        ("elder_disciplines", "Vicissitude: Breath of the Dragon", None),
        ("elder_disciplines", "Auspex: Psychic Assault", None),
    )

    found = reference(troupe, character_id)
    others = {o["name"]: o for o in found["other_powers"]}
    blood = {"tracker": "blood", "amount": 1, "most": None}
    assault = others["Auspex: Psychic Assault"]
    assert assault["note"].startswith("1 Blood, standard action, Auspex test: 4 damage")
    assert (assault["page"], assault["cost"], assault["switches"]) == (
        "213",
        blood,
        ["Psychic Assault"],
    )
    flick = others["Potence: Flick"]
    assert (flick["page"], flick["cost"], flick["switches"]) == ("220", blood, ["Flick"])
    assert others["Vicissitude: Breath of the Dragon"]["cost"] == {
        "tracker": "blood",
        "amount": 2,
        "most": None,
    }

    brawl = pool(found, "attack:Brawl")
    assert ("Flick", "Flick", 3) in switched(brawl)
    # Potence 5 makes it 3, and Force 4; Intensity's 2 more on an exceptional success.
    assert (brawl["damage"]["total"], brawl["damage"]["exceptional"]) == (4, 2)
    thrown = pool(found, "attack:Athletics")["damage"]
    assert (thrown["total"], thrown["type"]) == (1, "normal")
    assert [(s["switch"], s["amount"], s["type"]) for s in thrown["switched"]] == [
        ("Breath of the Dragon", 3, "aggravated")
    ]


def test_killer_instincts_shows_its_bonus_only_against_the_hunted_target(troupe: Troupe) -> None:
    """Issue #613: Killer Instincts makes Physical attacks on the one target you hunt
    Accurate (+2) and Brutal (Vol. 2 p. 84; core p. 516), so each attack keeps its
    total and has a line of its own for that target while the switch is on."""
    character_id = created(
        troupe,
        "Ahrimane",
        ("attributes", "Physical", 5),
        ("skills", "Brawl", 3),
        ("skills", "Melee", 2),
        ("skills", "Firearms", 1),
        ("skills", "Athletics", 4),
        ("skills", "Dodge", 2),
        ("elder_disciplines", "Spiritus: Killer Instincts", None),
    )

    found = reference(troupe, character_id)
    brutal = {
        "name": "Brutal",
        "play": "Win on the larger pool: exceptional success",
        "page": "p. 516",
    }
    for skill, total in (("Brawl", 8), ("Melee", 7), ("Firearms", 6), ("Athletics", 9)):
        attack = pool(found, f"attack:{skill}")
        assert attack["total"] == total
        # Nothing on the switch changes the attack's own total.
        assert switched(attack) == []
        assert attack["variants"] == [
            {
                "when": "Against your hunted target",
                "total": total + 2,
                "parts": [{"label": "Accurate", "value": 2}],
                "instead": False,
                "tracked": [],
                "switch": "Killer Instincts",
                "qualities": [brutal],
            }
        ]
    # Not a Physical attack: Dodge and the defences have no such line.
    assert all(p["variants"] == [] for p in found["pools"] if not p["key"].startswith("attack:"))
    others = {o["name"]: o for o in found["other_powers"]}
    assert others["Spiritus: Killer Instincts"]["switches"] == ["Killer Instincts"]

    # The switch's line says whom it is for; the unarmed choice stays a note.
    sheet = Sheet(
        ratings={("elder_disciplines", "Spiritus: Killer Instincts"): 0},
        others=[("elder_disciplines", "Elder Powers", "Spiritus: Killer Instincts")],
    )
    switch = by_key(work_out(sheet, {}).switches)["Killer Instincts"]
    assert switch.changes == ["Against your hunted target: +2 attacks (Accurate), Brutal"]
    assert not any("every attack" in n for n in switch.notes)
    assert any("Harrying or Encumbering" in n for n in switch.notes)


def test_luminary_powers_switch_on_forms_blood_health_and_a_frenzy() -> None:
    """Issue #587: Ghost Body is a form (Vol. 2 p. 233), Awaken the Heartsblood gives
    2 more Blood a turn (p. 236), Mythic Form's Tough 4 Healthy (p. 234), and Embrace
    the Beast a rage frenzy's numbers (core p. 301), +3 with Manipulation (p. 117)."""
    held = [
        "Protean: Ghost Body",
        "Protean: Mythic Form",
        "Quietus: Awaken the Heartsblood",
        "Animalism: Embrace the Beast",
    ]
    sheet = Sheet(
        ratings={
            ("attributes", "Physical"): 4,
            ("skills", "Brawl"): 2,
            ("skills", "Dodge"): 2,
            **{("luminary_disciplines", name): 1 for name in held},
        },
        focuses={"Manipulation"},
        disciplines={"Protean": 5, "Quietus": 5, "Animalism": 5},
    )

    worked = work_out(sheet, {})
    found = by_key(worked.switches)
    ghost = found["Ghost Body"]
    assert (ghost.form, ghost.origin, ghost.page) == (True, "Protean: Ghost Body", "Vol. 2, p. 233")
    assert found["Awaken the Heartsblood"].blood_per_turn == 2
    # Mythic Form's qualities are its own options, picked each use (issue #821).
    tough = found["Mythic Form/Tough"]
    assert [(h.level, h.boxes) for h in tough.health] == [("Healthy", 4)]
    assert (tough.form, tough.option_of) == (False, "Mythic Form")

    made = {p.key: p for p in pools(sheet, worked.effects, worked.hurts, worked.switches)}
    on = [(s.switch, s.value) for s in made["attack:Brawl"].switched]
    assert ("Embrace the Beast", 1) in on and ("Embrace the Beast", 2) in on
    assert ("Mythic Form/Vicious", 3) in on
    assert ("Embrace the Beast", -2) in [(s.switch, s.value) for s in made["dodge"].switched]
    physical = made["defense:Physical"].switched
    assert [(s.switch, s.value) for s in physical] == [("Embrace the Beast", -2)]


def test_powers_add_notes_to_another_powers_switch_for_those_who_have_them() -> None:
    """Issue #601: Quickness (core p. 214) and Momentum Swing (Vol. 2 p. 200) add to
    Celerity's switch, Earth Control (core p. 221) to Earth Meld's and Acid Blood
    (core p. 224) to Blood Form's, each under its own name and page."""
    disciplines = {"Celerity": 5, "Protean": 5, "Vicissitude": 5}
    held = {
        ("elder_disciplines", "Celerity: Quickness"): 1,
        ("luminary_disciplines", "Celerity: Momentum Swing"): 1,
        ("elder_disciplines", "Protean: Earth Control"): 1,
        ("elder_disciplines", "Vicissitude: Acid Blood"): 1,
    }

    found = by_key(work_out(Sheet(ratings=held, disciplines=disciplines), {}).switches)
    added = {key: [(a.source, a.page) for a in s.added] for key, s in found.items() if s.added}
    assert added == {
        "Celerity": [
            ("Quickness", "p. 214"),
            ("Momentum Swing", "Vol. 2, p. 200"),
            ("Momentum Swing", "Vol. 2, p. 200"),
        ],
        "Earth Meld": [("Earth Control", "p. 221"), ("Earth Control", "p. 221")],
        "Blood Form": [("Acid Blood", "p. 224")],
    }
    assert found["Celerity"].added[0].note.startswith("An extra round of actions")
    # Celerity's own notes are as they were.
    assert found["Celerity"].notes == [
        "For the turn: 1 Blood activates every Celerity power you have."
    ]

    # Without the powers, the switches are as the book's disciplines give them.
    bare = work_out(Sheet(disciplines=disciplines), {}).switches
    assert all(s.added == [] for s in bare)
    # The power without the switch's discipline adds nothing anywhere.
    alone = Sheet(ratings=held, disciplines={"Celerity": 5})
    assert [s.key for s in work_out(alone, {}).switches if s.added] == ["Celerity"]


def test_the_play_view_sends_what_quickness_adds_to_celerity(troupe: Troupe, swift: str) -> None:
    response = troupe.player.client.get(f"/characters/{swift}/play")
    assert response.status_code == 200, response.text
    celerity = next(p for p in response.json()["powers"] if p["key"] == "Celerity")
    assert [(a["source"], a["page"]) for a in celerity["added"]] == [("Quickness", "p. 214")]
    plain_id = created(troupe, "Plain", ("disciplines", "Celerity", 4))
    plain = troupe.player.client.get(f"/characters/{plain_id}/play").json()
    assert next(p for p in plain["powers"] if p["key"] == "Celerity")["added"] == []


def test_the_path_of_the_graveborn_has_its_five_powers(troupe: Troupe) -> None:
    """Vol. 2 pp. 116-119 (#413): each power with its note and focus, Use for the
    ones that cost Blood, and the scythe's aggravated Melee while it is out."""
    graveborn = "Necromancy: Path of the Graveborn"
    character_id = created(
        troupe,
        "Gravedigger",
        ("attributes", "Social", 4),
        ("focus_socials", "Appearance", None),
        ("skills", "Melee", 2),
        ("skills", "Occult", 3),
        ("disciplines", graveborn, 5),
    )

    found = reference(troupe, character_id)
    path = next(d for d in found["disciplines"] if d["name"] == graveborn)

    assert [(p["level"], p["name"]) for p in path["powers"]] == [
        (1, "Lord of the Flies"),
        (2, "Death's Scythe"),
        (3, "Reaper's Due"),
        (4, "Corpulent Discharge"),
        (5, "Death Perfected"),
    ]
    assert path["pool"] == "Social + Occult"
    blood = {"tracker": "blood", "amount": 1, "most": None}
    assert [p["cost"] for p in path["powers"]] == [blood, blood, None, blood, blood]
    assert all(p["note"] for p in path["powers"])
    # With Appearance, the focus notes of the powers that have one for it.
    powers = {p["name"]: p for p in path["powers"]}
    assert powers["Death Perfected"]["focus"] == (
        "+2 to the pool of each retest you spend Willpower on."
    )
    assert powers["Lord of the Flies"]["focus"] is None  # a Charisma focus
    melee = pool(found, "attack:Melee")["damage"]
    assert [(s["switch"], s["type"]) for s in melee["switched"]] == [
        ("Death's Scythe", "aggravated")
    ]


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
    entries = [*book.disciplines.values(), *(p for ps in book.powers.values() for p in ps)]
    for entry in [*entries, *book.others.values()]:
        given = entry.get("cost")
        if given is not None:
            assert set(given) <= {"blood", "willpower", "unless_focus", "most"}, entry["name"]
            # A cost chosen each use runs up from its amount (issue #824).
            if "most" in given:
                assert given["most"] > given.get("blood", given.get("willpower")), entry["name"]
    # Elder and luminary powers and techniques with a plain cost in the book.
    others = {name: cost(entry, Sheet()) for (_, name), entry in book.others.items()}
    blood = {n: c.amount for n, c in others.items() if c and c.tracker == "blood"}
    assert blood["Celerity: Projectile"] == 1  # core p. 214
    assert blood["Celerity: Nimble Departure"] == 2  # Vol. 2 p. 198
    assert blood["Serpentis: Divine Image"] == 3  # core p. 222


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


def test_defences_that_are_not_a_flat_bonus(troupe: Troupe) -> None:
    """Rampart of Faith adds Morality minus Beast traits to each defence, which
    counts Willpower, for 1 Blood; the Play View counts it from its trackers.
    Rockheart offers Physical + Survival in place of Mental and Social defence,
    with its other effects as notes (issue #602)."""
    stone = created(
        troupe,
        "Stone",
        ("attributes", "Physical", 5),
        ("attributes", "Social", 3),
        ("attributes", "Mental", 2),
        ("skills", "Survival", 3),
        ("elder_disciplines", "Valeren: Rampart of Faith", None),
        ("luminary_disciplines", "Visceratika: Rockheart", None),
    )
    found = reference(troupe, stone)

    for key in ("defense:Mental", "defense:Social", "defense:Physical"):
        rampart = next(v for v in pool(found, key)["variants"] if v["when"] == "For 1 Blood")
        assert rampart["total"] == pool(found, key)["total"]
        assert rampart["tracked"] == [
            {"label": "Rampart of Faith", "tracks": "morality_less_beast"}
        ]
        assert not rampart["instead"]
    for key in ("defense:Mental", "defense:Social"):
        rockheart = next(v for v in pool(found, key)["variants"] if v["instead"])
        assert rockheart["when"] == "Instead, with Rockheart"
        assert rockheart["parts"] == [
            {"label": "Physical", "value": 5},
            {"label": "Survival", "value": 3},
        ]
        assert rockheart["total"] == 8
    assert not any(v["instead"] for v in pool(found, "defense:Physical")["variants"])
    assert pool(found, "defense:Social")["notes"] == [
        "A Willpower spent to retest a Social power comes straight back (Rockheart)"
    ]
    assert "Rockheart: 1 Blood wins a frenzy test outright" in found["notes"]
    # Neither changes any other pool, nor the frenzy numbers.
    assert all(p["variants"] == [] for p in found["pools"] if not p["key"].startswith("defense:"))
    assert found["frenzy"]["parts"] == [{"label": "Mental", "value": 2}]


def test_defences_without_those_powers_have_no_variants(troupe: Troupe, swift: str) -> None:
    found = reference(troupe, swift)
    for key in ("defense:Mental", "defense:Social", "defense:Physical"):
        assert pool(found, key)["variants"] == []
    assert not any("Rockheart" in n for n in found["notes"])


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
        assert [p["level"] for p in book.powers.get(name, [])] == [1, 2, 3, 4, 5], name
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


def vital(potence: int, fortitude: int) -> tuple[Any, dict[str, Any]]:
    """Mercurial Vitality's switch, and each attack's damage, for a sheet with
    Potence and Fortitude at these dots."""
    sheet = Sheet(
        ratings={
            ("attributes", "Physical"): 3,
            ("skills", "Brawl"): 2,
            ("skills", "Melee"): 1,
            ("techniques", "Mercurial Vitality"): 1,
        },
        disciplines={"Potence": potence, "Fortitude": fortitude, "Vicissitude": 2},
    )
    worked = work_out(sheet, {})
    made = pools(sheet, worked.effects, worked.hurts, worked.switches)
    return by_key(worked.switches)["Mercurial Vitality"], {
        p.key: p.damage for p in made if p.damage
    }


def test_mercurial_vitality_counts_potence_and_fortitude_a_dot_higher_while_on() -> None:
    """Issue #849: Mercurial Vitality raises Potence and Fortitude by a dot each for
    the turn, never past the 5th (core p. 229). The powers gained count while its
    switch is on: Might's damage at Potence 1, and Mettle's note at Fortitude 1."""
    switch, damage = vital(potence=1, fortitude=1)

    assert [(r.discipline, r.to) for r in switch.disciplines] == [("Potence", 2), ("Fortitude", 2)]
    assert switch.changes[:2] == ["Potence counts as 2", "Fortitude counts as 2"]
    assert "+1 Brawl and Melee damage" in switch.changes
    assert any(n.startswith("Potence 2, Might: ") for n in switch.notes)
    assert any(n.startswith("Fortitude 2, Mettle: ") for n in switch.notes)
    # Off, the damage is Prowess's: nothing more; on, Might's point.
    brawl = damage["attack:Brawl"]
    assert brawl.total == 1
    assert [(s.switch, s.label, s.amount) for s in brawl.switched] == [
        ("Mercurial Vitality", "Might", 1)
    ]


def test_mercurial_vitality_gives_intensity_or_puissance_and_never_a_sixth_dot() -> None:
    _, at_three = vital(potence=3, fortitude=3)
    # Potence 4's Intensity: an exceptional success adds one more (core p. 151).
    assert [(s.label, s.exceptional) for s in at_three["attack:Melee"].switched] == [
        ("Intensity", 1)
    ]
    _, at_four = vital(potence=4, fortitude=2)
    assert [(s.label, s.amount) for s in at_four["attack:Brawl"].switched] == [("Puissance", 1)]

    switch, at_five = vital(potence=5, fortitude=5)
    assert at_five["attack:Brawl"].switched == []
    assert switch.changes[:2] == [
        "Potence is already at 5, the most",
        "Fortitude is already at 5, the most",
    ]


def test_quickened_blood_waives_celerity_while_on() -> None:
    """Issue #849: with Quickened Blood on, Celerity's first five dots cost no Blood
    for five minutes (core p. 230). Its switch names what it waives."""
    sheet = Sheet(
        ratings={("techniques", "Quickened Blood"): 1},
        disciplines={"Celerity": 2, "Fortitude": 1},
    )
    switch = by_key(work_out(sheet, {}).switches)["Quickened Blood"]
    assert (switch.waives, switch.page) == (["Celerity"], "p. 230")


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


# --- Damage through a power's own test (issue #600) -------------------------


def power_pools(sheet: Sheet) -> dict[str, Any]:
    """The pools of the powers that deal damage through a test, by name."""
    worked = work_out(sheet, {})
    found = pools(sheet, worked.effects, worked.hurts, worked.switches)
    return {p.name: p for p in found if p.key.startswith("power:")}


def test_psychic_assault_is_an_auspex_test_for_damage_nothing_reduces(troupe: Troupe) -> None:
    """Core p. 213: the Auspex test pool, 4 damage (5 on an exceptional success) that
    armour and Fortitude can't reduce. It shows in Combat while its switch is on."""
    character_id = created(
        troupe,
        "Seer",
        ("attributes", "Mental", 5),
        ("skills", "Investigation", 3),
        ("disciplines", "Auspex", 5),
        ("elder_disciplines", "Auspex: Psychic Assault", None),
    )

    found = reference(troupe, character_id)
    assault = pool(found, "power:Psychic Assault")
    assert (assault["name"], assault["group"], assault["switch"]) == (
        "Psychic Assault",
        "Combat",
        "Psychic Assault",
    )
    assert [(p["label"], p["value"]) for p in assault["parts"]] == [
        ("Mental", 5),
        ("Investigation", 3),
    ]
    assert (assault["total"], assault["versus"]) == (8, "Mental + Willpower")
    hurt = assault["damage"]
    assert (hurt["total"], hurt["exceptional"], hurt["type"], hurt["reducible"]) == (
        4,
        1,
        "normal",
        False,
    )
    # The attacks and the discipline's own pool show at all times, as before.
    assert pool(found, "attack:Brawl")["switch"] is None
    assert pool(found, "discipline:Auspex")["total"] == 8
    switch = next(p for p in found["other_powers"] if p["name"] == "Auspex: Psychic Assault")
    assert switch["switches"] == ["Psychic Assault"]


def test_powers_deal_damage_through_their_own_test() -> None:
    """Shadowy Betrayal names its pool (Vol. 2 p. 224), Chronoton Bolt comes with
    Temporal Anomaly (pp. 240-241), Scourge of Arikel has no test of its own (p. 231),
    and Cataclysmic Upheaval does damage nothing reduces (p. 250)."""
    held = {
        ("elder_disciplines", "Obtenebration: Shadowy Betrayal"): 1,
        ("elder_disciplines", "Temporis: Temporal Anomaly"): 1,
        ("elder_disciplines", "Visceratika: Cataclysmic Upheaval"): 1,
        ("luminary_disciplines", "Presence: Scourge of Arikel"): 1,
    }
    sheet = Sheet(
        ratings={
            ("attributes", "Physical"): 4,
            ("attributes", "Social"): 5,
            ("attributes", "Mental"): 3,
            ("skills", "Occult"): 2,
            ("skills", "Survival"): 1,
            ("skills", "Athletics"): 4,
            **held,
        },
        disciplines={"Obtenebration": 5, "Temporis": 5, "Visceratika": 5, "Presence": 5},
    )

    found = power_pools(sheet)
    assert set(found) == {
        "Shadowy Betrayal",
        "Chronoton Bolt",
        "Cataclysmic Upheaval",
        "Scourge of Arikel",
    }
    shadow = found["Shadowy Betrayal"]
    assert (shadow.total, shadow.versus, shadow.switch) == (
        7,
        "Social + Willpower",
        "Shadowy Betrayal",
    )
    assert (shadow.damage.total, shadow.damage.exceptional, shadow.damage.reducible) == (2, 0, True)
    assert shadow.damage.notes == ["2 more for each simple action you spend on it later"]

    bolt = found["Chronoton Bolt"]
    assert (bolt.total, bolt.versus, bolt.switch) == (5, "Physical + Willpower", "Temporal Anomaly")
    assert (bolt.damage.total, bolt.damage.exceptional, bolt.damage.type) == (2, 1, "aggravated")

    upheaval = found["Cataclysmic Upheaval"]
    assert [(p.label, p.value) for p in upheaval.parts] == [("Mental", 3), ("Athletics", 4)]
    assert (upheaval.damage.total, upheaval.damage.exceptional) == (3, 1)
    assert not upheaval.damage.reducible

    scourge = found["Scourge of Arikel"]
    assert (scourge.parts, scourge.versus) == ([], None)
    assert scourge.challenge and scourge.challenge.startswith("Any Social challenge you win")
    assert (scourge.damage.total, scourge.damage.type) == (3, "aggravated")

    # Each switch says so, beside what else it changes.
    switches = by_key(work_out(sheet, {}).switches)
    assert "Chronoton Bolt in Combat: 2 aggravated damage" in switches["Temporal Anomaly"].changes
    assert switches["Cataclysmic Upheaval"].changes == [
        "Cataclysmic Upheaval in Combat: 3 damage that nothing reduces"
    ]


def test_a_focus_can_change_a_power_tests_damage() -> None:
    """Stygian Lance (core pp. 177-178): Social + Occult against Physical + Dodge, and
    with the Charisma focus nothing reduces its damage."""
    sheet = Sheet(
        ratings={("attributes", "Social"): 4, ("skills", "Occult"): 3},
        disciplines={"Necromancy: Ash Path": 4},
    )
    lance = power_pools(sheet)["Stygian Lance"]
    assert (lance.total, lance.versus, lance.damage.total, lance.damage.reducible) == (
        7,
        "Physical + Dodge",
        3,
        True,
    )
    sheet.focuses.add("Charisma")
    assert not power_pools(sheet)["Stygian Lance"].damage.reducible
    # Flame Bolt is the Lure of Flames pool, dodged with Physical + Dodge (core p. 187).
    flames = Sheet(
        ratings={("attributes", "Mental"): 4}, disciplines={"Thaumaturgy: Lure of Flames": 2}
    )
    bolt = power_pools(flames)["Flame Bolt"]
    assert (bolt.versus, bolt.damage.type, bolt.damage.total + bolt.damage.exceptional) == (
        "Physical + Dodge",
        "aggravated",
        3,
    )


def test_every_power_test_names_its_switch_a_pool_and_a_page() -> None:
    book = catalogue()
    entries = [*book.disciplines.values(), *(p for ps in book.powers.values() for p in ps)]
    entries += list(book.others.values())
    found = [(e, t) for e in entries for t in own_tests(e)]
    assert len(found) >= 12
    attributes = {"Physical", "Social", "Mental"}
    for e, t in found:
        assert t["when"] in [a["key"] for a in actives(e)], e["name"]
        assert t["page"] > 0 and t.get("book", "core") in ("core", "Vol. 2", "Vol. 2 Issue 1")
        assert isinstance(t["damage"], int) and t["damage"] > 0
        assert t.get("type", "normal") in ("normal", "aggravated")
        spec = t.get("pool")
        if spec is None:
            assert t["challenge"], e["name"]
        elif spec.startswith("discipline:"):
            assert book.disciplines[spec.removeprefix("discipline:")].get("pool"), e["name"]
        else:
            attribute, _, skill = (s.strip() for s in spec.partition("+"))
            assert attribute in attributes and skill and t["versus"], e["name"]


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


def test_ravenous_conglomeration_allows_two_forms_at_once() -> None:
    """Issue #597: Vol. 2 p. 249. Everyone else has one (core p. 114)."""
    ravenous = ("luminary_disciplines", "Vicissitude: Ravenous Conglomeration")
    assert forms_at_once(Sheet(ratings={ravenous: 1}, disciplines={"Vicissitude": 5})) == 2
    assert forms_at_once(Sheet(disciplines={"Vicissitude": 5, "Protean": 5})) == 1


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


def test_focuses_azhi_dahaka_gives_count_and_say_where_they_are_from(troupe: Troupe) -> None:
    """Issue #598: the power's focuses are on the sheet, so the Play View counts
    them as the character's own, and says what gives them."""
    character_id = luminary_tzimisce(troupe)
    before = reference(troupe, character_id)
    assert switched(pool(before, "attack:Brawl")) == [("Horrid Form", "Horrid Form", 3)]

    taken = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "luminary_disciplines", "name": AZHI_DAHAKA, "rating": 1},
    )
    assert taken.status_code == 200, taken.text

    found = reference(troupe, character_id)
    # The Charisma focus: Horrid Form's +5 to Brawl in place of +3 (core p. 169).
    assert switched(pool(found, "attack:Brawl")) == [("Horrid Form", "Horrid Form", 5)]
    vicissitude = next(d for d in found["disciplines"] if d["name"] == "Vicissitude")
    visage = vicissitude["powers"][0]
    assert (visage["name"], visage["focus"]) == (
        "Malleable Visage",
        "One standard action, no hands needed.",
    )
    traits = {(t["category"], t["name"]): t["granted_by"] for t in found["traits"]}
    assert traits[("focus_socials", "Charisma")] == [AZHI_DAHAKA]
    assert traits[("focus_socials", "Manipulation")] == []
    assert sum(1 for c, _ in traits if c.startswith("focus_")) == 9


def test_every_when_in_the_powers_names_a_switch_and_every_switch_a_page() -> None:
    book = catalogue()
    entries = [*book.disciplines.values(), *(p for ps in book.powers.values() for p in ps)]
    entries += list(book.others.values())
    keys = [a["key"] for e in entries for a in actives(e)]
    assert len(keys) == len(set(keys)), "switch keys are unique"
    for e in entries:
        for x in [*e.get("pools", []), *e.get("damage", [])]:
            when = x.get("when")
            # What the trackers hold can only be a variant (Rampart of Faith's "for 1
            # Blood", Manic Episode's "With Celerity active").
            tracked = x.get("amount") in TRACKED
            assert not (tracked and when in book.switch_keys), e["name"]
            assert when is None or when in book.switch_keys or tracked, (e["name"], when)
            assert when if tracked else True, e["name"]
            # Whom a bonus holds against shows only while its switch is on (issue #613).
            if "against" in x:
                assert when in book.switch_keys, e["name"]
            for q in x.get("qualities", []):
                assert q["name"] and q["play"] and q["page"] > 0, e["name"]
        for n in e.get("notes", []):
            assert n["when"] in book.switch_keys and n["note"], (e["name"], n)
            assert n["page"] > 0 and n.get("book", "core") in ("core", "Vol. 2", "Vol. 2 Issue 1")
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    for e in entries:
        for a in actives(e):
            assert a["page"] > 0 and a.get("book", "core") in ("core", "Vol. 2", "Vol. 2 Issue 1")
            # Each quality it gives is one the equipment rules have (#820).
            for q in a.get("qualities", []):
                assert (q["kind"], q["name"]) in rule_set.equipment.qualities, (e["name"], q)
            # Its own options (issue #821): named without "/", which their keys use,
            # from a page, with the qualities and kinds the equipment rules have.
            picks = a.get("picks", {})
            for kind in [*([picks["kind"]] if "kind" in picks else []), *picks.get("kinds", [])]:
                assert rule_set.equipment.qualities_of(kind), (e["name"], kind)
            for name in picks.get("only", []):
                assert (picks["kind"], name) in rule_set.equipment.qualities, (e["name"], name)
            for o in picks.get("options", []):
                assert o["name"] and "/" not in o["name"], e["name"]
                assert o.get("page", a["page"]) > 0, (e["name"], o["name"])
                # An amount chosen each use runs from at least 1 (issue #824).
                if "amount" in o:
                    least = o["amount"].get("least", 1)
                    assert 1 <= least <= o["amount"]["most"], (e["name"], o["name"])
                for q in o.get("qualities", []):
                    assert (q["kind"], q["name"]) in rule_set.equipment.qualities, (e["name"], q)
    for category, name in book.others:
        assert (category, name) in rule_set.traits, name


# --- Timed powers as switches (#820) -------------------------------------------


def test_timed_powers_switch_on_each_from_its_page() -> None:
    """Powers whose effect lasts a while are switches the Play View can turn on,
    each with its book page, as checked against the books for #820."""
    sheet = Sheet(
        disciplines={
            "Protean": 1,
            "Quietus": 2,
            "Thanatosis": 5,
            "Visceratika": 4,
            "Thaumaturgy: Path of Elemental Mastery": 1,
            "Serpentis": 2,
            "Thaumaturgy: Movement of the Mind": 3,
            "Necromancy: Path of the Graveborn": 1,
            "Thaumaturgy: Green Path": 2,
            "Thaumaturgy: Path of Caelestikinesis": 2,
            "Temporis": 5,
            "Presence": 5,
            "Obfuscate": 2,
            "Auspex": 5,
            "Animalism": 4,
            "Dominate": 5,
            "Necromancy: Bone Path": 5,
            "Vicissitude": 2,
            "Potence": 2,
        },
        ratings={
            ("techniques", name): 1
            for name in (
                "Armor of Darkness",
                "Flame's Bane",
                "Unnatural Grace",
                "Mercurial Vitality",
                "Quickened Blood",
                "Maw of the Anaconda",
                "Rend Flesh",
            )
        },
    )
    pages = {s.key: s.page for s in work_out(sheet, {}).switches}
    assert {
        k: pages[k]
        for k in (
            "Eyes of the Beast",
            "Scorpion's Touch",
            "Necrosis",
            "Armor of Terra",
            "Elemental Strength: Strength",
            "Elemental Strength: Stamina",
            "Tongue of the Asp",
            "Skin of the Chameleon",
            "Flight",
            "Lord of the Flies",
            "Boughs Below",
            "Gravity Well",
            "Split Second",
            "Clotho's Gift",
            "Awe",
            "Majesty",
            "Unseen Presence",
            "Psychic Projection",
            "Subsume the Spirit",
            "Possession",
            "Death's Puppetry",
            "Fleshcraft",
            "Armor of Darkness",
            "Flame's Bane",
            "Unnatural Grace",
            "Mercurial Vitality",
            "Quickened Blood",
            "Maw of the Anaconda",
            "Rend Flesh",
        )
    } == {
        "Eyes of the Beast": "p. 154",
        "Scorpion's Touch": "p. 157",
        "Necrosis": "p. 165",
        "Armor of Terra": "p. 171",
        "Elemental Strength: Strength": "p. 193",
        "Elemental Strength: Stamina": "p. 193",
        "Tongue of the Asp": "p. 159",
        "Skin of the Chameleon": "p. 170",
        "Flight": "p. 197",
        "Lord of the Flies": "Vol. 2, p. 117",
        "Boughs Below": "Vol. 2, p. 150",
        "Gravity Well": "Vol. 2, p. 154",
        "Split Second": "p. 162",
        "Clotho's Gift": "p. 163",
        "Awe": "p. 151",
        "Majesty": "p. 153",
        "Unseen Presence": "p. 145",
        "Psychic Projection": "p. 120",
        "Subsume the Spirit": "p. 116",
        "Possession": "p. 136",
        "Death's Puppetry": "p. 176",
        "Fleshcraft": "p. 168",
        "Armor of Darkness": "p. 225",
        "Flame's Bane": "p. 228",
        "Unnatural Grace": "p. 232",
        "Mercurial Vitality": "p. 229",
        "Quickened Blood": "p. 230",
        "Maw of the Anaconda": "Vol. 2 Issue 1, p. 72",
        "Rend Flesh": "Vol. 2 Issue 1, p. 76",
    }


def test_elemental_strength_gives_the_strength_or_the_stamina_focus() -> None:
    """Core p. 193: one of the two foci for five minutes, and +2 to grappling with
    the Intelligence focus."""
    sheet = Sheet(
        disciplines={"Thaumaturgy: Path of Elemental Mastery": 1}, focuses={"Intelligence"}
    )
    found = by_key(work_out(sheet, {}).switches)
    strength = found["Elemental Strength: Strength"]
    assert (strength.name, strength.focuses) == ("Elemental Strength (Strength)", ["Strength"])
    assert found["Elemental Strength: Stamina"].focuses == ["Stamina"]
    assert "+2 to grappling challenges." in strength.notes
    assert "The Strength focus" in strength.changes


def test_armor_of_terra_gives_its_qualities_and_full_body_with_wits() -> None:
    """Core p. 171: Hardened and Ballistic, and Full Body with the Wits focus."""
    plain = by_key(work_out(Sheet(disciplines={"Visceratika": 4}), {}).switches)["Armor of Terra"]
    assert [(q.kind, q.name) for q in plain.qualities] == [
        ("protective", "Hardened"),
        ("protective", "Ballistic"),
    ]
    assert plain.changes == ["Hardened, Ballistic"]
    witty = Sheet(disciplines={"Visceratika": 4}, focuses={"Wits"})
    found = by_key(work_out(witty, {}).switches)["Armor of Terra"]
    assert [q.name for q in found.qualities] == ["Hardened", "Ballistic", "Full Body"]


def test_fleshcraft_and_rend_flesh_are_brawl_attacks_nothing_reduces() -> None:
    """Core p. 168: Fleshcraft's attack does 1 (2 on an exceptional success), 2 (3)
    with the Manipulation focus. Vol. 2 Issue 1 p. 76: Rend Flesh needs Potence 2,
    so it always has Might's point: 2 (3), or 3 (4) with the focus."""
    ratings = {
        ("attributes", "Physical"): 4,
        ("skills", "Brawl"): 3,
        ("techniques", "Rend Flesh"): 1,
    }
    plain = power_pools(Sheet(ratings=ratings, disciplines={"Vicissitude": 2, "Potence": 2}))
    focused = power_pools(
        Sheet(
            ratings=ratings, disciplines={"Vicissitude": 2, "Potence": 2}, focuses={"Manipulation"}
        )
    )

    def hurt(p: Any) -> tuple[int, int, bool]:
        assert p.damage is not None
        return (p.damage.total, p.damage.exceptional, p.damage.reducible)

    flesh = plain["Fleshcraft attack"]
    assert (flesh.total, flesh.versus, flesh.switch) == (7, "Physical + Dodge", "Fleshcraft")
    assert hurt(flesh) == (1, 1, False)
    assert hurt(focused["Fleshcraft attack"]) == (2, 1, False)
    assert hurt(plain["Rend Flesh"]) == (2, 1, False)
    assert hurt(focused["Rend Flesh"]) == (3, 1, False)
    # Without Potence 2, Rend Flesh does nothing here.
    weak = power_pools(Sheet(ratings=ratings, disciplines={"Vicissitude": 2, "Potence": 1}))
    assert "Rend Flesh" not in weak


def test_manic_episode_adds_derangement_traits_to_initiative_with_celerity() -> None:
    """Vol. 2 Issue 1 p. 71: always on; with Celerity active, initiative gains the
    current Derangement traits, which the Play View counts from its tracker. Paying
    for Celerity with a Derangement trait is a note on Celerity's switch."""
    sheet = Sheet(
        ratings={
            ("attributes", "Physical"): 3,
            ("attributes", "Mental"): 2,
            ("techniques", "Manic Episode"): 1,
        },
        disciplines={"Celerity": 1, "Dementation": 2},
    )
    worked = work_out(sheet, {})
    initiative = by_key(pools(sheet, worked.effects, worked.hurts, worked.switches))["initiative"]
    manic = next(v for v in initiative.variants if v.when == "With Celerity active")
    assert (manic.total, [t.model_dump() for t in manic.tracked]) == (
        initiative.total,
        [{"label": "Manic Episode", "tracks": "derangements"}],
    )
    celerity = by_key(worked.switches)["Celerity"]
    assert [a.source for a in celerity.added] == ["Manic Episode"]


USE_KEYS = {
    "label",
    "cost",
    "heal",
    "convert",
    "mend",
    "gain",
    "beast",
    "retainer",
    "when",
    "once",
    "focus",
    "unless_focus",
    "note",
    "page",
    "book",
    "target",
}
CHANGES = ("heal", "convert", "mend", "gain", "beast", "retainer")


def test_every_use_says_what_it_changes_and_where() -> None:
    """Issue #825: a use heals, converts, gains or takes something, from a page,
    and one that waits on a switch names one the file has."""
    book = catalogue()
    entries = [*(p for ps in book.powers.values() for p in ps), *book.others.values()]
    found = [(e["name"], u) for e in entries for u in e.get("use", [])]
    assert len(found) >= 20
    for name, u in found:
        assert set(u) <= USE_KEYS, (name, set(u) - USE_KEYS)
        assert u["label"] and u.get("page"), name
        assert any(k in u for k in CHANGES), name
        if "heal" in u:
            assert u["heal"]["damage"] in {"normal", "aggravated", "worst", "all", "asked"}, name
        assert set(u.get("gain", {})) <= {"blood", "willpower"}, name
        assert set(u.get("cost", {})) <= {"blood", "willpower"}, name
        if "when" in u:
            assert u["when"] in book.switch_keys, name
        # A use on another character (issue #823) heals them, and only that for now.
        assert u.get("target", "self") in {"self", "other"}, name
        if u.get("target") == "other":
            assert set(u) & set(CHANGES) == {"heal"}, name
            assert u["heal"]["damage"] != "asked", name


def test_a_switch_used_on_others_is_kept() -> None:
    """Issue #823: a switch that can be used on another character is an effect on
    them, kept until undone, and is never a form."""
    book = catalogue()
    entries = [
        *book.disciplines.values(),
        *(p for ps in book.powers.values() for p in ps),
        *book.others.values(),
    ]
    found = [a for e in entries for a in actives(e) if a.get("target", "self") != "self"]
    assert found
    for a in found:
        assert a["target"] in {"other", "any"}, a["key"]
        assert a.get("kept") and not a.get("form"), a["key"]


def test_another_characters_switch_is_built_from_the_powers_file() -> None:
    """What an effect from another's power does on a character who hasn't the power."""
    found = switch_for("Reshaped by Fleshcraft")
    assert [s.key for s in found] == [
        "Reshaped by Fleshcraft",
        "Reshaped by Fleshcraft/Ordinary change",
        "Reshaped by Fleshcraft/Alien beauty",
    ]
    assert found[2].attributes[0].amount == -2 and found[2].focuses == ["Appearance"]
    assert switch_for("No such switch") == []


def test_healing_powers_heal_as_the_book_says() -> None:
    """Corpore Sano (core p. 143), Mens Sana (p. 166), Repair the Undead Flesh
    (p. 216), Second Wind (p. 231) and the rest, with what a focus adds."""
    book = catalogue()
    plain, wits = Sheet(), Sheet(focuses={"Wits"})

    def summary(found: list[Any]) -> list[tuple[Any, ...]]:
        return [
            (
                u.label,
                u.cost.amount if u.cost else 0,
                (u.heal.damage, u.heal.amount) if u.heal else None,
                u.once,
            )
            for u in found
        ]

    def own(found: list[Any]) -> list[Any]:
        return [u for u in found if u.target == "self"]

    corpore = book.power("Obeah", "Corpore Sano")
    assert corpore is not None
    assert summary(own(uses(corpore, plain))) == [
        ("Heal 1 normal", 1, ("normal", 1), "Once a turn")
    ]
    assert [u.label for u in own(uses(corpore, wits))] == ["Heal 1 normal", "Heal 1 aggravated"]
    # On a willing character too (issue #823), the same heals.
    others = [u for u in uses(corpore, wits) if u.target == "other"]
    assert summary(others) == summary(own(uses(corpore, wits)))
    mens = book.power("Valeren", "Mens Sana")
    assert mens is not None
    assert [u.once for u in uses(mens, plain)] == ["Once a turn"]
    assert [u.once for u in uses(mens, wits)] == ["Twice a turn"]
    repair = book.others[("elder_disciplines", "Fortitude: Repair the Undead Flesh")]
    assert summary(uses(repair, plain)) == [("Heal 1 aggravated", 2, ("aggravated", 1), None)]
    wind = uses(book.others[("techniques", "Second Wind")], plain)
    assert [(u.convert_all, u.cost and u.cost.amount) for u in wind] == [(True, 1)]
    # Reflection of Endurance is Mens Sana, Reflection of Mercy Corpore Sano (pp. 230-231).
    endurance = uses(book.others[("techniques", "Reflection of Endurance")], wits)
    assert summary(endurance) == summary(uses(mens, wits))
    mercy = uses(book.others[("techniques", "Reflection of Mercy")], wits)
    assert [s[:3] for s in summary(mercy)] == [s[:3] for s in summary(own(uses(corpore, wits)))]
    # The third Moment of Reflection gives back 2 Willpower with Intelligence (Vol. 2 p. 160).
    moment = book.power("Thaumaturgy: Path of Neptune's Might", "Moment of Reflection")
    assert moment is not None
    third = [u for u in uses(moment, Sheet(focuses={"Intelligence"})) if u.once == "Once a night"]
    assert [(g.tracker, g.amount) for g in third[0].gains] == [("willpower", 2)]
    assert not uses(moment, plain)[1].gains


def test_uses_that_gain_spend_half_or_move_damage() -> None:
    """Theft of Vitae's 3 Blood, 4 on an exceptional success (core p. 189);
    Indestructible's half the Blood held (Vol. 2 p. 214); Beast's Vigor's damage
    moved to a ghoul Retainer for a Beast trait (Vol. 2 Issue 1 pp. 58-59)."""
    book = catalogue()
    theft = book.power("Thaumaturgy: Path of Blood", "Theft of Vitae")
    assert theft is not None
    assert [[(g.tracker, g.amount) for g in u.gains] for u in uses(theft, Sheet())] == [
        [("blood", 3)],
        [("blood", 4)],
    ]
    # Theft's uses spend nothing, so its plain Use button stays for the 1 Blood.
    assert cost(theft, Sheet()) == Cost(tracker="blood", amount=1)
    indestructible = uses(
        book.others[("luminary_disciplines", "Fortitude: Indestructible")], Sheet()
    )
    said = [(u.half, u.cost and u.cost.tracker, u.heal and u.heal.damage) for u in indestructible]
    assert said == [(True, "blood", "asked")]
    vigor = book.others[("techniques", "Beast's Vigor")]
    assert [a["key"] for a in actives(vigor)] == ["Beast's Vigor"]
    assert [(u.retainer, u.beast, u.when) for u in uses(vigor, Sheet())] == [
        (3, 1, "Beast's Vigor")
    ]
    wolf = uses(book.others[("techniques", "Feed the Blighted Wolf")], Sheet())
    assert [(u.beast, u.cost) for u in wolf] == [(1, None)]


def test_the_reference_sends_a_powers_uses(troupe: Troupe) -> None:
    """The Pools tab gets each power's uses, as its focus allows (issue #825)."""
    character_id = created(
        troupe,
        "Mender",
        ("disciplines", "Obeah", 3),
        ("techniques", "Second Wind", None),
    )
    found = reference(troupe, character_id)
    obeah = next(d for d in found["disciplines"] if d["name"] == "Obeah")
    corpore = next(p for p in obeah["powers"] if p["name"] == "Corpore Sano")
    # On yourself, and on a willing character within a step (issue #823).
    assert [(u["label"], u["cost"], u["heal"], u["target"]) for u in corpore["uses"]] == [
        (
            "Heal 1 normal",
            {"tracker": "blood", "amount": 1, "most": None},
            {"damage": "normal", "amount": 1},
            "self",
        ),
        (
            "Heal 1 normal",
            {"tracker": "blood", "amount": 1, "most": None},
            {"damage": "normal", "amount": 1},
            "other",
        ),
    ]
    wind = next(o for o in found["other_powers"] if o["name"] == "Second Wind")
    said = [(u["label"], u["convert_all"]) for u in wind["uses"]]
    assert said == [("Aggravated to normal", True)]


# --- A power's own options, picked each use (issue #821) ----------------------


def test_mantle_of_atiras_qualities_are_options_doubled_by_manipulation() -> None:
    """Mantle of Atira (Vol. 2 p. 82): two of six qualities picked each use, each a
    switch of its own while picked; the Manipulation focus doubles their bonuses."""

    def mantle(focuses: set[str]) -> tuple[Any, dict[str, Any]]:
        sheet = Sheet(
            ratings={("attributes", "Physical"): 3, ("skills", "Dodge"): 2},
            focuses=focuses,
            disciplines={"Spiritus": 4},
        )
        worked = work_out(sheet, {})
        switch = by_key(worked.switches)["Mantle of Atira"]
        made = {p.key: p for p in pools(sheet, worked.effects, worked.hurts, worked.switches)}
        return switch, made

    switch, made = mantle(set())
    assert switch.picks.count == 2
    assert [o.name for o in switch.picks.options] == [
        "Bear Strength",
        "Stride of the Gazelle",
        "Falcon's Eye",
        "Speed of the Hare",
        "Agility of the Fox",
        "Chameleon Camouflage",
    ]
    assert [(s.switch, s.value) for s in made["dodge"].switched] == [
        ("Mantle of Atira/Agility of the Fox", 1)
    ]
    assert ("Mantle of Atira/Speed of the Hare", 1) in [
        (s.switch, s.value) for s in made["initiative"].switched
    ]
    stride = next(o for o in switch.picks.options if o.name == "Stride of the Gazelle")
    assert stride.note.startswith("1 step more")

    switch, made = mantle({"Manipulation"})
    assert [(s.switch, s.value) for s in made["dodge"].switched] == [
        ("Mantle of Atira/Agility of the Fox", 2)
    ]
    stride = next(o for o in switch.picks.options if o.name == "Stride of the Gazelle")
    assert stride.note.startswith("2 steps more")


def test_options_follow_a_focus_traits_that_add_them_and_a_flaw_that_hides_them() -> None:
    """The shape Bonecraft and Malleable Visage (#812, #813) need: a count the
    Manipulation focus raises, options another trait adds (Bonecraft Prodigy, Vol. 2
    Issue 1 p. 61), options Tzimisce: Scar Tissue rules out (Vol. 2 p. 278), and one
    that a form doesn't pause (Second Stomach)."""
    active = {
        "key": "Bonecraft",
        "page": 168,
        "normal_form_only": True,
        "picks": {
            "count": 1,
            "focus_count": {"Manipulation": 2},
            "options": [
                {"name": "Tough", "health": [{"level": "Healthy", "boxes": 2}]},
                {"name": "Crippled", "note": "On another only."},
                {
                    "name": "Second Stomach",
                    "page": 61,
                    "book": "Vol. 2 Issue 1",
                    "from": "Bonecraft Prodigy",
                    "normal_form_only": False,
                    "blood": {"most": "half"},
                },
                {"name": "Extra Limbs", "hidden_by": "Tzimisce: Scar Tissue"},
            ],
        },
    }

    def picked(ratings: dict[tuple[str, str], int], focuses: set[str]) -> Any:
        sheet = Sheet(ratings=ratings, focuses=focuses, disciplines={"Vicissitude": 3})
        owner = Owner({"name": "Bonecraft"}, "Bonecraft", "Vicissitude 3")
        return _switch(owner, active, sheet)

    plain = picked({}, set())
    assert plain.picks is not None and plain.picks.count == 1
    assert [o.name for o in plain.picks.options] == ["Tough", "Crippled", "Extra Limbs"]
    assert plain.picks.options[0].key == "Bonecraft/Tough"
    assert plain.picks.options[0].page == "p. 168"

    prodigy = picked(
        {("techniques", "Bonecraft Prodigy"): 1, ("flaws", "Tzimisce: Scar Tissue"): 3},
        {"Manipulation"},
    )
    assert prodigy.picks is not None and prodigy.picks.count == 2
    assert [o.name for o in prodigy.picks.options] == ["Tough", "Crippled", "Second Stomach"]
    stomach = prodigy.picks.options[2]
    assert stomach.page == "Vol. 2 Issue 1, p. 61"

    found = by_key(option_switches(prodigy))
    assert set(found) == {"Bonecraft/Tough", "Bonecraft/Crippled", "Bonecraft/Second Stomach"}
    assert found["Bonecraft/Tough"].normal_form_only
    assert [(h.level, h.boxes) for h in found["Bonecraft/Tough"].health] == [("Healthy", 2)]
    assert not found["Bonecraft/Second Stomach"].normal_form_only
    assert found["Bonecraft/Second Stomach"].blood_half
    assert found["Bonecraft/Crippled"].notes == ["On another only."]
    assert {s.option_of for s in found.values()} == {"Bonecraft"}


def test_malleable_visage_reshapes_for_an_ordinary_change_or_alien_beauty() -> None:
    """Malleable Visage (core p. 168, #812): each use is an ordinary change or alien
    beauty (-2 Social, the Appearance focus), kept until it is sculpted again, in the
    normal form only; Tzimisce: Scar Tissue (Vol. 2 p. 278) rules it out on yourself."""
    sheet = Sheet(
        ratings={("attributes", "Social"): 4}, disciplines={"Vicissitude": 1, "Presence": 1}
    )
    worked = work_out(sheet, {})
    found = by_key(worked.switches)
    visage = found["Malleable Visage"]
    assert (visage.kept, visage.normal_form_only, visage.form) == (True, True, False)
    assert visage.page == "p. 168"
    assert visage.picks is not None and visage.picks.count == 1
    assert [o.name for o in visage.picks.options] == ["Ordinary change", "Alien beauty"]
    beauty = found["Malleable Visage/Alien beauty"]
    assert beauty.normal_form_only
    assert beauty.changes == ["-2 Social", "The Appearance focus"]
    assert found["Malleable Visage/Ordinary change"].changes == []
    made = {p.key: p for p in pools(sheet, worked.effects, worked.hurts, worked.switches)}
    for key in ("defense:Social", "discipline:Presence"):
        assert [(s.switch, s.value) for s in made[key].switched if s.attribute] == [
            ("Malleable Visage/Alien beauty", -2)
        ], key
    vicissitude = next(d for d in disciplines(sheet) if d.name == "Vicissitude")
    assert vicissitude.powers[0].switches == ["Malleable Visage"]

    # With Scar Tissue there is nothing to switch on: Use only spends the Blood.
    scarred = Sheet(ratings={("flaws", "Tzimisce: Scar Tissue"): 3}, disciplines={"Vicissitude": 1})
    assert not [s for s in work_out(scarred, {}).switches if s.key.startswith("Malleable Visage")]
    vicissitude = next(d for d in disciplines(scarred) if d.name == "Vicissitude")
    assert vicissitude.powers[0].switches == []
    assert vicissitude.powers[0].cost == Cost(tracker="blood", amount=1)


def test_blood_tempering_and_assimilate_switch_on_from_their_pages() -> None:
    """Blood Tempering (Vol. 2 Issue 1 pp. 60-61): one of four applications each use;
    Assimilate (Vol. 2 p. 131): the wraith's discipline is a note."""
    sheet = Sheet(
        ratings={("techniques", "Blood Tempering"): 1},
        disciplines={"Necromancy: Path of Soul Bonding": 5},
    )
    sheet.others.append(("techniques", "Techniques", "Blood Tempering"))
    found = by_key(work_out(sheet, {}).switches)
    tempering = found["Blood Tempering"]
    assert tempering.page == "Vol. 2 Issue 1, p. 60"
    assert tempering.picks is not None
    assert [(o.name, o.page) for o in tempering.picks.options] == [
        ("Damaged or Old Equipment", "Vol. 2 Issue 1, p. 60"),
        ("Improvised Weapon", "Vol. 2 Issue 1, p. 61"),
        ("Incorrect Equipment", "Vol. 2 Issue 1, p. 61"),
        ("Unbreakable", "Vol. 2 Issue 1, p. 61"),
    ]
    assimilate = found["Assimilate"]
    assert assimilate.page == "Vol. 2, p. 131"
    assert assimilate.picks is None
    assert any("wraith's disciplines" in n for n in assimilate.notes)


# --- An amount chosen at use (issue #824) --------------------------------------


def test_a_cost_the_player_chooses_from_one_up() -> None:
    """Promises Like Steel spends 1 to 3 Blood, as its user chooses (Vol. 2 pp. 217-
    218); Fog of War spends 1 Blood for each ten minutes (Vol. 2 p. 195), a Use each;
    Deny 3 Blood for each object (core p. 215)."""
    book = catalogue()
    promises = book.others[("elder_disciplines", "Mytherceria: Promises Like Steel")]
    assert cost(promises, Sheet()) == Cost(tracker="blood", amount=1, most=3)
    fog = book.others[("elder_disciplines", "Auspex: Fog of War")]
    assert cost(fog, Sheet()) == Cost(tracker="blood", amount=1)
    deny = book.others[("elder_disciplines", "Dementation: Deny")]
    assert cost(deny, Sheet()) == Cost(tracker="blood", amount=3)

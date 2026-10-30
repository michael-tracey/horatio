"""Merits and flaws whose rules apply while a character is built (#313): traits they
bar, clans that cannot take them, those chosen at creation only, the paths they open,
and what they make cheaper."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import XpEntry
from horatio.rules.checks import Context, violations
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import SheetTrait
from tests.api_helpers import Person, Troupe, new_character

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def step(person: Person, character_id: str, category: str, picks: list[tuple[str, int]]) -> Any:
    return person.client.put(
        f"/characters/{character_id}/creation/categories/{category}",
        json={"picks": [{"name": n, "rating": r} for n, r in picks]},
    )


def take(person: Person, character_id: str, category: str, name: str, rating: int) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating},
    )


def give_xp(troupe: Troupe, character_id: str, amount: int) -> None:
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="award",
            amount=amount,
            reason="Test",
            entered_by=uuid.UUID(troupe.custodian.id),
        )
    )
    troupe.session.flush()


def make_home(troupe: Troupe, character_id: str) -> None:
    asked = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert asked.status_code == 201, asked.text
    approved = troupe.lead.client.post(f"/approvals/{asked.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text


# --- traits a flaw bars ----------------------------------------------------------------


def test_artless_bars_crafts_and_performance(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Toreador")
    assert step(troupe.player, character_id, "skills", [("Performance", 3)]).status_code == 200

    refused = step(troupe.player, character_id, "flaws", [("Toreador: Artless", 1)])

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Artless: you cannot purchase the Performance or Crafts skills. (Vol. 2, p. 276)"
    )
    assert step(troupe.player, character_id, "skills", [("Brawl", 3)]).status_code == 200
    assert step(troupe.player, character_id, "flaws", [("Toreador: Artless", 1)]).status_code == 200


def rules_violations(sheet: list[SheetTrait], context: Context | None = None) -> list[str]:
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    return [v.message for v in violations(rule_set.checks, sheet, context or Context())]


def clan(name: str) -> SheetTrait:
    return SheetTrait("clan", name, None)


@pytest.mark.parametrize(
    ("trait", "barred", "message"),
    [
        (
            SheetTrait("flaws", "Gargoyle: Clay Pigeon", 3),
            SheetTrait("focus_physicals", "Stamina", 1),
            "Clay Pigeon: you cannot possess the Stamina focus. (Vol. 2, p. 285)",
        ),
        (
            SheetTrait("flaws", "Gargoyle: Stone Scarecrow", 1),
            SheetTrait("backgrounds", "Contacts", 1),
            "Stone Scarecrow: you cannot purchase the Allies or Contacts backgrounds."
            " (Vol. 2, p. 285)",
        ),
        (
            SheetTrait("flaws", "Giovanni: All My Friends Are Dead", 1),
            SheetTrait("backgrounds", "Herd", 3),
            "All My Friends Are Dead: no more than 2 dots in any background relating to the"
            " mortal world (Influence, Contacts, Allies or Herd). (Vol. 2, p. 272)",
        ),
        (
            SheetTrait("flaws", "Lhiannan: Technophobe", 2),
            SheetTrait("skills", "Firearms", 1),
            "Technophobe: you cannot possess any dots in Computer, Drive, Firearms, Science or"
            " Security. (Vol. 2, p. 56)",
        ),
        (
            SheetTrait("flaws", "Nosferatu: Anosmia", 1),
            SheetTrait("merits", "Acute Sense", 1, detail="Smell"),
            "Anosmia: you cannot purchase the Acute Sense merit for smell or taste."
            " (Vol. 2, p. 275)",
        ),
        (
            SheetTrait("flaws", "Nagaraja: Snake Charmed", 3),
            SheetTrait("disciplines", "Serpentis", 1),
            "Snake Charmed: you may never purchase the Serpentis discipline. (Vol. 2, p. 63)",
        ),
        (
            SheetTrait("flaws", "Nagaraja: Snake Charmed", 3),
            SheetTrait("merits", "Favored of Inauhaten", 3),
            "You may not take Snake Charmed with the Favored of Inauhaten merit. (Vol. 2, p. 63)",
        ),
        (
            SheetTrait("flaws", "Salubri: Unblinking Eyes", 1),
            SheetTrait("flaws", "Salubri: Fusion", 2),
            "You cannot take Unblinking Eyes and the Fusion flaw. (Vol. 2, p. 283)",
        ),
        (
            SheetTrait("flaws", "Sectarian", 2),
            SheetTrait("skills", "Lore", 3),
            "Sectarian: you cannot possess the Lore skill above 2, nor the Loremaster merit."
            " (p. 405)",
        ),
        (
            SheetTrait("merits", "Spiritual Armor", 2),
            SheetTrait("disciplines", "Daimoinon", 1),
            "Spiritual Armor: you cannot learn demonic powers, purchase infernal merits, or"
            " learn the Daimoinon discipline. (p. 247)",
        ),
        (
            SheetTrait("merits", "Bloodline: Carpathian", 3),
            SheetTrait("disciplines", "Vicissitude", 1),
            "Carpathians can never learn Vicissitude. (p. 244)",
        ),
    ],
)
def test_traits_a_merit_or_flaw_bars(trait: SheetTrait, barred: SheetTrait, message: str) -> None:
    assert message in rules_violations([trait, barred])
    assert message not in rules_violations([trait])
    assert message not in rules_violations([barred])


def test_tone_deaf_holds_singing_to_2() -> None:
    # Spelt as the book has it; #315 renames the catalogue's "Cacophany".
    flaw = SheetTrait("flaws", "Daughters of Cacophony: Tone Deaf", 3)
    message = (
        "Tone Deaf: you cannot purchase the Performance: Singing skill higher than 2 dots."
        " (Vol. 2, p. 284)"
    )
    assert message not in rules_violations(
        [flaw, SheetTrait("skills", "Performance", 2, 0, "Singing")]
    )
    assert message in rules_violations([flaw, SheetTrait("skills", "Performance", 3, 0, "Singing")])
    assert message not in rules_violations(
        [flaw, SheetTrait("skills", "Performance", 3, 0, "Acting")]
    )


# --- clans that cannot take it ---------------------------------------------------------------


def test_short_fuse_repeats_the_brujah_weakness(troupe: Troupe) -> None:
    brujah = new_character(troupe, troupe.player, finished=False, clan="Brujah")
    gangrel = new_character(troupe, troupe.player, "Bea", finished=False, clan="Gangrel")

    refused = step(troupe.player, brujah, "flaws", [("Short Fuse", 2)])

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Short Fuse repeats the Brujah weakness, so a Brujah cannot take it. (p. 236)"
    )
    assert step(troupe.player, gangrel, "flaws", [("Short Fuse", 2)]).status_code == 200


@pytest.mark.parametrize(
    ("flaw", "barred", "allowed"),
    [
        ("Gangrel: Roadkill", "Gangrel: Ahrimanes", "Gangrel: Coyote"),
        ("Gangrel: Species Speech", "Gangrel: Coyote", "Gangrel: Ahrimanes"),
        ("Tzimisce: Scar Tissue", "Tzimisce: Koldun", "Tzimisce"),
        ("Tzimisce: Scar Tissue", "Tzimisce: Carpathian", "Tzimisce: Bratovitch"),
        ("Tzimisce: Revenant Family Weakness", "Tzimisce: Bratovitch", "Tzimisce"),
        ("Prey Exclusion", "Ventrue: Crusader", "Toreador"),
        ("Disease Carrier", "Cappadocians: Lamia", "Cappadocians"),
        ("Repelled by Religion", "Baali: Angelis Ater", "Lasombra"),
    ],
)
def test_clans_that_cannot_take_a_flaw(flaw: str, barred: str, allowed: str) -> None:
    def broken(name: str) -> list[str]:
        return [
            m
            for m in rules_violations(
                [
                    clan(name),
                    SheetTrait("backgrounds", "Generation", 1),
                    SheetTrait("flaws", flaw, 1),
                ]
            )
            if "is only for" not in m
        ]

    assert broken(barred)
    assert not broken(allowed)


def test_a_thin_blooded_vampire_is_always_caitiff(troupe: Troupe) -> None:
    brujah = new_character(troupe, troupe.player, finished=False, clan="Brujah")

    refused = step(troupe.player, brujah, "flaws", [("Thin Blooded", 3)])

    assert refused.status_code == 409
    assert "Thin Blooded vampires are always Caitiff. (p. 265)" in refused.json()["detail"]
    caitiff = new_character(troupe, troupe.player, "Cass", finished=False, clan="Caitiff")
    assert step(troupe.player, caitiff, "flaws", [("Thin Blooded", 3)]).status_code == 200
    # Nor can a Thin Blooded Caitiff become a Brujah.
    changed = troupe.player.client.put(
        f"/characters/{caitiff}/traits", json={"category": "clan", "name": "Brujah", "rating": None}
    )
    assert changed.status_code == 409


# --- chosen at creation only -----------------------------------------------------------------


def test_black_sheep_is_taken_at_creation_only(troupe: Troupe) -> None:
    building = new_character(troupe, troupe.player, "Bea", finished=False, clan="Brujah")
    assert step(troupe.player, building, "flaws", [("Black Sheep", 2)]).status_code == 200

    character_id = new_character(troupe, troupe.player, clan="Brujah")
    make_home(troupe, character_id)

    refused = take(troupe.player, character_id, "flaws", "Black Sheep", 2)

    assert refused.status_code == 409
    assert "Black Sheep can only be chosen during character creation." in refused.json()["detail"]


def test_an_anarch_elder_needs_elder_of_the_revolution() -> None:
    message = (
        "An Anarch needs the Elder of the Revolution merit to buy the 4th or 5th dot of"
        " Generation at character creation. (p. 485)"
    )
    assert message in rules_violations(
        [SheetTrait("sect", "Anarch", None), SheetTrait("backgrounds", "Generation", 4)]
    )
    assert message not in rules_violations(
        [
            SheetTrait("sect", "Anarch", None),
            SheetTrait("backgrounds", "Generation", 4),
            SheetTrait("merits", "Elder of the Revolution", 2),
        ]
    )
    assert message not in rules_violations(
        [SheetTrait("sect", "Camarilla", None), SheetTrait("backgrounds", "Generation", 4)]
    )
    # Diablerie later needs no merit (p. 486).
    assert message not in rules_violations(
        [SheetTrait("sect", "Anarch", None), SheetTrait("backgrounds", "Generation", 4)],
        Context(accepted=True),
    )


# --- paths a merit opens ---------------------------------------------------------------------


def test_sea_witch_opens_the_path_of_neptunes_might(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Gangrel: Noiad")
    give_xp(troupe, character_id, 20)
    neptune = "Thaumaturgy: Path of Neptune's Might"
    refused = take(troupe.player, character_id, "disciplines", neptune, 1)
    assert refused.status_code == 409

    assert take(troupe.player, character_id, "merits", "Sea Witch", 3).status_code == 200
    bought = take(troupe.player, character_id, "disciplines", neptune, 1)

    assert bought.status_code == 200, bought.text
    # Only the path it names.
    other = take(troupe.player, character_id, "disciplines", "Thaumaturgy: Green Path", 1)
    assert other.status_code == 409
    assert "A path of Thaumaturgy needs Thaumaturgic Training" in other.json()["detail"]


def test_voudoun_master_opens_the_bone_path_and_one_other() -> None:
    merit = SheetTrait("merits", "Voudoun Master", 3)
    sect = SheetTrait("clan", "Followers of Set", None)
    message = (
        "A path of Necromancy needs Necromantic Training, a merit that grants the path, or a"
        " clan that has it in-clan. (p. 112)"
    )

    def path(name: str) -> SheetTrait:
        return SheetTrait("disciplines", f"Necromancy: {name}", 1)

    assert message not in rules_violations([sect, merit, path("Bone Path"), path("Ash Path")])
    assert message in rules_violations([sect, merit, path("Mortis Path")])
    assert message in rules_violations([sect, merit, path("Ash Path"), path("Path of Grief")])
    assert message in rules_violations([sect, path("Bone Path")])


def test_the_volgirre_learn_vicissitude_to_2_before_acceptance() -> None:
    message = (
        "Before a home troupe accepts the character, out-of-clan disciplines are the common"
        " ones only, up to 3 dots. (p. 106)"
    )
    volgirre = clan("Toreador: Volgirre")
    assert message not in rules_violations([volgirre, SheetTrait("disciplines", "Vicissitude", 2)])
    assert message in rules_violations([volgirre, SheetTrait("disciplines", "Vicissitude", 3)])
    prodigy = SheetTrait("merits", "Prodigy of the Flesh", 1)
    assert message not in rules_violations(
        [volgirre, prodigy, SheetTrait("disciplines", "Vicissitude", 5)]
    )


def test_necromantic_prowess_prices_its_path_in_clan(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Nagaraja")
    give_xp(troupe, character_id, 20)
    taken = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={
            "category": "merits",
            "name": "Necromantic Prowess",
            "rating": 1,
            "detail": "Necromancy: Bone Path",
        },
    )
    assert taken.status_code == 200, taken.text

    quote = troupe.player.client.post(
        f"/characters/{character_id}/quote",
        json={"category": "disciplines", "name": "Necromancy: Bone Path", "rating": 1},
    )

    # In-clan cost, 3 XP for the first dot (p. 112), and the path check passes.
    assert quote.json()["cost"] == 3
    bought = take(troupe.player, character_id, "disciplines", "Necromancy: Bone Path", 1)
    assert bought.status_code == 200, bought.text


# --- what a merit makes cheaper -------------------------------------------------------------


def test_ritual_supremacy_prices_rituals_at_their_rating(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Tremere: Telyav")
    give_xp(troupe, character_id, 20)
    ritual = {"category": "rituals", "name": "Thaumaturgy: Banish Big Brother", "rating": 2}

    def quote() -> int:
        found = troupe.player.client.post(f"/characters/{character_id}/quote", json=ritual)
        assert found.status_code == 200, found.text
        cost: int = found.json()["cost"]
        return cost

    assert quote() == 4
    assert take(troupe.player, character_id, "merits", "Ritual Supremacy", 1).status_code == 200
    assert quote() == 2


def test_monopoly_gives_two_influence_areas_a_dot() -> None:
    elite = SheetTrait("backgrounds", "Influences: The Elite", 1)
    areas = [
        SheetTrait("influence_elite_specializations", "Finance", 1),
        SheetTrait("influence_elite_specializations", "Legal", 1),
    ]
    one = "Each dot of Influences: The Elite gives one area. (p. 103)"
    assert one in rules_violations([elite, *areas])
    assert one not in rules_violations([elite, *areas, SheetTrait("merits", "Monopoly", 1)])


def test_ritually_inept_holds_necromancy_rituals_to_half_the_dots() -> None:
    flaw = SheetTrait("flaws", "Nagaraja: Ritually Inept", 1)
    ash = SheetTrait("disciplines", "Necromancy: Ash Path", 3)
    message = (
        "Ritually Inept: you cannot learn more Necromancy rituals than half your dots of"
        " Necromancy, rounded down. (Vol. 2, p. 63)"
    )
    one = SheetTrait("rituals", "Necromancy: Call of the Hungry Dead", 1)
    two = SheetTrait("rituals", "Necromancy: Eyes of the Grave", 2)
    assert message not in rules_violations([flaw, ash, one])
    assert message in rules_violations([flaw, ash, one, two])


# --- what taking a merit does to the sheet ---------------------------------------------------


def humanity(person: Person, character_id: str) -> tuple[int, int]:
    traits = person.client.get(f"/characters/{character_id}/sheet").json()["traits"]
    found = next(t for t in traits if t["category"] == "paths")
    return (found["rating"], found["free_rating"])


def test_flexible_morals_drops_morality_to_3(troupe: Troupe) -> None:
    building = new_character(troupe, troupe.player, "Bea", finished=False, clan="Lasombra")
    assert step(troupe.player, building, "merits", [("Flexible Morals", 3)]).status_code == 200
    assert humanity(troupe.player, building) == (3, 3)
    # Taken back while building, Humanity starts at 5 again.
    assert step(troupe.player, building, "merits", []).status_code == 200
    assert humanity(troupe.player, building) == (5, 5)

    finished = new_character(troupe, troupe.player, clan="Lasombra")
    give_xp(troupe, finished, 10)
    assert take(troupe.player, finished, "merits", "Flexible Morals", 3).status_code == 200
    assert humanity(troupe.player, finished) == (3, 3)

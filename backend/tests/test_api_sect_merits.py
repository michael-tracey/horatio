"""Sect merits and flaws are for their sect's members (#458): needed to finish creation,
then held for the home troupe's review. Emissary to the Camarilla is for those no sect
has Accepted; an infiltrator's Alternate Identity opens nothing; a troupe that moves a
sect merit to another category lifts the check, and a troupe can switch it off. Those
who hold one already, or change sect, keep it, flagged."""

from collections.abc import Callable, Sequence
from functools import cache
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.rules.checks import Context, Violation, violations
from horatio.rules.files import DATA_DIR, load_checks, load_rule_set
from horatio.rules.model import RuleSetData, SheetTrait
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_book_traits import recategorise
from tests.test_api_creation import FULL_BUILD, pick
from tests.test_api_own_checks import take
from tests.test_api_sheets import sheet

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


# --- the checks, on plain sheets ------------------------------------------------------


@cache
def vampire() -> RuleSetData:
    return load_rule_set(DATA_DIR / "bns_met_vampire.toml")


def t(category: str, name: str, rating: int | None = 1) -> SheetTrait:
    return SheetTrait(category=category, name=name, rating=rating, free_rating=0)


def broken(sheet: Sequence[SheetTrait], *, finished: bool = False) -> list[Violation]:
    """The sect checks the sheet breaks."""
    context = Context(kinds=vampire().kinds, finished=finished)
    return [v for v in violations(vampire().checks, sheet, context) if v.key[0].startswith("sect/")]


def held(sect: str | None, *traits: SheetTrait) -> list[SheetTrait]:
    return [t("clan", "Brujah", None), *([t("sect", sect, None)] if sect else []), *traits]


# One merit or flaw of each sect's, its catalogue type, and the sect's page.
EACH_SECT = [
    ("merits", "Moniker", "Anarch", "an Anarch merit", "the Anarch Movement", "485"),
    ("flaws", "Once Enslaved", "Anarch", "an Anarch flaw", "the Anarch Movement", "487"),
    ("merits", "Antiquities", "Camarilla", "a Camarilla merit", "the Camarilla", "404"),
    ("flaws", "Sectarian", "Camarilla", "a Camarilla flaw", "the Camarilla", "405"),
    ("merits", "Sanctified", "Sabbat", "a Sabbat merit", "the Sabbat", "452"),
    ("flaws", "Soul Shard", "Sabbat", "a Sabbat flaw", "the Sabbat", "454"),
    (
        "merits",
        "Made",
        "Independent Alliance",
        "an Independent Alliance merit",
        "the Independent Alliance",
        "Vol. 2 Issue 1, p. 14",
    ),
]


@pytest.mark.parametrize(("category", "name", "sect", "kind", "members", "page"), EACH_SECT)
def test_each_sects_merits_and_flaws_are_for_its_members(
    category: str, name: str, sect: str, kind: str, members: str, page: str
) -> None:
    trait = t(category, name, vampire().trait_properties(category, name)["rating"])
    assert vampire().kinds[(category, name)] == sect

    assert broken(held(sect, trait)) == []
    for other in [None, *({"Camarilla", "Sabbat", "Anarch"} - {sect})]:
        [during] = broken(held(other, trait))
        [after] = broken(held(other, trait), finished=True)
        where = page if page.startswith("Vol.") else f"p. {page}"
        assert during.message == (
            f"{name} is {kind}: only members of {members} can take it. ({where})"
        )
        # Needed to finish creation; once it is finished, waiting for review.
        assert (during.check.strength, after.check.strength) == ("complete", "review")


def test_anarch_republic_is_the_anarch_movement() -> None:
    assert (
        broken(held("Anarch Republic", t("merits", "Moniker"), t("flaws", "Once Enslaved"))) == []
    )


def test_general_merits_are_for_every_sect() -> None:
    assert (
        broken(held("Sabbat", t("merits", "Iron Will", 3), t("flaws", "Addiction (Amphetamine)")))
        == []
    )


EMISSARY = t("merits", "Emissary to the Camarilla")
EMISSARY_MESSAGE = (
    "Emissary to the Camarilla is for a character no sect has Accepted, not for members of"
    " the Camarilla, the Sabbat or the Anarch Movement. (p. 404)"
)


@pytest.mark.parametrize("sect", [None, "Autarkis", "Independent Alliance", "Inconnu", "Nictuku"])
def test_emissary_to_the_camarilla_is_for_those_no_sect_has_accepted(sect: str | None) -> None:
    assert broken(held(sect, EMISSARY)) == []
    assert broken(held(sect, EMISSARY), finished=True) == []


@pytest.mark.parametrize("sect", ["Camarilla", "Sabbat", "Anarch", "Anarch Republic"])
def test_emissary_to_the_camarilla_is_not_for_a_sects_members(sect: str) -> None:
    [refused] = broken(held(sect, EMISSARY))

    assert refused.message == EMISSARY_MESSAGE
    assert refused.check.key == "sect/merits/Emissary to the Camarilla"


def test_an_infiltrators_alternate_identity_opens_no_other_sects_merits() -> None:
    """An Alternate Identity may be Accepted by a second sect (p. 310), but the sheet
    does not say which, and the book gives it that sect's status, not its merits."""
    identity = t("backgrounds", "Alternate Identity", 4)

    [refused] = broken(held("Camarilla", identity, t("merits", "Sanctified")))

    assert refused.subject.name == "Sanctified"


def test_a_giovanni_of_the_independent_alliance_comes_to_the_camarilla_as_an_outsider() -> None:
    sheet = [
        t("clan", "Giovanni", None),
        t("sect", "Independent Alliance", None),
        t("merits", "Made"),
        EMISSARY,
        t("merits", "Antiquities"),
    ]

    assert [v.subject.name for v in broken(sheet)] == ["Antiquities"]


def test_once_finished_a_check_refuses_waits_for_review_or_notes() -> None:
    raw = {
        "category": "merits",
        "name": "Sanctified",
        "forbids": {"npc": False},
        "strength": "complete",
        "once_finished": "complete",
    }

    with pytest.raises(ValueError, match="once_finished must be refuse, review or note"):
        load_checks("test", [raw], vampire().traits, vampire().categories)
    loaded = load_checks(
        "test", [{**raw, "once_finished": "note"}], vampire().traits, vampire().categories
    )
    # Beside the checks the catalogue's requirements make.
    assert loaded[-1].once_finished == "note"


# --- in play ----------------------------------------------------------------------------


def creating(troupe: Troupe, sect: str, name: str = "Odile") -> str:
    """A Brujah of `sect` being built in the troupe, every pick placed."""
    made = troupe.player.client.post(
        "/characters", json={"splat": "vampire", "name": name, "building_troupe_id": troupe.id}
    )
    assert made.status_code == 201, made.text
    character_id: str = made.json()["id"]
    take(troupe.player, character_id, "clan", "Brujah", None)
    take(troupe.player, character_id, "sect", sect, None)
    for category, trait, rating in FULL_BUILD:
        placed = pick(troupe.player, character_id, category, trait, rating)
        assert placed.status_code == 200, (trait, placed.text)
    return character_id


def finish(person: Person, character_id: str) -> Any:
    return person.client.post(f"/characters/{character_id}/creation/complete")


def problems(person: Person, character_id: str) -> list[str]:
    return [p["message"] for p in sheet(person, character_id)["problems"]]


def approvals(troupe: Troupe) -> list[dict[str, Any]]:
    return troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()


def asked(troupe: Troupe, character_id: str, name: str) -> str:
    """Ask for a merit after acceptance (horatio.merit_requests): what the request
    tells the storytellers about it."""
    taken = take(troupe.player, character_id, "merits", name, 1)
    assert taken.status_code == 200, taken.text
    [request] = [a for a in approvals(troupe) if a["character_id"] == character_id]
    return request["player_note"]


def approve_all(troupe: Troupe) -> None:
    for request in approvals(troupe):
        approved = troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
        assert approved.status_code == 200, approved.text


def holds(person: Person, character_id: str, name: str) -> bool:
    return name in [t["name"] for t in sheet(person, character_id)["traits"]]


def of_sect(troupe: Troupe, sect: str, name: str = "Agnes") -> str:
    """A finished Brujah of `sect`, accepted by the troupe."""
    character_id = new_character(troupe, troupe.player, name, clan="Brujah")
    assert take(troupe.player, character_id, "sect", sect, None).status_code == 200
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    return character_id


SOUL_SHARD = "Soul Shard is a Sabbat flaw: only members of the Sabbat can take it. (p. 454)"
SANCTIFIED = "Sanctified is a Sabbat merit: only members of the Sabbat can take it. (p. 452)"


def test_creation_cannot_finish_with_another_sects_flaw(troupe: Troupe) -> None:
    character_id = creating(troupe, "Camarilla")
    # Allowed while the character is built, and shown as a problem on the sheet.
    assert pick(troupe.player, character_id, "flaws", "Soul Shard", 3).status_code == 200
    assert SOUL_SHARD in problems(troupe.player, character_id)

    refused = finish(troupe.player, character_id)

    assert refused.status_code == 409
    assert SOUL_SHARD in refused.json()["detail"]
    # A member of the Sabbat finishes with it.
    take(troupe.player, character_id, "sect", "Sabbat", None)
    assert finish(troupe.player, character_id).status_code == 200


def test_after_creation_another_sects_merit_waits_for_review(troupe: Troupe) -> None:
    """After acceptance a merit is asked for (horatio.merit_requests); the request
    tells the storytellers what it breaks, and they decide."""
    camarilla = of_sect(troupe, "Camarilla")
    sabbat = of_sect(troupe, "Sabbat", "Bram")

    assert SANCTIFIED in asked(troupe, camarilla, "Sanctified")
    assert SANCTIFIED not in asked(troupe, sabbat, "Sanctified")
    approve_all(troupe)
    assert holds(troupe.player, camarilla, "Sanctified")
    assert SANCTIFIED in problems(troupe.lead, camarilla)


def test_after_creation_with_no_home_troupe_it_is_flagged_for_acceptance(troupe: Troupe) -> None:
    """Before a home troupe, review checks let a change through: accepting the
    character reviews the whole sheet."""
    character_id = new_character(troupe, troupe.player, clan="Brujah")
    take(troupe.player, character_id, "sect", "Camarilla", None)

    assert take(troupe.player, character_id, "merits", "Sanctified", 1).status_code == 200
    assert SANCTIFIED in problems(troupe.player, character_id)


def test_a_sect_merit_moved_to_general_is_for_every_sect(troupe: Troupe) -> None:
    """#436: the checks key on the catalogue type the troupe's change swaps."""
    assert recategorise(troupe, "Soul Shard", "General", "flaws").status_code == 200
    assert recategorise(troupe, "Sanctified", "General").status_code == 200
    character_id = creating(troupe, "Camarilla")
    pick(troupe.player, character_id, "flaws", "Soul Shard", 3)

    assert finish(troupe.player, character_id).status_code == 200
    assert take(troupe.player, character_id, "merits", "Sanctified", 1).status_code == 200
    assert approvals(troupe) == []
    assert problems(troupe.player, character_id) == []


def test_the_checks_are_listed_together_and_a_troupe_can_switch_one_off(troupe: Troupe) -> None:
    listed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/checks").json()
    sect = {
        c["key"]: c for c in listed if c["group"] == "Sect merits and flaws, only for their sect"
    }
    assert sorted(sect) == [
        "sect/flaws/Anarch",
        "sect/flaws/Camarilla",
        "sect/flaws/Sabbat",
        "sect/merits/Anarch",
        "sect/merits/Camarilla",
        "sect/merits/Emissary to the Camarilla",
        "sect/merits/Independent Alliance",
        "sect/merits/Sabbat",
    ]
    assert {(c["strength"], c["once_finished"]) for c in sect.values()} == {("complete", "review")}

    off = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/checks/sect/merits/Sabbat", json={"strength": "off"}
    )

    assert off.status_code == 200, off.text
    camarilla = of_sect(troupe, "Camarilla")
    assert SANCTIFIED not in asked(troupe, camarilla, "Sanctified")
    approve_all(troupe)
    assert holds(troupe.player, camarilla, "Sanctified")
    assert SANCTIFIED not in problems(troupe.player, camarilla)
    # The Sabbat's flaws are a check of their own, still on.
    building = creating(troupe, "Camarilla", "Bram")
    pick(troupe.player, building, "flaws", "Soul Shard", 3)
    assert finish(troupe.player, building).status_code == 409


def test_a_troupes_strength_is_for_before_and_after_creation(troupe: Troupe) -> None:
    played = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/checks/sect/merits/Sabbat", json={"strength": "refuse"}
    )
    assert (played.json()["house"], played.json()["once_finished"]) == ("refuse", "review")
    camarilla = of_sect(troupe, "Camarilla")

    refused = take(troupe.player, camarilla, "merits", "Sanctified", 1)

    assert refused.status_code == 409
    assert SANCTIFIED in refused.json()["detail"]
    read = troupe.stranger.client.get(f"/troupes/{troupe.id}/house-rules").json()
    assert {
        "rule": "{name} is a Sabbat merit: only members of the Sabbat can take it.",
        "page": "452",
        "strength": "complete",
        "house": "refuse",
        "once_finished": "review",
        "own": False,
    } in read["checks"]


def test_a_change_of_sect_leaves_the_old_sects_merits_flagged(troupe: Troupe) -> None:
    character_id = of_sect(troupe, "Sabbat")
    asked(troupe, character_id, "Sanctified")
    approve_all(troupe)

    moved = take(troupe.player, character_id, "sect", "Camarilla", None)

    assert moved.status_code == 200, moved.text
    assert holds(troupe.player, character_id, "Sanctified")
    assert SANCTIFIED in problems(troupe.player, character_id)
    # Nothing waits on the troupe for it, and other changes go on.
    assert approvals(troupe) == []
    assert take(troupe.player, character_id, "skills", "Brawl", 1).status_code == 200


def test_a_character_already_holding_another_sects_merit_is_flagged(troupe: Troupe) -> None:
    """One bought before the check, here while the troupe had it off."""
    troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/checks/sect/merits/Sabbat", json={"strength": "off"}
    )
    character_id = of_sect(troupe, "Camarilla")
    asked(troupe, character_id, "Sanctified")
    approve_all(troupe)
    assert SANCTIFIED not in problems(troupe.player, character_id)

    troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/checks/sect/merits/Sabbat", json={"strength": None}
    )

    assert holds(troupe.player, character_id, "Sanctified")
    assert SANCTIFIED in problems(troupe.player, character_id)
    # Staff see it too.
    assert SANCTIFIED in problems(troupe.lead, character_id)


def test_an_emissary_to_the_camarilla_with_no_sect(troupe: Troupe) -> None:
    character_id = creating(troupe, "Independent Alliance")
    pick(troupe.player, character_id, "merits", "Emissary to the Camarilla", 1)
    assert finish(troupe.player, character_id).status_code == 200

    camarilla = creating(troupe, "Camarilla", "Bram")
    pick(troupe.player, camarilla, "merits", "Emissary to the Camarilla", 1)
    refused = finish(troupe.player, camarilla)
    assert refused.status_code == 409
    assert EMISSARY_MESSAGE in refused.json()["detail"]

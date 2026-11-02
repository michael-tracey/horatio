"""A troupe's own checks (#432): storytellers build them from blocks, they run through
the same engine as the book's, and the characters they break are flagged, not
changed. Each of Land of the Sky's five examples can be built."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent
from horatio.rules.checks import Context, violations
from horatio.rules.house_checks import is_house_check
from horatio.rules.model import SheetTrait
from horatio.rules.store import forget_rules, read_troupe_rules
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_creation import FULL_BUILD, pick

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def add(troupe: Troupe, check: dict[str, Any], person: Person | None = None) -> Any:
    return (person or troupe.storyteller).client.post(
        f"/troupes/{troupe.id}/house-checks", json=check
    )


def added(troupe: Troupe, check: dict[str, Any]) -> dict[str, Any]:
    response = add(troupe, check)
    assert response.status_code == 201, response.text
    return response.json()


def accepted(troupe: Troupe, clan: str, name: str = "Agnes", merit: str | None = None) -> str:
    """A finished character the troupe has accepted, holding `merit` from before."""
    character_id = new_character(troupe, troupe.player, name, clan=clan)
    if merit is not None:
        bought = take(troupe.player, character_id, "merits", merit, 3)
        assert bought.status_code == 200, bought.text
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    return character_id


def take(person: Person, character_id: str, category: str, name: str, rating: int | None) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating},
    )


# Iron Will is a General merit anyone may take; this troupe keeps it for the Ventrue.
IRON_WILL_FOR_VENTRUE = {
    "category": "merits",
    "name": "Iron Will",
    "mode": "requires",
    "condition": {"clan_family": ["Ventrue"]},
    "strength": "refuse",
    "message": "Iron Will is for the Ventrue here.",
}


# --- the five examples ---------------------------------------------------------------

PLIABLE_BLOOD = {
    "category": "merits",
    "name": "Pliable Blood",
    "mode": "forbids",
    "condition": {"finished": True},
    "strength": "refuse",
    "message": "Pliable Blood can only be taken at character creation.",
}
OLD_BLOOD = {
    "category": "backgrounds",
    "name": "Generation",
    "mode": "requires",
    "condition": {
        "any_of": [
            {"not": {"clan_family": ["Daughters of Cacophony", "Nagaraja"]}},
            {"generation": {"lte": 4}},
        ]
    },
    "strength": "complete",
    "message": "Daughters of Cacophony and Nagaraja can be no older than Generation 4.",
    "step": "backgrounds",
}
SECOND_IDENTITY = {
    "category": "clan",
    "mode": "requires",
    "condition": {
        "any_of": [
            {
                "not": {
                    "clan": [
                        "Caitiff",
                        "Nagaraja",
                        "Followers of Set",
                        "Giovanni",
                        "Tremere: Telyav",
                    ]
                }
            },
            {"has": {"category": "backgrounds", "name": "Alternate Identity", "rating": 5}},
        ]
    },
    "strength": "complete",
    "message": "{name} need Alternate Identity 5.",
}
ONE_SHARED = {
    "category": "backgrounds",
    "mode": "forbids",
    "condition": {"copies": {"gte": 2}, "self": {"names": ["Allies", "Contacts", "Haven", "Herd"]}},
    "strength": "refuse",
    "message": "A character may hold only one {name}.",
}
EMISSARY = {
    "category": "sect",
    "mode": "requires",
    "condition": {
        "any_of": [
            {"has": {"category": "sect", "name": "Camarilla"}},
            {"has": {"category": "merits", "name": "Emissary to the Camarilla"}},
        ]
    },
    "strength": "review",
    "message": "A character not of the Camarilla needs Emissary to the Camarilla.",
}


def broken(
    troupe: Troupe, sheet: list[SheetTrait], *, finished: bool = True
) -> list[tuple[str, str]]:
    """The troupe's own checks the sheet breaks, as the troupe's rules run them:
    (message, subject)."""
    forget_rules(troupe.session)
    rules = read_troupe_rules(troupe.session, "vampire", uuid.UUID(troupe.id))
    own = [c for c in rules.checks() if is_house_check(c.key)]
    context = Context(finished=finished, kinds=rules.rule_set.kinds)
    return [(v.message, v.subject.full_name) for v in violations(own, sheet, context)]


HOUSE = " (House rule — Lords of the Night)"


def test_pliable_blood_only_at_creation(troupe: Troupe) -> None:
    made = added(troupe, PLIABLE_BLOOD)
    assert made["text"] == "Pliable Blood: refused once creation is finished."
    sheet = [SheetTrait("clan", "Nosferatu"), SheetTrait("merits", "Pliable Blood", 3)]

    assert broken(troupe, sheet, finished=False) == []
    assert broken(troupe, sheet) == [
        ("Pliable Blood can only be taken at character creation." + HOUSE, "Pliable Blood")
    ]


def test_daughters_and_nagaraja_no_older_than_generation_4(troupe: Troupe) -> None:
    made = added(troupe, OLD_BLOOD)
    assert made["text"] == (
        "Generation: to be put right before creation is finished unless either the clan is "
        "not Daughters of Cacophony or Nagaraja nor one of their bloodlines or Generation 4 "
        "or less."
    )

    def generation(clan: str, rating: int) -> list[tuple[str, str]]:
        return broken(
            troupe, [SheetTrait("clan", clan), SheetTrait("backgrounds", "Generation", rating)]
        )

    assert generation("Nagaraja", 4) == []
    assert [s for _, s in generation("Nagaraja", 5)] == ["Generation"]
    assert [s for _, s in generation("Daughters of Cacophony", 5)] == ["Generation"]
    assert generation("Ventrue", 5) == []


def test_some_clans_need_alternate_identity_5(troupe: Troupe) -> None:
    added(troupe, SECOND_IDENTITY)

    def identity(clan: str, rating: int | None) -> list[str]:
        sheet = [SheetTrait("clan", clan)]
        if rating is not None:
            sheet.append(SheetTrait("backgrounds", "Alternate Identity", rating, detail="Mr Grey"))
        return [m for m, _ in broken(troupe, sheet)]

    assert identity("Giovanni", None) == ["Giovanni need Alternate Identity 5." + HOUSE]
    assert identity("Tremere: Telyav", 4) == ["Tremere: Telyav need Alternate Identity 5." + HOUSE]
    assert identity("Caitiff", 5) == []
    assert identity("Tremere", None) == []
    assert identity("Followers of Set", 5) == []


def test_one_of_each_shared_background(troupe: Troupe) -> None:
    added(troupe, ONE_SHARED)
    two_havens = [
        SheetTrait("backgrounds", "Haven", 2, detail="Docks"),
        SheetTrait("backgrounds", "Haven", 1, detail="Chantry"),
    ]
    two_identities = [
        SheetTrait("backgrounds", "Alternate Identity", 2, detail="Mr Grey"),
        SheetTrait("backgrounds", "Alternate Identity", 1, detail="Mr Brown"),
    ]

    assert {m for m, _ in broken(troupe, two_havens)} == {
        "A character may hold only one Haven: Docks." + HOUSE,
        "A character may hold only one Haven: Chantry." + HOUSE,
    }
    assert broken(troupe, two_havens[:1]) == []
    assert broken(troupe, two_identities) == []


def test_outside_the_camarilla_needs_emissary(troupe: Troupe) -> None:
    added(troupe, EMISSARY)

    assert broken(troupe, [SheetTrait("sect", "Camarilla")]) == []
    assert [s for _, s in broken(troupe, [SheetTrait("sect", "Anarch")])] == ["Anarch"]
    assert (
        broken(
            troupe,
            [SheetTrait("sect", "Anarch"), SheetTrait("merits", "Emissary to the Camarilla", 1)],
        )
        == []
    )


def test_a_clan_merit_subject_by_catalogue_type(troupe: Troupe) -> None:
    """A subject by type: Clan merits need the character's creation unfinished."""
    added(
        troupe,
        {
            "category": "merits",
            "kind": "Clan",
            "mode": "requires",
            "condition": {"not": {"finished": True}},
            "strength": "note",
            "message": "Clan merits are chosen at creation here.",
        },
    )

    assert broken(troupe, [SheetTrait("merits", "Iron Will", 3)]) == []
    assert [s for _, s in broken(troupe, [SheetTrait("merits", "Pliable Blood", 3)])] == [
        "Pliable Blood"
    ]
    assert broken(troupe, [SheetTrait("merits", "Pliable Blood", 3)], finished=False) == []


# --- through the API ---------------------------------------------------------------


def test_storytellers_add_change_and_remove_and_the_log_says_so(troupe: Troupe) -> None:
    assert add(troupe, IRON_WILL_FOR_VENTRUE, troupe.assistant).status_code == 403
    made = added(troupe, IRON_WILL_FOR_VENTRUE)
    path = f"/troupes/{troupe.id}/house-checks/{made['id']}"

    listed = troupe.assistant.client.get(f"/troupes/{troupe.id}/house-checks").json()
    assert [c["id"] for c in listed] == [made["id"]]
    assert (
        listed[0]["text"]
        == "Iron Will: refused unless the clan is Ventrue or one of its bloodlines."
    )
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/house-checks").status_code == 403
    assert troupe.assistant.client.put(path, json=IRON_WILL_FOR_VENTRUE).status_code == 403

    changed = troupe.storyteller.client.put(
        path, json={**IRON_WILL_FOR_VENTRUE, "strength": "note"}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["strength"] == "note"
    assert troupe.storyteller.client.delete(path).status_code == 204
    assert troupe.storyteller.client.get(f"/troupes/{troupe.id}/house-checks").json() == []
    assert troupe.storyteller.client.delete(path).status_code == 404

    actions = troupe.session.scalars(
        select(AuditEvent.action)
        .where(
            AuditEvent.troupe_id == uuid.UUID(troupe.id), AuditEvent.action.like("house.check_%")
        )
        .order_by(AuditEvent.created_at)
    ).all()
    assert actions == ["house.check_added", "house.check_changed", "house.check_removed"]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"condition": {"clan": "Ventrue"}}, "Choose at least one clan."),
        ({"condition": {"clan": ["Martians"]}}, "Martians: no such clan in these rules."),
        ({"condition": {"in_clan": True}}, "A house check cannot use 'in_clan'."),
        ({"condition": {}}, "Add at least one block to the condition."),
        ({"condition": {"generation": {"lte": 9}}}, "Generation is 1 to 5."),
        (
            {"condition": {"has": {"category": "merits", "name": "Juggling"}}},
            "Juggling is not one of the merits.",
        ),
        ({"name": "Juggling"}, "Juggling is not one of the merits."),
        ({"message": " "}, "Write the message the player sees."),
        ({"step": "backgrounds"}, "Only a check needed to finish creation can name a step."),
        ({"name_prefix": "Bloodline:"}, "A check is about one trait, a name prefix or a type."),
    ],
)
def test_a_check_the_rules_cannot_run_is_refused(
    troupe: Troupe, change: dict[str, Any], problem: str
) -> None:
    refused = add(troupe, {**IRON_WILL_FOR_VENTRUE, **change})

    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == problem


def test_it_refuses_a_purchase_as_a_book_check_does(troupe: Troupe) -> None:
    character_id = accepted(troupe, "Brujah")
    added(troupe, IRON_WILL_FOR_VENTRUE)

    refused = take(troupe.player, character_id, "merits", "Iron Will", 3)

    assert refused.status_code == 409, refused.text
    assert "Iron Will is for the Ventrue here." in refused.json()["detail"]


def test_review_holds_the_purchase_for_the_troupe(troupe: Troupe) -> None:
    character_id = accepted(troupe, "Brujah")
    added(troupe, {**IRON_WILL_FOR_VENTRUE, "strength": "review"})

    taken = take(troupe.player, character_id, "merits", "Iron Will", 3)

    assert taken.status_code == 200, taken.text
    [request] = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()
    assert "Iron Will is for the Ventrue here." in request["player_note"]


def test_complete_holds_finishing_creation_and_names_the_step(troupe: Troupe) -> None:
    made = troupe.player.client.post(
        "/characters", json={"splat": "vampire", "name": "Odile", "building_troupe_id": troupe.id}
    )
    character_id = made.json()["id"]
    take(troupe.player, character_id, "clan", "Brujah", None)
    added(
        troupe,
        {
            "category": "backgrounds",
            "name": "Fame",
            "mode": "forbids",
            "condition": {"clan_family": ["Brujah"]},
            "strength": "complete",
            "message": "No Brujah is famous here.",
            "step": "backgrounds",
        },
    )
    for category, name, rating in FULL_BUILD:
        placed = pick(troupe.player, character_id, category, name, rating)
        assert placed.status_code == 200, (name, placed.text)

    state = troupe.player.client.get(f"/characters/{character_id}/creation").json()
    assert {"step": "backgrounds", "message": "No Brujah is famous here." + HOUSE} in state["needs"]
    finished = troupe.player.client.post(f"/characters/{character_id}/creation/complete")
    assert finished.status_code == 409
    assert "No Brujah is famous here." in finished.text


def test_those_it_breaks_are_listed_first_then_flagged_not_changed(troupe: Troupe) -> None:
    character_id = accepted(troupe, "Brujah", "Bertrand", merit="Iron Will")

    preview = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/house-checks/preview",
        json={"check": {**IRON_WILL_FOR_VENTRUE, "message": ""}},
    ).json()
    assert preview["problem"] is None
    assert preview["text"].startswith("Iron Will: refused unless")
    assert [(b["name"], b["message"]) for b in preview["breaking"]] == [
        ("Bertrand", preview["text"] + HOUSE)
    ]

    made = added(troupe, IRON_WILL_FOR_VENTRUE)
    assert [b["name"] for b in made["breaking"]] == ["Bertrand"]
    sheet = troupe.player.client.get(f"/characters/{character_id}/sheet").json()
    assert "Iron Will" in [t["name"] for t in sheet["traits"]]
    assert "Iron Will is for the Ventrue here." + HOUSE in [p["message"] for p in sheet["problems"]]
    # A check the sheet already broke stops no other change.
    assert take(troupe.player, character_id, "merits", "Calm Heart", 1).status_code == 409
    assert take(troupe.player, character_id, "backgrounds", "Resources", 1).status_code == 200


def test_a_preview_says_what_is_missing(troupe: Troupe) -> None:
    preview = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/house-checks/preview",
        json={"check": {**IRON_WILL_FOR_VENTRUE, "condition": {}}},
    ).json()

    assert preview == {
        "text": "",
        "problem": "Add at least one block to the condition.",
        "breaking": [],
    }


def test_own_checks_are_listed_apart_and_for_players(troupe: Troupe) -> None:
    made = added(troupe, IRON_WILL_FOR_VENTRUE)

    book = troupe.storyteller.client.get(f"/troupes/{troupe.id}/checks").json()
    assert made["key"] not in [c["key"] for c in book]
    assert (
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/checks/{made['key']}", json={"strength": "off"}
        ).status_code
        == 404
    )
    rules = troupe.stranger.client.get(f"/troupes/{troupe.id}/house-rules").json()
    assert {
        "rule": "Iron Will is for the Ventrue here.",
        "page": None,
        "strength": "refuse",
        "house": "refuse",
        "own": True,
    } in rules["checks"]

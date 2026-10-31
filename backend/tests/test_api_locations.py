"""Locations (issue #325): the troupe's staff-only record of its Stock Locations and
havens, with qualities from the catalogue as the troupe plays it, the quality
limits, negatives kept secret, conglomerates and the control limit."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_downtimes import member_character

GROVE = [
    "Size",
    "Guards",
    "Location",
    "Staff",
    "Profitable",
    "Profitable",
    "Historic",
    "Fancy",
    "Luxury",
    "Haunt",
]


class Scene:
    """Agnes, at home in the troupe, played by its player."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.agnes = member_character(troupe, troupe.player, "Agnes")

    @property
    def path(self) -> str:
        return f"/troupes/{self.troupe.id}/locations"

    def add(self, by: Person | None = None, **body: Any) -> Any:
        return (by or self.troupe.storyteller).client.post(self.path, json=body)

    def added(self, **body: Any) -> dict[str, Any]:
        made = self.add(**body)
        assert made.status_code == 201, made.text
        return made.json()

    def change(self, location: dict[str, Any], **body: Any) -> Any:
        return self.troupe.storyteller.client.patch(f"/locations/{location['id']}", json=body)

    def give(
        self, character_id: str, category: str, name: str, rating: int, detail: str = ""
    ) -> None:
        given = self.troupe.storyteller.client.post(
            f"/characters/{character_id}/give",
            json={
                "category": category,
                "name": name,
                "detail": detail,
                "rating": rating,
                "free": True,
                "reason": "test",
            },
        )
        assert given.status_code == 200, given.text

    def option(self, key: str, on: bool) -> None:
        set_ = self.troupe.storyteller.client.put(
            f"/troupes/{self.troupe.id}/location-options/{key}", json={"on": on}
        )
        assert set_.status_code == 200, set_.text

    def limit(self, strength: str) -> None:
        set_ = self.troupe.storyteller.client.put(
            f"/troupes/{self.troupe.id}/location-limit", json={"strength": strength}
        )
        assert set_.status_code == 200, set_.text

    def controlled_by(self, character_id: str, name: str, **body: Any) -> Any:
        return self.add(name=name, control="character", controller_id=character_id, **body)

    def messages(self) -> list[str]:
        log = self.troupe.lead.client.get(f"/troupes/{self.troupe.id}/log").json()
        return [e["message"] for e in log]


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def qualities(*names: str) -> list[dict[str, str]]:
    return [{"name": n} for n in names]


# --- the Grove Arcade ------------------------------------------------------------------


def test_a_storyteller_adds_the_grove_arcade(scene: Scene) -> None:
    grove = scene.added(
        name="Grove Arcade",
        kind="prestige",
        rating=5,
        qualities=qualities(*GROVE),
        control="character",
        controller_id=scene.agnes,
        influence_type="elite",
        influence_area="Commercial Industry",
        feeding_block="The Rack",
        address="1 Page Ave, Asheville",
    )

    assert (grove["kind"], grove["rating"]) == ("prestige", 5)
    assert [q["name"] for q in grove["qualities"]] == GROVE
    assert (grove["quality_count"], grove["most_qualities"]) == (10, 10)
    assert grove["controller"] == {"id": scene.agnes, "name": "Agnes"}
    assert (grove["influence_area"], grove["feeding_block"]) == ("Commercial Industry", "The Rack")
    assert grove["warnings"] == []
    assert "storyteller added the location Grove Arcade." in scene.messages()

    eleventh = scene.change(grove, qualities=qualities(*GROVE, "Isolated"))
    assert eleventh.status_code == 422
    assert eleventh.json()["detail"] == (
        "A prestige 5 location has at most 10 qualities (Vol. II Issue 1, p. 121); "
        "this one would have 11."
    )


def test_a_standard_location_takes_its_rating_in_qualities(scene: Scene) -> None:
    made = scene.add(name="Bar", rating=2, qualities=qualities("Isolated", "Size", "Staff"))
    assert made.status_code == 422
    assert "A standard 2 location has at most 2 qualities" in made.json()["detail"]


def test_iconic_qualities_only_on_an_iconic_location(scene: Scene) -> None:
    refused = scene.add(name="Hall", kind="prestige", rating=3, qualities=qualities("Celebrity"))
    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("Celebrity is an iconic quality")
    assert (
        scene.add(
            name="Hall", kind="iconic", rating=3, qualities=qualities("Celebrity")
        ).status_code
        == 201
    )


def test_one_supernatural_quality_at_most(scene: Scene) -> None:
    refused = scene.add(name="Crypt", rating=3, qualities=qualities("Haunt", "Buffet"))
    assert refused.status_code == 422
    assert "one supernatural quality at most" in refused.json()["detail"]


def test_a_quality_is_held_once_unless_it_says_otherwise(scene: Scene) -> None:
    twice = scene.add(name="Mill", rating=3, qualities=qualities("Size", "Size"))
    assert twice.status_code == 422
    assert twice.json()["detail"] == "A location has Size only once (Vol. II Issue 1, p. 123)."
    labs = scene.add(
        name="Lab",
        rating=3,
        qualities=[
            {"name": "Laboratory", "detail": "Chemistry"},
            {"name": "Laboratory", "detail": "Biology"},
        ],
    )
    assert labs.status_code == 201, labs.text
    assert [q["detail"] for q in labs.json()["qualities"]] == ["Chemistry", "Biology"]


# --- house options ---------------------------------------------------------------------


def test_fancy_needs_rating_four_while_the_limits_option_is_on(scene: Scene) -> None:
    assert scene.add(name="Club", rating=4, qualities=qualities("Fancy")).status_code == 201

    refused = scene.add(name="Lounge", rating=3, qualities=qualities("Fancy"))
    assert refused.status_code == 422
    assert refused.json()["detail"] == (
        "Fancy needs a location rated 4 or higher (house option: Limits on qualities)."
    )

    scene.option("quality_limits", False)
    assert scene.add(name="Lounge", rating=3, qualities=qualities("Fancy")).status_code == 201
    assert "storyteller switched the location house option Limits on qualities off." in (
        scene.messages()
    )


def test_profitable_twice_only_under_the_limits_option(scene: Scene) -> None:
    scene.option("quality_limits", False)
    twice = scene.add(
        name="Mall", kind="prestige", rating=3, qualities=qualities("Profitable", "Profitable")
    )
    assert twice.status_code == 422
    scene.option("quality_limits", True)
    # A prestige 3 can have 6 qualities: Profitable twice, one for each 3.
    assert (
        scene.add(
            name="Mall", kind="prestige", rating=3, qualities=qualities("Profitable", "Profitable")
        ).status_code
        == 201
    )
    thrice = scene.add(
        name="Shops", kind="prestige", rating=3, qualities=qualities(*["Profitable"] * 3)
    )
    assert thrice.status_code == 422
    assert "Profitable at most twice" in thrice.json()["detail"]


def test_derelict_does_not_count_and_libraries_split(scene: Scene) -> None:
    made = scene.add(
        name="Old mill", rating=1, qualities=qualities("Derelict", "Library [Mundane]")
    )
    assert made.status_code == 201, made.text
    assert made.json()["quality_count"] == 1

    catalogue = scene.troupe.storyteller.client.get(f"{scene.path}/catalogue").json()
    names = [q["name"] for q in catalogue["qualities"]]
    assert "Library [Repository]" in names and "Library" not in names
    scene.option("two_libraries", False)
    scene.option("house_qualities", False)
    catalogue = scene.troupe.storyteller.client.get(f"{scene.path}/catalogue").json()
    names = [q["name"] for q in catalogue["qualities"]]
    assert "Library" in names and "Library [Mundane]" not in names and "Derelict" not in names
    # A quality the location already has stays, counted as a standard one.
    kept = scene.troupe.storyteller.client.get(f"/locations/{made.json()['id']}").json()
    assert [(q["name"], q["known"]) for q in kept["qualities"]] == [
        ("Derelict", False),
        ("Library [Mundane]", False),
    ]
    assert scene.add(name="Ruin", rating=2, qualities=qualities("Derelict")).status_code == 422


def test_the_troupe_adds_a_quality_of_its_own(scene: Scene) -> None:
    made = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/location-qualities",
        json={
            "name": "Rooftop",
            "text": "A view over the city.",
            "suggested": [{"trait": "Athletics", "levels": [2, 3, 4]}, {"text": "A good ladder"}],
        },
    )
    assert made.status_code == 201, made.text
    catalogue = scene.troupe.storyteller.client.get(f"{scene.path}/catalogue").json()
    rooftop = next(q for q in catalogue["qualities"] if q["name"] == "Rooftop")
    assert rooftop["house"] is True
    assert rooftop["suggested"][0]["levels"] == [2, 3, 4]
    assert scene.add(name="Tower", rating=1, qualities=qualities("Rooftop")).status_code == 201
    clash = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/location-qualities", json={"name": "Fancy", "text": "x"}
    )
    assert clash.status_code == 409
    by_assistant = scene.troupe.assistant.client.post(
        f"/troupes/{scene.troupe.id}/location-qualities", json={"name": "Pier", "text": "x"}
    )
    assert by_assistant.status_code == 403


# --- negatives -------------------------------------------------------------------------


def test_a_secret_compromised_is_kept_from_the_controllers_player(scene: Scene) -> None:
    bar = scene.added(
        name="The Rack bar",
        rating=2,
        control="character",
        controller_id=scene.agnes,
        negatives=[{"name": "Compromised", "level": 1, "secret": True, "by": "hunters"}],
    )
    assert bar["negatives"] == [
        {
            "name": "Compromised",
            "level": 1,
            "secret": True,
            "by": "hunters",
            "effect": "Hostile forces watch who comes and goes.",
            "games": 0,
        }
    ]
    player = scene.troupe.player.client
    assert player.get(f"/locations/{bar['id']}").status_code == 404
    assert player.get(scene.path).status_code == 403
    assert player.get(f"/characters/{scene.agnes}/locations").status_code == 403


def test_a_negative_goes_to_three_or_four_with_its_quality(scene: Scene) -> None:
    four = [{"name": "Damaged", "level": 4}]
    refused = scene.add(name="Shed", rating=1, negatives=four)
    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("Damaged goes from ×1 to ×3")
    assert (
        scene.add(
            name="Bunker", rating=1, qualities=qualities("Sturdy"), negatives=four
        ).status_code
        == 201
    )


# --- control ---------------------------------------------------------------------------


def test_retainers_raise_the_control_limit(scene: Scene) -> None:
    scene.give(scene.agnes, "backgrounds", "Retainers", 1, "Igor")
    for n in range(6):
        assert scene.controlled_by(scene.agnes, f"Shop {n}").status_code == 201

    seventh = scene.controlled_by(scene.agnes, "Shop 6")
    assert seventh.status_code == 409
    assert seventh.json()["detail"] == (
        "Agnes would control 7 locations, over the 6 they can: 5, and one for each dot of "
        "Retainers (Retainers 1) (Vol. II Issue 1, p. 119)."
    )

    scene.limit("note")
    noted = scene.controlled_by(scene.agnes, "Shop 6")
    assert noted.status_code == 201, noted.text
    assert noted.json()["warnings"] == [seventh.json()["detail"]]
    standing = scene.troupe.storyteller.client.get(f"/characters/{scene.agnes}/locations").json()
    assert (standing["controls"], standing["limit"], standing["over"]) == (7, 6, True)


def test_joint_control_counts_for_both(scene: Scene) -> None:
    bram = member_character(scene.troupe, scene.troupe.player, "Bram")
    for n in range(5):
        assert scene.controlled_by(bram, f"Stall {n}").status_code == 201
    shared = scene.controlled_by(scene.agnes, "Stall 5", joint_id=bram)
    assert shared.status_code == 409
    assert shared.json()["detail"].startswith("Bram would control 6 locations")


def test_a_conglomerate_lists_its_subsidiaries_and_comes_free(scene: Scene) -> None:
    office = scene.added(
        name="Mall office",
        rating=2,
        qualities=qualities("Conglomerate"),
        control="character",
        controller_id=scene.agnes,
    )
    scene.added(
        name="Mall bookshop",
        parent_id=office["id"],
        control="character",
        controller_id=scene.agnes,
    )
    scene.added(name="Mall cafe", parent_id=office["id"], control="named", controller_name="Doris")

    read = scene.troupe.storyteller.client.get(f"/locations/{office['id']}").json()
    assert [
        (s["name"], s["controller"]["name"], s["with_parent"]) for s in read["subsidiaries"]
    ] == [
        ("Mall bookshop", "Agnes", True),
        ("Mall cafe", "Doris", False),
    ]
    assert read["not_counted"] is None

    cafe = next(s for s in read["subsidiaries"] if s["name"] == "Mall cafe")
    assert scene.change(cafe, control="character", controller_id=scene.agnes).status_code == 200
    read = scene.troupe.storyteller.client.get(f"/locations/{office['id']}").json()
    assert read["not_counted"] == "a conglomerate whose every subsidiary it controls"
    standing = scene.troupe.storyteller.client.get(f"/characters/{scene.agnes}/locations").json()
    assert standing["controls"] == 2

    loop = scene.change(office, parent_id=cafe["id"])
    assert loop.status_code == 422


def test_uncontrollable_has_no_controller(scene: Scene) -> None:
    made = scene.added(
        name="Capitol", kind="iconic", rating=5, control="uncontrollable", locked=True
    )
    assert (made["control"], made["controller"], made["locked"]) == ("uncontrollable", None, True)
    joint = scene.change(made, joint_name="Doris")
    assert joint.status_code == 422


# --- havens ----------------------------------------------------------------------------


def test_a_haven_is_placed_with_its_advantages_and_not_counted(scene: Scene) -> None:
    no_haven = scene.add(name="Agnes's flat", kind="haven", rating=2, haven_of_id=scene.agnes)
    assert no_haven.status_code == 422
    assert no_haven.json()["detail"] == "Agnes has no Haven background."

    scene.give(scene.agnes, "backgrounds", "Haven", 2)
    too_many = scene.add(
        name="Agnes's flat",
        kind="haven",
        rating=2,
        haven_of_id=scene.agnes,
        haven_advantages=["Security", "Luxury", "Size"],
    )
    assert too_many.status_code == 422
    occult = scene.add(
        name="Agnes's flat",
        kind="haven",
        rating=2,
        haven_of_id=scene.agnes,
        haven_advantages=["Occult"],
    )
    assert (
        occult.json()["detail"] == "The Occult advantage needs the Occult skill (MET: VTM, p. 102)."
    )

    flat = scene.added(
        name="Agnes's flat",
        kind="haven",
        rating=2,
        haven_of_id=scene.agnes,
        control="character",
        controller_id=scene.agnes,
        address="12 Elm St",
        haven_advantages=["Security", "Luxury"],
    )
    assert (flat["address"], flat["haven_advantages"]) == ("12 Elm St", ["Security", "Luxury"])
    assert flat["not_counted"] == "a Haven"
    standing = scene.troupe.storyteller.client.get(f"/characters/{scene.agnes}/locations").json()
    assert standing["controls"] == 0
    assert [(h["name"], h["not_counted"]) for h in standing["locations"]] == [
        ("Agnes's flat", "a Haven")
    ]
    with_qualities = scene.change(flat, qualities=qualities("Size"))
    assert with_qualities.status_code == 422


def test_security_is_free_on_a_haven_of_someone_with_the_skill(scene: Scene) -> None:
    scene.give(scene.agnes, "backgrounds", "Haven", 1)
    scene.give(scene.agnes, "skills", "Security", 1)
    loft = scene.added(
        name="Loft", rating=2, qualities=qualities("Security", "Firewall"), haven_of_id=scene.agnes
    )
    free = {q["name"]: q["free_here"] for q in loft["qualities"]}
    assert free["Security"] == (
        "Free for Agnes, whose Haven this is, with Security (Vol. II Issue 1, p. 123)."
    )
    assert free["Firewall"] == "Free on a Haven of someone with Computer (Vol. II Issue 1, p. 122)."


# --- Elysium ---------------------------------------------------------------------------


def test_an_elysium_earns_its_qualities_with_time(scene: Scene) -> None:
    not_elysium = scene.add(name="Museum", rating=3, qualities=qualities("Soothing"))
    assert not_elysium.status_code == 422
    new = scene.add(
        name="Museum", rating=3, elysium_since=2026, qualities=qualities("Soothing", "Quarantined")
    )
    assert new.status_code == 422
    assert "has 1 Elysium quality" in new.json()["detail"]
    old = scene.add(
        name="Museum",
        rating=3,
        elysium_since=1900,
        qualities=qualities("Soothing", "Quarantined", "Holy Ground"),
    )
    assert old.status_code == 201, old.text
    assert old.json()["elysium_qualities"] >= 3
    # Elysium qualities don't count toward the location's qualities.
    assert old.json()["quality_count"] == 0
    clash = scene.add(
        name="Gallery", rating=3, elysium_since=1800, qualities=qualities("Arena", "Traditional")
    )
    assert clash.status_code == 422
    assert clash.json()["detail"].startswith("Arena can't be held with Traditional")


# --- who sees it -----------------------------------------------------------------------


def test_only_storytellers_and_assistants_see_the_list(scene: Scene) -> None:
    made = scene.added(name="Warehouse", rating=1)
    for person in (scene.troupe.storyteller, scene.troupe.assistant, scene.troupe.lead):
        assert person.client.get(scene.path).status_code == 200
        assert person.client.get(f"/locations/{made['id']}").status_code == 200
    for person in (scene.troupe.narrator, scene.troupe.player, scene.troupe.stranger):
        assert person.client.get(scene.path).status_code == 403
        assert person.client.get(f"{scene.path}/catalogue").status_code == 403
        assert person.client.get(f"/locations/{made['id']}").status_code == 404
        assert scene.add(by=person, name="Shed").status_code == 403


def test_the_location_keeps_a_log_of_changes(scene: Scene) -> None:
    made = scene.added(name="Warehouse", rating=2)
    changed = scene.change(
        made,
        address="3 Dock Rd",
        qualities=qualities("Size"),
        control="character",
        controller_id=scene.agnes,
        negatives=[{"name": "Shunned", "level": 2}],
    )
    assert changed.status_code == 200, changed.text
    log = scene.troupe.storyteller.client.get(f"/locations/{made['id']}").json()["log"]
    assert [e["message"] for e in log] == [
        "storyteller changed Warehouse: controller Agnes; address; qualities +Size; "
        "negatives +Shunned ×2.",
        "storyteller added the location Warehouse.",
    ]
    assert scene.troupe.storyteller.client.delete(f"/locations/{made['id']}").status_code == 204
    assert "storyteller removed the location Warehouse." in scene.messages()


def test_names_are_unique_in_the_troupe(scene: Scene) -> None:
    scene.added(name="Warehouse", rating=1)
    assert scene.add(name="Warehouse", rating=2).status_code == 409


def test_the_controller_must_be_in_the_troupe(scene: Scene) -> None:
    stranger = scene.troupe.stranger.client.post(
        "/characters", json={"splat": "vampire", "name": "Zed"}
    )
    assert stranger.status_code == 201
    refused = scene.controlled_by(stranger.json()["id"], "Den")
    assert refused.status_code == 422
    assert refused.json()["detail"] == "The controller must be a character in the troupe."


def test_a_deleted_controller_is_kept_by_name(scene: Scene) -> None:
    made = scene.added(name="Pawn shop", rating=1, control="character", controller_id=scene.agnes)
    left = scene.troupe.player.client.delete(f"/characters/{scene.agnes}/troupes/{scene.troupe.id}")
    assert left.status_code in (200, 204), left.text
    assert scene.troupe.player.client.delete(f"/characters/{scene.agnes}").status_code == 204
    read = scene.troupe.storyteller.client.get(f"/locations/{made['id']}").json()
    assert (read["control"], read["controller"]) == ("named", {"id": None, "name": "Agnes"})

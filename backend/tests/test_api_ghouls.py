"""Ghoul player characters through the API: building one bound to its domitor,
changing domitor, and the troupes that take them (MET: VTM pp. 296–297)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Character
from tests.api_helpers import Person, Troupe, new_character

# Every ghoul creation pick but the disciplines: a vampire's, without Generation.
BUILD = [
    ("attributes", "Physical", 7),
    ("attributes", "Social", 5),
    ("attributes", "Mental", 3),
    ("focus_physicals", "Strength", 1),
    ("focus_mentals", "Wits", 1),
    ("focus_socials", "Charisma", 1),
    ("skills", "Brawl", 4),
    ("skills", "Dodge", 3),
    ("skills", "Athletics", 3),
    ("skills", "Awareness", 2),
    ("skills", "Empathy", 2),
    ("skills", "Firearms", 2),
    ("skills", "Investigation", 1),
    ("skills", "Leadership", 1),
    ("skills", "Medicine", 1),
    ("skills", "Melee", 1),
    ("backgrounds", "Fame", 3),
    ("backgrounds", "Herd", 2),
    ("backgrounds", "Allies", 1),
]

pytestmark = pytest.mark.usefixtures("ghoul_rules")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def new_ghoul(person: Person, name: str = "Renfield", **body: Any) -> Any:
    return person.client.post("/characters", json={"splat": "ghoul", "name": name, **body})


def typed(name: str = "Lady Vasquez", clan: str = "Toreador", **more: Any) -> dict[str, Any]:
    return {"name": name, "clan": clan, **more}


def ghoul_of(person: Person, domitor: dict[str, Any], **body: Any) -> str:
    response = new_ghoul(person, domitor=domitor, **body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def pick(person: Person, character_id: str, category: str, name: str, rating: int = 1) -> Any:
    return person.client.put(
        f"/characters/{character_id}/creation/picks",
        json={"category": category, "name": name, "rating": rating},
    )


def place(person: Person, character_id: str, picks: list[tuple[str, str, int]]) -> None:
    for category, name, rating in picks:
        response = pick(person, character_id, category, name, rating)
        assert response.status_code == 200, (name, response.text)


def complete(person: Person, character_id: str) -> Any:
    return person.client.post(f"/characters/{character_id}/creation/complete")


def sheet(person: Person, character_id: str) -> dict[str, Any]:
    return person.client.get(f"/characters/{character_id}/sheet").json()


def ratings(person: Person, character_id: str, category: str) -> dict[str, int | None]:
    return {
        t["name"]: t["rating"]
        for t in sheet(person, character_id)["traits"]
        if t["category"] == category
    }


def quote(person: Person, character_id: str, category: str, name: str, rating: int) -> Any:
    return person.client.post(
        f"/characters/{character_id}/quote",
        json={"category": category, "name": name, "rating": rating},
    )


def domitor(person: Person, character_id: str) -> Any:
    return person.client.get(f"/characters/{character_id}/domitor").json()


def bind(person: Person, character_id: str, body: dict[str, Any]) -> Any:
    return person.client.put(f"/characters/{character_id}/domitor", json=body)


def allow(troupe: Troupe, splats: list[str], person: Person | None = None) -> Any:
    return (person or troupe.storyteller).client.patch(
        f"/troupes/{troupe.id}", json={"allowed_splats": splats}
    )


def vampire_domitor(troupe: Troupe, name: str = "Vasquez") -> str:
    """The player's Toreador, with Auspex 2, Celerity 1 and Presence 1."""
    vampire = new_character(troupe, troupe.player, name, finished=False, clan="Toreador")
    place(
        troupe.player,
        vampire,
        [
            ("disciplines", "Auspex", 2),
            ("disciplines", "Celerity", 1),
            ("disciplines", "Presence", 1),
        ],
    )
    return vampire


# --- building a ghoul ---------------------------------------------------------------------


def test_a_ghoul_with_a_domitor_not_in_horatio(troupe: Troupe) -> None:
    ghoul = new_ghoul(troupe.player, domitor=typed())

    assert ghoul.status_code == 201, ghoul.text
    assert ghoul.json()["splat"] == "ghoul"
    assert ghoul.json()["clan"] == "Toreador"
    assert domitor(troupe.player, ghoul.json()["id"]) == {
        "character_id": None,
        "name": "Lady Vasquez",
        "clan": "Toreador",
    }
    # No Humanity: a ghoul starts with the rest of a vampire's starting traits, and 30 XP.
    found = sheet(troupe.player, ghoul.json()["id"])
    assert {t["name"]: t["rating"] for t in found["traits"]} == {
        "Toreador": None,
        "Healthy": 3,
        "Injured": 3,
        "Incapacitated": 3,
        "Willpower": 6,
    }
    assert found["xp"]["balance"] == 30


def test_a_ghoul_needs_a_named_domitor_of_a_clan(troupe: Troupe) -> None:
    assert new_ghoul(troupe.player, domitor={"name": "  ", "clan": "Toreador"}).status_code == 422
    assert new_ghoul(troupe.player, domitor={"name": "Vasquez"}).status_code == 422
    assert new_ghoul(troupe.player, domitor=typed(clan="Elves")).status_code == 422
    assert (
        troupe.player.client.post(
            "/characters", json={"splat": "vampire", "name": "Agnes", "domitor": typed()}
        ).status_code
        == 422
    )


def test_a_ghoul_linked_to_a_vampire_takes_its_clan(troupe: Troupe) -> None:
    vampire = vampire_domitor(troupe)

    ghoul = ghoul_of(troupe.player, {"character_id": vampire})

    assert domitor(troupe.player, ghoul) == {
        "character_id": vampire,
        "name": "Vasquez",
        "clan": "Toreador",
    }
    assert ratings(troupe.player, ghoul, "clan") == {"Toreador": None}
    # Nor can the ghoul's player give it another clan.
    other = troupe.player.client.put(
        f"/characters/{ghoul}/traits", json={"category": "clan", "name": "Brujah", "rating": None}
    )
    assert other.status_code == 409
    assert "its domitor's" in other.json()["detail"]


def test_a_domitor_is_a_vampire_the_player_can_see(troupe: Troupe) -> None:
    theirs = vampire_domitor(troupe)
    strangers = new_character(troupe, troupe.stranger, "Mx Unknown", clan="Brujah")
    unclanned = new_character(troupe, troupe.player, "Nobody Yet")
    ghoul = ghoul_of(troupe.player, typed())

    assert new_ghoul(troupe.player, domitor={"character_id": strangers}).status_code == 404
    assert new_ghoul(troupe.player, domitor={"character_id": unclanned}).status_code == 409
    assert new_ghoul(troupe.player, domitor={"character_id": ghoul}).status_code == 422
    assert new_ghoul(troupe.player, domitor={"character_id": theirs}).status_code == 201


def test_five_discipline_dots_in_the_domitors_in_clan_disciplines(troupe: Troupe) -> None:
    ghoul = ghoul_of(troupe.player, typed())
    state = troupe.player.client.get(f"/characters/{ghoul}/creation").json()
    pool = next(p for p in state["pools"] if p["category"] == "disciplines")
    assert (pool["kind"], pool["allowed"], pool["restriction"]) == ("points", 5, "in_clan")

    assert pick(troupe.player, ghoul, "disciplines", "Auspex", 3).status_code == 200
    # Potence is not one of a Toreador's.
    assert pick(troupe.player, ghoul, "disciplines", "Potence", 1).status_code == 422
    # Two dots are left, not three.
    assert pick(troupe.player, ghoul, "disciplines", "Celerity", 3).status_code == 409
    assert pick(troupe.player, ghoul, "disciplines", "Celerity", 1).status_code == 200


def test_no_generation_for_a_ghoul(troupe: Troupe) -> None:
    ghoul = ghoul_of(troupe.player, typed())

    assert pick(troupe.player, ghoul, "backgrounds", "Generation", 1).status_code == 422
    catalogue = troupe.player.client.get("/rules/ghoul").json()
    assert not [t for t in catalogue["traits"] if t["name"] == "Generation"]
    assert not [c for c in catalogue["categories"] if c["key"] == "paths"]


def test_a_linked_domitors_powers_limit_the_ghouls(troupe: Troupe) -> None:
    ghoul = ghoul_of(troupe.player, {"character_id": vampire_domitor(troupe)})

    # Vasquez has Celerity 1, not 2.
    refused = pick(troupe.player, ghoul, "disciplines", "Celerity", 2)
    assert refused.status_code == 409
    assert "does not have Celerity that high" in refused.json()["detail"]
    assert pick(troupe.player, ghoul, "disciplines", "Auspex", 2).status_code == 200
    assert pick(troupe.player, ghoul, "disciplines", "Celerity", 1).status_code == 200


def test_dots_not_placed_at_creation_are_saved(troupe: Troupe) -> None:
    ghoul = ghoul_of(troupe.player, typed())
    place(troupe.player, ghoul, [*BUILD, ("disciplines", "Auspex", 2)])

    finished = complete(troupe.player, ghoul)

    assert finished.status_code == 200, finished.text
    assert ratings(troupe.player, ghoul, "disciplines") == {"Auspex": 2}


def test_finishing_needs_a_domitor(troupe: Troupe) -> None:
    created = new_ghoul(troupe.player)
    assert created.status_code == 201
    ghoul = created.json()["id"]
    assert domitor(troupe.player, ghoul) is None
    place(troupe.player, ghoul, BUILD)

    refused = complete(troupe.player, ghoul)

    assert refused.status_code == 409
    assert "domitor" in refused.json()["detail"]
    assert bind(troupe.player, ghoul, typed()).status_code == 200
    assert complete(troupe.player, ghoul).status_code == 200


def test_what_a_ghoul_pays_for_xp(troupe: Troupe) -> None:
    ghoul = ghoul_of(troupe.player, typed())
    place(troupe.player, ghoul, [*BUILD, ("disciplines", "Auspex", 2)])
    complete(troupe.player, ghoul)

    def cost(category: str, name: str, rating: int) -> int:
        response = quote(troupe.player, ghoul, category, name, rating)
        assert response.status_code == 200, response.text
        return response.json()["cost"]

    # An attribute 3 XP; a skill or background its new level; a merit its rating.
    assert cost("attributes", "Mental", 4) == 3
    assert cost("skills", "Brawl", 5) == 5
    assert cost("skills", "Computer", 2) == 1 + 2
    assert cost("backgrounds", "Resources", 1) == 1
    assert cost("merits", "Lucky", 2) == 2
    # Disciplines cannot be bought with XP.
    assert quote(troupe.player, ghoul, "disciplines", "Auspex", 3).status_code == 422
    bought = troupe.player.client.put(
        f"/characters/{ghoul}/traits", json={"category": "skills", "name": "Brawl", "rating": 5}
    )
    assert bought.status_code == 200, bought.text
    assert sheet(troupe.player, ghoul)["xp"]["balance"] == 30 - 5


def test_merits_and_flaws_for_vampires_are_refused(troupe: Troupe) -> None:
    ghoul = ghoul_of(troupe.player, typed())

    refusals = troupe.player.client.get(
        f"/characters/{ghoul}/refusals", params={"category": "merits"}
    ).json()
    assert "vampiric condition" in refusals["Calm Heart"]["message"]
    assert "Morality" in refusals["Path of Caine"]["message"]
    assert "clan merit" in refusals["Absent Sway"]["message"]
    for allowed in ("Bloodline: Ishtarri", "Uncommon Clan", "Lucky"):
        assert allowed not in refusals
    flaws = troupe.player.client.get(
        f"/characters/{ghoul}/refusals", params={"category": "flaws"}
    ).json()
    assert "vampiric condition" in flaws["Beast in the Mirror"]["message"]
    assert "Amnesia" not in flaws
    taken = pick(troupe.player, ghoul, "merits", "Calm Heart", 1)
    assert taken.status_code == 409


def test_staff_can_allow_one_by_exception(troupe: Troupe) -> None:
    ghoul = accepted_ghoul(troupe)

    given = troupe.storyteller.client.post(
        f"/characters/{ghoul}/give",
        json={
            "category": "merits",
            "name": "Calm Heart",
            "rating": 1,
            "despite": True,
            "free": True,
            "reason": "Raised among Brujah, she keeps her head.",
        },
    )

    assert given.status_code == 200, given.text
    assert given.json()["breaks"] == [
        "Calm Heart is about the vampiric condition, so a ghoul cannot take it. (p. 296)"
    ]
    assert ratings(troupe.player, ghoul, "merits") == {"Calm Heart": 1}


def test_a_troupe_that_takes_ghouls_can_switch_their_checks_off(troupe: Troupe) -> None:
    key = "ghoul/merits/vampire-only"
    off = {"strength": "off"}
    checks = troupe.lead.client.get(f"/troupes/{troupe.id}/checks").json()
    assert key not in {c["key"] for c in checks}
    assert troupe.lead.client.put(f"/troupes/{troupe.id}/checks/{key}", json=off).status_code == 404

    allow(troupe, ["vampire", "ghoul"])
    checks = troupe.lead.client.get(f"/troupes/{troupe.id}/checks").json()
    assert key in {c["key"] for c in checks}
    assert len(checks) == len({c["key"] for c in checks})
    switched = troupe.lead.client.put(f"/troupes/{troupe.id}/checks/{key}", json=off)
    assert switched.status_code == 200, switched.text

    ghoul = ghoul_of(troupe.player, typed(), building_troupe_id=troupe.id)
    assert pick(troupe.player, ghoul, "merits", "Calm Heart", 1).status_code == 200


# --- changing domitor (p. 297) --------------------------------------------------------------


def finished_ghoul(troupe: Troupe, **body: Any) -> str:
    ghoul = ghoul_of(troupe.player, typed(), **body)
    place(
        troupe.player, ghoul, [*BUILD, ("disciplines", "Auspex", 3), ("disciplines", "Presence", 2)]
    )
    assert complete(troupe.player, ghoul).status_code == 200
    return ghoul


def test_a_new_domitor_and_the_dots_kept(troupe: Troupe) -> None:
    ghoul = finished_ghoul(troupe)

    changed = bind(troupe.player, ghoul, typed("Marcus", "Brujah"))

    assert changed.status_code == 200, changed.text
    assert changed.json() == {"character_id": None, "name": "Marcus", "clan": "Brujah"}
    assert ratings(troupe.player, ghoul, "clan") == {"Brujah": None}
    assert ratings(troupe.player, ghoul, "disciplines") == {"Auspex": 3, "Presence": 2}
    messages = [e["message"] for e in troupe.player.client.get(f"/characters/{ghoul}/log").json()]
    assert "player made Marcus Renfield's domitor, of Brujah; discipline dots kept." in messages


def test_a_new_domitor_and_the_dots_moved(troupe: Troupe) -> None:
    ghoul = finished_ghoul(troupe)

    def move(*moved: tuple[str, int]) -> Any:
        return bind(
            troupe.player,
            ghoul,
            typed(
                "Marcus",
                "Brujah",
                disciplines="move",
                moved=[{"name": n, "rating": r} for n, r in moved],
            ),
        )

    # All five dots move, and only to the new domitor's in-clan disciplines.
    assert move(("Celerity", 3), ("Potence", 1)).status_code == 422
    assert move(("Celerity", 3), ("Auspex", 2)).status_code == 422
    assert move(("Celerity", 6)).status_code == 422
    assert ratings(troupe.player, ghoul, "clan") == {"Toreador": None}

    moved = move(("Celerity", 3), ("Potence", 2))

    assert moved.status_code == 200, moved.text
    assert ratings(troupe.player, ghoul, "disciplines") == {"Celerity": 3, "Potence": 2}
    assert sheet(troupe.player, ghoul)["xp"]["balance"] == 30


def test_dots_move_only_to_powers_a_linked_domitor_has(troupe: Troupe) -> None:
    ghoul = finished_ghoul(troupe)
    vampire = vampire_domitor(troupe)

    def move(*moved: tuple[str, int]) -> Any:
        return bind(
            troupe.player,
            ghoul,
            {
                "character_id": vampire,
                "disciplines": "move",
                "moved": [{"name": n, "rating": r} for n, r in moved],
            },
        )

    assert move(("Auspex", 3), ("Celerity", 2)).status_code == 422
    assert move(("Auspex", 2), ("Celerity", 1), ("Presence", 1), ("Potence", 1)).status_code == 422
    assert move(("Auspex", 2), ("Celerity", 1), ("Presence", 2)).status_code == 422


def accepted_ghoul(troupe: Troupe) -> str:
    """A finished ghoul whose home troupe, which takes ghouls, has accepted it."""
    allow(troupe, ["vampire", "ghoul"])
    ghoul = finished_ghoul(troupe, building_troupe_id=troupe.id)
    joined = troupe.player.client.post(
        f"/characters/{ghoul}/troupes", json={"troupe_id": troupe.id}
    )
    assert joined.status_code == 201, joined.text
    troupe.session.get_one(Character, uuid.UUID(ghoul)).home_troupe_id = uuid.UUID(troupe.id)
    troupe.session.flush()
    return ghoul


def test_once_accepted_the_home_troupes_staff_change_the_domitor(troupe: Troupe) -> None:
    ghoul = accepted_ghoul(troupe)

    assert bind(troupe.player, ghoul, typed("Marcus", "Brujah")).status_code == 403
    assert bind(troupe.stranger, ghoul, typed("Marcus", "Brujah")).status_code == 404
    changed = bind(troupe.assistant, ghoul, typed("Marcus", "Brujah"))
    assert changed.status_code == 200, changed.text
    # Accepted, the dots it kept are its staff's to answer for.
    assert not [
        p for p in sheet(troupe.player, ghoul)["problems"] if p["category"] == "disciplines"
    ]


def test_a_deleted_domitor_is_kept_by_name(troupe: Troupe) -> None:
    vampire = vampire_domitor(troupe)
    ghoul = ghoul_of(troupe.player, {"character_id": vampire})

    assert troupe.player.client.delete(f"/characters/{vampire}").status_code == 204

    assert domitor(troupe.player, ghoul) == {
        "character_id": None,
        "name": "Vasquez",
        "clan": "Toreador",
    }


# --- which splats a troupe takes --------------------------------------------------------------


def test_troupes_take_vampires_until_their_storytellers_say(troupe: Troupe) -> None:
    assert troupe.player.client.get(f"/troupes/{troupe.id}").json()["allowed_splats"] == ["vampire"]
    assert allow(troupe, ["ghoul"], troupe.assistant).status_code == 403
    assert allow(troupe, ["werewolf"]).status_code == 422
    assert allow(troupe, []).status_code == 422

    changed = allow(troupe, ["ghoul", "vampire", "ghoul"])

    assert changed.json()["allowed_splats"] == ["vampire", "ghoul"]
    messages = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert messages[0] == "storyteller set which splats may join: Vampire, Ghoul."


def test_a_ghoul_is_built_for_a_troupe_only_if_it_takes_ghouls(troupe: Troupe) -> None:
    refused = new_ghoul(troupe.player, domitor=typed(), building_troupe_id=troupe.id)
    assert refused.status_code == 409
    assert "does not take ghoul characters" in refused.json()["detail"]
    unbuilt = ghoul_of(troupe.player, typed())
    moved = troupe.player.client.put(
        f"/characters/{unbuilt}/building-troupe", json={"troupe_id": troupe.id}
    )
    assert moved.status_code == 409

    allow(troupe, ["vampire", "ghoul"])

    assert (
        new_ghoul(troupe.player, domitor=typed(), building_troupe_id=troupe.id).status_code == 201
    )
    moved = troupe.player.client.put(
        f"/characters/{unbuilt}/building-troupe", json={"troupe_id": troupe.id}
    )
    assert moved.status_code == 200


def test_a_troupe_refuses_a_pc_of_a_splat_it_does_not_take(troupe: Troupe) -> None:
    ghoul = ghoul_of(troupe.player, typed())

    refused = troupe.player.client.post(
        f"/characters/{ghoul}/troupes", json={"troupe_id": troupe.id}
    )
    assert refused.status_code == 409
    assert "does not take ghoul characters" in refused.json()["detail"]
    home = troupe.player.client.post(
        f"/characters/{ghoul}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert home.status_code == 409

    allow(troupe, ["ghoul"])

    assert (
        troupe.player.client.post(
            f"/characters/{ghoul}/troupes", json={"troupe_id": troupe.id}
        ).status_code
        == 201
    )
    vampire = new_character(troupe, troupe.player, "Agnes")
    assert (
        troupe.player.client.post(
            f"/characters/{vampire}/troupes", json={"troupe_id": troupe.id}
        ).status_code
        == 409
    )


def test_the_splats_there_are(troupe: Troupe) -> None:
    assert troupe.player.client.get("/rules").json() == [
        {"splat": "vampire", "label": "Vampire", "has_domitor": False},
        {"splat": "ghoul", "label": "Ghoul", "has_domitor": True},
    ]


def test_a_ghouls_pages_open(troupe: Troupe) -> None:
    """Its sheet, printed sheet, badge and Play View, as a vampire's do."""
    ghoul = finished_ghoul(troupe)

    for page in ("sheet", "print", "badge", "play", "play/reference", "play/modifiers"):
        response = troupe.player.client.get(f"/characters/{ghoul}/{page}")
        assert response.status_code == 200, (page, response.text)

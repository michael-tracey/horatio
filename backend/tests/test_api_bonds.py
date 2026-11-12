"""Blood bonds (#660): the troupe's setting, staff recording drinks, the level from the
drinks log, a full bond wiping lesser ones, entering and breaking bonds, and who
sees what (MET: VTM pp. 295-296)."""

import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.bonds import level_of
from horatio.models import BondEntry
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_downtimes import member_character


class Scene:
    """Agnes (the player's) is at home in a troupe that has bonds switched on; Bram
    (another player's) is a vampire there too, and Cora (a third player's) is a
    bystander. Ghislaine is the troupe's mortal NPC, Vidal its vampire NPC."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.other = sign_up(troupe.client_for, "other")
        self.third = sign_up(troupe.client_for, "third")
        self.agnes = member_character(troupe, troupe.player, "Agnes")
        self.bram = member_character(troupe, self.other, "Bram")
        self.cora = member_character(troupe, self.third, "Cora")
        self.vidal = self.npc("Vidal")
        self.ghislaine = self.npc("Ghislaine", npc_kind="mortal")
        assert self.set("staff").status_code == 200

    def npc(self, name: str, **body: Any) -> str:
        made = self.troupe.lead.client.post(
            f"/troupes/{self.troupe.id}/npcs", json={"name": name, **body}
        )
        assert made.status_code == 201, made.text
        return made.json()["id"]

    @property
    def path(self) -> str:
        return f"/troupes/{self.troupe.id}/bonds"

    def set(self, setting: str, by: Person | None = None) -> Any:
        return (by or self.troupe.storyteller).client.put(
            f"/troupes/{self.troupe.id}/blood-bonds", json={"setting": setting}
        )

    def drink(
        self,
        thrall: str | dict[str, Any],
        regnant: str | dict[str, Any],
        night: str = "2026-10-03",
        by: Person | None = None,
        **body: Any,
    ) -> Any:
        return (by or self.troupe.storyteller).client.post(
            f"{self.path}/drinks",
            json={
                "thrall": side(thrall),
                "regnant": side(regnant),
                "night": night,
                "source": "game",
                **body,
            },
        )

    def drunk(self, thrall: str | dict[str, Any], regnant: str | dict[str, Any], *nights: str):
        bond: dict[str, Any] = {}
        for night in nights:
            made = self.drink(thrall, regnant, night)
            assert made.status_code == 201, made.text
            bond = made.json()
        return bond

    def enter(self, thrall: str | dict[str, Any], regnant: str | dict[str, Any], **body: Any):
        return self.troupe.storyteller.client.post(
            self.path,
            json={
                "thrall": side(thrall),
                "regnant": side(regnant),
                "level": 2,
                "night": "2025-06-01",
                "reason": "From before Horatio",
                **body,
            },
        )

    def bonds(self, by: Person | None = None) -> list[dict[str, Any]]:
        listed = (by or self.troupe.storyteller).client.get(self.path)
        assert listed.status_code == 200, listed.text
        return listed.json()["bonds"]

    def card(self, character_id: str, by: Person) -> Any:
        return by.client.get(f"/characters/{character_id}/bonds")

    def messages(self) -> list[str]:
        log = self.troupe.lead.client.get(f"/troupes/{self.troupe.id}/log").json()
        return [e["message"] for e in log]

    def character_log(self, character_id: str, by: Person) -> list[str]:
        log = by.client.get(f"/characters/{character_id}/log")
        assert log.status_code == 200, log.text
        return [e["message"] for e in log.json()]


def side(who: str | dict[str, Any]) -> dict[str, Any]:
    """A character by id, or a name only."""
    return who if isinstance(who, dict) else {"character_id": who}


def named(name: str) -> dict[str, Any]:
    return {"name": name}


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def entry(night: str, kind: str = "drink", level: int | None = None) -> BondEntry:
    return BondEntry(kind=kind, night=date.fromisoformat(night), level=level)


# --- the level, from the drinks log ------------------------------------------------------


def test_each_separate_night_is_one_drink_up_to_a_full_bond() -> None:
    assert level_of([]) == 0
    assert level_of([entry("2026-10-01")]) == 1
    assert level_of([entry("2026-10-01"), entry("2026-10-08")]) == 2
    nights = ["2026-10-01", "2026-10-08", "2026-10-15", "2026-10-22"]
    assert level_of([entry(n) for n in nights]) == 3


def test_drinks_on_the_same_night_count_once() -> None:
    assert level_of([entry("2026-10-01"), entry("2026-10-01"), entry("2026-10-01")]) == 1
    assert level_of([entry("2026-10-08"), entry("2026-10-01"), entry("2026-10-08")]) == 2


def test_a_bond_entered_stands_at_its_level_from_its_night() -> None:
    entered = entry("2026-09-01", "entered", 2)
    assert level_of([entered]) == 2
    assert level_of([entered, entry("2026-10-01")]) == 3
    # What was drunk before, or that night, is in the level entered.
    assert level_of([entry("2026-08-01"), entry("2026-09-01"), entered]) == 2


# --- the setting ---------------------------------------------------------------------------


def test_new_troupes_have_bonds_off_and_storytellers_switch_them_on(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    troupe = Troupe(client_for, session)
    path = f"/troupes/{troupe.id}"
    assert troupe.lead.client.get(path).json()["blood_bonds"] == "off"
    for person in (troupe.assistant, troupe.narrator, troupe.player):
        refused = person.client.put(f"{path}/blood-bonds", json={"setting": "staff"})
        assert refused.status_code == 403, refused.text

    changed = troupe.storyteller.client.put(f"{path}/blood-bonds", json={"setting": "staff"})

    assert changed.status_code == 200, changed.text
    assert changed.json()["blood_bonds"] == "staff"
    log = [e["message"] for e in troupe.lead.client.get(f"{path}/log").json()]
    assert "storyteller set Blood bonds to Staff manages." in log
    # All four are defined; the player modes work as Staff manages until #661.
    for setting in ("players_report", "players_manage", "off"):
        assert (
            troupe.lead.client.put(f"{path}/blood-bonds", json={"setting": setting}).json()[
                "blood_bonds"
            ]
            == setting
        )
    bad = troupe.lead.client.put(f"{path}/blood-bonds", json={"setting": "on"})
    assert bad.status_code == 422


# --- staff record drinks ----------------------------------------------------------------


def test_staff_record_three_drinks_and_the_bond_is_full(scene: Scene) -> None:
    first = scene.drink(scene.agnes, scene.bram, "2026-10-03", note="At Elysium")
    assert first.status_code == 201, first.text
    assert first.json()["level"] == 1
    assert scene.drink(scene.agnes, scene.bram, "2026-10-03").json()["level"] == 1
    assert scene.drink(scene.agnes, scene.bram, "2026-10-10").json()["level"] == 2
    full = scene.drink(scene.agnes, scene.bram, "2026-10-17", source="downtime").json()

    assert full["level"] == 3
    assert full["status"] == "active"
    assert (full["thrall"]["name"], full["regnant"]["name"]) == ("Agnes", "Bram")
    assert [(e["night"], e["source"]) for e in full["entries"]] == [
        ("2026-10-03", "game"),
        ("2026-10-03", "game"),
        ("2026-10-10", "game"),
        ("2026-10-17", "downtime"),
    ]
    assert full["entries"][0]["note"] == "At Elysium"
    assert full["entries"][0]["recorded_by"] == "storyteller"
    assert full["last_drink"] == "2026-10-17"
    # One bond between them, however many drinks.
    assert [b["id"] for b in scene.bonds()] == [full["id"]]
    messages = scene.messages()
    assert (
        "storyteller recorded Agnes (player) drinking Bram's blood on 17 Oct 2026, in a downtime:"
        " a full bond." in messages
    )
    assert (
        "storyteller recorded Agnes (player) drinking Bram's blood on 3 Oct 2026, at a game:"
        " one drink (a drink that night already counted)." in messages
    )
    assert any(
        "drinking Bram's blood" in m for m in scene.character_log(scene.agnes, scene.troupe.player)
    )


def test_either_side_can_be_an_npc_or_a_name_only(scene: Scene) -> None:
    by_npc = scene.drink(scene.ghislaine, scene.vidal)
    assert by_npc.status_code == 201, by_npc.text
    assert by_npc.json()["thrall"] == {
        "character_id": scene.ghislaine,
        "name": "Ghislaine",
        "kind": "npc",
    }
    by_name = scene.drink(named("Lady Ophelia"), named("The Prince"))
    assert by_name.status_code == 201, by_name.text
    assert by_name.json()["regnant"] == {"character_id": None, "name": "The Prince", "kind": None}
    # A name matches the bond already there, whatever its capitals.
    again = scene.drink(named("lady ophelia"), named("the prince"), "2026-10-10")
    assert (again.json()["id"], again.json()["level"]) == (by_name.json()["id"], 2)
    assert any(
        m.startswith("storyteller recorded Lady Ophelia drinking The Prince's blood")
        for m in scene.messages()
    )


def test_who_may_be_on_each_side(scene: Scene) -> None:
    ghoul = scene.drink(scene.agnes, scene.ghislaine)
    assert ghoul.status_code == 422
    assert ghoul.json()["detail"] == "Ghislaine isn't a vampire: only a vampire's blood binds."
    elsewhere = sign_up(scene.troupe.client_for, "elsewhere")
    outside = elsewhere.client.post("/characters", json={"splat": "vampire", "name": "Outsider"})
    not_here = scene.drink(outside.json()["id"], scene.bram)
    assert not_here.status_code == 422
    assert not_here.json()["detail"] == "The thrall isn't a character in this troupe."
    neither = scene.drink({"name": " "}, scene.bram)
    assert neither.status_code == 422
    both = scene.drink({"character_id": scene.agnes, "name": "Agnes"}, scene.bram)
    assert both.status_code == 422
    themself = scene.drink(scene.bram, scene.bram)
    assert themself.status_code == 422
    assert scene.drink(scene.agnes, scene.bram, "2999-01-01").status_code == 422


def test_a_full_bond_wipes_away_lesser_bonds(scene: Scene) -> None:
    lesser = scene.drunk(scene.agnes, scene.vidal, "2026-09-01")
    named_lesser = scene.drunk(scene.agnes, named("Lady Ophelia"), "2026-09-02", "2026-09-09")
    other_thrall = scene.drunk(scene.cora, scene.vidal, "2026-09-01")

    full = scene.drunk(scene.agnes, scene.bram, "2026-10-03", "2026-10-10", "2026-10-17")

    by_id = {b["id"]: b for b in scene.bonds()}
    assert by_id[full["id"]]["status"] == "active"
    for wiped in (lesser, named_lesser):
        assert by_id[wiped["id"]]["status"] == "ended"
        assert by_id[wiped["id"]]["ended_reason"] == "Wiped away by the full bond to Bram."
    assert by_id[other_thrall["id"]]["status"] == "active"
    assert (
        "Agnes (player)'s lesser bond to Lady Ophelia was wiped away by the full bond to Bram."
        in scene.messages()
    )
    # A drink after an end starts a new bond.
    again = scene.drink(scene.agnes, scene.vidal, "2026-10-20")
    assert again.json()["id"] != lesser["id"]
    assert again.json()["level"] == 1


def test_staff_enter_a_bond_that_already_stands_with_a_reason(scene: Scene) -> None:
    entered = scene.enter(scene.agnes, scene.bram)
    assert entered.status_code == 201, entered.text
    assert entered.json()["level"] == 2
    assert entered.json()["entries"][0]["kind"] == "entered"
    assert entered.json()["entries"][0]["note"] == "From before Horatio"
    assert (
        "storyteller entered Agnes (player)'s bond to Bram, at two drinks from 1 Jun 2025:"
        " From before Horatio" in scene.messages()
    )
    # One more drink makes it full.
    assert scene.drink(scene.agnes, scene.bram).json()["level"] == 3

    twice = scene.enter(scene.agnes, scene.bram)
    assert twice.status_code == 409
    no_reason = scene.enter(scene.cora, scene.bram, reason=" ")
    assert no_reason.status_code == 422
    too_high = scene.enter(scene.cora, scene.bram, level=4)
    assert too_high.status_code == 422
    # Entered full, it wipes the lesser.
    lesser = scene.drunk(scene.cora, scene.vidal, "2026-09-01")
    assert scene.enter(scene.cora, scene.bram, level=3).status_code == 201
    assert {b["id"]: b["status"] for b in scene.bonds()}[lesser["id"]] == "ended"


def test_staff_add_a_drink_to_a_bond_and_break_it_with_a_reason(scene: Scene) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    path = f"{scene.path}/{bond['id']}"
    added = scene.troupe.assistant.client.post(
        f"{path}/drinks", json={"night": "2026-10-10", "source": "staff"}
    )
    assert added.status_code == 201, added.text
    assert added.json()["level"] == 2

    assert (
        scene.troupe.assistant.client.post(f"{path}/break", json={"reason": ""}).status_code == 422
    )
    broken = scene.troupe.assistant.client.post(
        f"{path}/break", json={"reason": "True love, at last"}
    )

    assert broken.status_code == 200, broken.text
    assert (broken.json()["status"], broken.json()["ended_reason"]) == (
        "broken",
        "True love, at last",
    )
    assert "assistant broke Agnes (player)'s bond to Bram: True love, at last" in scene.messages()
    assert (
        scene.troupe.assistant.client.post(f"{path}/break", json={"reason": "x"}).status_code == 409
    )
    late = scene.troupe.assistant.client.post(f"{path}/drinks", json={"night": "2026-10-17"})
    assert late.status_code == 409
    assert scene.card(scene.agnes, scene.troupe.player).json()["bound_to"] == []


# --- who sees what -----------------------------------------------------------------------


def test_only_running_staff_and_the_custodian_use_the_bonds_screen(scene: Scene) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, "2026-10-03")
    t = scene.troupe
    for person in (t.lead, t.storyteller, t.assistant, t.custodian):
        assert person.client.get(scene.path).status_code == 200
    calls: list[tuple[str, str, dict[str, Any]]] = [
        ("GET", scene.path, {}),
        (
            "POST",
            f"{scene.path}/drinks",
            {"thrall": side(scene.agnes), "regnant": side(scene.bram), "night": "2026-10-10"},
        ),
        (
            "POST",
            scene.path,
            {
                "thrall": side(scene.cora),
                "regnant": side(scene.bram),
                "level": 1,
                "night": "2026-10-10",
                "reason": "x",
            },
        ),
        ("POST", f"{scene.path}/{bond['id']}/drinks", {"night": "2026-10-10"}),
        ("POST", f"{scene.path}/{bond['id']}/break", {"reason": "x"}),
        ("PUT", f"{scene.path}/{bond['id']}/known", {"known": True}),
    ]
    for person in (t.narrator, t.player, scene.other, scene.third, t.stranger):
        for method, url, body in calls:
            response = person.client.request(method, url, json=body or None)
            assert response.status_code == 403, (person.email, method, url, response.text)
    assert scene.bonds()[0]["level"] == 1
    assert scene.bonds()[0]["known_to_regnant"] is False


def test_the_thrall_sees_their_bonds_and_the_regnant_only_once_known(scene: Scene) -> None:
    bond = scene.drunk(scene.agnes, scene.bram, "2026-10-03", "2026-10-10")
    t = scene.troupe

    thralls = scene.card(scene.agnes, t.player)
    assert thralls.status_code == 200, thralls.text
    assert [(b["name"], b["level"]) for b in thralls.json()["bound_to"]] == [("Bram", 2)]
    assert thralls.json()["bound_by"] == []
    assert thralls.json()["manage_troupe_id"] is None
    # Bram's player isn't told, nor sees Agnes's sheet.
    regnants = scene.card(scene.bram, scene.other).json()
    assert (regnants["bound_to"], regnants["bound_by"]) == ([], [])
    assert scene.card(scene.agnes, scene.other).status_code == 404
    assert not any("blood" in m for m in scene.character_log(scene.bram, scene.other))
    # Nobody else sees anything.
    for person in (scene.third, t.narrator, t.stranger):
        for character in (scene.agnes, scene.bram):
            assert scene.card(character, person).status_code == 404
    assert scene.card(scene.cora, scene.third).json()["bound_to"] == []
    # Staff see both sides, and may open the Bonds screen.
    staff = scene.card(scene.bram, t.assistant).json()
    assert [(b["name"], b["level"]) for b in staff["bound_by"]] == [("Agnes", 2)]
    assert staff["manage_troupe_id"] == t.id

    known = t.storyteller.client.put(f"{scene.path}/{bond['id']}/known", json={"known": True})
    assert known.status_code == 200, known.text
    assert known.json()["known_to_regnant"] is True
    regnants = scene.card(scene.bram, scene.other).json()
    assert [(b["name"], b["level"]) for b in regnants["bound_by"]] == [("Agnes", 2)]
    assert "storyteller marked Agnes (player)'s bond to Bram known to the regnant." in (
        scene.messages()
    )


def test_off_hides_everything_and_keeps_it_for_later(scene: Scene) -> None:
    scene.drunk(scene.agnes, scene.bram, "2026-10-03", "2026-10-10")
    t = scene.troupe
    before = scene.character_log(scene.agnes, t.player)
    assert any("Bram's blood" in m for m in before)

    assert scene.set("off").json()["blood_bonds"] == "off"

    assert t.storyteller.client.get(scene.path).status_code == 404
    assert scene.drink(scene.agnes, scene.bram, "2026-10-17").status_code == 404
    for character, person in ((scene.agnes, t.player), (scene.bram, t.storyteller)):
        card = scene.card(character, person).json()
        assert (card["bound_to"], card["bound_by"], card["manage_troupe_id"]) == ([], [], None)
    assert not any("blood" in m for m in scene.character_log(scene.agnes, t.player))
    assert not any("blood" in m for m in scene.messages())
    assert "storyteller set Blood bonds to Off." in scene.messages()

    scene.set("staff")

    assert [(b["thrall"]["name"], b["level"]) for b in scene.bonds()] == [("Agnes", 2)]
    assert scene.card(scene.agnes, t.player).json()["bound_to"][0]["level"] == 2
    assert scene.character_log(scene.agnes, t.player) == before


def test_deleting_a_character_keeps_its_bonds_by_name(scene: Scene, session: Session) -> None:
    npc = scene.npc("Old Vidal")
    bond = scene.drunk(scene.agnes, npc, "2026-10-03")
    deleted = scene.troupe.lead.client.delete(f"/characters/{npc}")
    assert deleted.status_code == 204, deleted.text
    session.expire_all()
    kept = next(b for b in scene.bonds() if b["id"] == bond["id"])
    assert kept["regnant"] == {"character_id": None, "name": "Old Vidal", "kind": None}
    assert uuid.UUID(kept["id"])

"""Targeted influence actions (MET: VtM core, pp. 510-512): Attacks, Defends, Boosts
and Blocks are logged with a target, and resolving them changes influence for as long
as the rules say."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import influence_effects
from tests.api_helpers import Person, Troupe
from tests.test_api_downtimes import member_character, my_downtime, new_cycle, open_cycle

REAL_NOW = datetime.now(UTC)
MONTH = influence_effects.month_start(REAL_NOW)
# Moments earlier this month, in order, whatever day the tests run.
EARLY, MIDDLE, LATE = (MONTH + (REAL_NOW - MONTH) * f for f in (0.25, 0.5, 0.75))


class Scene:
    """Agnes (Elite 4) and Bea (Elite 3), both at home in the troupe."""

    def __init__(self, troupe: Troupe, session: Session) -> None:
        self.troupe = troupe
        self.session = session
        self.agnes = member_character(troupe, troupe.player, "Agnes", elite=4)
        self.bea = member_character(troupe, troupe.player, "Bea", elite=3)

    @property
    def path(self) -> str:
        return f"/troupes/{self.troupe.id}/influence-log"

    def log(self, by: Person | None = None, **body: Any) -> Any:
        entry = {"type": "elite", "happened_at": MIDDLE.isoformat(), **body}
        return (by or self.troupe.storyteller).client.post(self.path, json=entry)

    def logged(self, **body: Any) -> dict[str, Any]:
        response = self.log(**body)
        assert response.status_code == 201, response.text
        return response.json()

    def attack(self, times: int, at: datetime = MIDDLE, **target: Any) -> dict[str, Any]:
        return self.logged(
            character_id=self.agnes,
            action_key="attack",
            times=times,
            happened_at=at.isoformat(),
            target={"character_id": self.bea, **target},
        )

    def defend(self, at: datetime, times: int = 1) -> dict[str, Any]:
        return self.logged(
            character_id=self.bea, action_key="defend", times=times, happened_at=at.isoformat()
        )

    def preview(self, entry: dict[str, Any], **query: Any) -> Any:
        return self.troupe.storyteller.client.get(
            f"/influence-entries/{entry['id']}/resolution", params=query
        )

    def resolve(self, entry: dict[str, Any], by: Person | None = None, **body: Any) -> Any:
        return (by or self.troupe.assistant).client.post(
            f"/influence-entries/{entry['id']}/resolution", json=body
        )

    def rating(self, character_id: str, influence_type: str = "elite") -> int:
        downtime = my_downtime(self.troupe.player, character_id).json()
        return next(s["rating"] for s in downtime["influence"] if s["type"] == influence_type)

    def allowance(self, character_id: str, kind: str = "influence_elite") -> int:
        return my_downtime(self.troupe.player, character_id).json()["allowance"][kind]

    def counter(self, character_id: str) -> int:
        view = self.troupe.player.client.get(f"/characters/{character_id}/play").json()
        return next(e["uses"] for e in view["expendables"] if e["name"] == "Influences: The Elite")

    def effects(self, character_id: str) -> list[dict[str, Any]]:
        found = self.troupe.player.client.get(f"/characters/{character_id}/influence-effects")
        assert found.status_code == 200, found.text
        return found.json()


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session), session)


# --- targets ----------------------------------------------------------------------------


def test_targeted_actions_need_a_target(scene: Scene) -> None:
    for action in ("attack", "boost"):
        refused = scene.log(character_id=scene.agnes, action_key=action)
        assert refused.status_code == 422, action
    blocked = scene.log(character_id=scene.agnes, action_key="block")
    assert blocked.status_code == 422
    assert "what the Block is on" in blocked.json()["detail"]
    # Still waiting on its details, it can go without.
    waiting = scene.log(character_id=scene.agnes, action_key="attack", needs_details=True)
    assert waiting.status_code == 201, waiting.text


def test_a_defend_protects_its_own_character_unless_told_otherwise(scene: Scene) -> None:
    defend = scene.defend(EARLY)

    assert defend["target"]["character_id"] == scene.bea
    assert defend["target"]["text"] == "Bea's Elite"


def test_a_boost_is_for_someone_else_and_of_the_same_type(scene: Scene) -> None:
    own = scene.log(
        character_id=scene.agnes, action_key="boost", target={"character_id": scene.agnes}
    )
    assert own.status_code == 422
    assert "someone else" in own.json()["detail"]
    across = scene.log(
        character_id=scene.agnes,
        action_key="boost",
        target={"character_id": scene.bea, "type": "underworld"},
    )
    assert across.status_code == 422


def test_an_attack_can_target_a_log_entry_without_knowing_whose_it_is(scene: Scene) -> None:
    beas = scene.logged(
        type="underworld",
        character_id=scene.bea,
        action_key="lockdown",
        purpose="To secure the docks",
        happened_at=EARLY.isoformat(),
    )
    attack = scene.logged(
        character_id=scene.agnes,
        action_key="attack",
        times=3,
        target={"entry": beas["short_id"].lower()},
    )

    assert attack["target"]["entry_short_id"] == "UW1"
    assert attack["target"]["character_id"] is None
    assert attack["target"]["type"] == "underworld"
    assert attack["target"]["text"] == "the Underworld behind UW1"
    unknown = scene.log(character_id=scene.agnes, action_key="attack", target={"entry": "UW99"})
    assert unknown.status_code == 422
    assert unknown.json()["detail"] == "No entry UW99 in this troupe's log."

    plan = scene.preview(attack).json()
    # Elite on Underworld costs 3 a level: the owner is found through the entry.
    assert (plan["name"], plan["per_level"], plan["levels"], plan["result"]) == ("Bea", 3, 1, 0)


# --- attacks ----------------------------------------------------------------------------


def test_resolving_an_attack_takes_defends_off_and_lowers_the_target(scene: Scene) -> None:
    open_cycle(scene.troupe, new_cycle(scene.troupe))
    assert (scene.rating(scene.bea), scene.allowance(scene.bea), scene.counter(scene.bea)) == (
        3,
        3,
        3,
    )
    defend = scene.defend(EARLY)
    scene.defend(LATE)  # after the attack: too late to count
    attack = scene.attack(4)

    plan = scene.preview(attack).json()
    assert (plan["per_level"], plan["levels"], plan["cost"], plan["spent"]) == (2, 2, 4, 4)
    assert (plan["defends"], plan["defended"], plan["result"]) == ([defend["short_id"]], 1, 1)
    resolved = scene.resolve(attack)

    assert resolved.status_code == 201, resolved.text
    effect = resolved.json()
    assert (effect["kind"], effect["levels"], effect["defended"], effect["text"]) == (
        "attack",
        1,
        1,
        "Elite 1 lower",
    )
    assert (effect["games"], effect["games_left"], effect["active"]) == (2, 2, True)
    assert datetime.fromisoformat(effect["ends_at"]) == influence_effects.a_month_on(MIDDLE)
    # The rating counts lower, the Play View starts lower, and the actions come off.
    assert scene.rating(scene.bea) == 2
    assert scene.counter(scene.bea) == 2
    assert scene.allowance(scene.bea) == 2
    downtime = my_downtime(scene.troupe.player, scene.bea).json()
    assert f"Lost to an attack ({attack['short_id']})" in [
        a["reason"] for a in downtime["adjustments"]
    ]
    # The sheet shows it, but not who made it.
    shown = scene.effects(scene.bea)
    assert [(e["text"], e["games_left"]) for e in shown] == [("Elite 1 lower", 2)]
    assert "name" not in shown[0]
    # Resolved once only.
    assert scene.resolve(attack).status_code == 409
    entry = scene.troupe.storyteller.client.get(scene.path).json()["entries"]
    assert next(e for e in entry if e["id"] == attack["id"])["effect"]["text"] == "Elite 1 lower"
    assert any("resolved E" in m for m in messages(scene))


def test_defends_count_against_every_attack_that_month(scene: Scene) -> None:
    scene.defend(EARLY, times=2)
    first = scene.attack(4)
    second = scene.attack(6, at=LATE)

    assert scene.resolve(first).json()["levels"] == 0
    assert scene.resolve(second).json()["levels"] == 1
    assert [e["text"] for e in scene.effects(scene.bea)] == ["Elite 1 lower"]


def test_a_defend_from_last_month_does_not_count(scene: Scene) -> None:
    scene.defend(MONTH - timedelta(days=3))
    attack = scene.attack(2)

    assert scene.preview(attack).json()["defended"] == 0


def test_staff_can_set_the_levels_and_see_what_they_cost(scene: Scene) -> None:
    attack = scene.attack(1)

    assert scene.preview(attack).json()["levels"] == 0
    plan = scene.preview(attack, levels=2).json()
    assert plan["cost"] == 4
    assert plan["notes"] == [f"2 levels cost 4 actions; {attack['short_id']} spent 1."]
    assert scene.resolve(attack).status_code == 422  # no levels: nothing to resolve
    assert scene.resolve(attack, levels=2).json()["levels"] == 2


def test_an_attack_lasts_two_games_or_a_month_whichever_is_later(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    attack = scene.attack(2, at=REAL_NOW - timedelta(minutes=5))
    scene.resolve(attack)
    assert scene.counter(scene.bea) == 2

    # Two games played, but not yet a month: it holds.
    for _ in range(2):
        play_a_game(scene.troupe.player, scene.bea)
    assert scene.counter(scene.bea) == 2

    # A month on, with the two games played, it is over: the levels come back.
    monkeypatch.setattr(influence_effects, "now", lambda: REAL_NOW + timedelta(days=40))
    assert scene.counter(scene.bea) == 3
    assert scene.effects(scene.bea) == []


def test_a_month_on_without_two_games_it_still_holds(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    attack = scene.attack(2, at=REAL_NOW - timedelta(minutes=5))
    scene.resolve(attack)
    play_a_game(scene.troupe.player, scene.bea)
    monkeypatch.setattr(influence_effects, "now", lambda: REAL_NOW + timedelta(days=40))

    assert [e["games_left"] for e in scene.effects(scene.bea)] == [1]
    assert scene.counter(scene.bea) == 2


def test_an_attack_on_someone_not_in_horatio_changes_nothing(scene: Scene) -> None:
    theirs = scene.logged(name="Old Tom", action_key="smooth_over", happened_at=EARLY.isoformat())
    attack = scene.logged(
        character_id=scene.agnes, action_key="attack", times=2, target={"entry": theirs["short_id"]}
    )

    refused = scene.resolve(attack)
    assert refused.status_code == 422
    assert "Old Tom" in refused.json()["detail"]


def test_taking_an_effect_back_gives_the_actions_back(scene: Scene) -> None:
    attack = scene.attack(2)
    effect = scene.resolve(attack).json()

    removed = scene.troupe.storyteller.client.delete(f"/influence-effects/{effect['id']}")

    assert removed.status_code == 200, removed.text
    assert removed.json() == {"note": None}
    assert scene.effects(scene.bea) == []
    open_cycle(scene.troupe, new_cycle(scene.troupe))
    assert scene.allowance(scene.bea) == 3
    assert scene.resolve(attack).status_code == 201  # it can be resolved again


# --- boosts -----------------------------------------------------------------------------


def test_a_boost_raises_the_level_and_the_allowance_for_the_month(scene: Scene) -> None:
    open_cycle(scene.troupe, new_cycle(scene.troupe))
    boost = scene.logged(
        character_id=scene.agnes, action_key="boost", times=3, target={"character_id": scene.bea}
    )

    plan = scene.preview(boost).json()
    assert (plan["rating"], plan["levels"], plan["cost"]) == (3, 1, 3)
    effect = scene.resolve(boost).json()

    assert effect["text"] == "Elite 1 higher"
    assert datetime.fromisoformat(effect["ends_at"]) == influence_effects.next_month(MIDDLE)
    assert (scene.rating(scene.bea), scene.counter(scene.bea), scene.allowance(scene.bea)) == (
        4,
        4,
        4,
    )


def test_boosting_costs_the_level_each_step_starts_from_up_to_ten(scene: Scene) -> None:
    assert influence_effects.boost_cost(5, 5) == 35  # 5 + 6 + 7 + 8 + 9 (p. 511)
    assert influence_effects.boost_levels(5, 34) == 4
    assert influence_effects.boost_levels(9, 100) == 1
    boost = scene.logged(
        character_id=scene.agnes, action_key="boost", times=3, target={"character_id": scene.bea}
    )
    refused = scene.preview(boost, levels=8)
    assert refused.status_code == 422
    assert "up to 10" in refused.json()["detail"]


def test_a_boost_ends_with_the_month(scene: Scene, monkeypatch: pytest.MonkeyPatch) -> None:
    boost = scene.logged(
        character_id=scene.agnes, action_key="boost", times=3, target={"character_id": scene.bea}
    )
    scene.resolve(boost)
    monkeypatch.setattr(
        influence_effects,
        "now",
        lambda: influence_effects.next_month(MIDDLE) + timedelta(minutes=1),
    )

    assert scene.effects(scene.bea) == []
    assert scene.counter(scene.bea) == 3


# --- blocks -----------------------------------------------------------------------------


def test_a_block_entry_and_a_location_action_record_blocks(scene: Scene) -> None:
    block = scene.logged(
        character_id=scene.agnes,
        action_key="block",
        times=2,
        target={"activity": "Acquiring firearms", "type": "underworld"},
    )
    assert block["target"]["text"] == "Acquiring firearms (Underworld)"
    assert block["resolves"] == "block"
    effect = scene.resolve(block).json()
    assert (effect["kind"], effect["type"], effect["levels"]) == ("block", "underworld", 2)

    lockdown = scene.logged(
        type="underworld",
        character_id=scene.bea,
        action_key="lockdown",
        purpose="the Weatherby Hotel",
        happened_at=(REAL_NOW - timedelta(hours=1)).isoformat(),
    )
    assert lockdown["resolves"] == "block"
    plan = scene.preview(lockdown).json()
    assert (plan["levels"], plan["activity"]) == (5, "Trouble at the site: the Weatherby Hotel")
    site = scene.resolve(lockdown).json()
    ends = datetime.fromisoformat(site["ends_at"]) - datetime.fromisoformat(site["starts_at"])
    assert ends == timedelta(hours=24)
    # A general action makes no effect.
    gossip = scene.logged(character_id=scene.agnes, action_key="gossip_and_insider_trading")
    assert gossip["resolves"] is None
    assert scene.resolve(gossip).status_code == 422


def test_the_response_editor_warns_of_a_block_an_answer_may_be_up_against(
    scene: Scene,
) -> None:
    recorded = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/influence-blocks",
        json={
            "type": "elite",
            "activity": "Buying the Herald's printing press",
            "strength": 2,
            "starts_at": EARLY.isoformat(),
        },
    )
    assert recorded.status_code == 201, recorded.text
    cycle = open_cycle(scene.troupe, new_cycle(scene.troupe))
    form = my_downtime(scene.troupe.player, scene.agnes).json()
    elite = next(q["id"] for q in form["questions"] if q["prompt"] == "Elite influence action")
    answers = [
        {
            "question_id": elite,
            "slot": 1,
            "body": "I lean on the Herald's printers.",
            "structured": {"action": "smooth_over"},
        },
        {
            "question_id": elite,
            "slot": 2,
            "body": "Tickets to the opera.",
            "structured": {"action": "a_friend_in_need"},
        },
    ]
    saved = scene.troupe.player.client.put(
        f"/characters/{scene.agnes}/downtime/answers", json={"answers": answers}
    )
    assert saved.status_code == 200, saved.text
    assert (
        scene.troupe.player.client.post(f"/characters/{scene.agnes}/downtime/submit").status_code
        == 200
    )

    items = scene.troupe.storyteller.client.get(f"/cycles/{cycle['id']}/responses").json()
    warned = {i["answer"]: [b["text"] for b in i["influence_blocks"]] for i in items}
    assert warned["I lean on the Herald's printers."] == [
        "Block 2 on Buying the Herald's printing press (Elite)"
    ]
    assert warned["Tickets to the opera."] == []
    listed = scene.troupe.assistant.client.get(f"/troupes/{scene.troupe.id}/influence-effects")
    assert [e["text"] for e in listed.json()] == [
        "Block 2 on Buying the Herald's printing press (Elite)"
    ]


def test_logging_a_targeted_answer_leaves_its_target_for_staff(scene: Scene) -> None:
    cycle = open_cycle(scene.troupe, new_cycle(scene.troupe))
    form = my_downtime(scene.troupe.player, scene.agnes).json()
    elite = next(q["id"] for q in form["questions"] if q["prompt"] == "Elite influence action")
    answers = [
        {
            "question_id": elite,
            "slot": 1,
            "body": "Attack Bea's Elite.",
            "structured": {"action": "attack"},
        }
    ]
    scene.troupe.player.client.put(
        f"/characters/{scene.agnes}/downtime/answers", json={"answers": answers}
    )
    scene.troupe.player.client.post(f"/characters/{scene.agnes}/downtime/submit")
    item = scene.troupe.storyteller.client.get(f"/cycles/{cycle['id']}/responses").json()[0]

    logged = scene.troupe.storyteller.client.post(
        f"/responses/{item['id']}/influence-entry", json={"purpose": "Attack Bea"}
    )

    assert logged.status_code == 200, logged.text
    assert logged.json()["entry"]["needs_details"] is True


# --- who may ----------------------------------------------------------------------------


def test_only_storytellers_and_assistants_resolve(scene: Scene) -> None:
    attack = scene.attack(2)
    for person in (scene.troupe.narrator, scene.troupe.player, scene.troupe.stranger):
        assert scene.resolve(attack, by=person).status_code in (403, 404)
        listed = person.client.get(f"/troupes/{scene.troupe.id}/influence-effects")
        assert listed.status_code in (403, 404)
    assert (
        scene.troupe.stranger.client.get(f"/characters/{scene.bea}/influence-effects").status_code
        == 404
    )
    assert scene.resolve(attack, by=scene.troupe.storyteller).status_code == 201


# --- helpers ----------------------------------------------------------------------------


def play_a_game(player: Person, character_id: str) -> None:
    """A game on the Play View: a tap, then a reset for the next one."""
    tap = {
        "id": str(uuid.uuid4()),
        "happened_at": datetime.now(UTC).isoformat(),
        "kind": "change",
        "tracker": "willpower",
        "amount": -1,
    }
    sent = player.client.post(f"/characters/{character_id}/play/taps", json={"taps": [tap]})
    assert sent.status_code == 200, sent.text
    reset = player.client.post(f"/characters/{character_id}/play/reset", json={})
    assert reset.status_code == 200, reset.text


def messages(scene: Scene) -> list[str]:
    log = scene.troupe.lead.client.get(f"/troupes/{scene.troupe.id}/log").json()
    return [e["message"] for e in log]

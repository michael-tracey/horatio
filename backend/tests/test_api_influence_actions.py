"""Influence answers name their action (MET: VtM core, pp. 510–512)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import influence
from horatio.models import Answer
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import ActionKindData
from horatio.rules.store import add_house_action_kind, read_troupe_rules
from tests.api_helpers import Troupe
from tests.test_api_downtimes import (
    member_character,
    my_downtime,
    new_cycle,
    open_cycle,
    question_id,
    save,
)

ELITE = "Elite influence action"
UNDERWORLD = "Underworld influence action"


class Scene:
    """Agnes, with Elite 2 and a News Media specialisation, in an open cycle."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.agnes = member_character(troupe, troupe.player, "Agnes", elite=2)
        taken = troupe.player.client.put(
            f"/characters/{self.agnes}/traits",
            json={
                "category": "influence_elite_specializations",
                "name": "News Media",
                "rating": 1,
            },
        )
        assert taken.status_code == 200, taken.text
        self.cycle = open_cycle(troupe, new_cycle(troupe))
        self.form = my_downtime(troupe.player, self.agnes).json()
        self.elite = question_id(self.form, ELITE)

    def answer(self, structured: dict[str, Any], body: str = "Lean on the mayor") -> Any:
        return save(
            self.troupe.player,
            self.agnes,
            [{"question_id": self.elite, "slot": 1, "body": body, "structured": structured}],
        )

    def submitted_responses(self) -> list[dict[str, Any]]:
        submitted = self.troupe.player.client.post(f"/characters/{self.agnes}/downtime/submit")
        assert submitted.status_code == 200, submitted.text
        return self.troupe.storyteller.client.get(f"/cycles/{self.cycle['id']}/responses").json()


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def test_each_type_has_ten_numbered_actions_and_the_conflict_actions() -> None:
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    for kind in ("influence_elite", "influence_underworld"):
        actions = [influence.action_from(a) for a in rules.action_kinds[kind].actions]
        assert [a.level for a in actions if a.general] == list(range(1, 11))
        assert [a.key for a in actions if a.conflict] == [
            "attack",
            "block",
            "boost",
            "defend",
            "discovery_block",
        ]
        assert all(a.level is None for a in actions if a.conflict)
    underworld = [
        influence.action_from(a) for a in rules.action_kinds["influence_underworld"].actions
    ]
    assert underworld[4].label == "5: Lockdown"
    assert underworld[10].label == "Attack"


def test_the_form_offers_each_types_actions_with_the_characters_reach(scene: Scene) -> None:
    standings = {s["type"]: s for s in scene.form["influence"]}

    elite = standings["elite"]
    assert (elite["action_kind"], elite["rating"], elite["held"]) == (
        "influence_elite",
        2,
        ["News Media"],
    )
    assert "News Media" in elite["options"] and "Finance" in elite["options"]
    assert elite["actions"][1] == {
        "key": "gossip_and_insider_trading",
        "name": "Gossip and Insider Trading",
        "label": "2: Gossip and Insider Trading",
        "level": 2,
        "conflict": False,
    }
    # No Underworld, so no Underworld question to ask about.
    assert set(standings) == {"elite"}


def test_an_answer_is_stored_as_the_actions_key(scene: Scene) -> None:
    saved = scene.answer({"specialization": "Finance", "action": "gossip_and_insider_trading"})

    assert saved.status_code == 200, saved.text
    assert saved.json()["answers"][0]["structured"] == {
        "specialization": "Finance",
        "action": "gossip_and_insider_trading",
    }


def test_a_general_action_needs_a_rating_at_least_its_level(scene: Scene) -> None:
    refused = scene.answer({"specialization": "Finance", "action": "bureaucratic_errors"})

    assert refused.status_code == 422
    assert refused.json()["detail"] == (
        "'Elite influence action': 3: Bureaucratic Errors needs Elite 3, "
        "or 2 with one of your Elite specialisations."
    )


def test_one_of_the_characters_specialisations_counts_one_higher(scene: Scene) -> None:
    saved = scene.answer({"specialization": "News Media", "action": "bureaucratic_errors"})

    assert saved.status_code == 200, saved.text
    # Not a level higher still.
    assert (
        scene.answer({"specialization": "News Media", "action": "smooth_over"}).status_code == 422
    )


def test_conflict_actions_have_no_level_to_reach(scene: Scene) -> None:
    for key in ("attack", "block", "boost", "defend", "discovery_block"):
        assert scene.answer({"action": key}).status_code == 200


def test_each_type_spends_from_its_own_list(scene: Scene) -> None:
    refused = scene.answer({"action": "word_on_the_street"})

    assert refused.status_code == 422
    assert refused.json()["detail"] == "'Elite influence action': choose one of the Elite actions."
    assert scene.answer({}).status_code == 422


def test_staff_see_the_actions_name_on_the_response(scene: Scene) -> None:
    scene.answer({"specialization": "News Media", "action": "gossip_and_insider_trading"})

    response = scene.submitted_responses()[0]

    assert response["influence"] == {
        "type": "elite",
        "specialization": "News Media",
        "action_key": "gossip_and_insider_trading",
        "action": "2: Gossip and Insider Trading",
        "level": 2,
        "conflict": False,
    }


def test_an_old_answer_with_only_a_level_reads_as_the_numbered_action(
    scene: Scene, session: Session
) -> None:
    assert scene.answer({"level": 1}).status_code == 200
    responses = scene.submitted_responses()
    assert responses[0]["influence"]["action"] == "1: A Friend in Need"
    # One saved before actions had names, beyond the character's reach today.
    answer = session.scalars(select(Answer).where(Answer.body == "Lean on the mayor")).one()
    answer.structured = {"level": 5}
    session.flush()

    responses = scene.troupe.storyteller.client.get(f"/cycles/{scene.cycle['id']}/responses")

    assert responses.json()[0]["influence"]["action"] == "5: No Party Crashers"
    # Saving it again unchanged is not refused: it is checked only when it changes.
    assert scene.answer({"level": 5}).status_code == 200


def test_other_answers_carry_no_influence(scene: Scene) -> None:
    general = question_id(scene.form, "Downtime action")
    save(
        scene.troupe.player,
        scene.agnes,
        [{"question_id": general, "slot": 1, "body": "Feed at the docks"}],
    )

    assert scene.submitted_responses()[0]["influence"] is None


def test_a_troupe_renames_and_adds_actions_as_a_house_rule(scene: Scene, session: Session) -> None:
    troupe_id = uuid.UUID(scene.troupe.id)
    generic = read_troupe_rules(session, "vampire", troupe_id).action_kinds()["influence_elite"]
    renamed = [
        {**a, "name": "Whispers"} if a["key"] == "gossip_and_insider_trading" else a
        for a in generic.actions
    ]
    add_house_action_kind(
        session,
        troupe_id,
        "vampire",
        ActionKindData(
            key="influence_elite",
            name=generic.name,
            fields=generic.fields,
            actions=(*renamed, {"key": "charity_gala", "name": "Charity Gala", "level": 2}),
        ),
    )

    form = my_downtime(scene.troupe.player, scene.agnes).json()
    elite = next(s for s in form["influence"] if s["type"] == "elite")

    assert elite["actions"][1]["label"] == "2: Whispers"
    assert elite["actions"][-1]["label"] == "2: Charity Gala"
    assert scene.answer({"action": "charity_gala"}).status_code == 200

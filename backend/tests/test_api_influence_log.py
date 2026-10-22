"""The troupe's influence log: logging downtime answers, entries by hand, the log
page's filters, edits, merges, and who may see it."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import influence_log
from horatio.models import AuditEvent, Submission
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_downtimes import (
    member_character,
    my_downtime,
    new_cycle,
    open_cycle,
    question_id,
    save,
)

AT = datetime(2026, 7, 11, 19, 30, tzinfo=UTC)


class Scene:
    """Agnes (Elite 2, News Media) has submitted two Elite answers in an open cycle."""

    def __init__(self, troupe: Troupe, session: Session) -> None:
        self.troupe = troupe
        self.session = session
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
        form = my_downtime(troupe.player, self.agnes).json()
        elite = question_id(form, "Elite influence action")
        fields = {"specialization": "News Media", "action": "gossip_and_insider_trading"}
        answers = [
            {"question_id": elite, "slot": n, "body": body, "structured": fields}
            for n, body in (
                (1, "I ask my friends at the Herald what is being said about the mayor."),
                (2, "And again, to hear more about the mayor."),
            )
        ]
        assert save(troupe.player, self.agnes, answers).status_code == 200
        submitted = troupe.player.client.post(f"/characters/{self.agnes}/downtime/submit")
        assert submitted.status_code == 200, submitted.text
        self.responses = troupe.storyteller.client.get(
            f"/cycles/{self.cycle['id']}/responses"
        ).json()

    @property
    def path(self) -> str:
        return f"/troupes/{self.troupe.id}/influence-log"

    def log(self, response: dict[str, Any], purpose: str, by: Person | None = None) -> Any:
        return (by or self.troupe.storyteller).client.post(
            f"/responses/{response['id']}/influence-entry", json={"purpose": purpose}
        )

    def entries(self, by: Person | None = None, **query: Any) -> dict[str, Any]:
        found = (by or self.troupe.assistant).client.get(self.path, params=query)
        assert found.status_code == 200, found.text
        return found.json()

    def add(self, by: Person | None = None, **body: Any) -> Any:
        entry = {
            "type": "underworld",
            "happened_at": AT.isoformat(),
            "name": "REDACTED",
            "specialization": "Transportation",
            "action_key": "lockdown",
            "purpose": "To secure the location of May's gather",
            **body,
        }
        return (by or self.troupe.storyteller).client.post(self.path, json=entry)

    def messages(self) -> list[str]:
        log = self.troupe.lead.client.get(f"/troupes/{self.troupe.id}/log").json()
        return [e["message"] for e in log]


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session), session)


# --- logging downtime answers -----------------------------------------------------------


def test_staff_log_an_influence_answer_with_its_purpose_trimmed(scene: Scene) -> None:
    logged = scene.log(scene.responses[0], "  To hear what is said about the mayor ")

    assert logged.status_code == 200, logged.text
    entry = logged.json()["entry"]
    assert logged.json()["repeat"] is False
    submitted_at = scene.session.scalars(select(Submission.submitted_at)).one()
    assert submitted_at is not None
    assert {k: entry[k] for k in ("short_id", "type", "name", "character_id", "source")} == {
        "short_id": "E1",
        "type": "elite",
        "name": "Agnes",
        "character_id": scene.agnes,
        "source": "downtime",
    }
    assert (entry["specialization"], entry["action"], entry["purpose"], entry["times"]) == (
        "News Media",
        "2: Gossip and Insider Trading",
        "To hear what is said about the mayor",
        1,
    )
    assert datetime.fromisoformat(entry["happened_at"]) == submitted_at
    assert (entry["cycle_id"], entry["cycle_name"]) == (scene.cycle["id"], "October 2026")
    assert entry["logged_by_name"] == "storyteller"
    assert entry["response_ids"] == [scene.responses[0]["id"]]
    response = scene.troupe.storyteller.client.get(f"/responses/{scene.responses[0]['id']}")
    assert response.json()["influence_entry"] == {"id": entry["id"], "short_id": "E1", "times": 1}
    assert scene.messages()[0] == (
        "storyteller logged E1 in the influence log: Agnes, 2: Gossip and Insider Trading."
    )


def test_a_second_answer_with_the_same_action_and_purpose_adds_to_the_times(
    scene: Scene,
) -> None:
    first = scene.log(scene.responses[0], "To hear about the mayor").json()["entry"]

    second = scene.log(scene.responses[1], "to hear  about the mayor")

    assert second.json()["repeat"] is True
    assert second.json()["entry"]["id"] == first["id"]
    assert second.json()["entry"]["times"] == 2
    assert scene.entries()["total"] == 1
    assert scene.log(scene.responses[1], "Again").status_code == 409


def test_a_different_purpose_is_a_new_entry(scene: Scene) -> None:
    scene.log(scene.responses[0], "To hear about the mayor")

    second = scene.log(scene.responses[1], "To hear about the chief of police")

    assert second.json()["entry"]["short_id"] == "E2"


def test_taking_an_answer_off_the_log(scene: Scene) -> None:
    for response in scene.responses:
        scene.log(response, "To hear about the mayor")
    storyteller = scene.troupe.storyteller.client

    assert (
        storyteller.delete(f"/responses/{scene.responses[1]['id']}/influence-entry").status_code
        == 204
    )
    assert scene.entries()["entries"][0]["times"] == 1
    assert (
        storyteller.delete(f"/responses/{scene.responses[0]['id']}/influence-entry").status_code
        == 204
    )
    assert scene.entries()["total"] == 0
    # It can be logged again.
    assert scene.log(scene.responses[0], "To hear about the mayor").status_code == 200


def test_only_influence_answers_are_logged(scene: Scene) -> None:
    general = question_id(my_downtime(scene.troupe.player, scene.agnes).json(), "Downtime action")
    answers = my_downtime(scene.troupe.player, scene.agnes).json()["answers"]
    save(
        scene.troupe.player,
        scene.agnes,
        [*answers, {"question_id": general, "slot": 1, "body": "Feed at the docks"}],
    )
    responses = scene.troupe.storyteller.client.get(f"/cycles/{scene.cycle['id']}/responses").json()
    feeding = next(r for r in responses if r["answer"] == "Feed at the docks")

    assert scene.log(feeding, "Feed").status_code == 422


# --- who sees it ------------------------------------------------------------------------


def test_storytellers_and_assistants_keep_the_log_and_no_one_else_sees_it(scene: Scene) -> None:
    troupe = scene.troupe
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert person.client.get(scene.path).status_code == 403
        assert person.client.get(f"{scene.path}/choices").status_code == 403
        assert scene.add(by=person).status_code == 403
    # A narrator answering an influence action cannot log it.
    assert scene.log(scene.responses[0], "x", by=troupe.narrator).status_code == 403
    for person in (troupe.lead, troupe.storyteller, troupe.assistant):
        assert scene.add(by=person).status_code == 201


def test_logging_is_kept_out_of_the_characters_own_log(scene: Scene) -> None:
    scene.log(scene.responses[0], "To hear about the mayor")

    own = scene.troupe.player.client.get(f"/characters/{scene.agnes}/log").json()

    assert not [e for e in own if e["action"].startswith("influence.")]


# --- by hand ----------------------------------------------------------------------------


def test_an_entry_by_hand_can_name_someone_not_in_horatio(scene: Scene) -> None:
    added = scene.add(times=3, blocks=1)

    assert added.status_code == 201, added.text
    entry = added.json()
    assert (entry["short_id"], entry["name"], entry["character_id"], entry["source"]) == (
        "UW1",
        "REDACTED",
        None,
        "hand",
    )
    assert (entry["action"], entry["times"], entry["blocks"]) == ("5: Lockdown", 3, 1)
    assert datetime.fromisoformat(entry["happened_at"]) == AT
    assert scene.messages()[0] == (
        "storyteller logged UW1 in the influence log: REDACTED, 5: Lockdown."
    )


def test_an_entry_by_hand_for_a_character_or_an_npc(scene: Scene) -> None:
    npc = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/npcs", json={"name": "Prince Vasquez"}
    ).json()

    pc = scene.add(character_id=scene.agnes, name="ignored")
    npc_entry = scene.add(character_id=npc["id"], type="elite", action_key="smooth_over")

    assert (pc.json()["name"], pc.json()["character_id"]) == ("Agnes", scene.agnes)
    assert (npc_entry.json()["short_id"], npc_entry.json()["name"]) == ("E1", "Prince Vasquez")
    # Deleting the NPC keeps its entries, with its name.
    assert scene.troupe.storyteller.client.delete(f"/characters/{npc['id']}").status_code == 204
    kept = scene.entries(type="elite")["entries"][0]
    assert (kept["character_id"], kept["name"]) == (None, "Prince Vasquez")


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"action_key": "gossip_and_insider_trading"}, "Choose one of the Underworld actions."),
        ({"action_key": None}, "Choose the action, or mark the entry as needing details."),
        ({"name": " "}, "Choose a character, or name someone not in Horatio."),
        ({"character_id": str(uuid.uuid4())}, "That character is not in this troupe."),
        ({"cycle_id": str(uuid.uuid4())}, "No such cycle here."),
    ],
)
def test_entries_by_hand_are_checked(scene: Scene, body: dict[str, Any], detail: str) -> None:
    refused = scene.add(**body)

    assert refused.status_code == 422
    assert refused.json()["detail"] == detail


def test_an_entry_needing_details_waits_for_its_action(scene: Scene) -> None:
    added = scene.add(action_key=None, needs_details=True, purpose="")

    assert added.status_code == 201, added.text
    assert (added.json()["action"], added.json()["needs_details"]) == ("No action yet", True)
    assert scene.entries(needs_details=True)["total"] == 1


def test_a_character_not_in_the_troupe_cannot_be_logged(scene: Scene) -> None:
    elsewhere = new_character(scene.troupe, scene.troupe.stranger, "Bianca")

    assert scene.add(character_id=elsewhere).status_code == 422


def test_an_entry_outlives_its_character_leaving_the_troupe(scene: Scene) -> None:
    entry = scene.log(scene.responses[0], "To hear about the mayor").json()["entry"]
    assert entry["left_troupe"] is False

    left = scene.troupe.player.client.delete(f"/characters/{scene.agnes}/troupes/{scene.troupe.id}")

    assert left.status_code == 204, left.text
    kept = scene.entries(character_id=scene.agnes)["entries"]
    assert [(e["short_id"], e["name"], e["left_troupe"]) for e in kept] == [("E1", "Agnes", True)]
    choices = scene.troupe.assistant.client.get(f"{scene.path}/choices").json()
    assert [(c["name"], c["in_troupe"]) for c in choices["characters"]] == [("Agnes", False)]
    # It can still be edited, though Agnes could not be newly logged here now.
    edited = scene.troupe.assistant.client.put(
        f"/influence-entries/{entry['id']}",
        json={
            "type": "elite",
            "happened_at": entry["happened_at"],
            "character_id": scene.agnes,
            "action_key": "gossip_and_insider_trading",
            "purpose": "To hear about the mayor's ledger",
        },
    )
    assert edited.status_code == 200, edited.text
    assert scene.add(character_id=scene.agnes).status_code == 422


def test_an_entry_keeps_the_name_it_was_logged_under(scene: Scene) -> None:
    from horatio.models import Character

    scene.log(scene.responses[0], "To hear about the mayor")
    scene.session.get_one(Character, uuid.UUID(scene.agnes)).name = "Agnes Duval"
    scene.session.flush()

    entry = scene.entries()["entries"][0]

    assert (entry["name"], entry["current_name"]) == ("Agnes", "Agnes Duval")


# --- the log page -----------------------------------------------------------------------


def test_the_log_filters_by_type_specialisation_character_action_and_date(
    scene: Scene,
) -> None:
    scene.log(scene.responses[0], "To hear about the mayor")
    scene.add()
    scene.add(happened_at=(AT - timedelta(days=40)).isoformat(), action_key="free_travel")
    scene.add(type="elite", character_id=scene.agnes, action_key="smooth_over")

    def ids(**query: Any) -> list[str]:
        return [e["short_id"] for e in scene.entries(**query)["entries"]]

    assert ids(type="underworld") == ["UW1", "UW2"]
    assert ids(specialization="News Media") == ["E1"]
    assert ids(character_id=scene.agnes) == ["E1", "E2"]
    assert ids(name="redacted") == ["UW1", "UW2"]
    assert ids(action="lockdown") == ["UW1"]
    # To the minute: `since` counts from it, `until` up to it.
    assert ids(since=AT.isoformat(), type="underworld") == ["UW1"]
    assert ids(since=(AT + timedelta(minutes=1)).isoformat(), type="underworld") == []
    assert ids(until=AT.isoformat(), type="underworld") == ["UW2"]
    page = scene.entries(limit=2, offset=1)
    assert (page["total"], len(page["entries"])) == (4, 2)


def test_the_log_is_newest_first(scene: Scene) -> None:
    scene.add(happened_at=(AT - timedelta(days=1)).isoformat())
    scene.add()

    assert [e["short_id"] for e in scene.entries()["entries"]] == ["UW2", "UW1"]


def test_staff_edit_an_entry(scene: Scene) -> None:
    entry = scene.add().json()
    changed = {
        "type": "underworld",
        "happened_at": AT.isoformat(),
        "name": "REDACTED",
        "specialization": "Transportation",
        "action_key": "lockdown",
        "purpose": "To lock down the arboretum",
        "times": 2,
        "blocks": 1,
    }

    edited = scene.troupe.assistant.client.put(f"/influence-entries/{entry['id']}", json=changed)

    assert edited.status_code == 200, edited.text
    assert (edited.json()["purpose"], edited.json()["times"], edited.json()["blocks"]) == (
        "To lock down the arboretum",
        2,
        1,
    )
    assert scene.messages()[0] == (
        "assistant changed UW1 in the influence log: purpose, times, blocks."
    )
    # A change of type gives it the other type's next number.
    retyped = scene.troupe.assistant.client.put(
        f"/influence-entries/{entry['id']}",
        json={**changed, "type": "elite", "action_key": "smooth_over"},
    )
    assert retyped.json()["short_id"] == "E1"
    assert (
        scene.troupe.narrator.client.put(
            f"/influence-entries/{entry['id']}", json=changed
        ).status_code
        == 403
    )


def test_staff_delete_an_entry(scene: Scene) -> None:
    entry = scene.log(scene.responses[0], "To hear about the mayor").json()["entry"]

    deleted = scene.troupe.assistant.client.delete(f"/influence-entries/{entry['id']}")

    assert deleted.status_code == 204
    assert scene.entries()["total"] == 0
    assert scene.messages()[0] == (
        "assistant deleted E1 from the influence log: Agnes, 2: Gossip and Insider Trading."
    )
    response = scene.troupe.storyteller.client.get(f"/responses/{scene.responses[0]['id']}")
    assert response.json()["influence_entry"] is None


def test_repeats_merge_into_one_entry(scene: Scene) -> None:
    first = scene.log(scene.responses[0], "To hear about the mayor").json()["entry"]
    second = scene.log(scene.responses[1], "To hear what the mayor is up to").json()["entry"]
    by_hand = scene.add(
        type="elite", character_id=scene.agnes, action_key="gossip_and_insider_trading", blocks=2
    ).json()

    merged = scene.troupe.storyteller.client.post(
        f"/influence-entries/{first['id']}/merge",
        json={"entry_ids": [second["id"], by_hand["id"]]},
    )

    assert merged.status_code == 200, merged.text
    assert (merged.json()["short_id"], merged.json()["times"], merged.json()["blocks"]) == (
        "E1",
        3,
        2,
    )
    assert merged.json()["response_ids"] == [r["id"] for r in scene.responses]
    assert scene.entries()["total"] == 1
    assert scene.messages()[0] == (
        "storyteller merged E2, E3 into E1 in the influence log (3 times)."
    )


def test_only_repeats_merge(scene: Scene) -> None:
    first = scene.log(scene.responses[0], "To hear about the mayor").json()["entry"]
    other = scene.add(type="elite", action_key="gossip_and_insider_trading").json()

    refused = scene.troupe.storyteller.client.post(
        f"/influence-entries/{first['id']}/merge", json={"entry_ids": [other["id"]]}
    )

    assert refused.status_code == 422
    assert refused.json()["detail"] == "Only repeats merge: the same type, character and action."


def test_choices_for_an_entry(scene: Scene) -> None:
    scene.add()

    choices = scene.troupe.assistant.client.get(f"{scene.path}/choices").json()

    elite = next(t for t in choices["types"] if t["type"] == "elite")
    assert elite["name"] == "Elite"
    assert elite["actions"][4]["label"] == "5: No Party Crashers"
    assert "News Media" in elite["specializations"]
    assert [c["name"] for c in choices["characters"]] == ["Agnes"]
    assert choices["names"] == ["REDACTED"]
    assert [c["name"] for c in choices["cycles"]] == ["October 2026"]


# --- for the issues that build on it ----------------------------------------------------


def test_short_ids_read_back(scene: Scene) -> None:
    entry = scene.add().json()

    assert influence_log.parse_short_id("uw 7") == ("underworld", 7)
    assert influence_log.parse_short_id("E334") == ("elite", 334)
    assert influence_log.parse_short_id("X1") is None
    found = influence_log.by_short_id(scene.session, uuid.UUID(scene.troupe.id), "UW1")
    assert found is not None and str(found.id) == entry["id"]


def test_an_import_keeps_its_reference_and_number(scene: Scene) -> None:
    from horatio.models import Troupe as TroupeRow

    troupe = scene.session.get_one(TroupeRow, uuid.UUID(scene.troupe.id))
    details = influence_log.Details(
        influence_type="elite",
        happened_at=AT,
        character_id=None,
        name="Dark Horse Hacker",
        specialization="News Media",
        action_key="smooth_over",
        purpose="To smooth over the confession",
    )

    entry = influence_log.add_entry(
        scene.session, None, troupe, details, source="import", reference="E334", number=334
    )

    assert (influence_log.short_id(entry), entry.reference, entry.logged_by) == (
        "E334",
        "E334",
        None,
    )
    assert scene.add(type="elite", action_key="smooth_over").json()["short_id"] == "E335"
    with pytest.raises(Exception, match="already has an entry for E334"):
        influence_log.add_entry(
            scene.session, None, troupe, details, source="import", reference="E334"
        )
    event = scene.session.scalars(
        select(AuditEvent).where(AuditEvent.action == "influence.logged")
    ).first()
    assert event is not None and event.data["source"] == "import"

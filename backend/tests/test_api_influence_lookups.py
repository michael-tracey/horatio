"""Gossip and Insider Trading and Word on the Street answered from the influence log
(#130), and discovery blocks that hide entries from them (#131)."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_downtimes import member_character, my_downtime, new_cycle, open_cycle, save

ELITE = "Elite influence action"
UNDERWORLD = "Underworld influence action"
WORD = {"specialization": "Finance", "action": "word_on_the_street"}


def buy(player: Person, character_id: str, category: str, name: str, rating: int) -> None:
    bought = player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating},
    )
    assert bought.status_code == 200, bought.text


class Scene:
    """Agnes, with Underworld 3 in Criminal Organizations, Finance and Infrastructure
    and Elite 1, and Bram, another of the troupe's characters, in an open cycle."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.agnes = new_character(troupe, troupe.player, "Agnes")
        buy(troupe.player, self.agnes, "backgrounds", "Influences: The Underworld", 3)
        buy(troupe.player, self.agnes, "backgrounds", "Influences: The Elite", 1)
        requested = troupe.player.client.post(
            f"/characters/{self.agnes}/home-troupe", json={"troupe_id": troupe.id}
        )
        assert requested.status_code == 201, requested.text
        approved = troupe.lead.client.post(f"/approvals/{requested.json()['id']}/approve", json={})
        assert approved.status_code == 200, approved.text
        for name in ("Criminal Organizations", "Finance", "Infrastructure"):
            buy(troupe.player, self.agnes, "influence_underworld_specializations", name, 1)
        self.bram = member_character(troupe, troupe.player, "Bram")
        self.cycle = open_cycle(troupe, new_cycle(troupe))
        self.closes_at = datetime.fromisoformat(self.cycle["closes_at"])
        self.form = my_downtime(troupe.player, self.agnes).json()

    def question(self, prompt: str) -> str:
        return next(q["id"] for q in self.form["questions"] if q["prompt"] == prompt)

    def submit(self, *answers: tuple[str, dict[str, Any], str]) -> list[dict[str, Any]]:
        """Agnes's answers, as (question, fields, body); her responses, in form order."""
        slots: dict[str, int] = {}
        body = []
        for prompt, fields, text in answers:
            question = self.question(prompt)
            slots[question] = slots.get(question, 0) + 1
            body.append(
                {
                    "question_id": question,
                    "slot": slots[question],
                    "body": text,
                    "structured": fields,
                }
            )
        saved = save(self.troupe.player, self.agnes, body)
        assert saved.status_code == 200, saved.text
        submitted = self.troupe.player.client.post(f"/characters/{self.agnes}/downtime/submit")
        assert submitted.status_code == 200, submitted.text
        everything = self.troupe.storyteller.client.get(
            f"/cycles/{self.cycle['id']}/responses"
        ).json()
        return [r for r in everything if r["character_id"] == self.agnes]

    def words(self, count: int) -> list[dict[str, Any]]:
        return self.submit(*[(UNDERWORLD, WORD, f"Ask around, {n + 1}") for n in range(count)])

    def add(self, before_close: timedelta, by: Person | None = None, **body: Any) -> str:
        entry = {
            "type": "underworld",
            "happened_at": (self.closes_at - before_close).isoformat(),
            "name": "REDACTED",
            "specialization": "Finance",
            "action_key": "illegal_favors",
            "purpose": "To get a ledger out of the bank",
            **body,
        }
        added = (by or self.troupe.storyteller).client.post(
            f"/troupes/{self.troupe.id}/influence-log", json=entry
        )
        assert added.status_code == 201, added.text
        return added.json()["short_id"]

    def look_up(self, response: dict[str, Any], by: Person | None = None) -> Any:
        return (by or self.troupe.assistant).client.get(f"/responses/{response['id']}/lookup")

    def found(self, response: dict[str, Any]) -> list[str]:
        looked = self.look_up(response)
        assert looked.status_code == 200, looked.text
        return [f["short_id"] for f in looked.json()["found"]]

    def entry(self, short_id: str) -> dict[str, Any]:
        log = self.troupe.assistant.client.get(f"/troupes/{self.troupe.id}/influence-log").json()
        return next(e for e in log["entries"] if e["short_id"] == short_id)

    def messages(self) -> list[str]:
        log = self.troupe.lead.client.get(f"/troupes/{self.troupe.id}/log").json()
        return [e["message"] for e in log]


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


# --- lookups ----------------------------------------------------------------------------


def test_two_word_on_the_street_actions_make_one_result_of_strength_two(scene: Scene) -> None:
    day = timedelta(days=1)
    docks = scene.add(
        10 * day,
        character_id=scene.bram,
        specialization="Criminal Organizations",
        action_key="lockdown",
        purpose="To lock down the docks",
        times=3,
    )
    once_blocked = scene.add(30 * day, blocks=1, purpose="To hide a payment")
    twice_blocked = scene.add(20 * day, specialization="Infrastructure", blocks=2)
    scene.add(5 * day, character_id=scene.agnes, action_key="free_travel")  # her own
    scene.add(
        5 * day, action_key="attack", target={"character_id": scene.bram}
    )  # a conflict action
    scene.add(5 * day, specialization="Arts")  # not one of hers
    scene.add(5 * day, type="elite", specialization="Finance", action_key="smooth_over")
    responses = scene.words(2)

    looked = scene.look_up(responses[0])

    assert looked.status_code == 200, looked.text
    result = looked.json()
    assert (result["type"], result["action_name"], result["strength"]) == (
        "underworld",
        "Word on the Street",
        2,
    )
    assert sorted(result["specializations"]) == [
        "Criminal Organizations",
        "Finance",
        "Infrastructure",
    ]
    # Oldest first: unblocked and once-blocked, in any of her specialisations.
    assert result["found"] == [
        {
            "short_id": once_blocked,
            "happened_at": result["found"][0]["happened_at"],
            "specialization": "Finance",
            "action": "3: Illegal Favors",
            "purpose": "To hide a payment",
            "times": 1,
        },
        {
            "short_id": docks,
            "happened_at": result["found"][1]["happened_at"],
            "specialization": "Criminal Organizations",
            "action": "5: Lockdown",
            "purpose": "To lock down the docks",
            "times": 3,
        },
    ]
    assert twice_blocked not in [f["short_id"] for f in result["found"]]
    # Never who took them.
    assert "Bram" not in looked.text and "REDACTED" not in looked.text
    # Both answers, in the form's order: the result goes on the last.
    assert [a["response_id"] for a in result["answers"]] == [r["id"] for r in responses]
    assert scene.found(responses[1]) == [once_blocked, docks]


def test_a_single_action_does_not_get_past_one_block(scene: Scene) -> None:
    open_one = scene.add(timedelta(days=3))
    scene.add(timedelta(days=2), blocks=1)

    (response,) = scene.words(1)

    assert scene.look_up(response).json()["strength"] == 1
    assert scene.found(response) == [open_one]


def test_the_window_ends_at_the_cycles_close_and_counts_back_the_lookback(
    scene: Scene,
) -> None:
    minute = timedelta(minutes=1)
    days = timedelta(days=90)
    just_outside = scene.add(days + minute)
    just_inside = scene.add(days - minute)
    at_close = scene.add(timedelta(0))
    after_close = scene.add(-minute)
    (response,) = scene.words(1)

    looked = scene.look_up(response).json()

    assert [f["short_id"] for f in looked["found"]] == [just_inside, at_close]
    assert datetime.fromisoformat(looked["window"]["until"]) == scene.closes_at
    assert datetime.fromisoformat(looked["window"]["since"]) == scene.closes_at - days
    assert looked["window"]["days"] == 90
    assert after_close not in [f["short_id"] for f in looked["found"]]

    # A longer lookback reaches further.
    changed = scene.troupe.storyteller.client.put(
        f"/troupes/{scene.troupe.id}/influence-lookback", json={"days": 91}
    )
    assert changed.status_code == 200, changed.text
    assert scene.found(response) == [just_outside, just_inside, at_close]


def test_entries_of_characters_who_have_left_are_still_found(scene: Scene) -> None:
    bram_s = scene.add(timedelta(days=4), character_id=scene.bram)
    left = scene.troupe.player.client.delete(f"/characters/{scene.bram}/troupes/{scene.troupe.id}")
    assert left.status_code == 204, left.text

    (response,) = scene.words(1)

    assert scene.found(response) == [bram_s]


def test_with_no_specialisations_of_the_type_nothing_is_found(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    troupe = Troupe(client_for, session)
    agnes = member_character(troupe, troupe.player, "Agnes", elite=2)
    open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()
    elite = next(q["id"] for q in form["questions"] if q["prompt"] == ELITE)
    gossip = {"action": "gossip_and_insider_trading"}
    answer = {"question_id": elite, "slot": 1, "body": "Ask", "structured": gossip}
    assert save(troupe.player, agnes, [answer]).status_code == 200
    assert troupe.player.client.post(f"/characters/{agnes}/downtime/submit").status_code == 200
    (response,) = troupe.storyteller.client.get(f"/cycles/{form['cycle_id']}/responses").json()

    looked = troupe.storyteller.client.get(f"/responses/{response['id']}/lookup").json()

    assert (looked["specializations"], looked["found"]) == ([], [])


def test_only_lookups_look_and_only_staff_who_keep_the_log(scene: Scene) -> None:
    responses = scene.submit(
        (UNDERWORLD, WORD, "Ask around"),
        (UNDERWORLD, {"specialization": "Finance", "action": "free_travel"}, "Travel"),
    )

    assert scene.look_up(responses[0], by=scene.troupe.narrator).status_code == 403
    assert scene.look_up(responses[0], by=scene.troupe.player).status_code == 403
    assert scene.look_up(responses[1]).status_code == 422
    # The other answer is no lookup, so the strength is one.
    assert scene.look_up(responses[0]).json()["strength"] == 1


# --- the lookback -----------------------------------------------------------------------


def test_storytellers_set_the_lookback_on_the_house_rules(scene: Scene) -> None:
    path = f"/troupes/{scene.troupe.id}"
    assert scene.troupe.lead.client.get(path).json()["influence_lookback_days"] == 90

    assert (
        scene.troupe.assistant.client.put(f"{path}/influence-lookback", json={"days": 100})
    ).status_code == 403
    assert (
        scene.troupe.storyteller.client.put(f"{path}/influence-lookback", json={"days": 0})
    ).status_code == 422
    changed = scene.troupe.storyteller.client.put(f"{path}/influence-lookback", json={"days": 100})

    assert changed.status_code == 200, changed.text
    assert changed.json()["influence_lookback_days"] == 100
    assert scene.messages()[0] == "storyteller set how far back influence lookups look: 100 days."


# --- discovery blocks -------------------------------------------------------------------


def block(fields: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"specialization": "Finance", "action": "discovery_block", **(fields or {})}


def test_a_player_picks_from_their_own_entries_in_the_lookback(scene: Scene) -> None:
    mine = scene.add(timedelta(days=3), character_id=scene.agnes, purpose="To move the money")
    elite = scene.add(
        timedelta(days=4),
        character_id=scene.agnes,
        type="elite",
        specialization="",
        action_key="a_friend_in_need",
    )
    scene.add(timedelta(days=200), character_id=scene.agnes)  # too long ago
    scene.add(
        timedelta(days=3),
        character_id=scene.agnes,
        action_key="attack",
        target={"character_id": scene.bram},
    )  # no blocking it
    scene.add(timedelta(days=3), character_id=scene.bram)  # someone else's

    choices = scene.troupe.player.client.get(f"/characters/{scene.agnes}/downtime/block-choices")

    assert choices.status_code == 200, choices.text
    entries = choices.json()["entries"]
    assert [(e["short_id"], e["action"]) for e in entries] == [
        (mine, "3: Illegal Favors"),
        (elite, "1: A Friend in Need"),
    ]
    assert entries[0]["purpose"] == "To move the money"
    assert "name" not in entries[0]
    assert (
        scene.troupe.stranger.client.get(f"/characters/{scene.agnes}/downtime/block-choices")
    ).status_code in (403, 404)


def test_staff_accept_a_block_on_the_entry_the_player_picked(scene: Scene) -> None:
    mine = scene.add(timedelta(days=3), character_id=scene.agnes)
    entry_id = scene.entry(mine)["id"]
    (response, word) = scene.submit(
        (UNDERWORLD, block({"block": "own", "block_entry": entry_id}), "Hide the bank job"),
        (UNDERWORLD, WORD, "Ask around"),
    )
    path = f"/responses/{response['id']}/discovery-block"

    shown = scene.troupe.assistant.client.get(path)

    assert shown.status_code == 200, shown.text
    assert shown.json()["whose"] == "own"
    assert shown.json()["picked"]["short_id"] == mine
    assert shown.json()["block"] is None
    assert mine in [c["short_id"] for c in shown.json()["choices"]]

    accepted = scene.troupe.assistant.client.post(path, json={"entry_id": entry_id})

    assert accepted.status_code == 200, accepted.text
    assert (accepted.json()["body"], accepted.json()["status"]) == ("Blocked (now 1).", "written")
    entry = scene.entry(mine)
    assert entry["blocks"] == 1
    assert [
        (b["character_name"], b["cycle_name"], b["response_id"]) for b in entry["blocked_by"]
    ] == [("Agnes", "October 2026", response["id"])]
    assert scene.troupe.assistant.client.get(path).json()["block"]["entry"]["short_id"] == mine
    assert scene.messages()[1] == (
        f"assistant blocked {mine} in the influence log: Agnes, 3: Illegal Favors (now 1)."
    )
    # One block for each answer.
    assert scene.troupe.assistant.client.post(path, json={"entry_id": entry_id}).status_code == 409
    # Agnes's own entries are never found by her own lookup, blocked or not.
    assert scene.found(word) == []


def test_a_block_on_someone_elses_entry_described_in_words(scene: Scene) -> None:
    theirs = scene.add(timedelta(days=3), character_id=scene.bram)
    (response,) = scene.submit(
        (UNDERWORLD, block({"block": "other"}), "Hide Bram's lockdown of the bank"),
    )
    path = f"/responses/{response['id']}/discovery-block"
    assert (scene.troupe.assistant.client.get(path).json()["whose"]) == "other"

    accepted = scene.troupe.assistant.client.post(
        path, json={"entry_id": scene.entry(theirs)["id"]}
    )

    assert accepted.status_code == 200, accepted.text
    assert scene.entry(theirs)["blocks"] == 1


def test_a_player_cannot_pick_someone_elses_entry(scene: Scene) -> None:
    theirs = scene.add(timedelta(days=3), character_id=scene.bram)
    picked = block({"block": "own", "block_entry": scene.entry(theirs)["id"]})
    (response,) = scene.submit((UNDERWORLD, picked, "Hide it"))

    shown = scene.troupe.assistant.client.get(f"/responses/{response['id']}/discovery-block")

    assert shown.json()["picked"] is None


def test_an_elite_block_can_hide_an_underworld_entry(scene: Scene) -> None:
    underworld = scene.add(timedelta(days=3))
    (response,) = scene.submit((ELITE, {"action": "discovery_block"}, "Hide the bank job"))

    accepted = scene.troupe.storyteller.client.post(
        f"/responses/{response['id']}/discovery-block",
        json={"entry_id": scene.entry(underworld)["id"]},
    )

    assert accepted.status_code == 200, accepted.text
    assert scene.entry(underworld)["blocks"] == 1


def test_conflict_actions_cannot_be_blocked(scene: Scene) -> None:
    attack = scene.add(timedelta(days=3), action_key="attack", target={"character_id": scene.bram})
    (response,) = scene.submit((UNDERWORLD, block(), "Hide the attack"))

    refused = scene.troupe.storyteller.client.post(
        f"/responses/{response['id']}/discovery-block",
        json={"entry_id": scene.entry(attack)["id"]},
    )

    assert refused.status_code == 422
    assert scene.entry(attack)["blocks"] == 0


def test_only_discovery_block_answers_block_and_only_log_keepers_accept(scene: Scene) -> None:
    entry = scene.add(timedelta(days=3))
    word, hide = scene.submit((UNDERWORLD, WORD, "Ask"), (UNDERWORLD, block(), "Hide"))
    body = {"entry_id": scene.entry(entry)["id"]}

    assert (
        scene.troupe.storyteller.client.post(f"/responses/{word['id']}/discovery-block", json=body)
    ).status_code == 422
    assert (
        scene.troupe.narrator.client.post(f"/responses/{hide['id']}/discovery-block", json=body)
    ).status_code == 403
    assert (
        scene.troupe.storyteller.client.get(f"/responses/{word['id']}/discovery-block").status_code
        == 404
    )


def test_blocks_add_up_and_a_lookup_needs_more_strength_than_them(scene: Scene) -> None:
    hidden = scene.add(timedelta(days=3))
    responses = scene.submit(
        (UNDERWORLD, block({"block": "other"}), "Hide the bank job"),
        (UNDERWORLD, WORD, "Ask around"),
        (UNDERWORLD, WORD, "Ask again"),
    )
    entry_id = scene.entry(hidden)["id"]
    assert scene.found(responses[1]) == [hidden]  # strength 2, no blocks yet

    scene.troupe.storyteller.client.post(
        f"/responses/{responses[0]['id']}/discovery-block", json={"entry_id": entry_id}
    )
    assert scene.found(responses[1]) == [hidden]  # strength 2 gets past 1 block
    changed = scene.troupe.storyteller.client.put(
        f"/influence-entries/{entry_id}",
        json={
            **{k: scene.entry(hidden)[k] for k in ("type", "happened_at", "name")},
            "blocks": 2,
            "specialization": "Finance",
            "action_key": "illegal_favors",
        },
    )
    assert changed.status_code == 200, changed.text

    assert scene.found(responses[1]) == []  # not past 2


def test_a_mistaken_block_is_taken_off_again(scene: Scene) -> None:
    entry = scene.add(timedelta(days=3))
    entry_id = scene.entry(entry)["id"]
    first, second = scene.submit(
        (UNDERWORLD, block({"block": "other"}), "Hide it"),
        (UNDERWORLD, block({"block": "other"}), "Hide it more"),
    )
    for response in (first, second):
        accepted = scene.troupe.storyteller.client.post(
            f"/responses/{response['id']}/discovery-block", json={"entry_id": entry_id}
        )
        assert accepted.json()["body"].startswith("Blocked (now")
    assert scene.entry(entry)["blocks"] == 2

    # From the response editor…
    undone = scene.troupe.storyteller.client.delete(f"/responses/{first['id']}/discovery-block")
    assert undone.status_code == 204, undone.text
    assert scene.entry(entry)["blocks"] == 1
    # …or from the log page.
    (source,) = scene.entry(entry)["blocked_by"]
    assert source["response_id"] == second["id"]
    removed = scene.troupe.assistant.client.delete(f"/influence-blocks/{source['id']}")
    assert removed.status_code == 204, removed.text
    assert (scene.entry(entry)["blocks"], scene.entry(entry)["blocked_by"]) == (0, [])
    assert scene.messages()[0] == (
        f"assistant took a block off {entry} in the influence log: REDACTED, "
        "3: Illegal Favors (now 0)."
    )
    assert (
        scene.troupe.storyteller.client.delete(f"/responses/{first['id']}/discovery-block")
    ).status_code == 409


def test_merging_entries_keeps_the_blocks_answers_added(scene: Scene) -> None:
    keep = scene.add(timedelta(days=3))
    other = scene.add(timedelta(days=2))
    (response,) = scene.submit((UNDERWORLD, block({"block": "other"}), "Hide it"))
    scene.troupe.storyteller.client.post(
        f"/responses/{response['id']}/discovery-block", json={"entry_id": scene.entry(other)["id"]}
    )

    merged = scene.troupe.storyteller.client.post(
        f"/influence-entries/{scene.entry(keep)['id']}/merge",
        json={"entry_ids": [scene.entry(other)["id"]]},
    )

    assert merged.status_code == 200, merged.text
    assert merged.json()["blocks"] == 1
    assert [b["response_id"] for b in merged.json()["blocked_by"]] == [response["id"]]


def test_a_characters_history_shows_the_blocks_it_placed_and_the_troupes_lookback(
    scene: Scene,
) -> None:
    # Blocked twice already by others, then once by Agnes.
    mine = scene.add(timedelta(days=3), character_id=scene.agnes, blocks=2)
    entry_id = scene.entry(mine)["id"]
    (response,) = scene.submit(
        (UNDERWORLD, block({"block": "own", "block_entry": entry_id}), "Hide the bank job"),
    )
    accepted = scene.troupe.assistant.client.post(
        f"/responses/{response['id']}/discovery-block", json={"entry_id": entry_id}
    )
    assert accepted.status_code == 200, accepted.text
    changed = scene.troupe.storyteller.client.put(
        f"/troupes/{scene.troupe.id}/influence-lookback", json={"days": 100}
    )
    assert changed.status_code == 200, changed.text

    found = scene.troupe.player.client.get(f"/characters/{scene.agnes}/influence").json()

    assert found["lookback_days"] == 100
    assert [(e["id"], e["own_blocks"]) for e in found["entries"]] == [(entry_id, 1)]

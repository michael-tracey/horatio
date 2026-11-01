"""Feeding in downtimes: each clan's difficulty, what traits and staff change, the
Feeding section with Herd and gifts, and the storytellers' answer."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.rules import feeding as rules
from horatio.rules.files import all_rule_set_files, load_rule_set
from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_api_downtimes import my_downtime, new_cycle, open_cycle, question_id

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def vampire(troupe: Troupe, player: Person, name: str, clan: str, *traits: Any) -> str:
    """A character of `clan` with `traits` ((category, name, rating) each), whose
    home troupe is `troupe`."""
    character_id = new_character(troupe, player, name, clan=clan)
    for category, trait, rating in traits:
        bought = player.client.put(
            f"/characters/{character_id}/traits",
            json={"category": category, "name": trait, "rating": rating},
        )
        assert bought.status_code == 200, bought.text
    requested = player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert requested.status_code == 201, requested.text
    approved = troupe.lead.client.post(f"/approvals/{requested.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    return character_id


def feeding_form(player: Person, character_id: str) -> dict[str, Any]:
    response = my_downtime(player, character_id)
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()["feeding"]
    return found


def save_feeding(
    player: Person, character_id: str, answers: list[dict[str, Any]] | None = None, **feeding: Any
) -> Any:
    return player.client.put(
        f"/characters/{character_id}/downtime/answers",
        json={"answers": answers or [], "feeding": feeding},
    )


def staff_view(troupe: Troupe, cycle_id: str, person: Person | None = None) -> Any:
    return (person or troupe.storyteller).client.get(f"/cycles/{cycle_id}/feeding")


def character_view(troupe: Troupe, cycle_id: str, name: str) -> dict[str, Any]:
    response = staff_view(troupe, cycle_id)
    assert response.status_code == 200, response.text
    return next(c for c in response.json()["characters"] if c["character_name"] == name)


def submit(player: Person, character_id: str) -> None:
    response = player.client.post(f"/characters/{character_id}/downtime/submit")
    assert response.status_code == 200, response.text


# --- the difficulty ---------------------------------------------------------------------


def test_each_clan_needs_one_unless_staff_say_otherwise(troupe: Troupe) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Gangrel: Coyote")
    cycle = open_cycle(troupe, new_cycle(troupe))

    form = feeding_form(troupe.player, agnes)
    assert form["need"]["needed"] == 1
    assert [line["text"] for line in form["need"]["lines"]] == ["Gangrel 1"]

    clans = {c["clan"]: c for c in staff_view(troupe, cycle["id"]).json()["clans"]}
    assert clans["Gangrel"] == {"clan": "Gangrel", "amount": 1, "reason": "", "characters": 1}
    assert clans["Ventrue"]["amount"] == 1

    url = f"/cycles/{cycle['id']}/feeding/clans/Gangrel"
    body = {"amount": 2, "reason": "the woods are crawling with hunters"}
    assert troupe.narrator.client.put(url, json=body).status_code == 403
    assert troupe.player.client.put(url, json=body).status_code == 403
    changed = troupe.assistant.client.put(url, json=body)
    assert changed.status_code == 200, changed.text
    unknown = troupe.storyteller.client.put(f"/cycles/{cycle['id']}/feeding/clans/Elves", json=body)
    assert unknown.status_code == 422

    form = feeding_form(troupe.player, agnes)
    assert form["need"]["needed"] == 2
    assert [line["text"] for line in form["need"]["lines"]] == [
        "Gangrel 2 (the woods are crawling with hunters)"
    ]
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert (
        "assistant set Gangrel feeding to 2 this cycle: the woods are crawling with hunters" in log
    )


def test_the_next_cycle_copies_each_clans_number(troupe: Troupe) -> None:
    cycle = open_cycle(troupe, new_cycle(troupe))
    troupe.storyteller.client.put(
        f"/cycles/{cycle['id']}/feeding/clans/Nosferatu", json={"amount": 3, "reason": "Hunters"}
    )
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")

    following = new_cycle(troupe)

    clans = {c["clan"]: c for c in staff_view(troupe, following["id"]).json()["clans"]}
    assert (clans["Nosferatu"]["amount"], clans["Nosferatu"]["reason"]) == (3, "Hunters")
    assert clans["Brujah"]["amount"] == 1


def test_traits_and_staff_change_a_characters_number(troupe: Troupe) -> None:
    agnes = vampire(
        troupe,
        troupe.player,
        "Agnes",
        "Gangrel",
        ("flaws", "Disease Carrier", 4),
        ("merits", "Efficient Digestion", 1),
    )
    cycle = open_cycle(troupe, new_cycle(troupe))

    need = feeding_form(troupe.player, agnes)["need"]
    assert need["needed"] == 2
    assert [line["text"] for line in need["lines"]] == [
        "Gangrel 1",
        "Disease Carrier +1",
        "Efficient Digestion (Herd counts 2×)",
    ]
    assert need["lines"][1]["page"] == "262"
    assert need["herd_factor"] == 2
    # Disease Carrier's extra action is feeding now, not fewer downtime actions.
    assert my_downtime(troupe.player, agnes).json()["allowance"]["general"] == 3

    participant = character_view(troupe, cycle["id"], "Agnes")["participant_id"]
    url = f"/cycles/{cycle['id']}/participants/{participant}/feeding-adjustments"
    body = {"delta": -1, "reason": "fed at the Elysium feast"}
    assert troupe.narrator.client.post(url, json=body).status_code == 403
    adjusted = troupe.assistant.client.post(url, json=body)
    assert adjusted.status_code == 200, adjusted.text

    need = feeding_form(troupe.player, agnes)["need"]
    assert need["needed"] == 1
    assert need["lines"][-1]["text"] == "Storyteller −1 (fed at the Elysium feast)"


def test_a_character_with_no_clan_has_no_feeding_section(troupe: Troupe) -> None:
    clanless = new_character(troupe, troupe.player, "Nobody")
    requested = troupe.player.client.post(
        f"/characters/{clanless}/home-troupe", json={"troupe_id": troupe.id}
    )
    troupe.lead.client.post(f"/approvals/{requested.json()['id']}/approve", json={})
    open_cycle(troupe, new_cycle(troupe))

    assert my_downtime(troupe.player, clanless).json()["feeding"] is None
    assert save_feeding(troupe.player, clanless, actions=1).status_code == 422


# --- the Feeding section ----------------------------------------------------------------


def test_feeding_actions_come_out_of_the_general_actions(troupe: Troupe) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    open_cycle(troupe, new_cycle(troupe))
    general = question_id(my_downtime(troupe.player, agnes).json(), "Downtime action")
    two = [
        {"question_id": general, "slot": 1, "body": "Patrol"},
        {"question_id": general, "slot": 2, "body": "Research"},
    ]

    assert save_feeding(troupe.player, agnes, two, actions=1, where="The docks").status_code == 200
    refused = save_feeding(troupe.player, agnes, two, actions=2)
    assert refused.status_code == 422
    assert "with 2 spent feeding" in refused.json()["detail"]
    assert save_feeding(troupe.player, agnes, actions=4).status_code == 422

    answer = feeding_form(troupe.player, agnes)["answer"]
    assert (answer["actions"], answer["where"]) == (1, "The docks")


def test_herd_is_shared_out_up_to_its_rating(troupe: Troupe) -> None:
    other = sign_up(troupe.client_for, "other")
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador", ("backgrounds", "Herd", 3))
    bram = vampire(troupe, other, "Bram", "Brujah")
    outsider = new_character(troupe, other, "Outsider", clan="Brujah")
    open_cycle(troupe, new_cycle(troupe))

    form = feeding_form(troupe.player, agnes)
    assert form["herd"] == 3
    assert [r["name"] for r in form["recipients"]] == ["Bram"]

    too_many = save_feeding(
        troupe.player, agnes, herd_own=2, gifts=[{"character_id": bram, "amount": 2}]
    )
    assert too_many.status_code == 422
    assert "4 dots of Herd" in too_many.json()["detail"]
    stranger = save_feeding(troupe.player, agnes, gifts=[{"character_id": outsider, "amount": 1}])
    assert stranger.status_code == 422
    assert save_feeding(other, bram, herd_own=1).status_code == 422  # Bram has no Herd

    saved = save_feeding(
        troupe.player,
        agnes,
        actions=0,
        herd_own=1,
        gifts=[{"character_id": bram, "amount": 2}],
    )
    assert saved.status_code == 200, saved.text

    received = feeding_form(other, bram)["received"]
    assert [(r["character_name"], r["amount"], r["submitted"]) for r in received] == [
        ("Agnes", 2, False)
    ]


# --- the answer -------------------------------------------------------------------------


def test_full_and_half_answers_carry_the_working_and_half_starts_play_at_half(
    troupe: Troupe,
) -> None:
    other = sign_up(troupe.client_for, "other")
    agnes = vampire(
        troupe,
        troupe.player,
        "Agnes",
        "Gangrel",
        ("backgrounds", "Herd", 3),
        ("flaws", "Disease Carrier", 4),
    )
    bram = vampire(troupe, other, "Bram", "Brujah")
    cycle = open_cycle(troupe, new_cycle(troupe))
    troupe.storyteller.client.put(
        f"/cycles/{cycle['id']}/feeding/clans/Brujah", json={"amount": 4, "reason": "Riots"}
    )
    save_feeding(
        troupe.player,
        agnes,
        actions=1,
        herd_own=1,
        gifts=[{"character_id": bram, "amount": 2}],
    )
    save_feeding(other, bram, actions=1, where="Night clubs")
    submit(troupe.player, agnes)

    # Agnes needs 2 and puts 2 towards it; Bram needs 4 and has 1 plus Agnes's 2.
    agnes_view = character_view(troupe, cycle["id"], "Agnes")
    assert agnes_view["tally"] == {
        "needed": 2,
        "parts": [
            {"label": "Feeding actions", "amount": 1},
            {"label": "your Herd", "amount": 1},
        ],
        "total": 2,
        "enough": True,
    }
    assert agnes_view["summary"] == "1 feeding action · Herd: 1 for my feeding, 2 to Bram"
    url = f"/cycles/{cycle['id']}/participants/{{}}/feeding-answer"
    early = troupe.storyteller.client.put(
        url.format(character_view(troupe, cycle["id"], "Bram")["participant_id"]),
        json={"result": "half"},
    )
    assert early.status_code == 409  # Bram has not submitted
    submit(other, bram)
    bram_view = character_view(troupe, cycle["id"], "Bram")
    assert (bram_view["tally"]["total"], bram_view["tally"]["enough"]) == (3, False)

    answer_agnes = url.format(agnes_view["participant_id"])
    answer_bram = url.format(bram_view["participant_id"])
    assert troupe.narrator.client.put(answer_agnes, json={"result": "full"}).status_code == 403
    assert troupe.storyteller.client.put(answer_agnes, json={"result": "other"}).status_code == 422
    full = troupe.assistant.client.put(
        answer_agnes, json={"result": "full", "reply": "The pack ran well."}
    )
    assert full.status_code == 200, full.text
    half = troupe.storyteller.client.put(answer_bram, json={"result": "half"})
    assert half.status_code == 200, half.text

    # Answered, the player's Feeding section can no longer change.
    locked = save_feeding(troupe.player, agnes, actions=0, herd_own=3)
    assert locked.status_code == 409
    assert feeding_form(troupe.player, agnes)["locked"] is True

    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    delivered = troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver")
    assert delivered.json()["delivered"] == 2

    agnes_result = troupe.player.client.get(f"/characters/{agnes}/downtime/results").json()[0]
    assert (
        "**Feeding**\n*Your feeding:* 1 feeding action · Herd: 1 for my feeding, 2 to Bram\n"
        "*Result:* **Full Blood next game.** The pack ran well.\n\n"
        "▸ How it was worked out: needed 2 (Gangrel 1, Disease Carrier +1). "
        "Feeding actions 1; your Herd 1. Total 2."
    ) in agnes_result["message"]
    bram_result = other.client.get(f"/characters/{bram}/downtime/results").json()[0]
    assert (
        "*Result:* **Half Blood next game.**\n\n"
        "▸ How it was worked out: needed 4 (Brujah 4 (Riots)). "
        "Feeding actions 1; Herd from Agnes 2. Total 3."
    ) in bram_result["message"]

    bram_play = other.client.get(f"/characters/{bram}/play").json()
    assert bram_play["half_blood"] is True
    assert bram_play["blood"]["start"] == -(-bram_play["blood"]["most"] // 2)
    assert bram_play["blood"]["value"] == bram_play["blood"]["start"]
    agnes_play = troupe.player.client.get(f"/characters/{agnes}/play").json()
    assert agnes_play["half_blood"] is False
    assert agnes_play["blood"]["start"] == agnes_play["blood"]["most"]


def test_half_blood_lasts_one_game(troupe: Troupe) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    cycle = open_cycle(troupe, new_cycle(troupe))
    submit(troupe.player, agnes)
    participant = character_view(troupe, cycle["id"], "Agnes")["participant_id"]
    troupe.storyteller.client.put(
        f"/cycles/{cycle['id']}/participants/{participant}/feeding-answer",
        json={"result": "half"},
    )
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver")
    play = troupe.player.client.get(f"/characters/{agnes}/play").json()
    assert play["half_blood"] is True

    tapped = troupe.player.client.post(
        f"/characters/{agnes}/play/taps",
        json={
            "taps": [
                {
                    "id": "0192f0c4-0000-7000-8000-000000000001",
                    "happened_at": "2026-10-23T20:00:00Z",
                    "kind": "change",
                    "tracker": "blood",
                    "amount": 1,
                }
            ]
        },
    )
    assert tapped.status_code == 200, tapped.text
    # Players can still add Blood by hand.
    assert tapped.json()["blood"]["value"] == play["blood"]["start"] + 1
    reset = troupe.player.client.post(f"/characters/{agnes}/play/reset", json={})
    assert reset.json()["half_blood"] is False
    assert reset.json()["blood"]["start"] == reset.json()["blood"]["most"]


def test_a_feeding_answer_changed_after_delivery_goes_out_as_an_update(troupe: Troupe) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    cycle = open_cycle(troupe, new_cycle(troupe))
    submit(troupe.player, agnes)
    participant = character_view(troupe, cycle["id"], "Agnes")["participant_id"]
    url = f"/cycles/{cycle['id']}/participants/{participant}/feeding-answer"
    troupe.storyteller.client.put(url, json={"result": "full"})
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    first = troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver").json()
    assert (first["delivered"], first["updated"]) == (1, 0)
    assert troupe.player.client.get(f"/characters/{agnes}/play").json()["half_blood"] is False

    # Still answerable once delivered: the change goes out with the next delivery.
    assert character_view(troupe, cycle["id"], "Agnes")["delivered"] is True
    changed = troupe.storyteller.client.put(url, json={"result": "half"})
    assert changed.status_code == 200, changed.text
    again = troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver").json()
    assert (again["delivered"], again["updated"]) == (1, 1)

    [result] = troupe.player.client.get(f"/characters/{agnes}/downtime/results").json()
    assert "*Result:* **Half Blood next game.**" in result["message"]
    assert troupe.player.client.get(f"/characters/{agnes}/play").json()["half_blood"] is True


def test_an_other_answer_has_no_working(troupe: Troupe) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    cycle = open_cycle(troupe, new_cycle(troupe))
    submit(troupe.player, agnes)
    participant = character_view(troupe, cycle["id"], "Agnes")["participant_id"]
    troupe.storyteller.client.put(
        f"/cycles/{cycle['id']}/participants/{participant}/feeding-answer",
        json={"result": "other", "reply": "You fed on a ghoul; see me at game."},
    )
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver")

    message = troupe.player.client.get(f"/characters/{agnes}/downtime/results").json()[0]["message"]
    assert "**Feeding**\n*Result:* You fed on a ghoul; see me at game." in message
    assert "How it was worked out" not in message
    assert troupe.player.client.get(f"/characters/{agnes}/play").json()["half_blood"] is False


# --- the troupe's setting ---------------------------------------------------------------


def set_feeding(troupe: Troupe, person: Person | None = None, **body: Any) -> Any:
    return (person or troupe.storyteller).client.put(f"/troupes/{troupe.id}/feeding", json=body)


def answer_url(troupe: Troupe, cycle_id: str, name: str) -> str:
    participant = character_view(troupe, cycle_id, name)["participant_id"]
    return f"/cycles/{cycle_id}/participants/{participant}/feeding-answer"


def test_a_troupe_that_doesnt_track_feeding_leaves_it_out_and_keeps_what_it_had(
    troupe: Troupe,
) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    cycle = open_cycle(troupe, new_cycle(troupe))
    general = question_id(my_downtime(troupe.player, agnes).json(), "Downtime action")
    patrol = [{"question_id": general, "slot": 1, "body": "Patrol"}]
    assert save_feeding(troupe.player, agnes, patrol, actions=1, where="The docks").status_code
    submit(troupe.player, agnes)
    url = answer_url(troupe, cycle["id"], "Agnes")
    assert troupe.storyteller.client.put(url, json={"result": "half"}).status_code == 200
    assert troupe.lead.client.get(f"/troupes/{troupe.id}").json()["feeding"] == "book"

    # Only storytellers change it, as with the troupe's other house rules.
    assert set_feeding(troupe, troupe.assistant, feeding="off").status_code == 403
    off = set_feeding(troupe, feeding="off")
    assert off.status_code == 200, off.text
    assert (off.json()["feeding"], off.json()["feeding_resonance"]) == ("off", False)
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller set feeding to not tracked, with optional rules: none." in log

    # No Feeding section, no Feeding tab, and nothing to answer.
    assert my_downtime(troupe.player, agnes).json()["feeding"] is None
    assert troupe.storyteller.client.get(f"/cycles/{cycle['id']}").json()["feeding"] is False
    assert staff_view(troupe, cycle["id"]).status_code == 409
    assert troupe.storyteller.client.put(url, json={"result": "full"}).status_code == 409
    # Its feeding action no longer counts against the general actions; what the player
    # sends for feeding is not saved over what they had.
    three = [{"question_id": general, "slot": n, "body": f"Action {n}"} for n in (1, 2, 3)]
    saved = save_feeding(troupe.player, agnes, three, actions=0, where="")
    assert saved.status_code == 200, saved.text

    # Delivered, the results have no feeding, and the next game starts at full Blood.
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    for r in troupe.assistant.client.get(f"/cycles/{cycle['id']}/responses").json():
        troupe.assistant.client.put(f"/responses/{r['id']}", json={"body": "Quiet night."})
    [ready] = troupe.assistant.client.get(f"/cycles/{cycle['id']}/deliveries").json()[
        "participants"
    ]
    assert (ready["answered"], ready["to_answer"]) == (3, 3)
    assert troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver").json()["delivered"]
    [result] = troupe.player.client.get(f"/characters/{agnes}/downtime/results").json()
    assert "Feeding" not in result["message"]
    assert troupe.player.client.get(f"/characters/{agnes}/play").json()["half_blood"] is False

    # Switched back on, everything is as it was, and goes out as an update.
    assert set_feeding(troupe, feeding="book").status_code == 200
    view = character_view(troupe, cycle["id"], "Agnes")
    assert (view["result"], view["summary"]) == ("half", "1 feeding action (The docks)")
    [ready] = troupe.assistant.client.get(f"/cycles/{cycle['id']}/deliveries").json()[
        "participants"
    ]
    assert (ready["answered"], ready["to_answer"], ready["changed"]) == (4, 4, True)
    again = troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver").json()
    assert (again["delivered"], again["updated"]) == (1, 1)
    results = troupe.player.client.get(f"/characters/{agnes}/downtime/results").json()
    assert "*Result:* **Half Blood next game.**" in results[0]["message"]
    assert troupe.player.client.get(f"/characters/{agnes}/play").json()["half_blood"] is True


def test_switching_feeding_off_after_delivery_is_no_news(troupe: Troupe) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    cycle = open_cycle(troupe, new_cycle(troupe))
    submit(troupe.player, agnes)
    troupe.storyteller.client.put(answer_url(troupe, cycle["id"], "Agnes"), json={"result": "half"})
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver")

    set_feeding(troupe, feeding="off")

    # The player keeps the results they had; switching feeding off is not an update,
    # and the half Blood they were told of no longer applies.
    [ready] = troupe.assistant.client.get(f"/cycles/{cycle['id']}/deliveries").json()[
        "participants"
    ]
    assert (ready["delivered"], ready["changed"], ready["due"]) == (True, False, False)
    [result] = troupe.player.client.get(f"/characters/{agnes}/downtime/results").json()
    assert "**Feeding**" in result["message"]
    assert troupe.player.client.get(f"/characters/{agnes}/play").json()["half_blood"] is False
    set_feeding(troupe, feeding="book")
    assert troupe.player.client.get(f"/characters/{agnes}/play").json()["half_blood"] is True


def test_the_setting_shows_in_the_troupes_house_rules(troupe: Troupe) -> None:
    names = ("Feeding", "Blood Resonance", "Feeding territories", "Advanced feeding: the Rack")

    def feeding_rules() -> list[dict[str, Any]]:
        house = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()
        return [o for o in house["other"] if o["name"] in names]

    assert feeding_rules() == []
    set_feeding(troupe, feeding="book", resonance=True)
    [rule] = feeding_rules()
    assert rule["name"] == "Blood Resonance"
    assert "Vol. 2, pp. 294-297" in rule["text"]
    set_feeding(troupe, feeding="book", resonance=True, territories=True, rack=True)
    assert [r["name"] for r in feeding_rules()] == list(names[1:])
    set_feeding(troupe, feeding="off", resonance=True)
    [rule] = feeding_rules()
    assert (rule["name"], rule["text"]) == (
        "Feeding",
        "Not tracked: no feeding in downtimes, results or at the next game",
    )
    # Resonance is kept for when feeding comes back.
    assert troupe.lead.client.get(f"/troupes/{troupe.id}").json()["feeding_resonance"] is True
    assert set_feeding(troupe, feeding="sometimes").status_code == 422


# --- Blood Resonance --------------------------------------------------------------------


def test_blood_resonance_from_the_form_to_the_results(troupe: Troupe) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    cycle = open_cycle(troupe, new_cycle(troupe))
    assert feeding_form(troupe.player, agnes)["humors"] == []
    set_feeding(troupe, feeding="book", resonance=True)

    form = feeding_form(troupe.player, agnes)
    assert [h["key"] for h in form["humors"]] == [
        "choleric",
        "melancholic",
        "phlegmatic",
        "sanguine",
    ]
    sanguine = form["humors"][3]
    assert sanguine["feelings"] == "enthusiasm, vitality, excitement or joy"
    assert "Manic High" in [d["name"] for d in sanguine["dyscrasias"]]
    assert save_feeding(troupe.player, agnes, actions=1, resonance="bilious").status_code == 422
    saved = save_feeding(troupe.player, agnes, actions=1, resonance="sanguine")
    assert saved.status_code == 200, saved.text
    submit(troupe.player, agnes)

    view = character_view(troupe, cycle["id"], "Agnes")
    assert view["summary"] == "1 feeding action · hunting sanguine blood"
    url = answer_url(troupe, cycle["id"], "Agnes")
    wrong = troupe.storyteller.client.put(
        url, json={"result": "full", "resonance": "phlegmatic", "dyscrasia": "Manic High"}
    )
    assert wrong.status_code == 422  # Manic High is sanguine
    answered = troupe.storyteller.client.put(
        url, json={"result": "full", "resonance": "sanguine", "dyscrasia": "Manic High"}
    )
    assert answered.status_code == 200, answered.text
    view = character_view(troupe, cycle["id"], "Agnes")
    assert (view["resonance"], view["dyscrasia"]) == ("sanguine", "Manic High")

    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver")
    [result] = troupe.player.client.get(f"/characters/{agnes}/downtime/results").json()
    assert (
        "**Feeding**\n*Your feeding:* 1 feeding action · hunting sanguine blood\n"
        "*Result:* **Full Blood next game.**\n\n"
        "Fed on **sanguine** blood (enthusiasm, vitality, excitement or joy). "
        "Dyscrasia: **Manic High**: +1 wild card if you won your last challenge, within the "
        "last minute. Use it once, before the end of the next game (Vol. 2, pp. 296-297)."
        "\n\n▸ How it was worked out:"
    ) in result["message"]

    # Switched off, the Resonance is kept but no longer shown, and is no news.
    set_feeding(troupe, feeding="book", resonance=False)
    view = character_view(troupe, cycle["id"], "Agnes")
    assert (view["resonance"], view["summary"]) == (None, "1 feeding action")
    [ready] = troupe.assistant.client.get(f"/cycles/{cycle['id']}/deliveries").json()[
        "participants"
    ]
    assert ready["changed"] is False
    set_feeding(troupe, feeding="book", resonance=True)
    assert character_view(troupe, cycle["id"], "Agnes")["dyscrasia"] == "Manic High"


def test_a_resonance_with_no_dyscrasia(troupe: Troupe) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    cycle = open_cycle(troupe, new_cycle(troupe))
    set_feeding(troupe, feeding="book", resonance=True)
    submit(troupe.player, agnes)
    url = answer_url(troupe, cycle["id"], "Agnes")
    troupe.storyteller.client.put(url, json={"result": "half", "resonance": "melancholic"})
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver")

    [result] = troupe.player.client.get(f"/characters/{agnes}/downtime/results").json()
    assert (
        "Fed on **melancholic** blood (sadness, fear, awareness or melancholy). No Dyscrasia."
    ) in result["message"]

    # Taking the answer back takes its Resonance with it.
    troupe.storyteller.client.put(url, json={"result": None})
    view = character_view(troupe, cycle["id"], "Agnes")
    assert (view["result"], view["resonance"]) == (None, None)


# --- the rules --------------------------------------------------------------------------


def test_the_working_reads_as_the_issue_shows_it() -> None:
    basis = {
        "clan": "Gangrel",
        "modifiers": [
            {
                "source": "Disease Carrier",
                "amount": 1,
                "herd_factor": 1,
                "always_half": False,
                "page": "262",
            }
        ],
        "herd": 1,
    }
    need = rules.need(1, "", basis)
    counted = rules.tally(need, 1, 1, [("Bram", 2)])

    assert rules.working(need, counted) == (
        "needed 2 (Gangrel 1, Disease Carrier +1). Feeding actions 1; your Herd 1; "
        "Herd from Bram 2. Total 4."
    )
    assert counted.enough


def test_no_herd_and_always_half() -> None:
    basis = {
        "clan": "Baali",
        "modifiers": [
            {"source": "Methuselah's Thirst", "amount": 0, "herd_factor": 0, "always_half": True}
        ],
        "herd": 2,
    }
    need = rules.need(1, "", basis)
    counted = rules.tally(need, 3, 2, [("Bram", 1)])

    assert [p for p in counted.parts] == [
        ("Feeding actions", 3),
        ("your Herd", 0),
        ("Herd from Bram", 0),
    ]
    assert not counted.enough


def test_every_feeding_modifier_names_a_trait() -> None:
    for path in all_rule_set_files():
        rule_set = load_rule_set(path)
        for modifier in rule_set.feeding_modifiers:
            assert (modifier.category, modifier.trait) in rule_set.traits


# --- feeding territories and the Rack -------------------------------------------------


def territory(troupe: Troupe, name: str, size: str, *holders: str, **body: Any) -> str:
    made = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/feeding-territories",
        json={"name": name, "size": size, "holder_ids": list(holders), **body},
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def results_of(player: Person, character_id: str) -> str:
    [result] = player.client.get(f"/characters/{character_id}/downtime/results").json()
    return str(result["message"])


def test_the_rack_needs_blood_resonance(troupe: Troupe) -> None:
    refused = set_feeding(troupe, feeding="book", rack=True)
    assert refused.status_code == 422
    assert "builds on Blood Resonance" in refused.json()["detail"]
    on = set_feeding(troupe, feeding="book", resonance=True, rack=True)
    assert (on.json()["feeding_rack"], on.json()["feeding_resonance"]) == (True, True)


def test_territories_with_book_feeding_poaching_and_patrols(troupe: Troupe) -> None:
    other = sign_up(troupe.client_for, "other")
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    bram = vampire(troupe, other, "Bram", "Brujah")
    body = {"name": "Docks", "size": "small"}
    url = f"/troupes/{troupe.id}/feeding-territories"
    assert troupe.storyteller.client.post(url, json=body).status_code == 409  # rule off
    set_feeding(troupe, feeding="book", territories=True)
    assert troupe.narrator.client.post(url, json=body).status_code == 403
    assert troupe.player.client.post(url, json=body).status_code == 403
    docks = territory(troupe, "Docks", "small", agnes, held_by="Clan Toreador")
    territory(troupe, "Gold Coast", "notable", area="Lakeside mansions")
    assert troupe.storyteller.client.post(url, json=body).status_code == 409  # same name
    listed = troupe.player.client.get(url).json()
    assert [(t["name"], t["vessels"], t["holders"]) for t in listed] == [
        ("Docks", 2, ["Agnes"]),
        ("Gold Coast", 6, []),
    ]
    assert troupe.stranger.client.get(url).status_code == 404

    cycle = open_cycle(troupe, new_cycle(troupe))
    form = feeding_form(troupe.player, agnes)
    assert [(t["name"], t["mine"]) for t in form["territories"]] == [
        ("Docks", True),
        ("Gold Coast", False),
    ]
    general = question_id(my_downtime(troupe.player, agnes).json(), "Downtime action")
    three = [{"question_id": general, "slot": n, "body": f"Action {n}"} for n in (1, 2, 3)]
    patrol = [{"territory_id": docks, "actions": 1}]
    too_many = save_feeding(troupe.player, agnes, three, territory=docks, patrols=patrol)
    assert too_many.status_code == 422
    assert "spent feeding or patrolling" in too_many.json()["detail"]
    saved = save_feeding(troupe.player, agnes, territory=docks, patrols=patrol)
    assert saved.status_code == 200, saved.text
    assert save_feeding(other, bram, patrols=patrol).status_code == 422  # not his to patrol
    assert save_feeding(other, bram, territory=docks).status_code == 200
    submit(troupe.player, agnes)
    submit(other, bram)

    # Feeding in a territory stands in for a feeding action; Bram poaches there.
    agnes_view = character_view(troupe, cycle["id"], "Agnes")
    assert (
        agnes_view["summary"]
        == "0 feeding actions · feeding in Docks · patrolling Docks (1 action)"
    )
    assert (agnes_view["tally"]["total"], agnes_view["tally"]["enough"]) == (1, True)
    bram_view = character_view(troupe, cycle["id"], "Bram")
    assert bram_view["poaching"] == "Docks"
    assert [(p["character_name"], p["actions"]) for p in bram_view["patrols"]] == [("Agnes", 1)]
    uses = staff_view(troupe, cycle["id"]).json()["territories"]
    assert uses[0]["feeding"] == ["Agnes", "Bram"]

    bram_url = answer_url(troupe, cycle["id"], "Bram")
    wrong = troupe.storyteller.client.put(bram_url, json={"result": "half", "caught_by": [bram]})
    assert wrong.status_code == 422
    caught = troupe.storyteller.client.put(bram_url, json={"result": "half", "caught_by": [agnes]})
    assert caught.status_code == 200, caught.text
    troupe.storyteller.client.put(answer_url(troupe, cycle["id"], "Agnes"), json={"result": "full"})
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    assert troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver").json()["delivered"] == 2

    assert "You were caught poaching in Docks by Agnes." in results_of(other, bram)
    assert "Patrolling Docks, you caught Bram poaching." in results_of(troupe.player, agnes)


def test_the_rack_from_laying_it_out_to_the_results(troupe: Troupe) -> None:
    other = sign_up(troupe.client_for, "other")
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador", ("backgrounds", "Herd", 2))
    bram = vampire(troupe, other, "Bram", "Ventrue")
    set_feeding(troupe, feeding="book", resonance=True, territories=True, rack=True)
    territory(troupe, "Docks", "small", agnes)
    cycle = open_cycle(troupe, new_cycle(troupe))

    rack_url = f"/cycles/{cycle['id']}/rack"
    assert troupe.narrator.client.post(rack_url, json={"count": 3}).status_code == 403
    dealt = troupe.storyteller.client.post(rack_url, json={"count": 3})
    assert dealt.status_code == 200, dealt.text
    laid = dealt.json()["rack"]
    assert (laid["players"], laid["suggested"]) == (2, 3)
    sources = sorted(c["source"] for c in laid["cards"])
    assert sources == ["herd", "herd", "rack", "rack", "rack", "territory", "territory"]
    assert len({c["number"] for c in laid["cards"]}) == 7
    assert {c["dealt_to"] for c in laid["cards"] if c["source"] == "herd"} == {"Agnes"}
    # Dealing again tops up the Rack, but never deals Herd or territory cards twice.
    again = troupe.storyteller.client.post(rack_url, json={"count": 0}).json()["rack"]
    assert len(again["cards"]) == 7

    agnes_form = feeding_form(troupe.player, agnes)
    bram_form = feeding_form(other, bram)
    assert agnes_form["rack"] is True
    assert len(agnes_form["cards"]) == 7
    assert sorted(c["source"] for c in bram_form["cards"]) == [
        "rack",
        "rack",
        "rack",
        "territory",
        "territory",
    ]

    # First come, first served: Agnes takes a card from the Rack, and Bram can't.
    on_rack = [c for c in agnes_form["cards"] if c["source"] == "rack"]
    take = "/characters/{}/downtime/vessel"
    taken = troupe.player.client.post(take.format(agnes), json={"card_id": on_rack[0]["id"]})
    assert taken.status_code == 200, taken.text
    assert (
        other.client.post(take.format(bram), json={"card_id": on_rack[0]["id"]}).status_code == 409
    )
    herd_card = next(c for c in agnes_form["cards"] if c["source"] == "herd")
    assert (
        other.client.post(take.format(bram), json={"card_id": herd_card["id"]}).status_code == 422
    )
    # Bram's Ventrue weakness: never a card ending as the second one does.
    participant = character_view(troupe, cycle["id"], "Bram")["participant_id"]
    restricted = troupe.storyteller.client.put(
        f"/cycles/{cycle['id']}/participants/{participant}/feeding-numbers",
        json={"rule": {"mode": "never", "endings": [on_rack[1]["number"] % 10]}},
    )
    assert restricted.status_code == 200, restricted.text
    refused = other.client.post(take.format(bram), json={"card_id": on_rack[1]["id"]})
    assert refused.status_code == 422
    assert "never cards ending in" in refused.json()["detail"]
    # Agnes changes her mind; the card she gave back is free again.
    troupe.player.client.post(take.format(agnes), json={"card_id": herd_card["id"]})
    docks_card = next(c for c in bram_form["cards"] if c["source"] == "territory")
    took = other.client.post(take.format(bram), json={"card_id": docks_card["id"]})
    assert took.status_code == 200, took.text

    # Hunting outside the Rack deals 3, 2 or 1 cards, once a cycle.
    hunted = other.client.post(f"/characters/{bram}/downtime/hunt")
    assert hunted.status_code == 200, hunted.text
    form = hunted.json()["feeding"]
    hunt_cards = [c for c in form["cards"] if c["source"] == "hunt"]
    assert len(hunt_cards) == {"win": 3, "tie": 2, "lose": 1}[form["hunt"]]
    assert other.client.post(f"/characters/{bram}/downtime/hunt").status_code == 409
    # With the Rack, feeding actions are not spent: all three actions are free.
    general = question_id(my_downtime(other, bram).json(), "Downtime action")
    three = [{"question_id": general, "slot": n, "body": f"Action {n}"} for n in (1, 2, 3)]
    assert save_feeding(other, bram, three, actions=2).status_code == 200
    assert feeding_form(other, bram)["hunt"] == form["hunt"]
    submit(troupe.player, agnes)
    submit(other, bram)

    view = character_view(troupe, cycle["id"], "Bram")
    assert view["vessel"]["id"] == docks_card["id"]
    assert view["poaching"] == "Docks"
    assert view["restriction"]["text"].startswith("Never cards ending in")
    card_url = f"{rack_url}/{docks_card['id']}"
    changed = troupe.storyteller.client.put(
        card_url, json={"resonance": "choleric", "dyscrasia": "Bully", "descriptor": "a dock hand"}
    )
    assert changed.status_code == 200, changed.text
    assert troupe.storyteller.client.delete(card_url).status_code == 409  # taken
    answered = troupe.storyteller.client.put(
        answer_url(troupe, cycle["id"], "Bram"),
        json={"result": "full", "resonance": "choleric", "dyscrasia": "Bully"},
    )
    assert answered.status_code == 200, answered.text
    locked = other.client.post(take.format(bram), json={"card_id": None})
    assert locked.status_code == 409
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    # His actions are not answered yet; his feeding goes out with what there is.
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver", json={"partial": True})

    message = results_of(other, bram)
    number = docks_card["number"]
    assert (
        f"*Your feeding:* Feeding Card {number}, choleric, Bully (a dock hand), from Docks"
    ) in message
    assert "Poaching in Docks, you went unnoticed." in message
    assert f"▸ How it was worked out: took Feeding Card {number}" in message


def test_the_book_number_of_cards() -> None:
    from horatio import rack

    assert [rack.suggested(n) for n in (10, 20, 30, 40)] == [14, 28, 42, 56]
    assert rack.suggested(20, masquerade="severe") == 20
    assert rack.suggested(10, mood="very") == 19

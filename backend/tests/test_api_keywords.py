"""Downtime keywords (#509): the defaults, what each question offers, Feed and Patrol
feeding the Feeding section, Learn standing for what is owed, Computer's Observe and
Cancel, keywords required each cycle, the resolution order, and troupes' own."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_downtimes import (
    member_character,
    my_downtime,
    new_cycle,
    open_cycle,
    question_id,
    save,
)
from tests.test_api_feeding import set_feeding, staff_view, territory, vampire
from tests.test_api_owed_actions import approve_all, take
from tests.test_api_quests import give as give_trait
from tests.test_api_sect_status import put_trait

pytestmark = pytest.mark.usefixtures("without_bank")

DEFAULT_ORDER = [
    "Feed",
    "Patrol",
    "Investigate",
    "Beyond Your Means",
    "Quest",
    "Learn",
    "Craft",
    "Perform",
    "Narrative",
    "Rhetorical",
    "Observe",
    "Cancel",
]


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def give(troupe: Troupe, character_id: str, category: str, name: str, rating: int) -> None:
    given = troupe.storyteller.client.post(
        f"/characters/{character_id}/give",
        json={
            "category": category,
            "name": name,
            "detail": "",
            "rating": rating,
            "free": True,
            "reason": "x",
        },
    )
    assert given.status_code == 200, given.text


def offered(form: dict[str, Any], prompt: str) -> list[str]:
    names = {k["key"]: k["name"] for k in form["keywords"]}
    return [names[k] for k in form["question_keywords"].get(question_id(form, prompt), [])]


def action(form: dict[str, Any], body: str, keyword: str | None, slot: int = 1, **fields: Any):
    structured = {"keyword": keyword, **fields} if keyword else fields
    return {
        "question_id": question_id(form, "Downtime action"),
        "slot": slot,
        "body": body,
        "structured": structured,
    }


def keywords_url(troupe: Troupe) -> str:
    return f"/troupes/{troupe.id}/keywords"


def submit(player: Person, character_id: str) -> Any:
    return player.client.post(f"/characters/{character_id}/downtime/submit")


def responses(troupe: Troupe, cycle: dict[str, Any]) -> list[dict[str, Any]]:
    found = troupe.storyteller.client.get(f"/cycles/{cycle['id']}/responses")
    assert found.status_code == 200, found.text
    return list(found.json())


def test_each_question_offers_the_keywords_its_kind_allows(troupe: Troupe) -> None:
    agnes = vampire(
        troupe, troupe.player, "Agnes", "Toreador", ("backgrounds", "Influences: The Elite", 1)
    )
    open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()

    # Patrol needs feeding territories, Observe and Cancel the Computer skill, and Quest
    # is the form's Quest action.
    assert offered(form, "Downtime action") == [
        "Feed",
        "Investigate",
        "Beyond Your Means",
        "Learn",
        "Craft",
        "Perform",
        "Narrative",
        "Rhetorical",
    ]
    # Influence answers take no keyword: their influence action says what they are.
    assert question_id(form, "Elite influence action") not in form["question_keywords"]

    give(troupe, agnes, "skills", "Computer", 1)
    set_feeding(troupe, feeding="book", territories=True)
    form = my_downtime(troupe.player, agnes).json()
    assert offered(form, "Downtime action")[-3:] == ["Rhetorical", "Observe", "Cancel"]
    assert "Patrol" in offered(form, "Downtime action")


def test_answers_with_no_keyword_count_as_narrative(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()
    saved = save(troupe.player, agnes, [action(form, "Visit the Prince", None)])
    assert saved.status_code == 200, saved.text
    assert submit(troupe.player, agnes).status_code == 200

    [item] = responses(troupe, cycle)
    assert (item["keyword"], item["keyword_key"], item["step"]) == ("Narrative", "narrative", 5)


def test_a_keyword_must_be_offered_and_keeps_only_its_fields(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()

    for bad in ("observe", "quest", "nonsense"):
        refused = save(troupe.player, agnes, [action(form, "x", bad)])
        assert refused.status_code == 422, bad

    # A field the keyword doesn't ask for is dropped.
    saved = save(
        troupe.player,
        agnes,
        [action(form, "A rifle", "beyond_your_means", item="Rifle", learn="X")],
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["answers"][0]["structured"] == {
        "keyword": "beyond_your_means",
        "item": "Rifle",
    }


def test_what_a_keyword_asks_for_is_needed_to_submit(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    bram = member_character(troupe, sign_up(troupe.client_for, "bram_player"), "Bram")
    cycle = open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()

    # A draft saves without it, as the player fills it in.
    assert save(troupe.player, agnes, [action(form, "Dig", "investigate")]).status_code == 200
    refused = submit(troupe.player, agnes)
    assert refused.status_code == 422
    assert "who or what it is aimed at for your Investigate action" in refused.json()["detail"]

    # A character, or something else in words.
    aims: list[dict[str, Any]] = [{"aimed_at": [bram]}, {"subject": "The missing ghoul"}]
    for fields in aims:
        saved = save(troupe.player, agnes, [action(form, "Dig", "investigate", **fields)])
        assert saved.status_code == 200, saved.text
        assert submit(troupe.player, agnes).status_code == 200

    [item] = responses(troupe, cycle)
    assert (item["keyword"], item["keyword_key"]) == ("Investigate", "investigate")


def test_feed_answers_are_the_feeding_actions(troupe: Troupe) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    cycle = open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()

    two = [action(form, "Hunt the docks", "feed"), action(form, "Hunt again", "feed", 2)]
    saved = save(troupe.player, agnes, two)
    assert saved.status_code == 200, saved.text
    assert saved.json()["feeding"]["answer"]["actions"] == 2
    # They spend their own actions, not the section's as well.
    three = [*two, action(form, "Ask around", "narrative", 3)]
    assert save(troupe.player, agnes, three).status_code == 200
    assert submit(troupe.player, agnes).status_code == 200
    [view] = staff_view(troupe, cycle["id"]).json()["characters"]
    assert view["summary"].startswith("2 feeding actions")

    # Gone, they take their feeding actions with them.
    one = save(troupe.player, agnes, [action(form, "Ask around", "narrative")])
    assert one.json()["feeding"]["answer"]["actions"] == 0


def test_feed_in_a_territory_and_patrol_go_to_the_feeding_section(troupe: Troupe) -> None:
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    set_feeding(troupe, feeding="book", territories=True)
    docks = territory(troupe, "Docks", "small", agnes)
    park = territory(troupe, "Park", "small")
    open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()

    # Feeding in a territory stands in for a feeding action without spending one, so
    # with three actions there is room for three more.
    answers = [
        action(form, "Feed at the docks", "feed", territory=docks),
        action(form, "Feed", "feed", 2),
        action(form, "Patrol", "patrol", 3, territory=docks),
        action(form, "Patrol", "patrol", 4, territory=docks),
    ]
    saved = save(troupe.player, agnes, answers)
    assert saved.status_code == 200, saved.text
    fed = saved.json()["feeding"]["answer"]
    assert (fed["actions"], fed["territory"]) == (1, docks)
    assert fed["patrols"] == [{"territory_id": docks, "actions": 2}]

    twice = [*answers[:1], action(form, "Feed", "feed", 2, territory=park)]
    assert save(troupe.player, agnes, twice).status_code == 422
    # Only a territory's holders patrol it.
    poaching = [action(form, "Patrol", "patrol", territory=park)]
    assert save(troupe.player, agnes, poaching).status_code == 422
    assert save(troupe.player, agnes, [action(form, "Patrol", "patrol")]).status_code == 200
    assert "which territory" in submit(troupe.player, agnes).json()["detail"]


def test_observe_and_cancel_come_from_computer_once_a_cycle(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    bram = member_character(troupe, sign_up(troupe.client_for, "bram_player"), "Bram")
    cycle = open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()
    observe = action(form, "Read Bram's email", "observe", aimed_at=[bram])
    assert save(troupe.player, agnes, [observe]).status_code == 422  # no Computer

    give(troupe, agnes, "skills", "Computer", 1)
    saved = save(troupe.player, agnes, [observe])
    assert saved.status_code == 200, saved.text
    # The keyword marks it Computer's Observe (#507).
    assert saved.json()["answers"][0]["structured"]["counter"] == "observe"
    both = [observe, action(form, "Stop him", "cancel", 2, aimed_at=[bram])]
    assert "one action a cycle" in save(troupe.player, agnes, both).json()["detail"]
    at_two = action(form, "x", "cancel", aimed_at=[bram, agnes])
    assert save(troupe.player, agnes, [at_two]).status_code == 422

    assert save(troupe.player, agnes, [observe]).status_code == 200
    assert submit(troupe.player, agnes).status_code == 200
    [item] = responses(troupe, cycle)
    assert (item["keyword"], item["step"]) == ("Observe", 6)


def test_learning_shows_ready_made_and_costs_nothing_more(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    take(troupe.player, agnes, "disciplines", "Celerity", 1)
    approve_all(troupe)
    open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()
    assert form["allowance"]["general"] == 2
    [learning] = form["learning"]
    assert (learning["what"], learning["teacher"]) == ("Celerity 1", "")

    confirmed = action(form, "Practise", "learn", learn="Celerity 1", owed_action_id=learning["id"])
    others = [action(form, f"Action {n}", "narrative", n) for n in (2, 3)]
    saved = save(troupe.player, agnes, [confirmed, *others])
    assert saved.status_code == 200, saved.text
    # Each owed action is one Learn action, and only a Learn action.
    twice = [confirmed, {**confirmed, "slot": 2}]
    assert save(troupe.player, agnes, twice).status_code == 422
    wrong = action(form, "x", "narrative", owed_action_id=learning["id"])
    assert (
        "owed_action_id"
        not in save(troupe.player, agnes, [wrong]).json()["answers"][0]["structured"]
    )


def test_a_keyword_can_be_required_each_cycle_by_social_age(troupe: Troupe) -> None:
    struggle = troupe.storyteller.client.post(
        keywords_url(troupe),
        json={
            "name": "Eternal Struggle",
            "explanation": "What your elder does to keep their place.",
            "required_for": ["Elder"],
        },
    )
    assert struggle.status_code == 201, struggle.text
    key = next(k["key"] for k in struggle.json()["keywords"] if k["name"] == "Eternal Struggle")
    elder = member_character(troupe, troupe.player, "Agnes")
    put_trait(troupe.session, elder, "backgrounds", "Generation", 3)
    neonate = member_character(troupe, troupe.player, "Bram")
    open_cycle(troupe, new_cycle(troupe))

    form = my_downtime(troupe.player, elder).json()
    assert form["required_keywords"] == [key]
    refused = submit(troupe.player, elder)
    assert refused.status_code == 422
    assert "add a Eternal Struggle action, which Elders take each cycle" in refused.json()["detail"]
    saved = save(troupe.player, elder, [action(form, "Hold court", key)])
    assert saved.status_code == 200, saved.text
    assert submit(troupe.player, elder).status_code == 200

    assert my_downtime(troupe.player, neonate).json()["required_keywords"] == []
    assert submit(troupe.player, neonate).status_code == 200


def test_staff_resolve_in_the_troupes_order(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes", elite=2)
    bram = member_character(troupe, sign_up(troupe.client_for, "bram_player"), "Bram")
    give(troupe, agnes, "skills", "Computer", 1)
    cycle = open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()
    elite = question_id(form, "Elite influence action")
    answers = [
        action(form, "Stop Bram", "cancel", aimed_at=[bram]),
        action(form, "Make a sword", "craft", 2),
        action(form, "Ask the Prince", None, 3),
        {
            "question_id": elite,
            "slot": 1,
            "body": "Gossip",
            "structured": {"action": "gossip_and_insider_trading"},
        },
        {"question_id": elite, "slot": 2, "body": "Defend", "structured": {"action": "defend"}},
    ]
    saved = save(troupe.player, agnes, answers)
    assert saved.status_code == 200, saved.text
    assert submit(troupe.player, agnes).status_code == 200

    items = sorted(responses(troupe, cycle), key=lambda i: i["resolution"])
    assert [(i["answer"], i["step"]) for i in items] == [
        ("Defend", 1),
        ("Gossip", 3),
        ("Stop Bram", 4),
        ("Make a sword", 5),
        ("Ask the Prince", 5),
    ]

    # Staff move Narrative ahead of Craft, and Cancel to come with the other actions.
    listed = troupe.storyteller.client.get(keywords_url(troupe)).json()["keywords"]
    keys = [k["key"] for k in listed]
    keys.remove("narrative")
    keys.insert(keys.index("craft"), "narrative")
    reordered = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/keyword-order", json={"keys": keys}
    )
    assert reordered.status_code == 200, reordered.text
    cancel = next(k for k in listed if k["key"] == "cancel")
    moved = troupe.storyteller.client.put(
        f"{keywords_url(troupe)}/cancel", json={**cancel, "step": 5}
    )
    assert moved.status_code == 200, moved.text
    items = sorted(responses(troupe, cycle), key=lambda i: i["resolution"])
    # An answer from before keywords is Narrative, so it comes ahead of Craft now.
    assert [i["answer"] for i in items][2:] == ["Ask the Prince", "Make a sword", "Stop Bram"]


def test_troupes_rename_retire_and_add_keywords_as_house_rules(troupe: Troupe) -> None:
    listed = troupe.storyteller.client.get(keywords_url(troupe))
    assert listed.status_code == 200, listed.text
    assert [k["name"] for k in listed.json()["keywords"]] == DEFAULT_ORDER
    assert troupe.player.client.get(keywords_url(troupe)).status_code == 403

    rhetorical = next(k for k in listed.json()["keywords"] if k["key"] == "rhetorical")
    body = {**rhetorical, "name": "Colour", "explanation": "Just for fun."}
    # Assistant storytellers read them; storytellers change them.
    assert troupe.assistant.client.get(keywords_url(troupe)).status_code == 200
    assert (
        troupe.assistant.client.put(f"{keywords_url(troupe)}/rhetorical", json=body).status_code
        == 403
    )
    changed = troupe.storyteller.client.put(f"{keywords_url(troupe)}/rhetorical", json=body)
    assert changed.status_code == 200, changed.text
    colour = next(k for k in changed.json()["keywords"] if k["key"] == "rhetorical")
    assert colour["default"]["name"] == "Rhetorical"

    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()
    saved = save(troupe.player, agnes, [action(form, "Paint", "rhetorical")])
    assert saved.status_code == 200, saved.text

    # Retired, it is offered no more, but an answer that has it keeps it.
    retired = troupe.storyteller.client.put(
        f"{keywords_url(troupe)}/rhetorical/retired", json={"retired": True}
    )
    assert retired.status_code == 200, retired.text
    form = my_downtime(troupe.player, agnes).json()
    assert "Colour" not in offered(form, "Downtime action")
    assert save(troupe.player, agnes, [action(form, "Paint more", "rhetorical")]).status_code == 200
    assert submit(troupe.player, agnes).status_code == 200
    [item] = responses(troupe, cycle)
    assert item["keyword"] == "Colour"

    own = troupe.storyteller.client.post(
        keywords_url(troupe),
        json={"name": "Hunt", "fields": ["target"], "cost": 2, "step": 5},
    )
    assert own.status_code == 201, own.text
    assert own.json()["keywords"][-1]["name"] == "Hunt"
    taken = troupe.storyteller.client.post(keywords_url(troupe), json={"name": "Feed"})
    assert taken.status_code == 409
    bad = troupe.storyteller.client.post(
        keywords_url(troupe), json={"name": "Odd", "action_kinds": ["nothing"]}
    )
    assert bad.status_code == 422

    rules = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()["other"]
    names = [r["name"] for r in rules]
    assert "Downtime keyword: Colour" in names
    assert "Downtime keyword: Hunt" in names

    reset = troupe.storyteller.client.delete(keywords_url(troupe))
    assert reset.status_code == 200, reset.text
    names_now = [(k["name"], k["retired"]) for k in reset.json()["keywords"]]
    assert names_now[: len(DEFAULT_ORDER)] == [(n, False) for n in DEFAULT_ORDER]
    assert ("Hunt", True) in names_now


def test_science_actions_go_only_on_keywords_that_fit_a_science(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    give_trait(troupe.session, agnes, "skills", "Science", 1, "Physics")
    open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()
    assert form["allowance"]["general"] == 4

    performing = [action(form, f"Sing {n}", "perform", n) for n in (1, 2, 3, 4)]
    refused = save(troupe.player, agnes, performing)
    assert refused.status_code == 422
    assert "1 of this character's actions is a Science action" in refused.json()["detail"]
    # One of them on a keyword that fits: Investigate, Craft or Narrative.
    fitting = [*performing[:3], action(form, "Test the blood", "investigate", 4)]
    assert save(troupe.player, agnes, fitting).status_code == 200


def test_staff_see_how_many_craft_actions_a_character_took(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()
    answers = [
        action(form, "Forge a blade", "craft"),
        action(form, "Sell it", "craft", 2),
        action(form, "Sing", "perform", 3),
    ]
    assert save(troupe.player, agnes, answers).status_code == 200
    assert submit(troupe.player, agnes).status_code == 200
    counts = {i["answer"]: i["keyword_actions"] for i in responses(troupe, cycle)}
    assert counts == {"Forge a blade": 2, "Sell it": 2, "Sing": 1}


def test_an_action_with_a_keyword_saves_before_it_is_described(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))
    form = my_downtime(troupe.player, agnes).json()
    saved = save(troupe.player, agnes, [action(form, "", "narrative"), action(form, "", None, 2)])
    assert saved.status_code == 200, saved.text
    assert [a["structured"] for a in saved.json()["answers"]] == [{"keyword": "narrative"}]
    refused = submit(troupe.player, agnes)
    assert "say what it is for your Narrative action" in refused.json()["detail"]

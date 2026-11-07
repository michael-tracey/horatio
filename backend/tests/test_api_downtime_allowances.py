"""Downtime allowances the book gives and takes (issue #506): Computer, Science, Soul
of the Homunculi, Ay Befriend, Triumphant, Veteran, Quick Hands, Quick Work, rare
disciplines, and what staff apply from a response: Call of the Hungry Dead, indirect
influence attacks, Crafts, Performance and overtaxed Resources."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import HeldStatus
from horatio.rules.model import AllowanceRuleData
from horatio.rules.store import add_house_allowance_rule
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_downtimes import (
    member_character,
    my_downtime,
    new_cycle,
    open_cycle,
    question_id,
    save,
)
from tests.test_api_feeding import (
    answer_url,
    character_view,
    feeding_form,
    results_of,
    save_feeding,
    set_feeding,
    submit,
    territory,
    vampire,
)
from tests.test_api_owed_actions import approve_all, take
from tests.test_api_play import send, tap
from tests.test_api_play_status import entry, undo, view
from tests.test_api_quests import give
from tests.test_api_sect_status import add, held_id, member

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def downtime(person: Person, character_id: str) -> dict[str, Any]:
    response = my_downtime(person, character_id)
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


def lines(form: dict[str, Any]) -> list[tuple[str, int, str]]:
    """The breakdown past the base allowance: source, amount, and what it is only for."""
    return [(b["source"], b["amount"], b["only"]) for b in form["breakdown"][1:]]


# --- what the sheet gives -----------------------------------------------------------------


def test_computer_gives_an_action_to_spend_or_to_stop_or_watch_another(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    give(troupe.session, agnes, "skills", "Computer", 1)

    open_cycle(troupe, new_cycle(troupe))

    form = downtime(troupe.player, agnes)
    assert form["allowance"]["general"] == 4
    [computer] = [b for b in form["breakdown"] if b["source"] == "Computer"]
    assert computer["amount"] == 1
    assert "p. 93" in computer["note"]


def test_each_science_gives_an_action_for_its_own_field(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    give(troupe.session, agnes, "skills", "Science", 1, "Physics")
    give(troupe.session, agnes, "skills", "Science", 2, "Chemistry")

    cycle = open_cycle(troupe, new_cycle(troupe))

    form = downtime(troupe.player, agnes)
    assert form["allowance"]["general"] == 5
    assert lines(form) == [
        ("Science: Chemistry", 1, "Chemistry"),
        ("Science: Physics", 1, "Physics"),
    ]
    # Staff see the same breakdown.
    [staff] = troupe.storyteller.client.get(f"/cycles/{cycle['id']}/participants").json()
    assert [b["only"] for b in staff["breakdown"] if b["only"]] == ["Chemistry", "Physics"]


def test_a_troupe_can_give_further_sciences_only_at_higher_ratings(
    troupe: Troupe, session: Session
) -> None:
    replaced = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/allowances",
        json={
            "action_kind": "general",
            "category": "skills",
            "trait": "Science",
            "scheme": "per_detail",
            "amount": 1,
            "detail_ratings": [1, 3, 5],
        },
    )
    assert replaced.status_code == 201, replaced.text
    assert replaced.json()["amount_text"] == "+1 downtime action for each field, at 1, 3, 5"
    agnes = member_character(troupe, troupe.player, "Agnes")
    give(troupe.session, agnes, "skills", "Science", 2, "Chemistry")
    give(troupe.session, agnes, "skills", "Science", 1, "Physics")
    bram = member_character(troupe, troupe.player, "Bram")
    give(troupe.session, bram, "skills", "Science", 3, "Chemistry")
    give(troupe.session, bram, "skills", "Science", 1, "Physics")
    give(troupe.session, bram, "skills", "Science", 1, "Botany")

    open_cycle(troupe, new_cycle(troupe))

    # A second field counts from 3 dots, a third from 5.
    assert lines(downtime(troupe.player, agnes)) == [("Science: Chemistry", 1, "Chemistry")]
    assert [s for s, _, _ in lines(downtime(troupe.player, bram))] == [
        "Science: Chemistry",
        "Science: Botany",
    ]
    bad = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/allowances",
        json={
            "action_kind": "general",
            "category": "skills",
            "trait": "Computer",
            "scheme": "fixed",
            "amount": 1,
            "detail_ratings": [1, 3],
        },
    )
    assert bad.status_code == 422


def test_soul_of_the_homunculi_and_ay_befriend_give_actions(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    give(troupe.session, agnes, "rituals", "Thaumaturgy: Soul of the Homunculi", 1)
    give(troupe.session, agnes, "disciplines", "Mytherceria", 3)
    bram = member_character(troupe, troupe.player, "Bram")
    give(troupe.session, bram, "disciplines", "Mytherceria", 2)

    open_cycle(troupe, new_cycle(troupe))

    form = downtime(troupe.player, agnes)
    assert form["allowance"]["general"] == 6
    befriend = next(b for b in form["breakdown"] if b["source"] == "Mytherceria")
    assert "no one can trace or watch" in befriend["note"]
    assert ("Thaumaturgy: Soul of the Homunculi", 2, "") in lines(form)
    # Ay Befriend is Mytherceria's third power.
    assert downtime(troupe.player, bram)["allowance"]["general"] == 3


def test_house_rules_override_a_book_allowance(troupe: Troupe, session: Session) -> None:
    add_house_allowance_rule(
        session,
        uuid.UUID(troupe.id),
        "vampire",
        AllowanceRuleData(
            action_kind="general", scheme="fixed", amount=0, category="skills", trait="Computer"
        ),
    )
    agnes = member_character(troupe, troupe.player, "Agnes")
    give(troupe.session, agnes, "skills", "Computer", 2)

    open_cycle(troupe, new_cycle(troupe))

    assert downtime(troupe.player, agnes)["allowance"]["general"] == 3


# --- feeding --------------------------------------------------------------------------------


def hold(session: Session, character_id: str, name: str) -> None:
    session.add(
        HeldStatus(character_id=uuid.UUID(character_id), name=name, given_on=date(2026, 11, 1))
    )
    session.flush()


def test_triumphant_feeds_with_one_action_fewer_and_never_poaches(troupe: Troupe) -> None:
    other = sign_up(troupe.client_for, "other")
    set_feeding(troupe, feeding="book", territories=True)
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador")
    bram = vampire(troupe, other, "Bram", "Brujah")
    hold(troupe.session, agnes, "Triumphant")
    docks = territory(troupe, "Docks", "small", bram)
    cycle = open_cycle(troupe, new_cycle(troupe))

    need = feeding_form(troupe.player, agnes)["need"]
    assert need["needed"] == 0
    assert [line["text"] for line in need["lines"]] == [
        "Toreador 1",
        "Triumphant −1 (feeds in any territory)",
    ]
    assert save_feeding(troupe.player, agnes, territory=docks).status_code == 200
    submit(troupe.player, agnes)
    assert character_view(troupe, cycle["id"], "Agnes")["poaching"] is None


# --- Quick Hands, Quick Work ------------------------------------------------------------------


def test_quick_hands_quick_work_trades_feeding_for_two_actions(troupe: Troupe) -> None:
    other = sign_up(troupe.client_for, "other")
    agnes = vampire(troupe, troupe.player, "Agnes", "Toreador", ("backgrounds", "Herd", 2))
    bram = vampire(troupe, other, "Bram", "Brujah", ("backgrounds", "Herd", 1))
    give(troupe.session, agnes, "techniques", "Quick Hands, Quick Work", 1)
    cycle = open_cycle(troupe, new_cycle(troupe))

    form = downtime(troupe.player, agnes)
    assert form["quick_hands"] == {"on": False, "can_change": True}
    assert downtime(other, bram)["quick_hands"] is None
    url = f"/characters/{agnes}/downtime/answers"
    refused = other.client.put(
        f"/characters/{bram}/downtime/answers", json={"answers": [], "quick_hands": True}
    )
    assert refused.status_code == 422

    # Feeding is refused under it; giving Herd away is not.
    fed = troupe.player.client.put(
        url, json={"answers": [], "quick_hands": True, "feeding": {"actions": 1}}
    )
    assert fed.status_code == 422
    gift = [{"character_id": bram, "amount": 2}]
    on = troupe.player.client.put(
        url, json={"answers": [], "quick_hands": True, "feeding": {"gifts": gift}}
    )
    assert on.status_code == 200, on.text
    form = on.json()
    assert form["allowance"]["general"] == 5
    assert ("Quick Hands, Quick Work", 2, "") in lines(form)
    general = question_id(form, "Downtime action")
    five = [{"question_id": general, "slot": n, "body": f"Action {n}"} for n in range(1, 6)]
    assert save(troupe.player, agnes, five).status_code == 200
    # Herd Bram gives her doesn't count: she takes none.
    save_feeding(other, bram, gifts=[{"character_id": agnes, "amount": 1}])
    submit(other, bram)
    submit(troupe.player, agnes)
    off = troupe.player.client.put(url, json={"answers": five, "quick_hands": False})
    assert off.status_code == 409  # fixed once submitted

    agnes_view = character_view(troupe, cycle["id"], "Agnes")
    assert agnes_view["quick_hands"] is True
    assert agnes_view["tally"]["parts"] == [{"label": "Feeding actions", "amount": 0}]
    troupe.storyteller.client.put(answer_url(troupe, cycle["id"], "Bram"), json={"result": "full"})
    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    for response in troupe.storyteller.client.get(f"/cycles/{cycle['id']}/responses").json():
        troupe.storyteller.client.put(f"/responses/{response['id']}", json={"body": "Done."})
    delivered = troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver")
    assert delivered.json()["delivered"] == 2

    assert (
        "*Your feeding:* none, using Quick Hands, Quick Work\n*Result:* **Half Blood next game.**"
    ) in results_of(troupe.player, agnes)
    assert troupe.player.client.get(f"/characters/{agnes}/play").json()["half_blood"] is True


# --- Veteran --------------------------------------------------------------------------------


def test_veteran_spent_at_a_game_gives_the_next_downtime_an_action(troupe: Troupe) -> None:
    agnes = member(troupe, sect="Anarch", clan="Brujah")
    assert add(troupe.player, agnes, "Veteran", story="The siege").status_code == 200
    key = f"held:{held_id(troupe.player, agnes, 'Veteran')}"
    assert entry(view(troupe.player, agnes), "Veteran")["key"] == key
    spend = tap(key, -1)
    send(troupe.player, agnes, spend)

    open_cycle(troupe, new_cycle(troupe))

    form = downtime(troupe.player, agnes)
    assert form["allowance"]["general"] == 4
    [veteran] = form["adjustments"]
    assert veteran["delta"] == 1
    assert veteran["reason"].startswith("Veteran spent at the ")
    assert veteran["reason"].endswith(" game")

    # Undone, the action goes with it.
    send(troupe.player, agnes, undo(spend["id"]))
    assert downtime(troupe.player, agnes)["allowance"]["general"] == 3


# --- rare disciplines -------------------------------------------------------------------------


def test_rare_disciplines_can_take_two_actions_a_dot(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    rule = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/rare-disciplines", json={"on": True}
    )
    assert rule.status_code == 200, rule.text
    assert rule.json()["rare_disciplines_two_actions"] is True
    assert (
        troupe.narrator.client.put(
            f"/troupes/{troupe.id}/rare-disciplines", json={"on": False}
        ).status_code
        == 403
    )
    take(troupe.player, agnes, "disciplines", "Obtenebration", 1)
    take(troupe.player, agnes, "disciplines", "Celerity", 1)
    approve_all(troupe)

    open_cycle(troupe, new_cycle(troupe))

    reasons = {a["reason"]: a["delta"] for a in downtime(troupe.player, agnes)["adjustments"]}
    assert reasons == {
        "Learning Obtenebration 1 (a rare discipline: 1 more a dot)": -2,
        "Learning Celerity 1": -1,
    }


def test_rare_disciplines_take_one_action_while_the_option_is_off(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    take(troupe.player, agnes, "disciplines", "Obtenebration", 1)
    approve_all(troupe)

    open_cycle(troupe, new_cycle(troupe))

    [learning] = downtime(troupe.player, agnes)["adjustments"]
    assert (learning["reason"], learning["delta"]) == ("Learning Obtenebration 1", -1)


# --- what staff apply from a response -----------------------------------------------------------


class Answered:
    """Agnes, with Elite 4, and Bram in an open cycle; Agnes has submitted a general
    action and a level-4 Elite action."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.other = sign_up(troupe.client_for, "other")
        self.agnes = member_character(troupe, troupe.player, "Agnes", elite=4)
        self.bram = member_character(troupe, self.other, "Bram")
        self.cycle = open_cycle(troupe, new_cycle(troupe))
        form = downtime(troupe.player, self.agnes)
        general = question_id(form, "Downtime action")
        elite = question_id(form, "Elite influence action")
        answers = [
            {"question_id": general, "slot": 1, "body": "Paint and sell a portrait"},
            {"question_id": general, "slot": 2, "body": "Rest my accounts"},
            {
                "question_id": elite,
                "slot": 1,
                "body": "Ruin Bram's name with the gentry",
                "structured": {"action": "smooth_over"},
            },
        ]
        assert save(troupe.player, self.agnes, answers).status_code == 200
        submit(troupe.player, self.agnes)

    def response(self, answer: str) -> str:
        found = self.troupe.storyteller.client.get(f"/cycles/{self.cycle['id']}/responses")
        return str(next(r["id"] for r in found.json() if r["answer"] == answer))

    def apply(self, answer: str, kind: str, person: Person | None = None, **body: Any) -> Any:
        person = person or self.troupe.storyteller
        return person.client.post(
            f"/responses/{self.response(answer)}/effects", json={"kind": kind, **body}
        )

    def changes(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = self.troupe.player.client.get(
            f"/characters/{self.agnes}/background-changes"
        ).json()
        return found


@pytest.fixture
def answered(client_for: Callable[[], TestClient], session: Session) -> Answered:
    return Answered(Troupe(client_for, session))


def test_call_of_the_hungry_dead_costs_its_target_an_action_once(answered: Answered) -> None:
    troupe, bram = answered.troupe, answered.bram
    answer = "Paint and sell a portrait"
    narrator = answered.apply(answer, "hungry_dead", troupe.narrator, character_id=bram)
    assert narrator.status_code == 403
    applied = answered.apply(answer, "hungry_dead", character_id=bram)
    assert applied.status_code == 200, applied.text
    assert [a["text"] for a in applied.json()["applied"]] == ["Call of the Hungry Dead: Bram −1"]

    # Bram hasn't submitted, so it comes off this downtime.
    form = downtime(answered.other, bram)
    assert form["allowance"]["general"] == 2
    assert [(a["delta"], a["reason"]) for a in form["adjustments"]] == [
        (-1, "Call of the Hungry Dead against you")
    ]
    again = answered.apply("Rest my accounts", "hungry_dead", character_id=bram)
    assert again.status_code == 409
    assert "doesn't stack" in again.json()["detail"]

    effect = applied.json()["applied"][0]["id"]
    removed = troupe.storyteller.client.delete(
        f"/responses/{answered.response(answer)}/effects/{effect}"
    )
    assert removed.json()["applied"] == []
    assert downtime(answered.other, bram)["allowance"]["general"] == 3


def test_an_indirect_influence_attack_costs_one_action_for_every_two_levels(
    answered: Answered,
) -> None:
    bram = answered.bram
    attack = "Ruin Bram's name with the gentry"
    effects = answered.troupe.storyteller.client.get(
        f"/responses/{answered.response(attack)}/effects"
    ).json()
    assert effects["indirect_cost"] == 2
    assert [t["name"] for t in effects["targets"]] == ["Agnes", "Bram"]
    not_influence = answered.apply("Rest my accounts", "indirect_attack", character_id=bram)
    assert not_influence.status_code == 422

    applied = answered.apply(attack, "indirect_attack", character_id=bram)
    assert applied.status_code == 200, applied.text
    assert downtime(answered.other, bram)["allowance"]["general"] == 1


def test_crafts_and_performance_raise_a_background_for_the_month(answered: Answered) -> None:
    troupe, agnes = answered.troupe, answered.agnes
    give(troupe.session, agnes, "backgrounds", "Resources", 2)
    crafts = answered.apply("Paint and sell a portrait", "crafts")
    assert crafts.status_code == 200, crafts.text
    answered.apply("Rest my accounts", "performance")

    changes = answered.changes()
    assert [(c["trait"], c["rating"], c["now"]) for c in changes] == [
        ("Resources", 2, 3),
        ("Fame", 0, 1),
    ]
    assert changes[0]["changes"][0]["source"] == "crafts"
    assert changes[0]["changes"][0]["ends_at"] is None
    reference = troupe.player.client.get(f"/characters/{agnes}/play/reference").json()
    assert [c["trait"] for c in reference["backgrounds_changed"]] == ["Resources", "Fame"]

    # The next cycle to open ends them.
    troupe.storyteller.client.post(f"/cycles/{answered.cycle['id']}/close")
    open_cycle(troupe, new_cycle(troupe))
    assert answered.changes() == []


def test_overtaxed_resources_recover_in_half_the_time_with_three_actions(
    answered: Answered,
) -> None:
    troupe, agnes = answered.troupe, answered.agnes
    give(troupe.session, agnes, "backgrounds", "Resources", 3)
    nothing = answered.apply("Rest my accounts", "recovery")
    assert nothing.status_code == 422  # not overtaxed
    assert answered.apply("Paint and sell a portrait", "overtaxed").status_code == 200

    [resources] = answered.changes()
    assert (resources["rating"], resources["now"]) == (3, 1)
    [overtaxed] = resources["changes"]
    assert (overtaxed["source"], overtaxed["delta"], overtaxed["games_left"]) == (
        "overtaxed",
        -2,
        6,
    )
    starts = datetime.fromisoformat(overtaxed["starts_at"])
    full = datetime.fromisoformat(overtaxed["ends_at"]) - starts
    assert timedelta(days=89) <= full <= timedelta(days=92)

    halved = answered.apply("Rest my accounts", "recovery")
    assert halved.status_code == 200, halved.text
    assert halved.json()["halved"] is True
    [resources] = answered.changes()
    shorter = resources["changes"][0]
    assert shorter["games_left"] == 3
    assert datetime.fromisoformat(shorter["ends_at"]) - starts == full / 2
    assert answered.apply("Rest my accounts", "recovery").status_code == 409

    effect = next(a["id"] for a in halved.json()["applied"] if a["kind"] == "recovery")
    troupe.storyteller.client.delete(
        f"/responses/{answered.response('Rest my accounts')}/effects/{effect}"
    )
    assert answered.changes()[0]["changes"][0]["games_left"] == 6
    assert datetime.now(UTC) < starts + full

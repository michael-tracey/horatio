"""A character's backstory: its text, who reads it, the troupe's questions, and its
approval as part of accepting the character (horatio.backstories)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import backstories
from horatio.models import AuditEvent, BackstoryQuestion
from tests.api_helpers import Person, Troupe, backstory_optional, new_character, sign_up

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def settings(troupe: Troupe, mode: str = "free", required: bool = True) -> dict[str, Any]:
    response = troupe.lead.client.put(
        f"/troupes/{troupe.id}/backstory-settings", json={"mode": mode, "required": required}
    )
    assert response.status_code == 200, response.text
    return response.json()


def save(person: Person, character_id: str, text: str, version: int) -> Any:
    return person.client.put(
        f"/characters/{character_id}/backstory", json={"text": text, "version": version}
    )


def read(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/backstory")
    assert response.status_code == 200, response.text
    return response.json()


def ask_home(person: Person, character_id: str, troupe_id: str) -> None:
    response = person.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe_id}
    )
    assert response.status_code == 201, response.text


def approval_id(person: Person, troupe_id: str) -> str:
    response = person.client.get(f"/troupes/{troupe_id}/approvals")
    assert response.status_code == 200, response.text
    return response.json()[0]["id"]


def other_troupe(troupe: Troupe, name: str, lead: Person) -> str:
    response = troupe.custodian.client.post(
        "/troupes", json={"name": name, "lead_handle": lead.handle}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


LONG = "\n\n".join(
    f"## Night {n}\n\nShe walked the *wet* streets of **Chicago**, again. " + "Rain. " * 40
    for n in range(1, 400)
)


# --- the text ------------------------------------------------------------------------------


def test_a_long_markdown_backstory_saves_and_reads_back_intact(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player)
    assert len(LONG) > 100_000
    assert read(troupe.player, agnes)["version"] == 0

    saved = save(troupe.player, agnes, LONG, 0)
    assert saved.status_code == 200, saved.text
    body = read(troupe.player, agnes)
    assert body["text"] == LONG
    assert body["version"] == 1
    assert body["written"] and body["length"] == len(LONG)
    assert body["changed_by_name"] == "player"
    assert body["changed_at"]

    # Loading the sheet does not load it.
    sheet = troupe.player.client.get(f"/characters/{agnes}/sheet")
    assert "Night 12" not in sheet.text
    assert "Night 12" not in troupe.player.client.get(f"/characters/{agnes}").text

    # A change goes in the character's log, without the text.
    log = troupe.player.client.get(f"/characters/{agnes}/log").json()
    assert any("changed Agnes's backstory" in e["message"] for e in log)
    assert not any("Night" in e["message"] for e in log)


def test_the_api_caps_its_length(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player)
    too_long = "a" * (backstories.MAX_LENGTH + 1)
    assert save(troupe.player, agnes, too_long, 0).status_code == 422


def test_saving_over_a_newer_version_is_refused(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player)
    assert save(troupe.player, agnes, "Born in 1890.", 0).status_code == 200
    # Another device opened it at version 0 and saves late.
    late = save(troupe.player, agnes, "Born in 1900.", 0)
    assert late.status_code == 409
    assert "submitted since you started" in late.json()["detail"]
    assert read(troupe.player, agnes)["text"] == "Born in 1890."


def draft(person: Person, character_id: str, text: str, based_on: int) -> Any:
    return person.client.put(
        f"/characters/{character_id}/backstory/draft", json={"text": text, "based_on": based_on}
    )


def test_a_draft_saves_as_it_is_typed_without_making_a_version(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player)
    kept = draft(troupe.player, agnes, "Born in 1890, in", 0)
    assert kept.status_code == 200, kept.text
    assert kept.json()["version"] == 0
    assert kept.json()["draft"] == {
        **kept.json()["draft"],
        "text": "Born in 1890, in",
        "based_on": 0,
        "behind": False,
    }
    assert draft(troupe.player, agnes, "Born in 1890, in Dublin.", 0).status_code == 200

    # Saving the draft makes no version and isn't logged; the backstory reads as before.
    body = read(troupe.player, agnes)
    assert body["version"] == 0 and body["text"] == "" and not body["written"]
    assert body["draft"]["text"] == "Born in 1890, in Dublin."
    log = troupe.player.client.get(f"/characters/{agnes}/log").json()
    assert not any("backstory" in e["message"] for e in log)

    # Submitting makes it the next version, and the draft goes.
    assert save(troupe.player, agnes, "Born in 1890, in Dublin.", 0).status_code == 200
    body = read(troupe.player, agnes)
    assert body["version"] == 1 and body["text"] == "Born in 1890, in Dublin."
    assert body["draft"] is None

    # A draft that says the same as the latest version is no draft.
    assert draft(troupe.player, agnes, "Born in 1890, in Cork.", 1).json()["draft"]["text"]
    assert draft(troupe.player, agnes, "Born in 1890, in Dublin.", 1).json()["draft"] is None
    assert read(troupe.player, agnes)["draft"] is None

    # Discarding it keeps the latest version.
    draft(troupe.player, agnes, "Something else.", 1)
    discarded = troupe.player.client.delete(f"/characters/{agnes}/backstory/draft")
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["draft"] is None
    assert discarded.json()["text"] == "Born in 1890, in Dublin."

    # It is capped like the backstory, and started from a version that exists.
    too_long = "a" * (backstories.MAX_LENGTH + 1)
    assert draft(troupe.player, agnes, too_long, 1).status_code == 422
    assert draft(troupe.player, agnes, "From the future.", 2).status_code == 422


def test_a_newer_version_never_loses_the_draft(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player)
    assert save(troupe.player, agnes, "Born in 1890.", 0).status_code == 200
    # On the phone, the player carries on writing.
    draft(troupe.player, agnes, "Born in 1890.\n\nShe fled to Chicago.", 1)
    # Meanwhile, on another device, they submit something else.
    assert save(troupe.player, agnes, "Born in 1900.", 1).status_code == 200

    # The draft is kept, behind the newer version, with how the two differ.
    body = read(troupe.player, agnes)
    assert body["text"] == "Born in 1900." and body["version"] == 2
    assert body["draft"]["text"] == "Born in 1890.\n\nShe fled to Chicago."
    assert body["draft"]["behind"] and body["draft"]["based_on"] == 1
    assert {(line["change"], line["text"]) for line in body["draft"]["differences"]} >= {
        ("removed", "Born in 1900."),
        ("added", "She fled to Chicago."),
    }
    # Submitting it as it stands is refused...
    assert save(troupe.player, agnes, body["draft"]["text"], 1).status_code == 409
    # ...until the player keeps theirs over the newer version.
    kept = draft(troupe.player, agnes, body["draft"]["text"], 2).json()
    assert kept["version"] == 2
    assert not kept["draft"]["behind"] and kept["draft"]["differences"] is None
    assert save(troupe.player, agnes, body["draft"]["text"], 2).status_code == 200
    assert read(troupe.player, agnes)["draft"] is None


def test_staff_never_read_the_draft(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player)
    save(troupe.player, agnes, "A secret past.", 0)
    draft(troupe.player, agnes, "A secret past, and a secret present.", 1)
    ask_home(troupe.player, agnes, troupe.id)
    for reader in (troupe.lead, troupe.assistant, troupe.custodian):
        body = read(reader, agnes)
        assert body["text"] == "A secret past." and body["draft"] is None
        assert (
            reader.client.put(
                f"/characters/{agnes}/backstory/draft", json={"text": "x", "based_on": 1}
            ).status_code
            == 403
        )


def test_only_its_player_and_home_troupe_storytellers_read_it(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    agnes = new_character(troupe, troupe.player)
    save(troupe.player, agnes, "A secret past.", 0)
    ask_home(troupe.player, agnes, troupe.id)
    decided = troupe.lead.client.post(
        f"/approvals/{approval_id(troupe.lead, troupe.id)}/approve", json={}
    )
    assert decided.status_code == 200, decided.text

    for reader in (troupe.lead, troupe.storyteller, troupe.assistant, troupe.custodian):
        assert read(reader, agnes)["text"] == "A secret past."
        standing = reader.client.get(f"/characters/{agnes}/backstory/standing").json()
        assert standing["read"] and not standing["write"]

    # Narrators and other players don't even see the character.
    for refused in (troupe.narrator, troupe.stranger):
        assert refused.client.get(f"/characters/{agnes}/backstory").status_code == 404
        assert refused.client.get(f"/characters/{agnes}/backstory/questions").status_code == 404

    # A visiting troupe's staff see the sheet, but not the backstory.
    visited = other_troupe(troupe, "Visited Court", troupe.stranger)
    joined = troupe.player.client.post(f"/characters/{agnes}/troupes", json={"troupe_id": visited})
    assert joined.status_code == 201, joined.text
    assert troupe.stranger.client.get(f"/characters/{agnes}/sheet").status_code == 200
    assert troupe.stranger.client.get(f"/characters/{agnes}/backstory").status_code == 403
    standing = troupe.stranger.client.get(f"/characters/{agnes}/backstory/standing").json()
    assert standing == {**standing, "read": False, "written": False, "length": 0}


def test_after_a_home_troupe_change_the_new_troupe_reads_it_and_the_old_does_not(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    agnes = new_character(troupe, troupe.player)
    save(troupe.player, agnes, "A secret past.", 0)
    ask_home(troupe.player, agnes, troupe.id)
    troupe.lead.client.post(f"/approvals/{approval_id(troupe.lead, troupe.id)}/approve", json={})

    new_lead = sign_up(client_for, "newlead")
    second = other_troupe(troupe, "Second Court", new_lead)
    backstory_optional(troupe.session, second)
    ask_home(troupe.player, agnes, second)
    # While it asks, both troupes' storytellers read it.
    assert read(new_lead, agnes)["text"] == "A secret past."
    assert read(troupe.lead, agnes)["text"] == "A secret past."
    decided = new_lead.client.post(f"/approvals/{approval_id(new_lead, second)}/approve", json={})
    assert decided.status_code == 200, decided.text
    assert read(new_lead, agnes)["text"] == "A secret past."
    assert troupe.lead.client.get(f"/characters/{agnes}/backstory").status_code in (403, 404)


def test_an_npcs_backstory_belongs_to_its_troupes_storytellers(troupe: Troupe) -> None:
    made = troupe.assistant.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Old Marrow"})
    assert made.status_code == 201, made.text
    npc = made.json()["id"]
    assert save(troupe.assistant, npc, "Older than the city.", 0).status_code == 200
    assert read(troupe.storyteller, npc)["text"] == "Older than the city."
    assert troupe.narrator.client.get(f"/characters/{npc}/backstory").status_code == 404


# --- the troupe's questions ----------------------------------------------------------------


def short_form(body: dict[str, Any]) -> dict[str, Any]:
    return next(s for s in body["sets"] if s["name"] == "Short Form")


def test_a_troupe_loads_the_template_and_edits_a_question(troupe: Troupe) -> None:
    settings(troupe, "wizard")
    loaded = troupe.lead.client.post(f"/troupes/{troupe.id}/backstory-template")
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    assert [(s["name"], len(s["questions"])) for s in body["sets"]] == [
        ("Short Form", 24),
        ("Long Form", 112),
    ]
    long_form = body["sets"][1]["questions"]
    assert long_form[43]["text"] == "How long has your character been in Lords of the Night?"
    pitch = short_form(body)["questions"][11]
    assert (pitch["text"], pitch["kind"]) == ("The Pitch", "heading")
    ancilla = short_form(body)["questions"][9]
    assert ancilla["condition"] == {"kind": "social_age", "ages": ["Ancilla"]}

    question = short_form(body)["questions"][5]
    changed = troupe.lead.client.patch(
        f"/backstory-questions/{question['id']}",
        json={"question": {**question, "text": "Who Embraced you, and why?", "title": "Sire"}},
    )
    assert changed.status_code == 200, changed.text
    edited = short_form(changed.json())["questions"][5]
    assert (edited["text"], edited["title"]) == ("Who Embraced you, and why?", "Sire")

    # Only storytellers keep them; assistant storytellers read them.
    assert (
        troupe.assistant.client.get(f"/troupes/{troupe.id}/backstory-settings").json()["can_edit"]
        is False
    )
    refused = troupe.assistant.client.patch(
        f"/backstory-questions/{question['id']}", json={"archived": True}
    )
    assert refused.status_code == 403


def answer(person: Person, character_id: str, question_id: str, text: str) -> Any:
    return person.client.put(
        f"/characters/{character_id}/backstory/answers/{question_id}", json={"answer": text}
    )


def test_under_free_text_only_the_questions_are_not_offered(troupe: Troupe) -> None:
    troupe.lead.client.post(f"/troupes/{troupe.id}/backstory-template")
    agnes = new_character(troupe, troupe.player)
    ask_home(troupe.player, agnes, troupe.id)
    asked = troupe.player.client.get(f"/characters/{agnes}/backstory/questions").json()
    assert asked["mode"] == "free" and asked["sets"] == []
    question = short_form(
        troupe.lead.client.get(f"/troupes/{troupe.id}/backstory-settings").json()
    )["questions"][0]
    assert answer(troupe.player, agnes, question["id"], "No").status_code == 422


def test_a_neonate_answers_the_short_form_and_gets_a_section_per_answer(troupe: Troupe) -> None:
    settings(troupe, "wizard")
    troupe.lead.client.post(f"/troupes/{troupe.id}/backstory-template")
    agnes = new_character(troupe, troupe.player)
    ask_home(troupe.player, agnes, troupe.id)

    asked = troupe.player.client.get(f"/characters/{agnes}/backstory/questions").json()
    assert asked["mode"] == "wizard"
    form = short_form(asked)
    texts = [q["text"] for q in form["questions"]]
    assert "What has your life been like since your Embrace?" in texts
    assert not any("Ancilla" in t or "Eldering" in t for t in texts)
    assert len(texts) == 24 - 5

    # Required questions come first.
    unanswered = troupe.player.client.post(
        f"/characters/{agnes}/backstory/sets/{form['id']}/build", json={}
    )
    assert unanswered.status_code == 422
    assert "Answer every question" in unanswered.json()["detail"]

    for q in form["questions"]:
        value = {
            "year": "1888",
            "scale": "2",
            "heading": "",
            "short": "A short answer",
            "long": f"All about {q['text'][:20]}",
        }[q["kind"]]
        if q["kind"] == "heading" or q["optional"]:
            continue
        saved = answer(troupe.player, agnes, q["id"], value)
        assert saved.status_code == 200, saved.text
    year = next(q for q in form["questions"] if q["kind"] == "year")
    assert answer(troupe.player, agnes, year["id"], "eighteen").status_code == 422
    elder = next(
        q
        for q in short_form(
            troupe.lead.client.get(f"/troupes/{troupe.id}/backstory-settings").json()
        )["questions"]
        if q["condition"] == {"kind": "social_age", "ages": ["Elder"]}
    )
    assert answer(troupe.player, agnes, elder["id"], "Long ago").status_code == 422

    built = troupe.player.client.post(
        f"/characters/{agnes}/backstory/sets/{form['id']}/build", json={}
    )
    assert built.status_code == 200, built.text
    text = built.json()["text"]
    answered = [q for q in form["questions"] if q["kind"] != "heading" and not q["optional"]]
    assert text.count("\n## ") + text.startswith("## ") == len(answered)
    assert "## Who was your Sire?\n\nA short answer" in text
    assert "## Action / Intrigue\n\nMore Action than Intrigue" in text
    assert "# The Pitch\n\n## What is your publicly accessible" in text
    # Sections follow the questions' order.
    assert text.index("Tell us about your mortal life") < text.index("Who was your Sire?")

    # Staff read the set as question and answer.
    staff = troupe.assistant.client.get(f"/characters/{agnes}/backstory/questions").json()
    sire = next(q for q in short_form(staff)["questions"] if q["text"] == "Who was your Sire?")
    assert sire["answer"] == "A short answer"


def test_building_again_keeps_what_the_player_wrote_outside_the_sections(
    troupe: Troupe,
) -> None:
    settings(troupe, "either")
    made = troupe.lead.client.post(f"/troupes/{troupe.id}/backstory-sets", json={"name": "Basics"})
    set_id = made.json()["sets"][0]["id"]
    for words in ("Where were you born?", "Who was your sire?"):
        added = troupe.lead.client.post(
            f"/backstory-sets/{set_id}/questions", json={"kind": "short", "text": words}
        )
        assert added.status_code == 201, added.text
    questions = added.json()["sets"][0]["questions"]
    agnes = new_character(troupe, troupe.player)
    ask_home(troupe.player, agnes, troupe.id)
    answer(troupe.player, agnes, questions[0]["id"], "Dublin")
    answer(troupe.player, agnes, questions[1]["id"], "Lord Ashe")
    built = troupe.player.client.post(f"/characters/{agnes}/backstory/sets/{set_id}/build", json={})
    assert built.status_code == 200, built.text
    body = built.json()

    # The player adds writing of their own before and after.
    mine = f"# Agnes\n\nMy own opening.\n\n{body['text']}\n## Later\n\nMy own ending.\n"
    assert save(troupe.player, agnes, mine, body["version"]).status_code == 200
    answer(troupe.player, agnes, questions[0]["id"], "Cork")
    again = troupe.player.client.post(f"/characters/{agnes}/backstory/sets/{set_id}/build", json={})
    assert again.status_code == 200, again.text
    text = again.json()["text"]
    assert text.startswith("# Agnes\n\nMy own opening.\n\n")
    assert text.endswith("## Later\n\nMy own ending.\n")
    assert "## Where were you born?\n\nCork" in text and "Dublin" not in text

    # Edits between the marks are replaced only when the player says so.
    edited = text.replace("Lord Ashe", "Lord Ashe, the bastard")
    assert save(troupe.player, agnes, edited, again.json()["version"]).status_code == 200
    assert read(troupe.player, agnes)["edited_sets"] == [set_id]
    asked = troupe.player.client.post(f"/characters/{agnes}/backstory/sets/{set_id}/build", json={})
    assert asked.status_code == 409
    replaced = troupe.player.client.post(
        f"/characters/{agnes}/backstory/sets/{set_id}/build", json={"replace_edits": True}
    )
    assert replaced.status_code == 200
    assert "the bastard" not in replaced.json()["text"]


def test_building_puts_the_sections_in_the_draft_too(troupe: Troupe) -> None:
    settings(troupe, "either")
    made = troupe.lead.client.post(f"/troupes/{troupe.id}/backstory-sets", json={"name": "Basics"})
    set_id = made.json()["sets"][0]["id"]
    added = troupe.lead.client.post(
        f"/backstory-sets/{set_id}/questions", json={"kind": "short", "text": "Where?"}
    )
    question = added.json()["sets"][0]["questions"][0]["id"]
    agnes = new_character(troupe, troupe.player)
    ask_home(troupe.player, agnes, troupe.id)
    answer(troupe.player, agnes, question, "Dublin")
    built = troupe.player.client.post(f"/characters/{agnes}/backstory/sets/{set_id}/build", json={})
    body = built.json()
    # The player is writing a draft around the sections when they answer again.
    mine = f"My own opening.\n\n{body['text']}"
    draft(troupe.player, agnes, mine, body["version"])
    answer(troupe.player, agnes, question, "Cork")
    again = troupe.player.client.post(f"/characters/{agnes}/backstory/sets/{set_id}/build", json={})
    assert again.status_code == 200, again.text
    after = again.json()
    assert "Cork" in after["text"] and "My own opening." not in after["text"]
    assert after["draft"]["text"].startswith("My own opening.\n\n<!-- questions:")
    assert "Cork" in after["draft"]["text"] and "Dublin" not in after["draft"]["text"]
    assert after["draft"]["based_on"] == after["version"] and not after["draft"]["behind"]

    # An edit between the marks in the draft is asked about before building replaces it.
    edited = after["draft"]["text"].replace("Cork", "Cork, by the sea")
    draft(troupe.player, agnes, edited, after["version"])
    assert read(troupe.player, agnes)["edited_sets"] == [set_id]
    asked = troupe.player.client.post(f"/characters/{agnes}/backstory/sets/{set_id}/build", json={})
    assert asked.status_code == 409


def test_archiving_a_question_keeps_its_answers(troupe: Troupe) -> None:
    settings(troupe, "wizard")
    made = troupe.lead.client.post(f"/troupes/{troupe.id}/backstory-sets", json={"name": "Basics"})
    set_id = made.json()["sets"][0]["id"]
    added = troupe.lead.client.post(
        f"/backstory-sets/{set_id}/questions",
        json={"kind": "choice", "text": "Calm or nervous?", "options": ["Calm", "Nervous"]},
    )
    question = added.json()["sets"][0]["questions"][0]
    agnes = new_character(troupe, troupe.player)
    ask_home(troupe.player, agnes, troupe.id)
    assert answer(troupe.player, agnes, question["id"], "Furious").status_code == 422
    assert answer(troupe.player, agnes, question["id"], "Calm").status_code == 200
    troupe.lead.client.patch(f"/backstory-questions/{question['id']}", json={"archived": True})

    assert troupe.player.client.get(f"/characters/{agnes}/backstory/questions").json()["sets"] == []
    staff = troupe.lead.client.get(f"/characters/{agnes}/backstory/questions").json()
    kept = staff["sets"][0]["questions"][0]
    assert (kept["answer"], kept["archived"]) == ("Calm", True)


def test_a_question_shows_only_when_its_condition_holds() -> None:
    neonate = backstories.Facts(
        age="Neonate",
        sect="Camarilla",
        traits=frozenset({("backgrounds", "alternate identity"), ("flaws", "dark secret")}),
    )
    assert backstories.shown(None, neonate)
    assert backstories.shown({"kind": "social_age", "ages": ["Neonate", "Ancilla"]}, neonate)
    assert not backstories.shown({"kind": "social_age", "ages": ["Elder"]}, neonate)
    assert backstories.shown({"kind": "sect", "sects": ["Camarilla"]}, neonate)
    assert not backstories.shown({"kind": "sect", "sects": ["Sabbat"]}, neonate)
    assert backstories.shown(
        {"kind": "trait", "category": "backgrounds", "name": "Alternate Identity"}, neonate
    )
    assert not backstories.shown(
        {"kind": "trait", "category": "merits", "name": "Alternate Identity"}, neonate
    )
    assert backstories.shown({"kind": "trait", "category": "flaws", "name": "Dark Secret"}, neonate)


def test_a_trait_condition_reads_the_sheet(troupe: Troupe, session: Session) -> None:
    settings(troupe, "wizard")
    made = troupe.lead.client.post(f"/troupes/{troupe.id}/backstory-sets", json={"name": "More"})
    set_id = made.json()["sets"][0]["id"]
    troupe.lead.client.post(
        f"/backstory-sets/{set_id}/questions",
        json={
            "kind": "long",
            "text": "What does an alt-ID check turn up?",
            "condition": {"kind": "trait", "category": "backgrounds", "name": "Herd"},
        },
    )
    agnes = new_character(troupe, troupe.player)
    ask_home(troupe.player, agnes, troupe.id)
    assert troupe.player.client.get(f"/characters/{agnes}/backstory/questions").json()["sets"] == []
    troupe.player.client.delete(f"/characters/{agnes}/home-troupe")
    bought = troupe.player.client.put(
        f"/characters/{agnes}/traits", json={"category": "backgrounds", "name": "Herd", "rating": 1}
    )
    assert bought.status_code == 200, bought.text
    ask_home(troupe.player, agnes, troupe.id)
    asked = troupe.player.client.get(f"/characters/{agnes}/backstory/questions").json()
    assert [q["text"] for q in asked["sets"][0]["questions"]] == [
        "What does an alt-ID check turn up?"
    ]
    assert session.scalar(select(BackstoryQuestion.condition).limit(1)) is not None


# --- approval ------------------------------------------------------------------------------


def test_staff_send_it_back_the_player_resubmits_and_staff_approve_it(troupe: Troupe) -> None:
    settings(troupe, "free", required=True)
    agnes = new_character(troupe, troupe.player)
    save(troupe.player, agnes, "## My sire\n\nHe was cruel.\n\n## Since\n\nI fled.", 0)
    ask_home(troupe.player, agnes, troupe.id)
    approval = approval_id(troupe.lead, troupe.id)

    # By default an approved backstory is needed before the character is accepted.
    refused = troupe.lead.client.post(f"/approvals/{approval}/approve", json={})
    assert refused.status_code == 409
    assert "backstory approved" in refused.json()["detail"]
    standing = troupe.lead.client.get(f"/characters/{agnes}/backstory/standing").json()
    assert standing["required"] and standing["review"] and not standing["approved"]

    # Narrators can't send it back or approve it.
    for path, body in (("feedback", {"body": "No"}), ("approve", {"version": 1})):
        assert troupe.narrator.client.post(
            f"/characters/{agnes}/backstory/{path}", json=body
        ).status_code in (403, 404)
        assert (
            troupe.player.client.post(
                f"/characters/{agnes}/backstory/{path}", json=body
            ).status_code
            == 403
        )

    sent = troupe.storyteller.client.post(
        f"/characters/{agnes}/backstory/feedback",
        json={"body": "More about the sire, please", "section": "My sire"},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["state"] == "returned"

    # The player is told, and sees the feedback.
    bell = troupe.player.client.get("/notifications").json()["items"]
    assert any("sent Agnes's backstory back" in n["summary"] for n in bell)
    body = read(troupe.player, agnes)
    assert body["state"] == "returned"
    assert [(e["kind"], e["section"], e["body"]) for e in body["thread"]] == [
        ("feedback", "My sire", "More about the sire, please")
    ]

    revised = "## My sire\n\nHe was cruel, and he taught me to hunt.\n\n## Since\n\nI fled."
    assert save(troupe.player, agnes, revised, body["version"]).status_code == 200
    resubmitted = troupe.player.client.post(
        f"/characters/{agnes}/backstory/resubmit", json={"note": "Added the hunting."}
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["state"] == "resubmitted"
    assert any(
        "revised and back with you" in n["summary"]
        for n in troupe.lead.client.get("/notifications").json()["items"]
    )

    # An assistant storyteller approves it, as it stands.
    staff_view = read(troupe.assistant, agnes)
    assert [e["kind"] for e in staff_view["thread"]] == ["feedback", "reply"]
    stale = troupe.assistant.client.post(
        f"/characters/{agnes}/backstory/approve", json={"version": 1}
    )
    assert stale.status_code == 409
    approved = troupe.assistant.client.post(
        f"/characters/{agnes}/backstory/approve", json={"version": staff_view["version"]}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved"] and approved.json()["approved_by_name"] == "assistant"

    accepted = troupe.lead.client.post(f"/approvals/{approval}/approve", json={})
    assert accepted.status_code == 200, accepted.text

    # Changed after acceptance: staff see what changed, and are told once.
    later = revised.replace("I fled.", "I fled to Chicago.")
    assert save(troupe.player, agnes, later, approved.json()["version"]).status_code == 200
    changed = read(troupe.lead, agnes)
    assert changed["changed_since_approval"] and not changed["approved"]
    assert {"change": "removed", "text": "I fled.", "count": 0} in changed["differences"]
    assert {"change": "added", "text": "I fled to Chicago.", "count": 0} in changed["differences"]
    assert read(troupe.player, agnes)["differences"] is None
    told = [
        n
        for n in troupe.lead.client.get("/notifications").json()["items"]
        if "changed since it was approved" in n["summary"]
    ]
    assert len(told) == 1
    save(troupe.player, agnes, later + "\n\nMore.", changed["version"])
    assert (
        len(
            [
                n
                for n in troupe.lead.client.get("/notifications").json()["items"]
                if "changed since it was approved" in n["summary"]
            ]
        )
        == 1
    )

    again = troupe.lead.client.post(
        f"/characters/{agnes}/backstory/approve", json={"version": changed["version"] + 1}
    )
    assert again.status_code == 200, again.text
    assert again.json()["approved"] and not again.json()["changed_since_approval"]

    actions = {
        e.action
        for e in troupe.session.scalars(
            select(AuditEvent).where(AuditEvent.character_id == uuid.UUID(agnes))
        )
    }
    assert {"backstory.returned", "backstory.resubmitted", "backstory.approved"} <= actions


def test_with_the_setting_off_a_character_is_accepted_without_one(troupe: Troupe) -> None:
    settings(troupe, "free", required=False)
    agnes = new_character(troupe, troupe.player)
    ask_home(troupe.player, agnes, troupe.id)
    decided = troupe.lead.client.post(
        f"/approvals/{approval_id(troupe.lead, troupe.id)}/approve", json={}
    )
    assert decided.status_code == 200, decided.text


def test_a_new_troupe_requires_an_approved_backstory(troupe: Troupe) -> None:
    second = other_troupe(troupe, "Fresh Court", troupe.stranger)
    found = troupe.stranger.client.get(f"/troupes/{second}/backstory-settings").json()
    assert (found["mode"], found["required"], found["sets"]) == ("free", True, [])


def test_an_empty_backstory_cannot_be_approved(troupe: Troupe) -> None:
    settings(troupe, "free", required=True)
    agnes = new_character(troupe, troupe.player)
    ask_home(troupe.player, agnes, troupe.id)
    refused = troupe.lead.client.post(f"/characters/{agnes}/backstory/approve", json={"version": 0})
    assert refused.status_code == 409


def test_differences_show_changed_lines_with_a_little_context() -> None:
    old = "\n".join(f"line {n}" for n in range(1, 21))
    new = old.replace("line 10", "line ten")
    lines = backstories.differences(old, new)
    assert [(line.change, line.text, line.count) for line in lines] == [
        ("skipped", "", 7),
        ("same", "line 8", 0),
        ("same", "line 9", 0),
        ("removed", "line 10", 0),
        ("added", "line ten", 0),
        ("same", "line 11", 0),
        ("same", "line 12", 0),
        ("skipped", "", 8),
    ]

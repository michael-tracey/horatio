"""A troupe's named scenes, kept on the server: listed for its running staff,
pinned in by any of them, renamed and removed by their maker or the lead
storyteller (issue #231)."""

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from horatio.api.scenes import pin_at_end
from horatio.models import Character, Scene, SceneCharacter, User
from horatio.models import Troupe as TroupeRecord
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_play import send, tap, view
from tests.test_api_sheets import make_home_troupe_member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def npc(troupe: Troupe, name: str, troupe_id: str | None = None) -> str:
    made = troupe.storyteller.client.post(
        f"/troupes/{troupe_id or troupe.id}/npcs", json={"name": name}
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


def scenes(person: Person, troupe: Troupe, **params: Any) -> list[dict[str, Any]]:
    response = person.client.get(f"/troupes/{troupe.id}/scenes", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def new_scene(person: Person, troupe: Troupe, name: str, **body: Any) -> dict[str, Any]:
    response = person.client.post(f"/troupes/{troupe.id}/scenes", json={"name": name, **body})
    assert response.status_code == 201, response.text
    return response.json()


def logged(troupe: Troupe) -> list[str]:
    return [
        e["message"]
        for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()
        if e["action"].startswith("scene.")
    ]


def test_running_staff_make_and_list_scenes_mine_or_all(troupe: Troupe) -> None:
    ballroom = new_scene(troupe.storyteller, troupe, "  Elysium, ballroom ")
    assert ballroom["name"] == "Elysium, ballroom"
    assert ballroom["characters"] == []
    assert ballroom["mine"] and ballroom["can_change"]
    new_scene(troupe.assistant, troupe, "Warehouse ambush")

    everyone = scenes(troupe.storyteller, troupe)
    assert [(s["name"], s["created_by_name"], s["mine"]) for s in everyone] == [
        ("Warehouse ambush", "assistant", False),
        ("Elysium, ballroom", "storyteller", True),
    ]
    assert [s["name"] for s in scenes(troupe.storyteller, troupe, mine=True)] == [
        "Elysium, ballroom"
    ]
    assert scenes(troupe.lead, troupe, mine=True) == []
    # The lead may change anyone's; another storyteller only their own.
    assert [s["can_change"] for s in scenes(troupe.lead, troupe)] == [True, True]
    assert [s["can_change"] for s in scenes(troupe.storyteller, troupe)] == [False, True]
    assert logged(troupe) == [
        "assistant made the scene Warehouse ambush.",
        "storyteller made the scene Elysium, ballroom.",
    ]


def test_narrators_players_and_strangers_have_no_scenes(troupe: Troupe) -> None:
    scene = new_scene(troupe.storyteller, troupe, "Rooftop")
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert person.client.get(f"/troupes/{troupe.id}/scenes").status_code == 403
        assert person.client.get(f"/troupes/{troupe.id}/scenes/{scene['id']}").status_code == 403
        made = person.client.post(f"/troupes/{troupe.id}/scenes", json={"name": "Mine"})
        assert made.status_code == 403
    # The custodian can, in any troupe.
    assert len(scenes(troupe.custodian, troupe)) == 1


def test_a_scene_needs_a_name_of_at_most_80_characters(troupe: Troupe) -> None:
    for name in ("", "   ", "x" * 81):
        made = troupe.lead.client.post(f"/troupes/{troupe.id}/scenes", json={"name": name})
        assert made.status_code == 422, name
    assert new_scene(troupe.lead, troupe, "x" * 80)["name"] == "x" * 80


def test_the_maker_or_the_lead_rename_and_remove(troupe: Troupe) -> None:
    scene = new_scene(troupe.storyteller, troupe, "Rooftop")
    url = f"/troupes/{troupe.id}/scenes/{scene['id']}"

    # Another storyteller and an assistant may open it, but not change it.
    for other in (troupe.assistant, troupe.narrator):
        assert other.client.patch(url, json={"name": "Mine now"}).status_code == 403
        assert other.client.delete(url).status_code == 403

    renamed = troupe.storyteller.client.patch(url, json={"name": "Rooftop chase"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Rooftop chase"
    by_lead = troupe.lead.client.patch(url, json={"name": "The rooftop"})
    assert by_lead.json()["name"] == "The rooftop"

    assert troupe.lead.client.delete(url).status_code == 204
    assert troupe.storyteller.client.get(url).status_code == 404
    assert scenes(troupe.storyteller, troupe) == []
    assert logged(troupe) == [
        "lead removed the scene The rooftop.",
        "lead renamed the scene Rooftop chase to The rooftop.",
        "storyteller renamed the scene Rooftop to Rooftop chase.",
        "storyteller made the scene Rooftop.",
    ]

    # Their own, an assistant changes too.
    own = new_scene(troupe.assistant, troupe, "Sewers")
    own_url = f"/troupes/{troupe.id}/scenes/{own['id']}"
    assert troupe.assistant.client.patch(own_url, json={"name": "Sewers"}).status_code == 200
    assert troupe.assistant.client.delete(own_url).status_code == 204


def test_any_running_staff_pin_and_unpin_in_order(troupe: Troupe, session: Session) -> None:
    lucien, mara = npc(troupe, "Lucien"), npc(troupe, "Mara")
    agnes = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, agnes)
    scene = new_scene(troupe.storyteller, troupe, "Ballroom")
    url = f"/troupes/{troupe.id}/scenes/{scene['id']}"

    assert troupe.storyteller.client.put(f"{url}/characters/{mara}").status_code == 200
    # Another storyteller's scene: an assistant pins in it too, and twice is once.
    pinned = troupe.assistant.client.put(f"{url}/characters/{lucien}")
    assert pinned.json()["characters"] == [mara, lucien]
    troupe.assistant.client.put(f"{url}/characters/{lucien}")
    troupe.assistant.client.put(f"{url}/characters/{agnes}")
    assert troupe.lead.client.get(url).json()["characters"] == [mara, lucien, agnes]
    assert scenes(troupe.lead, troupe)[0]["count"] == 3

    unpinned = troupe.lead.client.delete(f"{url}/characters/{mara}")
    assert unpinned.json()["characters"] == [lucien, agnes]
    assert troupe.narrator.client.put(f"{url}/characters/{mara}").status_code == 403


def test_two_pins_at_once_take_places_one_after_the_other(engine: Engine) -> None:
    # Two requests at once, each in its own transaction (issue #407): the second
    # waits for the first to be saved, then goes after it.
    tag = uuid.uuid4().hex[:8]
    with Session(engine) as db:
        lead = User(email=f"pins-{tag}@example.com", display_name="Pins", handle=f"pins{tag}")
        db.add(lead)
        db.flush()
        court = TroupeRecord(name=f"Pins {tag}", lead_user_id=lead.id)
        db.add(court)
        db.flush()
        alder, brant = (
            Character(player_id=lead.id, splat="vampire", name=n) for n in ("Alder", "Brant")
        )
        scene = Scene(troupe_id=court.id, name="Ball", created_by_id=lead.id)
        db.add_all([alder, brant, scene])
        db.commit()
        ids = scene.id, alder.id, brant.id, court.id, lead.id
    scene_id, alder_id, brant_id, court_id, lead_id = ids
    first = Session(engine)
    try:
        pin_at_end(first, scene_id, alder_id)

        def second() -> None:
            with Session(engine) as db:
                pin_at_end(db, scene_id, brant_id)
                db.commit()

        waiting = threading.Thread(target=second)
        waiting.start()
        waiting.join(0.5)
        assert waiting.is_alive(), "the second pin went ahead before the first was saved"
        first.commit()
        waiting.join(10)
        with Session(engine) as db:
            places = db.execute(
                select(SceneCharacter.character_id, SceneCharacter.position)
                .where(SceneCharacter.scene_id == scene_id)
                .order_by(SceneCharacter.position)
            ).all()
        assert [tuple(p) for p in places] == [(alder_id, 0), (brant_id, 1)]
    finally:
        first.close()
        with Session(engine) as db:
            db.execute(delete(Scene).where(Scene.id == scene_id))
            db.execute(delete(Character).where(Character.id.in_([alder_id, brant_id])))
            db.execute(delete(TroupeRecord).where(TroupeRecord.id == court_id))
            db.execute(delete(User).where(User.id == lead_id))
            db.commit()


def test_only_the_troupes_own_characters_are_pinned(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    made = troupe.custodian.client.post(
        "/troupes", json={"name": "The Other Court", "lead_handle": troupe.storyteller.handle}
    )
    elsewhere = npc(troupe, "Stranger", made.json()["id"])
    # A PC in no troupe at all.
    loner = new_character(troupe, troupe.player, "Loner")
    lucien = npc(troupe, "Lucien")
    scene = new_scene(troupe.storyteller, troupe, "Ballroom")
    url = f"/troupes/{troupe.id}/scenes/{scene['id']}"

    for other in (elsewhere, loner):
        assert troupe.storyteller.client.put(f"{url}/characters/{other}").status_code == 404
    # Making a scene with characters, as the device's old scene does, leaves them out.
    imported = new_scene(
        troupe.storyteller, troupe, "My scene", characters=[lucien, elsewhere, lucien, loner]
    )
    assert imported["characters"] == [lucien]

    # Nor is another troupe's scene reached through this one.
    other_scene = troupe.storyteller.client.post(
        f"/troupes/{made.json()['id']}/scenes", json={"name": "Theirs"}
    ).json()
    reached = troupe.lead.client.get(f"/troupes/{troupe.id}/scenes/{other_scene['id']}")
    assert reached.status_code == 404


def test_a_stock_npc_is_pinned_with_its_rating(troupe: Troupe) -> None:
    made = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs",
        json={"name": "Ghoul guard", "npc_form": "stock", "stock": {"rating": 2}},
    )
    assert made.status_code == 201, made.text
    guard, lucien = made.json()["id"], npc(troupe, "Lucien")
    scene = new_scene(troupe.storyteller, troupe, "Gate", characters=[lucien, guard])

    assert scene["characters"] == [lucien, guard]
    assert scene["stock"] == [{"character_id": guard, "name": "Ghoul guard", "rating": 2}]


def test_removing_a_scene_leaves_its_characters_and_their_play(troupe: Troupe) -> None:
    lucien = npc(troupe, "Lucien")
    scene = new_scene(troupe.storyteller, troupe, "Ambush", characters=[lucien])
    send(troupe.storyteller, lucien, tap("blood", -2), tap("willpower", -1, at=1))
    before = view(troupe.storyteller, lucien)

    url = f"/troupes/{troupe.id}/scenes/{scene['id']}"
    assert troupe.storyteller.client.delete(url).status_code == 204

    after = view(troupe.storyteller, lucien)
    assert (after["blood"], after["willpower"], after["log"]) == (
        before["blood"],
        before["willpower"],
        before["log"],
    )
    roster = troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()
    assert lucien in [c["character_id"] for c in roster]


def test_the_lead_removes_scenes_not_used_since_a_date(troupe: Troupe, session: Session) -> None:
    old = new_scene(troupe.storyteller, troupe, "Last month")
    new_scene(troupe.assistant, troupe, "Tonight")
    session.get_one(Scene, old["id"]).last_used_at = datetime.now(UTC) - timedelta(days=40)
    session.flush()
    since = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    url = f"/troupes/{troupe.id}/scenes"
    assert troupe.storyteller.client.delete(url, params={"unused_since": since}).status_code == 403
    cleared = troupe.lead.client.delete(url, params={"unused_since": since})
    assert cleared.json() == {"removed": 1}
    assert [s["name"] for s in scenes(troupe.lead, troupe)] == ["Tonight"]
    assert logged(troupe)[0].startswith("lead removed the scenes not used since ")


def test_opening_a_scene_marks_it_used(troupe: Troupe, session: Session) -> None:
    first = new_scene(troupe.storyteller, troupe, "First")
    new_scene(troupe.storyteller, troupe, "Second")
    session.get_one(Scene, first["id"]).last_used_at = datetime.now(UTC) - timedelta(days=1)
    session.flush()
    assert [s["name"] for s in scenes(troupe.lead, troupe)] == ["Second", "First"]

    troupe.lead.client.get(f"/troupes/{troupe.id}/scenes/{first['id']}")
    assert [s["name"] for s in scenes(troupe.lead, troupe)] == ["First", "Second"]

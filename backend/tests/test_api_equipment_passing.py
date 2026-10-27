"""Players give equipment to each other in their home troupe, and discard it (issue
#282): at once, only between characters of the same home troupe, told to the
receiver's player and in both characters' logs; discarded items kept for staff to
restore; staff doing the same from the troupe's tab; and, from the Play View, taps
with Undo."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Character
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_downtimes import member_character
from tests.test_api_renames import character_log, other_troupe, summaries, troupe_log, visit
from tests.test_api_troupe_equipment import DAGGER, RIFLE, given, listed, path


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def second(client_for: Callable[[], TestClient]) -> Person:
    return sign_up(client_for, "second")


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    return member_character(troupe, troupe.player, "Agnes")


@pytest.fixture
def bram(troupe: Troupe, second: Person) -> str:
    return member_character(troupe, second, "Bram")


def npc(troupe: Troupe, name: str, title: str | None = None) -> str:
    made = troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": name})
    assert made.status_code == 201, made.text
    npc_id: str = made.json()["id"]
    if title:
        sect = {"category": "sect", "name": "Camarilla", "rating": None}
        assert troupe.storyteller.client.put(f"/characters/{npc_id}/npc/ratings", json=sect)
        titled = troupe.lead.client.put(
            f"/troupes/{troupe.id}/characters/{npc_id}/titles", json={"titles": [title]}
        )
        assert titled.status_code == 200, titled.text
    return npc_id


def moved_home(troupe: Troupe, character_id: str, troupe_id: str) -> None:
    character = troupe.session.get_one(Character, uuid.UUID(character_id))
    character.home_troupe_id = uuid.UUID(troupe_id)
    troupe.session.flush()


def equipment_of(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/equipment")
    assert response.status_code == 200, response.text
    return response.json()


def names(person: Person, character_id: str) -> list[str]:
    return [i["name"] for i in equipment_of(person, character_id)["items"]]


def give_to(person: Person, holder: str, item: dict[str, Any], to: str, note: str = "") -> Any:
    return person.client.post(
        f"/characters/{holder}/equipment/{item['id']}/give",
        json={"to_character_id": to, "note": note},
    )


def discard(person: Person, holder: str, item: dict[str, Any], note: str = "") -> Any:
    return person.client.post(
        f"/characters/{holder}/equipment/{item['id']}/discard", json={"note": note}
    )


def history(troupe: Troupe, item: dict[str, Any]) -> list[tuple[str, str]]:
    response = troupe.storyteller.client.get(f"{path(troupe)}/{item['id']}")
    assert response.status_code == 200, response.text
    return [(e["summary"], e["reason"]) for e in response.json()["history"]]


def test_a_player_gives_the_silver_dagger_to_another_character_of_the_home_troupe(
    troupe: Troupe, second: Person, agnes: str, bram: str
) -> None:
    dagger = given(troupe, agnes, **DAGGER)

    response = give_to(troupe.player, agnes, dagger, bram)
    assert response.status_code == 200, response.text
    assert response.json()["character_name"] == "Bram"

    # It moves at once: Bram's player sees it, and Agnes holds it no more.
    assert names(second, bram) == ["Silver Dagger"]
    assert names(troupe.player, agnes) == []
    assert "player gave Bram Silver Dagger, from Agnes." in summaries(second)
    # The troupe's tab shows the new holder, and the item keeps its history.
    assert [(i["name"], i["character_name"]) for i in listed(troupe)] == [("Silver Dagger", "Bram")]
    assert history(troupe, dagger) == [
        ("Given to Agnes by Lords of the Night", ""),
        ("Given by Agnes to Bram", ""),
    ]
    # Both characters' logs say so; the troupe's log once.
    assert character_log(troupe.player, agnes)[0] == "player gave Agnes's Silver Dagger to Bram."
    assert character_log(second, bram)[0] == "player gave Bram (second) Silver Dagger, from Agnes."
    log = troupe_log(troupe.lead, troupe.id)
    assert log[0] == "player gave Agnes's Silver Dagger to Bram."
    assert not any("from Agnes" in line for line in log)

    # Bram's player can give it back; Agnes's no longer can.
    assert give_to(troupe.player, bram, dagger, agnes).status_code == 404
    assert give_to(second, bram, dagger, agnes, "Thanks").status_code == 200
    assert names(troupe.player, agnes) == ["Silver Dagger"]
    assert "second gave Agnes Silver Dagger, from Bram (Thanks)." in summaries(troupe.player)


def test_the_receivers_are_the_home_troupes_pcs_and_its_titled_npcs(
    troupe: Troupe, agnes: str, bram: str
) -> None:
    npc(troupe, "Gaspard")
    prince = npc(troupe, "Lucien", "Prince")

    mine = equipment_of(troupe.player, agnes)
    assert mine["can_pass"]
    assert [(r["name"], r["kind"], r["player_name"], r["title"]) for r in mine["receivers"]] == [
        ("Bram", "pc", "second", ""),
        ("Lucien", "npc", None, "Prince"),
    ]
    # Staff can give to any home character, the NPCs without a title too.
    staff = equipment_of(troupe.storyteller, agnes)
    assert [r["name"] for r in staff["receivers"]] == ["Bram", "Gaspard", "Lucien"]
    # A narrator sees no sheets; the stranger nothing.
    assert troupe.narrator.client.get(f"/characters/{agnes}/equipment").status_code == 404

    # A player can give to the Prince, not to an NPC without a title.
    dagger = given(troupe, agnes, **DAGGER)
    rifle = given(troupe, agnes, **RIFLE)
    gaspard = staff["receivers"][1]["id"]
    refused = give_to(troupe.player, agnes, dagger, gaspard)
    assert refused.status_code == 422
    assert "PCs, and to the NPCs holding a title there" in refused.json()["detail"]
    assert give_to(troupe.player, agnes, dagger, prince).status_code == 200
    # Staff can, from the troupe's tab, as they move any item between home characters.
    assert give_to(troupe.storyteller, agnes, rifle, gaspard, "Seized").status_code == 200
    assert "storyteller gave Agnes's Hunting rifle to Gaspard (Seized)." in summaries(troupe.player)


def test_giving_to_a_character_of_another_home_troupe_is_refused(
    troupe: Troupe, second: Person, agnes: str
) -> None:
    elsewhere = other_troupe(troupe)
    # Vera's home is elsewhere, and she visits Lords of the Night.
    vera = member_character(troupe, second, "Vera")
    moved_home(troupe, vera, elsewhere)
    visit(second, vera, troupe.id)
    dagger = given(troupe, agnes, **DAGGER)

    refused = give_to(troupe.player, agnes, dagger, vera)
    assert refused.status_code == 422
    assert refused.json()["detail"] == (
        "That character isn't one of Lords of the Night's: equipment passes only between"
        " characters of the same home troupe."
    )
    # Not even the troupe's staff.
    assert give_to(troupe.lead, agnes, dagger, vera).status_code == 422
    assert names(troupe.player, agnes) == ["Silver Dagger"]
    # Nor a character that doesn't exist.
    assert give_to(troupe.player, agnes, dagger, str(uuid.uuid4())).status_code == 422


def test_only_the_holders_player_or_staff_give_or_discard_it(
    troupe: Troupe, second: Person, agnes: str, bram: str
) -> None:
    dagger = given(troupe, agnes, **DAGGER)
    # Bram's player can't take it from Agnes: they don't even see her sheet.
    assert give_to(second, agnes, dagger, bram).status_code == 404
    assert discard(second, agnes, dagger).status_code == 404
    # Nor through Bram, which doesn't hold it.
    assert give_to(second, bram, dagger, bram).status_code == 404
    # A visiting troupe's staff see the sheet, but aren't its home troupe's.
    elsewhere = other_troupe(troupe)
    visit(troupe.player, agnes, elsewhere)
    refused = discard(troupe.stranger, agnes, dagger)
    assert refused.status_code == 403
    assert refused.json()["detail"] == (
        "Only Agnes's player, or its home troupe's staff, give or discard its equipment."
    )
    assert not equipment_of(troupe.stranger, agnes)["can_pass"]
    assert equipment_of(troupe.stranger, agnes)["receivers"] == []


def test_a_discarded_item_is_kept_for_staff_who_restore_it(troupe: Troupe, agnes: str) -> None:
    dagger = given(troupe, agnes, **DAGGER)

    response = discard(troupe.player, agnes, dagger, "  lost in the river ")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "discarded"
    assert names(troupe.player, agnes) == []
    assert listed(troupe) == []
    # Under Discarded on the troupe's tab, with the note and who did it.
    (kept,) = listed(troupe, status="discarded")
    assert kept["character_name"] == "Agnes"
    assert kept["discarded"]["note"] == "lost in the river"
    assert kept["discarded"]["by_name"] == "player"
    assert not kept["can_change"]
    assert history(troupe, dagger)[-1] == ("Discarded by Agnes", "lost in the river")
    assert character_log(troupe.player, agnes)[0] == (
        "player discarded Agnes's Silver Dagger (lost in the river)."
    )
    # Not twice, and not given on.
    assert discard(troupe.player, agnes, dagger).status_code == 409

    # The lead restores it: back with Agnes, and her player is told.
    restored = troupe.lead.client.post(f"{path(troupe)}/{dagger['id']}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["history"][-1]["summary"] == "Restored to Agnes"
    assert names(troupe.player, agnes) == ["Silver Dagger"]
    assert "lead gave Agnes Silver Dagger back." in summaries(troupe.player)
    assert troupe.lead.client.post(f"{path(troupe)}/{dagger['id']}/restore").status_code == 409
    # Only staff restore.
    assert troupe.player.client.post(f"{path(troupe)}/{dagger['id']}/restore").status_code == 403

    # Staff discard it too, from the troupe's tab, and the player is told.
    assert discard(troupe.assistant, agnes, dagger, "Confiscated").status_code == 200
    assert "assistant discarded Agnes's Silver Dagger: Confiscated" in summaries(troupe.player)


# --- the Play View --------------------------------------------------------------------------


def tap(**fields: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "happened_at": datetime.now(UTC).isoformat(),
        **fields,
    }


def send(person: Person, character_id: str, *taps: dict[str, Any]) -> list[dict[str, Any]]:
    response = person.client.post(f"/characters/{character_id}/play/taps", json={"taps": taps})
    assert response.status_code == 200, response.text
    return response.json()["log"]


def item_tap(item: dict[str, Any], to: str | None = None, note: str = "") -> dict[str, Any]:
    equipment = {"to_character_id": to, "item_name": item["name"]} if to else None
    return tap(
        kind="change", tracker=f"item:{item['id']}", amount=-1, note=note, equipment=equipment
    )


def test_a_give_from_the_play_view_is_a_tap_with_undo(
    troupe: Troupe, second: Person, agnes: str, bram: str
) -> None:
    dagger = given(troupe, agnes, **DAGGER)
    gave = item_tap(dagger, bram)

    log = send(troupe.player, agnes, gave)
    assert log[0]["text"] == "Gave Silver Dagger to Bram"
    assert names(second, bram) == ["Silver Dagger"]
    assert "player gave Bram Silver Dagger, from Agnes." in summaries(second)

    log = send(troupe.player, agnes, tap(kind="undo", undoes=gave["id"]))
    assert log[0]["text"] == "Undid: Gave Silver Dagger to Bram"
    assert names(troupe.player, agnes) == ["Silver Dagger"]
    assert names(second, bram) == []
    assert history(troupe, dagger)[-1] == ("Back from Bram to Agnes", "undone in the Play View")
    assert "player gave Bram's Silver Dagger to Agnes (undone in the Play View)." in summaries(
        second
    )

    # Once Bram has given it on, Undo leaves it where it is.
    again = item_tap(dagger, bram)
    send(troupe.player, agnes, again)
    assert give_to(second, bram, dagger, agnes).status_code == 200
    assert give_to(troupe.player, agnes, dagger, bram).status_code == 200
    log = send(troupe.player, agnes, tap(kind="undo", undoes=again["id"]))
    assert log[0]["text"] == (
        "Undid: Gave Silver Dagger to Bram. Silver Dagger has moved on since, so it stays"
        " where it is."
    )
    assert names(second, bram) == ["Silver Dagger"]


def test_a_discard_from_the_play_view_is_undone_and_a_refused_tap_changes_nothing(
    troupe: Troupe, second: Person, agnes: str
) -> None:
    dagger = given(troupe, agnes, **DAGGER)
    rifle = given(troupe, agnes, **RIFLE)
    threw = item_tap(dagger, note="Into the river")

    log = send(troupe.player, agnes, threw)
    assert (log[0]["text"], log[0]["note"]) == ("Discarded Silver Dagger", "Into the river")
    assert names(troupe.player, agnes) == ["Hunting rifle"]
    send(troupe.player, agnes, tap(kind="undo", undoes=threw["id"]))
    assert names(troupe.player, agnes) == ["Hunting rifle", "Silver Dagger"]
    assert history(troupe, dagger)[-1] == ("Back with Agnes", "undone in the Play View")

    # To a character of another home troupe: the tap is kept, refused, and changes nothing.
    elsewhere = other_troupe(troupe)
    vera = member_character(troupe, second, "Vera")
    moved_home(troupe, vera, elsewhere)
    log = send(troupe.player, agnes, item_tap(rifle, vera))
    assert log[0]["text"] == (
        "Couldn't give Hunting rifle to Vera: That character isn't one of Lords of the"
        " Night's: equipment passes only between characters of the same home troupe."
    )
    assert names(troupe.player, agnes) == ["Hunting rifle", "Silver Dagger"]

    # Only −1 is a give or discard.
    bad = tap(kind="change", tracker=f"item:{rifle['id']}", amount=1)
    response = troupe.player.client.post(f"/characters/{agnes}/play/taps", json={"taps": [bad]})
    assert response.status_code == 422

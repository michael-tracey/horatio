"""Finding a troupe's characters by what is on their sheets (issue #36)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character, sign_up


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def buy(person: Person, character_id: str, category: str, name: str, rating: int | None) -> None:
    bought = person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating},
    )
    assert bought.status_code == 200, bought.text


def member(troupe: Troupe, player: Person, name: str, clan: str, occult: int = 0) -> str:
    character_id = new_character(troupe, player, name, clan=clan)
    if occult:
        buy(player, character_id, "skills", "Occult", occult)
    joined = player.client.post(
        f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id}
    )
    assert joined.status_code == 201, joined.text
    return character_id


def make_home(troupe: Troupe, player: Person, character_id: str) -> None:
    asked = player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert asked.status_code == 201, asked.text
    approved = troupe.lead.client.post(f"/approvals/{asked.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text


@pytest.fixture
def court(troupe: Troupe, client_for: Callable[[], TestClient]) -> dict[str, Any]:
    """Agnes (Brujah, Occult 2, home), Mara (Tremere, Occult 4, visiting, another
    player's) and Nell (Giovanni, no Occult, visiting)."""
    other = sign_up(client_for, "other")
    agnes = member(troupe, troupe.player, "Agnes", "Brujah", occult=2)
    mara = member(troupe, other, "Mara", "Tremere", occult=4)
    nell = member(troupe, troupe.player, "Nell", "Giovanni")
    make_home(troupe, troupe.player, agnes)
    return {"agnes": agnes, "mara": mara, "nell": nell, "other": other}


def find(
    troupe: Troupe, *items: dict[str, Any], match: str = "all", who: Person | None = None
) -> Any:
    response = (who or troupe.lead).client.post(
        f"/troupes/{troupe.id}/characters/search", json={"match": match, "items": list(items)}
    )
    return response


def names(troupe: Troupe, *items: dict[str, Any], match: str = "all") -> list[str]:
    response = find(troupe, *items, match=match)
    assert response.status_code == 200, response.text
    roster = {
        e["character_id"]: e["character_name"]
        for e in troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()
    }
    return [roster[m["character_id"]] for m in response.json()]


OCCULT_BELOW_3 = {"what": "trait", "which": "skills/Occult", "op": "lt", "value": 3}


def test_a_missing_trait_counts_as_zero(troupe: Troupe, court: dict[str, Any]) -> None:
    response = find(troupe, OCCULT_BELOW_3)

    assert response.status_code == 200, response.text
    found = {m["character_id"]: m["values"] for m in response.json()}
    assert found == {
        court["agnes"]: {"trait:skills/Occult": 2},
        court["nell"]: {"trait:skills/Occult": 0},
    }


def test_compound_filters(troupe: Troupe, court: dict[str, Any]) -> None:
    either_clan = {
        "match": "any",
        "items": [
            {"what": "choice", "which": "clan", "op": "is", "value": ["Tremere"]},
            {"what": "choice", "which": "clan", "op": "family", "value": ["Giovanni"]},
        ],
    }

    assert names(troupe, either_clan) == ["Mara", "Nell"]
    assert names(troupe, OCCULT_BELOW_3, either_clan) == ["Nell"]
    assert names(troupe, OCCULT_BELOW_3, either_clan, match="any") == ["Agnes", "Mara", "Nell"]
    not_brujah = {"what": "choice", "which": "clan", "op": "is_not", "value": ["Brujah"]}
    assert names(troupe, not_brujah) == ["Mara", "Nell"]


def test_statuses(troupe: Troupe, court: dict[str, Any]) -> None:
    def status(value: str, op: str = "is") -> list[str]:
        return names(troupe, {"what": "status", "op": op, "value": value})

    assert status("home") == ["Agnes"]
    assert status("visiting") == ["Mara", "Nell"]
    assert status("pc") == ["Agnes", "Mara", "Nell"]
    assert status("active") == ["Agnes", "Mara", "Nell"]
    troupe.player.client.post(f"/characters/{court['nell']}/retire")
    assert status("retired") == ["Nell"]
    assert status("retired", "is_not") == ["Agnes", "Mara"]
    court["other"].client.post(
        f"/characters/{court['mara']}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert status("waiting") == ["Mara"]
    assert status("approvals") == ["Mara"]
    troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Prince"})
    assert status("npc") == ["Prince"]


def test_titles_players_experience_and_counts(troupe: Troupe, court: dict[str, Any]) -> None:
    troupe.assistant.client.put(
        f"/troupes/{troupe.id}/characters/{court['agnes']}/titles", json={"titles": ["Soldier"]}
    )
    buy(court["other"], court["mara"], "merits", "Acute Sense", 1)

    assert names(troupe, {"what": "title", "op": "has", "value": "Soldier"}) == ["Agnes"]
    assert names(troupe, {"what": "title", "op": "has"}) == ["Agnes"]
    assert names(troupe, {"what": "title", "op": "lacks"}) == ["Mara", "Nell"]
    other = court["other"].id
    assert names(troupe, {"what": "player", "op": "is", "value": other}) == ["Mara"]
    assert names(troupe, {"what": "player", "op": "is_not", "value": other}) == ["Agnes", "Nell"]
    spent_more = {"what": "xp", "which": "unspent", "op": "lt", "value": 30}
    assert names(troupe, spent_more) == ["Agnes", "Mara"]
    merits = {"what": "count", "which": "merits", "op": "gte", "value": 1}
    assert names(troupe, merits) == ["Mara"]
    acute = {"what": "trait", "which": "merits/Acute Sense", "op": "has"}
    assert names(troupe, acute) == ["Mara"]
    assert names(troupe, {**acute, "op": "lacks"}) == ["Agnes", "Nell"]


@pytest.mark.parametrize(
    ("item", "refusal"),
    [
        ({"what": "trait", "which": "skills/Juggling", "op": "lt", "value": 3}, "no trait"),
        ({"what": "trait", "which": "skills/Occult", "op": "is", "value": 3}, "does not work"),
        ({"what": "trait", "which": "skills/Occult", "op": "lt"}, "Give a number"),
        ({"what": "status", "op": "is", "value": "sleepy"}, "no status"),
        ({"what": "choice", "which": "kith", "op": "is", "value": ["x"]}, "no category"),
        ({"what": "colour", "op": "is", "value": "red"}, "no filter"),
    ],
)
def test_nonsense_is_refused(
    troupe: Troupe, court: dict[str, Any], item: dict[str, Any], refusal: str
) -> None:
    response = find(troupe, item)

    assert response.status_code == 422
    assert refusal in response.json()["detail"]


def test_only_storytellers_and_assistants_search_sheets(
    troupe: Troupe, court: dict[str, Any]
) -> None:
    assert find(troupe, OCCULT_BELOW_3, who=troupe.assistant).status_code == 200
    for person in (troupe.narrator, troupe.player):
        assert find(troupe, OCCULT_BELOW_3, who=person).status_code == 403

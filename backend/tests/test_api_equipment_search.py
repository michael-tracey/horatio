"""Equipment search (issue #284): an equipment condition in the troupe's Characters
filter ("who has a staking weapon?"), and item search on its Equipment tab ("where
did the rifle go?"), for its storytellers and assistant storytellers only."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import EquipmentItem
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_character_search import find, member
from tests.test_api_downtimes import member_character
from tests.test_api_equipment_passing import discard, npc
from tests.test_api_troupe_equipment import DAGGER, LEGEND, RIFLE, given, path

STAKE = {
    "name": "Wooden Stake",
    "kind": "melee",
    "grade": "standard",
    "qualities": [{"name": "Concealable"}, {"name": "Staking"}],
}
VEST = {"name": "Kevlar vest", "kind": "protective", "grade": "standard", "qualities": []}
PISTOL = {
    "name": "Hunter's pistol",
    "kind": "ranged",
    "grade": "cheap",
    "qualities": [{"name": "Silver Ammunition"}],
}
LAPTOP = {
    "name": "Laptop",
    "kind": "miscellaneous",
    "grade": "standard",
    "qualities": [{"name": "Customized", "detail": "hacking"}],
}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def camarilla(person: Person, character_id: str) -> None:
    chosen = person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "sect", "name": "Camarilla", "rating": None},
    )
    assert chosen.status_code == 200, chosen.text


@pytest.fixture
def court(troupe: Troupe, client_for: Callable[[], TestClient]) -> dict[str, Any]:
    """Agnes (Camarilla) holds a stake and a silver dagger; Bram (no sect) a stake
    and a pistol with silver ammunition; Cora (Camarilla) a vest; the NPC Dov
    (Camarilla) nothing; Vera (Camarilla) only visits, holding her own home's stake."""
    other = sign_up(client_for, "other")
    agnes = member_character(troupe, troupe.player, "Agnes")
    bram = member_character(troupe, other, "Bram")
    cora = member_character(troupe, other, "Cora")
    for character_id, person in ((agnes, troupe.player), (cora, other)):
        camarilla(person, character_id)
    dov = npc(troupe, "Dov", title="Sheriff")
    vera = member(troupe, troupe.player, "Vera", "Ventrue")
    camarilla(troupe.player, vera)
    items = {
        "stake": given(troupe, agnes, **STAKE),
        "dagger": given(troupe, agnes, **DAGGER),
        "bram_stake": given(troupe, bram, **STAKE),
        "pistol": given(troupe, bram, **PISTOL),
        "vest": given(troupe, cora, **VEST),
    }
    return {
        "agnes": agnes,
        "bram": bram,
        "cora": cora,
        "dov": dov,
        "vera": vera,
        "other": other,
        **items,
    }


def matched(troupe: Troupe, *items: dict[str, Any], match: str = "all") -> dict[str, list[str]]:
    """Each character matched, by name, with the items shown beside it."""
    response = find(troupe, *items, match=match)
    assert response.status_code == 200, response.text
    roster = {
        e["character_id"]: e["character_name"]
        for e in troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()
    }
    return {roster[m["character_id"]]: m["equipment"] for m in response.json()}


def equipment(op: str = "has", **value: Any) -> dict[str, Any]:
    return {"what": "equipment", "op": op, "value": value or None}


CAMARILLA = {"what": "choice", "which": "sect", "op": "is", "value": ["Camarilla"]}


def test_camarilla_characters_holding_a_staking_item(troupe: Troupe, court: dict[str, Any]) -> None:
    # Only Agnes is Camarilla with a stake, and only the stake shows; not Vera,
    # whose stake is her own home troupe's.
    assert matched(troupe, CAMARILLA, equipment(quality="Staking")) == {"Agnes": ["Wooden Stake"]}
    assert matched(troupe, equipment(quality="Staking")) == {
        "Agnes": ["Wooden Stake"],
        "Bram": ["Wooden Stake"],
    }


def test_lacking_protective_gear(troupe: Troupe, court: dict[str, Any]) -> None:
    # Home characters only, each with what it does hold.
    assert matched(troupe, equipment("lacks", kind="protective")) == {
        "Agnes": ["Silver Dagger", "Wooden Stake"],
        "Bram": ["Hunter's pistol", "Wooden Stake"],
        "Dov": [],
    }


def test_kind_quality_detail_name_and_special(troupe: Troupe, court: dict[str, Any]) -> None:
    given(troupe, court["cora"], **LAPTOP)
    given(troupe, court["cora"], **LEGEND)
    assert matched(troupe, equipment(kind="ranged", quality="Silver Ammunition")) == {
        "Bram": ["Hunter's pistol"]
    }
    assert matched(troupe, equipment(kind="melee", quality="Silver")) == {
        "Agnes": ["Silver Dagger"],
        "Cora": ["Blade of Saulot"],
    }
    assert matched(troupe, equipment(quality="Customized", detail="HACK")) == {"Cora": ["Laptop"]}
    assert matched(troupe, equipment(quality="Customized", detail="cooking")) == {}
    assert matched(troupe, equipment(name="stake")) == {
        "Agnes": ["Wooden Stake"],
        "Bram": ["Wooden Stake"],
    }
    assert matched(troupe, equipment(special=True)) == {"Cora": ["Blade of Saulot"]}
    # Nothing set is any item; "lacks" with nothing set, none.
    assert set(matched(troupe, equipment())) == {"Agnes", "Bram", "Cora"}
    assert matched(troupe, equipment("lacks")) == {"Dov": []}
    # With a "has" and a "lacks" the "has" picks what shows.
    assert matched(
        troupe, equipment(kind="melee"), equipment("lacks", kind="ranged"), match="all"
    ) == {"Agnes": ["Silver Dagger", "Wooden Stake"], "Cora": ["Blade of Saulot"]}


def test_only_held_items_count_and_retired_characters_with_their_status(
    troupe: Troupe, court: dict[str, Any]
) -> None:
    gone = discard(troupe.player, court["agnes"], court["stake"], "lost in the river")
    assert gone.status_code == 200, gone.text
    assert matched(troupe, equipment(quality="Staking")) == {"Bram": ["Wooden Stake"]}

    retired = court["other"].client.post(f"/characters/{court['bram']}/retire")
    assert retired.status_code == 200, retired.text
    active = {"what": "status", "op": "is", "value": "active"}
    assert matched(troupe, active, equipment(quality="Staking")) == {}
    assert matched(troupe, equipment(quality="Staking")) == {"Bram": ["Wooden Stake"]}


def test_a_character_condition(troupe: Troupe, court: dict[str, Any]) -> None:
    some = {"what": "character", "op": "is", "value": [court["agnes"], court["dov"]]}
    assert set(matched(troupe, some)) == {"Agnes", "Dov"}
    others = {**some, "op": "is_not"}
    assert set(matched(troupe, others)) == {"Bram", "Cora", "Vera"}


@pytest.mark.parametrize(
    ("value", "says"),
    [
        ({"kind": "laser"}, "There is no kind of equipment 'laser'."),
        ({"quality": "Sparkly"}, "There is no quality 'Sparkly'."),
        (
            {"kind": "protective", "quality": "Staking"},
            "There is no quality 'Staking' for protective.",
        ),
    ],
)
def test_nonsense_is_refused(
    troupe: Troupe, court: dict[str, Any], value: dict[str, Any], says: str
) -> None:
    response = find(troupe, equipment(**value))
    assert response.status_code == 422
    assert response.json()["detail"] == says
    wrong = find(troupe, {"what": "equipment", "op": "is", "value": None})
    assert wrong.status_code == 422
    unknown = find(troupe, {"what": "equipment", "op": "has", "value": {"colour": "red"}})
    assert unknown.status_code == 422


# --- the Equipment tab ------------------------------------------------------------------


def search(troupe: Troupe, who: Person | None = None, **params: Any) -> Any:
    response = (who or troupe.storyteller).client.get(path(troupe), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def found(troupe: Troupe, **params: Any) -> list[tuple[str, str]]:
    return [(i["name"], i["character_name"]) for i in search(troupe, **params)["items"]]


def test_searching_words_in_an_item(troupe: Troupe, court: dict[str, Any]) -> None:
    given(troupe, court["cora"], **LEGEND)
    given(troupe, court["cora"], **LAPTOP, staff_note="Bugged by the Nosferatu")
    given(troupe, court["dov"], **RIFLE, description="Engraved with a wolf")
    # A word in a special effect, in a quality's detail, the staff note, the
    # description and the name, whatever the case; every word must be there.
    assert found(troupe, q="heals") == []
    assert found(troupe, q="heal") == [("Blade of Saulot", "Cora")]
    assert found(troupe, q="blood normal") == [("Blade of Saulot", "Cora")]
    assert found(troupe, q="blood rifle") == []
    assert found(troupe, q="HACKING") == [("Laptop", "Cora")]
    assert found(troupe, q="nosferatu") == [("Laptop", "Cora")]
    assert found(troupe, q="wolf") == [("Hunting rifle", "Dov")]
    assert found(troupe, q="silver") == [
        ("Silver Dagger", "Agnes"),
        ("Hunter's pistol", "Bram"),
        ("Blade of Saulot", "Cora"),
    ]


def test_filters_and_sorting(troupe: Troupe, court: dict[str, Any], session: Session) -> None:
    def given_on(item: dict[str, Any], day: int) -> None:
        session.get_one(EquipmentItem, uuid.UUID(item["id"])).given_at = datetime(
            2026, 10, day, 20, tzinfo=UTC
        )
        session.flush()

    for item, day in (("stake", 1), ("dagger", 2), ("bram_stake", 3), ("pistol", 4), ("vest", 5)):
        given_on(court[item], day)
    by_lead = given(troupe, court["dov"], by=troupe.lead, **RIFLE)
    given_on(by_lead, 6)

    holders = [court["agnes"], court["cora"]]
    assert found(troupe, character_id=holders) == [
        ("Silver Dagger", "Agnes"),
        ("Wooden Stake", "Agnes"),
        ("Kevlar vest", "Cora"),
    ]
    assert found(troupe, kind="melee", quality="Staking") == [
        ("Wooden Stake", "Agnes"),
        ("Wooden Stake", "Bram"),
    ]
    assert found(troupe, quality="Staking", character_id=[court["bram"]]) == [
        ("Wooden Stake", "Bram")
    ]
    assert found(troupe, grade="cheap") == [("Hunter's pistol", "Bram")]
    lead = next(g["id"] for g in search(troupe)["givers"] if g["name"] == "lead")
    assert by_lead["given_by_name"] == "lead"
    assert found(troupe, given_by=lead) == [("Hunting rifle", "Dov")]
    between = {"given_after": "2026-10-02T00:00:00Z", "given_before": "2026-10-04T00:00:00Z"}
    assert found(troupe, **between) == [("Silver Dagger", "Agnes"), ("Wooden Stake", "Bram")]
    assert [n for n, _ in found(troupe, sort="date")] == [
        "Hunting rifle",
        "Kevlar vest",
        "Hunter's pistol",
        "Wooden Stake",
        "Silver Dagger",
        "Wooden Stake",
    ]
    assert found(troupe, sort="name")[:2] == [("Hunter's pistol", "Bram"), ("Hunting rifle", "Dov")]

    listed = search(troupe)
    assert [g["name"] for g in listed["givers"]] == ["lead", "storyteller"]
    assert listed["not_shown"] == {}


def test_discarded_items_and_their_history(troupe: Troupe, court: dict[str, Any]) -> None:
    gone = discard(troupe.player, court["agnes"], court["stake"], "lost in the river")
    assert gone.status_code == 200, gone.text

    assert ("Wooden Stake", "Agnes") not in found(troupe)
    assert search(troupe)["not_shown"] == {"discarded": 1}
    assert search(troupe, q="stake", status=["discarded"])["items"][0]["discarded"]["note"] == (
        "lost in the river"
    )
    both = search(troupe, q="stake", status=["held", "discarded"])
    assert [(i["character_name"], i["status"]) for i in both["items"]] == [
        ("Agnes", "discarded"),
        ("Bram", "held"),
    ]
    assert both["not_shown"] == {}
    item_id = both["items"][0]["id"]
    history = troupe.storyteller.client.get(f"{path(troupe)}/{item_id}").json()["history"]
    assert [e["summary"] for e in history] == [
        "Given to Agnes by Lords of the Night",
        "Discarded by Agnes",
    ]


def test_retired_characters_items_only_when_asked(troupe: Troupe, court: dict[str, Any]) -> None:
    retired = court["other"].client.post(f"/characters/{court['bram']}/retire")
    assert retired.status_code == 200, retired.text
    assert ("Hunter's pistol", "Bram") not in found(troupe)
    assert ("Hunter's pistol", "Bram") in found(troupe, retired=True)


def test_only_running_staff_search(troupe: Troupe, court: dict[str, Any]) -> None:
    filter_ = {"match": "all", "items": [equipment(quality="Staking")]}
    for who in (troupe.assistant, troupe.lead):
        assert search(troupe, who, q="stake")["items"]
        searched = who.client.post(f"/troupes/{troupe.id}/characters/search", json=filter_)
        assert searched.status_code == 200, searched.text
    for who in (troupe.player, troupe.narrator, troupe.stranger):
        refused = who.client.get(path(troupe), params={"q": "stake"})
        assert refused.status_code == 403, who
        refused = who.client.post(f"/troupes/{troupe.id}/characters/search", json=filter_)
        assert refused.status_code == 403, who

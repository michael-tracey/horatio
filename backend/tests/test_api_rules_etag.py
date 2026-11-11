"""Browsers keep the rules catalogue (issue #643): it, the rules browser and the
equipment rules come with a weak ETag of the rules' version, and asking again with it
gets 304 Not Modified, with no body, until the rules change."""

from collections.abc import Callable
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.api.etags import matches
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.store import sync_rule_set
from tests.api_helpers import Person, Troupe
from tests.test_api_sect_status import other_troupe

VAMPIRE = load_rule_set(DATA_DIR / "bns_met_vampire.toml")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def tag(person: Person, path: str = "/rules/vampire", **params: str) -> str:
    response = person.client.get(path, params=params)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-cache"
    found = response.headers["etag"]
    assert found.startswith('W/"'), found
    return found


def again(person: Person, sent: str, path: str = "/rules/vampire", **params: str) -> int:
    """Ask again with If-None-Match: `sent`."""
    response = person.client.get(path, params=params, headers={"If-None-Match": sent})
    if response.status_code == 304:
        assert response.content == b""
        assert matches(sent, response.headers["etag"])
        assert response.headers["cache-control"] == "private, no-cache"
    return response.status_code


def test_asking_again_with_the_etag_gets_not_modified(troupe: Troupe) -> None:
    for params in ({}, {"troupe_id": troupe.id}, {"troupe_id": troupe.id, "category": "clan"}):
        etag = tag(troupe.player, **params)
        assert again(troupe.player, etag, **params) == 304
        # As nginx sends it on once it has gzipped it, and in a list.
        assert again(troupe.player, etag.removeprefix("W/"), **params) == 304
        assert again(troupe.player, f'W/"other", {etag}', **params) == 304
        assert again(troupe.player, 'W/"other"', **params) == 200
    # Anyone signed in gets the same catalogue, so the same ETag.
    assert tag(troupe.stranger, troupe_id=troupe.id) == tag(troupe.player, troupe_id=troupe.id)


def test_the_rules_browser_and_the_equipment_rules_too(troupe: Troupe) -> None:
    for path, params in (
        ("/rules/vampire/browse", {}),
        ("/rules/vampire/browse", {"troupe_id": troupe.id}),
        ("/rules/vampire/equipment", {}),
    ):
        etag = tag(troupe.player, path, **params)
        assert again(troupe.player, etag, path, **params) == 304


def test_each_kind_of_change_to_the_rules_changes_the_etag(
    troupe: Troupe, session: Session
) -> None:
    def changes(change: Callable[[], object]) -> None:
        before = tag(troupe.player, troupe_id=troupe.id)
        browsed = tag(troupe.player, "/rules/vampire/browse", troupe_id=troupe.id)
        change()
        assert again(troupe.player, before, troupe_id=troupe.id) == 200
        assert again(troupe.player, browsed, "/rules/vampire/browse", troupe_id=troupe.id) == 200

    base = f"/troupes/{troupe.id}"
    storyteller = troupe.storyteller.client

    def house_rule() -> None:
        price = {"category": "attributes", "scheme": "per_dot", "rate": 4}
        assert storyteller.post(f"{base}/costs", json=price).status_code == 201

    def written_rule() -> None:
        made = storyteller.post(f"{base}/written-rules", json={"title": "By county"})
        assert made.status_code == 201, made.text

    def allowed_sects() -> None:
        changed = troupe.lead.client.patch(base, json={"allowed_sects": ["Sabbat"]})
        assert changed.status_code == 200, changed.text

    changes(house_rule)
    changes(written_rule)
    changes(allowed_sects)
    # The book's rules loaded again, as every deploy does.
    changes(lambda: sync_rule_set(session, replace(VAMPIRE, starting_xp=VAMPIRE.starting_xp + 1)))


def test_the_book_reloaded_changes_the_equipment_rules_etag(
    troupe: Troupe, session: Session
) -> None:
    path = "/rules/vampire/equipment"
    before = tag(troupe.player, path)
    sync_rule_set(session, replace(VAMPIRE, starting_xp=VAMPIRE.starting_xp + 1))
    assert again(troupe.player, before, path) == 200


def test_troupes_and_categories_have_etags_of_their_own(troupe: Troupe) -> None:
    other = other_troupe(troupe)
    etags = [
        tag(troupe.player),
        tag(troupe.player, troupe_id=troupe.id),
        tag(troupe.player, troupe_id=other.id),
        tag(troupe.player, troupe_id=troupe.id, category="clan"),
        tag(troupe.player, troupe_id=troupe.id, category="merits"),
        tag(troupe.player, troupe_id=troupe.id, category=""),
        tag(troupe.player, "/rules/vampire/browse", troupe_id=troupe.id),
    ]
    assert len(set(etags)) == len(etags)


def test_not_modified_is_only_for_who_may_see_it(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    etag = tag(troupe.player, troupe_id=troupe.id)
    signed_out = client_for().get(
        "/rules/vampire", params={"troupe_id": troupe.id}, headers={"If-None-Match": etag}
    )
    assert signed_out.status_code == 401
    assert "etag" not in signed_out.headers


def test_no_such_troupe_or_splat(troupe: Troupe) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    for path in ("/rules/vampire", "/rules/vampire/browse"):
        response = troupe.player.client.get(path, params={"troupe_id": missing})
        assert (response.status_code, response.json()["detail"]) == (404, "No such troupe.")
    for path in ("/rules/werewolf", "/rules/werewolf/browse", "/rules/werewolf/equipment"):
        response = troupe.player.client.get(path, params={"troupe_id": troupe.id})
        assert response.status_code == 404, path
        assert response.json()["detail"] == "No rules for 'werewolf'."


def test_if_none_match_is_compared_weakly() -> None:
    etag = 'W/"abc"'
    assert matches('W/"abc"', etag)
    assert matches('"abc"', etag)
    assert matches('W/"x", "abc"', etag)
    assert matches("*", etag)
    assert not matches(None, etag)
    assert not matches("", etag)
    assert not matches('"abcd"', etag)

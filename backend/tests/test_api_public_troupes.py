"""The troupes anyone may find from the landing page (#1164): only those whose profile is
public and that aren't archived, a page at a time, with only what their public profile
shows; and the blog's articles the landing page reads are only the published ones."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.api import public_troupes
from tests.api_helpers import Troupe
from tests.test_api_troupe_profiles import PROFILE


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def anyone(client_for: Callable[[], TestClient]) -> TestClient:
    """Someone signed out."""
    return client_for()


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def another(troupe: Troupe, name: str, *, public: bool = True) -> str:
    """Another troupe the lead runs, public or not; its id."""
    made = troupe.custodian.client.post(
        "/troupes", json={"name": name, "lead_handle": troupe.lead.handle}
    )
    made_id = ok(made, 201)["id"]
    if public:
        path = f"/troupes/{made_id}/profile/public"
        ok(troupe.lead.client.put(path, json={"public": True}))
    return made_id


def names(page: dict[str, Any]) -> list[str]:
    return [t["name"] for t in page["troupes"]]


def test_only_public_troupes_still_running_are_listed(troupe: Troupe, anyone: TestClient) -> None:
    body = {**PROFILE, "public": True, "contact_id": troupe.storyteller.id}
    ok(troupe.storyteller.client.put(f"/troupes/{troupe.id}/profile", json=body))
    description = "A Camarilla court in Leeds."
    ok(troupe.lead.client.patch(f"/troupes/{troupe.id}", json={"description": description}))
    another(troupe, "Hidden court", public=False)
    gone = another(troupe, "Old court")
    ok(troupe.lead.client.post(f"/troupes/{gone}/archive", json={"reason": "Done"}))
    another(troupe, "ashen choir")

    response = anyone.get("/public/troupes")
    page = ok(response)

    # By name, whatever its case; never the private or the archived one.
    assert names(page) == ["ashen choir", "Lords of the Night"]
    assert (page["page"], page["pages"], page["total"]) == (1, 1, 2)
    lords = page["troupes"][1]
    assert lords == {
        "id": troupe.id,
        "name": "Lords of the Night",
        "abbreviation": "LotN",
        "portrait": None,
        "description": description,
        "place": "Leeds",
    }
    # Nothing its public profile keeps from people signed out, nor anyone's email.
    assert "Mill Lane" not in response.text
    for person in (troupe.lead, troupe.storyteller, troupe.custodian):
        assert person.email not in response.text
    # Signed in, it is the same list.
    assert names(ok(troupe.player.client.get("/public/troupes"))) == names(page)

    # Made private again, it leaves the list.
    ok(troupe.lead.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": False}))
    assert names(ok(anyone.get("/public/troupes"))) == ["ashen choir"]


def test_the_list_comes_a_page_at_a_time(
    troupe: Troupe, anyone: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(public_troupes, "PAGE_SIZE", 2)
    for name in ("Court A", "Court B", "Court C"):
        another(troupe, name)

    first = ok(anyone.get("/public/troupes"))
    second = ok(anyone.get("/public/troupes", params={"page": 2}))

    assert names(first) == ["Court A", "Court B"]
    assert (first["page"], first["pages"], first["total"]) == (1, 2, 3)
    assert names(second) == ["Court C"]
    assert ok(anyone.get("/public/troupes", params={"page": 3}))["troupes"] == []
    assert anyone.get("/public/troupes", params={"page": 0}).status_code == 422


def test_with_none_public_the_list_is_empty(troupe: Troupe, anyone: TestClient) -> None:
    assert ok(anyone.get("/public/troupes")) == {"troupes": [], "page": 1, "pages": 1, "total": 0}


def test_the_landing_pages_articles_are_only_published_ones(
    troupe: Troupe, anyone: TestClient
) -> None:
    """The landing page shows the blog's first page and its featured row
    (GET /blog/public/articles): a draft, one waiting or one unpublished is in neither."""

    def draft(title: str) -> dict[str, Any]:
        body = {"title": title, "summary": "", "body": "Words.", "troupe_id": troupe.id}
        return ok(troupe.storyteller.client.post("/blog/articles", json=body), 201)

    def publish(article: dict[str, Any]) -> None:
        ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
        ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))

    def feature(article: dict[str, Any]) -> None:
        path = f"/blog/articles/{article['id']}/featured"
        ok(troupe.custodian.client.put(path, json={"featured": True}))

    out = draft("Out now")
    publish(out)
    feature(out)
    draft("Still a draft")
    ok(troupe.storyteller.client.post(f"/blog/articles/{draft('Waiting')['id']}/submit"))
    down = draft("Taken down")
    publish(down)
    feature(down)
    path = f"/blog/articles/{down['id']}/unpublish"
    ok(troupe.custodian.client.post(path, json={"reason": "Out of date"}))

    page = ok(anyone.get("/blog/public/articles"))

    assert [a["title"] for a in page["articles"]] == ["Out now"]
    assert [a["title"] for a in page["featured"]] == ["Out now"]

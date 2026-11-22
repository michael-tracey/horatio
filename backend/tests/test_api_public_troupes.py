"""The troupes anyone may find from the landing page (#1164) and the troupe directory
(#1192): only those whose profile is public and that aren't archived, a page at a time,
with only what their public profile shows, searched by its own fields; and the blog's
articles the landing page reads are only the published ones."""

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
        "schedule": "Second Saturday of the month, 7 pm to midnight",
        "new_players": "welcoming",
        "min_age": 18,
        "content_notes": "Violence and body horror.",
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


def profiled(troupe: Troupe, troupe_id: str, **profile: Any) -> None:
    """Gives the troupe `profile`, public."""
    path = f"/troupes/{troupe_id}/profile"
    ok(troupe.lead.client.put(path, json={**profile, "public": True}))


def found(client: TestClient, **search: Any) -> list[str]:
    return names(ok(client.get("/public/troupes", params=search)))


def test_the_directory_searches_by_name_and_place_but_never_the_street_address(
    troupe: Troupe, anyone: TestClient
) -> None:
    profiled(troupe, troupe.id, **PROFILE)
    york = another(troupe, "Court of York")
    profiled(
        troupe,
        york,
        venue={"region": "North Yorkshire", "name": "The Minster Rooms", "address": "Leeds Road"},
        setting={"city": "Chicago"},
    )
    setting = another(troupe, "Shadows over Hull")
    profiled(troupe, setting, setting={"city": "Hull"})
    hidden = another(troupe, "Hidden court of Leeds", public=False)
    profiled(troupe, hidden, venue={"region": "Leeds"})
    ok(troupe.lead.client.put(f"/troupes/{hidden}/profile/public", json={"public": False}))
    gone = another(troupe, "Old court of Leeds")
    profiled(troupe, gone, venue={"region": "Leeds"})
    ok(troupe.lead.client.post(f"/troupes/{gone}/archive", json={"reason": "Done"}))

    # By any part of its name, whatever the case, or by the abbreviation its lead set.
    assert found(anyone, name="COURT") == ["Court of York"]
    assert found(anyone, name="  lords ") == ["Lords of the Night"]
    ok(troupe.lead.client.patch(f"/troupes/{york}", json={"abbreviation": "CoY"}))
    assert found(anyone, name="coy") == ["Court of York"]
    # By the venue's region or name, or the setting's city where it gives no region.
    assert found(anyone, place="yorkshire") == ["Court of York"]
    assert found(anyone, place="chicago") == []
    assert found(anyone, place="minster") == ["Court of York"]
    assert found(anyone, place="hull") == ["Shadows over Hull"]
    assert found(anyone, place="crypt") == ["Lords of the Night"]
    # Never by the street address, which only people signed in see: York's is on a
    # Leeds Road, and Lords' on Mill Lane. Never a private or archived troupe either.
    assert found(anyone, place="Leeds") == ["Lords of the Night"]
    assert found(anyone, place="Mill Lane") == []
    assert found(anyone, place="LS1") == []
    assert found(troupe.player.client, place="Mill Lane") == []
    response = anyone.get("/public/troupes", params={"place": "Leeds"})
    assert "Mill Lane" not in response.text and "Leeds Road" not in response.text
    # A search for the characters a pattern uses finds only those characters.
    assert found(anyone, name="%") == []
    assert found(anyone, place="_") == []


def test_the_directory_filters_by_schedule_new_players_and_age(
    troupe: Troupe, anyone: TestClient
) -> None:
    schedules = {
        "Monthly Saturdays": ("Second Saturday of the month, 7 pm to midnight", "welcoming", 18),
        "Weekly Fridays": ("Every Friday from 8 pm", "closed", 16),
        "Fortnightly Fridays": ("Every other Fri, 7 till late", None, None),
        "Fortnightly Sundays": ("Sundays, fortnightly", "welcoming", 21),
        "Bi-weekly Thursdays": ("Bi-weekly on Thursdays", "welcoming", None),
        "Weekly Wednesdays": ("Wednesdays, weekly", None, 14),
        "No schedule": ("", None, None),
    }
    for name, (schedule, new_players, min_age) in schedules.items():
        made = another(troupe, name)
        profiled(troupe, made, schedule=schedule, new_players=new_players, min_age=min_age)

    assert found(anyone, day="friday") == ["Fortnightly Fridays", "Weekly Fridays"]
    assert found(anyone, day="saturday") == ["Monthly Saturdays"]
    assert found(anyone, day="thursday") == ["Bi-weekly Thursdays"]
    assert found(anyone, day="monday") == []
    assert found(anyone, frequency="weekly") == ["Weekly Fridays", "Weekly Wednesdays"]
    assert found(anyone, frequency="fortnightly") == [
        "Bi-weekly Thursdays",
        "Fortnightly Fridays",
        "Fortnightly Sundays",
    ]
    assert found(anyone, frequency="monthly") == ["Monthly Saturdays"]
    assert found(anyone, day="friday", frequency="weekly") == ["Weekly Fridays"]
    assert found(anyone, new_players=True) == [
        "Bi-weekly Thursdays",
        "Fortnightly Sundays",
        "Monthly Saturdays",
    ]
    # Those a player of 16 may join: their minimum age is 16 or less, or they give none.
    assert found(anyone, age=16) == [
        "Bi-weekly Thursdays",
        "Fortnightly Fridays",
        "No schedule",
        "Weekly Fridays",
        "Weekly Wednesdays",
    ]
    assert found(anyone, age=16, new_players=True) == ["Bi-weekly Thursdays"]
    # The count and pages are of what was found.
    page = ok(anyone.get("/public/troupes", params={"day": "friday"}))
    assert (page["page"], page["pages"], page["total"]) == (1, 1, 2)
    # Only the days and frequencies it knows, and an age a profile can give.
    for wrong in ({"day": "someday"}, {"frequency": "yearly"}, {"age": -1}, {"age": 100}):
        assert anyone.get("/public/troupes", params=wrong).status_code == 422


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

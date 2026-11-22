"""Everyone hears of a new blog article on the bell (issue #1165): once, when it is
first published, by the delivery worker; not its author, a merged or suspended
account, or someone who turned it off; and never by email or push."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import blog_bell
from horatio.config import get_settings
from horatio.models import EmailNotice, Notification, PushNotice, Suspension, User
from tests.api_helpers import Person, Troupe, sign_up

NEW = "New on the blog: “Running your first Elysium”, by storyteller."


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def published(troupe: Troupe) -> dict[str, Any]:
    made = ok(
        troupe.storyteller.client.post(
            "/blog/articles",
            json={"title": "Running your first Elysium", "body": "Start small."},
        ),
        201,
    )
    path = f"/blog/articles/{made['id']}"
    ok(troupe.storyteller.client.post(f"{path}/submit"))
    return ok(troupe.custodian.client.post(f"{path}/publish"))


def bell(person: Person) -> list[dict[str, Any]]:
    return ok(person.client.get("/notifications"))["items"]


def told(person: Person) -> list[str]:
    return [i["summary"] for i in bell(person) if i["kind"] == "blog.new"]


def notices(session: Session, user_id: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == uuid.UUID(user_id), Notification.kind == "blog.new")
        )
        or 0
    )


def test_everyone_hears_of_a_new_article_once_by_the_worker(
    troupe: Troupe, session: Session
) -> None:
    article = published(troupe)
    # Not in the custodian's request: the worker tells everyone.
    assert told(troupe.player) == []

    assert blog_bell.tell_due(session) == 1

    for person in (troupe.player, troupe.stranger, troupe.lead, troupe.narrator, troupe.custodian):
        assert told(person) == [NEW]
    notice = next(i for i in bell(troupe.player) if i["kind"] == "blog.new")
    assert notice["link"] == f"/blog/{article['slug']}"
    assert notice["task"] is False
    assert notice["troupe_id"] is None
    # Its author hears it is published instead.
    assert told(troupe.storyteller) == []
    assert "Your article “Running your first Elysium” is published on the blog." in [
        i["summary"] for i in bell(troupe.storyteller)
    ]
    # Once: the next round tells nobody.
    assert blog_bell.tell_due(session) == 0
    assert told(troupe.player) == [NEW]


def test_not_again_for_its_changes_or_when_it_comes_back(troupe: Troupe, session: Session) -> None:
    article = published(troupe)
    blog_bell.tell_due(session)
    path = f"/blog/articles/{article['id']}"
    ok(
        troupe.storyteller.client.put(
            path, json={"title": "Running your first Elysium", "body": "Start smaller."}
        )
    )
    ok(troupe.storyteller.client.post(f"{path}/submit"))
    ok(troupe.custodian.client.post(f"{path}/publish"))
    assert blog_bell.tell_due(session) == 0

    ok(troupe.custodian.client.post(f"{path}/unpublish", json={"reason": "A typo."}))
    ok(troupe.storyteller.client.post(f"{path}/submit"))
    ok(troupe.custodian.client.post(f"{path}/publish"))
    assert blog_bell.tell_due(session) == 0

    assert told(troupe.player) == [NEW]


def test_one_unpublished_before_it_was_told_is_told_when_published_again(
    troupe: Troupe, session: Session
) -> None:
    article = published(troupe)
    path = f"/blog/articles/{article['id']}"
    ok(troupe.custodian.client.post(f"{path}/unpublish", json={"reason": "Too soon."}))
    assert blog_bell.tell_due(session) == 0
    assert told(troupe.player) == []

    ok(troupe.storyteller.client.post(f"{path}/submit"))
    ok(troupe.custodian.client.post(f"{path}/publish"))
    blog_bell.tell_due(session)

    assert told(troupe.player) == [NEW]


def test_someone_who_turned_it_off_isnt_told(troupe: Troupe, session: Session) -> None:
    ok(
        troupe.player.client.put(
            "/notification-settings", json={"topic": "blog_new", "way": "bell", "on": False}
        )
    )
    # Turned off and on again, it comes.
    for on in (False, True):
        ok(
            troupe.lead.client.put(
                "/notification-settings", json={"topic": "blog_new", "way": "bell", "on": on}
            )
        )
    published(troupe)

    blog_bell.tell_due(session)

    assert told(troupe.player) == []
    assert told(troupe.lead) == [NEW]
    assert told(troupe.stranger) == [NEW]


def test_merged_and_suspended_accounts_arent_told(
    client_for: Callable[[], TestClient], troupe: Troupe, session: Session
) -> None:
    merged = sign_up(client_for, "twice")
    suspended = sign_up(client_for, "barred")
    session.get_one(User, uuid.UUID(merged.id)).merged_into_id = uuid.UUID(troupe.player.id)
    session.add(
        Suspension(
            user_id=uuid.UUID(suspended.id),
            reason="Rude.",
            suspended_by_id=uuid.UUID(troupe.custodian.id),
        )
    )
    session.flush()
    published(troupe)

    blog_bell.tell_due(session)

    assert notices(session, merged.id) == 0
    assert notices(session, suspended.id) == 0
    assert notices(session, troupe.player.id) == 1


def test_it_comes_only_to_the_bell(troupe: Troupe, session: Session) -> None:
    published(troupe)
    blog_bell.tell_due(session)

    assert session.scalar(select(EmailNotice.id).where(EmailNotice.summary == NEW)) is None
    assert session.scalar(select(PushNotice.id).where(PushNotice.summary == NEW)) is None
    topics = {
        t["name"]: t
        for g in ok(troupe.player.client.get("/notification-settings"))["groups"]
        for t in g["topics"]
    }
    assert topics["blog_new"]["title"] == "New blog articles"
    assert {r["way"]: (r["on"], r["always"]) for r in topics["blog_new"]["routes"]} == {
        "bell": (True, False)
    }


def test_a_server_with_it_off_tells_nobody_and_counts_it_told(
    troupe: Troupe, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "blog_bell", False)
    published(troupe)

    assert blog_bell.tell_due(session) == 1

    assert told(troupe.player) == []
    # Turned on again, it isn't sent late.
    monkeypatch.setattr(get_settings(), "blog_bell", True)
    assert blog_bell.tell_due(session) == 0

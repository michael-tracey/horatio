"""Asking the custodian for a new troupe (issue #51)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent
from tests.api_helpers import Person, sign_up


@pytest.fixture
def custodian(client_for: Callable[[], TestClient], session: Session) -> Person:
    return sign_up(client_for, "custodian", custodian=True, session=session)


@pytest.fixture
def asker(client_for: Callable[[], TestClient]) -> Person:
    return sign_up(client_for, "asker")


def ask(person: Person, name: str = "Nights of Boston", **more: str) -> Any:
    response = person.client.post("/troupe-requests", json={"name": name, **more})
    assert response.status_code == 201, response.text
    return response.json()


def bell(person: Person) -> list[dict[str, Any]]:
    return person.client.get("/notifications").json()["items"]


def test_approving_makes_the_troupe_with_the_asker_as_lead(
    custodian: Person, asker: Person, session: Session
) -> None:
    request = ask(asker, description="Camarilla in Back Bay", note="Twelve players so far.")
    assert request["status"] == "pending"
    assert request["requester_name"] == "asker"

    # The custodian has a task waiting; it goes once decided.
    [task] = [i for i in bell(custodian) if i["kind"] == "troupe_request"]
    assert task["task"] is True
    assert task["summary"] == "asker asks for a new troupe, Nights of Boston"
    assert task["link"] == "/custodian/troupe-requests"

    approved = custodian.client.post(f"/troupe-requests/{request['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["decided_by_name"] == "custodian"
    troupe_id = approved.json()["troupe_id"]

    troupe = asker.client.get(f"/troupes/{troupe_id}").json()
    assert troupe["name"] == "Nights of Boston"
    assert troupe["description"] == "Camarilla in Back Bay"
    assert troupe["my_role"] == "lead_storyteller"
    assert not [i for i in bell(custodian) if i["kind"] == "troupe_request"]

    [message] = [i for i in bell(asker) if i["kind"] == "troupe_request.approved"]
    assert message["summary"] == (
        "Your troupe Nights of Boston is ready, with you as its lead storyteller"
    )
    assert message["link"] == f"/troupes/{troupe_id}"

    # Decided once only.
    again = custodian.client.post(f"/troupe-requests/{request['id']}/approve")
    assert again.status_code == 409
    actions = session.scalars(
        select(AuditEvent.action).where(AuditEvent.action.like("troupe_request.%"))
    ).all()
    assert sorted(actions) == ["troupe_request.approved", "troupe_request.made"]


def test_declining_tells_the_asker_why(custodian: Person, asker: Person) -> None:
    request = ask(asker)
    declined = custodian.client.post(
        f"/troupe-requests/{request['id']}/decline", json={"reason": "Join Boston by Night."}
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "declined"
    assert declined.json()["troupe_id"] is None
    assert custodian.client.get("/troupes").json() == []

    [message] = [i for i in bell(asker) if i["kind"] == "troupe_request.declined"]
    assert message["summary"] == (
        "Your request for the troupe Nights of Boston was declined: Join Boston by Night."
    )
    mine = asker.client.get("/troupe-requests/mine").json()
    assert [(r["status"], r["reason"]) for r in mine] == [("declined", "Join Boston by Night.")]


def test_only_the_custodian_sees_and_decides(
    client_for: Callable[[], TestClient], custodian: Person, asker: Person
) -> None:
    request = ask(asker)
    other = sign_up(client_for, "other")
    assert asker.client.get("/troupe-requests").status_code == 403
    assert other.client.get("/troupe-requests/mine").json() == []
    for path in ("approve", "decline"):
        refused = asker.client.post(f"/troupe-requests/{request['id']}/{path}", json={})
        assert refused.status_code == 403
    assert not [i for i in bell(asker) if i["task"]]
    assert [r["id"] for r in custodian.client.get("/troupe-requests").json()] == [request["id"]]


def test_withdrawing(
    client_for: Callable[[], TestClient], custodian: Person, asker: Person
) -> None:
    request = ask(asker)
    other = sign_up(client_for, "other")
    assert other.client.delete(f"/troupe-requests/{request['id']}").status_code == 404
    assert asker.client.delete(f"/troupe-requests/{request['id']}").status_code == 204
    assert asker.client.delete(f"/troupe-requests/{request['id']}").status_code == 409
    assert not [i for i in bell(custodian) if i["kind"] == "troupe_request"]
    approve = custodian.client.post(f"/troupe-requests/{request['id']}/approve")
    assert approve.status_code == 409
    assert approve.json()["detail"] == "This request was already withdrawn."


def test_asking_twice_for_the_same_name(asker: Person) -> None:
    ask(asker)
    twice = asker.client.post("/troupe-requests", json={"name": " nights of boston "})
    assert twice.status_code == 409
    assert asker.client.post("/troupe-requests", json={"name": "   "}).status_code == 422
    ask(asker, "Chicago by Night")
    assert [r["name"] for r in asker.client.get("/troupe-requests/mine").json()] == [
        "Chicago by Night",
        "Nights of Boston",
    ]

"""Delivering downtime results through a troupe's connectors, with a fake one: the
worker sends what is queued, retries failures with backoff, and never sends twice."""

from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import delivery
from horatio.connectors import CONNECTORS, Connector, Message, Recipient, SendError
from horatio.models import Delivery
from tests.api_helpers import Troupe
from tests.test_api_responses import Scene

START = datetime(2026, 10, 20, 12, tzinfo=UTC)


class FakeConnector(Connector):
    """Records what it sends; fails as told."""

    kind = "discord"
    name = "Fake chat"

    def __init__(self) -> None:
        self.sent: list[tuple[str, Message]] = []
        self.failures: list[SendError] = []
        self.down: str | None = None

    def unavailable(self) -> str | None:
        return self.down

    def check_settings(
        self, settings: Mapping[str, Any], current: Mapping[str, Any]
    ) -> dict[str, Any]:
        if "test_target" not in settings:
            raise ValueError("Name a test target.")
        return dict(settings)

    def target(self, settings: Mapping[str, Any], recipient: Recipient, test_mode: bool) -> str:
        if test_mode:
            return settings["test_target"]
        if recipient.character_name == "Nobody":
            raise SendError("No channel for Nobody.", retry=False)
        return f"#{recipient.character_name.lower()}"

    def send(self, settings: Mapping[str, Any], target: str, message: Message) -> dict[str, Any]:
        if self.failures:
            raise self.failures.pop(0)
        self.sent.append((target, message))
        return {"message_id": str(len(self.sent))}


@pytest.fixture
def fake() -> Iterator[FakeConnector]:
    connector = FakeConnector()
    real = CONNECTORS.get("discord")
    CONNECTORS["discord"] = connector
    yield connector
    if real is not None:
        CONNECTORS["discord"] = real


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    """A cycle closed with one written response, ready to deliver."""
    scene = Scene(Troupe(client_for, session))
    feed = scene.response_for("Feed at the docks")["id"]
    scene.troupe.assistant.client.put(f"/responses/{feed}", json={"body": "You feed well."})
    scene.troupe.assistant.client.post(f"/cycles/{scene.cycle['id']}/close")
    return scene


def connect(scene: Scene, **change: Any) -> Any:
    body = {"enabled": True, "settings": {"test_target": "#st-test"}, **change}
    return scene.troupe.storyteller.client.put(
        f"/troupes/{scene.troupe.id}/connectors/discord", json=body
    )


def deliver(scene: Scene) -> dict[str, int]:
    response = scene.troupe.assistant.client.post(f"/cycles/{scene.cycle['id']}/deliver")
    assert response.status_code == 200, response.text
    return response.json()


def status(scene: Scene) -> dict[str, Any]:
    response = scene.troupe.assistant.client.get(f"/cycles/{scene.cycle['id']}/deliveries")
    assert response.status_code == 200, response.text
    return response.json()


def agnes_on(scene: Scene, channel: str) -> dict[str, Any]:
    [agnes] = status(scene)["participants"]
    return agnes["deliveries"][channel]


def send_due(session: Session, at: datetime = START) -> int:
    return delivery.send_due(session, at)


def test_with_no_connectors_results_stay_in_horatio(scene: Scene, session: Session) -> None:
    assert deliver(scene) == {"delivered": 1, "queued": 0}

    assert status(scene)["channels"] == ["horatio"]
    assert agnes_on(scene, "horatio")["status"] == "sent"
    assert send_due(session) == 0


def test_storytellers_set_up_a_connector(scene: Scene, fake: FakeConnector) -> None:
    troupe = scene.troupe
    url = f"/troupes/{troupe.id}/connectors"
    assert troupe.assistant.client.put(f"{url}/discord", json={"enabled": True}).status_code == 403
    assert connect(scene, settings={}).status_code == 422
    assert troupe.storyteller.client.put(f"{url}/pigeon", json={"enabled": True}).status_code == 404

    changed = connect(scene, mode="full")

    assert changed.status_code == 200, changed.text
    assert (changed.json()["enabled"], changed.json()["mode"]) == (True, "full")
    listed = next(c for c in troupe.assistant.client.get(url).json() if c["kind"] == "discord")
    assert (listed["kind"], listed["name"], listed["unavailable"]) == ("discord", "Fake chat", None)
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller turned the Fake chat connector on." in log


def test_a_connector_the_server_cannot_use_cannot_be_switched_on(
    scene: Scene, fake: FakeConnector
) -> None:
    fake.down = "No bot token is set on this server."

    refused = connect(scene)

    assert refused.status_code == 409
    assert refused.json()["detail"] == "No bot token is set on this server."


def test_delivering_queues_a_copy_that_the_worker_sends_once(
    scene: Scene, fake: FakeConnector, session: Session
) -> None:
    connect(scene, mode="full")

    assert deliver(scene) == {"delivered": 1, "queued": 1}
    assert agnes_on(scene, "discord")["status"] == "pending"
    assert send_due(session) == 1

    [(target, message)] = fake.sent
    assert target == "#agnes"
    assert message.text.startswith("**Downtime results for Agnes (October 2026)**")
    assert message.subject == "Lords of the Night: downtime results for Agnes (October 2026)"
    assert message.link.endswith(f"/characters/{scene.agnes}/results")
    assert agnes_on(scene, "discord")["status"] == "sent"
    # Delivering again, or the worker running again, sends nothing more.
    assert deliver(scene) == {"delivered": 0, "queued": 0}
    assert send_due(session) == 0
    assert len(fake.sent) == 1


def test_an_alert_says_the_results_are_ready(
    scene: Scene, fake: FakeConnector, session: Session
) -> None:
    connect(scene, mode="alert")
    deliver(scene)
    send_due(session)

    [(_, message)] = fake.sent
    assert message.text.startswith("Your downtime results for Agnes (October 2026) are ready: ")
    assert message.text.endswith(f"/characters/{scene.agnes}/results")


def test_failures_worth_retrying_back_off_then_send(
    scene: Scene, fake: FakeConnector, session: Session
) -> None:
    connect(scene)
    deliver(scene)
    fake.failures = [SendError("Service unavailable", retry=True)] * 2

    send_due(session)
    first = agnes_on(scene, "discord")
    assert (first["status"], first["attempts"], first["last_error"]) == (
        "pending",
        1,
        "Service unavailable",
    )
    # Not due again for a minute, then two after the second failure.
    assert send_due(session, START + timedelta(seconds=30)) == 0
    assert send_due(session, START + timedelta(minutes=1)) == 1
    assert send_due(session, START + timedelta(minutes=2)) == 0
    assert send_due(session, START + timedelta(minutes=3)) == 1

    assert agnes_on(scene, "discord")["status"] == "sent"
    assert len(fake.sent) == 1


def test_a_rate_limit_waits_as_long_as_asked(
    scene: Scene, fake: FakeConnector, session: Session
) -> None:
    connect(scene)
    deliver(scene)
    fake.failures = [SendError("Slow down", retry=True, retry_after=600)]

    send_due(session)

    assert send_due(session, START + timedelta(minutes=5)) == 0
    assert send_due(session, START + timedelta(minutes=10)) == 1


def test_it_gives_up_after_too_many_tries(
    scene: Scene, fake: FakeConnector, session: Session
) -> None:
    connect(scene)
    deliver(scene)
    fake.failures = [SendError("Service unavailable", retry=True)] * delivery.MAX_ATTEMPTS

    at = START
    for _ in range(delivery.MAX_ATTEMPTS):
        send_due(session, at)
        at += timedelta(hours=2)

    failed = agnes_on(scene, "discord")
    assert failed["status"] == "failed"
    assert failed["last_error"] == "Gave up after 6 tries: Service unavailable"


def test_a_failure_that_needs_a_storyteller_can_be_retried(
    scene: Scene, fake: FakeConnector, session: Session
) -> None:
    connect(scene)
    deliver(scene)
    fake.failures = [SendError("Missing access to #agnes", retry=False)]
    send_due(session)
    failed = agnes_on(scene, "discord")
    assert (failed["status"], failed["last_error"]) == ("failed", "Missing access to #agnes")

    troupe = scene.troupe
    assert troupe.narrator.client.post(f"/deliveries/{failed['id']}/retry").status_code == 403
    retried = troupe.assistant.client.post(f"/deliveries/{failed['id']}/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "pending"
    send_due(session, START + timedelta(days=1))

    assert agnes_on(scene, "discord")["status"] == "sent"
    assert troupe.assistant.client.post(f"/deliveries/{failed['id']}/retry").status_code == 409


def test_marking_a_delivery_sent_by_hand(
    scene: Scene, fake: FakeConnector, session: Session
) -> None:
    connect(scene)
    deliver(scene)
    fake.failures = [SendError("Missing access", retry=False)]
    send_due(session)
    failed = agnes_on(scene, "discord")

    marked = scene.troupe.assistant.client.post(f"/deliveries/{failed['id']}/mark-sent")

    assert marked.status_code == 200, marked.text
    shown = agnes_on(scene, "discord")
    assert (shown["status"], shown["marked_by"]) == ("sent", "assistant")
    assert fake.sent == []
    log = [
        e["message"] for e in scene.troupe.lead.client.get(f"/troupes/{scene.troupe.id}/log").json()
    ]
    assert "assistant marked Agnes's discord delivery as sent by hand." in log


def test_test_mode_sends_to_the_test_target_only(
    scene: Scene, fake: FakeConnector, session: Session
) -> None:
    connect(scene, test_mode=True)
    deliver(scene)
    send_due(session)

    assert [target for target, _ in fake.sent] == ["#st-test"]
    assert agnes_on(scene, "discord")["test_mode"] is True
    # Out of test mode, delivering again sends it for real.
    connect(scene, test_mode=False)
    assert deliver(scene) == {"delivered": 0, "queued": 1}
    send_due(session)
    assert [target for target, _ in fake.sent] == ["#st-test", "#agnes"]
    rows = session.scalars(select(Delivery).where(Delivery.channel == "discord")).all()
    assert sorted(r.test_mode for r in rows) == [False, True]

"""How Horatio looks, which the custodian chooses: its loading animation (#568)."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent
from tests.api_helpers import sign_up


def test_anyone_signed_out_reads_the_blood_drip_until_one_is_chosen(
    client_for: Callable[[], TestClient],
) -> None:
    response = client_for().get("/appearance")

    assert response.status_code == 200, response.text
    assert response.json() == {"loading_animation": {"default": "drip"}}


def test_the_custodian_chooses_the_loading_animation_for_everyone(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    custodian = sign_up(client_for, "custodian", custodian=True, session=session)

    response = custodian.client.put(
        "/appearance/loading-animation", json={"loading_animation": {"default": "candle"}}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"loading_animation": {"default": "candle"}}
    assert client_for().get("/appearance").json() == {"loading_animation": {"default": "candle"}}
    event = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "appearance.loading_animation")
    ).one()
    assert event.data["animation"] == "candle"
    log = custodian.client.get("/audit", params={"group": "system"}).json()
    assert any(
        e["message"] == "custodian chose the candle loading animation." for e in log["entries"]
    )


def test_a_splat_can_have_its_own_beside_the_default(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    custodian = sign_up(client_for, "custodian", custodian=True, session=session)

    chosen = {"default": "heartbeat", "ghoul": "rising"}
    response = custodian.client.put(
        "/appearance/loading-animation", json={"loading_animation": chosen}
    )

    assert response.status_code == 200, response.text
    assert client_for().get("/appearance").json() == {"loading_animation": chosen}


def test_it_needs_a_default_a_known_splat_and_a_known_animation(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    custodian = sign_up(client_for, "custodian", custodian=True, session=session)
    put = lambda chosen: custodian.client.put(  # noqa: E731
        "/appearance/loading-animation", json={"loading_animation": chosen}
    )

    assert put({"ghoul": "drip"}).status_code == 422
    assert put({"default": "drip", "fae": "candle"}).status_code == 422
    assert put({"default": "quill"}).status_code == 422
    assert client_for().get("/appearance").json() == {"loading_animation": {"default": "drip"}}


def test_only_the_custodian_chooses_it(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    player = sign_up(client_for, "player", session=session)

    response = player.client.put(
        "/appearance/loading-animation", json={"loading_animation": {"default": "candle"}}
    )

    assert response.status_code == 403
    assert (
        client_for()
        .put("/appearance/loading-animation", json={"loading_animation": {"default": "candle"}})
        .status_code
        == 401
    )

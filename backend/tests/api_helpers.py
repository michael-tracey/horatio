"""Helpers for API tests: people signed in as each role."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import Character, User

PASSWORD = "correct horse battery"


class Person:
    """Someone with an account, and an API client signed in as them."""

    def __init__(self, client: TestClient, email: str, data: dict[str, Any]) -> None:
        self.client = client
        self.email = email
        self.id: str = data["id"]


def sign_up(
    client_for: Callable[[], TestClient],
    name: str,
    *,
    custodian: bool = False,
    session: Session | None = None,
) -> Person:
    client = client_for()
    email = f"{name}@example.com"
    response = client.post(
        "/auth/signup", json={"email": email, "password": PASSWORD, "display_name": name}
    )
    assert response.status_code == 201, response.text
    if custodian:
        assert session is not None
        session.scalars(select(User).where(User.email == email)).one().is_custodian = True
        session.flush()
    return Person(client, email, response.json())


class Troupe:
    """A troupe with one person in each role, plus a member player and a stranger."""

    def __init__(self, client_for: Callable[[], TestClient], session: Session) -> None:
        self.client_for = client_for
        self.session = session
        self.custodian = sign_up(client_for, "custodian", custodian=True, session=session)
        self.lead = sign_up(client_for, "lead")
        self.storyteller = sign_up(client_for, "storyteller")
        self.assistant = sign_up(client_for, "assistant")
        self.narrator = sign_up(client_for, "narrator")
        self.player = sign_up(client_for, "player")
        self.stranger = sign_up(client_for, "stranger")

        response = self.custodian.client.post(
            "/troupes", json={"name": "Lords of the Night", "lead_email": self.lead.email}
        )
        assert response.status_code == 201, response.text
        self.id: str = response.json()["id"]
        for person, role in (
            (self.storyteller, "storyteller"),
            (self.assistant, "assistant_storyteller"),
            (self.narrator, "narrator"),
        ):
            response = self.lead.client.put(
                f"/troupes/{self.id}/staff", json={"email": person.email, "role": role}
            )
            assert response.status_code == 200, response.text


def new_character(
    troupe: Troupe, player: Person, name: str = "Agnes", *, finished: bool = True
) -> str:
    """A new Vampire. `finished` skips placing creation picks, for tests about
    something else; tests about creation place them through the API."""
    response = player.client.post("/characters", json={"splat": "vampire", "name": name})
    assert response.status_code == 201, response.text
    character_id: str = response.json()["id"]
    if finished:
        character = troupe.session.get_one(Character, uuid.UUID(character_id))
        character.creation_completed_at = datetime.now(UTC)
        troupe.session.flush()
    return character_id


STARTING_TRAITS = {"Humanity", "Healthy", "Injured", "Incapacitated", "Willpower"}


def without_starting_traits(traits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in traits if t["name"] not in STARTING_TRAITS]

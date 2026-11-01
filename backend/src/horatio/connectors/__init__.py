"""Connectors: ways out of Horatio that a troupe sets up, such as its Discord
server or email (CONTEXT.md: Connector). In-app delivery is always on and is
not a connector.

Each connector says whether the server is set up for it, checks a troupe's
settings, finds where one person's message goes, and sends one message there.
A failure says whether trying again later could help. Downtime results are the
first thing connectors carry; nothing here is specific to them.
"""

import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass(frozen=True)
class Recipient:
    """Whose message it is: the character, and the player who plays it."""

    character_id: uuid.UUID
    character_name: str
    player_name: str
    player_email: str


@dataclass(frozen=True)
class Message:
    troupe: str
    # A short title, for connectors that have one (an email's subject).
    subject: str
    # What to send, as Markdown: the whole result, or a note that it is ready.
    text: str
    # Where to read it in Horatio.
    link: str


class SendError(Exception):
    """Sending failed. `retry` says whether trying again later could help (the
    service was down, or asked us to slow down); if not, someone must fix it."""

    def __init__(self, reason: str, *, retry: bool, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry = retry
        # Seconds the service asked us to wait, if it said.
        self.retry_after = retry_after


class Connector(ABC):
    kind: ClassVar[str]
    name: ClassVar[str]
    # The server settings it needs (environment variables), named only to the
    # custodian, who sets them; a storyteller can't act on them.
    needs: ClassVar[tuple[str, ...]] = ()

    def unavailable(self) -> str | None:
        """Why the server cannot use this connector (it is not configured), in plain
        words for a storyteller, or None."""
        return None

    @abstractmethod
    def check_settings(
        self, settings: Mapping[str, Any], current: Mapping[str, Any]
    ) -> dict[str, Any]:
        """A troupe's new settings, tidied, given what is stored now (some settings
        only Horatio sets, such as a connected Discord server); raises ValueError
        when they cannot work."""

    @abstractmethod
    def target(self, settings: Mapping[str, Any], recipient: Recipient, test_mode: bool) -> str:
        """Where this recipient's message goes (in test mode, the test target).
        Raises SendError, not worth retrying, when there is nowhere to send it."""

    @abstractmethod
    def send(self, settings: Mapping[str, Any], target: str, message: Message) -> dict[str, Any]:
        """Send one message; returns what the service called it, for the record.
        Raises SendError."""


# The connectors this server offers, by kind. Discord and email register here.
CONNECTORS: dict[str, Connector] = {}


def register(connector: Connector) -> Connector:
    CONNECTORS[connector.kind] = connector
    return connector

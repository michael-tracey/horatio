"""Who Horatio's emails come from (#833): the From name and address, and a default
Reply-To, which the custodian may set on Custodian › Site.

The server's `HORATIO_MAIL_FROM` is the default; what the custodian sets overrides
it, part by part, and is kept as a server setting. Nothing secret is kept here: the
mail server, its username and password stay in the server's environment
(horatio.config), never in the database.

Every email goes through `horatio.connectors.email.new_message`, which takes the
`Sender` this makes. A troupe's own Reply-To for its downtime results (its email
connector) still wins over the default.
"""

from dataclasses import dataclass
from email.utils import formataddr, parseaddr

from sqlalchemy.orm import Session

from horatio.config import get_settings
from horatio.models import ServerSetting

KEY = "mail_sender"
# The parts the custodian may set, as kept.
PARTS = ("from_name", "from_address", "reply_to")


@dataclass(frozen=True)
class Sender:
    # The From header, such as "Horatio <horatio@example.org>".
    from_: str
    # Where replies go unless the email sets its own; None for the From address.
    reply_to: str | None = None


def kept(db: Session) -> dict[str, str]:
    """What the custodian set, only the parts set."""
    row = db.get(ServerSetting, KEY)
    value = row.value if row is not None and isinstance(row.value, dict) else {}
    return {part: str(value[part]) for part in PARTS if value.get(part)}


def environment() -> tuple[str, str]:
    """The server's `HORATIO_MAIL_FROM`, as its name and address (either may be "")."""
    return parseaddr(get_settings().mail_from or "")


def sender(db: Session) -> Sender:
    """Who an email comes from now: the server's From, with what the custodian set
    over it."""
    name, address = environment()
    chosen = kept(db)
    name = chosen.get("from_name", name)
    address = chosen.get("from_address", address)
    return Sender(
        from_=formataddr((name, address)) if address else "", reply_to=chosen.get("reply_to")
    )

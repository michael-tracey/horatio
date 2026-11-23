"""Every check of the custodian's powers goes through horatio.permissions (#1213): a
custodian has them only with custodian access switched on, which
`acting_as_custodian` alone asks. Reading `is_custodian` itself says only that an
account is the custodian's: who may switch it on, who is told of the custodian's
work, whom no one views as. Each such read is listed here, so a new one, which is
most likely a check that would let a custodian through with access off, fails until
it is looked at."""

import re
from collections import Counter
from pathlib import Path

import horatio

# Each file that reads `is_custodian`, how many times, and why it isn't a check.
IDENTITY: dict[str, tuple[int, str]] = {
    "permissions.py": (6, "acting_as_custodian itself, and its docs"),
    "models/people.py": (1, "the column"),
    "custodian.py": (4, "the server command that makes a custodian"),
    "auth/custodian_access.py": (2, "only a custodian has access on, and while they are one"),
    "api/custodian_access.py": (2, "only a custodian switches it on"),
    "api/auth.py": (3, "Me says the account may switch it on: the Custodian menu"),
    "auth/two_step.py": (1, "a custodian must have a second step, on or off"),
    "auth/viewing.py": (3, "a viewing ends once its custodian is one no longer"),
    "api/viewing.py": (1, "no one views as a custodian"),
    "api/players.py": (6, "a person's profile and People say they are a custodian"),
    "account_merges.py": (1, "a custodian's account is never merged away"),
    "suspensions.py": (2, "the last custodian can't be suspended"),
    "email_changes.py": (1, "naming the custodians to ask"),
    "notifications.py": (5, "the custodians' own bell and email: the work waiting on them"),
    "api/notification_settings.py": (1, "the custodian's own notification settings"),
    "posts.py": (1, "a post signed by the custodian"),
}


def test_only_permissions_checks_the_custodians_powers() -> None:
    source = Path(horatio.__file__).parent
    found = Counter(
        {
            path.relative_to(source).as_posix(): len(re.findall(r"\bis_custodian\b", text))
            for path in source.rglob("*.py")
            if "is_custodian" in (text := path.read_text())
        }
    )
    listed = {name: count for name, (count, _) in IDENTITY.items()}
    assert dict(found) == listed, (
        "A check of the custodian's powers asks horatio.permissions.acting_as_custodian; "
        "only a read that says an account is the custodian's belongs in IDENTITY."
    )

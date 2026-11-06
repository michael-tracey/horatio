"""Make an existing account the custodian, or stop it being one:
`uv run python -m horatio.custodian [--remove] EMAIL`.

The custodian can do everything, so this is deliberately a command run on the
server rather than anything reachable through the API. The last custodian can't
be removed: someone has to be able to look after the site.
"""

import sys

from sqlalchemy import func, select

from horatio.db import get_sessionmaker
from horatio.models import User

USAGE = "usage: python -m horatio.custodian [--remove] EMAIL"


def main(argv: list[str]) -> int:
    remove = argv[:1] == ["--remove"]
    if remove:
        argv = argv[1:]
    if len(argv) != 1 or argv[0].startswith("-"):
        print(USAGE, file=sys.stderr)
        return 2
    email = argv[0]
    with get_sessionmaker()() as db, db.begin():
        user = db.scalar(
            select(User).where(
                func.lower(User.email) == email.lower(), User.merged_into_id.is_(None)
            )
        )
        if user is None:
            print(f"No account with email {email}. Sign up first.", file=sys.stderr)
            return 1
        if not remove:
            user.is_custodian = True
        elif not user.is_custodian:
            print(f"{email} is not a custodian.", file=sys.stderr)
            return 1
        elif not db.scalar(
            select(func.count()).where(
                User.is_custodian, User.id != user.id, User.merged_into_id.is_(None)
            )
        ):
            print(
                f"{email} is the only custodian. Make someone else the custodian first.",
                file=sys.stderr,
            )
            return 1
        else:
            user.is_custodian = False
    print(f"{email} is {'no longer' if remove else 'now'} a custodian.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

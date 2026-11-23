"""Make an existing account the custodian, or stop it being one:
`uv run python -m horatio.custodian [--remove] EMAIL`.

The custodian can do everything, so this is deliberately a command run on the
server rather than anything reachable through the API. The last custodian can't
be removed: someone has to be able to look after the site.

`--switch-on [--for SECONDS] EMAIL` makes them the custodian and switches custodian
access on for each sign-in they have now (horatio.auth.custodian_access), as giving
their second step again would: for the test suites, whose custodians are made by
this command after signing up. `--for` is how long it lasts after its last use, an
hour unless it says.
"""

import sys
from datetime import timedelta

from sqlalchemy import func, select

from horatio.auth import custodian_access
from horatio.auth.sessions import live
from horatio.db import get_sessionmaker
from horatio.models import Session as SignInSession
from horatio.models import User

USAGE = "usage: python -m horatio.custodian [--remove | --switch-on [--for SECONDS]] EMAIL"
SWITCHED_ON = "Switched on from the server."


def main(argv: list[str]) -> int:
    remove = argv[:1] == ["--remove"]
    switch_on = argv[:1] == ["--switch-on"]
    if remove or switch_on:
        argv = argv[1:]
    lasts = custodian_access.ACCESS_FOR
    if switch_on and argv[:1] == ["--for"]:
        if len(argv) < 2 or not argv[1].isdigit():
            print(USAGE, file=sys.stderr)
            return 2
        lasts = timedelta(seconds=int(argv[1]))
        argv = argv[2:]
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
        if switch_on:
            for session_id in db.scalars(
                select(SignInSession.id).where(SignInSession.user_id == user.id, *live())
            ):
                custodian_access.switch_on(db, user, session_id, SWITCHED_ON, lasts)
    print(f"{email} is {'no longer' if remove else 'now'} a custodian.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

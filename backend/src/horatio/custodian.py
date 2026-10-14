"""Make an existing account the custodian: `uv run python -m horatio.custodian EMAIL`.

The custodian can do everything, so this is deliberately a command run on the
server rather than anything reachable through the API.
"""

import sys

from sqlalchemy import func, select

from horatio.db import get_sessionmaker
from horatio.models import User


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m horatio.custodian EMAIL", file=sys.stderr)
        return 2
    email = argv[0]
    with get_sessionmaker()() as db, db.begin():
        user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if user is None:
            print(f"No account with email {email}. Sign up first.", file=sys.stderr)
            return 1
        user.is_custodian = True
    print(f"{email} is now a custodian.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

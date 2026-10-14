"""Load every rule set file into the database: `uv run python -m horatio.rules`."""

from horatio.db import get_sessionmaker
from horatio.rules.files import all_rule_set_files, load_rule_set
from horatio.rules.store import sync_rule_set


def main() -> None:
    with get_sessionmaker()() as session, session.begin():
        for path in all_rule_set_files():
            data = load_rule_set(path)
            sync_rule_set(session, data)
            print(f"loaded {data.name} (version {data.version}) from {path.name}")


if __name__ == "__main__":
    main()

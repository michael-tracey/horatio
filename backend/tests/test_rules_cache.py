"""The rules each process keeps (issue #641): read again only when their version
changes, which every change to what they are read from does."""

import re
import uuid
from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import event, text, update
from sqlalchemy.orm import Session

from horatio.api import (
    book_traits,
    house_checks,
    house_rules,
    house_traits,
    teachers,
    written_rules,
)
from horatio.models import CostRule, RuleSet, TraitCategory
from horatio.models import Troupe as TroupeRow
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import ActionKindData, CostRuleData, StartingTraitData, TroupeRules
from horatio.rules.store import (
    add_house_action_kind,
    add_house_rule,
    change_house_action_kind,
    forget_rules,
    load_troupe_rules,
    read_troupe_rules,
    rules_version,
    set_house_starting_trait,
    sync_rule_set,
)
from tests.api_helpers import Person, Troupe
from tests.test_api_own_checks import IRON_WILL_FOR_VENTRUE
from tests.test_api_sect_status import other_troupe
from tests.test_api_teachers import LORE_SPECIALISATIONS

VAMPIRE = load_rule_set(DATA_DIR / "bns_met_vampire.toml")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def ids(troupe: Troupe) -> uuid.UUID:
    return uuid.UUID(troupe.id)


def read(session: Session, troupe_id: uuid.UUID | None) -> TroupeRules:
    """The rules as a new session reads them."""
    forget_rules(session)
    return read_troupe_rules(session, "vampire", troupe_id)


@pytest.fixture
def statements(session: Session) -> Iterator[list[str]]:
    """The SQL the session sends, from when it is asked for."""
    sent: list[str] = []

    def keep(*args: Any) -> None:
        sent.append(args[2])

    connection = session.connection()
    event.listen(connection, "before_cursor_execute", keep)
    yield sent
    event.remove(connection, "before_cursor_execute", keep)


def test_a_new_session_reads_the_kept_rules_with_one_query(
    troupe: Troupe, session: Session, statements: list[str]
) -> None:
    for troupe_id in (ids(troupe), None):
        first = read(session, troupe_id)
        statements.clear()

        again = read(session, troupe_id)

        assert again is first
        # Only the version: nothing of the rules themselves.
        assert len(statements) == 1
        assert "rules_version" in statements[0]


def test_two_troupes_keep_their_own_rules(troupe: Troupe, session: Session) -> None:
    other = other_troupe(troupe)
    book, mine, theirs = read(session, None), read(session, ids(troupe)), read(session, ids(other))
    their_version = rules_version(session, "vampire", ids(other))
    price = CostRuleData(category="attributes", scheme="per_dot", rate=4)

    add_house_rule(session, ids(troupe), "vampire", price)

    assert [r.rate for r in read(session, ids(troupe)).house_rules] == [4]
    assert read(session, ids(other)) is theirs
    assert read(session, None) is book
    assert rules_version(session, "vampire", ids(other)) == their_version
    assert theirs.house_rules == [] and book.house_rules == []
    assert mine.house_rules == []


def test_a_change_rolled_back_is_never_read(troupe: Troupe, session: Session) -> None:
    """A version read with a change no one has committed is new, so the rules read
    with it are never read again once the change is rolled back."""
    before = read(session, ids(troupe))
    price = CostRuleData(category="attributes", scheme="per_dot", rate=4)
    with session.begin_nested() as savepoint:
        add_house_rule(session, ids(troupe), "vampire", price)
        assert len(read(session, ids(troupe)).house_rules) == 1
        savepoint.rollback()

    after = read(session, ids(troupe))
    assert after.house_rules == []
    assert after == before


def test_the_books_rules_are_read_again_when_they_are_loaded_again(
    troupe: Troupe, session: Session
) -> None:
    book, mine = read(session, None), read(session, ids(troupe))
    version = rules_version(session, "vampire", ids(troupe))

    sync_rule_set(session, replace(VAMPIRE, starting_xp=VAMPIRE.starting_xp + 1))

    assert rules_version(session, "vampire", ids(troupe)) != version
    assert read(session, None).rule_set.starting_xp == book.rule_set.starting_xp + 1
    assert read(session, ids(troupe)).rule_set.starting_xp == mine.rule_set.starting_xp + 1


@pytest.mark.parametrize(
    "change",
    [
        update(RuleSet).where(RuleSet.splat == "vampire").values(banked_xp=None),
        update(TraitCategory).values(position=TraitCategory.position + 1),
        update(CostRule).where(CostRule.troupe_id.is_(None)).values(text="changed"),
        text("update equipment_qualities set play = 'changed'"),
        text("delete from starting_traits where troupe_id is null"),
    ],
    ids=["rule set", "categories", "book prices", "equipment", "starting traits"],
)
def test_a_change_to_the_books_rules_from_anywhere_changes_the_version(
    session: Session, change: Any
) -> None:
    before = rules_version(session, "vampire", None)

    session.execute(change)

    assert rules_version(session, "vampire", None) != before


def tables_in(sql: str) -> set[str]:
    return set(re.findall(r"\b(?:FROM|JOIN)\s+(\w+)", sql))


def test_every_table_the_rules_are_read_from_changes_the_version(
    troupe: Troupe, session: Session, statements: list[str]
) -> None:
    """A table the rules are read from without a trigger to change the version would
    leave a process reading old rules: one added to load_troupe_rules needs one in a
    migration too (as 0162)."""
    load_troupe_rules(session, "vampire", ids(troupe))
    read_from = set().union(*map(tables_in, statements))
    triggered = set(
        session.scalars(
            text(
                "select c.relname from pg_trigger t join pg_class c on c.oid = t.tgrelid "
                "where t.tgname = 'rules_changed'"
            )
        )
    )

    assert "cost_rules" in read_from and "troupes" in read_from
    assert read_from <= triggered


# --- every way a troupe's rules change ----------------------------------------------------

# The routers whose every change is to a troupe's rules, or to its own row.
RULES_ROUTERS = (house_rules, house_checks, house_traits, book_traits, teachers, written_rules)
# Their changes that are to something else: a preview, a character's sheet, a teaching.
NOT_RULES = re.compile(r"/preview$|^/characters/|^/teachings/")


class Walk:
    """Changes a troupe's rules through the API, checking each changes the troupe's
    version, and the rules read after it where `changes` (written and teacher rules,
    and most settings on the troupe's row, are not in them), and nothing of another
    troupe's or the book's."""

    def __init__(self, troupe: Troupe, other: Troupe) -> None:
        self.troupe = troupe
        self.session = troupe.session
        self.other = other
        self.walked: list[tuple[str, str]] = []

    def version(self, troupe: Troupe | None) -> str:
        return rules_version(self.session, "vampire", ids(troupe) if troupe else None)

    def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        changes: bool = True,
        by: Person | None = None,
    ) -> Any:
        url = f"/troupes/{self.troupe.id}{path}"

        def change() -> Any:
            client = (by or self.troupe.storyteller).client
            response = client.request(method, url, json=body)
            assert response.is_success, (method, url, response.text)
            return response.json() if response.content else None

        return self.changing(change, changes=changes, walked=(method, url))

    def changing(
        self,
        change: Callable[[], Any],
        *,
        changes: bool = True,
        walked: tuple[str, str] | None = None,
    ) -> Any:
        before = read(self.session, ids(self.troupe))
        versions = self.version(self.troupe), self.version(self.other), self.version(None)
        found = change()
        if walked:
            self.walked.append(walked)

        assert self.version(self.troupe) != versions[0], walked
        assert (self.version(self.other), self.version(None)) == versions[1:], walked
        after = read(self.session, ids(self.troupe))
        assert after is not before, walked
        if changes:
            assert after != before, walked
        return found


def test_every_change_to_a_troupes_rules_changes_its_version(
    troupe: Troupe, session: Session
) -> None:
    walk = Walk(troupe, other_troupe(troupe))
    key = read(session, ids(troupe)).rule_set.checks[0].key
    tid = ids(troupe)

    # A check's house strength.
    walk.call("PUT", f"/checks/{key}", {"strength": "off"})
    walk.call("PUT", f"/checks/{key}", {"strength": None})
    # Prices.
    price = walk.call("POST", "/costs", {"category": "attributes", "scheme": "per_dot", "rate": 4})
    walk.call("PUT", f"/costs/{price['id']}", {"scheme": "per_dot", "rate": 5})
    walk.call("DELETE", f"/costs/{price['id']}")
    # Starting picks.
    walk.call("PUT", "/creation/skills", {"rules": [{"rating": 5, "picks": 1}]})
    walk.call("DELETE", "/creation/skills")
    # Downtime allowances.
    allowance = walk.call("POST", "/allowances", {"action_kind": "general", "amount": 4})
    walk.call("PUT", f"/allowances/{allowance['id']}", {"amount": 6})
    walk.call("DELETE", f"/allowances/{allowance['id']}")
    # House options and settings on the troupe's own row.
    walk.call("PUT", "/golconda", {"on": True})
    clans = ["Assamite", "Gangrel", "Malkavian", "Nosferatu", "Toreador", "Tremere", "Ventrue"]
    walk.call("PUT", "/status-ban-clans", {"key": "pillar_clans", "clans": clans})
    walk.call("PUT", "/languages", {"mode": "accelerated"})
    walk.call("PUT", "/starting-blood", {"blood": 3}, changes=False)
    walk.call("PUT", "/diablerie-flaws", {"setting": "remove"}, changes=False)
    walk.call("PUT", "/rare-disciplines", {"on": True}, changes=False)
    walk.call("PUT", "/feeding", {"feeding": "off"}, changes=False)
    walk.call("PUT", "/clan-names", {"assamite": "Assamite"}, changes=False)
    walk.call("PUT", "/clan-rarity", {"rarities": {"Toreador": "rare"}}, changes=False)
    walk.call("PUT", "/default-bloodlines", {"defaults": {"Brujah": "Brujah"}}, changes=False)
    walk.call("PATCH", "", {"name": "Lords of the Long Night"}, by=troupe.lead)
    # Changes to the book's traits.
    lucky = {"category": "merits", "name": "Lucky"}
    walk.call("PUT", "/book-traits", {**lucky, "banned": True, "ban_reason": "Too swingy."})
    walk.call("PUT", "/book-traits", {**lucky, "banned": False})
    # The troupe's own merits and flaws.
    merit = {
        "category": "merits",
        "name": "Child of the Crossroads",
        "points": 2,
        "availability": "building",
        "description": "Knows every back road out of town.",
    }
    house = walk.call("POST", "/house-traits", merit)
    walk.call("PUT", f"/house-traits/{house['id']}", {**merit, "points": 3})
    walk.call("PUT", f"/house-traits/{house['id']}/archived", {"archived": True})
    walk.call("DELETE", f"/house-traits/{house['id']}")
    # The troupe's own checks.
    check = walk.call("POST", "/house-checks", IRON_WILL_FOR_VENTRUE)
    walk.call("PUT", f"/house-checks/{check['id']}", {**IRON_WILL_FOR_VENTRUE, "message": "No."})
    walk.call("DELETE", f"/house-checks/{check['id']}")
    # Teacher rules and written rules: not in the rules read, but in the version.
    teacher = walk.call("POST", "/teacher-rules", LORE_SPECIALISATIONS, changes=False)
    walk.call(
        "PUT",
        f"/teacher-rules/{teacher['id']}",
        {**LORE_SPECIALISATIONS, "actions": 2},
        changes=False,
    )
    walk.call("DELETE", f"/teacher-rules/{teacher['id']}", changes=False)
    written = walk.call("POST", "/written-rules", {"title": "Influence by county"}, changes=False)
    [rule] = written["rules"]
    walk.call("PUT", f"/written-rules/{rule['id']}", {"title": "By county"}, changes=False)
    walk.call("DELETE", f"/written-rules/{rule['id']}", changes=False)
    walk.call("PUT", "/written-rules-public", {"public": True}, changes=False)
    # The troupe's own equipment templates: not in the rules read either.
    template = {"name": "Sheriff's pistol", "kind": "ranged", "grade": "standard", "qualities": []}
    saved = walk.call("POST", "/equipment/templates", template, changes=False)
    walk.call("DELETE", f"/equipment/templates/{saved['id']}", changes=False)
    # What only copying another troupe's settings changes (horatio.troupe_settings_share).
    starting = StartingTraitData(category="backgrounds", name="Resources", rating=1)
    walk.changing(lambda: set_house_starting_trait(session, tid, "vampire", starting))
    kind = ActionKindData(key="hunt", name="Hunt")
    walk.changing(lambda: add_house_action_kind(session, tid, "vampire", kind))
    walk.changing(
        lambda: change_house_action_kind(session, tid, "vampire", replace(kind, name="Stalk"))
    )
    # Its own row, written from anywhere.
    walk.changing(
        lambda: session.execute(
            update(TroupeRow).where(TroupeRow.id == tid).values(natural_linguist_doubles=False)
        )
    )

    # Every change those routers make was walked.
    walked = [(method, url.removeprefix(f"/troupes/{troupe.id}")) for method, url in walk.walked]
    for route in routes(RULES_ROUTERS):
        if NOT_RULES.search(route.path):
            continue
        local = route.path.removeprefix("/troupes/{troupe_id}")
        wild = re.sub(r"\{[^}]+:path\}", ".+", local)
        pattern = re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", wild) + "$")
        for method in changing(route):
            assert any(m == method and pattern.match(u) for m, u in walked), (method, route.path)


def routes(modules: tuple[Any, ...]) -> list[APIRoute]:
    """The routes that change something, of each module's router."""
    return [
        r
        for module in modules
        for r in module.router.routes
        if isinstance(r, APIRoute) and changing(r)
    ]


def changing(route: APIRoute) -> set[str]:
    return (route.methods or set[str]()) - {"GET", "HEAD"}


def test_the_routers_walked_are_found() -> None:
    """The walk above checks the routes it finds, so it must find them."""
    paths = {r.path for r in routes(RULES_ROUTERS)}
    assert "/troupes/{troupe_id}/costs" in paths
    assert "/troupes/{troupe_id}/house-traits/{house_trait_id}" in paths
    assert "/troupes/{troupe_id}/book-traits" in paths

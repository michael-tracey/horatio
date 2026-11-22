"""Account › Notifications (#1053): every kind of notification Horatio sends is on the
page, each comes where the person chose, and with nothing chosen everything comes as
it did before the page."""

import ast
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import horatio
from horatio import notification_choices, notification_emails, notifications, posts, web_push
from horatio.config import get_settings
from horatio.connectors import email
from horatio.models import EmailNotice, Notification, PushNotice, User
from horatio.notification_choices import TOPICS, Topic, Way
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_boon_reports_told import court, told_path  # noqa: F401
from tests.test_api_boon_standings import at_home
from tests.test_api_boon_talons import Talons
from tests.test_email_connector import FakeSMTP
from tests.test_web_push import Browser, FakePushService, endpoint, pushes, turn_on  # noqa: F401

SOURCE = Path(horatio.__file__).parent
# The functions that send a notification of a kind their caller names.
SENDERS = {"notify", "tell", "told", "tell_staff"}
# Where a notification's kind isn't written out at the call: each function, and why.
PASSED_ON = {
    # Of the kind its own callers name.
    ("equipment.py", "tell"),
    ("play_on_others.py", "tell"),
    ("quests.py", "tell"),
    ("titles.py", "tell_staff"),
    # `KIND`, setting.changed.
    ("setting_notices.py", "changed"),
    # A post's kind and "published" (the others, f"{post.kind}.missed", are read).
    ("posts.py", "tell_everyone"),
    # A task's kind, as the bell shows it (horatio.notifications).
    ("notifications.py", "approval_waiting"),
    ("notifications.py", "notify"),
}
# Its own `notify`, an email about a suspension, not a notification (account_emails).
NOT_NOTIFICATIONS = {"suspensions.py"}


def kinds_in(node: ast.AST) -> set[str]:
    """The notification kinds a call or an f-string names."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        parts = node.value.split(".")
        if len(parts) == 2 and all(p.replace("_", "").isalpha() and p.islower() for p in parts):
            return {node.value}
    if isinstance(node, ast.JoinedStr):
        # f"{post.kind}.missed", for each kind of post.
        last = node.values[-1]
        if (
            len(node.values) == 2
            and isinstance(last, ast.Constant)
            and isinstance(last.value, str)
            and last.value.startswith(".")
            and "post.kind" in ast.unparse(node.values[0])
        ):
            return {f"{kind}{last.value}" for kind in posts.KINDS}
    return set()


def scan() -> tuple[set[str], set[tuple[str, str]]]:
    """Every notification kind named in Horatio's code, where a notification is sent or a
    task made; and each function where the kind isn't written out at the call."""
    found: set[str] = set()
    dynamic: set[tuple[str, str]] = set()
    for path in sorted(SOURCE.rglob("*.py")):
        where = str(path.relative_to(SOURCE))
        if where in NOT_NOTIFICATIONS:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            # setting_notices.KIND, and posts' kind = f"{post.kind}.published"
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in ("KIND", "kind") for t in node.targets
            ):
                found |= kinds_in(node.value)
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef):
                continue
            for call in ast.walk(function):
                if not isinstance(call, ast.Call):
                    continue
                name = call.func.attr if isinstance(call.func, ast.Attribute) else None
                name = name or (call.func.id if isinstance(call.func, ast.Name) else None)
                if name == "Item":
                    # A task, as the bell lists it.
                    for keyword in call.keywords:
                        if keyword.arg == "kind" and isinstance(keyword.value, ast.Constant):
                            found.add(str(keyword.value.value))
                    continue
                if name == "queue" and ast.unparse(call.func) == "notification_emails.queue":
                    kind = call.args[2]
                    if isinstance(kind, ast.Constant):
                        found.add(str(kind.value))
                    else:
                        dynamic.add((where, function.name))
                    continue
                if name not in SENDERS:
                    continue
                named = set().union(*(kinds_in(a) for a in call.args), set())
                found |= named
                if name == "notify" and not named:
                    dynamic.add((where, function.name))
    return found, dynamic


def covered(kind: str) -> bool:
    try:
        notification_choices.topic_for(kind)
    except notification_choices.UnknownKind:
        return False
    return True


def test_every_kind_sent_is_on_the_page() -> None:
    """A kind of notification no topic covers fails here, and is refused by `notify`."""
    found, dynamic = scan()
    assert len(found) > 70
    assert sorted(k for k in found if not covered(k)) == []
    # A kind made where it is sent, not named there, is listed here once checked.
    assert dynamic == PASSED_ON
    # And nothing on the page that is never sent, but each kind of approval.
    listed = {k for t in TOPICS for k in t.kinds if not k.endswith(".*")}
    assert sorted(listed - found) == []
    with pytest.raises(notification_choices.UnknownKind):
        notification_choices.topic_for("made.up")


def test_each_kind_has_one_topic() -> None:
    listed = [k for t in TOPICS for k in t.kinds]
    assert len(listed) == len(set(listed))
    assert len({t.name for t in TOPICS}) == len(TOPICS)
    assert notification_choices.topic_for("approval.bond_drink").name == "approvals"


# --- the page ---------------------------------------------------------------------------


def page(person: Person) -> dict[str, Any]:
    response = person.client.get("/notification-settings")
    assert response.status_code == 200, response.text
    return response.json()


def shown(person: Person) -> dict[str, dict[str, Any]]:
    """Each topic on the person's page, by name."""
    return {t["name"]: t for g in page(person)["groups"] for t in g["topics"]}


def routes(topic: dict[str, Any]) -> dict[str, tuple[bool, bool]]:
    return {r["way"]: (r["on"], r["always"]) for r in topic["routes"]}


def test_the_page_lists_every_topic_that_applies(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    troupe = Troupe(client_for, session)
    # The custodian who also runs a troupe sees every one, in the catalogue's order.
    ok_(
        troupe.lead.client.put(
            f"/troupes/{troupe.id}/staff",
            json={"handle": troupe.custodian.handle, "role": "storyteller"},
        )
    )
    names = [t["name"] for g in page(troupe.custodian)["groups"] for t in g["topics"]]
    assert names == [t.name for t in TOPICS]
    # Staff see staff work, but not the custodian's.
    groups = [g["name"] for g in page(troupe.narrator)["groups"]]
    assert groups == ["account", "characters", "downtimes", "boons", "troupes", "blog", "staff"]
    # A player sees neither.
    groups = [g["name"] for g in page(troupe.player)["groups"]]
    assert groups == ["account", "characters", "downtimes", "boons", "troupes", "blog"]
    assert client_for().get("/notification-settings").status_code == 401


def ok_(response: Any) -> Any:
    assert response.status_code < 300, response.text
    return response.json()


def test_the_locked_ones_say_so(client_for: Callable[[], TestClient]) -> None:
    person = sign_up(client_for, "locked")
    topics = shown(person)
    assert routes(topics["security"]) == {"bell": (True, True)}
    assert routes(topics["account_emails"]) == {"email": (True, True)}
    # New blog articles: in the bell unless turned off, and never by email or push (#1165).
    assert routes(topics["blog_new"]) == {"bell": (True, False)}
    # Teaching asked of your character: always in the bell; pushed if you tick it (#1097).
    assert routes(topics["teaching"]) == {"bell": (True, True), "push": (False, False)}
    assert topics["teaching"]["task"] is True
    for way in ("bell", "email", "push"):
        refused = person.client.put(
            "/notification-settings", json={"topic": "security", "way": way, "on": False}
        )
        assert refused.status_code == (409 if way == "bell" else 422), refused.text
    refused = person.client.put(
        "/notification-settings", json={"topic": "nothing", "way": "bell", "on": False}
    )
    assert refused.status_code == 404
    # Nor through the settings themselves: there is no setting to change.
    assert person.client.patch("/preferences", json={"bell_security": False}).status_code == 422
    assert person.client.patch("/preferences", json={"bell_news": "no"}).status_code == 422


# --- defaults ---------------------------------------------------------------------------

# Every setting there was before the page (#106, #510, #511), with its default.
BEFORE = {
    "email_downtime": False,
    "email_downtime_reminders": False,
    "email_approvals": False,
    "email_troupe_requests": False,
    "email_renames": False,
    "email_pictures": False,
    "email_titles": False,
    "bell_news": True,
    "email_news": False,
    "bell_announcements": True,
    "email_announcements": True,
}
# The kinds each came under.
EMAILED_BEFORE = {
    "downtime": ("downtime.delivered",),
    "downtime_reminders": ("downtime.reminder",),
    "approvals": ("approval.discipline", "approval.home_troupe_change"),
    "troupe_requests": ("troupe_request", "troupe_request.approved", "troupe_request.declined"),
    "renames": ("character.renamed",),
    "pictures": ("picture.removed",),
    "titles": ("title.chosen", "title.made_active", "title.given_up"),
    "news": ("news.published",),
    "announcements": ("announcement.published",),
}


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSMTP]:
    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(email, "smtp_factory", fake)
    yield fake


def message_kinds() -> list[str]:
    """Every kind the bell keeps as a message, not a task."""
    return [k for t in TOPICS if not t.task for k in t.kinds]


def user_of(session: Session, person: Person) -> User:
    return session.get_one(User, uuid.UUID(person.id))


def sent(session: Session, user: User, kind: str) -> tuple[bool, bool]:
    """Send `user` a notification of `kind`: whether it reached their bell, and whether
    an email waits to go."""
    notifications.notify(session, [user.id], kind, f"About {kind}", "/characters")
    bell = session.scalar(
        select(Notification.id).where(Notification.user_id == user.id, Notification.kind == kind)
    )
    mailed = session.scalar(
        select(EmailNotice.id).where(
            EmailNotice.user_id == user.id, EmailNotice.summary == f"About {kind}"
        )
    )
    return bell is not None, mailed is not None


def test_the_settings_from_before_keep_their_names_and_defaults() -> None:
    assert {k: v for k, v in notification_choices.SETTINGS.items() if k in BEFORE} == BEFORE
    for name, kinds in EMAILED_BEFORE.items():
        for kind in kinds:
            assert notification_choices.topic_for(kind).name == name


def test_with_nothing_chosen_everything_comes_as_before(
    client_for: Callable[[], TestClient], session: Session, mail: FakeSMTP
) -> None:
    """Before the page every message came to the bell, and by email only troupe
    announcements, unless the person chose otherwise."""
    user = user_of(session, sign_up(client_for, "defaults"))
    for kind in message_kinds():
        bell, mailed = sent(session, user, kind)
        assert bell, kind
        assert mailed == (kind == "announcement.published"), kind


def test_what_people_chose_before_still_holds(
    client_for: Callable[[], TestClient], session: Session, mail: FakeSMTP
) -> None:
    user = user_of(session, sign_up(client_for, "chose-before"))
    user.preferences = {"email_downtime": True, "bell_news": False, "email_announcements": False}
    session.flush()
    assert sent(session, user, "downtime.delivered") == (True, True)
    assert sent(session, user, "news.published") == (False, False)
    assert sent(session, user, "announcement.published") == (True, False)
    assert sent(session, user, "character.renamed") == (True, False)


def choosable() -> list[tuple[Topic, Way]]:
    return [
        (topic, way)
        for topic in TOPICS
        for way in topic.routes
        if topic.choosable(way) and topic.kinds
    ]


def pushed_to(session: Session, kind: str) -> bool:
    """Whether a push waits to go of what `sent` sent."""
    return (
        session.scalar(select(PushNotice.id).where(PushNotice.summary == f"About {kind}"))
        is not None
    )


@pytest.mark.parametrize(("topic", "way"), choosable(), ids=lambda v: getattr(v, "name", v))
def test_each_choice_is_honoured(
    topic: Topic,
    way: Way,
    client_for: Callable[[], TestClient],
    session: Session,
    mail: FakeSMTP,
    pushes: FakePushService,  # noqa: F811
) -> None:
    person = sign_up(client_for, "chooser")
    user = user_of(session, person)
    # On a phone of theirs (#1054).
    assert turn_on(person, Browser(endpoint("chooser"))).status_code == 200
    kind = topic.kinds[0].replace("*", "review")
    default = topic.routes[way].default
    changed = person.client.put(
        "/notification-settings", json={"topic": topic.name, "way": way, "on": not default}
    )
    assert changed.status_code == 200, changed.text
    session.refresh(user)
    assert notification_choices.chosen(user, topic, way) is not default
    if topic.task:
        # A task's bell is always on; its email and push go as the work arrives.
        notification_emails.queue(session, [user.id], kind, "Waiting", "/troupes")
        web_push.queue(session, [user.id], kind, "Waiting", "/troupes")
        mailed = session.scalar(select(EmailNotice.id).where(EmailNotice.user_id == user.id))
        pushed = session.scalar(select(PushNotice.id).where(PushNotice.summary == "Waiting"))
        assert ((mailed if way == "email" else pushed) is not None) == (not default)
        return
    bell, mailed = sent(session, user, kind)
    came = {"bell": bell, "email": mailed, "push": pushed_to(session, kind)}
    assert came[way] == (not default)
    # The other ways are as they were.
    for other, route in topic.routes.items():
        if other != way:
            assert came[other] == route.default, other


def test_the_always_ones_come_whatever_is_stored(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    user = user_of(session, sign_up(client_for, "always"))
    user.preferences = {"bell_security": False}
    session.flush()
    assert sent(session, user, "account.viewed_as")[0] is True


def test_an_important_announcement_is_emailed_even_so(
    client_for: Callable[[], TestClient], session: Session, mail: FakeSMTP
) -> None:
    user = user_of(session, sign_up(client_for, "important"))
    user.preferences = {"email_announcements": False, "bell_announcements": False}
    session.flush()
    notification_emails.queue(
        session, [user.id], "announcement.published", "Game moved", "/troupes", forced=True
    )
    assert session.scalar(select(EmailNotice.forced).where(EmailNotice.user_id == user.id))


# --- unsubscribe links ------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(EMAILED_BEFORE))
def test_links_already_sent_turn_off_the_same_choice(
    name: str, client_for: Callable[[], TestClient], session: Session
) -> None:
    person = sign_up(client_for, "unsubscriber")
    user = user_of(session, person)
    ok_(
        person.client.put(
            "/notification-settings", json={"topic": name, "way": "email", "on": True}
        )
    )
    session.refresh(user)
    # A link as an email before the page made it: the topic's name, signed.
    token = f"{user.id}.{name}.{notification_emails.signature(user, name)}"
    stopped = client_for().post(f"/unsubscribe/{token}")
    assert stopped.status_code == 200, stopped.text
    session.refresh(user)
    topic = notification_choices.BY_NAME[name]
    assert notification_choices.chosen(user, topic, "email") is False
    # The bell is as it was.
    assert notification_choices.chosen(user, topic, "bell") is True
    if name in shown(person):
        assert routes(shown(person)[name])["email"] == (False, False)


def test_a_link_for_a_topic_that_never_emails_does_nothing(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    user = user_of(session, sign_up(client_for, "never-emailed"))
    for name in ("security", "setting", "teaching"):
        token = f"{user.id}.{name}.{notification_emails.signature(user, name)}"
        assert client_for().post(f"/unsubscribe/{token}").status_code == 404, name


# --- choices that go with a role (#1018) ------------------------------------------------


def roles(person: Person) -> list[dict[str, Any]]:
    return shown(person)["boon_reports"]["roles"]


def test_reported_boons_show_each_role_and_stay_in_step(court: Talons) -> None:  # noqa: F811
    storyteller, harpy = court.troupe.storyteller, court.harpy_player
    [staff] = roles(storyteller)
    assert (staff["troupe_id"], staff["role"], staff["on"]) == (court.troupe.id, "staff", False)
    [keeper] = roles(harpy)
    assert (keeper["role"], keeper["on"], keeper["office"]) == ("keeper", True, "Harpy")
    assert keeper["character_name"] == "Hestia"
    assert roles(court.troupe.player) == []

    # Changed beside the role, the page shows it; one choice, kept in one place.
    ok_(storyteller.client.put(told_path(court), json={"on": True, "role": "staff"}))
    assert roles(storyteller)[0]["on"] is True
    ok_(harpy.client.put(told_path(court), json={"on": False, "role": "keeper"}))
    assert roles(harpy)[0]["on"] is False
    assert ok_(harpy.client.get(told_path(court)))["keeper"] is False

    # A Lesser Harpy who approves reported boons, as the troupe names the office.
    ok_(court.give(court.iris, can_review=True))
    [talon] = roles(court.iris_player)
    assert (talon["office"], talon["on"]) == ("Lesser Harpy", True)


def test_where_the_troupe_sends_it_itself(
    client_for: Callable[[], TestClient], session: Session, mail: FakeSMTP
) -> None:
    """Downtime results and quest news through the troupe's own connectors: its choice,
    shown to the players at home there."""
    troupe = Troupe(client_for, session)
    at_home(troupe, troupe.player, "Agnes", "Brujah")
    assert shown(troupe.player)["downtime"]["troupes_send"] == []
    ok_(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/connectors/email",
            json={"enabled": True, "settings": {"reply_to": "sts@example.com"}},
        )
    )
    topics = shown(troupe.player)
    sends = [
        {
            "troupe_id": troupe.id,
            "troupe_name": "Lords of the Night",
            "connectors": ["Email"],
            # No Discord, so no character's own channel to turn off (#1077).
            "own_channels": [],
        }
    ]
    assert topics["downtime"]["troupes_send"] == sends
    assert topics["quests"]["troupes_send"] == sends
    assert topics["renames"]["troupes_send"] == []
    # Not to a stranger, with no character at home there.
    assert shown(troupe.stranger)["downtime"]["troupes_send"] == []

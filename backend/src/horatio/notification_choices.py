"""Every kind of notification Horatio sends, and where each person has it go
(#1053): Account › Notifications.

Each notification kind (`Notification.kind`, such as downtime.delivered) belongs to
one `Topic`, and topics come in `GROUPS` as the page shows them. A topic says, for
each way it can come (`Route`): the bell, email, or push to the person's phones
(#1054), whether the person chooses it (and what it is until they do) or it always
comes. Work waiting on someone (a task: an approval to decide) is always in the
bell, and goes when the work is done; so is word about their account's safety. A
topic with no route for a way never comes that way. `horatio.notifications.notify`,
`horatio.notification_emails.queue` and `horatio.web_push.queue` honour each
person's choice; a kind no topic covers is refused there, so a new kind can't be
sent without a line on the page.

A choice is kept with the person's other settings (`users.preferences`, only where
it differs from the default), named `<way>_<topic>`: `email_downtime`,
`bell_news`. Those are the names the settings had before this page (#106, #510,
#511), so what people chose then, and the unsubscribe links in emails already sent
(by topic name), still hold. Push came later (#1054): `push_downtime`. Which devices
it goes to is kept apart, a row for each (horatio.web_push).

Two things the person doesn't choose here, and the page says so:
- Whether they're told at all, for a notification that goes with a role: reported
  boons, chosen as staff or as the Harpy or a Lesser Harpy (horatio.boon_reports_told,
  #1018). That choice is kept where #1018 keeps it, and the page changes it there.
- A troupe's connectors (CONTEXT.md: Connector): downtime results and quest news
  that the troupe also sends to Discord, or by its own email. That's the troupe's
  choice (`connectors`). The one part of it the player chooses is their character's
  own channel on the troupe's Discord (#1077): they can turn off what the connector
  posts there, character by character (`own_channel_on`). The troupe's shared
  channels, and the result in Horatio, are unchanged.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from horatio.models import User

# The ways a notification can come to a person. The bell is Horatio's own; push is
# to the phones and computers where they turned it on (#1054, horatio.web_push).
Way = Literal["bell", "email", "push"]
WAYS: tuple[Way, ...] = ("bell", "email", "push")

# Who a topic is for: anyone, the staff of a troupe, or the custodian.
Audience = Literal["everyone", "staff", "custodian"]


@dataclass(frozen=True)
class Route:
    """One way a topic comes: chosen by the person, on or off until they do, or
    `always`."""

    default: bool = True
    always: bool = False


ON = Route(True)
OFF = Route(False)
ALWAYS = Route(always=True)


@dataclass(frozen=True)
class Topic:
    # As settings and unsubscribe links name it.
    name: str
    title: str
    # One line saying what comes under it.
    hint: str
    # The notification kinds it covers: a kind, or "approval.*" for every kind under
    # approval.
    kinds: tuple[str, ...]
    routes: dict[Way, Route] = field(
        default_factory=lambda: {"bell": ON, "email": OFF, "push": OFF}
    )
    # Work waiting on the person, worked out from what waits (horatio.notifications
    # TASK_SOURCES): in the bell until it is done.
    task: bool = False
    # The troupe may send it through its connectors too: its Discord, its own email.
    connectors: bool = False
    # Whether the person is told at all depends on a role, chosen beside it (#1018).
    by_role: bool = False
    # Where the switches for the characters' own Discord channels sit (#1077). They
    # cover downtime results and quest news alike, so they're shown once.
    own_channels: bool = False

    def setting(self, way: Way) -> str:
        return f"{way}_{self.name}"

    def choosable(self, way: Way) -> bool:
        route = self.routes.get(way)
        return route is not None and not route.always


@dataclass(frozen=True)
class Group:
    name: str
    title: str
    audience: Audience
    topics: tuple[Topic, ...]


# Work waiting on someone: always in the bell; by email where it says so.
TASK_BELL: dict[Way, Route] = {"bell": ALWAYS}
# What someone at a game wants on their phone at once: pushed until they turn it off,
# on each device where they turn push on (#1054). Everything else that can be pushed
# isn't until they choose it.
PUSHED: dict[Way, Route] = {"bell": ON, "email": OFF, "push": ON}

GROUPS = (
    Group(
        "account",
        "Your account",
        "everyone",
        (
            Topic(
                "security",
                "Your account's safety",
                "The custodian viewing Horatio as you, merging your accounts, moving a"
                " character to or from you, or resetting your two-step sign-in. Always in"
                " the bell.",
                (
                    "account.viewed_as",
                    "account.merged",
                    "character.moved",
                    "account.two_step_reset",
                ),
                {"bell": ALWAYS},
            ),
            Topic(
                "account_emails",
                "Sign-in and suspension emails",
                "Links to set a new password or confirm a new email, word that your accounts"
                " were merged, and your account being suspended or let back in. Always by"
                " email.",
                (),
                {"email": ALWAYS},
            ),
            Topic(
                "troupe_requests",
                "Troupe requests",
                "The answer to a troupe you asked for and, for the custodian, each new"
                " troupe people ask for.",
                ("troupe_request", "troupe_request.approved", "troupe_request.declined"),
                {"bell": ALWAYS, "email": OFF, "push": OFF},
            ),
        ),
    ),
    Group(
        "characters",
        "Your characters",
        "everyone",
        (
            Topic(
                "sheets",
                "Changes to your sheets",
                "Staff giving or removing a house trait or an exception, a diablerie recorded"
                " or declined, an Embrace, and free changes ending.",
                (
                    "sheet.given",
                    "sheet.diablerie",
                    "sheet.embrace",
                    "character.free_changes_ended",
                ),
            ),
            Topic(
                "backstories",
                "Backstories",
                "Your troupe sending a backstory back to you, or approving it.",
                ("backstory.returned", "backstory.approved"),
            ),
            Topic(
                "renames",
                "Character renames",
                "When a character you play or run is renamed.",
                ("character.renamed",),
            ),
            Topic(
                "pictures",
                "Pictures removed",
                "When someone removes a picture you added.",
                ("picture.removed",),
            ),
            Topic(
                "bonds",
                "Blood bonds",
                "A drink to confirm, a bond weakening or fading, and the answer to one you"
                " reported.",
                ("sheet.bond",),
                PUSHED,
            ),
            Topic(
                "equipment",
                "Equipment",
                "Items given, changed, passed on, taken back or discarded, and items about to"
                " expire.",
                (
                    "equipment.given",
                    "equipment.changed",
                    "equipment.passed",
                    "equipment.taken_back",
                    "equipment.discarded",
                    "equipment.restored",
                    "equipment.expiring",
                    "equipment.expired",
                ),
            ),
            Topic(
                "play",
                "Powers used in play",
                "A power used on your character, ended or taken back, and the answer to one"
                " you used.",
                (
                    "play.effect_on_you",
                    "play.used_on_you",
                    "play.effect_ended_on_you",
                    "play.effect_acknowledged",
                    "play.effect_disputed",
                ),
                PUSHED,
            ),
            Topic(
                "teaching",
                "Teaching to confirm",
                "Teaching asked of your character, at the cost of their Willpower. Always in"
                " the bell until you answer.",
                ("teaching",),
                # Pushed as it is asked, to those who tick it (#1097).
                {"bell": ALWAYS, "push": OFF},
                task=True,
            ),
            Topic(
                "quests",
                "Quests",
                "A quest's requirements and results, one you can join, a quest closed, a tale"
                " approved, and the answer to a quest request.",
                (
                    "quest.sent",
                    "quest.result",
                    "quest.closed",
                    "quest.shared",
                    "quest.tale",
                    "quest.answered",
                ),
                connectors=True,
            ),
            Topic(
                "projects",
                "Projects",
                "A project under way, finished, or made a quest request.",
                ("project.confirmed", "project.finished", "project.made_quest_request"),
            ),
            Topic(
                "locations",
                "Locations lost",
                "When your character no longer controls a location.",
                ("location.lost",),
            ),
            Topic(
                "npcs",
                "NPCs given to you",
                "A troupe giving you an NPC, and someone claiming one with your claim link.",
                ("npc.given", "npc.claimed"),
            ),
            Topic(
                "discord_channels",
                "Your Discord channels",
                "An invite to a troupe's Discord server, and your character's channel there"
                " being ready.",
                ("discord.invite", "discord.channel_ready"),
            ),
        ),
    ),
    Group(
        "downtimes",
        "Downtimes",
        "everyone",
        (
            Topic(
                "downtime",
                "Downtime results",
                "When your downtime results are ready, or updated.",
                ("downtime.delivered",),
                PUSHED,
                connectors=True,
                own_channels=True,
            ),
            Topic(
                "downtime_reminders",
                "Downtime reminders",
                "When staff remind you that a downtime isn't submitted yet.",
                ("downtime.reminder",),
            ),
            Topic(
                "nominations",
                "Player Nominations",
                "A cycle's Player Nominations going up, and being named in them.",
                ("nominations.published", "nominations.about"),
            ),
            Topic(
                "remembrances",
                "Remembrances",
                "A troupe's remembrances of a retired character going up.",
                ("remembrance.published",),
            ),
        ),
    ),
    Group(
        "boons",
        "Boons",
        "everyone",
        (
            Topic(
                "boon_reports",
                "Boons players report",
                "Each boon a player reports to the ledger. Only staff who ask, the Harpy and"
                " Lesser Harpies who approve reported boons are told: choose that for each"
                " troupe below.",
                ("boon.reported",),
                by_role=True,
            ),
            Topic(
                "boons",
                "Your boons",
                "A boon you reported accepted or not, one of yours traded, and an audit given"
                " to your character.",
                ("boon.accepted", "boon.rejected", "boon.traded", "boon.audit"),
                PUSHED,
            ),
        ),
    ),
    Group(
        "troupes",
        "Troupe news",
        "everyone",
        (
            Topic(
                "announcements",
                "Troupe announcements",
                "Each announcement from your troupes' staff, such as a game moved. By email"
                " too unless you turn it off; one they mark important is emailed anyway.",
                ("announcement.published",),
                {"bell": ON, "email": ON, "push": ON},
            ),
            Topic(
                "news",
                "Troupe news",
                "Each new story from your troupes' news agencies. Not by email unless you turn"
                " it on, so a busy week doesn't fill your inbox.",
                ("news.published",),
            ),
            Topic(
                "proposals",
                "Stories and announcements you proposed",
                "One you proposed being published or declined.",
                (
                    "news.proposal_published",
                    "news.proposal_declined",
                    "announcement.proposal_published",
                    "announcement.proposal_declined",
                ),
            ),
            Topic(
                "setting",
                "Setting changes",
                "Staff changing a troupe's setting, gathered into one notice while they work.",
                ("setting.changed",),
                {"bell": ON},
            ),
            Topic(
                "troupe_status",
                "Troupes archived or reopened",
                "A troupe you play in or run being archived, or opened again.",
                ("troupe.archived", "troupe.reopened"),
            ),
        ),
    ),
    Group(
        "staff",
        "Staff work",
        "staff",
        (
            Topic(
                "approvals",
                "Approvals waiting",
                "Requests in troupes where you approve changes. Always in the bell until decided.",
                ("approval.*",),
                {"bell": ALWAYS, "email": OFF, "push": OFF},
                task=True,
            ),
            Topic(
                "quest_requests",
                "Quest requests waiting",
                "Quest requests to answer, or assigned to you. Always in the bell until answered.",
                ("quest_request",),
                TASK_BELL,
                task=True,
            ),
            Topic(
                "titles",
                "Titles chosen",
                "When a player in a troupe you run chooses, gives up or switches their"
                " character's title.",
                ("title.chosen", "title.made_active", "title.given_up"),
            ),
            Topic(
                "backstory_reviews",
                "Backstories to read again",
                "A backstory revised and back with you, or changed since it was approved.",
                ("backstory.resubmitted", "backstory.changed"),
            ),
            Topic(
                "project_reviews",
                "Projects proposed",
                "A player proposing a project, and a change of Path finished.",
                ("project.proposed", "project.path_changed"),
            ),
            Topic(
                "location_reviews",
                "Locations at risk",
                "A location to forfeit, and Out of Code growing after a game.",
                ("location.forfeit", "location.out_of_code"),
            ),
            Topic(
                "sires",
                "Sires changed",
                "A player changing their character's sire.",
                ("character.sire",),
            ),
            Topic(
                "retainers",
                "Retainers neglected",
                "A character who couldn't pay a retainer's upkeep.",
                ("retainer.neglected",),
            ),
            Topic(
                "remembrance_asks",
                "Remembrances asked for",
                "A player asking for remembrances of a retired character.",
                ("remembrance.asked",),
            ),
            Topic(
                "leaving",
                "Characters leaving",
                "A character leaving your troupe as its home.",
                ("troupe.left_home",),
            ),
            Topic(
                "posts_missed",
                "Posts not published",
                "A scheduled story or announcement whose time came while the troupe was archived.",
                ("news.missed", "announcement.missed"),
            ),
            Topic(
                "merges",
                "Accounts merged",
                "The custodian merging two accounts of one person, moving their characters"
                " or their place on staff in a troupe you lead.",
                ("troupe.accounts_merged",),
            ),
            Topic(
                "discord_problems",
                "Discord channel problems",
                "A character's Discord channel Horatio couldn't make or keep in step.",
                ("discord.channel_problem",),
            ),
        ),
    ),
    Group(
        "custodian",
        "Custodian",
        "custodian",
        (
            Topic(
                "sign_ups",
                "Sign-ups",
                "Each new account.",
                ("account.signed_up",),
            ),
        ),
    ),
)

TOPICS = tuple(topic for group in GROUPS for topic in group.topics)
BY_NAME = {topic.name: topic for topic in TOPICS}
GROUP_OF = {topic.name: group for group in GROUPS for topic in group.topics}
# Every setting a person can change here, with its default.
SETTINGS: dict[str, bool] = {
    topic.setting(way): route.default
    for topic in TOPICS
    for way, route in topic.routes.items()
    if not route.always
}


class UnknownKind(ValueError):
    """A notification kind no topic covers: add it to a topic in GROUPS."""


def topic_for(kind: str) -> Topic:
    """The topic a notification kind comes under."""
    for topic in TOPICS:
        for covered in topic.kinds:
            if kind == covered or (covered.endswith(".*") and kind.startswith(covered[:-1])):
                return topic
    raise UnknownKind(f"No topic in horatio.notification_choices covers {kind!r}.")


def chosen(user: User, topic: Topic, way: Way) -> bool:
    """Whether the person has `topic` come `way`: always, as they chose, or as it is
    until they choose."""
    route = topic.routes.get(way)
    if route is None:
        return False
    if route.always:
        return True
    value: Any = (user.preferences or {}).get(topic.setting(way), route.default)
    return value if isinstance(value, bool) else route.default


def kept(changes: dict[str, Any]) -> dict[str, bool]:
    """The changes among `changes` that are choices here, each checked to be on or off.
    Raises ValueError for one that isn't."""
    found: dict[str, bool] = {}
    for name, value in changes.items():
        if name not in SETTINGS:
            continue
        if not isinstance(value, bool):
            raise ValueError(f"{name} is on or off: true or false.")
        found[name] = value
    return found


# The characters whose own Discord channel the person has turned off (#1077), by id:
# what a troupe's Discord connector would post to that channel is skipped. On until
# they turn it off; kept with their other settings, like the choices above.
OWN_CHANNELS_OFF = "own_channels_off"


def own_channel_on(user: User, character_id: uuid.UUID) -> bool:
    """Whether the troupe's Discord connector may post to the character's own channel,
    as its player chose."""
    off: Any = (user.preferences or {}).get(OWN_CHANNELS_OFF)
    return not (isinstance(off, list) and str(character_id) in off)


def choose_own_channel(user: User, character_id: uuid.UUID, on: bool) -> None:
    """Turn the character's own Discord channel on or off for its player."""
    stored = dict(user.preferences or {})
    off = {str(c) for c in stored.pop(OWN_CHANNELS_OFF, None) or []} - {str(character_id)}
    if not on:
        off.add(str(character_id))
    if off:
        stored[OWN_CHANNELS_OFF] = sorted(off)
    user.preferences = stored

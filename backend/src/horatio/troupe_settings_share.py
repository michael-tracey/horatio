"""Sharing a troupe's settings (issue #521): exporting its customisation as a file,
and importing one into another troupe, merging.

**The document** is what Export downloads and Import reads: a format version, the
Horatio and rule set versions it was made against, the source troupe's name, and
its settings by section, grouped as Customise groups them. It never holds an id:
traits, categories and checks are named by their keys and names. Only what differs
from Horatio's default goes in: a troupe setting at its default is left out, and
every row a troupe keeps for itself (a house merit, a house check, a price) is a
change by definition. Archived and retired items are left out. What is never
carried, and why, is listed in `NOT_EXPORTED_COLUMNS` and `NOT_EXPORTED_TABLES`; a
test fails on a column or table that is in neither those nor the export.

**Reviewing** compares a document with the troupe it is going into, item by item:
**New**, **Changes yours** (with what it is now and what it would be), **Same as
yours**, or **Can't import** (with why: a trait this troupe's rule set lacks, say).
The client edits the document's text, and finds and replaces in it, between
reviewing and applying.

**Applying** takes the edited document and the items ticked, in one transaction:
all of them or none. Each goes through the same service as its editor in Customise
(horatio.house_traits, horatio.house_checks, horatio.keywords, the rule store's
checks of prices and starting points...), so an imported item is checked exactly as
one made by hand; a failure names the item and saves nothing. It merges: what
matches is overwritten, and nothing the document leaves out is reset or removed.
House merits and flaws go first, so the rules that name them can find them. One
entry in the troupe's log says who imported what, from where.
"""

import json
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, Any, Literal, cast, get_args

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import (
    audit,
    backstories,
    book_traits,
    downtimes,
    feeding,
    free_changes,
    game_xp,
    house_checks,
    house_traits,
    influence_lookups,
    keywords,
    languages,
    play_tabs,
    posts,
    quests,
    responses,
    retainer_upkeep,
    specializations,
    teaching,
    titles,
    troupe_settings,
    written_rules,
)
from horatio.models import (
    HouseCheck,
    HouseTrait,
    NewsAgency,
    RandomTable,
    RuleSet,
    TeacherRule,
    Troupe,
    TroupeSpecialization,
    User,
    WrittenRule,
)
from horatio.rules import conditions
from horatio.rules import locations as location_catalogue
from horatio.rules.house_checks import HouseCheckData, is_house_check
from horatio.rules.model import (
    ActionKindData,
    AllowanceRuleData,
    CostRuleData,
    CreationRuleData,
    StartingTraitData,
    TroupeRules,
)
from horatio.rules.splats import SPLATS
from horatio.rules.store import (
    TiedHouseRule,
    add_house_action_kind,
    add_house_allowance_rule,
    add_house_rule,
    change_house_action_kind,
    change_house_allowance_rule,
    change_house_rule,
    check_house_creation_conditions,
    check_house_price,
    forget_rules,
    house_allowance_rules,
    house_cost_rules,
    read_troupe_rules,
    same_subject,
    set_check_override,
    set_house_creation_rules,
    set_house_starting_trait,
)
from horatio.rules.teachers import TeacherRuleData
from horatio.sheets import sync_troupe_fixed_ratings

FORMAT = "horatio-troupe-settings"
FORMAT_VERSION = 1
# The most a document may be, as a request: around 2 MB.
MAX_BYTES = 2 * 1024 * 1024

Splat = Annotated[str, Field(min_length=1, max_length=20)]
Name = Annotated[str, Field(min_length=1, max_length=200)]


Blood = Annotated[int, Field(ge=0, le=30)]
Chart = Annotated[list[int], Field(max_length=20)]


class Strict(BaseModel):
    """Refuses keys it doesn't know: the file is untrusted."""

    model_config = ConfigDict(extra="forbid")


# --- the items ---------------------------------------------------------------------------


class SettingItem(Strict):
    """One of the troupe's own settings (a column of `troupes`), by its key."""

    type: Literal["setting"] = "setting"
    key: str = Field(max_length=60)
    value: JsonValue


class CheckItem(Strict):
    """How the troupe plays one of the rule set's checks."""

    type: Literal["check"] = "check"
    check: str = Field(min_length=1, max_length=300)
    strength: Literal["refuse", "complete", "review", "note", "off"]


class HouseCheckItem(Strict):
    """A check of the troupe's own (horatio.house_checks)."""

    type: Literal["house_check"] = "house_check"
    splat: Splat = "vampire"
    category: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    name_prefix: str | None = Field(default=None, max_length=200)
    kind: str | None = Field(default=None, max_length=100)
    mode: Literal["requires", "forbids"]
    condition: dict[str, JsonValue]
    strength: Literal["refuse", "complete", "review", "note"] = "refuse"
    message: str = Field(default="", max_length=500)
    step: str | None = Field(default=None, max_length=100)


class CostItem(Strict):
    """The troupe's price for a trait or a category, perhaps under a condition."""

    type: Literal["cost"] = "cost"
    splat: Splat = "vampire"
    category: str = Field(min_length=1, max_length=100)
    trait: str | None = Field(default=None, max_length=200)
    condition: dict[str, JsonValue] | None = None
    scheme: Literal["per_dot", "progressive", "table", "fixed", "free", "not_allowed"]
    rate: int | None = None
    table: list[int] | None = Field(default=None, max_length=20)
    # The house rule's own wording, shown with the trait.
    text: str | None = Field(default=None, max_length=2000)


class StartingRuleItem(Strict):
    rating: int | None = None
    picks: int | None = None
    points: int | None = None
    restriction: str | None = Field(default=None, max_length=100)
    when: dict[str, JsonValue] | None = None


class CreationItem(Strict):
    """What new characters start with in one category: these replace the troupe's."""

    type: Literal["creation"] = "creation"
    splat: Splat = "vampire"
    category: str = Field(min_length=1, max_length=100)
    rules: list[StartingRuleItem] = Field(min_length=1, max_length=20)


class StartingTraitItem(Strict):
    """A trait the troupe's new characters start with, free."""

    type: Literal["starting_trait"] = "starting_trait"
    splat: Splat = "vampire"
    category: str = Field(min_length=1, max_length=100)
    name: Name
    rating: int | None = None


class ActionKindItem(Strict):
    """A kind of downtime action the troupe added itself."""

    type: Literal["action_kind"] = "action_kind"
    splat: Splat = "vampire"
    key: str = Field(min_length=1, max_length=100)
    name: Name
    fields: list[dict[str, JsonValue]] = Field(default=[], max_length=20)
    actions: list[dict[str, JsonValue]] = Field(default=[], max_length=100)


class AllowanceItem(Strict):
    """The troupe's own rule for how many downtime actions characters get."""

    type: Literal["allowance"] = "allowance"
    splat: Splat = "vampire"
    action_kind: str = Field(min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    trait: str | None = Field(default=None, max_length=200)
    min_rating: int = Field(default=1, ge=1)
    scheme: Literal["fixed", "per_dot", "per_detail"] = "fixed"
    amount: int
    note: str = Field(default="", max_length=500)
    detail_ratings: list[int] = Field(default=[], max_length=10)


class KeywordItem(Strict):
    """One of the troupe's downtime keywords, as it has changed or added it."""

    type: Literal["keyword"] = "keyword"
    key: str = Field(pattern=r"^[a-z_]{1,40}$|^own_[0-9a-f]{8}$")
    name: str = Field(min_length=1, max_length=60)
    explanation: str = Field(default="", max_length=300)
    fields: list[str] = Field(default=[], max_length=6)
    action_kinds: list[str] = Field(default=["general"], max_length=20)
    computers_only: bool = False
    science: bool = False
    cost: int = Field(default=1, ge=0, le=5)
    required_for: list[str] = Field(default=[], max_length=3)
    step: int = Field(default=keywords.NORMAL_STEP, ge=1, le=6)


class HouseTraitItem(Strict):
    """A merit or flaw the troupe made itself (horatio.house_traits)."""

    type: Literal["house_trait"] = "house_trait"
    splat: Splat = "vampire"
    category: house_traits.Category
    name: str = Field(min_length=1, max_length=100)
    points: int = Field(ge=1, le=7)
    kind: house_traits.Kind = "General"
    availability: house_traits.Availability
    creation_only: bool = False
    description: str = Field(default="", max_length=4000)
    requirement: str = Field(default="", max_length=200)
    effects: list[dict[str, JsonValue]] = Field(default=[], max_length=20)


class TraitLinkItem(Strict):
    splat: Splat = "vampire"
    category: str = Field(min_length=1, max_length=100)
    name: Name


class WrittenRuleItem(Strict):
    """A house rule in words alone (horatio.written_rules)."""

    type: Literal["written_rule"] = "written_rule"
    section: str = Field(default="", max_length=100)
    title: Name
    body: str = Field(default="", max_length=20000)
    trait: TraitLinkItem | None = None
    page: str | None = Field(default=None, max_length=300)


class BookTraitItem(Strict):
    """The troupe's changes to one book trait (horatio.book_traits): a ban, its own
    wording, and a merit or flaw's category."""

    type: Literal["book_trait"] = "book_trait"
    splat: Splat = "vampire"
    category: str = Field(min_length=1, max_length=100)
    name: Name
    banned: bool = False
    ban_reason: str = Field(default="", max_length=500)
    wording: str = Field(default="", max_length=4000)
    wording_mode: Literal["added", "replaces"] = "added"
    kind: str | None = Field(default=None, max_length=100)


class TeacherRuleItem(Strict):
    """A rule that a kind of trait needs a teacher (horatio.teaching)."""

    type: Literal["teacher_rule"] = "teacher_rule"
    splat: Splat = "vampire"
    category: str = Field(min_length=1, max_length=100)
    names: list[str] = Field(default=[], max_length=50)
    name_prefix: str | None = Field(default=None, max_length=200)
    condition: dict[str, JsonValue] | None = None
    always: bool = False
    holds: Literal["same", "rating"] = "same"
    rating: int | None = Field(default=None, ge=1, le=10)
    actions: int = Field(default=0, ge=0, le=5)
    willpower: int = Field(default=0, ge=0, le=5)
    games: int = Field(default=0, ge=0, le=12)


class SpecialisationItem(Strict):
    """An option the troupe offers for one kind of specialisation."""

    type: Literal["specialisation"] = "specialisation"
    category: str = Field(min_length=1, max_length=100)
    name: Name


class FillTableItem(Strict):
    """A fill table: its entries, one per line, `[Table]` references kept as written."""

    type: Literal["fill_table"] = "fill_table"
    name: str = Field(min_length=1, max_length=100)
    entries: list[Annotated[str, Field(max_length=2000)]] = Field(default=[], max_length=1000)


class NewsAgencyItem(Strict):
    """A news agency: its name, description and colour, never its picture or channel."""

    type: Literal["news_agency"] = "news_agency"
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    colour: str = Field(default="#8b1e1e", pattern=posts.COLOUR)


Settings = list[SettingItem]


class Sections(Strict):
    """The settings by section, as Customise groups them. The first seven are the
    groups of its Troupe settings page."""

    who_may_join: Settings = []
    xp: Settings = []
    status_titles: Settings = []
    at_game: Settings = []
    downtimes: Settings = []
    feeding: Settings = []
    names: Settings = []
    checks: list[Annotated[CheckItem | HouseCheckItem, Field(discriminator="type")]] = []
    costs: list[CostItem] = []
    starting: list[
        Annotated[SettingItem | CreationItem | StartingTraitItem, Field(discriminator="type")]
    ] = []
    actions: list[
        Annotated[SettingItem | ActionKindItem | AllowanceItem, Field(discriminator="type")]
    ] = []
    keywords: list[KeywordItem] = []
    languages: Settings = []
    house_traits: list[HouseTraitItem] = []
    written_rules: list[Annotated[SettingItem | WrittenRuleItem, Field(discriminator="type")]] = []
    book_traits: list[BookTraitItem] = []
    locations: Settings = []
    quests: Settings = []
    retainers: Settings = []
    backstories: Settings = []
    free_changes: Settings = []
    teachers: list[TeacherRuleItem] = []
    specialisations: list[SpecialisationItem] = []
    fill_tables: list[FillTableItem] = []
    news_agencies: list[NewsAgencyItem] = []


SectionKey = Literal[
    "who_may_join",
    "xp",
    "status_titles",
    "at_game",
    "downtimes",
    "feeding",
    "names",
    "checks",
    "costs",
    "starting",
    "actions",
    "keywords",
    "languages",
    "house_traits",
    "written_rules",
    "book_traits",
    "locations",
    "quests",
    "retainers",
    "backstories",
    "free_changes",
    "teachers",
    "specialisations",
    "fill_tables",
    "news_agencies",
]

TROUPE_SETTINGS = "Troupe settings"
# Each section's name, and the group it is in: those of the Troupe settings page,
# then the tabs of Customise › Rules, then the troupe's other catalogues.
SECTIONS: dict[SectionKey, tuple[str, str | None]] = {
    "who_may_join": ("Who may join", TROUPE_SETTINGS),
    "xp": ("XP", TROUPE_SETTINGS),
    "status_titles": ("Status and titles", TROUPE_SETTINGS),
    "at_game": ("At game", TROUPE_SETTINGS),
    "downtimes": ("Downtimes", TROUPE_SETTINGS),
    "feeding": ("Feeding", TROUPE_SETTINGS),
    "names": ("Names", TROUPE_SETTINGS),
    "checks": ("Checks", None),
    "costs": ("Costs", None),
    "starting": ("Starting points", None),
    "actions": ("Downtime actions", None),
    "keywords": ("Downtime keywords", None),
    "languages": ("Languages", None),
    "house_traits": ("House merits and flaws", None),
    "written_rules": ("Written rules", None),
    "book_traits": ("Book traits", None),
    "locations": ("Locations", None),
    "quests": ("Quests", None),
    "retainers": ("Retainers", None),
    "backstories": ("Backstories", None),
    "free_changes": ("Free changes", None),
    "teachers": ("Teachers", None),
    "specialisations": ("Specialisations", None),
    "fill_tables": ("Fill tables", None),
    "news_agencies": ("News agencies", None),
}
assert list(SECTIONS) == list(get_args(SectionKey)) == list(Sections.model_fields)


class SettingsDocument(Strict):
    """A troupe's settings, as Export writes them and Import reads them."""

    format: Literal["horatio-troupe-settings"] = FORMAT
    version: Literal[1] = FORMAT_VERSION
    # The Horatio it was made by, and the version of each rule set the troupe plays.
    horatio: str = Field(default="", max_length=50)
    rule_sets: dict[str, int] = Field(default={}, max_length=20)
    # The troupe it came from, shown on import and offered for find & replace.
    troupe: str = Field(default="", max_length=200)
    exported_on: date | None = None
    sections: Sections = Sections()


def items(document: SettingsDocument, section: SectionKey) -> list[Any]:
    return getattr(document.sections, section)


# --- the troupe's settings -----------------------------------------------------------------


@dataclass(frozen=True)
class Setting:
    """A troupe setting that is exported, where it goes and what it may be."""

    key: str
    section: SectionKey
    label: str
    type: Any
    words: Callable[[Any], str] | None = None

    @cached_property
    def adapter(self) -> TypeAdapter[Any]:
        return TypeAdapter(self.type)


def on_off(value: Any) -> str:
    return "On" if value else "Off"


def chosen(choices: Mapping[str, str]) -> Callable[[Any], str]:
    return lambda value: choices.get(str(value), str(value))


def listing(value: Any) -> str:
    return ", ".join(str(v) for v in value) if value else "None"


def pairs(value: Any) -> str:
    return ", ".join(f"{k}: {v}" for k, v in value.items()) if value else "The book's"


def blood(value: Any) -> str:
    return "Full" if value is None else str(value)


def retainer_words(value: Any) -> str:
    rules = retainer_rules_of(value)
    found = [rules.upkeep.text() if rules.upkeep else "", rules.growth_text() or ""]
    return "; ".join(f for f in found if f) or "None"


def game_xp_words(value: Any) -> str:
    found = game_xp.GameXpSettings.model_validate(value or {})
    return "; ".join(
        [
            game_xp.chart_text(found),
            f"Cap: {game_xp.cap_text(found).lower()}",
            f"Absentee games: {game_xp.absentee_text(found).lower()}",
        ]
    )


def ban_clans_words(value: Any) -> str:
    """ "Pillar clans: Assamite, Gangrel; Lesser antitribu: none"."""
    return (
        "; ".join(
            f"{key.replace('_', ' ').capitalize()}: {', '.join(clans) or 'none'}"
            for key, clans in value.items()
        )
        or "The rule set's"
    )


def excluded_words(value: Any) -> str:
    return ", ".join(e["name"] for e in value) if value else "None"


class UpkeepIn(Strict):
    amount: int = Field(ge=1, le=retainer_upkeep.MOST_UPKEEP)
    pool: Literal["blood", "willpower"]
    ghouls_only: bool = False
    per: Literal["game", "month"] = "game"
    month_at: Literal["game", "downtime"] = "game"


class RetainerRulesIn(Strict):
    upkeep: UpkeepIn | None = None
    growth: int | None = Field(default=None, ge=1, le=retainer_upkeep.MOST_GROWTH)


def retainer_rules_of(value: Any) -> retainer_upkeep.Rules:
    found = RetainerRulesIn.model_validate(value or {})
    upkeep = found.upkeep
    return retainer_upkeep.Rules(
        upkeep=retainer_upkeep.Upkeep(
            amount=upkeep.amount,
            pool=upkeep.pool,
            ghouls_only=upkeep.ghouls_only,
            per=upkeep.per,
            month_at=upkeep.month_at if upkeep.per == "month" else "game",
        )
        if upkeep
        else None,
        growth=found.growth,
    )


class ExcludedTrait(Strict):
    category: str = Field(max_length=100)
    name: str = Field(max_length=200)


SETTINGS: dict[str, Setting] = {
    s.key: s
    for s in [
        Setting("allowed_splats", "who_may_join", "Splats", list[Splat], listing),
        Setting(
            "allowed_sects",
            "who_may_join",
            "Sects",
            Annotated[list[str], Field(max_length=20)],
            lambda v: listing(v) if v else "Any",
        ),
        Setting("session_xp", "xp", "Session XP", Annotated[int, Field(ge=0, le=100)]),
        Setting("downtime_xp", "xp", "Downtime XP", Annotated[int, Field(ge=0, le=100)]),
        Setting("starting_xp", "xp", "Starting XP", Annotated[int, Field(ge=0, le=10000)]),
        Setting("game_xp", "xp", "Game XP", dict[str, JsonValue], game_xp_words),
        Setting(
            "status_by",
            "status_titles",
            "Who keeps fleeting and negative status",
            Literal["players", "staff"],
            chosen({"players": "Players", "staff": "Staff only"}),
        ),
        Setting(
            "titles_by",
            "status_titles",
            "Who chooses titles",
            Literal["players", "staff"],
            chosen({"players": "Players", "staff": "Staff only"}),
        ),
        Setting(
            "one_holder_titles",
            "status_titles",
            "Titles held to one holder at a time",
            Annotated[list[str], Field(max_length=200)],
            listing,
        ),
        Setting(
            "status_at_checkin", "status_titles", "Abiding status chosen at check-in", bool, on_off
        ),
        Setting(
            "whos_who_negative", "status_titles", "Negative status on the Who's Who", bool, on_off
        ),
        Setting(
            "golconda_enlightened",
            "status_titles",
            "Golconda Seekers are Enlightened",
            bool,
            on_off,
        ),
        Setting(
            "status_ban_clans",
            "status_titles",
            "The clans the status bans name",
            dict[
                Annotated[str, Field(max_length=100)],
                Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=100)],
            ],
            ban_clans_words,
        ),
        Setting("badge_titles", "at_game", "Titles on badges", bool, on_off),
        Setting(
            "badge_status",
            "at_game",
            "Status on badges",
            Literal["all", "negative", "none"],
            chosen({"all": "All status", "negative": "Negative status only", "none": "None"}),
        ),
        Setting("badge_pronouns", "at_game", "Pronouns on badges", bool, on_off),
        Setting(
            "starting_blood",
            "at_game",
            "Blood at the start of a game",
            Blood | None,
            blood,
        ),
        Setting(
            "diablerie_flaws",
            "at_game",
            "What diablerie does to Lesser Generation and Thin Blooded",
            Literal["leave", "remove", "keep_xp"],
            chosen(
                {
                    "leave": "Leave the flaw",
                    "remove": "Remove it, and the XP it gave",
                    "keep_xp": "Remove it, keep the XP",
                }
            ),
        ),
        Setting("items_expire", "at_game", "Items can expire", bool, on_off),
        Setting(
            "blood_bonds",
            "at_game",
            "Blood bonds",
            Literal["off", "staff", "players_report", "players_manage"],
            chosen(
                {
                    "off": "Off",
                    "staff": "Staff manages",
                    "players_report": "Players report and staff approves",
                    "players_manage": "Players manage",
                }
            ),
        ),
        Setting("boons", "at_game", "Boons", bool, on_off),
        Setting(
            "boon_players_see",
            "at_game",
            "What players see of the boon ledger",
            Literal["intake", "owes", "owed"],
            chosen(
                {
                    "intake": "The form to report a boon only",
                    "owes": "Also what they owe",
                    "owed": "Also what they owe and are owed",
                }
            ),
        ),
        Setting(
            "boon_players_settle",
            "at_game",
            "Players mark boons owed to them settled",
            bool,
            on_off,
        ),
        Setting(
            "play_tabs_off",
            "at_game",
            "Play View tabs for players",
            Annotated[list[play_tabs.PlayTab], Field(max_length=len(play_tabs.PLAY_TABS))],
            play_tabs.words,
        ),
        Setting("player_nominations", "downtimes", "Player Nominations", bool, on_off),
        Setting("remembrances", "downtimes", "Remembrances", bool, on_off),
        Setting(
            "feeding",
            "feeding",
            "Feeding",
            Literal["off", "book"],
            chosen({"off": "Not tracked", "book": "Tracked as the book has it"}),
        ),
        Setting("feeding_resonance", "feeding", "Blood Resonance", bool, on_off),
        Setting("feeding_territories", "feeding", "Feeding territories", bool, on_off),
        Setting("feeding_rack", "feeding", "The Rack", bool, on_off),
        Setting(
            "assamite_name", "names", "The Assamites are called", Literal["Banu Haqim", "Assamite"]
        ),
        Setting(
            "clan_rarity",
            "starting",
            "How rare clans are",
            dict[str, Literal["common", "uncommon", "rare", "restricted"]],
            pairs,
        ),
        Setting("default_bloodlines", "starting", "Default bloodlines", dict[str, str], pairs),
        Setting(
            "influence_lookback_days",
            "actions",
            "Days influence lookups look back",
            Annotated[int, Field(ge=1, le=3650)],
        ),
        Setting(
            "rare_disciplines_two_actions",
            "actions",
            "Rare disciplines take two actions a dot",
            bool,
            on_off,
        ),
        Setting(
            "languages",
            "languages",
            "Languages Linguistics gives",
            Literal["book", "accelerated", "custom"],
            chosen(
                {"book": "One a dot", "accelerated": "The accelerated chart", "custom": "Our own"}
            ),
        ),
        Setting(
            "languages_table",
            "languages",
            "Our own chart",
            Chart | None,
            listing,
        ),
        Setting(
            "natural_linguist_doubles", "languages", "Natural Linguist doubles it", bool, on_off
        ),
        Setting(
            "written_rules_public", "written_rules", "Written rules on the profile", bool, on_off
        ),
        Setting(
            "location_options_off",
            "locations",
            "House options switched off",
            Annotated[list[str], Field(max_length=50)],
            listing,
        ),
        Setting(
            "location_limit",
            "locations",
            "Going over the control limit",
            Literal["refuse", "note"],
            chosen({"refuse": "Refuse it", "note": "Allow it, and show staff"}),
        ),
        Setting("quests_enabled", "quests", "Quests", bool, on_off),
        Setting(
            "quest_requests_per_cycle",
            "quests",
            "Quest requests a cycle",
            Annotated[int, Field(ge=0, le=20)],
        ),
        Setting("retainer_rules", "retainers", "Retainer rules", RetainerRulesIn, retainer_words),
        Setting(
            "backstory_mode",
            "backstories",
            "How backstories are written",
            Literal["free", "either", "wizard"],
            chosen(backstories.MODE_WORDS),
        ),
        Setting("backstory_required", "backstories", "An approved backstory to join", bool, on_off),
        Setting(
            "free_changes",
            "free_changes",
            "Free changes",
            Literal["none", "date", "games"],
            chosen({"none": "None", "date": "For some days", "games": "For some games"}),
        ),
        Setting("free_changes_days", "free_changes", "Days", Annotated[int, Field(ge=1, le=365)]),
        Setting("free_changes_games", "free_changes", "Games", Annotated[int, Field(ge=1, le=50)]),
        Setting(
            "free_changes_excluded",
            "free_changes",
            "Never refunded",
            Annotated[list[ExcludedTrait], Field(max_length=100)],
            excluded_words,
        ),
    ]
}

# The columns of `troupes` that are never exported, and why.
NOT_EXPORTED_COLUMNS: dict[str, str] = {
    "id": "an id, never exported",
    "created_at": "when the troupe was made",
    "updated_at": "when the troupe last changed",
    "legacy_id": "where Yorick's copy came from",
    "name": "the troupe's own name",
    "description": "the troupe's own description",
    "lead_user_id": "its staff are its own",
    "archived_at": "whether the troupe is open",
    "public": "its profile is its own",
    "portrait_id": "its profile is its own",
    "portrait_crop": "its profile is its own",
    "banner_id": "its profile is its own",
    "profile": "its profile is its own",
    "contact_id": "its staff are its own",
    "seated_clans": "its court is its own (titles and seats aren't carried)",
    "free_changes_since": "set to the time of import when free changes are switched on",
    "rules_version": "kept by the database, changing with the troupe's rules",
}

# The tables that belong to a troupe and are exported, each in its section.
EXPORTED_TABLES: dict[str, SectionKey] = {
    "check_overrides": "checks",
    "house_checks": "checks",
    "cost_rules": "costs",
    "creation_rules": "starting",
    "starting_traits": "starting",
    "action_kinds": "actions",
    "allowance_rules": "actions",
    "downtime_keywords": "keywords",
    "house_traits": "house_traits",
    # A house merit's own definition, made again as it is imported.
    "trait_definitions": "house_traits",
    "written_rules": "written_rules",
    "trait_overrides": "book_traits",
    "teacher_rules": "teachers",
    "troupe_specializations": "specialisations",
    "random_tables": "fill_tables",
    "news_agencies": "news_agencies",
}

PLAY = "play, not settings"
# The tables that belong to a troupe and are never exported, and why.
NOT_EXPORTED_TABLES: dict[str, str] = {
    "approvals": PLAY,
    "audit_events": "the troupe's own log",
    "background_changes": PLAY,
    "backstories": PLAY,
    "backstory_feedback": PLAY,
    "backstory_question_sets": "backstory question sets aren't carried",
    "blood_bonds": PLAY,
    "boons": PLAY,
    "calendar_feeds": "people's own calendar links",
    "character_titles": PLAY,
    "characters": PLAY,
    "diableries": PLAY,
    "downtime_cycles": "downtimes are the troupe's own",
    "embraces": PLAY,
    "equipment_events": PLAY,
    "equipment_items": PLAY,
    "equipment_templates": "the troupe's own equipment templates aren't carried",
    "feeding_territories": "who holds which territory is play",
    "held_statuses": PLAY,
    "home_troupe_changes": PLAY,
    "influence_effects": PLAY,
    "influence_entries": "the influence log is the troupe's own",
    "locations": "its locations are its world, not settings",
    "notifications": "people's own notifications",
    "owed_actions": PLAY,
    "posts": "news stories and announcements are never carried",
    "projects": PLAY,
    "quest_requests": PLAY,
    "quests": PLAY,
    "remembrances": PLAY,
    "scenes": PLAY,
    "scheduled_games": "games are the troupe's own",
    "shared_backgrounds": PLAY,
    "sheet_versions": PLAY,
    "teachings": PLAY,
    "troupe_connectors": "connectors (tokens, Discord channels) are never carried",
    "troupe_location_qualities": "house location qualities aren't carried",
    "troupe_memberships": PLAY,
    "troupe_requests": "how the troupe began",
    "troupe_staff": "its staff are its own",
    "troupe_titles": "the troupe's titles aren't carried",
    "xp_range_entries": "the XP floor and ceiling's history is the troupe's own",
    "yorick_imports": "imports from Yorick are the troupe's own",
}


def column_default(key: str) -> Any:
    """What a new troupe has for a setting: Horatio's default."""
    default = Troupe.__table__.c[key].default
    if default is None:
        return None
    arg = getattr(default, "arg", None)
    return arg(None) if callable(arg) else arg


def setting_value(troupe: Troupe, key: str) -> Any:
    return json.loads(json.dumps(getattr(troupe, key), default=str))


# --- reading a troupe ------------------------------------------------------------------------


@dataclass
class Target:
    """A troupe, read for exporting its settings or comparing a document with it."""

    db: Session
    troupe: Troupe
    # The document coming in, for what it brings with it: splats, house merits.
    document: SettingsDocument | None = None

    def rules(self, splat: str) -> TroupeRules:
        return read_troupe_rules(self.db, splat, self.troupe.id)

    @cached_property
    def loaded(self) -> set[str]:
        """The splats this Horatio has a rule set for."""
        return set(self.db.scalars(select(RuleSet.splat)))

    @property
    def splats(self) -> list[str]:
        return ["vampire", *(s for s in self.troupe.allowed_splats if s != "vampire")]

    @cached_property
    def incoming_splats(self) -> set[str]:
        found = set(self.splats)
        if self.document is not None:
            for item in self.document.sections.who_may_join:
                if item.key == "allowed_splats" and isinstance(item.value, list):
                    found |= {str(s) for s in item.value}
        return found

    @cached_property
    def incoming_traits(self) -> set[tuple[str, str, str]]:
        """The house merits and flaws the document brings, by splat, category and name."""
        if self.document is None:
            return set()
        return {(h.splat, h.category, h.name) for h in self.document.sections.house_traits}

    def splat_problem(self, splat: str) -> str | None:
        if splat not in SPLATS or splat not in self.loaded:
            return f"This Horatio has no rules for {splat} characters."
        if splat not in self.incoming_splats:
            return f"{self.troupe.name} doesn't take {SPLATS[splat].label.lower()} characters."
        return None

    def category_name(self, splat: str, category: str) -> str:
        if splat not in self.loaded:
            return category
        found = self.rules(splat).rule_set.categories.get(category)
        return found.name if found else category

    def has_trait(self, splat: str, category: str, name: str) -> bool:
        return (category, name) in self.rules(splat).rule_set.traits or (
            splat,
            category,
            name,
        ) in self.incoming_traits

    def trait_problem(self, splat: str, category: str, name: str | None) -> str | None:
        """Why a trait (or with no name, a category) can't be found in the troupe's rules."""
        problem = self.splat_problem(splat)
        if problem:
            return problem
        if category not in self.rules(splat).rule_set.categories:
            return f"This troupe's rule set has no category {category!r}."
        if name is not None and not self.has_trait(splat, category, name):
            return f"{name} isn't in this troupe's rule set."
        return None


def for_splat(text: str, splat: str) -> str:
    found = SPLATS.get(splat)
    return text if splat == "vampire" else f"{text} for {found.label.lower() if found else splat}s"


# --- each kind of item -------------------------------------------------------------------------


@dataclass(frozen=True)
class Editable:
    """A field of an item with free text, which can be edited on the way in."""

    field: str
    label: str
    # Long text, edited in a box of several lines; or `lines`, a list edited one per line.
    multiline: bool = False
    lines: bool = False


class Kind[I: BaseModel]:
    """How one kind of item is exported, matched, described and applied."""

    editable: tuple[Editable, ...] = ()
    # What each field is called, where its name won't do.
    labels: Mapping[str, str] = {}

    def export(self, target: Target) -> list[I]:
        raise NotImplementedError

    def label(self, target: Target, item: I) -> str:
        raise NotImplementedError

    def current(self, target: Target, item: I) -> I | None:
        """The troupe's own item matching this one, in the same shape; None for none."""
        raise NotImplementedError

    def problem(self, target: Target, item: I) -> str | None:
        """Why the item can't be imported here, or None."""
        return None

    def apply(self, target: Target, user: User, item: I, current: I | None) -> None:
        raise NotImplementedError

    def same(self, item: I, current: I | None) -> bool:
        return current is not None and current.model_dump() == item.model_dump()

    def words(self, item: I, current: I) -> tuple[str, str]:
        """What changes, before and after, field by field."""
        before: list[str] = []
        after: list[str] = []
        now, then = current.model_dump(), item.model_dump()
        for name, value in then.items():
            if name == "type" or now.get(name) == value:
                continue
            label = self.labels.get(name) or name.replace("_", " ").capitalize()
            before.append(f"{label}: {shown(now.get(name))}")
            after.append(f"{label}: {shown(value)}")
        return "; ".join(before), "; ".join(after)


def shown(value: Any) -> str:
    """A value in words, for before and after."""
    if value is None or value == "" or value == [] or value == {}:
        return "None"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        value = cast(list[Any], value)
        if all(isinstance(v, str | int) for v in value):
            return ", ".join(str(v) for v in value)
        return json.dumps(value)
    if isinstance(value, dict):
        return json.dumps(value)
    text = str(value)
    return text if len(text) <= 300 else f"{text[:299]}…"


class SettingKind(Kind[SettingItem]):
    def export(self, target: Target) -> list[SettingItem]:
        raise NotImplementedError  # by section, in `export`

    def label(self, target: Target, item: SettingItem) -> str:
        found = SETTINGS.get(item.key)
        return found.label if found else item.key

    def current(self, target: Target, item: SettingItem) -> SettingItem | None:
        if item.key not in SETTINGS:
            return None
        return SettingItem(key=item.key, value=setting_value(target.troupe, item.key))

    def problem(self, target: Target, item: SettingItem) -> str | None:
        found = SETTINGS.get(item.key)
        if found is None:
            return "Not a setting this Horatio has."
        try:
            found.adapter.validate_python(item.value)
        except ValidationError as error:
            return f"Not a value it can have: {error.errors()[0]['msg']}."
        return None

    def same(self, item: SettingItem, current: SettingItem | None) -> bool:
        if current is None:
            return False
        found = SETTINGS[item.key]
        try:
            mine = found.adapter.validate_python(current.value)
        except ValidationError:
            # A value its editor could no longer save: the import puts it right.
            return False
        dump = found.adapter.dump_python
        return dump(found.adapter.validate_python(item.value), mode="json") == dump(
            mine, mode="json"
        )

    def words(self, item: SettingItem, current: SettingItem) -> tuple[str, str]:
        found = SETTINGS[item.key]
        say = found.words or shown
        return say(current.value), say(item.value)

    def apply(
        self, target: Target, user: User, item: SettingItem, current: SettingItem | None
    ) -> None:
        raise NotImplementedError  # together, in `apply_settings`


def known_checks(target: Target) -> dict[str, str]:
    """The rule set's checks the troupe can play differently: key -> what it says."""
    found: dict[str, str] = {}
    for splat in target.splats:
        for check in target.rules(splat).rule_set.checks:
            if not is_house_check(check.key):
                found.setdefault(
                    check.key, check.message or check.name or check.name_prefix or check.key
                )
    return found


class CheckKind(Kind[CheckItem]):
    labels = {"strength": "Setting"}

    def export(self, target: Target) -> list[CheckItem]:
        return [
            CheckItem(check=key, strength=cast(Any, strength))
            for key, strength in sorted(target.rules("vampire").check_overrides.items())
        ]

    def label(self, target: Target, item: CheckItem) -> str:
        return known_checks(target).get(item.check, item.check)

    def current(self, target: Target, item: CheckItem) -> CheckItem | None:
        strength = target.rules("vampire").check_overrides.get(item.check)
        return CheckItem(check=item.check, strength=cast(Any, strength)) if strength else None

    def problem(self, target: Target, item: CheckItem) -> str | None:
        if item.check not in known_checks(target):
            return "Not a check in this troupe's rule set."
        return None

    def apply(self, target: Target, user: User, item: CheckItem, current: CheckItem | None) -> None:
        set_check_override(target.db, target.troupe.id, item.check, item.strength)


def house_check_item(row: HouseCheck) -> HouseCheckItem:
    return HouseCheckItem(
        splat=row.splat,
        category=row.category,
        name=row.name,
        name_prefix=row.name_prefix,
        kind=row.kind,
        mode=cast(Any, row.mode),
        condition=row.condition,
        strength=cast(Any, row.strength),
        message=row.message,
        step=row.step,
    )


class HouseCheckKind(Kind[HouseCheckItem]):
    editable = (Editable("message", "Message"),)

    def rows(self, target: Target) -> list[HouseCheck]:
        return list(
            target.db.scalars(
                select(HouseCheck)
                .where(HouseCheck.troupe_id == target.troupe.id)
                .order_by(HouseCheck.created_at, HouseCheck.id)
            )
        )

    def export(self, target: Target) -> list[HouseCheckItem]:
        return [house_check_item(r) for r in self.rows(target)]

    def label(self, target: Target, item: HouseCheckItem) -> str:
        return item.message or item.name or item.name_prefix or item.category

    def current(self, target: Target, item: HouseCheckItem) -> HouseCheckItem | None:
        # Only one just like it: one that differs is another check, added beside it.
        mine = item.model_dump()
        return next((c for c in self.export(target) if c.model_dump() == mine), None)

    def problem(self, target: Target, item: HouseCheckItem) -> str | None:
        return target.trait_problem(item.splat, item.category, item.name)

    def apply(
        self, target: Target, user: User, item: HouseCheckItem, current: HouseCheckItem | None
    ) -> None:
        house_checks.create(
            target.db,
            user,
            target.troupe,
            HouseCheckData(
                splat=item.splat,
                category=item.category,
                name=item.name or None,
                name_prefix=item.name_prefix or None,
                kind=item.kind or None,
                mode=item.mode,
                condition=item.condition,
                strength=item.strength,
                message=item.message,
                step=item.step or None,
            ),
        )


def cost_item(splat: str, rule: CostRuleData) -> CostItem:
    return CostItem(
        splat=splat,
        category=rule.category,
        trait=rule.trait,
        condition=dict(rule.condition) if rule.condition else None,
        scheme=rule.scheme,
        rate=rule.rate,
        table=list(rule.table) if rule.table is not None else None,
        text=rule.text,
    )


def cost_rule(item: CostItem) -> CostRuleData:
    """A house price as the Costs editor makes one: only the amount or table its
    scheme uses."""
    return CostRuleData(
        category=item.category,
        trait=item.trait,
        condition=item.condition or None,
        scheme=item.scheme,
        rate=item.rate if item.scheme in ("per_dot", "progressive", "fixed") else None,
        table=tuple(item.table) if item.scheme == "table" and item.table is not None else None,
        text=(item.text or "").strip() or None,
        house=True,
    )


class CostKind(Kind[CostItem]):
    editable = (Editable("text", "Wording", multiline=True),)
    labels = {"text": "Wording"}

    def export(self, target: Target) -> list[CostItem]:
        return [
            cost_item(splat, rule)
            for splat in target.splats
            for _, rule in house_cost_rules(target.db, splat, target.troupe.id)
        ]

    def label(self, target: Target, item: CostItem) -> str:
        what = item.trait or target.category_name(item.splat, item.category)
        splat = SPLATS.get(item.splat)
        when = conditions.describe(item.condition, splat.fact_words) if splat else None
        return for_splat(f"{what} ({when})" if when else what, item.splat)

    def found(self, target: Target, item: CostItem) -> tuple[uuid.UUID, CostRuleData] | None:
        rule = cost_rule(item)
        return next(
            (
                (i, r)
                for i, r in house_cost_rules(target.db, item.splat, target.troupe.id)
                if same_subject(r, rule)
            ),
            None,
        )

    def current(self, target: Target, item: CostItem) -> CostItem | None:
        found = self.found(target, item)
        return cost_item(item.splat, found[1]) if found else None

    def problem(self, target: Target, item: CostItem) -> str | None:
        problem = target.trait_problem(item.splat, item.category, item.trait)
        rule_set = target.rules(item.splat).rule_set if problem is None else None
        if rule_set is None or (item.trait and (item.category, item.trait) not in rule_set.traits):
            # A house merit coming in the same import is checked as it is priced.
            return problem
        # As the Costs editor checks it: a condition some character could meet, and
        # no tie with another of the troupe's prices.
        found = self.found(target, item)
        others = [
            r
            for i, r in house_cost_rules(target.db, item.splat, target.troupe.id)
            if found is None or i != found[0]
        ]
        try:
            check_house_price(cost_rule(item), others, rule_set)
        except TiedHouseRule as error:
            return self.tie_reason(target, item.splat, error)
        except ValueError as error:
            return str(error)
        return None

    def tie_reason(self, target: Target, splat: str, error: TiedHouseRule) -> str:
        other = cost_item(splat, error.other)
        return (
            f"It ties with this troupe's price for {self.label(target, other)}: a character "
            "could meet both conditions, and neither is more specific."
        )

    def apply(self, target: Target, user: User, item: CostItem, current: CostItem | None) -> None:
        rule = cost_rule(item)
        found = self.found(target, item)
        try:
            if found is None:
                add_house_rule(target.db, target.troupe.id, item.splat, rule)
            else:
                change_house_rule(target.db, target.troupe.id, item.splat, found[0], rule)
        except TiedHouseRule as error:
            raise unprocessable(self.tie_reason(target, item.splat, error)) from error


class CreationKind(Kind[CreationItem]):
    def export(self, target: Target) -> list[CreationItem]:
        found: list[CreationItem] = []
        for splat in target.splats:
            rules = target.rules(splat)
            for category in rules.rule_set.categories:
                mine = [r for r in rules.house_creation_rules if r.category == category]
                if mine:
                    found.append(self.item(splat, category, mine))
        return found

    def item(self, splat: str, category: str, rules: Sequence[CreationRuleData]) -> CreationItem:
        return CreationItem(
            splat=splat,
            category=category,
            rules=[
                StartingRuleItem(
                    rating=r.rating,
                    picks=r.picks,
                    points=r.points,
                    restriction=r.restriction,
                    when=dict(r.when) if r.when else None,
                )
                for r in rules
            ],
        )

    def label(self, target: Target, item: CreationItem) -> str:
        return for_splat(target.category_name(item.splat, item.category), item.splat)

    def current(self, target: Target, item: CreationItem) -> CreationItem | None:
        mine = [
            r for r in target.rules(item.splat).house_creation_rules if r.category == item.category
        ]
        return self.item(item.splat, item.category, mine) if mine else None

    def problem(self, target: Target, item: CreationItem) -> str | None:
        problem = target.trait_problem(item.splat, item.category, None)
        if problem is None and not any(
            r.category == item.category for r in target.rules(item.splat).rule_set.creation_rules
        ):
            return "This troupe's rule set gives no starting points in it."
        return problem

    def apply(
        self, target: Target, user: User, item: CreationItem, current: CreationItem | None
    ) -> None:
        rules = [
            CreationRuleData(
                category=item.category,
                rating=r.rating,
                picks=r.picks,
                points=r.points,
                restriction=r.restriction or None,
                when=r.when or None,
                house=True,
            )
            for r in item.rules
        ]
        check_house_creation_conditions(rules, target.rules(item.splat).rule_set, item.category)
        set_house_creation_rules(target.db, target.troupe.id, item.splat, item.category, rules)


class StartingTraitKind(Kind[StartingTraitItem]):
    def export(self, target: Target) -> list[StartingTraitItem]:
        return [
            StartingTraitItem(splat=splat, category=t.category, name=t.name, rating=t.rating)
            for splat in target.splats
            for t in target.rules(splat).house_starting_traits
        ]

    def label(self, target: Target, item: StartingTraitItem) -> str:
        return for_splat(item.name, item.splat)

    def current(self, target: Target, item: StartingTraitItem) -> StartingTraitItem | None:
        return next(
            (
                t
                for t in self.export(target)
                if (t.splat, t.category, t.name) == (item.splat, item.category, item.name)
            ),
            None,
        )

    def problem(self, target: Target, item: StartingTraitItem) -> str | None:
        return target.trait_problem(item.splat, item.category, item.name)

    def apply(
        self,
        target: Target,
        user: User,
        item: StartingTraitItem,
        current: StartingTraitItem | None,
    ) -> None:
        set_house_starting_trait(
            target.db,
            target.troupe.id,
            item.splat,
            StartingTraitData(
                category=item.category, name=item.name, rating=item.rating, house=True
            ),
        )


class ActionKindKind(Kind[ActionKindItem]):
    def export(self, target: Target) -> list[ActionKindItem]:
        return [
            ActionKindItem(
                splat=splat,
                key=k.key,
                name=k.name,
                fields=[dict(f) for f in k.fields],
                actions=[dict(a) for a in k.actions],
            )
            for splat in target.splats
            for k in target.rules(splat).house_action_kinds
        ]

    def label(self, target: Target, item: ActionKindItem) -> str:
        return for_splat(item.name, item.splat)

    def current(self, target: Target, item: ActionKindItem) -> ActionKindItem | None:
        return next(
            (k for k in self.export(target) if (k.splat, k.key) == (item.splat, item.key)), None
        )

    def problem(self, target: Target, item: ActionKindItem) -> str | None:
        return target.splat_problem(item.splat)

    def apply(
        self, target: Target, user: User, item: ActionKindItem, current: ActionKindItem | None
    ) -> None:
        kind = ActionKindData(
            key=item.key, name=item.name, fields=tuple(item.fields), actions=tuple(item.actions)
        )
        if current is None:
            add_house_action_kind(target.db, target.troupe.id, item.splat, kind)
        else:
            change_house_action_kind(target.db, target.troupe.id, item.splat, kind)


def allowance_item(splat: str, rule: AllowanceRuleData) -> AllowanceItem:
    return AllowanceItem(
        splat=splat,
        action_kind=rule.action_kind,
        category=rule.category,
        trait=rule.trait,
        min_rating=rule.min_rating,
        scheme=rule.scheme,
        amount=rule.amount,
        note=rule.note,
        detail_ratings=list(rule.detail_ratings),
    )


class AllowanceKind(Kind[AllowanceItem]):
    editable = (Editable("note", "Note", multiline=True),)
    labels = {"min_rating": "Least rating"}

    def export(self, target: Target) -> list[AllowanceItem]:
        return [
            allowance_item(splat, rule)
            for splat in target.splats
            for _, rule in house_allowance_rules(target.db, splat, target.troupe.id)
        ]

    def data(self, item: AllowanceItem) -> AllowanceRuleData:
        return AllowanceRuleData(
            action_kind=item.action_kind,
            scheme=item.scheme,
            amount=item.amount,
            category=item.category or None,
            trait=item.trait or None,
            min_rating=item.min_rating,
            house=True,
            note=item.note.strip(),
            detail_ratings=tuple(item.detail_ratings),
        )

    def found(
        self, target: Target, item: AllowanceItem
    ) -> tuple[uuid.UUID, AllowanceRuleData] | None:
        # The troupe has one rule for each action kind and trait, as the editor allows.
        key = self.data(item).key
        return next(
            (
                (i, r)
                for i, r in house_allowance_rules(target.db, item.splat, target.troupe.id)
                if r.key == key
            ),
            None,
        )

    def label(self, target: Target, item: AllowanceItem) -> str:
        kinds = (
            target.rules(item.splat).action_kinds() if not target.splat_problem(item.splat) else {}
        )
        kind = kinds[item.action_kind].name if item.action_kind in kinds else item.action_kind
        return for_splat(f"{item.trait or 'Everyone'}: {kind}", item.splat)

    def current(self, target: Target, item: AllowanceItem) -> AllowanceItem | None:
        found = self.found(target, item)
        return allowance_item(item.splat, found[1]) if found else None

    def problem(self, target: Target, item: AllowanceItem) -> str | None:
        problem = target.splat_problem(item.splat)
        if problem is None and item.category is not None:
            problem = target.trait_problem(item.splat, item.category, item.trait)
        return problem

    def apply(
        self, target: Target, user: User, item: AllowanceItem, current: AllowanceItem | None
    ) -> None:
        found = self.found(target, item)
        if found is None:
            add_house_allowance_rule(target.db, target.troupe.id, item.splat, self.data(item))
        else:
            change_house_allowance_rule(target.db, target.troupe.id, found[0], self.data(item))


def keyword_item(keyword: keywords.Keyword) -> KeywordItem:
    return KeywordItem(
        key=keyword.key,
        name=keyword.name,
        explanation=keyword.explanation,
        fields=list(keyword.fields),
        action_kinds=list(keyword.action_kinds),
        computers_only=keyword.computers_only,
        science=keyword.science,
        cost=keyword.cost,
        required_for=list(keyword.required_for),
        step=keyword.step,
    )


class KeywordKind(Kind[KeywordItem]):
    editable = (Editable("name", "Name"), Editable("explanation", "Explanation"))

    def export(self, target: Target) -> list[KeywordItem]:
        # Only a troupe that has changed them; then only those it changed or added.
        if not keywords.rows(target.db, target.troupe.id):
            return []
        found: list[KeywordItem] = []
        for keyword in keywords.troupe_keywords(target.db, target.troupe.id):
            if keyword.retired:
                continue
            item = keyword_item(keyword)
            default = keywords.DEFAULT_BY_KEY.get(keyword.key)
            if default is None or keyword_item(default).model_dump() != item.model_dump():
                found.append(item)
        return found

    def label(self, target: Target, item: KeywordItem) -> str:
        return item.name

    def current(self, target: Target, item: KeywordItem) -> KeywordItem | None:
        found = keywords.by_key(keywords.troupe_keywords(target.db, target.troupe.id)).get(item.key)
        return keyword_item(found) if found is not None else None

    def problem(self, target: Target, item: KeywordItem) -> str | None:
        if item.key not in keywords.DEFAULT_KEYS and not item.key.startswith("own_"):
            return "Not one of Horatio's keywords, nor a troupe's own."
        return None

    def apply(
        self, target: Target, user: User, item: KeywordItem, current: KeywordItem | None
    ) -> None:
        change = keywords.Change(
            name=item.name,
            explanation=item.explanation,
            fields=list(item.fields),
            action_kinds=list(item.action_kinds),
            computers_only=item.computers_only,
            science=item.science,
            cost=item.cost,
            required_for=list(item.required_for),
            step=item.step,
        )
        kinds = downtimes.troupe_action_kinds(target.db, target.troupe)
        if current is None:
            keywords.add(target.db, user, target.troupe, change, kinds, key=item.key)
        else:
            # The troupe's first change writes Horatio's list for it first.
            keywords.change(target.db, user, target.troupe, item.key, change, kinds)


def house_trait_item(row: HouseTrait) -> HouseTraitItem:
    return HouseTraitItem(
        splat=row.splat,
        category=cast(Any, row.category),
        name=row.name,
        points=row.points,
        kind=cast(Any, row.kind),
        availability=cast(Any, row.availability),
        creation_only=row.creation_only,
        description=row.description,
        requirement=row.requirement,
        effects=row.effects,
    )


class HouseTraitKind(Kind[HouseTraitItem]):
    editable = (
        Editable("name", "Name"),
        Editable("description", "Description", multiline=True),
        Editable("requirement", "Requirement"),
    )

    def rows(self, target: Target) -> list[HouseTrait]:
        return list(
            target.db.scalars(
                select(HouseTrait)
                .where(HouseTrait.troupe_id == target.troupe.id)
                .order_by(HouseTrait.splat, HouseTrait.category, HouseTrait.name)
            )
        )

    def export(self, target: Target) -> list[HouseTraitItem]:
        return [house_trait_item(r) for r in self.rows(target) if r.archived_at is None]

    def label(self, target: Target, item: HouseTraitItem) -> str:
        return for_splat(f"★ {item.name} ({house_traits.noun(item.category)})", item.splat)

    def row(self, target: Target, item: HouseTraitItem) -> HouseTrait | None:
        return next(
            (
                r
                for r in self.rows(target)
                if (r.splat, r.category, r.name.lower())
                == (item.splat, item.category, item.name.strip().lower())
            ),
            None,
        )

    def current(self, target: Target, item: HouseTraitItem) -> HouseTraitItem | None:
        row = self.row(target, item)
        return house_trait_item(row) if row is not None else None

    def problem(self, target: Target, item: HouseTraitItem) -> str | None:
        problem = target.splat_problem(item.splat)
        if problem:
            return problem
        other = next(
            (
                r
                for r in self.rows(target)
                if r.splat == item.splat
                and r.category != item.category
                and r.name.lower() == item.name.strip().lower()
            ),
            None,
        )
        if other is not None:
            noun = house_traits.noun(other.category)
            return f"This troupe already has a {noun} called {other.name}."
        return None

    def apply(
        self, target: Target, user: User, item: HouseTraitItem, current: HouseTraitItem | None
    ) -> None:
        spec = house_traits.Spec(
            category=item.category,
            name=item.name.strip(),
            points=item.points,
            kind=item.kind,
            availability=item.availability,
            creation_only=item.creation_only,
            description=item.description.strip(),
            requirement=item.requirement.strip(),
            splat=item.splat,
            effects=tuple(item.effects),
        )
        row = self.row(target, item)
        if row is None:
            house_traits.create(target.db, user, target.troupe, spec)
        else:
            house_traits.change(target.db, user, target.troupe, row, spec)


class WrittenRuleKind(Kind[WrittenRuleItem]):
    editable = (
        Editable("section", "Section"),
        Editable("title", "Title"),
        Editable("body", "The rule", multiline=True),
    )

    def export(self, target: Target) -> list[WrittenRuleItem]:
        found = written_rules.listed(target.db, target.troupe.id)
        traits = written_rules.linked_traits(target.db, found)
        return [self.item(r, traits) for r in found]

    def item(
        self, rule: WrittenRule, traits: Mapping[uuid.UUID, written_rules.LinkedTrait]
    ) -> WrittenRuleItem:
        trait = traits.get(rule.trait_definition_id) if rule.trait_definition_id else None
        return WrittenRuleItem(
            section=rule.section,
            title=rule.title,
            body=rule.body,
            trait=TraitLinkItem(splat=trait.splat, category=trait.category, name=trait.name)
            if trait
            else None,
            page=rule.page,
        )

    def row(self, target: Target, item: WrittenRuleItem) -> WrittenRule | None:
        return next(
            (
                r
                for r in written_rules.listed(target.db, target.troupe.id)
                if (r.section, r.title) == (item.section.strip(), item.title.strip())
            ),
            None,
        )

    def label(self, target: Target, item: WrittenRuleItem) -> str:
        return f"{item.section}: {item.title}" if item.section else item.title

    def current(self, target: Target, item: WrittenRuleItem) -> WrittenRuleItem | None:
        row = self.row(target, item)
        if row is None:
            return None
        return self.item(row, written_rules.linked_traits(target.db, [row]))

    def problem(self, target: Target, item: WrittenRuleItem) -> str | None:
        if item.trait is None:
            return None
        return target.trait_problem(item.trait.splat, item.trait.category, item.trait.name)

    def apply(
        self, target: Target, user: User, item: WrittenRuleItem, current: WrittenRuleItem | None
    ) -> None:
        trait = None
        if item.trait is not None:
            found = written_rules.find_trait(
                target.db, target.troupe.id, item.trait.splat, item.trait.category, item.trait.name
            )
            if found is None:
                raise unprocessable(f"There is no {item.trait.category} trait {item.trait.name!r}.")
            trait = found.id
        words = written_rules.Words(
            section=item.section.strip(),
            title=item.title.strip(),
            body=item.body,
            trait_definition_id=trait,
            page=(item.page or "").strip() or None,
        )
        if not words.title:
            raise unprocessable("Give it a title.")
        row = self.row(target, item)
        if row is None:
            written_rules.add(target.db, user, target.troupe, words)
        else:
            written_rules.change(target.db, user, target.troupe, row, words)


class BookTraitKind(Kind[BookTraitItem]):
    editable = (
        Editable("wording", "House wording", multiline=True),
        Editable("ban_reason", "Why it is banned"),
    )
    labels = {"wording_mode": "Wording", "kind": "Category", "ban_reason": "Why"}

    def export(self, target: Target) -> list[BookTraitItem]:
        return [
            self.item(splat, change.category, change.name, change)
            for splat, change in book_traits.changes(target.db, target.troupe)
        ]

    def item(self, splat: str, category: str, name: str, change: Any) -> BookTraitItem:
        return BookTraitItem(
            splat=splat,
            category=category,
            name=name,
            banned=change.banned,
            ban_reason=change.ban_reason,
            wording=change.wording,
            wording_mode=change.wording_mode,
            kind=change.kind,
        )

    def label(self, target: Target, item: BookTraitItem) -> str:
        return for_splat(item.name, item.splat)

    def current(self, target: Target, item: BookTraitItem) -> BookTraitItem | None:
        if target.splat_problem(item.splat):
            return None
        found = target.rules(item.splat).trait_changes.get((item.category, item.name))
        return self.item(item.splat, item.category, item.name, found) if found else None

    def problem(self, target: Target, item: BookTraitItem) -> str | None:
        problem = target.splat_problem(item.splat)
        if problem:
            return problem
        try:
            book_traits.book_definition(target.db, item.splat, item.category, item.name)
        except HTTPException:
            return f"{item.name} isn't in this troupe's rule set."
        return None

    def apply(
        self, target: Target, user: User, item: BookTraitItem, current: BookTraitItem | None
    ) -> None:
        db, troupe = target.db, target.troupe
        definition = book_traits.book_definition(db, item.splat, item.category, item.name)
        book_traits.set_ban(
            db,
            user,
            troupe,
            item.splat,
            definition,
            item.category,
            banned=item.banned,
            reason=item.ban_reason,
        )
        book_traits.set_wording(
            db,
            user,
            troupe,
            item.splat,
            definition,
            item.category,
            wording=item.wording,
            mode=item.wording_mode,
        )
        now = book_traits.change_of(db, troupe, item.splat, item.category, item.name)
        if now.kind != item.kind:
            book_traits.set_kind(
                db, user, troupe, item.splat, definition, item.category, kind=item.kind
            )


def teacher_item(row: TeacherRule) -> TeacherRuleItem:
    data = teaching.rule_data(row)
    return TeacherRuleItem(
        splat=data.splat,
        category=data.category,
        names=list(data.names),
        name_prefix=data.name_prefix,
        condition=dict(data.condition) if data.condition else None,
        always=data.always,
        holds=data.holds,
        rating=data.rating,
        actions=data.actions,
        willpower=data.willpower,
        games=data.games,
    )


class TeacherRuleKind(Kind[TeacherRuleItem]):
    def export(self, target: Target) -> list[TeacherRuleItem]:
        return [teacher_item(r) for r in teaching.rule_rows(target.db, target.troupe.id)]

    def label(self, target: Target, item: TeacherRuleItem) -> str:
        what = ", ".join(item.names) or (
            f"{item.name_prefix}…"
            if item.name_prefix
            else target.category_name(item.splat, item.category)
        )
        return for_splat(f"Teachers for {what}", item.splat)

    def current(self, target: Target, item: TeacherRuleItem) -> TeacherRuleItem | None:
        mine = item.model_dump()
        return next((t for t in self.export(target) if t.model_dump() == mine), None)

    def problem(self, target: Target, item: TeacherRuleItem) -> str | None:
        problem = target.trait_problem(item.splat, item.category, None)
        if problem is None:
            missing = [n for n in item.names if not target.has_trait(item.splat, item.category, n)]
            if missing:
                return f"{missing[0]} isn't in this troupe's rule set."
        return problem

    def apply(
        self, target: Target, user: User, item: TeacherRuleItem, current: TeacherRuleItem | None
    ) -> None:
        teaching.create(
            target.db,
            user,
            target.troupe,
            TeacherRuleData(
                splat=item.splat,
                category=item.category,
                names=tuple(dict.fromkeys(n for n in item.names if n)),
                name_prefix=item.name_prefix or None,
                condition=item.condition or None,
                always=item.always,
                holds=item.holds,
                rating=item.rating if item.holds == "rating" else None,
                actions=item.actions,
                willpower=item.willpower,
                games=item.games if item.willpower else 0,
            ),
        )


class SpecialisationKind(Kind[SpecialisationItem]):
    def export(self, target: Target) -> list[SpecialisationItem]:
        return [
            SpecialisationItem(category=category, name=name)
            for category, names in sorted(
                specializations.troupe_options(target.db, target.troupe.id).items()
            )
            for name in names
        ]

    def label(self, target: Target, item: SpecialisationItem) -> str:
        return f"{target.category_name('vampire', item.category)}: {item.name}"

    def current(self, target: Target, item: SpecialisationItem) -> SpecialisationItem | None:
        found = target.db.scalar(
            select(TroupeSpecialization).where(
                TroupeSpecialization.troupe_id == target.troupe.id,
                TroupeSpecialization.category_key == item.category,
                TroupeSpecialization.name == item.name.strip(),
            )
        )
        return item if found is not None else None

    def problem(self, target: Target, item: SpecialisationItem) -> str | None:
        category = target.rules("vampire").rule_set.categories.get(item.category)
        if category is None or not category.specializes:
            return "Not a kind of specialisation in this troupe's rule set."
        return None

    def apply(
        self,
        target: Target,
        user: User,
        item: SpecialisationItem,
        current: SpecialisationItem | None,
    ) -> None:
        listed = specializations.troupe_options(target.db, target.troupe.id).get(item.category, [])
        specializations.set_troupe_options(
            target.db, user, target.troupe, item.category, [*listed, item.name]
        )


class FillTableKind(Kind[FillTableItem]):
    editable = (Editable("entries", "Entries, one per line", multiline=True, lines=True),)

    def export(self, target: Target) -> list[FillTableItem]:
        return [
            FillTableItem(name=t.name, entries=t.entries)
            for t in target.db.scalars(
                select(RandomTable)
                .where(RandomTable.troupe_id == target.troupe.id)
                .order_by(RandomTable.name)
            )
        ]

    def label(self, target: Target, item: FillTableItem) -> str:
        return item.name

    def current(self, target: Target, item: FillTableItem) -> FillTableItem | None:
        return next((t for t in self.export(target) if t.name == item.name.strip()), None)

    def apply(
        self, target: Target, user: User, item: FillTableItem, current: FillTableItem | None
    ) -> None:
        responses.save_table(target.db, target.troupe.id, item.name.strip(), item.entries)

    def same(self, item: FillTableItem, current: FillTableItem | None) -> bool:
        tidy = [e.strip() for e in item.entries if e.strip()]
        return current is not None and current.entries == tidy


class NewsAgencyKind(Kind[NewsAgencyItem]):
    editable = (Editable("name", "Name"), Editable("description", "Description", multiline=True))

    def rows(self, target: Target) -> list[NewsAgency]:
        return list(
            target.db.scalars(
                select(NewsAgency)
                .where(NewsAgency.troupe_id == target.troupe.id)
                .order_by(NewsAgency.name)
            )
        )

    def export(self, target: Target) -> list[NewsAgencyItem]:
        return [
            NewsAgencyItem(name=a.name, description=a.description, colour=a.colour)
            for a in self.rows(target)
            if a.retired_at is None
        ]

    def label(self, target: Target, item: NewsAgencyItem) -> str:
        return item.name

    def row(self, target: Target, item: NewsAgencyItem) -> NewsAgency | None:
        return next((a for a in self.rows(target) if a.name == item.name.strip()), None)

    def current(self, target: Target, item: NewsAgencyItem) -> NewsAgencyItem | None:
        row = self.row(target, item)
        if row is None:
            return None
        return NewsAgencyItem(name=row.name, description=row.description, colour=row.colour)

    def apply(
        self, target: Target, user: User, item: NewsAgencyItem, current: NewsAgencyItem | None
    ) -> None:
        posts.keep_agency(
            target.db,
            user,
            target.troupe,
            self.row(target, item),
            item.name,
            item.description,
            item.colour,
        )


KINDS: dict[str, Kind[Any]] = {
    "setting": SettingKind(),
    "check": CheckKind(),
    "house_check": HouseCheckKind(),
    "cost": CostKind(),
    "creation": CreationKind(),
    "starting_trait": StartingTraitKind(),
    "action_kind": ActionKindKind(),
    "allowance": AllowanceKind(),
    "keyword": KeywordKind(),
    "house_trait": HouseTraitKind(),
    "written_rule": WrittenRuleKind(),
    "book_trait": BookTraitKind(),
    "teacher_rule": TeacherRuleKind(),
    "specialisation": SpecialisationKind(),
    "fill_table": FillTableKind(),
    "news_agency": NewsAgencyKind(),
}

# The kinds of rows each section exports, after its settings, in order.
SECTION_KINDS: dict[SectionKey, tuple[str, ...]] = {
    "checks": ("check", "house_check"),
    "costs": ("cost",),
    "starting": ("creation", "starting_trait"),
    "actions": ("action_kind", "allowance"),
    "keywords": ("keyword",),
    "house_traits": ("house_trait",),
    "written_rules": ("written_rule",),
    "book_traits": ("book_trait",),
    "teachers": ("teacher_rule",),
    "specialisations": ("specialisation",),
    "fill_tables": ("fill_table",),
    "news_agencies": ("news_agency",),
}


# --- exporting --------------------------------------------------------------------------------


def horatio_version() -> str:
    try:
        return version("horatio")
    except PackageNotFoundError:
        return ""


def export(db: Session, troupe: Troupe) -> SettingsDocument:
    """The troupe's settings that differ from Horatio's default, every section."""
    target = Target(db, troupe)
    sections: dict[str, list[Any]] = {key: [] for key in SECTIONS}
    for setting in SETTINGS.values():
        value = setting_value(troupe, setting.key)
        if value != setting_value_of_default(setting.key):
            sections[setting.section].append(SettingItem(key=setting.key, value=value))
    for section, kinds in SECTION_KINDS.items():
        for kind in kinds:
            sections[section] += KINDS[kind].export(target)
    versions = {
        r.splat: r.version
        for r in db.scalars(select(RuleSet).where(RuleSet.splat.in_(target.splats)))
    }
    return SettingsDocument(
        horatio=horatio_version(),
        rule_sets=dict(sorted(versions.items())),
        troupe=troupe.name,
        exported_on=date.today(),
        sections=Sections.model_validate(
            {k: [i.model_dump() for i in v] for k, v in sections.items()}
        ),
    )


def setting_value_of_default(key: str) -> Any:
    return json.loads(json.dumps(column_default(key), default=str))


# --- reviewing ---------------------------------------------------------------------------------

Status = Literal["new", "changes", "same", "cannot"]


@dataclass(frozen=True)
class Reviewed:
    section: SectionKey
    index: int
    label: str
    status: Status
    reason: str | None = None
    before: str | None = None
    after: str | None = None
    editable: tuple[Editable, ...] = ()


@dataclass(frozen=True)
class Review:
    troupe: str
    items: list[Reviewed]
    warnings: list[str] = field(default_factory=list[str])


def section_items(document: SettingsDocument) -> Iterable[tuple[SectionKey, int, Any]]:
    for section in SECTIONS:
        for index, item in enumerate(items(document, section)):
            yield section, index, item


def setting_in_place(section: SectionKey, item: Any) -> str | None:
    """Why a setting is in a section it doesn't belong to, or None."""
    if not isinstance(item, SettingItem):
        return None
    found = SETTINGS.get(item.key)
    if found is not None and found.section != section:
        return f"It belongs under {SECTIONS[found.section][0]}."
    return None


def review_item(target: Target, section: SectionKey, index: int, item: Any) -> Reviewed:
    kind = KINDS[item.type]
    problem = setting_in_place(section, item) or kind.problem(target, item)
    label = kind.label(target, item)
    if problem is not None:
        return Reviewed(section, index, label, "cannot", reason=problem)
    current = kind.current(target, item)
    editable = kind.editable
    if current is None:
        return Reviewed(section, index, label, "new", editable=editable)
    if kind.same(item, current):
        return Reviewed(section, index, label, "same", editable=editable)
    before, after = kind.words(item, current)
    return Reviewed(section, index, label, "changes", before=before, after=after, editable=editable)


def review(db: Session, troupe: Troupe, document: SettingsDocument) -> Review:
    """Each item of the document as it stands against the troupe."""
    target = Target(db, troupe, document)
    found = [review_item(target, s, i, item) for s, i, item in section_items(document)]
    return Review(troupe=document.troupe, items=found, warnings=warnings(target, document))


def warnings(target: Target, document: SettingsDocument) -> list[str]:
    """What the troupe should know before importing: backstory questions it lacks."""
    found: list[str] = []
    mode = next((i.value for i in document.sections.backstories if i.key == "backstory_mode"), None)
    if mode in ("either", "wizard") and not backstories.question_sets(
        target.db, target.troupe, archived=False
    ):
        found.append(
            "Backstory questions aren't carried, and this troupe has none: add some under "
            "Rules › Backstories, or players won't be able to write a backstory from questions."
        )
    return found


# --- applying -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Pick:
    section: SectionKey
    index: int


@dataclass
class Applied:
    # By section: how many items were added and how many changed.
    added: dict[str, int] = field(default_factory=dict[str, int])
    changed: dict[str, int] = field(default_factory=dict[str, int])

    def count(self, section: SectionKey, status: Status) -> None:
        tally = self.added if status == "new" else self.changed
        tally[section] = tally.get(section, 0) + 1

    def text(self) -> str:
        parts = []
        for key, (label, _) in SECTIONS.items():
            added, changed = self.added.get(key, 0), self.changed.get(key, 0)
            if added or changed:
                said = [f"{added} added" if added else "", f"{changed} changed" if changed else ""]
                parts.append(f"{label} ({', '.join(s for s in said if s)})")
        return "; ".join(parts) or "nothing"


def unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


# Applied first: what the others can name. The splats a troupe takes, then its house
# merits and flaws, then its own action kinds.
FIRST: tuple[SectionKey, ...] = ("who_may_join", "house_traits", "actions")
KIND_ORDER = ("setting", "action_kind")


def apply(
    db: Session,
    user: User,
    troupe: Troupe,
    document: SettingsDocument,
    picks: Sequence[Pick],
    source: str,
) -> Applied:
    """Import the ticked items, all or none. A failure names the item, and nothing is
    saved. One entry in the troupe's log says what came in, from where."""
    if troupe.archived_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Nothing can be imported into an archived troupe."
        )
    ticked = set(picks)
    for pick in ticked:
        if not 0 <= pick.index < len(items(document, pick.section)):
            raise unprocessable(f"{SECTIONS[pick.section][0]} has no item {pick.index + 1}.")
    order: list[SectionKey] = [*FIRST, *(s for s in SECTIONS if s not in FIRST)]
    applied = Applied()
    try:
        with db.begin_nested(), audit.quiet(db):
            target = Target(db, troupe, document)
            priced = False
            for section in order:
                chosen_items = sorted(
                    (
                        (i, item)
                        for i, item in enumerate(items(document, section))
                        if Pick(section, i) in ticked
                    ),
                    key=lambda found: (
                        KIND_ORDER.index(found[1].type) if found[1].type in KIND_ORDER else 9
                    ),
                )
                # A section's settings are set together, first: those set as one
                # (feeding, languages, free changes...) are always in one section.
                settings: list[tuple[str, SettingItem]] = []
                for index, item in chosen_items:
                    seen = review_item(target, section, index, item)
                    where = f"{SECTIONS[section][0]} › {seen.label}"
                    if seen.status == "cannot":
                        raise unprocessable(f"{where}: {seen.reason}")
                    if seen.status == "same":
                        continue
                    applied.count(section, seen.status)
                    if isinstance(item, SettingItem):
                        settings.append((where, item))
                        continue
                    if settings:
                        apply_settings(target, user, settings)
                        settings = []
                    kind = KINDS[item.type]
                    with failing(where):
                        kind.apply(target, user, item, kind.current(target, item))
                    priced = priced or item.type == "cost"
                if settings:
                    apply_settings(target, user, settings)
            if priced:
                # A troupe's fixed price for a fixed-rating merit is its value.
                sync_troupe_fixed_ratings(db, troupe.id)
        audit.record(
            db,
            user,
            "house.settings_imported",
            troupe_id=troupe.id,
            source=source,
            what=applied.text(),
        )
    finally:
        forget_rules(db)
    return applied


@contextmanager
def failing(where: str) -> Iterator[None]:
    """Name the item in any failure to apply it."""
    try:
        yield
    except HTTPException as error:
        if error.status_code >= 500:
            raise
        raise unprocessable(f"{where}: {error.detail}") from error
    except (ValueError, LookupError, ValidationError) as error:
        raise unprocessable(f"{where}: {error}") from error


def apply_settings(target: Target, user: User, chosen: Sequence[tuple[str, SettingItem]]) -> None:
    """Set some of the troupe's settings, each through what sets it in Customise; those
    that are set together (feeding, languages, free changes...) with the troupe's
    others. A failure names the setting, or for several, them all."""
    db, troupe = target.db, target.troupe
    values: dict[str, Any] = {}
    for _, item in chosen:
        setting = SETTINGS[item.key]
        values[item.key] = setting.adapter.validate_python(item.value)
    where = chosen[0][0] if len(chosen) == 1 else "; ".join(w for w, _ in chosen)

    def now(key: str) -> Any:
        return values[key] if key in values else getattr(troupe, key)

    def touched(*keys: str) -> bool:
        return any(k in values for k in keys)

    with failing(where):
        if touched("allowed_splats"):
            troupe_settings.set_splats(db, user, troupe, values["allowed_splats"])
        if touched("allowed_sects"):
            troupe_settings.set_sects(db, user, troupe, values["allowed_sects"])
        for key in (
            "session_xp",
            "downtime_xp",
            "starting_xp",
            "status_by",
            "titles_by",
            "status_at_checkin",
            "whos_who_negative",
            "badge_titles",
            "badge_status",
            "badge_pronouns",
            "starting_blood",
            "diablerie_flaws",
            "items_expire",
            "blood_bonds",
            "boons",
            "boon_players_see",
            "boon_players_settle",
            "player_nominations",
            "remembrances",
            "assamite_name",
            "rare_disciplines_two_actions",
            "written_rules_public",
            "location_limit",
        ):
            # Set as their editors set them: the value alone, checked by its type.
            if key in values:
                setattr(troupe, key, values[key])
        if touched("play_tabs_off"):
            play_tabs.set_tabs_off(db, user, troupe, values["play_tabs_off"])
        if touched("game_xp"):
            game_xp.save(db, user, troupe, game_xp.GameXpSettings.model_validate(values["game_xp"]))
        if touched("one_holder_titles"):
            # The rule sets' titles only: the troupe's own aren't carried.
            troupe.one_holder_titles = titles.offices(db, values["one_holder_titles"])
        if touched("golconda_enlightened"):
            troupe_settings.set_golconda(db, user, troupe, values["golconda_enlightened"])
        if touched("feeding", "feeding_resonance", "feeding_territories", "feeding_rack"):
            feeding.set_setting(
                db,
                user,
                troupe,
                feeding.Setting(
                    now("feeding"),
                    now("feeding_resonance"),
                    now("feeding_territories"),
                    now("feeding_rack"),
                ),
            )
        if touched("clan_rarity"):
            troupe_settings.set_clan_rarity(db, user, troupe, values["clan_rarity"])
        if touched("status_ban_clans"):
            troupe_settings.set_status_ban_clans(db, user, troupe, values["status_ban_clans"])
        if touched("default_bloodlines"):
            troupe_settings.set_default_bloodlines(db, user, troupe, values["default_bloodlines"])
        if touched("influence_lookback_days"):
            influence_lookups.set_lookback(db, user, troupe, values["influence_lookback_days"])
        if touched("languages", "languages_table", "natural_linguist_doubles"):
            languages.set_rule(
                db,
                user,
                troupe,
                now("languages"),
                values.get("languages_table"),
                now("natural_linguist_doubles"),
            )
        if touched("location_options_off"):
            options = location_catalogue.load_catalogue().options
            unknown = [k for k in values["location_options_off"] if k not in options]
            if unknown:
                raise unprocessable(f"No house option {unknown[0]!r} for locations.")
            troupe.location_options_off = sorted(set(values["location_options_off"]))
        if touched("quests_enabled", "quest_requests_per_cycle"):
            quests.set_settings(
                db, user, troupe, now("quests_enabled"), now("quest_requests_per_cycle")
            )
        if touched("retainer_rules"):
            retainer_upkeep.set_rules(
                db, user, troupe, retainer_rules_of(values["retainer_rules"].model_dump())
            )
        if touched("backstory_mode", "backstory_required"):
            backstories.set_settings(
                db, user, troupe, now("backstory_mode"), now("backstory_required")
            )
        if touched(
            "free_changes", "free_changes_days", "free_changes_games", "free_changes_excluded"
        ):
            excluded = (
                [(e.category, e.name) for e in values["free_changes_excluded"]]
                if "free_changes_excluded" in values
                else [(e["category"], e["name"]) for e in troupe.free_changes_excluded]
            )
            free_changes.check_excluded(db, troupe, excluded)
            free_changes.change_setting(
                db,
                user,
                troupe,
                now("free_changes"),
                now("free_changes_days"),
                now("free_changes_games"),
                excluded,
            )
        db.flush()
        forget_rules(db)

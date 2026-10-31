"""Sect status: what each status does, each sect's name for Accepted and its status
bans, the status each title and social age gives, and how much status a character
carries into a game (MET: VTM pp. 310-317, and the Camarilla, Sabbat and Anarch
chapters). The rules are written in `bns_met_vampire_status.toml`.

A status is a trait in the `status_traits` category, and what it does is kept in
the trait's properties:

    type        Abiding, Innate, Fleeting, Negative, or Accepted (which is not a
                status: it never counts toward a total, and cannot be spent, p. 310)
    sect        "General" for the status every sect has (pp. 313-317), else the sect
    passive     what holding it does, in a line of our own words
    spent       what spending it does
    source      where it usually comes from: a title, a merit, another status
    censure     a negative status: what its holder must not do (p. 316)
    punishment  a negative status: what breaking the censure brings
    duration    how long it lasts, as below: a negative status, or a fleeting one
                that lapses (Scholar)
    brings      a negative status: the negative status given with it, unless held
                already (Bloodhunted brings Forsaken, p. 389)
    takes_away  a negative status: the types of status its holder loses (Bloodhunted:
                abiding, innate and fleeting). Given it, the fleeting status held is
                lost for good; while it is held, titles, social age and merits give
                none of those types, and no fleeting status is gained.

and its page is the trait's page reference. A status says what holding it does,
or that it has `no_rules_yet`: a status of the Independent Alliance has its sect
and nothing more, as no book describes it, and staff use the troupe's own words.

A duration lasts `games` games or `months` months, whichever is longer; `stacks`
when each further one adds the same again (Warned); `this_game` for the game it is
given at only (Vulgar); `while_held` as long as the holder has that other status
(Disgraced, while Warned), else as `games` and `months` say. With none of these it
lasts until someone removes it. `text` says it in words.

Each sect names its Accepted (Acknowledged, Initiated, Committed) and its status
bans: a lesser ban cuts a character's fleeting status to 3 and a greater ban to 1
(the caps below). A ban says who it applies to, in words, and, where the sheet can
tell, `when` that holds, in the condition vocabulary of horatio.rules.checks.

A title gives the abiding status named in `status` for as long as it is held; or
one of `choose_one`, chosen at the start of each game (a Bishop's Blessed or
Enforcer); and with `while_absent`, more status while the holder of another title
is away from the game (a Seneschal's Authority, while the Prince is absent).
Horatio cannot know who is at a game, so the holder says so. A `note` says in words
what the data cannot (a Myrmidon's Sanctioned, which is fleeting status).

A title of a sect says what it gives: its status, or in `gives_none` why the book
gives it none, with the page; or that it has `no_rules_yet` (the Independent
Alliance's), with no page. The loader refuses a sect title that says none of
these, so no title is blank without a reason. A title with no sect can go to
anyone; a clan's title (a Tremere Lord) names its `clan` and no sect, and gives no
sect status.

A title's `aliases` are other names for the same office (a Templar is also called
a Paladin): each is a title of its own, giving the same as the title it names
(`alias_of`), ranked beside it, and a `unique` title's names are one office, held
by one character between them. A `unique` title is held by only one character in a
troupe at a time (a Prince, a Sheriff); any other may be held by several (a
Primogen, an Archon).

The caps (p. 313): a character carries into a game the status of one abiding
source (its titles and its social age are each a source), all its innate and
negative status, and up to 5 fleeting, or 3 under a lesser ban and 1 under a
greater.

Some merits and flaws change the fleeting cap (`cap_changes`): Reputation carries
1 more (p. 252), Tainted Embrace 1 fewer (p. 405), on top of any ban. One lets a
character no sect has Accepted hold a sect's fleeting status all the same
(`outsiders`): Emissary to the Camarilla, one Camarilla fleeting status (p. 404).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, cast, get_args

# A condition in the vocabulary of horatio.rules.checks, which imports the rule
# model, which imports this.
Condition = Mapping[str, Any]

StatusType = Literal["Abiding", "Innate", "Fleeting", "Negative", "Accepted"]
STATUS_TYPES: tuple[str, ...] = get_args(StatusType)
BanLevel = Literal["lesser", "greater"]
BAN_LEVELS: tuple[str, ...] = get_args(BanLevel)

STATUS_CATEGORY = "status_traits"
# The sect of the status every sect has.
GENERAL = "General"
# The types of status a negative status can take away from its holder.
TAKEN_TYPES = ("Abiding", "Innate", "Fleeting")
# Social ages, as horatio.social_age works them out.
SOCIAL_AGES = ("Neonate", "Ancilla", "Elder")


@dataclass(frozen=True)
class DurationData:
    text: str
    games: int | None = None
    months: int | None = None
    stacks: bool = False
    this_game: bool = False
    while_held: str | None = None

    @property
    def until_removed(self) -> bool:
        return not (self.games or self.months or self.this_game or self.while_held)


@dataclass(frozen=True)
class StatusData:
    name: str
    type: StatusType
    sect: str
    passive: str = ""
    spent: str = ""
    source: str = ""
    page: str | None = None
    censure: str = ""
    punishment: str = ""
    duration: DurationData | None = None
    # The negative status given with it: Bloodhunted's Forsaken.
    brings: tuple[str, ...] = ()
    # The types of status its holder loses: Bloodhunted's abiding, innate and fleeting.
    takes_away: tuple[str, ...] = ()
    # No book describes it yet (the Independent Alliance's): it has a name and a sect.
    no_rules_yet: bool = False

    @property
    def counts(self) -> bool:
        """Whether it is status at all: Accepted is not (p. 310)."""
        return self.type != "Accepted"


@dataclass(frozen=True)
class StatusBanData:
    level: BanLevel
    # Who it applies to, in words.
    applies_to: str
    # Where the sheet can tell (a clan, a Path): the condition, as in checks.
    when: Condition | None = None
    page: str | None = None


@dataclass(frozen=True)
class SectData:
    name: str
    # Its name for Accepted: Acknowledged, Initiated, Committed.
    accepted: str
    bans: tuple[StatusBanData, ...] = ()
    page: str | None = None


@dataclass(frozen=True)
class WhileAbsentData:
    """Status a title gives while the holder of another title is away from the game."""

    title: str
    status: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class TitleData:
    name: str
    sect: str | None = None
    status: tuple[str, ...] = ()
    choose_one: tuple[str, ...] = ()
    while_absent: tuple[WhileAbsentData, ...] = ()
    page: str | None = None
    # Its place at court, highest first: the order the rules data describes the
    # titles in (horatio.whos_who). None for a title that is only a name.
    rank: int | None = None
    # Only one character in a troupe holds it at a time (a Prince): a player cannot
    # choose it while another character holds it (horatio.titles).
    unique: bool = False
    # A clan's title (a Tremere Lord): it has no sect, and gives no sect status.
    clan: str | None = None
    # Other names for the same office (a Templar's Paladin), each a title of its own.
    aliases: tuple[str, ...] = ()
    # The title this one is another name for: it gives the same.
    alias_of: str | None = None
    # Why it gives no status, in words, where the book says so (the page is `page`).
    gives_none: str = ""
    # What the data cannot say about what it gives, in a line of our own words.
    note: str = ""
    # No book describes it yet (the Independent Alliance's): it gives nothing.
    no_rules_yet: bool = False

    @property
    def gives_status(self) -> bool:
        return bool(self.status or self.choose_one or self.while_absent)

    @property
    def office(self) -> str:
        """The title it is, whichever of its names it goes by: Baron for an Advocate."""
        return self.alias_of or self.name

    @property
    def named_status(self) -> tuple[str, ...]:
        """Every status the title can give."""
        return self.status + self.choose_one + tuple(s for a in self.while_absent for s in a.status)


@dataclass(frozen=True)
class SocialAgeStatusData:
    """The abiding status a sect gives a social age (a Camarilla elder's)."""

    sect: str
    age: str
    status: tuple[str, ...]
    page: str | None = None


@dataclass(frozen=True)
class StatusCapsData:
    abiding_sources: int = 1
    fleeting: int = 5
    lesser_ban: int = 3
    greater_ban: int = 1
    page: str | None = None


@dataclass(frozen=True)
class CapChangeData:
    """A merit or flaw that changes the most fleeting status its holder carries:
    `fleeting` more, or fewer, after any ban (Tainted Embrace: 1 fewer)."""

    category: str
    name: str
    fleeting: int
    page: str | None = None


@dataclass(frozen=True)
class OutsiderData:
    """A merit that lets a character no sect has Accepted hold up to `fleeting`
    fleeting status of `sect` (Emissary to the Camarilla)."""

    category: str
    name: str
    sect: str
    fleeting: int
    page: str | None = None


@dataclass(frozen=True)
class StatusRulesData:
    """A rule set's status rules beyond its status traits."""

    caps: StatusCapsData | None = None
    sects: Mapping[str, SectData] = field(default_factory=dict[str, SectData])
    social_ages: tuple[SocialAgeStatusData, ...] = ()
    cap_changes: tuple[CapChangeData, ...] = ()
    outsiders: tuple[OutsiderData, ...] = ()


NO_STATUS_RULES = StatusRulesData()


# --- reading ---------------------------------------------------------------------------------


def duration_from_dict(raw: Mapping[str, Any]) -> DurationData:
    return DurationData(
        text=raw.get("text", ""),
        games=raw.get("games"),
        months=raw.get("months"),
        stacks=raw.get("stacks", False),
        this_game=raw.get("this_game", False),
        while_held=raw.get("while_held"),
    )


def status_from_trait(name: str, properties: Mapping[str, Any], page: str | None) -> StatusData:
    duration = properties.get("duration")
    return StatusData(
        name=name,
        type=properties.get("type", ""),
        sect=properties.get("sect", ""),
        passive=properties.get("passive", ""),
        spent=properties.get("spent", ""),
        source=properties.get("source", ""),
        page=page,
        censure=properties.get("censure", ""),
        punishment=properties.get("punishment", ""),
        duration=duration_from_dict(duration) if duration else None,
        brings=tuple(properties.get("brings", [])),
        takes_away=tuple(properties.get("takes_away", [])),
        no_rules_yet=properties.get("no_rules_yet", False),
    )


def statuses_of(traits: Mapping[tuple[str, str], Any]) -> dict[str, StatusData]:
    """Each status in a rule set's traits (TraitData), by name."""
    return {
        name: status_from_trait(name, trait.properties, trait.page_reference)
        for (category, name), trait in traits.items()
        if category == STATUS_CATEGORY
    }


def ban_from_dict(raw: Mapping[str, Any]) -> StatusBanData:
    return StatusBanData(
        level=raw["level"],
        applies_to=raw.get("applies_to", ""),
        when=raw.get("when"),
        page=raw.get("page"),
    )


def sect_from_dict(raw: Mapping[str, Any]) -> SectData:
    return SectData(
        name=raw["name"],
        accepted=raw.get("accepted", ""),
        bans=tuple(ban_from_dict(b) for b in raw.get("bans", [])),
        page=raw.get("page"),
    )


def title_from_dict(raw: Mapping[str, Any]) -> TitleData:
    return TitleData(
        name=raw["name"],
        sect=raw.get("sect"),
        status=tuple(raw.get("status", [])),
        choose_one=tuple(raw.get("choose_one", [])),
        while_absent=tuple(
            WhileAbsentData(title=a["title"], status=tuple(a["status"]), note=a.get("note", ""))
            for a in raw.get("while_absent", [])
        ),
        page=raw.get("page"),
        rank=raw.get("rank"),
        unique=raw.get("unique", False),
        clan=raw.get("clan"),
        aliases=tuple(raw.get("aliases", [])),
        gives_none=raw.get("gives_none", ""),
        note=raw.get("note", ""),
        no_rules_yet=raw.get("no_rules_yet", False),
    )


def titles_from(raw: Iterable[str | Mapping[str, Any]]) -> tuple[TitleData, ...]:
    """Titles from a list of names, or tables with a name and what the title is
    (sect, status). A name may come both bare and as a table; the table says what it
    is. A table without a rank is ranked by its place among the tables, so the rules
    data lists them highest first. Each of a table's aliases is a title too, the same
    as the one it names. Sorted by name."""
    found: dict[str, TitleData] = {}
    described: dict[str, TitleData] = {}
    for entry in raw:
        if isinstance(entry, str):
            found.setdefault(entry, TitleData(name=entry))
            continue
        title = title_from_dict(entry)
        if title.name in described:
            raise ValueError(f"title {title.name!r} is described twice")
        if title.rank is None:
            title = replace(title, rank=len(described) + 1)
        described[title.name] = title
        found[title.name] = title
    named_by: dict[str, str] = {}
    for title in described.values():
        for alias in title.aliases:
            if alias in described:
                raise ValueError(f"{alias!r} is a title, and another name for {title.name}")
            if alias in named_by:
                raise ValueError(
                    f"{alias!r} is another name for both {named_by[alias]} and {title.name}"
                )
            named_by[alias] = title.name
            found[alias] = replace(title, name=alias, aliases=(), alias_of=title.name)
    return tuple(found[name] for name in sorted(found))


def social_age_from_dict(raw: Mapping[str, Any]) -> SocialAgeStatusData:
    return SocialAgeStatusData(
        sect=raw["sect"], age=raw["age"], status=tuple(raw["status"]), page=raw.get("page")
    )


def caps_from_dict(raw: Mapping[str, Any]) -> StatusCapsData:
    return StatusCapsData(
        abiding_sources=raw.get("abiding_sources", 1),
        fleeting=raw.get("fleeting", 5),
        lesser_ban=raw.get("lesser_ban", 3),
        greater_ban=raw.get("greater_ban", 1),
        page=raw.get("page"),
    )


def cap_change_from_dict(raw: Mapping[str, Any]) -> CapChangeData:
    return CapChangeData(
        category=raw["category"], name=raw["name"], fleeting=raw["fleeting"], page=raw.get("page")
    )


def outsider_from_dict(raw: Mapping[str, Any]) -> OutsiderData:
    return OutsiderData(
        category=raw["category"],
        name=raw["name"],
        sect=raw["sect"],
        fleeting=raw["fleeting"],
        page=raw.get("page"),
    )


def status_rules_from(
    caps: Mapping[str, Any] | None,
    sects: Iterable[Mapping[str, Any]],
    social_ages: Iterable[Mapping[str, Any]],
    cap_changes: Iterable[Mapping[str, Any]] = (),
    outsiders: Iterable[Mapping[str, Any]] = (),
) -> StatusRulesData:
    by_name: dict[str, SectData] = {}
    for raw in sects:
        sect = sect_from_dict(raw)
        if sect.name in by_name:
            raise ValueError(f"sect {sect.name!r} is described twice")
        by_name[sect.name] = sect
    return StatusRulesData(
        caps=caps_from_dict(caps) if caps is not None else None,
        sects=by_name,
        social_ages=tuple(social_age_from_dict(a) for a in social_ages),
        cap_changes=tuple(cap_change_from_dict(c) for c in cap_changes),
        outsiders=tuple(outsider_from_dict(o) for o in outsiders),
    )


# --- storing ---------------------------------------------------------------------------------


def plain(value: Any) -> Any:
    """A dataclass as a dict of what it says, leaving out what is empty: tuples as
    lists, nested dataclasses as dicts."""
    if hasattr(value, "__dataclass_fields__"):
        found = {k: plain(v) for k, v in vars(value).items()}
        return {
            k: v
            for k, v in found.items()
            if not (v is None or v is False or (isinstance(v, str | list | dict) and not v))
        }
    if isinstance(value, tuple | list):
        return [plain(v) for v in cast(Sequence[Any], value)]
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in cast(Mapping[str, Any], value).items()}
    return value


def status_rules_to_dict(rules: StatusRulesData, titles: Sequence[TitleData]) -> dict[str, Any]:
    """What `rule_sets.status_rules` holds: the caps and what changes them, the
    sects, the social ages, and the titles that are more than a name, each with its
    aliases (the names, aliases among them, are in `rule_sets.titles`)."""
    found: dict[str, Any] = {
        "sects": [plain(s) for s in rules.sects.values()],
        "social_ages": [plain(a) for a in rules.social_ages],
        "cap_changes": [plain(c) for c in rules.cap_changes],
        "outsiders": [plain(o) for o in rules.outsiders],
        "titles": [
            plain(t)
            for t in titles
            if t.alias_of is None
            and (t.sect or t.clan or t.gives_status or t.page or t.rank is not None)
        ],
    }
    if rules.caps is not None:
        found["caps"] = plain(rules.caps)
    return found


def status_rules_from_dict(raw: Mapping[str, Any]) -> StatusRulesData:
    return status_rules_from(
        raw.get("caps"),
        raw.get("sects", []),
        raw.get("social_ages", []),
        raw.get("cap_changes", []),
        raw.get("outsiders", []),
    )


# --- checking --------------------------------------------------------------------------------


def check_status_rules(
    traits: Mapping[tuple[str, str], Any],
    rules: StatusRulesData,
    titles: Sequence[TitleData],
) -> None:
    """Refuse status rules that name a status, sect, clan or title the rule set
    lacks; a status that says not what it does, nor that it has no rules yet; a
    status other than negative that brings or takes away status, or that brings
    status other than negative status of its sect; a title or social age giving
    status that is not abiding status of its sect; and a sect's title that says not
    what it gives, or why it gives nothing."""
    from horatio.rules.checks import validate_condition

    sect_names = {name for category, name in traits if category == "sect"}
    clan_names = {name for category, name in traits if category == "clan"}
    statuses = statuses_of(traits)

    for status in statuses.values():
        where = f"status {status.name!r}"
        if status.type not in STATUS_TYPES:
            raise ValueError(f"{where} has unknown type {status.type!r}")
        if status.sect != GENERAL and status.sect not in sect_names:
            raise ValueError(f"{where} has unknown sect {status.sect!r}")
        says = status.passive or status.spent or status.censure
        if status.no_rules_yet:
            if says or status.page:
                raise ValueError(f"{where} has no rules yet, so it says nothing more")
        elif not says:
            raise ValueError(f"{where} says not what it does, nor that it has no rules yet")
        duration = status.duration
        if duration is not None:
            if not duration.text:
                raise ValueError(f"{where}: its duration needs a text")
            if any(n is not None and n < 1 for n in (duration.games, duration.months)):
                raise ValueError(f"{where}: a duration is at least one game or month")
            if duration.while_held is not None and duration.while_held not in statuses:
                raise ValueError(f"{where} lasts while an unknown status is held")
        if (status.brings or status.takes_away) and status.type != "Negative":
            raise ValueError(f"{where} is not negative status, so brings or takes away none")
        for name in status.brings:
            brought = statuses.get(name)
            if brought is None:
                raise ValueError(f"{where} brings an unknown status {name!r}")
            if brought.type != "Negative" or brought.sect not in (GENERAL, status.sect):
                raise ValueError(f"{where} brings {name}, which is not negative status of its sect")
            if brought.brings:
                raise ValueError(f"{where} brings {name}, which brings more")
        for taken in status.takes_away:
            if taken not in TAKEN_TYPES:
                raise ValueError(f"{where} takes away {taken!r}, not a type of status it can")

    known_traits = set(traits)
    for sect in rules.sects.values():
        where = f"sect {sect.name!r}"
        if sect.name not in sect_names:
            raise ValueError(f"{where} is not a sect in the catalogue")
        accepted = statuses.get(sect.accepted)
        if accepted is None or accepted.type != "Accepted" or accepted.sect != sect.name:
            raise ValueError(f"{where}: its Accepted must be an Accepted status of the sect")
        for ban in sect.bans:
            if ban.level not in BAN_LEVELS:
                raise ValueError(f"{where} has a ban of unknown level {ban.level!r}")
            if not ban.applies_to:
                raise ValueError(f"{where} has a ban that says not who it applies to")
            if ban.when:
                validate_condition(ban.when, known_traits)

    def abiding(names: Iterable[str], sect: str | None, where: str) -> None:
        for name in names:
            status = statuses.get(name)
            if status is None:
                raise ValueError(f"{where} gives an unknown status {name!r}")
            if status.type != "Abiding":
                raise ValueError(f"{where} gives {name}, which is not abiding status")
            if sect is not None and status.sect not in (GENERAL, sect):
                raise ValueError(f"{where} gives {name}, which is {status.sect} status")

    title_names = {t.name for t in titles}
    for title in titles:
        where = f"title {title.name!r}"
        if title.sect is not None and title.sect not in sect_names:
            raise ValueError(f"{where} has unknown sect {title.sect!r}")
        if title.clan is not None:
            if title.clan not in clan_names:
                raise ValueError(f"{where} has unknown clan {title.clan!r}")
            if title.sect is not None:
                raise ValueError(f"{where} is a clan's title, so it has no sect")
            if title.gives_status:
                raise ValueError(f"{where} is a clan's title, so it gives no sect status")
        if title.no_rules_yet:
            if title.sect is None:
                raise ValueError(f"{where} has no rules yet, but no sect to have them")
            if title.gives_status or title.gives_none or title.note or title.page:
                raise ValueError(f"{where} has no rules yet, so it says nothing more")
        elif title.gives_none:
            if title.gives_status:
                raise ValueError(f"{where} gives status, and says why it gives none")
            if not title.page:
                raise ValueError(f"{where} says why it gives no status, but not where")
        elif title.sect is not None and not title.gives_status:
            raise ValueError(f"{where} is a {title.sect} title that says not what it gives")
        abiding(title.named_status, title.sect, where)
        if len(title.choose_one) == 1:
            raise ValueError(f"{where} gives a choice of one status")
        for absent in title.while_absent:
            if absent.title not in title_names:
                raise ValueError(f"{where} names an unknown title {absent.title!r}")
            if not absent.status:
                raise ValueError(f"{where} gives nothing while {absent.title} is absent")

    for age in rules.social_ages:
        where = f"social age {age.sect} {age.age}"
        if age.sect not in sect_names:
            raise ValueError(f"{where} has unknown sect")
        if age.age not in SOCIAL_AGES:
            raise ValueError(f"{where}: no such social age")
        abiding(age.status, age.sect, where)

    for change in rules.cap_changes:
        if (change.category, change.name) not in known_traits:
            raise ValueError(f"a cap change names an unknown trait {change.name!r}")
        if not change.fleeting:
            raise ValueError(f"the cap change of {change.name!r} changes nothing")
    for outsider in rules.outsiders:
        if (outsider.category, outsider.name) not in known_traits:
            raise ValueError(f"an outsider rule names an unknown trait {outsider.name!r}")
        if outsider.sect not in rules.sects:
            raise ValueError(f"{outsider.name!r} gives status of a sect with no status rules")
        if outsider.fleeting < 1:
            raise ValueError(f"{outsider.name!r} lets its holder hold no status")

    caps = rules.caps
    if caps is not None and not (
        caps.abiding_sources >= 1 and caps.fleeting >= caps.lesser_ban >= caps.greater_ban >= 0
    ):
        raise ValueError("status caps: the fleeting caps must shrink from no ban to a greater ban")

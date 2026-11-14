"""A character's Jyhad card (#537): a just-for-fun card of a vampire in the style of
a *Vampire: The Eternal Struggle* crypt card, made from its portrait and sheet. It
is hidden (its player finds it by tapping the clan symbol seven times; staff open
it from the troupe's Characters list), it has no bearing on play, and it is never
official: its frame is Horatio's own drawing (#560), with no frame scan or card
image, and it is marked unofficial.

**Capacity** (1-11 in VTES) comes from the Generation background and the
disciplines. KRCG's card data (all 1,802 vampires) gives each capacity's average
discipline points, counting an inferior discipline 1 and a superior 2
(`AVERAGE_POINTS`). The Generation background sets a band (`BANDS`, overlapping, as
VTES's own vampires do), and within it:

1. the capacity whose average is nearest the character's own points over the
   disciplines on its card (the lower on a tie);
2. one higher, while there is room in the band, for a character that has earned
   well over its troupe's starting XP in play (`XP_WELL_ABOVE` times it);
3. one or two lower for Lesser Generation 1 or 2 (MET: VTM p. 263), never below
   the band's bottom.

Thin Blooded (p. 265) is always capacity 1.

**Disciplines:** superior at 4 or 5 dots, inferior at 1 to 3. A path of
Thaumaturgy or Necromancy counts as its discipline, at its primary path's dots
(the highest: no other path may be above the primary, p. 187). At most six, the
highest kept, as on any VTES card; a tie keeps the sheet's order. They're printed as a
VTES card prints them (#869): the inferior first, then the superior, each in the order
of their three letters, stacked up the sidebar so the superior sit at its foot; with
KRCG's white-bordered symbols (squares and diamonds) once fetched, all or none.

**Title:** those VTES has, with its votes ("Camarilla Prince of Asheville: 2
votes"); a character with none shows its sect.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import checkin, crypt_templates, pictures, sheets, social_age, titles, vtes_symbols
from horatio.models import Character, RuleSet, Troupe

# Each capacity's average discipline points (inferior 1, superior 2) over every
# vampire in KRCG's card data (static.krcg.org/data/vtes.json), as #537 found.
AVERAGE_POINTS = {
    1: 1.2,
    2: 1.3,
    3: 2.1,
    4: 3.0,
    5: 4.7,
    6: 5.5,
    7: 6.7,
    8: 7.4,
    9: 8.5,
    10: 9.4,
    11: 10.3,
}
# The capacities each Generation background may have, lowest and highest. No dots
# is a Neonate's (MET: VTM p. 101).
BANDS = {
    1: (1, 4),  # Neonate
    2: (4, 6),  # Ancilla
    3: (6, 7),  # Pretender Elder
    4: (7, 8),  # Master Elder
    5: (8, 9),  # Luminary Elder
}
# A discipline is superior from this many dots (MET's intermediate to advanced).
SUPERIOR_FROM = 4
# The most disciplines any VTES card has.
MOST_DISCIPLINES = 6
# Earning this many times the troupe's starting XP in play moves the capacity up
# one within its band: at 30 starting XP and a game's 3 to 5, about a year of play.
XP_WELL_ABOVE = 2
# What a character with no troupe started with, as the book has it (MET: VTM p. 108).
BOOK_STARTING_XP = 30
LESSER_GENERATION = {"Lesser Generation 1": 1, "Lesser Generation 2": 2}
THIN_BLOODED = "Thin Blooded"
# The titles VTES has, with their votes. A Baron's other names are a Baron's.
VOTES = {
    "Inner Circle": 4,
    "Justicar": 3,
    "Prince": 2,
    "Primogen": 1,
    "Cardinal": 3,
    "Priscus": 3,
    "Archbishop": 2,
    "Bishop": 1,
    "Baron": 2,
}
SAME_AS = {"Advocate": "Baron", "President": "Baron", "Minister": "Baron"}
# Titles held of a city, "Prince of Asheville"; the rest are the sect's.
OF_A_CITY = {"Prince", "Primogen", "Archbishop", "Bishop", "Baron"}


@dataclass(frozen=True)
class Discipline:
    name: str
    dots: int

    @property
    def superior(self) -> bool:
        return self.dots >= SUPERIOR_FROM

    @property
    def points(self) -> int:
        return 2 if self.superior else 1


def on_card(held: Iterable[tuple[str, int]]) -> list[Discipline]:
    """The disciplines a card shows, from (name, dots) in sheet order: each path
    counted as its discipline at its highest, highest first, at most six."""
    dots: dict[str, int] = {}
    for name, rating in held:
        if rating > 0:
            discipline = vtes_symbols.discipline_of(name)
            dots[discipline] = max(dots.get(discipline, 0), rating)
    found = sorted(dots.items(), key=lambda d: -d[1])  # stable: ties keep their order
    return [Discipline(name, n) for name, n in found[:MOST_DISCIPLINES]]


def printed_order(disciplines: Iterable[Discipline]) -> list[Discipline]:
    """The disciplines in the order a VTES card prints them, top to bottom (#869):
    the inferior ones, then the superior, each in the order of their three letters,
    so a superior sits at the foot of the stack, by the text box."""
    return sorted(disciplines, key=lambda d: (d.superior, abbreviation(d.name)))


def points(disciplines: Iterable[Discipline]) -> int:
    return sum(d.points for d in disciplines)


def band(generation: int) -> tuple[int, int]:
    return BANDS[min(max(generation, 1), max(BANDS))]


def nearest(found: int, low: int, high: int) -> int:
    """The capacity from `low` to `high` whose average points are nearest `found`."""
    return min(range(low, high + 1), key=lambda c: (abs(AVERAGE_POINTS[c] - found), c))


def capacity(
    generation: int,
    discipline_points: int,
    *,
    earned_xp: int = 0,
    starting_xp: int = BOOK_STARTING_XP,
    lesser_generation: int = 0,
    thin_blooded: bool = False,
) -> int:
    """A vampire's capacity, as the module's docstring says."""
    if thin_blooded:
        return 1
    low, high = band(generation)
    chosen = nearest(discipline_points, low, high)
    if earned_xp >= XP_WELL_ABOVE * max(starting_xp, 1):
        chosen = min(chosen + 1, high)
    return max(chosen - lesser_generation, low)


def votes(title: str) -> int:
    return VOTES.get(SAME_AS.get(title, title), 0)


def title_line(sect: str | None, held: Sequence[str], city: str = "") -> str | None:
    """The card's sect and title line: the held title with the most votes, if VTES
    has any of them, else the sect alone."""
    voting = [t for t in held if votes(t)]
    if not voting:
        return sect
    title = max(voting, key=votes)  # the first of the most
    city = city.strip()
    place = f" of {city}" if city and SAME_AS.get(title, title) in OF_A_CITY else ""
    n = votes(title)
    said = f"{title}{place}: {n} vote{'s' if n > 1 else ''}"
    return f"{sect} {said}" if sect else said


# --- a character's card --------------------------------------------------------------------


@dataclass(frozen=True)
class CardDiscipline:
    name: str
    superior: bool
    # Where KRCG's symbol is, if the custodian fetched it; else its three letters show.
    # White-bordered, as a printed card has them, when the fetch brought those (#869).
    symbol: str | None
    abbreviation: str
    # Whether `symbol` is white-bordered: then it's drawn as it is, on no plate.
    bordered: bool = False


@dataclass(frozen=True)
class Card:
    # Why it has no card, or None: then the rest is the card.
    missing: str | None
    name: str
    clan: str | None
    clan_symbol: str | None
    # The sect, as the sheet has it: the frame is dark for the Camarilla, lighter else.
    sect: str | None
    sect_line: str | None
    capacity: int | None
    # KRCG's capacity drop, if fetched; else the card draws one.
    capacity_symbol: str | None
    disciplines: list[CardDiscipline]
    # The 4:5 portrait (horatio.pictures); add "/portrait.webp".
    picture: str | None
    text: str
    flavour: str
    # The clan's crypt card template the custodian uploaded (horatio.crypt_templates),
    # if there is one: the card is drawn on it, not on Horatio's own frame.
    template: str | None = None
    template_key: str | None = None


def symbol_url(group: str, name: str | None, fetched: set[str]) -> str | None:
    return f"/api/vtes-symbols/svg/{group}/{name}.svg" if name and name in fetched else None


def bordered_url(group: str, name: str | None, fetched: set[str]) -> str | None:
    """A white-bordered symbol, as a printed card has them: WebP, KRCG having no SVG
    of them."""
    return f"/api/vtes-symbols/webp_wb/{group}/{name}.webp" if name and name in fetched else None


def card_disciplines(
    shown: Sequence[Discipline],
    inferior: set[str],
    superior: set[str],
    bordered: Mapping[str, set[str]],
) -> list[CardDiscipline]:
    """The disciplines on the card: all with KRCG's white-bordered symbols if every one
    has one, so the stack is all of a kind; else their plain symbols, else letters."""

    def group(d: Discipline) -> str:
        return "disc/sup" if d.superior else "disc/inf"

    def krcg(d: Discipline) -> str | None:
        return vtes_symbols.DISCIPLINES.get(d.name)

    edged = [bordered_url(group(d), krcg(d), bordered[group(d)]) for d in shown]
    whole = all(edged)
    return [
        CardDiscipline(
            name=d.name,
            superior=d.superior,
            symbol=edge
            if whole
            else symbol_url(group(d), krcg(d), superior if d.superior else inferior),
            abbreviation=abbreviation(d.name),
            bordered=whole and edge is not None,
        )
        for d, edge in zip(shown, edged, strict=True)
    ]


def capacity_symbol_url(record: Mapping[str, object]) -> str | None:
    """KRCG's capacity drop: in WebP (and PNG) only, as KRCG has no SVG of it."""
    files = record.get("files")
    icons = files.get("webp/icon", []) if isinstance(files, Mapping) else []
    found = vtes_symbols.CAPACITY in icons
    return f"/api/vtes-symbols/webp/icon/{vtes_symbols.CAPACITY}.webp" if found else None


def abbreviation(discipline: str) -> str:
    return vtes_symbols.DISCIPLINES.get(discipline, discipline[:3].lower())


def troupe_of(db: Session, character: Character) -> Troupe | None:
    """Where its titles are: its home troupe (an NPC's own), else the first it joined."""
    joined = [m.troupe_id for m in sheets.memberships(db, character)]
    chosen = character.home_troupe_id or character.owner_troupe_id or next(iter(joined), None)
    return db.get(Troupe, chosen) if chosen else None


def starting_xp(db: Session, character: Character, troupe: Troupe | None) -> int:
    if troupe is not None:
        return troupe.starting_xp
    found = db.scalar(select(RuleSet.starting_xp).where(RuleSet.splat == character.splat))
    return found or BOOK_STARTING_XP


def city_of(troupe: Troupe | None) -> str:
    setting = (troupe.profile or {}).get("setting", {}) if troupe else {}
    city = setting.get("city", "") if isinstance(setting, Mapping) else ""
    return city if isinstance(city, str) else ""


def card(db: Session, character: Character) -> Card:
    """The character's card as its sheet stands now."""
    age = social_age.standings(db, [character.id])[character.id]
    blank = Card(
        missing=None,
        name=character.name,
        clan=age.clan,
        clan_symbol=None,
        sect=None,
        sect_line=None,
        capacity=None,
        capacity_symbol=None,
        disciplines=[],
        picture=None,
        text=character.card_text,
        flavour=character.card_flavour,
    )
    if age.age not in social_age.AGES:
        return replace(blank, missing="Only a vampire has a Jyhad card.")
    picture = pictures.picture_url(character.id, character.picture_id)
    if picture is None:
        return replace(blank, missing="A Jyhad card needs the character's picture.")

    rows = sheets.sheet_rows(db, character)
    generation = 0
    lesser = 0
    thin = False
    sect: str | None = None
    held: list[tuple[str, int]] = []
    for row in rows:
        key, name, rating = row.category.key, row.definition.name, row.trait.rating
        if key == "backgrounds" and name == "Generation":
            generation = rating or 0
        elif key == "flaws" and name in LESSER_GENERATION:
            lesser = max(lesser, LESSER_GENERATION[name])
        elif key == "flaws" and name == THIN_BLOODED:
            thin = True
        elif key == "sect":
            sect = name
        elif key == "disciplines":
            held.append((name, rating or 0))
    shown = on_card(held)
    troupe = troupe_of(db, character)
    record = vtes_symbols.manifest()
    clans = vtes_symbols.symbols(record, "clan")
    inferior = vtes_symbols.symbols(record, "disc/inf")
    superior = vtes_symbols.symbols(record, "disc/sup")
    bordered = {
        "disc/inf": vtes_symbols.bordered(record, "disc/inf"),
        "disc/sup": vtes_symbols.bordered(record, "disc/sup"),
    }
    clan = age.clan
    templates = crypt_templates.manifest()
    template_key = crypt_templates.chosen(clan, sect, crypt_templates.present(templates))
    krcg_clan = (
        vtes_symbols.CLANS.get(clan) or vtes_symbols.CLANS.get(clan.split(":")[0].strip())
        if clan
        else None
    )
    return replace(
        blank,
        clan_symbol=symbol_url("clan", krcg_clan, clans),
        sect=sect,
        sect_line=title_line(
            sect, titles.held(db, troupe.id, character.id) if troupe else [], city_of(troupe)
        ),
        capacity=capacity(
            generation,
            points(shown),
            earned_xp=checkin.earned(db, [character.id])[character.id],
            starting_xp=starting_xp(db, character, troupe),
            lesser_generation=lesser,
            thin_blooded=thin,
        ),
        capacity_symbol=capacity_symbol_url(record),
        disciplines=card_disciplines(printed_order(shown), inferior, superior, bordered),
        picture=picture,
        template=(
            f"/api/characters/{character.id}/jyhad-card/template.webp"
            f"?v={crypt_templates.version(templates)}"
            if template_key
            else None
        ),
        template_key=template_key,
    )

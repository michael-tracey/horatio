"""Clan merits: the bloodline and rarity merits a character's clan needs (MET: VTM
pp. 237-238), taken from its merit points while it is built.

A bloodline needs its bloodline merit ("Bloodline: Coyote" for Gangrel: Coyote), and
a clan that is not common in the setting a rarity merit: Uncommon Clan (2 points),
Rare Clan (4) or Restricted Clan (6). Choosing the clan takes them, at their value,
from the merit points; choosing another gives them back. The wizard shows them as
the clan's, not picks, and they cannot be picked or taken off by hand. They count
against the 7-point merit limit like any merit bought (p. 237), and once creation is
finished they stay as they are: they cannot be removed (p. 236).

The setting decides the rarity. It is the sect of the troupe the character is built
for or homed in, if that troupe takes characters of one sect only, and otherwise the
character's own sect. The clan's rarity there is the troupe's house rule for the clan
(Troupe.clan_rarity), else the book's for that sect (`clan_rarity` in the rule set,
kept in each clan's properties by horatio.rules.files). A bloodline is as rare as its
clan. A setting's default bloodline needs no bloodline merit, and its clan's own line
is then one step rarer instead (p. 238). A clan and bloodline that would cost more
than 7 points take Restricted Clan instead (p. 237). With no rarity to go by (no sect
yet, or one the book gives no rarities for, and no house rule), the rarity merits are
left to the player to pick, and staff to check.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from horatio.models import Character, CharacterTrait, Troupe
from horatio.rules.files import EVERYWHERE, RARITIES
from horatio.rules.model import RuleSetData, SheetTrait, TroupeRules
from horatio.rules.pricing import fixed_rating
from horatio.sheets import (
    chosen,
    conflict,
    find_definition,
    rules_for,
    rules_troupe,
    sheet_rows,
)

BLOODLINE = "Bloodline:"
# The merit each rarity needs; a common clan needs none.
RARITY_MERITS = {"uncommon": "Uncommon Clan", "rare": "Rare Clan", "restricted": "Restricted Clan"}
RESTRICTED = "Restricted Clan"
# The merit limit (p. 237), where the rule set's merits category gives none.
MERIT_LIMIT = 7


@dataclass(frozen=True)
class ClanMerit:
    """A merit the clan needs, at its value, and why."""

    name: str
    points: int
    why: str
    page: str | None = None


@dataclass(frozen=True)
class Setting:
    """Where a clan's rarity comes from: the setting's sect, and the troupe's house
    rule (by clan, without the bloodline), named for the reason it gives."""

    sect: str | None = None
    house: Mapping[str, str] | None = None
    troupe: str = ""


def family_of(clan: str) -> str:
    return clan.split(":", 1)[0].strip()


def bloodline_merit(rule_set: RuleSetData, clan: str) -> str | None:
    """The bloodline merit a bloodline's clan needs, if the catalogue has one."""
    if ":" not in clan:
        return None
    merit = f"{BLOODLINE} {clan.split(':', 1)[1].strip()}"
    return merit if ("merits", merit) in rule_set.traits else None


def is_clan_merit(name: str) -> bool:
    return name.startswith(BLOODLINE) or name in RARITY_MERITS.values()


def book_rarity(rule_set: RuleSetData, family: str, sect: str | None) -> tuple[str, str] | None:
    """The clan's rarity in the sect's setting and the page saying so, if the book
    gives it: for the sect's setting, or for every setting (an independent bloodline)."""
    by_sect = rule_set.trait_properties("clan", family).get("rarity", {})
    found = by_sect.get(EVERYWHERE) or (by_sect.get(sect) if sect else None)
    return (found["rarity"], found["page"]) if found else None


def default_bloodline(rule_set: RuleSetData, family: str, sect: str) -> str | None:
    """The bloodline the sect's setting plays as the clan's default, if any."""
    return next(
        (
            name
            for (category, name), trait in rule_set.traits.items()
            if category == "clan"
            and family_of(name) == family
            and sect in trait.properties.get("default_in", {})
        ),
        None,
    )


def rarity_known(rule_set: RuleSetData, clan: str | None, setting: Setting) -> bool:
    """Whether the setting says how rare the clan is, so its rarity merit is the
    setting's to give rather than the player's to pick."""
    if clan is None:
        return False
    family = family_of(clan)
    return (
        family in (setting.house or {}) or book_rarity(rule_set, family, setting.sect) is not None
    )


def needed(
    rule_set: RuleSetData, clan: str | None, setting: Setting, value: Callable[[str], int]
) -> list[ClanMerit]:
    """The merits this clan needs in this setting, each at its `value`."""
    if clan is None:
        return []
    family = family_of(clan)
    sect = setting.sect
    merits: list[ClanMerit] = []
    rarity: str | None = None
    because, page = "", None
    house = (setting.house or {}).get(family)
    book = book_rarity(rule_set, family, sect)
    everywhere = EVERYWHERE in rule_set.trait_properties("clan", family).get("rarity", {})
    if house is not None:
        rarity = house
        because = f"{setting.troupe or 'The troupe'} plays {family} as {rarity}."
    elif book is not None:
        rarity, page = book
        because = (
            f"{family} is {rarity} in every setting."
            if everywhere
            else f"{family} is {rarity} in the {sect} setting."
            if rarity != "restricted"
            else f"The {sect} setting does not list {family}, so it is restricted."
        )
    default = default_bloodline(rule_set, family, sect) if sect else None
    if rarity is not None and default is not None and clan == family:
        # The default bloodline's merit cost moves to the clan's own line (p. 238).
        rarity = RARITIES[min(RARITIES.index(rarity) + 1, len(RARITIES) - 1)]
        because = (
            f"The {sect} setting plays {default} as the default {family}, so {family}'s"
            f" own line takes its bloodline's cost: it is {rarity} there."
        )
        page = f"238, {page}" if page else "238"
    restricted = ClanMerit(RESTRICTED, value(RESTRICTED), because, page)
    if rarity == "restricted":
        return [restricted]
    if rarity is not None and rarity != "common":
        name = RARITY_MERITS[rarity]
        merits.append(ClanMerit(name, value(name), because, page))
    merit = bloodline_merit(rule_set, clan)
    if merit is not None and not (sect and sect in default_in(rule_set, clan)):
        merits.append(ClanMerit(merit, value(merit), f"{clan} is a bloodline.", "238"))
    total = sum(m.points for m in merits)
    if rarity is not None and total > MERIT_LIMIT:
        names = " and ".join(f"{m.name} ({m.points})" for m in merits)
        return [
            ClanMerit(
                RESTRICTED,
                value(RESTRICTED),
                f"{clan} would cost {total} merit points, {names}, more than {MERIT_LIMIT}:"
                " Restricted Clan covers it.",
                "237",
            )
        ]
    return merits


def default_in(rule_set: RuleSetData, clan: str) -> Mapping[str, str]:
    return rule_set.trait_properties("clan", clan).get("default_in", {})


# --- the character ---------------------------------------------------------------


def setting_of(db: Session, character: Character) -> Setting:
    """The character's setting: its troupe's one sect, else its own; and the troupe's
    house rule for rarity."""
    troupe_id = rules_troupe(character)
    troupe = db.get(Troupe, troupe_id) if troupe_id is not None else None
    sect = chosen(db, character, "sect")
    if troupe is not None and len(troupe.allowed_sects) == 1:
        sect = troupe.allowed_sects[0]
    if troupe is None:
        return Setting(sect)
    return Setting(sect, dict(troupe.clan_rarity), troupe.name)


def valuer(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> Callable[[str], int]:
    """A merit's value under the character's rules (a troupe can price it)."""

    def value(name: str) -> int:
        return fixed_rating(rules, sheet, "merits", name) or 0

    return value


@dataclass(frozen=True)
class ClanMerits:
    """What the character's clan needs, and which merits are the clan's to give."""

    merits: list[ClanMerit]
    # The setting gives the rarity, so the rarity merits are the clan's, not picks.
    rarity_known: bool

    def managed(self, name: str) -> bool:
        return name.startswith(BLOODLINE) or (self.rarity_known and name in RARITY_MERITS.values())

    @property
    def names(self) -> set[str]:
        return {m.name for m in self.merits}

    @property
    def points(self) -> int:
        return sum(m.points for m in self.merits)


def clan_merits(db: Session, character: Character) -> ClanMerits:
    rules = rules_for(db, character)
    sheet = [r.as_rules_trait() for r in sheet_rows(db, character)]
    clan = chosen(db, character, "clan")
    setting = setting_of(db, character)
    return ClanMerits(
        needed(rules.rule_set, clan, setting, valuer(rules, sheet)),
        rarity_known(rules.rule_set, clan, setting),
    )


def building(character: Character) -> bool:
    """Whether the character's clan merits follow its clan: a PC still being built."""
    return character.kind == "pc" and character.creation_completed_at is None


def held(db: Session, character: Character) -> ClanMerits:
    """The clan merits the character holds now, as the clan gives them: none for a
    character that is not being built."""
    if not building(character):
        return ClanMerits([], False)
    found = clan_merits(db, character)
    names = {
        r.definition.name
        for r in sheet_rows(db, character)
        if r.category.key == "merits" and r.trait.creation_pick is not None
    }
    return ClanMerits([m for m in found.merits if m.name in names], found.rarity_known)


def not_by_hand(name: str, found: ClanMerits) -> str:
    """Why a clan merit cannot be picked or taken off by hand."""
    if name in found.names:
        return f"{name} comes with the clan; choose another clan to take it off."
    if name.startswith(BLOODLINE):
        return f"{name} comes with its bloodline's clan: choose that clan instead."
    return f"{name} comes with the clan's rarity in this setting, not as a pick."


def sync(db: Session, character: Character) -> str | None:
    """Give a character being built the merits its clan needs, from its merit points,
    and take back those it no longer needs. Says why, if the merits it now needs
    leave the merit points overspent."""
    if not building(character):
        return None
    found = clan_merits(db, character)
    rows = [r for r in sheet_rows(db, character) if r.category.key == "merits"]
    changed = False
    for row in rows:
        name = row.definition.name
        if found.managed(name) and name not in found.names and not row.trait.granted_rating:
            db.delete(row.trait)
            changed = True
    have = {r.definition.name for r in rows}
    for merit in found.merits:
        if merit.name in have:
            continue
        definition, _ = find_definition(db, character, "merits", merit.name)
        db.add(
            CharacterTrait(
                character_id=character.id,
                trait_definition_id=definition.id,
                rating=merit.points,
                free_rating=merit.points,
                creation_pick=merit.points,
            )
        )
        changed = True
    db.flush()
    if not changed:
        return None
    return overspent(db, character, found)


def overspent(db: Session, character: Character, found: ClanMerits) -> str | None:
    """Why the merit points are overspent, if the clan's merits overspend them."""
    from horatio.creation import pools  # imports horatio.sheets, as this does

    budget = pools(db, character).get(("merits", 0))
    if budget is None or budget.kind != "points" or budget.remaining >= 0 or not found.merits:
        return None
    clan = chosen(db, character, "clan")
    names = " and ".join(f"{m.name} ({m.points} points)" for m in found.merits)
    spent = budget.used - found.points
    return (
        f"{clan} needs {names}, which does not fit: {spent} of the {budget.allowed} merit"
        " points are spent on other merits. Take some off first, or choose another clan."
    )


def resync(db: Session, characters: Sequence[Character]) -> None:
    """Bring these characters' clan merits into line after their setting changes (a
    house rule, or another troupe to build for). Overspent points are left for the
    player to settle: finishing creation waits on it."""
    for character in characters:
        sync(db, character)


def refuse_overspent(message: str | None) -> None:
    if message is not None:
        raise conflict(message)

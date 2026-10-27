"""A troupe's Who's Who (issue #264): its active characters, for its players as well
as its staff, in place of the spreadsheet troupes kept by hand. It is never public:
only the troupe's staff and the players of active characters in it, home or
visiting, see it (horatio.permissions.can_see_whos_who).

**Who is on it.** The troupe's characters now, not retired: its PCs, home or
visiting, and of its NPCs only those that hold a title there or that staff list on
it (Character.on_whos_who). Untitled NPCs stay the storytellers' own, as at a game
(horatio.play_others).

**Each entry:** the picture, name, clan and social age (horatio.social_age), the
player (by their name, or their handle if they prefer, horatio.preferences), the
titles held here in court order, what others can see or sense about it, as its
badge says (horatio.badges), and the status bans that apply to it (MET: VTM p. 312).
Sect status is not shown, unless the troupe adds the negative status each character
carries into a game here, which is public in the sect anyway (p. 312).

**The views:**

- the court: every titled character, once, in the order of its highest title
  (horatio.titles.court_order);
- by clan: one section per seated clan, by name;
- Other: the characters of clans with no seat at court. A clan has a seat when
  someone holds Primogen for it here; a troupe where no one does seats every clan;
- no longer with us: retired characters the troupe lists.

Each entry has the character's pronouns and its player's (horatio.pronouns). Who
represents a clan without a seat (#267) and why a character left (#268) each have
their place in an entry, empty until those land.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import badges, preferences, sect_status, social_age, titles
from horatio.models import Character, CharacterTitle, Troupe, TroupeMembership, User
from horatio.sheets import rules_for, sheet_rows

# The title whose holders give their clan a seat at court.
PRIMOGEN = "Primogen"


@dataclass(frozen=True)
class Entry:
    character: Character
    clan: str | None
    social_age: str
    sect: str | None
    # The player's name or handle; None for an NPC.
    player: str | None
    titles: list[str]
    visible: list[str]
    bans: list[str]
    # Carried into a game here, if the troupe shows it.
    negative: list[str]
    # Its home troupe's name, for a visiting character.
    visiting_from: str | None
    visiting: bool
    # The character's pronouns and its player's, if they gave them.
    pronouns: str | None = None
    player_pronouns: str | None = None
    # Filled in by #267 and #268.
    represented_by: str | None = None
    left_reason: str | None = None

    @property
    def family(self) -> str | None:
        """Its clan without the bloodline: "Brujah" for "Brujah: True Brujah"."""
        return clan_family(self.clan)


@dataclass
class WhosWho:
    # Everyone on it, by name.
    entries: list[Entry]
    # Titled characters, in court order.
    court: list[uuid.UUID] = field(default_factory=list[uuid.UUID])
    # Each seated clan's characters, by clan and then name; None for no clan yet.
    clans: list[tuple[str | None, list[uuid.UUID]]] = field(
        default_factory=list[tuple[str | None, list[uuid.UUID]]]
    )
    other: list[uuid.UUID] = field(default_factory=list[uuid.UUID])
    departed: list[uuid.UUID] = field(default_factory=list[uuid.UUID])
    # The clans with a seat at court, or None if every clan has one.
    seated: list[str] | None = None


def clan_family(clan: str | None) -> str | None:
    return clan.split(":")[0].strip() if clan else None


def ban_wording(level: str, applies_to: str) -> str:
    """A status ban in words, such as "Greater status ban: A known Caitiff."."""
    return f"{level.capitalize()} status ban: {applies_to}"


def bans(db: Session, character: Character) -> list[str]:
    """The status bans of its sect that apply to it, as the sheet shows or staff say."""
    rows = sheet_rows(db, character)
    sect = next((r.definition.name for r in rows if r.category.key == "sect"), None)
    sect_data = rules_for(db, character).rule_set.status_rules.sects.get(sect) if sect else None
    found = sect_status.bans_of(db, character, sect_data, [r.as_rules_trait() for r in rows])
    return [ban_wording(b.level, b.applies_to) for b in found if b.applies]


def player_name(user: User) -> str:
    """The player as the Who's Who names them: their name, or their handle."""
    return f"@{user.handle}" if preferences.read(user).whos_who_handle else user.display_name


def members(db: Session, troupe: Troupe, held: dict[uuid.UUID, list[str]]) -> list[Character]:
    """The troupe's active characters on its Who's Who, by name."""
    found = db.scalars(
        select(Character)
        .join(TroupeMembership, TroupeMembership.character_id == Character.id)
        .where(
            TroupeMembership.troupe_id == troupe.id,
            TroupeMembership.left_at.is_(None),
            Character.status == "active",
        )
        .order_by(Character.name, Character.id)
    )
    return [c for c in found if c.kind == "pc" or c.on_whos_who or held.get(c.id)]


def seated_clans(entries: Sequence[Entry]) -> list[str] | None:
    """The clans with a seat at court: those someone holds Primogen for. None, for
    every clan, where no one holds Primogen."""
    found = {e.family for e in entries if PRIMOGEN in e.titles and e.family}
    return sorted(found) if found else None


def whos_who(db: Session, troupe: Troupe) -> WhosWho:
    order = titles.court_order(db, troupe.id)
    held: dict[uuid.UUID, list[str]] = defaultdict(list)
    for who, name in db.execute(
        select(CharacterTitle.character_id, CharacterTitle.name).where(
            CharacterTitle.troupe_id == troupe.id
        )
    ):
        held[who].append(name)
    for names in held.values():
        names.sort(key=lambda n: titles.court_key(order, n))
    characters = members(db, troupe, held)
    ids = [c.id for c in characters]
    standing = social_age.standings(db, ids)
    sects = titles.character_sects(db, ids)
    visible = badges.visible_to_others(db, characters)
    players = {
        u.id: u
        for u in db.scalars(
            select(User).where(User.id.in_({c.player_id for c in characters if c.kind == "pc"}))
        )
    }
    homes = {
        t.id: t.name
        for t in db.scalars(
            select(Troupe).where(Troupe.id.in_({c.home_troupe_id for c in characters}))
        )
    }
    entries: list[Entry] = []
    for c in characters:
        visiting = c.kind == "pc" and c.home_troupe_id != troupe.id
        negative = (
            badges.counted([n for n, t in badges.carried(db, c, troupe.id) if t == "Negative"])
            if troupe.whos_who_negative
            else []
        )
        entries.append(
            Entry(
                character=c,
                clan=standing[c.id].clan,
                social_age=standing[c.id].age,
                sect=sects.get(c.id),
                player=player_name(players[c.player_id]) if c.kind == "pc" else None,
                pronouns=c.pronouns,
                player_pronouns=players[c.player_id].pronouns if c.kind == "pc" else None,
                titles=held.get(c.id, []),
                visible=visible[c.id],
                bans=bans(db, c),
                negative=negative,
                visiting=visiting,
                visiting_from=homes.get(c.home_troupe_id)
                if visiting and c.home_troupe_id
                else None,
            )
        )
    found = WhosWho(entries=entries, seated=seated_clans(entries))
    titled = [e for e in entries if e.titles]
    titled.sort(key=lambda e: (titles.court_key(order, e.titles[0]), e.character.name.lower()))
    found.court = [e.character.id for e in titled]
    by_clan: dict[str | None, list[uuid.UUID]] = defaultdict(list)
    other: list[Entry] = []
    for e in entries:
        if found.seated is None or e.family is None or e.family in found.seated:
            by_clan[e.family].append(e.character.id)
        else:
            other.append(e)
    # Other by clan, so each clan's characters are together.
    found.other = [e.character.id for e in sorted(other, key=lambda e: e.family or "")]
    # Clans by name, and characters with no clan yet last.
    found.clans = sorted(by_clan.items(), key=lambda c: (c[0] is None, c[0] or ""))
    return found

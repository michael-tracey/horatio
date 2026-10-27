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
- Other: the characters of clans with no seat at court, each with who speaks for
  it there;
- no longer with us: retired characters the troupe lists.

**Seats at court** (#267) are the court's custom, not the sect's rules. The troupe's
staff choose which clans have one (Troupe.seated_clans). Until they do, a clan has
one when someone holds Primogen for it here, and a troupe where no one does seats
every clan. A character of a clan without a seat is **represented by** a seated
clan, or by what its player says ("Anarch"). Its player sets it, and staff can
change it. It is kept on the character's membership of the troupe, so it goes when
the character leaves.

Each entry has the character's pronouns and its player's (horatio.pronouns). Why
a character left (#268) has its place in an entry, empty until that lands.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, badges, feeding, preferences, sect_status, social_age, titles
from horatio.models import Character, CharacterTitle, Troupe, TroupeMembership, User
from horatio.sheets import conflict, membership, rules_for, sheet_rows, unprocessable

# The title whose holders give their clan a seat at court, until staff choose.
PRIMOGEN = "Primogen"
# The longest a character's Represented by can be, in characters.
REPRESENTED_BY_LENGTH = 60


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


# --- seats at court ------------------------------------------------------------------------


def primogen_clans(db: Session, troupe: Troupe) -> list[str]:
    """The clans someone active holds Primogen for here, by clan without the bloodline."""
    holders = db.scalars(
        select(CharacterTitle.character_id)
        .join(Character, CharacterTitle.character_id == Character.id)
        .where(
            CharacterTitle.troupe_id == troupe.id,
            CharacterTitle.name == PRIMOGEN,
            Character.status == "active",
        )
    )
    standing = social_age.standings(db, list(holders))
    return sorted({f for s in standing.values() if (f := clan_family(s.clan))})


def seated_clans(db: Session, troupe: Troupe) -> list[str] | None:
    """The clans with a seat at court: those staff chose, or else those someone holds
    Primogen for. None, for every clan, where staff haven't chosen and no one holds
    Primogen."""
    if troupe.seated_clans is not None:
        return sorted(troupe.seated_clans)
    return primogen_clans(db, troupe) or None


def has_seat(seated: Sequence[str] | None, clan: str | None) -> bool:
    """Whether a character of this clan sits with its clan: one with no clan yet does."""
    family = clan_family(clan)
    return seated is None or family is None or family in seated


def set_seats(db: Session, staff: User, troupe: Troupe, clans: Sequence[str] | None) -> None:
    """Choose the clans with a seat at court, each one of the troupe's clans; None goes
    back to the clans whose Primogen is held here."""
    if clans is not None:
        known = feeding.troupe_clans(db, troupe)
        unknown = sorted(set(clans) - set(known))
        if unknown:
            raise unprocessable(f"Not a clan here: {', '.join(unknown)}.")
        if not clans:
            raise unprocessable(
                "Give at least one clan a seat; to seat every clan, choose them all."
            )
        clans = sorted(set(clans))
    if troupe.seated_clans == clans:
        return
    troupe.seated_clans = list(clans) if clans is not None else None
    db.flush()
    audit.record(
        db,
        staff,
        "troupe.seats",
        troupe_id=troupe.id,
        clans=", ".join(clans) if clans is not None else "those whose Primogen is held here",
    )


def set_represented_by(
    db: Session, actor: User, troupe: Troupe, character: Character, words: str | None
) -> str | None:
    """Say who speaks at court for a character of a clan without a seat: a seated
    clan, or a few words of the player's own. Blank leaves it to nobody yet."""
    found = membership(db, character, troupe.id)
    if found is None or character.status != "active":
        raise conflict(f"{character.name} is not in this troupe.")
    clan = social_age.standings(db, [character.id])[character.id].clan
    if has_seat(seated_clans(db, troupe), clan):
        raise conflict(f"{character.name}'s clan has a seat at court here.")
    words = " ".join((words or "").split()) or None
    if words is not None and len(words) > REPRESENTED_BY_LENGTH:
        raise unprocessable(f"Keep it to {REPRESENTED_BY_LENGTH} characters.")
    if found.represented_by != words:
        found.represented_by = words
        db.flush()
        audit.record(
            db,
            actor,
            "character.represented_by",
            troupe_id=troupe.id,
            character_id=character.id,
            by=words or "nobody yet",
        )
    return words


# --- the Who's Who ---------------------------------------------------------------------------


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
    seated = seated_clans(db, troupe)
    represented = {
        who: by
        for who, by in db.execute(
            select(TroupeMembership.character_id, TroupeMembership.represented_by).where(
                TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None)
            )
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
                represented_by=None
                if has_seat(seated, standing[c.id].clan)
                else represented.get(c.id),
                negative=negative,
                visiting=visiting,
                visiting_from=homes.get(c.home_troupe_id)
                if visiting and c.home_troupe_id
                else None,
            )
        )
    found = WhosWho(entries=entries, seated=seated)
    titled = [e for e in entries if e.titles]
    titled.sort(key=lambda e: (titles.court_key(order, e.titles[0]), e.character.name.lower()))
    found.court = [e.character.id for e in titled]
    by_clan: dict[str | None, list[uuid.UUID]] = defaultdict(list)
    other: list[Entry] = []
    for e in entries:
        if has_seat(seated, e.clan):
            by_clan[e.family].append(e.character.id)
        else:
            other.append(e)
    # Other by clan, so each clan's characters are together.
    found.other = [e.character.id for e in sorted(other, key=lambda e: e.family or "")]
    # Clans by name, and characters with no clan yet last.
    found.clans = sorted(by_clan.items(), key=lambda c: (c[0] is None, c[0] or ""))
    return found

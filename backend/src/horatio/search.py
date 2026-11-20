"""Searching everything from the top bar (#1046): what a word finds among the
characters, players, boons, locations, quests, equipment, news and announcements the
person may see, each kind a group of its own, each hit opening its page.

Nothing shows that its own page would refuse the person. Each kind asks the rules its
pages ask (horatio.permissions, the boon ledger's keepers in horatio.boon_harpy, the
quests' `role_of`, and so on), never rules of its own; where the page is more generous
than a search should be, the search is narrower (players, below).

A search asks the database a bounded number of times: once or twice for each kind, and
for the few kinds that depend on a troupe's own setting (the Who's Who, a Harpy's
ledger), once or twice for each of the person's troupes, up to `MOST_TROUPES`. Each
kind finds at most `LIMIT` hits, the current troupe's first, and says if there were more.

The manual, and later the troupe's settings (#1047), are searched in the browser, which
already holds them (frontend/src/search).
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from sqlalchemy import (
    ColumnElement,
    SQLColumnExpression,
    and_,
    case,
    false,
    func,
    or_,
    select,
    true,
    union,
)
from sqlalchemy.orm import Session

from horatio import boon_harpy, boon_ledger, boons, locations, quests, whos_who
from horatio.models import (
    Boon,
    Character,
    EquipmentItem,
    Location,
    Post,
    Quest,
    QuestMember,
    Troupe,
    TroupeMembership,
    TroupeStaff,
    User,
)
from horatio.permissions import (
    Role,
    TroupeAction,
    allows,
    member_troupe_ids,
    troupe_roles,
    viewable_characters,
    whos_who_troupes,
)

# Hits shown of each kind.
LIMIT = 5
# What is searched for: at least two letters, and no more than a long name.
SHORTEST = 2
LONGEST = 100
# The person's troupes asked one by one, the current troupe first.
MOST_TROUPES = 10


@dataclass(frozen=True)
class Hit:
    """One thing found: what it is called, a few words more, and where its page is."""

    kind: str
    key: uuid.UUID
    title: str
    detail: str
    to: str
    troupe_id: uuid.UUID | None


@dataclass
class Reach:
    """Who is searching, the troupes they are a member of, not archived, with their
    role in each, and the troupe they are in now, if any."""

    db: Session
    user: User
    current: uuid.UUID | None
    troupes: dict[uuid.UUID, Troupe] = field(default_factory=dict)
    roles: dict[uuid.UUID, Role | None] = field(default_factory=dict)

    @classmethod
    def of(cls, db: Session, user: User, current: uuid.UUID | None) -> "Reach":
        ids = member_troupe_ids(db, user)
        found = list(db.scalars(select(Troupe).where(Troupe.id.in_(ids)))) if ids else []
        # The current troupe first, then by name, for those asked one by one.
        found.sort(key=lambda t: (t.id != current, t.name.lower()))
        return cls(db, user, current, {t.id: t for t in found}, troupe_roles(db, user, found))

    @property
    def custodian(self) -> bool:
        return self.user.is_custodian

    def may(self, action: TroupeAction) -> list[uuid.UUID]:
        """The person's troupes where they may take `action`, as horatio.permissions says."""
        return [t for t in self.troupes if allows(self.roles[t], action)]

    def where(
        self, column: SQLColumnExpression[uuid.UUID], action: TroupeAction
    ) -> ColumnElement[bool]:
        """`column` is a troupe where the person may take `action`: any troupe for the
        custodian, who can do anything in any troupe."""
        return true() if self.custodian else column.in_(self.may(action))

    def first(self, column: SQLColumnExpression[Any]) -> list[ColumnElement[int]]:
        """An order that puts the current troupe's first, to go before the rest."""
        if self.current is None:
            return []
        return [case((column == self.current, 0), else_=1)]

    @cached_property
    def characters(self) -> list[Character]:
        """The person's own PCs, retired and in creation too."""
        return list(
            self.db.scalars(
                select(Character).where(Character.kind == "pc", Character.player_id == self.user.id)
            )
        )


def like(text: str) -> str:
    """`text` anywhere, ignoring case, with `%` and `_` only themselves (escape "\\")."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def holds(text: str, *columns: SQLColumnExpression[str]) -> ColumnElement[bool]:
    pattern = like(text)
    return or_(*(c.ilike(pattern, escape="\\") for c in columns))


def shortened(text: str, most: int = 90) -> str:
    """The first line of `text`, cut at a word to at most `most` characters."""
    line = " ".join(text.split())
    if len(line) <= most:
        return line
    cut = line[:most].rsplit(" ", 1)[0]
    return f"{cut}…"


def in_order(reach: Reach, hits: Sequence[Hit]) -> list[Hit]:
    """The current troupe's first, each once, keeping the order otherwise."""
    once: dict[uuid.UUID, Hit] = {}
    for hit in hits:
        once.setdefault(hit.key, hit)
    return sorted(once.values(), key=lambda h: h.troupe_id != reach.current)


# --- characters -------------------------------------------------------------------------------


def character_page(character: Character) -> str:
    """A character's page: a stock NPC's is its troupe's builder, as the roster links it."""
    if character.kind == "npc" and character.npc_form == "stock":
        return f"/troupes/{character.owner_troupe_id}/npcs/{character.id}"
    return f"/characters/{character.id}"


def character_detail(character: Character) -> str:
    words = ["NPC" if character.kind == "npc" else ""]
    if character.status == "retired":
        words.append("Retired")
    elif character.creation_completed_at is None:
        words.append("Being built")
    return " · ".join(w for w in words if w)


def find_characters(reach: Reach, text: str) -> list[Hit]:
    """The sheets the person may open (`viewable_characters`); and, from the Who's Who
    of each troupe they play in, the characters it lists, opening it there."""
    db = reach.db
    troupe = func.coalesce(
        Character.home_troupe_id, Character.owner_troupe_id, Character.building_troupe_id
    )
    sheets = db.scalars(
        select(Character)
        .where(viewable_characters(reach.user), holds(text, Character.name))
        .order_by(*reach.first(troupe), func.lower(Character.name), Character.id)
        .limit(LIMIT + 1)
    )
    hits = [
        Hit(
            "characters",
            c.id,
            c.name,
            character_detail(c),
            character_page(c),
            c.home_troupe_id or c.owner_troupe_id or c.building_troupe_id,
        )
        for c in sheets
    ]
    if not reach.custodian:
        hits += whos_who_hits(reach, text, {h.key for h in hits})
    return in_order(reach, hits)


def whos_who_hits(reach: Reach, text: str, found: set[uuid.UUID]) -> list[Hit]:
    """Characters on the Who's Who of the person's troupes where they are not its
    running staff, who see every sheet there already."""
    troupes = [
        t
        for t in list(reach.troupes.values())[:MOST_TROUPES]
        if not allows(reach.roles[t.id], TroupeAction.VIEW_MEMBER_CHARACTERS)
    ]
    seen = whos_who_troupes(reach.db, reach.user, troupes, reach.roles)
    lower = text.casefold()
    hits: list[Hit] = []
    for troupe in troupes:
        if troupe.id not in seen:
            continue
        for c in whos_who.listed(reach.db, troupe):
            if c.id in found or lower not in c.name.casefold():
                continue
            found.add(c.id)
            gone = "No longer with us" if c.status == "retired" else "On the Who's Who"
            to = f"/troupes/{troupe.id}/whos-who#c-{c.id}"
            hits.append(Hit("characters", c.id, c.name, gone, to, troupe.id))
            if len(hits) > LIMIT:
                return hits
    return hits


# --- players ----------------------------------------------------------------------------------


def people_of(troupe_ids: Sequence[uuid.UUID]) -> ColumnElement[bool]:
    """The people in any of the troupes, as a condition on User: their staff, and the
    players of their active characters, home or visiting (as horatio.permissions'
    `is_member` has it)."""
    ids = list(troupe_ids)
    if not ids:
        return false()
    members = union(
        select(Troupe.lead_user_id).where(Troupe.id.in_(ids)),
        select(TroupeStaff.user_id).where(TroupeStaff.troupe_id.in_(ids)),
        select(Character.player_id)
        .join(TroupeMembership, TroupeMembership.character_id == Character.id)
        .where(
            TroupeMembership.troupe_id.in_(ids),
            TroupeMembership.left_at.is_(None),
            Character.kind == "pc",
            Character.status == "active",
        ),
    )
    return User.id.in_(select(members.subquery().c[0]))


def find_players(reach: Reach, text: str) -> list[Hit]:
    """By name or handle, never email. Anyone signed in may open a profile, but a search
    finds only the people of the person's own troupes; the custodian finds anyone."""
    name = text.removeprefix("@")
    if len(name) < SHORTEST:
        return []
    # Those of the current troupe first, and said to be of it.
    here = people_of([reach.current]) if reach.current is not None else None
    query = (
        select(User, here if here is not None else false())
        .where(User.merged_into_id.is_(None), holds(name, User.display_name, User.handle))
        .order_by(*([here.desc()] if here is not None else []))
        .order_by(func.lower(User.display_name), User.id)
        .limit(LIMIT + 1)
    )
    if not reach.custodian:
        query = query.where(people_of(list(reach.troupes)))
    return [
        Hit(
            "players",
            u.id,
            u.display_name,
            f"@{u.handle}",
            f"/players/{u.id}",
            reach.current if is_here else None,
        )
        for u, is_here in reach.db.execute(query)
    ]


# --- boons ------------------------------------------------------------------------------------


def find_boons(reach: Reach, text: str) -> list[Hit]:
    """As the ledger shows them: every boon of the troupes whose ledger the person keeps
    as staff, or as a Harpy or Lesser Harpy who may see it (horatio.boon_harpy.keeper);
    and those their own characters' Play Views show (horatio.boons.shown_to_player).
    By the sides' names, the reason and the conditions, never the staff note."""
    db = reach.db
    found: list[tuple[Boon, str]] = []
    # Staff, and the custodian everywhere.
    staff = reach.may(TroupeAction.MANAGE_BOONS)
    query = (
        select(Boon)
        .join(Troupe, Troupe.id == Boon.troupe_id)
        .where(Troupe.boons, boon_ledger.holding(text))
        .order_by(*reach.first(Boon.troupe_id), Boon.made_on.desc(), Boon.id)
        .limit(LIMIT + 1)
    )
    if reach.custodian or staff:
        kept = query.where(true() if reach.custodian else Boon.troupe_id.in_(staff))
        found += [(b, f"/troupes/{b.troupe_id}/boons?boon={b.id}") for b in db.scalars(kept)]
    # A Harpy's or Lesser Harpy's, as their character, in the Play View's ledger.
    if not reach.custodian:
        harpies: dict[uuid.UUID, uuid.UUID] = {}
        for troupe in list(reach.troupes.values())[:MOST_TROUPES]:
            if troupe.id in staff or not boons.tracked(troupe) or troupe.boon_harpy != "full":
                continue
            keeper = boon_harpy.keeper(db, reach.user, troupe, "view")
            if keeper is not None and keeper.character is not None:
                harpies[troupe.id] = keeper.character.id
        if harpies:
            for b in db.scalars(query.where(Boon.troupe_id.in_(list(harpies)))):
                ledger = f"/play/characters/{harpies[b.troupe_id]}/ledger"
                found.append((b, f"{ledger}?troupe={b.troupe_id}&boon={b.id}"))
    # Their own characters', in each one's Play View.
    found += player_boons(reach, text)
    return boon_hits(reach, found)


def player_boons(reach: Reach, text: str) -> list[tuple[Boon, str]]:
    db = reach.db
    ledgers = [(c, boons.ledger_of(db, c)) for c in reach.characters]
    sides = [
        and_(Boon.troupe_id == t.id, or_(Boon.debtor_id == c.id, Boon.creditor_id == c.id))
        for c, t in ledgers
        if t is not None and t.boon_players_see != "intake"
    ]
    if not sides:
        return []
    candidates = db.scalars(
        select(Boon)
        .where(
            or_(*sides),
            Boon.state.in_(("registered", "settled")),
            boon_ledger.holding(text),
        )
        .order_by(*reach.first(Boon.troupe_id), Boon.made_on.desc(), Boon.id)
        .limit(LIMIT * 4)
    )
    found: list[tuple[Boon, str]] = []
    for boon in candidates:
        for character, troupe in ledgers:
            if troupe is not None and boons.shown_to_player(troupe, boon, character):
                found.append((boon, f"/play/characters/{character.id}?tab=boons"))
                break
    return found


def boon_hits(reach: Reach, found: list[tuple[Boon, str]]) -> list[Hit]:
    ids = {i for b, _ in found for i in (b.debtor_id, b.creditor_id) if i is not None}
    names: dict[uuid.UUID, str] = {}
    if ids:
        query = select(Character.id, Character.name).where(Character.id.in_(ids))
        names = {i: name for i, name in reach.db.execute(query)}

    def side(character_id: uuid.UUID | None, name: str) -> str:
        return names.get(character_id, name) if character_id is not None else name

    hits = []
    for b, to in found:
        title = (
            f"{shortened(side(b.debtor_id, b.debtor_name), 40)} owes "
            f"{shortened(side(b.creditor_id, b.creditor_name), 40)} {boons.a_boon(b.kind)}"
        )
        state = "" if b.state == "registered" else boons.STATES[b.state]
        detail = " · ".join(w for w in (state, shortened(b.reason)) if w)
        hits.append(Hit("boons", b.id, title, detail, to, b.troupe_id))
    return in_order(reach, hits)


# --- locations --------------------------------------------------------------------------------


def find_locations(reach: Reach, text: str) -> list[Hit]:
    """The record, for those who keep it (MANAGE_LOCATIONS); for a player, the names of
    the locations their characters hold, shown on the character's sheet."""
    db = reach.db
    kept = db.scalars(
        select(Location)
        .where(
            reach.where(Location.troupe_id, TroupeAction.MANAGE_LOCATIONS),
            holds(text, Location.name, Location.address),
        )
        .order_by(*reach.first(Location.troupe_id), func.lower(Location.name), Location.id)
        .limit(LIMIT + 1)
    )
    hits = [
        Hit(
            "locations",
            loc.id,
            loc.name,
            shortened(loc.address, 60),
            f"/troupes/{loc.troupe_id}/locations/{loc.id}",
            loc.troupe_id,
        )
        for loc in kept
    ]
    mine = {c.id: c for c in reach.characters}
    if mine and len(hits) <= LIMIT:
        held = db.scalars(
            select(Location)
            .join(Troupe, Troupe.id == Location.troupe_id)
            .where(
                locations.held(mine),
                Troupe.archived_at.is_(None),
                holds(text, Location.name),
            )
            .order_by(*reach.first(Location.troupe_id), func.lower(Location.name), Location.id)
            .limit(LIMIT + 1)
        )
        for loc in held:
            holder = mine.get(loc.controller_id) or mine[loc.joint_id]  # type: ignore[index]
            to = f"/characters/{holder.id}"
            hits.append(
                Hit("locations", loc.id, loc.name, f"Held by {holder.name}", to, loc.troupe_id)
            )
    return in_order(reach, hits)


# --- quests -----------------------------------------------------------------------------------


def find_quests(reach: Reach, text: str) -> list[Hit]:
    """By name and objective, never staff's notes: for staff, the troupe's quests where it
    runs them, a narrator only those assigned to them or to any narrator
    (horatio.quests.narrator_may_see); for a player, those their characters may see
    (horatio.quests.role_of), in the character's Quests."""
    db = reach.db
    staff = reach.may(TroupeAction.ANSWER_ASSIGNED_RESPONSES)
    running = reach.may(TroupeAction.MANAGE_QUESTS)
    narrating = [t for t in staff if t not in running]
    hits: list[Hit] = []
    if reach.custodian or staff:
        mine = (
            true()
            if reach.custodian
            else or_(
                Quest.troupe_id.in_(running),
                and_(
                    Quest.troupe_id.in_(narrating),
                    or_(
                        Quest.assigned_to_user_id == reach.user.id,
                        Quest.assigned_to_any_narrator,
                    ),
                ),
            )
        )
        kept = db.scalars(
            select(Quest)
            .join(Troupe, Troupe.id == Quest.troupe_id)
            .where(Troupe.quests_enabled, mine, holds(text, Quest.name, Quest.objective))
            .order_by(*reach.first(Quest.troupe_id), func.lower(Quest.name), Quest.id)
            .limit(LIMIT + 1)
        )
        for q in kept:
            if q.troupe_id in narrating and not quests.narrator_may_see(reach.user, q):
                continue
            to = f"/troupes/{q.troupe_id}/quests/{q.id}"
            hits.append(Hit("quests", q.id, q.name, shortened(q.objective), to, q.troupe_id))
    if len(hits) <= LIMIT:
        hits += player_quests(reach, text, {h.key for h in hits})
    return in_order(reach, hits)


def player_quests(reach: Reach, text: str, found: set[uuid.UUID]) -> list[Hit]:
    db = reach.db
    mine = {c.id: c for c in reach.characters}
    if not mine:
        return []
    candidates = [
        q
        for q in db.scalars(
            select(Quest)
            .join(Troupe, Troupe.id == Quest.troupe_id)
            .where(quests.maybe_seen_by(mine), holds(text, Quest.name, Quest.objective))
            .order_by(*reach.first(Quest.troupe_id), func.lower(Quest.name), Quest.id)
            .limit(LIMIT * 2)
        )
        if q.id not in found
    ]
    if not candidates:
        return []
    # Which of the characters each quest might be for, so `role_of` is asked only of them.
    joined = db.execute(
        select(QuestMember.quest_id, QuestMember.character_id).where(
            QuestMember.quest_id.in_([q.id for q in candidates]),
            QuestMember.character_id.in_(list(mine)),
        )
    ).all()
    playing = db.execute(
        select(TroupeMembership.troupe_id, TroupeMembership.character_id).where(
            TroupeMembership.character_id.in_(list(mine)), TroupeMembership.left_at.is_(None)
        )
    ).all()
    hits: list[Hit] = []
    for q in candidates:
        maybe = dict.fromkeys(
            [q.leader_id]
            + [c for quest_id, c in joined if quest_id == q.id]
            + [c for troupe_id, c in playing if troupe_id == q.troupe_id]
        )
        for character_id in maybe:
            character = mine.get(character_id)  # type: ignore[arg-type]
            if character is not None and quests.role_of(db, q, character) is not None:
                to = f"/characters/{character.id}/quests/{q.id}"
                hits.append(Hit("quests", q.id, q.name, shortened(q.objective), to, q.troupe_id))
                break
        if len(hits) > LIMIT:
            break
    return hits


# --- equipment --------------------------------------------------------------------------------


def find_equipment(reach: Reach, text: str) -> list[Hit]:
    """Items held by the characters whose sheets the person may open, by name and
    description, never the staff note; each opens its holder's Equipment."""
    found = reach.db.execute(
        select(EquipmentItem, Character)
        .join(Character, Character.id == EquipmentItem.character_id)
        .where(
            EquipmentItem.status == "held",
            viewable_characters(reach.user),
            holds(text, EquipmentItem.name, EquipmentItem.description),
        )
        .order_by(
            *reach.first(func.coalesce(Character.home_troupe_id, Character.owner_troupe_id)),
            func.lower(EquipmentItem.name),
            EquipmentItem.id,
        )
        .limit(LIMIT + 1)
    ).all()
    hits = []
    for item, holder in found:
        page = character_page(holder)
        to = page if page.startswith("/troupes/") else f"{page}/equipment"
        troupe = holder.home_troupe_id or holder.owner_troupe_id
        hits.append(Hit("equipment", item.id, item.name, f"Held by {holder.name}", to, troupe))
    return in_order(reach, hits)


# --- news and announcements -------------------------------------------------------------------

POST_STATES = {
    "draft": "Draft",
    "proposed": "Proposed",
    "scheduled": "Scheduled",
    "declined": "Declined",
    "published": "",
}


def find_posts(kind: str) -> Callable[[Reach, str], list[Hit]]:
    def find(reach: Reach, text: str) -> list[Hit]:
        """Published, for the troupe's members; and not yet, for those who write them
        (WRITE_POSTS). By title and words. Never an archived troupe's, which has none to
        open."""
        # The person's troupes are those they are a member of (horatio.permissions.is_member).
        members = true() if reach.custodian else Post.troupe_id.in_(list(reach.troupes))
        writes = reach.where(Post.troupe_id, TroupeAction.WRITE_POSTS)
        shown = or_(and_(Post.status == "published", members), writes)
        found = reach.db.scalars(
            select(Post)
            .join(Troupe, Troupe.id == Post.troupe_id)
            .where(
                Post.kind == kind,
                Troupe.archived_at.is_(None),
                shown,
                holds(text, Post.title, Post.body),
            )
            .order_by(
                *reach.first(Post.troupe_id),
                Post.published_at.desc().nulls_last(),
                Post.id.desc(),
            )
            .limit(LIMIT + 1)
        )
        section = "news" if kind == "news" else "announcements"
        return [
            Hit(
                section,
                p.id,
                p.title,
                POST_STATES.get(p.status, ""),
                f"/troupes/{p.troupe_id}/{section}/{p.id}",
                p.troupe_id,
            )
            for p in found
        ]

    return find


# --- all of them ------------------------------------------------------------------------------

# Each kind, in the order its group shows, with the words its group is headed by.
KINDS: dict[str, tuple[str, Callable[[Reach, str], list[Hit]]]] = {
    "characters": ("Characters", find_characters),
    "players": ("Players", find_players),
    "boons": ("Boons", find_boons),
    "locations": ("Locations", find_locations),
    "quests": ("Quests", find_quests),
    "equipment": ("Equipment", find_equipment),
    "news": ("News", find_posts("news")),
    "announcements": ("Announcements", find_posts("announcement")),
}


@dataclass(frozen=True)
class Group:
    kind: str
    label: str
    hits: list[Hit]
    # More were found than are shown.
    more: bool


def search(db: Session, user: User, text: str, current: uuid.UUID | None = None) -> list[Group]:
    """Every kind's hits for `text`, the groups with none left out."""
    text = " ".join(text.split())[:LONGEST]
    if len(text) < SHORTEST:
        return []
    reach = Reach.of(db, user, current)
    groups: list[Group] = []
    for kind, (label, find) in KINDS.items():
        hits = find(reach, text)
        if hits:
            groups.append(Group(kind, label, hits[:LIMIT], len(hits) > LIMIT))
    return groups


def troupe_names(db: Session, groups: Sequence[Group]) -> dict[uuid.UUID, str]:
    """The names of the troupes the hits are in, asked once."""
    ids = {h.troupe_id for g in groups for h in g.hits if h.troupe_id is not None}
    if not ids:
        return {}
    return dict(db.execute(select(Troupe.id, Troupe.name).where(Troupe.id.in_(ids))).all())

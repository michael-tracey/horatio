"""Reviewing boons (#687): the troupe's review setting, the flags raised on boons, and
the review queue, for its running staff (and the Harpy, #688).

A troupe may hold the boons its players report (#686) for review: they wait, pending,
until staff accept them, edit and accept them, or reject them with a reason their
reporter sees; the reporter is told either way (accepted since #1054). Off, they stand
at once. Either way the report is logged. What staff register themselves stands at once:
they are the reviewers. So does what the Harpy or a Lesser Harpy registers.

**Approval by kind** (#993). While reports wait, the troupe says which kinds go
straight into the ledger all the same (`boon_auto_accept`, none to start with): a
reported boon of a kind ticked there is accepted at once, its log saying "Accepted
automatically" with no one as its actor; any other waits. So does a boon with one of
the troupe's Lesser Harpies on either side (a character with access to the ledger now,
horatio.boon_talons): it never waits, whatever its kind, and its log says no more
than any other accepted automatically, so it doesn't tell who the talons are. Whoever
runs the queue sets the kinds (`sets_approval`): its staff, and a Harpy given the
queue or the full ledger, never a Lesser Harpy. Changing them never touches a boon
already waiting. Who approves (`can_review`): staff, the Harpy given the queue or
more, and a Lesser Harpy the Harpy lets approve reported boons.

Horatio flags a new boon for review, whoever entered it:
- a side named by a name only that matches no character's link: "unmatched", saying
  which character has that name if one does, so it can be linked;
- a likely duplicate: the same parties, kind, night and reason as another boon in the
  ledger that isn't void (boons entered together, as "×3", don't count against each
  other).
Staff flag any boon by hand for a ruling, with a note. A flag stays raised until it
is cleared, with a note, or until what it is about is put right: accepting or
rejecting a boon clears its flags, and linking a name clears that side's.

Linking a name puts a character in its place, on one boon or on every boon in the
ledger that names it, on either side.

The review queue is every pending boon and every boon with a flag still raised.
"""

import uuid
from collections.abc import Collection, Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import audit, boon_harpy, boons, notifications
from horatio.models import (
    Boon,
    BoonEvent,
    BoonFlag,
    BoonTalon,
    Character,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.sheets import conflict, unprocessable

FLAGS = {"unmatched": "Name not linked", "duplicate": "Likely duplicate", "hand": "Flagged"}
# The note on the log line of a reported boon that went straight in (#993).
AUTOMATIC = "Accepted automatically"


def held(troupe: Troupe) -> bool:
    """Whether boons its players report wait for review."""
    return troupe.boon_review


def set_review(db: Session, user: User, troupe: Troupe, hold: bool) -> None:
    """Hold boons players report for review, or let them stand at once. Logged."""
    if troupe.boon_review == hold:
        return
    troupe.boon_review = hold
    audit.record(
        db,
        user,
        "house.boon_review",
        troupe_id=troupe.id,
        setting="wait for review" if hold else "stand at once",
    )


def can_review(db: Session, user: User, troupe: Troupe) -> bool:
    """Who reviews the troupe's boons: its running staff and the custodian, a Harpy
    where the troupe gives them the review queue or more (horatio.boon_harpy, #688),
    and a Lesser Harpy the Harpy lets approve reported boons (#993)."""
    return boon_harpy.keeper(db, user, troupe, "submissions") is not None


def approver(troupe: Troupe) -> str:
    """Who a player is told approves what they report: "harpy" where the troupe gives
    its Harpy the review queue or more, else "staff". Never a Lesser Harpy by name."""
    return "staff" if troupe.boon_harpy == "none" else "harpy"


# --- approval by kind (#993) --------------------------------------------------------------


def auto_accepts(troupe: Troupe) -> list[str]:
    """The kinds a player reports that go straight into the ledger, lightest first."""
    return [k for k in boons.KINDS if k in troupe.boon_auto_accept]


def sets_approval(db: Session, user: User, troupe: Troupe) -> boon_harpy.Keeper | None:
    """Who may say which kinds go straight in, and as whom: whoever runs the queue,
    its running staff, or a Harpy given the queue or the full ledger. Never a Lesser
    Harpy."""
    keeper = boon_harpy.keeper(db, user, troupe, "submissions")
    return keeper if keeper is not None and keeper.role != "talon" else None


def set_auto_accept(
    db: Session,
    user: User,
    troupe: Troupe,
    kinds: Iterable[str],
    as_character: Character | None = None,
) -> None:
    """The kinds a player reports that go straight into the ledger. Logged, with the
    character it was done as, if it changes. Boons already waiting stay waiting."""
    wanted = set(kinds)
    if wanted - set(boons.KINDS):
        raise unprocessable(f"A boon is one of {', '.join(boons.KINDS)}.")
    chosen = [k for k in boons.KINDS if k in wanted]
    if chosen == auto_accepts(troupe):
        return
    troupe.boon_auto_accept = chosen
    names = [boons.KINDS[k].lower() for k in chosen]
    audit.record(
        db,
        user,
        "house.boon_auto_accept",
        troupe_id=troupe.id,
        acting=f" as {as_character.name}" if as_character is not None else "",
        kinds=f"{', '.join(names[:-1])} and {names[-1]} boons"
        if len(names) > 1
        else f"{names[0]} boons"
        if names
        else "none: every one waits",
    )


def talons_on(db: Session, troupe: Troupe) -> set[uuid.UUID]:
    """The troupe's Lesser Harpies now: characters with access to its ledger, while the
    Harpy may give it (horatio.boon_talons)."""
    from horatio import boon_talons  # imports horatio.boon_harpy, as this module does

    if not boon_talons.enabled(troupe):
        return set()
    return set(db.scalars(select(BoonTalon.character_id).where(BoonTalon.troupe_id == troupe.id)))


def waits(troupe: Troupe, boon: Boon, talons: Collection[uuid.UUID]) -> bool:
    """Whether a boon a player just reported waits for approval: while the troupe holds
    reports, unless its kind goes straight in or a Lesser Harpy (`talons`) is on it."""
    if not held(troupe) or boon.kind in troupe.boon_auto_accept:
        return False
    return boon.debtor_id not in talons and boon.creditor_id not in talons


def accept_automatically(db: Session, made: Sequence[Boon]) -> None:
    """Boons a player just reported, accepted at once: each stands, its log saying
    "Accepted automatically", done by no one, and never why. Logged once."""
    if not made:
        return
    for boon in made:
        must_wait(boon, "accepted")
        boon.state = "registered"
        db.flush()
        line = BoonEvent(
            boon_id=boon.id,
            kind="accepted",
            note=AUTOMATIC,
            changes={"state": ["Pending", "Standing"]},
            actor_id=None,
            as_character_id=None,
            # Horatio's doing, which shows as the ledger's state changing does (#992).
            role="staff",
        )
        db.add(line)
    boons.log(db, None, "boon.auto_accepted", made[0], what=boons.a_boon(made[0].kind, len(made)))
    db.flush()


def report(
    db: Session,
    user: User,
    troupe: Troupe,
    debtor: boons.Party,
    creditor: boons.Party,
    terms: boons.Terms,
    count: int,
    note: str,
    character: Character,
) -> list[Boon]:
    """Boons a player reports for their character, as it: standing at once, or, where
    the troupe holds reports, waiting for approval unless they go straight in
    (`waits`). Each boon is judged on its own, so a report of several kinds would be
    split by them."""
    hold = held(troupe)
    made = boons.register(
        db, user, troupe, debtor, creditor, terms, count, note, as_character=character, pending=hold
    )
    if hold:
        talons = talons_on(db, troupe)
        accept_automatically(db, [b for b in made if not waits(troupe, b, talons)])
    return made


# --- flags --------------------------------------------------------------------------------


def raised(db: Session, boon_ids: Iterable[uuid.UUID]) -> list[BoonFlag]:
    """The flags still raised on the boons, oldest first."""
    ids = list(boon_ids)
    if not ids:
        return []
    return list(
        db.scalars(
            select(BoonFlag)
            .where(BoonFlag.boon_id.in_(ids), BoonFlag.cleared_at.is_(None))
            .order_by(BoonFlag.created_at, BoonFlag.id)
        )
    )


def named(db: Session, troupe: Troupe, name: str) -> list[Character]:
    """The troupe's characters whose name is `name`, ignoring case."""
    wanted = name.strip().casefold()
    return [c for c in characters_of(db, troupe) if c.name.casefold() == wanted]


def characters_of(db: Session, troupe: Troupe) -> list[Character]:
    """Every character the troupe's ledger can name (horatio.boons.in_troupe)."""
    members = select(TroupeMembership.character_id).where(TroupeMembership.troupe_id == troupe.id)
    return list(
        db.scalars(
            select(Character).where(
                or_(Character.id.in_(members), Character.owner_troupe_id == troupe.id)
            )
        )
    )


def unmatched_detail(db: Session, troupe: Troupe, name: str) -> str:
    found = named(db, troupe, name)
    if len(found) == 1:
        return f"{found[0].name} is a character in the troupe: link it?"
    if found:
        return f"{len(found)} characters in the troupe are called {name}: link one?"
    return "No character in the troupe has this name."


def alike(a: Boon, b: Boon) -> bool:
    """The same parties, kind, night and reason, as a duplicate would be."""
    return (
        a.debtor_id == b.debtor_id
        and a.creditor_id == b.creditor_id
        and a.debtor_name.casefold() == b.debtor_name.casefold()
        and a.creditor_name.casefold() == b.creditor_name.casefold()
        and a.kind == b.kind
        and a.made_on == b.made_on
        and a.reason.strip().casefold() == b.reason.strip().casefold()
    )


def flag_new(db: Session, troupe: Troupe, made: Sequence[Boon]) -> list[BoonFlag]:
    """Horatio's own flags on boons just entered together: names that link to no
    character, and likely duplicates of boons already in the ledger."""
    if not made:
        return []
    new_ids = {b.id for b in made}
    others = [
        b
        for b in db.scalars(
            select(Boon).where(
                Boon.troupe_id == troupe.id, Boon.state != "void", Boon.id.not_in(new_ids)
            )
        )
    ]
    flags: list[BoonFlag] = []
    details: dict[str, str] = {}
    for boon in made:
        for side in ("debtor", "creditor"):
            name = getattr(boon, f"{side}_name")
            if getattr(boon, f"{side}_id") is None and name:
                if name not in details:
                    details[name] = unmatched_detail(db, troupe, name)
                flags.append(
                    BoonFlag(boon_id=boon.id, kind="unmatched", side=side, detail=details[name])
                )
        twin = next((o for o in others if alike(boon, o)), None)
        if twin is not None:
            debtor, creditor = boons.parties(db, twin)
            flags.append(
                BoonFlag(
                    boon_id=boon.id,
                    kind="duplicate",
                    other_boon_id=twin.id,
                    detail=f"Like {debtor.shown}'s {boons.KINDS[twin.kind].lower()} boon to"
                    f" {creditor.shown} of {boons.when(twin.made_on)}, registered"
                    f" {boons.when(twin.created_at.date())}.",
                )
            )
    db.add_all(flags)
    db.flush()
    return flags


def flag(
    db: Session, user: User, boon: Boon, note: str, as_character: Character | None = None
) -> BoonFlag:
    """Flag the boon by hand, for a ruling, with a note."""
    note = boons.need_note(note, "the flag")
    found = BoonFlag(boon_id=boon.id, kind="hand", note=note, raised_by=user.id)
    db.add(found)
    db.flush()
    boons.event(db, user, boon, "flagged", note, as_character=as_character)
    boons.log(db, user, "boon.flagged", boon, reason=note)
    return found


def clear_flags(
    db: Session,
    user: User,
    found: Iterable[BoonFlag],
    note: str,
    *,
    logged: bool = True,
    as_character: Character | None = None,
) -> int:
    """Clear the flags, with a note. Logged on each boon unless the caller logs it."""
    now = datetime.now(UTC)
    cleared = 0
    by_boon: dict[uuid.UUID, list[BoonFlag]] = {}
    for f in found:
        if f.cleared_at is not None:
            continue
        f.cleared_at = now
        f.cleared_by = user.id
        f.cleared_note = note
        by_boon.setdefault(f.boon_id, []).append(f)
        cleared += 1
    if logged:
        for boon_id, flags in by_boon.items():
            boon = db.get(Boon, boon_id)
            if boon is None:
                continue
            what = ", ".join(FLAGS[f.kind].lower() for f in flags)
            boons.event(
                db,
                user,
                boon,
                "flag_cleared",
                note,
                {"flags": (what, "cleared")},
                as_character,
            )
            boons.log(db, user, "boon.flag_cleared", boon, what=what, reason=note)
    db.flush()
    return cleared


def clear(
    db: Session,
    user: User,
    found: BoonFlag,
    note: str = "",
    as_character: Character | None = None,
) -> None:
    """Clear one flag, with an optional note: the name is right as it is, say."""
    if found.cleared_at is not None:
        raise conflict("That flag is cleared already.")
    clear_flags(db, user, [found], note.strip(), as_character=as_character)


# --- accepting and rejecting --------------------------------------------------------------


def must_wait(boon: Boon, doing: str) -> None:
    if boon.state != "pending":
        raise conflict(f"Only a boon waiting for review can be {doing}.")


def accept(
    db: Session,
    user: User,
    boon: Boon,
    note: str = "",
    as_character: Character | None = None,
    tell: bool = True,
) -> None:
    """The boon stands: it was reviewed and is right, perhaps after an edit. Its flags
    are cleared with it, and whoever reported it is told (`tell_accepted`)."""
    must_wait(boon, "accepted")
    note = note.strip()
    boon.state = "registered"
    db.flush()
    boons.event(db, user, boon, "accepted", note, {"state": ("Pending", "Standing")}, as_character)
    boons.log(db, user, "boon.accepted", boon, reason=note)
    clear_flags(db, user, raised(db, [boon.id]), note or "Accepted.", logged=False)
    if tell:
        tell_accepted(db, user, [boon])


def accept_all(
    db: Session,
    user: User,
    found: Sequence[Boon],
    note: str = "",
    as_character: Character | None = None,
) -> int:
    """Accept every boon given that waits for review, as `accept` does each: "Accept
    all shown" (#993). Any that no longer waits is left as it is. Each reporter is
    told once. Returns how many were accepted."""
    accepted: list[Boon] = []
    for boon in found:
        if boon.state == "pending":
            accept(db, user, boon, note, as_character, tell=False)
            accepted.append(boon)
    tell_accepted(db, user, accepted)
    return len(accepted)


def tell_accepted(db: Session, user: User, accepted: Sequence[Boon]) -> None:
    """Tell whoever reported each boon that it stands now (#1054), once for each
    character they reported as: a line for one boon, a count for several. Not the
    reviewer, for one they reported themselves."""
    told: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID | None], list[Boon]] = {}
    for boon in accepted:
        by, character = reporter(db, boon)
        if by is None or by == user.id:
            continue
        told.setdefault((by, boon.troupe_id, character.id if character else None), []).append(boon)
    for (by, troupe_id, character_id), these in told.items():
        if len(these) == 1:
            boon = these[0]
            debtor, creditor = boons.parties(db, boon)
            summary = (
                f"The {boons.KINDS[boon.kind].lower()} boon you reported ({debtor.shown} owes"
                f" {creditor.shown}, {boons.when(boon.made_on)}) was accepted."
            )
        else:
            summary = f"The {len(these)} boons you reported were accepted."
        notifications.notify(
            db,
            [by],
            "boon.accepted",
            summary,
            f"/play/characters/{character_id}?tab=boons" if character_id else "/",
            troupe_id=troupe_id,
            character_id=character_id,
        )


def reported_as(db: Session, boon_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Character]:
    """The character each boon was reported as, in the Play View, if it was."""
    ids = list(boon_ids)
    if not ids:
        return {}
    found: dict[uuid.UUID, Character] = {}
    rows = db.execute(
        select(BoonEvent.boon_id, Character)
        .join(Character, Character.id == BoonEvent.as_character_id)
        .where(BoonEvent.boon_id.in_(ids), BoonEvent.kind == "submitted")
        .order_by(BoonEvent.created_at, BoonEvent.id)
    ).all()
    for boon_id, character in rows:
        found.setdefault(boon_id, character)
    return found


def reporter(db: Session, boon: Boon) -> tuple[uuid.UUID | None, Character | None]:
    """Who submitted the boon, and the character they reported it as, if any."""
    first = db.scalars(
        select(BoonEvent)
        .where(BoonEvent.boon_id == boon.id, BoonEvent.kind.in_(("submitted", "registered")))
        .order_by(BoonEvent.created_at, BoonEvent.id)
        .limit(1)
    ).first()
    character = (
        db.get(Character, first.as_character_id)
        if first is not None and first.as_character_id is not None
        else None
    )
    return boon.submitted_by, character


def reject(
    db: Session, user: User, boon: Boon, reason: str, as_character: Character | None = None
) -> None:
    """The boon isn't accepted, with a reason its reporter sees. It stays in the ledger
    as void, and its flags are cleared with it."""
    must_wait(boon, "rejected")
    reason = boons.need_note(reason, "rejecting it")
    boons.close(boon, "void", reason)
    db.flush()
    boons.event(
        db, user, boon, "rejected", reason, {"state": ("Pending", "Rejected")}, as_character
    )
    boons.log(db, user, "boon.rejected", boon, reason=reason)
    clear_flags(db, user, raised(db, [boon.id]), "Rejected.", logged=False)
    by, character = reporter(db, boon)
    if by is None or by == user.id:
        return
    debtor, creditor = boons.parties(db, boon)
    link = f"/play/characters/{character.id}?tab=boons" if character is not None else "/"
    notifications.notify(
        db,
        [by],
        "boon.rejected",
        f"The {boons.KINDS[boon.kind].lower()} boon you reported ({debtor.shown} owes"
        f" {creditor.shown}, {boons.when(boon.made_on)}) wasn't accepted: {reason}",
        link,
        troupe_id=boon.troupe_id,
        character_id=character.id if character is not None else None,
    )


# --- linking names ------------------------------------------------------------------------


def link(
    db: Session,
    user: User,
    troupe: Troupe,
    boon: Boon,
    side: str,
    to: Character,
    everywhere: bool,
    note: str = "",
    as_character: Character | None = None,
) -> tuple[int, int]:
    """Put `to` in place of the name on the boon's `side`: on that boon, or, with
    `everywhere`, on every boon in the ledger that names it, on either side. Each
    linked boon's log says so, and its flags about that name are cleared. Returns how
    many boons were linked, and how many were skipped because `to` is already on
    their other side."""
    if side not in ("debtor", "creditor"):
        raise unprocessable("Link the debtor's name or the creditor's.")
    name = getattr(boon, f"{side}_name")
    if getattr(boon, f"{side}_id") is not None or not name:
        raise unprocessable(f"The {side} is a character already, not a name.")
    if not boons.in_troupe(db, troupe, to):
        raise unprocessable(f"{to.name} isn't a character in this troupe.")
    wanted = name.casefold()
    if everywhere:
        found = list(
            db.scalars(
                select(Boon)
                .where(
                    Boon.troupe_id == troupe.id,
                    or_(Boon.debtor_id.is_(None), Boon.creditor_id.is_(None)),
                )
                .order_by(Boon.created_at, Boon.id)
            )
        )
        targets = [
            (b, s)
            for b in found
            for s in ("debtor", "creditor")
            if getattr(b, f"{s}_id") is None and getattr(b, f"{s}_name").casefold() == wanted
        ]
    else:
        targets = [(boon, side)]
    note = note.strip()
    role = boons.acting_as(db, troupe.id, as_character)
    linked: set[uuid.UUID] = set()
    skipped: set[uuid.UUID] = set()
    for b, s in targets:
        other = "creditor" if s == "debtor" else "debtor"
        if getattr(b, f"{other}_id") == to.id:
            skipped.add(b.id)
            continue
        was = getattr(b, f"{s}_name")
        boons.place(b, s, boons.Party(to, ""))
        db.flush()
        boons.event(db, user, b, "linked", note, {s: (was, to.name)}, as_character, role)
        linked.add(b.id)
        clear_flags(
            db,
            user,
            [f for f in raised(db, [b.id]) if f.kind == "unmatched" and f.side == s],
            note or f"Linked to {to.name}.",
            logged=False,
        )
    if not linked:
        raise unprocessable(f"{to.name} is on the other side of every boon naming {name}.")
    audit.record(
        db,
        user,
        "boon.linked",
        troupe_id=troupe.id,
        name=name,
        linked_to=to.name,
        what=f"{len(linked)} boon" if len(linked) == 1 else f"{len(linked)} boons",
        reason=note,
    )
    return len(linked), len(skipped)


# --- the queue ----------------------------------------------------------------------------


def queue(db: Session, troupe: Troupe) -> list[Boon]:
    """Every boon waiting for review or with a flag raised, oldest first."""
    flagged = select(BoonFlag.boon_id).where(BoonFlag.cleared_at.is_(None))
    return list(
        db.scalars(
            select(Boon)
            .where(
                Boon.troupe_id == troupe.id,
                or_(Boon.state == "pending", Boon.id.in_(flagged)),
            )
            .order_by(Boon.created_at, Boon.id)
        )
    )

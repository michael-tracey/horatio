"""XP debt: XP a character owes, from a ghoul's Embrace (MET: VTM pp. 297–299,
horatio.embrace) or put on it by its home troupe's staff.

Debt is the XP history gone below nothing: every line summed, a negative balance.
So the refunds and saved XP a character has pay its debt first, and all the XP it
earns after goes to the debt until it is paid off (p. 298). An award is written as
it always is, and the history says how much of it went to the debt. While any is
owed, nothing that costs XP can be bought (horatio.sheets.set_trait), but for the
discipline dots the Embrace took, where the Storyteller lets them be bought back
into debt, and what staff give free.

Staff add debt, or forgive some or all of it, with a reason: each its own line in
the XP history, of the kind "debt". Unspent XP pays added debt first, as it pays
the Embrace's.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, User, XpEntry
from horatio.sheets import conflict, unprocessable, xp_balance


def owed(balance: int) -> int:
    """The debt a balance comes to: what it is below nothing."""
    return max(0, -balance)


def debt(db: Session, character: Character) -> int:
    return owed(xp_balance(db, character))


def short_of(balance: int, cost: int, *, repriced: bool = False) -> str:
    """Why a purchase of `cost` XP cannot be made with `balance`."""
    if balance < 0:
        return (
            f"The character owes {owed(balance)} XP of debt. The XP it earns pays that off"
            " first, and nothing new can be bought until it has."
        )
    return (
        f"That costs {cost} XP"
        + (", with earlier buys repriced" if repriced else "")
        + f", and the character has {balance}."
    )


@dataclass(frozen=True)
class Paid:
    """For one line of the XP history: how much of what it gave went to the debt,
    and the debt left after it."""

    to_debt: int
    debt: int


def running(amounts: Iterable[int]) -> list[Paid]:
    """The debt line by line, for the XP history in order."""
    balance = 0
    found: list[Paid] = []
    for amount in amounts:
        before = balance
        balance += amount
        paid = min(amount, owed(before)) if amount > 0 else 0
        found.append(Paid(to_debt=paid, debt=owed(balance)))
    return found


def adjust(db: Session, staff: User, character: Character, amount: int, reason: str) -> XpEntry:
    """Add `amount` XP of debt, or with a negative `amount` forgive that much. Only
    what is owed can be forgiven: more would be an award."""
    reason = reason.strip()
    if not reason:
        raise unprocessable("Say why.")
    if amount == 0:
        raise unprocessable("Add or forgive at least 1 XP.")
    owing = debt(db, character)
    if amount < 0 and -amount > owing:
        raise conflict(
            f"{character.name} owes {owing} XP, so at most {owing} can be forgiven;"
            " to give XP, award it."
        )
    entry = XpEntry(
        character_id=character.id,
        kind="debt",
        amount=-amount,
        reason=reason,
        entered_by=staff.id,
    )
    db.add(entry)
    db.flush()
    audit.record(
        db,
        staff,
        "xp.debt_added" if amount > 0 else "xp.debt_forgiven",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
        amount=abs(amount),
        reason=reason,
        debt=debt(db, character),
    )
    return entry

"""What a blood bond does to its thrall at a game (#664; MET: VTM p. 295), for the
thrall's Play View and the Scene view.

One drink has no rules effect: the thrall only feels it, so it is a quiet line to
roleplay. Two drinks: defensive Social test pools against the regnant's powers are
1 lower, and directly harming the regnant costs 1 Willpower an hour. A full bond,
three drinks: defensive Social and Mental test pools against the regnant's powers
are 3 lower; doing what the thrall believes the regnant would disapprove of costs 1
Willpower, and directly harming them 3 Willpower an hour.

The penalties are lines under the defence pools, "Against Duke Ravel's powers", as
Killer Instincts' line against its hunted target is (#613): the pool's own total
leaves them out, since they count only against the regnant. Only the thrall's side
shows: a regnant's Play View says nothing of the bonds to them.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from horatio.reference import PoolPart, PoolVariant, TestPool

PAGE = "p. 295"
LABEL = "Blood bond"

# The defence pools a bond lowers at each level, and by how much.
PENALTIES: dict[int, tuple[tuple[str, int], ...]] = {
    2: (("defense:Social", -1),),
    3: (("defense:Social", -3), ("defense:Mental", -3)),
}
DRINKS = {1: "One drink", 2: "Two drinks", 3: "Full bond"}


@dataclass(frozen=True)
class Felt:
    """A bond the character feels as thrall: to whom, and at what level."""

    regnant: str
    level: int


class BondLine(BaseModel):
    """A bond the character feels, for the Play View's Sheet tab."""

    regnant: str
    # 1 to 3: drinks on separate nights, three a full bond.
    level: int
    # "Two drinks", "Full bond".
    drinks: str
    # What it means at a game, in words.
    effects: list[str]


def effects_of(felt: Felt) -> list[str]:
    who = felt.regnant
    if felt.level >= 3:
        return [
            f"Resisting {who}'s powers: −3 to Social and Mental defence.",
            f"Doing what you believe {who} would disapprove of costs 1 Willpower.",
            f"Directly harming {who} costs 3 Willpower an hour ({PAGE}).",
        ]
    if felt.level == 2:
        return [
            f"Resisting {who}'s powers: −1 to Social defence.",
            f"Directly harming {who} costs 1 Willpower an hour ({PAGE}).",
        ]
    return [f"No rules effect yet: feelings for {who} to roleplay ({PAGE})."]


def lines(felt: Sequence[Felt]) -> list[BondLine]:
    """The bonds felt, strongest first."""
    return [
        BondLine(
            regnant=f.regnant, level=f.level, drinks=DRINKS[min(f.level, 3)], effects=effects_of(f)
        )
        for f in sorted(felt, key=lambda f: -f.level)
        if f.level >= 1
    ]


def with_penalties(pools: Sequence[TestPool], felt: Sequence[Felt]) -> list[TestPool]:
    """The pools with a line under each defence a bond lowers: "Against Duke Ravel's
    powers (−3 Blood bond)"."""
    out: list[TestPool] = []
    for pool in pools:
        added = [
            PoolVariant(
                when=f"Against {f.regnant}'s powers",
                total=pool.total + amount,
                parts=[PoolPart(label=LABEL, value=amount)],
            )
            for f in felt
            for key, amount in PENALTIES.get(min(f.level, 3), ())
            if key == pool.key
        ]
        out.append(
            pool.model_copy(update={"variants": [*pool.variants, *added]}) if added else pool
        )
    return out

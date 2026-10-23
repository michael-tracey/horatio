"""Working out what a character must do to feed between games, from its sheet
and the rules (horatio.feeding has the rest).

A character spends one downtime action feeding, or comes to the next game at
half Blood, rounded up (MET: VtM core, Downtime chapter, "Feeding").
Storytellers set how many actions each clan needs each cycle; traits change it
(the rule set's feeding modifiers); and each dot of Herd stands in for one
feeding action (p. 102).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from horatio.rules.model import SheetTrait, TroupeRules

# Feeding actions a clan needs when storytellers have not said otherwise.
DEFAULT_DIFFICULTY = 1
HERD = ("backgrounds", "Herd")


def clan_family(name: str) -> str:
    """The clan a clan or bloodline belongs to: "Gangrel: Coyote" is a Gangrel."""
    return name.split(":")[0].strip()


def basis(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> dict[str, Any]:
    """What the sheet says about feeding, kept on the participant when it joins a
    cycle: its clan (None for a character with none, which does not feed), the
    traits that change feeding, and its Herd rating."""
    clan = next((t.name for t in sheet if t.category == "clan"), None)
    held = {(t.category, t.name) for t in sheet if t.rating is None or t.rating > 0}
    modifiers = [
        {
            "source": m.trait,
            "amount": m.amount,
            "herd_factor": m.herd_factor,
            "always_half": m.always_half,
            "page": m.page,
        }
        for m in rules.rule_set.feeding_modifiers
        if (m.category, m.trait) in held
    ]
    herd = max(
        (t.rating or 0 for t in sheet if (t.category, t.name) == HERD),
        default=0,
    )
    return {
        "clan": clan_family(clan) if clan else None,
        "modifiers": modifiers,
        "herd": herd,
    }


@dataclass(frozen=True)
class NeedLine:
    """One reason in "Gangrel 1 · Disease Carrier +1"."""

    source: str
    amount: int
    kind: str  # clan | trait | adjustment
    # Why: a storyteller's reason, or what a trait does besides changing the number.
    note: str = ""
    page: str | None = None

    @property
    def text(self) -> str:
        if self.kind == "clan":
            words = f"{self.source} {self.amount}"
        elif self.amount:
            words = f"{self.source} {self.amount:+d}".replace("-", "−")
        else:
            words = self.source
        return f"{words} ({self.note})" if self.note else words


@dataclass(frozen=True)
class Need:
    needed: int
    lines: tuple[NeedLine, ...]
    # What each dot of Herd counts for: 0 when the character cannot use Herd.
    herd_factor: int
    # No feeding brings the character to full Blood.
    always_half: bool


def herd_note(factor: int) -> str:
    return "no Herd" if factor == 0 else f"Herd counts {factor}×" if factor != 1 else ""


def need(
    clan_amount: int,
    clan_reason: str,
    feeding_basis: Mapping[str, Any],
    adjustments: Sequence[tuple[int, str]] = (),
) -> Need:
    """How many feeding actions the character needs, and why."""
    lines = [NeedLine(feeding_basis["clan"], clan_amount, "clan", clan_reason)]
    factor = 1
    always_half = False
    for m in feeding_basis["modifiers"]:
        notes = [herd_note(m["herd_factor"])]
        if m["always_half"]:
            notes.append("always half Blood")
        lines.append(
            NeedLine(
                m["source"],
                m["amount"],
                "trait",
                ", ".join(n for n in notes if n),
                m.get("page"),
            )
        )
        factor *= m["herd_factor"]
        always_half = always_half or m["always_half"]
    for delta, reason in adjustments:
        lines.append(NeedLine("Storyteller", delta, "adjustment", reason))
    needed = max(0, sum(line.amount for line in lines))
    return Need(needed, tuple(lines), factor, always_half)


@dataclass(frozen=True)
class Tally:
    """The advisory count: what the character puts towards feeding."""

    needed: int
    parts: tuple[tuple[str, int], ...]
    always_half: bool
    total: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "total", sum(n for _, n in self.parts))

    @property
    def enough(self) -> bool:
        return not self.always_half and self.total >= self.needed


def tally(
    feeding_need: Need,
    actions: int,
    herd_own: int,
    received: Sequence[tuple[str, int]],
) -> Tally:
    """Feeding actions, the character's own Herd, and Herd given by others, each
    dot counted as the character's traits say."""
    factor = feeding_need.herd_factor
    parts: list[tuple[str, int]] = [("Feeding actions", actions)]
    if herd_own:
        parts.append(("your Herd", herd_own * factor))
    parts += [(f"Herd from {name}", amount * factor) for name, amount in received]
    return Tally(feeding_need.needed, tuple(parts), feeding_need.always_half)


def working(feeding_need: Need, counted: Tally) -> str:
    """The calculation, as the player is shown it under the answer: "needed 2
    (Gangrel 1, Disease Carrier +1). Feeding actions 1; your Herd 1; Herd from
    Bram 2. Total 4." """
    reasons = ", ".join(line.text for line in feeding_need.lines)
    parts = "; ".join(f"{label} {n}" for label, n in counted.parts)
    text = f"needed {feeding_need.needed} ({reasons}). {parts}. Total {counted.total}."
    if counted.always_half:
        text += " No feeding brings this character to full Blood."
    return text

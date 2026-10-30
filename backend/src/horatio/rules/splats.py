"""What each splat's cost-rule conditions can test, and how those facts are worked out."""

from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass, field, fields
from typing import Any

from horatio.rules.model import SheetTrait, TroupeRules

Facts = Mapping[str, Any]
FactsFn = Callable[[TroupeRules, Sequence[SheetTrait], SheetTrait], Facts]


@dataclass(frozen=True)
class Panels:
    """Which parts of the Vampire sheet and Play View a character has, from its
    splat and, for an NPC, its kind (horatio.rules.npc_kinds). A vampire has them
    all; a ghoul, a mortal or a werewolf has no Beast, Humanity or Generation."""

    # Beast traits, and the frenzy reminders that go with them.
    beast: bool = True
    frenzy: bool = True
    # A Humanity or Path of Enlightenment track.
    morality: bool = True
    # The Generation background.
    generation: bool = True
    # Feeding, which is for those who spend Blood (and not a werewolf's Rage).
    feed: bool = True


NO_VAMPIRE_PANELS = Panels(beast=False, frenzy=False, morality=False, generation=False, feed=False)


def both(first: Panels, second: Panels) -> Panels:
    """The panels two sources both allow: an NPC's kind's and its splat's."""
    return Panels(
        **{f.name: getattr(first, f.name) and getattr(second, f.name) for f in fields(Panels)}
    )


@dataclass(frozen=True)
class Vitae:
    """Blood that is part vampiric vitae (a ghoul's, MET: VtM core p. 297): `pool` in
    all, of which at most `most` is vitae, spent `per_turn` a turn on healing,
    boosting attributes or disciplines. The rest is human Blood, which cannot be
    spent. Vitae refills only by drinking it, up to `most` at any time; spent vitae
    comes back as human Blood, 1 a day. Without a drink for `days`, the character
    ages 10 years a day."""

    pool: int = 10
    most: int = 5
    per_turn: int = 1
    days: int = 30


@dataclass(frozen=True)
class Splat:
    fact_names: frozenset[str]
    facts: FactsFn
    # The character's in-clan (native) powers, for checks.
    in_clan: Callable[[TroupeRules, Sequence[SheetTrait]], list[str]] = lambda _r, _s: []
    # How each fact reads in plain words (horatio.rules.conditions.describe).
    fact_words: Mapping[str, Any] = field(default_factory=dict)
    # The splat's name in the app: "Vampire".
    label: str = ""
    # A character of this splat is bound to a vampire, its domitor (horatio.domitors),
    # whose clan and in-clan disciplines it takes.
    has_domitor: bool = False
    # The splat whose clans these are, where it has none of its own: a ghoul's clan
    # is its domitor's, with the vampire's clan logos.
    clans_from: str | None = None
    # What sets a vampire apart, so another splat can leave out what it lacks. Its
    # panels: the Beast and frenzy (MET: VtM core pp. 290, 301-303), Morality, the
    # Generation background, which sets Blood, social age and the attribute bonus
    # and which some merits ask for (pp. 100-102), and feeding on mortals (Feed,
    # Herd and feeding in downtimes).
    panels: Panels = Panels()
    # Diablerie (p. 306).
    diablerie: bool = True
    # A clan weakness with rules effects (a Malkavian's Derangement trait, p. 57).
    # A ghoul plays its domitor's for roleplay only (p. 297).
    weakness: bool = True
    # Blood that is part vitae and part human; None for Blood that is all vitae.
    vitae: Vitae | None = None


# --- Vampire ---------------------------------------------------------------


def vampire_generation(sheet: Sequence[SheetTrait]) -> int:
    """The Generation background's rating, or 1 without one. A rating of 0 also
    counts as 1, as it did in Yorick."""
    for trait in sheet:
        if trait.category == "backgrounds" and trait.name == "Generation":
            return trait.rating or 1
    return 1


@dataclass(frozen=True)
class ClanChoice:
    """An in-clan discipline the clan leaves to its player, from its `choices` (Angelis
    Ater: Potence, Presence or Obfuscate, MET: VTM p. 72), kept as the clan's detail."""

    clan: str
    choices: tuple[str, ...]
    # The one chosen; None until one of `choices` is.
    chosen: str | None
    page: str | None = None


def clan_choice(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> ClanChoice | None:
    """The clan's in-clan choice, or None for a clan with none, or while a merit sets
    the in-clan disciplines in place of the clan's (Shadows of the Past)."""
    from horatio.rules.grants import in_clan_replaced

    clan = next((t for t in sheet if t.category == "clan"), None)
    if clan is None:
        return None
    choices = rules.rule_set.trait_properties("clan", clan.name).get("choices")
    if not choices or in_clan_replaced(rules.rule_set, sheet) is not None:
        return None
    found = rules.rule_set.traits.get(("clan", clan.name))
    return ClanChoice(
        clan.name,
        tuple(choices),
        clan.detail if clan.detail in choices else None,
        found.page_reference if found is not None else None,
    )


def clan_in_clan_disciplines(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> list[str]:
    """The clan's own in-clan disciplines, with the one its player chose if it leaves
    one to them, or the ones a merit sets in their place."""
    from horatio.rules.grants import in_clan_replaced

    replaced = in_clan_replaced(rules.rule_set, sheet)
    disciplines: list[str] = []
    for trait in sheet:
        if trait.category == "clan" and replaced is None:
            disciplines.extend(
                rules.rule_set.trait_properties("clan", trait.name).get("in_clan", [])
            )
    choice = clan_choice(rules, sheet) if replaced is None else None
    if choice is not None and choice.chosen is not None:
        disciplines.append(choice.chosen)
    disciplines.extend(replaced or [])
    return disciplines


def vampire_in_clan_disciplines(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> list[str]:
    """The clan's in-clan disciplines (or the ones a merit sets in their place)
    plus any extra in-clan disciplines on the sheet."""
    disciplines = clan_in_clan_disciplines(rules, sheet)
    disciplines.extend(t.name for t in sheet if t.category == "extra_in_clan_disciplines")
    return disciplines


# Powers named after their discipline ("Celerity: Projectile"), in-clan when it is.
VAMPIRE_ELDER_POWERS = frozenset({"elder_disciplines", "luminary_disciplines"})


@dataclass(frozen=True)
class VampireSheet:
    """What a vampire's sheet says for every trait priced on it."""

    generation: int
    # The clan or bloodline exactly ("Brujah: True Brujah").
    clan: str
    in_clan: frozenset[str]
    # What its grants price as in-clan (Thaumaturgic Expertise's extra path).
    priced_in_clan: Set[tuple[str, str, str | None]]
    # What they price as out-of-clan (Inept's discipline), and the extra in-clan
    # disciplines that start without a free dot, with what each is because of.
    priced_out_of_clan: Mapping[tuple[str, str, str | None], tuple[tuple[str, str], ...]]
    without_free_dot: Mapping[str, tuple[tuple[str, str], ...]]


def vampire_sheet(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> VampireSheet:
    """Worked out once for each sheet, as pricing asks it of every trait it prices."""
    from horatio.rules.grants import priced

    def work_out() -> VampireSheet:
        found = priced(rules.rule_set, sheet)
        # An extra in-clan discipline starts without a free dot when a grant says so,
        # unless the clan has it in-clan itself.
        own = set(clan_in_clan_disciplines(rules, sheet))
        extras = {t.name for t in sheet if t.category == "extra_in_clan_disciplines"}
        without = {
            name: sources
            for (category, name, _), sources in found.no_free_dot.items()
            if category == "extra_in_clan_disciplines" and name in extras and name not in own
        }
        return VampireSheet(
            generation=vampire_generation(sheet),
            clan=next((t.name for t in sheet if t.category == "clan"), ""),
            in_clan=frozenset(vampire_in_clan_disciplines(rules, sheet)),
            priced_in_clan=found.in_clan,
            priced_out_of_clan=found.out_of_clan,
            without_free_dot=without,
        )

    return rules.rule_set.remembered(("vampire", tuple(sheet)), work_out)


def in_clan_names(trait: SheetTrait) -> set[str]:
    """An in-clan entry matches the trait's name, or its name with its detail: so
    "Celerity" matches any Celerity, but "Thaumaturgy: Path of Blood" only that path.
    An elder or luminary power matches its discipline."""
    names = {trait.name, trait.full_name}
    if trait.category in VAMPIRE_ELDER_POWERS:
        names.add(trait.name.split(":")[0].strip())
    return names


def vampire_facts(rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait) -> Facts:
    from horatio.rules.grants import matching

    found = vampire_sheet(rules, sheet)
    inept = matching(found.priced_out_of_clan, trait)
    # What stops a free starting dot, and what it is because of (Inept, or the merit
    # that gave an extra in-clan discipline).
    no_dot: tuple[tuple[str, str], ...] = (
        found.priced_out_of_clan[inept]
        if inept is not None
        else next(
            (
                found.without_free_dot[n]
                for n in in_clan_names(trait)
                if n in found.without_free_dot
            ),
            (),
        )
    )
    return {
        "generation": found.generation,
        "in_clan": inept is None
        and (
            not in_clan_names(trait).isdisjoint(found.in_clan)
            or matching(found.priced_in_clan, trait) is not None
        ),
        "no_free_dot": bool(no_dot),
        "no_free_dot_because": no_dot,
        # The clan or bloodline exactly ("Brujah: True Brujah"), and its clan ("Brujah").
        "clan": found.clan,
        "clan_family": found.clan.split(":")[0].strip(),
    }


# --- Ghoul ------------------------------------------------------------------
# A ghoul has no clan of its own: its sheet holds its domitor's clan and bloodline
# (MET: VTM p. 296), so its in-clan disciplines are its domitor's clan's. A Caitiff
# domitor has none from its clan, but three it chose (p. 246): the ghoul's sheet
# holds those too, set from the domitor (horatio.domitors).

DOMITOR_IN_CLAN = "domitor_in_clan_disciplines"


def ghoul_in_clan_disciplines(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> list[str]:
    """The domitor's clan's in-clan disciplines, and a Caitiff domitor's three."""
    return clan_in_clan_disciplines(rules, sheet) + [
        t.name for t in sheet if t.category == DOMITOR_IN_CLAN and (t.rating or 0) > 0
    ]


def ghoul_facts(rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait) -> Facts:
    def work_out() -> tuple[frozenset[str], str]:
        clan = next((t.name for t in sheet if t.category == "clan"), "")
        return frozenset(ghoul_in_clan_disciplines(rules, sheet)), clan

    in_clan, clan = rules.rule_set.remembered(("ghoul", tuple(sheet)), work_out)
    return {
        "in_clan": not in_clan_names(trait).isdisjoint(in_clan),
        "clan": clan,
        "clan_family": clan.split(":")[0].strip(),
    }


SPLATS: dict[str, Splat] = {
    "vampire": Splat(
        fact_names=frozenset({"generation", "in_clan", "clan", "clan_family"}),
        facts=vampire_facts,
        in_clan=vampire_in_clan_disciplines,
        fact_words={
            "generation": "Generation {}",
            "in_clan": ("in-clan", "out-of-clan"),
            "clan": "{}",
            "clan_family": "{} clan",
        },
        label="Vampire",
    ),
    "ghoul": Splat(
        fact_names=frozenset({"in_clan", "clan", "clan_family"}),
        facts=ghoul_facts,
        in_clan=ghoul_in_clan_disciplines,
        fact_words={
            "in_clan": ("in-clan", "out-of-clan"),
            "clan": "{}",
            "clan_family": "{} clan",
        },
        label="Ghoul",
        has_domitor=True,
        clans_from="vampire",
        # A ghoul is mortal (MET: VtM core p. 297): no Generation, no Beast, no
        # diablerie, and it drinks vitae rather than feeding.
        panels=NO_VAMPIRE_PANELS,
        diablerie=False,
        weakness=False,
        vitae=Vitae(),
    ),
}


def splat_order(splat: str) -> int:
    """Where a splat comes in a list of them: as here, vampires first."""
    return list(SPLATS).index(splat) if splat in SPLATS else len(SPLATS)

"""Blood Resonance, an optional feeding rule (MET: VTM Vol. 2, pp. 294-297), as a
troupe plays it when it switches the rule on (Troupe.feeding_resonance).

Blood carries one of four humors, its Resonance, which colours how the vampire who
drinks it feels (p. 295). A vessel in a strong emotional state has a Dyscrasia too:
a one-time benefit the vampire can use before the night ends, and only one at a time
(pp. 296-297). Horatio runs feeding through downtimes, so a player names the humor
their character hunts for on the downtime form, and the storytellers answer with the
Resonance it fed on and any Dyscrasia, which comes to the next game.

The Dyscrasias are the book's, each summed up in a line of our own; the book has the
full text.
"""

from dataclasses import dataclass

PAGES = "Vol. 2, pp. 294-297"
DYSCRASIA_PAGES = "Vol. 2, pp. 296-297"


@dataclass(frozen=True)
class Dyscrasia:
    name: str
    # What it does, in a line.
    summary: str


@dataclass(frozen=True)
class Humor:
    key: str
    name: str
    # The feelings blood of this humor brings (p. 295).
    feelings: str
    dyscrasias: tuple[Dyscrasia, ...]


HUMORS: dict[str, Humor] = {
    h.key: h
    for h in (
        Humor(
            "choleric",
            "Choleric",
            "anger, violence, passion, envy or aggression",
            (
                Dyscrasia(
                    "Bully",
                    "+1 wild card to your attack in one Physical or Social challenge"
                    " against someone of equal or lower standing.",
                ),
                Dyscrasia(
                    "Cycle of Violence",
                    "+1 wild card to your attack in one Physical challenge to bite or grapple.",
                ),
                Dyscrasia(
                    "Envy",
                    "+1 wild card to your attack in one Physical or Social challenge"
                    " against someone of equal or higher standing.",
                ),
                Dyscrasia(
                    "Principled",
                    "A retest without spending Willpower in a challenge against an"
                    " ideological enemy.",
                ),
                Dyscrasia(
                    "Vengeful",
                    "+1 wild card in one challenge against someone who beat you in a"
                    " challenge earlier that night.",
                ),
                Dyscrasia(
                    "Vicious",
                    "A retest without spending Willpower in a challenge using Intimidation.",
                ),
                Dyscrasia(
                    "Driving",
                    "Use one Celerity, Potence or Temporis power without spending its Blood.",
                ),
            ),
        ),
        Humor(
            "melancholic",
            "Melancholic",
            "sadness, fear, awareness or melancholy",
            (
                Dyscrasia(
                    "In Mourning",
                    "+1 wild card to your defence in one challenge involving Presence,"
                    " Serpentis or Thaumaturgy: Path of Corruption.",
                ),
                Dyscrasia(
                    "Lost Love",
                    "+1 wild card to your attack in one challenge involving Presence.",
                ),
                Dyscrasia(
                    "Lost Relative",
                    "Clear your Derangement points; a Malkavian keeps its last one.",
                ),
                Dyscrasia(
                    "Massive Failure",
                    "A retest without spending Willpower against someone who beat you in a"
                    " challenge earlier that night.",
                ),
                Dyscrasia(
                    "Nostalgic",
                    "A retest without spending Willpower in a challenge using Empathy.",
                ),
                Dyscrasia(
                    "Recalling",
                    "As the defender, a retest without spending Willpower against a power"
                    " you have seen the attacker use that night.",
                ),
                Dyscrasia(
                    "Reflection",
                    "Use one Auspex or Necromancy power without spending its Blood.",
                ),
            ),
        ),
        Humor(
            "phlegmatic",
            "Phlegmatic",
            "apathy, calm, lethargy or indifference",
            (
                Dyscrasia("Chill", "+3 wild card to one test to resist frenzy."),
                Dyscrasia(
                    "Comfortably Numb",
                    "Turn an exceptional success against you in a Physical or Social"
                    " challenge into an ordinary one.",
                ),
                Dyscrasia("Eating Your Emotions", "Remove 2 Beast traits."),
                Dyscrasia(
                    "Given Up",
                    "+3 wild card to your defence if you relented to the challenge before,"
                    " in the last 5 minutes and with no ally involved.",
                ),
                Dyscrasia(
                    "Lone Wolf", "+1 wild card in one challenge while no one is helping you."
                ),
                Dyscrasia(
                    "Procrastinate",
                    "+1 in one challenge after lowering your initiative by 5 or more this"
                    " round; not with a surprise action.",
                ),
            ),
        ),
        Humor(
            "sanguine",
            "Sanguine",
            "enthusiasm, vitality, excitement or joy",
            (
                Dyscrasia(
                    "Contagious Enthusiasm",
                    "+1 wild card in one challenge against someone you are touching.",
                ),
                Dyscrasia(
                    "Smell Game",
                    "+1 wild card to your attack in one challenge that uses your sense of smell.",
                ),
                Dyscrasia(
                    "High on Life",
                    "Seem alive for an hour without spending Blood, with +2 against tests"
                    " to tell you are a vampire; it ends if you feed.",
                ),
                Dyscrasia(
                    "Manic High",
                    "+1 wild card if you won your last challenge, within the last minute.",
                ),
                Dyscrasia(
                    "True Love",
                    "+2 to your defence in one challenge while you assist a defender.",
                ),
                Dyscrasia(
                    "Stirring",
                    "Use one Presence or Thaumaturgy power without spending its Blood.",
                ),
            ),
        ),
    )
}


def dyscrasia(humor: str, name: str) -> Dyscrasia | None:
    found = HUMORS.get(humor)
    return next((d for d in found.dyscrasias if d.name == name), None) if found else None


def answer_text(humor: str | None, name: str) -> str:
    """The Resonance part of a feeding answer, as the player reads it: "Fed on
    **sanguine** blood (enthusiasm, ...). Dyscrasia: **Manic High**: ..."; "" for
    none."""
    found = HUMORS.get(humor or "")
    if found is None:
        return ""
    text = f"Fed on **{found.name.lower()}** blood ({found.feelings})."
    carried = dyscrasia(found.key, name)
    if carried is None:
        return f"{text} No Dyscrasia."
    return (
        f"{text} Dyscrasia: **{carried.name}**: {carried.summary} Use it once, before the"
        f" end of the next game ({DYSCRASIA_PAGES})."
    )

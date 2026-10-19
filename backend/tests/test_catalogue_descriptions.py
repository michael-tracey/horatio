"""Every trait a player chooses from a list says what it is (issues #31, #42)."""

from horatio.rules.files import DATA_DIR, load_rule_set

DESCRIBED = (
    "attributes",
    "focus_physicals",
    "focus_socials",
    "focus_mentals",
    "skills",
    "backgrounds",
    "disciplines",
    "merits",
    "flaws",
)


def test_every_trait_players_choose_has_a_description() -> None:
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")

    missing = sorted(
        f"{category}: {name}"
        for (category, name), trait in rules.traits.items()
        if category in DESCRIBED and not trait.description
    )
    assert missing == []

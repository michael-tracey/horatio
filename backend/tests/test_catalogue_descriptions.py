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


# Not in the core book's list (p. 87), which invites players to make their own:
# they came with the Yorick catalogue, so they have no page to give.
NOT_IN_THE_BOOK = {("archetype", "Hedonist"), ("archetype", "Hunter")}


def test_every_skill_and_archetype_says_what_it_does_and_where() -> None:
    """Skills give their System and archetypes their line from the book, each
    with a real page, for the Play View's Sheet tab (issue #212)."""
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    found = {key: trait for key, trait in rules.traits.items() if key[0] in ("skills", "archetype")}

    missing = sorted(
        f"{category}: {name}"
        for (category, name), trait in found.items()
        if not trait.description
        or (
            (category, name) not in NOT_IN_THE_BOOK
            and not (trait.page_reference or "")[:1].isdigit()
        )
    )
    assert missing == []

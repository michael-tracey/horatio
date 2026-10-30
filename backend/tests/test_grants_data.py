"""Every merit or flaw that says it gives another trait gives it through a grant, or
is listed as rules only for staff to apply by hand (issue #140)."""

import re
import tomllib

from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.grants import options
from horatio.rules.model import SheetTrait

# How the catalogue's descriptions say a trait gives, or counts as, another.
GIVES = re.compile(
    r"benefits of"
    r"|\bfree\b(?! of| retest| defensive retest)"
    r"|\bgain (?:the |a |an |two |second |\d+ )?(?:\w+ ){0,3}(?:attribute )?focus\b"
    r"|\bgain \d+ dots\b|\bgain (?-i:[A-Z][\w']*(?: [A-Z][\w']*)*) \d\b"
    r"|\bgain (?:the )?(?-i:[A-Z])[\w' ]* merit\b|\bat (?:no|zero) cost\b"
    r"|\bin-clan discipline\b"
    r"|\binnate status\b|\bstatus traits? (?-i:[A-Z])"
    r"|\bcounts? as having\b|\bas if (?:you )?(?:had|has) (?:the )?(?-i:[A-Z])"
    r"|\bwithout (?:buying|purchasing)\b"
    r"|\badditional (?:health )?level\b|\bhealth levels\b"
    r"|\bthe most (?:\w+ )*rises\b|\bcan go \d higher\b",
    re.I,
)
GRANTS_FILE = DATA_DIR / "bns_met_vampire_grants.toml"


def rules_only() -> list[dict[str, str]]:
    with open(GRANTS_FILE, "rb") as f:
        return tomllib.load(f)["rules_only"]


def test_traits_that_give_others_have_grants_or_are_rules_only() -> None:
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    granting = {(g.source["category"], g.source["name"]) for g in rules.grants}
    listed = {(t["category"], t["name"]) for t in rules_only()}

    unlisted = sorted(
        f"{category}: {name}"
        for (category, name), trait in rules.traits.items()
        if category in ("merits", "flaws")
        and GIVES.search(trait.description or "")
        and (category, name) not in granting | listed
    )

    assert unlisted == [], (
        "These say they give another trait: add their grants to "
        f"{GRANTS_FILE.name}, or list them there as rules_only."
    )


def test_the_wording_catches_what_the_audit_found() -> None:
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")

    for name in ("Extrasensory Perceptions", "Angelic Visage", "Rugged", "Web of Knives"):
        assert GIVES.search(rules.traits[("merits", name)].description or ""), name
    for name in ("Slippery Customer", "Iron Will", "Blasé"):
        assert not GIVES.search(rules.traits[("merits", name)].description or ""), name


def test_rules_only_traits_exist_say_why_and_have_no_grants_unless_partly() -> None:
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    granting = {(g.source["category"], g.source["name"]) for g in rules.grants}

    for entry in rules_only():
        key = (entry["category"], entry["name"])
        assert key in rules.traits, key
        # A merit that is `partly` modelled has grants for the part that is, and
        # says here what is missing.
        assert (key in granting) == bool(entry.get("partly")), key
        assert entry["page"] and entry["why"], key


def test_every_free_choices_grant_offers_something_it_can_be_answered_with() -> None:
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    chosen = [g for g in rules.grants if g.kind == "free_choices"]

    assert {g.source["name"] for g in chosen} == {
        "Ventrue Royalty",
        "Chosen of Cappadocius",
        "Old Habits",
        "Piece That Remains",
        "Auspicious",
        "Shadows of the Past",
    }
    for grant in chosen:
        found = options(grant, rules, [SheetTrait("clan", "Caitiff")])
        assert found, grant.key
        assert grant.page, grant.key
        offered = {o.name for o in found}
        places = (grant.picks or {}).get("places", ())
        assert len(offered) >= len(places), grant.key
        # Everything a grant offers is one trait the grant could give.
        assert all((o.category, o.name) in rules.traits for o in found), grant.key
        if grant.target["category"] == "merits":
            assert all(o.rating for o in found), grant.key

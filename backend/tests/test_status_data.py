"""Sect status as data (issue #251): every status with its sect, effects, source
and page; each sect's Accepted and bans; the status each title and social age
gives; and the caps."""

import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from horatio.models import RuleSet, TraitCategory, TraitDefinition
from horatio.rules.checks import matches
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import SheetTrait, TraitData
from horatio.rules.status import (
    GENERAL,
    SOCIAL_AGES,
    STATUS_TYPES,
    TitleData,
    WhileAbsentData,
    check_status_rules,
    titles_from,
)
from horatio.rules.store import read_troupe_rules, sync_rule_set
from horatio.social_age import AGES
from tests.conftest import load_rules

VAMPIRE = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
GHOUL = load_rule_set(DATA_DIR / "bns_met_ghoul.toml")
BOOK_SECTS = (GENERAL, "Camarilla", "Sabbat", "Anarch")
INDEPENDENT_ALLIANCE = "Independent Alliance"


def test_every_status_has_a_sect() -> None:
    by_sect: dict[str, set[str]] = {}
    for status in VAMPIRE.statuses.values():
        by_sect.setdefault(status.sect, set()).add(status.name)

    assert {sect: len(names) for sect, names in by_sect.items()} == {
        GENERAL: 18,
        "Camarilla": 13,
        "Sabbat": 17,
        "Anarch": 12,
        INDEPENDENT_ALLIANCE: 9,
    }
    assert by_sect[INDEPENDENT_ALLIANCE] == {
        "Chairman", "Cold", "Executor", "Licensed", "Muscle", "Trusted",
        "Black-Balled", "Bounty", "Controller",
    }  # fmt: skip
    assert all(s.type in STATUS_TYPES for s in VAMPIRE.statuses.values())


def test_every_book_status_says_what_it_does_and_where() -> None:
    """Each Camarilla, Sabbat, Anarch and general status has its effects, its source
    and its page; a negative status its censure, punishment and duration."""
    missing: list[str] = []
    for status in VAMPIRE.statuses.values():
        if status.sect not in BOOK_SECTS:
            continue
        needs = {"source": status.source, "page": (status.page or "")[:1].isdigit()}
        if status.type == "Negative":
            needs |= {
                "censure": status.censure,
                "punishment": status.punishment,
                "duration": status.duration and status.duration.text,
            }
        elif status.type == "Accepted":
            needs |= {"passive": status.passive}
        else:
            needs |= {"passive": status.passive, "spent": status.spent}
        missing += [f"{status.name}: {field}" for field, value in needs.items() if not value]

    assert missing == []


def test_the_independent_alliance_has_no_effects_without_a_book() -> None:
    for status in VAMPIRE.statuses.values():
        if status.sect == INDEPENDENT_ALLIANCE:
            assert (status.passive, status.spent, status.page) == ("", "", None), status.name
        assert status.no_rules_yet == (status.sect == INDEPENDENT_ALLIANCE), status.name


def test_status_names_are_spelt_as_the_book_has_them() -> None:
    assert {"Architect", "Anointed"} <= set(VAMPIRE.statuses)
    assert not {"Architech", "Annointed"} & set(VAMPIRE.statuses)
    granted = {
        g.target.get("name") for g in VAMPIRE.grants if g.target.get("category") == "status_traits"
    }
    assert {"Architect", "Anointed"} <= granted


def test_negative_status_lasts_as_the_book_says() -> None:
    warned = VAMPIRE.statuses["Warned"].duration
    assert warned is not None
    assert (warned.games, warned.months, warned.stacks) == (2, 1, True)

    disgraced = VAMPIRE.statuses["Disgraced"].duration
    assert disgraced is not None and disgraced.while_held == "Warned"

    vulgar = VAMPIRE.statuses["Vulgar"].duration
    assert vulgar is not None and vulgar.this_game

    forsaken = VAMPIRE.statuses["Forsaken"].duration
    assert forsaken is not None and forsaken.until_removed


def test_accepted_is_not_status() -> None:
    accepted = {s.name for s in VAMPIRE.statuses.values() if not s.counts}

    assert accepted == {"Acknowledged", "Initiated", "Committed"}


def test_each_sect_names_its_accepted_and_bans() -> None:
    sects = VAMPIRE.status_rules.sects

    assert {name: s.accepted for name, s in sects.items()} == {
        "Camarilla": "Acknowledged",
        "Sabbat": "Initiated",
        "Anarch": "Committed",
    }
    for sect in sects.values():
        assert {b.level for b in sect.bans} == {"lesser", "greater"}, sect.name
        assert all(b.applies_to and b.page for b in sect.bans), sect.name


def banned(sect: str, sheet: list[SheetTrait]) -> set[str]:
    """The levels of the sect's bans whose condition the sheet meets."""
    subject = SheetTrait(category="sect", name=sect)
    return {
        b.level
        for b in VAMPIRE.status_rules.sects[sect].bans
        if b.when is not None and matches(b.when, sheet, subject)
    }


def test_bans_the_sheet_can_tell() -> None:
    def sheet(clan: str, path: str = "Humanity") -> list[SheetTrait]:
        return [
            SheetTrait(category="clan", name=clan),
            SheetTrait(category="paths", name=path, rating=4),
        ]

    assert banned("Camarilla", sheet("Ventrue")) == set()
    assert banned("Camarilla", sheet("Gangrel")) == {"lesser"}
    assert banned("Camarilla", sheet("Caitiff")) == {"lesser", "greater"}
    assert banned("Camarilla", sheet("Toreador", "Path of Night")) == {"lesser"}
    assert banned("Sabbat", sheet("Lasombra", "Path of Night")) == set()
    assert banned("Sabbat", sheet("Lasombra")) == {"lesser"}
    assert banned("Sabbat", sheet("Tremere: Telyav", "Path of Night")) == {"greater"}
    assert banned("Anarch", sheet("Brujah", "Path of Night")) == {"greater"}


def test_the_caps_are_the_books() -> None:
    caps = VAMPIRE.status_rules.caps

    assert caps is not None
    assert (caps.abiding_sources, caps.fleeting, caps.lesser_ban, caps.greater_ban) == (1, 5, 3, 1)


TITLE_STATUS = {
    "Inner Circle": ("Camarilla", {"Ascendant", "Authority", "Commander", "Ominous"}),
    "Imperator": ("Camarilla", {"Ascendant", "Authority", "Commander"}),
    "Justicar": ("Camarilla", {"Ascendant", "Authority", "Commander"}),
    "Archon": ("Camarilla", {"Commander", "Noble"}),
    "Myrmidon": ("Camarilla", {"Commander"}),
    "Alastor": ("Camarilla", {"Commander"}),
    "Prince": ("Camarilla", {"Authority", "Commander", "Sovereign"}),
    "Petty Prince": ("Camarilla", {"Authority", "Sovereign"}),
    "Seneschal": ("Camarilla", {"Noble"}),
    "Primogen": ("Camarilla", {"Noble"}),
    "Whip": ("Camarilla", set()),
    "Harpy": ("Camarilla", {"Prominent", "Noble", "Guardian"}),
    "Master Harpy": ("Camarilla", {"Prominent", "Noble", "Guardian"}),
    "Lesser Harpy": ("Camarilla", set()),
    "Keeper of Elysium": ("Camarilla", {"Enforcer", "Guardian"}),
    "Sheriff": ("Camarilla", {"Enforcer", "Privileged"}),
    "Scourge": ("Camarilla", {"Enforcer"}),
    "Regent": ("Sabbat", {"Authority", "Commander", "Ominous", "Sacrosanct"}),
    "Cardinal": ("Sabbat", {"Authority", "Glorious", "Sacrosanct"}),
    "Archbishop": ("Sabbat", {"Authority", "Glorious", "Ordained"}),
    "Bishop": ("Sabbat", set()),
    "Templar": ("Sabbat", {"Enforcer"}),
    "Paladin": ("Sabbat", {"Enforcer"}),
    "Priscus": ("Sabbat", {"Infamous", "Prominent", "Sacrosanct"}),
    "Ductus": ("Sabbat", {"Blessed"}),
    "Priest": ("Sabbat", {"Ordained"}),
    "Abbot": ("Sabbat", set()),
    "Baron": ("Anarch", {"Authority", "Mandate"}),
    "Advocate": ("Anarch", {"Authority", "Mandate"}),
    "President": ("Anarch", {"Authority", "Mandate"}),
    "Minister": ("Anarch", {"Authority", "Mandate"}),
    "Constable": ("Anarch", {"Enforcer", "Warrant"}),
    "Architect": ("Anarch", {"Enforcer"}),
    "Civil Engineer": ("Anarch", {"Enforcer"}),
    "Ambassador": ("Anarch", {"Established"}),
    "Herald": ("Anarch", {"Established"}),
}


def test_titles_give_the_books_status() -> None:
    titles = VAMPIRE.titles_by_name

    for name, (sect, status) in TITLE_STATUS.items():
        assert (titles[name].sect, set(titles[name].status)) == (sect, status), name
        assert (titles[name].page or "").isdigit(), name
    giving = {t.name for t in VAMPIRE.titles if t.gives_status}
    assert giving == set(TITLE_STATUS) - {"Abbot"}


def test_conditional_title_status() -> None:
    titles = VAMPIRE.titles_by_name

    assert titles["Seneschal"].while_absent == (WhileAbsentData("Prince", ("Authority",)),)
    assert titles["Whip"].while_absent == (WhileAbsentData("Primogen", ("Noble",)),)
    bishop = titles["Bishop"]
    assert bishop.choose_one == ("Blessed", "Enforcer")
    assert [(a.title, a.status) for a in bishop.while_absent] == [("Archbishop", ("Ordained",))]
    assert "Blood Bath" in bishop.while_absent[0].note
    # A Lesser Harpy gains Guardian at her gathering while the Master Harpy is away.
    lesser = titles["Lesser Harpy"]
    assert lesser.while_absent == (
        WhileAbsentData("Harpy", ("Guardian",), "At her own local gathering."),
    )
    assert (lesser.page, lesser.unique) == ("379", False)


def test_a_myrmidon_is_an_archon_with_sanctioned_in_place_of_noble() -> None:
    myrmidon = VAMPIRE.titles_by_name["Myrmidon"]

    assert (myrmidon.status, myrmidon.page) == (("Commander",), "371")
    assert "Sanctioned" in myrmidon.note
    assert VAMPIRE.statuses["Sanctioned"].type == "Fleeting"


def test_every_sect_title_gives_status_or_says_why_not() -> None:
    """A title of a sect gives status, or says why the book gives it none and where,
    or has no rules yet (the Independent Alliance's)."""
    for title in VAMPIRE.titles:
        if title.sect is None:
            continue
        if title.no_rules_yet:
            assert (title.sect, title.page) == (INDEPENDENT_ALLIANCE, None), title.name
        elif not title.gives_status:
            assert title.gives_none and (title.page or "").isdigit(), title.name


def test_titles_the_book_gives_no_status_say_so() -> None:
    titles = VAMPIRE.titles_by_name

    for name, (sect, page) in {
        "Abbot": ("Sabbat", "421"),
        "Seraph": ("Sabbat", "424"),
        "Dominion": ("Sabbat", "424"),
        "Agent": ("Sabbat", "424"),
        "Grand Inquisitor": ("Sabbat", "425"),
        "Judge Inquisitor": ("Sabbat", "425"),
        "Knight Inquisitor": ("Sabbat", "425"),
        "Watcher": ("Sabbat", "425"),
        "Josian Archon": ("Camarilla", "373"),
    }.items():
        assert (titles[name].sect, titles[name].page) == (sect, page), name
        assert titles[name].gives_none and not titles[name].gives_status, name


def test_the_independent_alliances_titles_have_no_rules_yet() -> None:
    alliance = {t.name for t in VAMPIRE.titles if t.sect == INDEPENDENT_ALLIANCE}

    assert alliance == {"Actuary", "Emissary", "Executioner", "Malak", "Trustee"}
    assert all(VAMPIRE.titles_by_name[name].no_rules_yet for name in alliance)
    assert not any(t.no_rules_yet for t in VAMPIRE.titles if t.sect != INDEPENDENT_ALLIANCE)


def test_other_names_give_the_same() -> None:
    titles = VAMPIRE.titles_by_name

    assert {
        name: titles[name].office
        for name in VAMPIRE.titles_by_name
        if titles[name].alias_of is not None
    } == {
        "Master Harpy": "Harpy",
        "Paladin": "Templar",
        "Advocate": "Baron",
        "President": "Baron",
        "Minister": "Baron",
        "Civil Engineer": "Architect",
        "Herald": "Ambassador",
    }
    # Emissary stays the Independent Alliance's title.
    assert titles["Emissary"].sect == INDEPENDENT_ALLIANCE
    assert titles["Master Harpy"].unique and titles["President"].unique


def test_an_advocate_is_a_baron() -> None:
    titles = VAMPIRE.titles_by_name
    advocate = titles["Advocate"]

    assert (advocate.alias_of, advocate.office, advocate.sect) == ("Baron", "Baron", "Anarch")
    assert advocate.status == titles["Baron"].status == ("Authority", "Mandate")
    assert advocate.unique and advocate.rank == titles["Baron"].rank
    assert titles["Baron"].aliases == ("Advocate", "President", "Minister")


def test_clan_titles_have_a_clan_and_no_sect() -> None:
    titles = VAMPIRE.titles_by_name

    for name, (clan, page) in {
        "Lord": ("Tremere", "64"),
        "Pontifex": ("Tremere", "187"),
        "Capo": ("Giovanni", "38"),
        "Don": ("Giovanni", "38"),
        "Dona": ("Giovanni", "38"),
    }.items():
        assert (titles[name].clan, titles[name].sect, titles[name].page) == (clan, None, page)
        assert not titles[name].gives_status
    # No sect's title is a clan's.
    assert not any(t.clan and t.sect for t in VAMPIRE.titles)


def test_social_ages_are_not_titles() -> None:
    assert not {"Neonate", "Ancilla", "Elder"} & set(VAMPIRE.titles_by_name)


def test_other_titles_stay_titles() -> None:
    titles = VAMPIRE.titles_by_name

    assert titles["Rom baro"] == TitleData("Rom baro")
    # Every title the catalogue listed is still there but the social ages, with
    # Petty Prince, Lesser Harpy and the other names beside them.
    assert len(VAMPIRE.titles) == 66


def test_social_age_status() -> None:
    by_age = {(a.sect, a.age): set(a.status) for a in VAMPIRE.status_rules.social_ages}

    assert by_age == {
        ("Camarilla", "Ancilla"): {"Confirmed"},
        ("Camarilla", "Elder"): {"Confirmed", "Established", "Privileged"},
    }
    assert SOCIAL_AGES == AGES


def test_a_ghoul_has_the_same_status_rules() -> None:
    assert GHOUL.statuses == VAMPIRE.statuses
    assert GHOUL.titles == VAMPIRE.titles
    assert GHOUL.status_rules == VAMPIRE.status_rules


# --- the rules checks ------------------------------------------------------------------------


def check(*titles: TitleData) -> None:
    check_status_rules(VAMPIRE.traits, VAMPIRE.status_rules, (*VAMPIRE.titles, *titles))


def test_a_title_naming_an_unknown_status_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown status 'Imperious'"):
        check(TitleData("Duke", sect="Camarilla", status=("Imperious",)))
    with pytest.raises(ValueError, match="unknown status"):
        check(TitleData("Duke", choose_one=("Noble", "Imperious")))


def test_a_title_gives_only_abiding_status_of_its_sect() -> None:
    with pytest.raises(ValueError, match="not abiding"):
        check(TitleData("Myrmidon Captain", sect="Camarilla", status=("Sanctioned",)))
    with pytest.raises(ValueError, match="Sabbat status"):
        check(TitleData("Duke", sect="Camarilla", status=("Glorious",)))
    with pytest.raises(ValueError, match="unknown sect"):
        check(TitleData("Duke", sect="Atlantean"))
    with pytest.raises(ValueError, match="unknown title 'King'"):
        check(TitleData("Duke", while_absent=(WhileAbsentData("King", ("Noble",)),)))
    # A title with no sect may give any sect's abiding status.
    check(TitleData("Master of Elysium", status=("Guardian",)))


def test_a_sect_title_says_what_it_gives_or_why_not() -> None:
    with pytest.raises(ValueError, match="Camarilla title that says not what it gives"):
        check(TitleData("Duke", sect="Camarilla"))
    with pytest.raises(ValueError, match="says why it gives no status, but not where"):
        check(TitleData("Duke", sect="Camarilla", gives_none="The book gives none."))
    with pytest.raises(ValueError, match="gives status, and says why it gives none"):
        check(TitleData("Duke", sect="Camarilla", status=("Noble",), gives_none="None.", page="1"))
    with pytest.raises(ValueError, match="no rules yet, so it says nothing more"):
        check(TitleData("Duke", sect=INDEPENDENT_ALLIANCE, no_rules_yet=True, page="12"))
    with pytest.raises(ValueError, match="no rules yet, but no sect"):
        check(TitleData("Duke", no_rules_yet=True))
    check(TitleData("Duke", sect="Camarilla", gives_none="The book gives none.", page="1"))
    check(TitleData("Duke", sect=INDEPENDENT_ALLIANCE, no_rules_yet=True))
    # A title of no sect may be only a name.
    check(TitleData("Duke"))


def test_a_clan_title_is_of_a_known_clan_and_no_sect() -> None:
    with pytest.raises(ValueError, match="unknown clan 'Atlanteans'"):
        check(TitleData("Duke", clan="Atlanteans"))
    with pytest.raises(ValueError, match="clan's title, so it has no sect"):
        check(TitleData("Duke", clan="Tremere", sect="Camarilla", status=("Noble",)))
    with pytest.raises(ValueError, match="clan's title, so it gives no sect status"):
        check(TitleData("Duke", clan="Tremere", status=("Noble",)))
    check(TitleData("Duke", clan="Tremere"))


def test_a_status_says_what_it_does_or_that_it_has_no_rules_yet() -> None:
    def with_status(**properties: Any) -> None:
        traits = {
            **VAMPIRE.traits,
            ("status_traits", "Gilded"): TraitData(
                category="status_traits",
                name="Gilded",
                properties={"type": "Abiding", "sect": "Camarilla", **properties},
            ),
        }
        check_status_rules(traits, VAMPIRE.status_rules, VAMPIRE.titles)

    with pytest.raises(ValueError, match="says not what it does, nor that it has no rules yet"):
        with_status()
    with pytest.raises(ValueError, match="no rules yet, so it says nothing more"):
        with_status(no_rules_yet=True, passive="You glitter.")
    with_status(passive="You glitter.")
    with_status(no_rules_yet=True)


def test_an_alias_is_a_name_of_one_title_only() -> None:
    with pytest.raises(ValueError, match="'Prince' is a title, and another name for Duke"):
        titles_from([{"name": "Duke", "aliases": ["Prince"]}, {"name": "Prince"}])
    with pytest.raises(ValueError, match="another name for both Duke and Earl"):
        titles_from([{"name": "Duke", "aliases": ["Lord"]}, {"name": "Earl", "aliases": ["Lord"]}])
    # A bare name in the catalogue's list may be an alias: the table says what it is.
    [advocate, baron] = titles_from(["Advocate", {"name": "Baron", "aliases": ["Advocate"]}])
    assert (advocate.name, advocate.alias_of, baron.aliases) == ("Advocate", "Baron", ("Advocate",))


def test_a_ban_with_a_condition_naming_an_unknown_trait_is_refused() -> None:
    camarilla = VAMPIRE.status_rules.sects["Camarilla"]
    ban = replace(camarilla.bans[0], when={"has": {"category": "merits", "name": "Nobody"}})
    rules = replace(
        VAMPIRE.status_rules,
        sects={**VAMPIRE.status_rules.sects, "Camarilla": replace(camarilla, bans=(ban,))},
    )

    with pytest.raises(ValueError, match="unknown trait"):
        check_status_rules(VAMPIRE.traits, rules, VAMPIRE.titles)


def test_loading_refuses_a_title_naming_an_unknown_status(tmp_path: Path) -> None:
    data = tmp_path / "data"
    shutil.copytree(DATA_DIR, data)
    with (data / "bns_met_vampire_status.toml").open("a") as f:
        f.write('\n[[titles]]\nname = "Duke"\nsect = "Camarilla"\nstatus = ["Imperious"]\n')

    with pytest.raises(ValueError, match="bns_met_vampire.toml: title 'Duke'"):
        load_rule_set(data / "bns_met_vampire.toml")


# --- in the database -------------------------------------------------------------------------


def test_the_status_rules_read_back_as_loaded(session: Session) -> None:
    sync_rule_set(session, VAMPIRE)

    stored = read_troupe_rules(session, "vampire", None).rule_set

    assert stored.titles == VAMPIRE.titles
    assert stored.status_rules == VAMPIRE.status_rules
    assert stored.statuses == VAMPIRE.statuses
    # horatio.titles reads the names alone.
    names = session.scalar(select(RuleSet.titles).where(RuleSet.splat == "vampire"))
    assert names == [t.name for t in VAMPIRE.titles]


def status_definition(engine: Engine, name: str) -> object:
    with Session(engine) as session:
        return session.scalar(
            select(TraitDefinition.id)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(TraitCategory.key == "status_traits", TraitDefinition.name == name)
        )


def test_the_migration_renames_the_misspelt_status_in_place(
    engine: Engine, alembic_config: Config
) -> None:
    """Sheets hold a status by its definition, so renaming the definition keeps
    every sheet, purchase and approved sheet holding it."""
    architect = status_definition(engine, "Architect")
    assert architect is not None

    command.downgrade(alembic_config, "0079")
    try:
        assert status_definition(engine, "Architech") == architect
        with engine.connect() as connection:
            grants = connection.scalar(text("select grants::text from rule_sets limit 1"))
        assert '"Architech"' in (grants or "")
    finally:
        command.upgrade(alembic_config, "head")
        load_rules(engine)

    assert status_definition(engine, "Architect") == architect
    assert status_definition(engine, "Architech") is None

"""The writes behind a few of a troupe's settings that check what they are given, or
change characters as they go: who may join, Golconda, clan rarity and default
bloodlines. Shared by their routes in Customise and by importing settings
(horatio.troupe_settings_share), so both are checked alike."""

from collections.abc import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, clan_merits
from horatio.models import Character, RuleSet, TraitCategory, TraitDefinition, Troupe, User
from horatio.rules.splats import SPLATS, splat_order
from horatio.rules.store import forget_rules, read_troupe_rules
from horatio.sheets import apply_grants, playing_by, unprocessable


def set_sects(db: Session, user: User, troupe: Troupe, sects: Sequence[str]) -> None:
    """The sects whose player characters may join; none for any."""
    known = set(
        db.scalars(
            select(TraitDefinition.name)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(TraitCategory.key == "sect")
        )
    )
    unknown = sorted(set(sects) - known)
    if unknown:
        raise unprocessable(f"No such sect: {', '.join(unknown)}.")
    troupe.allowed_sects = sorted(set(sects))
    audit.record(
        db,
        user,
        "troupe.sects_limited",
        troupe_id=troupe.id,
        sects=", ".join(troupe.allowed_sects) or "any",
    )


def set_splats(db: Session, user: User, troupe: Troupe, splats: Sequence[str]) -> None:
    """The splats whose player characters may join, and be built for it: at least one."""
    known = set(db.scalars(select(RuleSet.splat)))
    unknown = sorted(set(splats) - known)
    if unknown:
        raise unprocessable(f"No such splat: {', '.join(unknown)}.")
    if not splats:
        raise unprocessable("A troupe takes at least one splat.")
    troupe.allowed_splats = sorted(set(splats), key=splat_order)
    audit.record(
        db,
        user,
        "troupe.splats_limited",
        troupe_id=troupe.id,
        splats=", ".join(SPLATS[s].label for s in troupe.allowed_splats),
    )


def set_golconda(db: Session, user: User, troupe: Troupe, on: bool) -> None:
    """Switch on or off the optional rule that Golconda Seekers are Enlightened. The
    characters playing by the troupe's rules gain or lose it at once."""
    if troupe.golconda_enlightened == on:
        return
    troupe.golconda_enlightened = on
    audit.record(
        db,
        user,
        "house.golconda",
        troupe_id=troupe.id,
        setting="are Enlightened" if on else "are not Enlightened",
    )
    db.flush()
    forget_rules(db)
    for character in playing_by(db, troupe.id):
        apply_grants(db, user, character)


def set_clan_rarity(db: Session, user: User, troupe: Troupe, rarities: Mapping[str, str]) -> None:
    """Name how rare clans are here. Characters being built here take the rarity merit
    it names straight away; finished characters keep theirs."""
    rule_set = read_troupe_rules(db, "vampire", troupe.id).rule_set
    unknown = [c for c in rarities if ("clan", c) not in rule_set.traits or ":" in c]
    if unknown:
        raise unprocessable(
            f"Not a clan: {', '.join(unknown)}. Name the clan; its bloodlines follow it."
        )
    troupe.clan_rarity = dict(sorted(rarities.items()))
    db.flush()
    clan_merits.resync(db, building_here(db, troupe))
    audit.record(
        db,
        user,
        "house.clan_rarity",
        troupe_id=troupe.id,
        rarities=", ".join(f"{c} {r}" for c, r in troupe.clan_rarity.items()) or "the book's",
    )


def set_default_bloodlines(
    db: Session, user: User, troupe: Troupe, defaults: Mapping[str, str]
) -> None:
    """Name the bloodline a clan plays as by default here, or the plain clan. Characters
    being built here take the clan merits it means straight away; finished characters
    keep the bloodline and merits they have."""
    rule_set = read_troupe_rules(db, "vampire", troupe.id).rule_set
    unknown = [
        f"{clan} as {line}"
        for clan, line in defaults.items()
        if ":" in clan
        or ("clan", clan) not in rule_set.traits
        or ("clan", line) not in rule_set.traits
        or clan_merits.family_of(line) != clan
    ]
    if unknown:
        raise unprocessable(f"Not a clan and one of its bloodlines: {', '.join(unknown)}.")
    troupe.default_bloodlines = dict(sorted(defaults.items()))
    db.flush()
    clan_merits.resync(db, building_here(db, troupe))
    audit.record(
        db,
        user,
        "house.default_bloodlines",
        troupe_id=troupe.id,
        defaults=", ".join(
            f"{c} as {'the plain clan' if line == c else line}"
            for c, line in troupe.default_bloodlines.items()
        )
        or "the book's",
    )


def building_here(db: Session, troupe: Troupe) -> list[Character]:
    """The characters still being built under the troupe's rules: homed here, or
    built for it with no home yet."""
    return list(
        db.scalars(
            select(Character).where(
                (Character.home_troupe_id == troupe.id)
                | (
                    Character.home_troupe_id.is_(None) & (Character.building_troupe_id == troupe.id)
                ),
                Character.creation_completed_at.is_(None),
            )
        ).all()
    )

"""A troupe's setting for how many languages Linguistics gives (horatio.rules.languages):
changing it, and the characters it leaves holding more than they may."""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Troupe, User
from horatio.rules import languages
from horatio.rules.checks import violations
from horatio.rules.languages import CATEGORY, SKILL, LanguageRule, Mode
from horatio.rules.store import forget_rules, read_troupe_rules
from horatio.sheets import playing_by, rules_for, sheet_rows

# The most languages one rating may give.
MOST = 999


@dataclass(frozen=True)
class Over:
    """A character holding more languages than its rules now allow."""

    character_id: uuid.UUID
    name: str
    held: int
    allowed: int


def max_rating(db: Session, troupe_id: uuid.UUID) -> int:
    """The highest rating Linguistics can reach, so the highest a chart needs."""
    skills = read_troupe_rules(db, "vampire", troupe_id).rule_set.categories["skills"]
    return skills.max_rating or 5


def over_limit(db: Session, troupe_id: uuid.UUID) -> list[Over]:
    """The active characters playing by the troupe's rules who hold more languages
    than its checks allow. They keep them; the sheet shows the broken check."""
    rule = languages.rule_of(db.get(Troupe, troupe_id))
    found: list[Over] = []
    for character in playing_by(db, troupe_id):
        if character.status == "retired":
            continue
        checks = [c for c in rules_for(db, character).checks() if languages.counts_languages(c)]
        if not checks:
            continue
        sheet = [r.as_rules_trait() for r in sheet_rows(db, character)]
        if not violations(checks, sheet):
            continue
        held = sum(1 for t in sheet if t.category == CATEGORY and t.rating != 0 and not t.granted)
        rating = sum(t.rating or 0 for t in sheet if t.category == "skills" and t.name == SKILL)
        natural = any(t.category == "merits" and t.name == languages.MERIT for t in sheet)
        found.append(Over(character.id, character.name, held, rule.allowed(rating, natural)))
    return sorted(found, key=lambda o: o.name)


def set_rule(
    db: Session,
    user: User,
    troupe: Troupe,
    mode: Mode,
    custom: list[int] | None,
    natural_doubles: bool,
) -> None:
    """Change the troupe's setting. Its own chart is kept while another is chosen,
    so going back to it finds it as it was; a change is logged."""
    before = languages.rule_of(troupe)
    if custom is not None:
        most = max_rating(db, troupe.id)
        if not 1 <= len(custom) <= most:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Give a number of languages for each rating from 1 to {most}.",
            )
        if any(n < 0 or n > MOST for n in custom):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Each rating gives from 0 to {MOST} languages.",
            )
        if any(b < a for a, b in zip(custom, custom[1:], strict=False)):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A higher rating never gives fewer languages than a lower one.",
            )
        troupe.languages_table = list(custom)
    if mode == "custom" and not troupe.languages_table:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Give the troupe's own number of languages for each rating.",
        )
    troupe.languages = mode
    troupe.natural_linguist_doubles = natural_doubles
    after = languages.rule_of(troupe)
    if played(after) != played(before):
        audit.record(
            db,
            user,
            "house.languages",
            troupe_id=troupe.id,
            setting=languages.setting_text(after),
        )
    db.flush()
    forget_rules(db)


def played(rule: LanguageRule) -> tuple[str, tuple[int, ...] | None, bool]:
    """What the setting plays, leaving out a chart kept but not chosen."""
    return rule.mode, rule.table, rule.natural_doubles

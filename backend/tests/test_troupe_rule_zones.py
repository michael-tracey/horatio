"""Rule days and months on the troupe's clock (#1215): a New York troupe at 11 pm on the
last day of a month is still in that month, while UTC is already in the next. A troupe
with no time zone of its own counts them in UTC, as it always did."""

from datetime import UTC, date, datetime

import pytest
from fastapi import HTTPException

from horatio import bonds, influence_effects, troupe_zones
from horatio.models import Troupe

# 11 pm on 31 October in New York (EDT), 3 am on 1 November in UTC.
LATE_ON_THE_31ST = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)


def new_york() -> Troupe:
    return Troupe(name="Nights of Manhattan", time_zone="America/New_York")


def no_zone() -> Troupe:
    return Troupe(name="Nights of Nowhere", time_zone=None)


def test_a_troupes_day_and_month_are_on_its_own_clock() -> None:
    assert troupe_zones.rule_day(new_york(), LATE_ON_THE_31ST) == date(2026, 10, 31)
    assert troupe_zones.month_began(new_york(), LATE_ON_THE_31ST) == datetime(
        2026, 10, 1, 4, 0, tzinfo=UTC
    )


def test_a_troupe_with_no_zone_counts_in_utc() -> None:
    assert troupe_zones.rule_day(no_zone(), LATE_ON_THE_31ST) == date(2026, 11, 1)
    assert troupe_zones.rule_day(None, LATE_ON_THE_31ST) == date(2026, 11, 1)
    assert troupe_zones.month_began(no_zone(), LATE_ON_THE_31ST) == datetime(
        2026, 11, 1, tzinfo=UTC
    )


def test_a_bonds_night_is_the_troupes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(troupe_zones, "now", lambda: LATE_ON_THE_31ST)

    assert bonds.today(new_york()) == date(2026, 10, 31)
    assert bonds.today(no_zone()) == date(2026, 11, 1)
    # With a day's grace: 1 November is fine in New York, the 2nd isn't yet.
    bonds.check_night(date(2026, 11, 1), new_york())
    with pytest.raises(HTTPException):
        bonds.check_night(date(2026, 11, 2), new_york())
    bonds.check_night(date(2026, 11, 2), no_zone())


def test_influence_effect_months_are_the_troupes() -> None:
    zone = troupe_zones.rule_zone(new_york())

    # Still October in New York: a Boost ends as November begins there.
    assert influence_effects.month_start(LATE_ON_THE_31ST, zone) == datetime(
        2026, 10, 1, 4, 0, tzinfo=UTC
    )
    assert influence_effects.next_month(LATE_ON_THE_31ST, zone) == datetime(
        2026, 11, 1, 4, 0, tzinfo=UTC
    )
    # A month on is 30 November at 11 pm there, after the clocks went back.
    assert influence_effects.a_month_on(LATE_ON_THE_31ST, zone) == datetime(
        2026, 12, 1, 4, 0, tzinfo=UTC
    )
    # In UTC it is already November.
    assert influence_effects.next_month(LATE_ON_THE_31ST) == datetime(2026, 12, 1, tzinfo=UTC)
    assert influence_effects.a_month_on(LATE_ON_THE_31ST) == datetime(2026, 12, 1, 3, 0, tzinfo=UTC)

"""A downtime cycle's Due, written with its time in each reader's own settings,
and whether a cycle is past it (#469)."""

from datetime import UTC, datetime, timedelta

import pytest

from horatio import downtimes
from horatio.models import DowntimeCycle, User

# 6 pm in New York on Saturday 14 November 2026.
DUE = datetime(2026, 11, 14, 23, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def in_october(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(downtimes, "now", lambda: datetime(2026, 10, 20, 12, 0, tzinfo=UTC))


def reader(**preferences: str) -> User:
    return User(preferences=preferences)


def test_due_is_written_with_its_time_in_the_readers_zone() -> None:
    assert (
        downtimes.due_text(reader(time_zone="America/New_York"), DUE) == "Sat 14 Nov, 6:00 pm EST"
    )
    assert downtimes.due_text(reader(), DUE) == "Sat 14 Nov, 11:00 pm UTC"
    assert (
        downtimes.due_text(reader(time_zone="Asia/Tokyo", clock="24"), DUE)
        == "Sun 15 Nov, 08:00 JST"
    )
    # A zone with no abbreviation is named by its offset.
    assert downtimes.due_text(reader(time_zone="Asia/Dubai"), DUE) == "Sun 15 Nov, 3:00 am GMT+4"


def test_due_follows_the_readers_date_format() -> None:
    new_york = {"time_zone": "America/New_York"}
    assert downtimes.due_text(reader(**new_york, date_format="month_day"), DUE) == (
        "Sat 11/14, 6:00 pm EST"
    )
    assert downtimes.due_text(reader(**new_york, date_format="iso", clock="24"), DUE) == (
        "Sat 2026-11-14, 18:00 EST"
    )
    # Next year's shows its year.
    assert downtimes.due_text(reader(**new_york), DUE + timedelta(days=60)) == (
        "Wed 13 Jan 2027, 6:00 pm EST"
    )


def test_a_cycle_is_past_due_from_the_moment_due_comes() -> None:
    cycle = DowntimeCycle(closes_at=DUE, grace_ends_at=DUE + timedelta(days=2))
    assert not downtimes.past_due(cycle, DUE - timedelta(seconds=1))
    assert downtimes.past_due(cycle, DUE)
    assert downtimes.past_due(cycle, DUE + timedelta(days=1))
    # Without a moment, now.
    assert not downtimes.past_due(cycle)

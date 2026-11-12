"""Boon statistics' sums (horatio.boon_statistics, #702), on rows alone: the months,
open debt over time, who owes whom, the flow between clans, and each game's boons."""

import uuid
from datetime import UTC, date, datetime, timedelta

from horatio.boon_standings import DEFAULT_WEIGHTS, Ledger, Row, Who
from horatio.boon_statistics import Game, compute, months_from

TODAY = date(2026, 11, 12)


def person(key: str, clan: str | None = None, standing: str = "active") -> Who:
    return Who(
        key=key,
        name=key.title(),
        character_id=uuid.uuid5(uuid.NAMESPACE_DNS, key),
        standing=standing,
        clan=clan,
        age="Neonate",
        sect="Camarilla",
    )


def at(day: date, hour: int = 20) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def owes(
    debtor: str,
    creditor: str,
    kind: str = "minor",
    entered: date = date(2026, 10, 3),
    state: str = "registered",
    closed: date | None = None,
    made_on: date | None = None,
    game: uuid.UUID | None = None,
    hour: int = 20,
) -> Row:
    return Row(
        debtor,
        creditor,
        kind,
        state,
        made_on or entered,
        "called_in" if state == "settled" else None,
        closed,
        at(entered, hour),
        at(closed) if closed else None,
        game,
    )


AGNES = person("agnes", "Toreador")
BRAM = person("bram", "Brujah: Anarch")
CORA = person("cora", "Toreador")
GONE = person("gone", "Ventrue", standing="final_death")


def ledger(*rows: Row) -> Ledger:
    return Ledger(list(rows), {p.key: p for p in (AGNES, BRAM, CORA, GONE)})


def line(found: list, month: str, kind: str = "minor"):  # type: ignore[type-arg]
    return next(m for m in found if m.month == month and m.kind == kind)


def test_months_run_from_the_first_to_the_last_across_a_new_year() -> None:
    assert months_from(date(2025, 11, 30), date(2026, 2, 1)) == [
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
    ]


def test_each_month_counts_registered_settled_and_what_stood_at_its_end() -> None:
    found = compute(
        ledger(
            owes("agnes", "bram", entered=date(2026, 9, 5)),
            owes(
                "bram",
                "agnes",
                "major",
                entered=date(2026, 9, 20),
                state="settled",
                closed=date(2026, 10, 10),
            ),
        ),
        DEFAULT_WEIGHTS,
        today=TODAY,
    ).by_entered

    assert [m.month for m in found if m.kind == "minor"] == ["2026-09", "2026-10", "2026-11"]
    september_minor, september_major = line(found, "2026-09"), line(found, "2026-09", "major")
    assert (september_minor.registered, september_minor.open) == (1, 1)
    assert (september_major.registered, september_major.open_weight) == (1, 3.0)
    october = line(found, "2026-10", "major")
    assert (october.settled, october.settled_weight, october.open) == (1, 3.0, 0)
    # The minor still stands, month after month.
    assert line(found, "2026-11").open == 1


def test_by_night_counts_registering_by_the_in_game_night() -> None:
    found = compute(
        ledger(owes("agnes", "bram", made_on=date(1991, 12, 2)), owes("cora", "bram")),
        DEFAULT_WEIGHTS,
        today=TODAY,
    ).by_night

    assert [(m.month, m.registered) for m in found] == [("1991-12", 1), ("2026-10", 1)]


def test_the_network_joins_each_debtor_to_each_creditor_by_weight() -> None:
    found = compute(
        ledger(
            owes("agnes", "bram", "major"),
            owes("agnes", "bram"),
            owes("cora", "agnes", "trivial"),
            owes("agnes", "gone", "life"),
        ),
        DEFAULT_WEIGHTS,
        today=TODAY,
    )

    heaviest = found.links[0]
    assert (heaviest.debtor, heaviest.creditor, heaviest.weight) == ("agnes", "bram", 4.0)
    assert heaviest.kinds == {"major": 1, "minor": 1}
    # The dead are out of the active scope, links and nodes alike.
    assert all("gone" not in (link.debtor, link.creditor) for link in found.links)
    assert {n.who.key: n.net for n in found.nodes} == {"bram": 4.0, "agnes": -3.5, "cora": -0.5}


def test_everyone_keeps_boons_with_the_departed() -> None:
    found = compute(
        ledger(owes("agnes", "gone", "life")), DEFAULT_WEIGHTS, scope="everyone", today=TODAY
    )

    assert [(link.debtor, link.creditor) for link in found.links] == [("agnes", "gone")]


def test_the_clan_flow_counts_bloodlines_as_their_clan_and_keeps_its_own_clan() -> None:
    found = compute(
        ledger(owes("agnes", "bram", "major"), owes("bram", "cora"), owes("agnes", "cora")),
        DEFAULT_WEIGHTS,
        today=TODAY,
    ).clan_flow

    assert found.groups == ["Toreador", "Brujah"]
    toreador, brujah = 0, 1
    assert found.matrix[toreador][brujah] == 3.0
    assert found.matrix[brujah][toreador] == 1.0
    assert found.matrix[toreador][toreador] == 1.0
    assert found.counts[toreador][toreador] == 1


def test_a_game_has_the_boons_registered_at_it_or_entered_that_night() -> None:
    night = date(2026, 10, 3)
    game = Game(uuid.uuid4(), at(night, 19), at(night, 19) + timedelta(hours=5))
    found = compute(
        ledger(
            # Typed in as the game ends, past midnight UTC.
            owes("agnes", "bram", entered=date(2026, 10, 4), hour=5),
            # Entered days later, but staff said it was at this game.
            owes("cora", "bram", "major", entered=date(2026, 10, 10), game=game.id),
            # Days later, and no game given: not this game's.
            owes("cora", "agnes", entered=date(2026, 10, 10)),
            owes(
                "bram",
                "agnes",
                entered=date(2026, 9, 1),
                state="settled",
                closed=date(2026, 10, 3),
            ),
        ),
        DEFAULT_WEIGHTS,
        [game],
        today=TODAY,
    ).games[0]

    assert (found.registered, found.registered_weight) == (2, 4.0)
    assert found.by_kind == {"minor": 1, "major": 1}
    assert found.settled == 1
    assert [(w.key, n) for w, n in found.most_active] == [("bram", 2), ("agnes", 1), ("cora", 1)]


def test_pending_boons_are_left_out() -> None:
    found = compute(ledger(owes("agnes", "bram", state="pending")), DEFAULT_WEIGHTS, today=TODAY)

    assert found.by_entered == []
    assert found.links == []

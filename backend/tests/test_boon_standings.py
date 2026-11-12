"""Boon standings' sums (horatio.boon_standings, #691), on rows alone: weights and
net, the active scope, the court, groups, the age of open debt, settling, boons
across lines and mutual debts."""

import uuid
from datetime import date

from horatio.boon_standings import (
    DEFAULT_WEIGHTS,
    Ledger,
    Row,
    Who,
    band_label,
    band_of,
    compute,
    months_between,
)

TODAY = date(2026, 11, 12)


def person(
    key: str,
    clan: str | None = None,
    standing: str = "active",
    titles: tuple[str, ...] = (),
) -> Who:
    """A character in the troupe, a Camarilla Neonate unless said otherwise."""
    return Who(
        key=key,
        name=key.title(),
        character_id=uuid.uuid5(uuid.NAMESPACE_DNS, key),
        standing=standing,
        clan=clan,
        age="Neonate",
        sect="Camarilla",
        titles=titles,
    )


def owes(
    debtor: str,
    creditor: str,
    kind: str = "minor",
    state: str = "registered",
    made_on: date = date(2026, 10, 3),
    settled_how: str | None = None,
    closed_on: date | None = None,
) -> Row:
    return Row(debtor, creditor, kind, state, made_on, settled_how, closed_on)


def ledger(rows: list[Row], *people: Who, order: dict[str, int] | None = None) -> Ledger:
    return Ledger(rows, {p.key: p for p in people}, order or {})


AGNES = person("agnes", "Toreador")
BRAM = person("bram", "Brujah")
CORA = person("cora", "Toreador")


def test_net_is_what_is_owed_to_them_less_what_they_owe_by_weight() -> None:
    found = compute(
        ledger(
            [
                owes("agnes", "bram", "major"),
                owes("bram", "agnes"),
                owes("cora", "agnes", "trivial"),
            ],
            AGNES,
            BRAM,
            CORA,
        ),
        DEFAULT_WEIGHTS,
        today=TODAY,
    )

    by = {s.who.key: s for s in found.characters}
    assert (by["agnes"].owed, by["agnes"].owes, by["agnes"].net) == (1.5, 3.0, -1.5)
    assert (by["bram"].owed, by["bram"].owes, by["bram"].net) == (3.0, 1.0, 2.0)
    assert [s.who.key for s in found.characters] == ["bram", "cora", "agnes"]
    assert {k.kind: (k.count, k.total) for k in found.by_kind}["major"] == (1, 3.0)


def test_a_troupe_s_own_weights_change_the_sums() -> None:
    weights = {**DEFAULT_WEIGHTS, "major": 4.0}

    found = compute(ledger([owes("agnes", "bram", "major")], AGNES, BRAM), weights, today=TODAY)

    assert found.characters[0].net == 4.0
    assert found.weights["major"] == 4.0


def test_active_leaves_out_boons_with_someone_departed_and_everyone_keeps_them() -> None:
    gone = person("dorian", "Ventrue", standing="final_death")
    rows = [owes("dorian", "agnes", "life"), owes("bram", "agnes")]
    book = ledger(rows, AGNES, BRAM, gone)

    active = compute(book, DEFAULT_WEIGHTS, today=TODAY)
    everyone = compute(book, DEFAULT_WEIGHTS, "everyone", today=TODAY)

    assert {s.who.key: s.owed for s in active.characters}["agnes"] == 1.0
    assert {s.who.key: s.owed for s in everyone.characters}["agnes"] == 11.0
    # The totals count the whole ledger either way.
    assert (active.totals.open, active.totals.departed) == (1, 1)
    assert everyone.totals == active.totals


def test_totals_count_settled_pending_and_boons_with_a_name_only() -> None:
    stranger = Who(key="name:the moon", name="The Moon")
    rows = [
        owes("agnes", "bram", state="settled", settled_how="called_in", closed_on=TODAY),
        owes("agnes", "bram", state="pending"),
        owes("name:the moon", "agnes"),
    ]

    totals = compute(ledger(rows, AGNES, BRAM, stranger), DEFAULT_WEIGHTS, today=TODAY).totals

    assert (totals.open, totals.settled, totals.pending, totals.name_only) == (1, 1, 1, 1)


def test_the_court_lists_each_title_holder_in_court_order_with_who_owes_them() -> None:
    prince = person("vera", "Ventrue", titles=("Prince",))
    harpy = person("hal", "Toreador", titles=("Harpy",))
    rows = [owes("agnes", "vera", "major"), owes("bram", "vera"), owes("vera", "hal")]

    court = compute(
        ledger(rows, AGNES, BRAM, prince, harpy, order={"Prince": 0, "Harpy": 1}),
        DEFAULT_WEIGHTS,
        today=TODAY,
    ).court

    assert [o.title for o in court] == ["Prince", "Harpy"]
    assert [(t.who.key, t.weight) for t in court[0].owe_them] == [("agnes", 3.0), ("bram", 1.0)]
    assert [t.who.key for t in court[0].they_owe] == ["hal"]
    assert court[0].standing.net == 3.0


def test_clans_ages_and_sects_roll_up_and_a_name_only_has_its_own_group() -> None:
    stranger = Who(key="name:the moon", name="The Moon")
    rows = [owes("agnes", "bram"), owes("cora", "bram"), owes("name:the moon", "agnes")]

    found = compute(ledger(rows, AGNES, BRAM, CORA, stranger), DEFAULT_WEIGHTS, today=TODAY)

    clans = {g.label: g for g in found.clans}
    assert (clans["Toreador"].characters, clans["Toreador"].owes, clans["Toreador"].owed) == (
        2,
        2.0,
        1.0,
    )
    assert clans["Brujah"].net == 2.0
    assert clans["Name only"].characters == 1
    assert {g.label for g in found.sects} == {"Camarilla", "Name only"}


def test_open_debt_is_aged_in_three_month_bands_from_the_night_it_was_made() -> None:
    rows = [
        owes("agnes", "bram", made_on=date(2026, 9, 12)),
        owes("agnes", "bram", "major", made_on=date(2026, 6, 1)),
        owes("agnes", "bram", made_on=date(1991, 12, 2)),
    ]

    bands = compute(ledger(rows, AGNES, BRAM), DEFAULT_WEIGHTS, today=TODAY).debt_age

    assert [b.label for b in bands][:3] == ["0–3", "4–6", "7–9"]
    assert bands[-1].label == "Over 36"
    assert (bands[0].count, bands[1].weight, bands[-1].count) == (1, 3.0, 1)


def test_band_edges() -> None:
    assert [band_of(m) for m in (0, 3, 4, 6, 7, 36, 37, 400)] == [0, 0, 1, 1, 2, 11, 12, 12]
    assert band_label(11) == "34–36"
    assert months_between(date(2026, 1, 31), date(2026, 2, 28)) == 0
    assert months_between(date(2026, 1, 15), date(2026, 4, 15)) == 3
    assert months_between(date(2026, 5, 1), date(2026, 4, 1)) == 0


def test_settling_by_kind_how_fast_and_who_calls_their_boons_in() -> None:
    rows = [
        owes(
            "agnes",
            "bram",
            state="settled",
            settled_how="called_in",
            made_on=date(2026, 1, 1),
            closed_on=date(2026, 3, 1),
        ),
        owes(
            "agnes",
            "bram",
            "major",
            state="settled",
            settled_how="forgiven",
            made_on=date(2026, 1, 1),
            closed_on=date(2026, 7, 1),
        ),
        owes("agnes", "bram"),
        owes("bram", "cora", "major"),
    ]

    settling = compute(ledger(rows, AGNES, BRAM, CORA), DEFAULT_WEIGHTS, today=TODAY).settling

    assert (settling.count, settling.weight, settling.median_months) == (2, 4.0, 4.0)
    minor = {k.kind: k for k in settling.by_kind}["minor"]
    assert (minor.count, minor.called_in, minor.forgiven, minor.median_months) == (1, 1, 0, 2.0)
    assert [(c.who.key, c.called_in, c.open, c.rate) for c in settling.calls_in] == [
        ("bram", 1.0, 1.0, 50)
    ]
    assert [(c.who.key, c.open) for c in settling.leaves] == [("cora", 3.0)]
    assert [(b.label, b.count) for b in settling.by_clan] == [("Toreador", 2)]


def test_boons_across_clan_lines_and_who_has_most_across_them() -> None:
    rows = [owes("agnes", "bram", "major"), owes("cora", "bram"), owes("agnes", "cora")]

    across = compute(ledger(rows, AGNES, BRAM, CORA), DEFAULT_WEIGHTS, today=TODAY).across_clans

    assert (across.crossing, across.crossing_weight, across.of) == (2, 4.0, 3)
    assert [(p.label, p.count, p.weight) for p in across.pairs] == [("Brujah ↔ Toreador", 2, 4.0)]
    assert [t.who.key for t in across.most] == ["bram", "agnes", "cora"]


def test_mutual_debts_put_the_one_who_owes_more_first() -> None:
    rows = [owes("agnes", "bram"), owes("bram", "agnes", "major"), owes("agnes", "cora")]

    mutual = compute(ledger(rows, AGNES, BRAM, CORA), DEFAULT_WEIGHTS, today=TODAY).mutual

    assert [(m.first.key, m.second.key, m.owes, m.back, m.net) for m in mutual] == [
        ("bram", "agnes", 3.0, 1.0, 2.0)
    ]

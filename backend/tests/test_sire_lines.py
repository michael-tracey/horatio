"""Building a troupe's sire lines from each character's sire (horatio.sire_lines.forest):
several roots, sires known by name only shared by name and clan, and never a loop."""

import uuid

from horatio.sire_lines import Node, Person, forest, named_key


def person(name: str, **kw: object) -> Person:
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": name,
        "clan": "Ventrue",
        "generation": None,
        "left_reason": None,
        "retired": False,
        "kind": "pc",
    }
    return Person(**{**base, **kw})  # type: ignore[arg-type]


def by_name(nodes: list[Node]) -> dict[str, Node]:
    return {n.name: n for n in nodes}


def test_each_eldest_known_is_a_root_and_childer_hang_from_their_sire() -> None:
    elsa = person("Elsa")
    anna = person("Anna", sire_id=elsa.id)
    berit = person("Berit", sire_id=elsa.id)
    carl = person("Carl", sire_id=anna.id)
    lone = person("Lone")
    found = by_name(forest([carl, anna, lone, berit, elsa]))
    assert found["Elsa"].sire_key is None
    assert found["Lone"].sire_key is None
    assert found["Anna"].sire_key == found["Berit"].sire_key == str(elsa.id)
    assert found["Carl"].sire_key == str(anna.id)
    # By name, whatever order they came in.
    assert [n.name for n in forest([carl, anna, lone, berit, elsa])] == [
        "Anna",
        "Berit",
        "Carl",
        "Elsa",
        "Lone",
    ]


def test_a_sire_known_by_name_is_one_node_for_every_childe_naming_it() -> None:
    anna = person("Anna", sire_name="Old Marcus", sire_clan="Tremere")
    # The same sire, however it is typed.
    berit = person("Berit", sire_name=" old marcus ", sire_clan="TREMERE")
    # Another Marcus, of another clan, is someone else.
    carl = person("Carl", sire_name="Old Marcus", sire_clan="Gangrel")
    nodes = forest([anna, berit, carl])
    named = [n for n in nodes if n.kind == "named"]
    assert len(named) == 2
    found = by_name(nodes)
    assert found["Anna"].sire_key == found["Berit"].sire_key == named_key("Old Marcus", "Tremere")
    assert found["Carl"].sire_key == named_key("Old Marcus", "Gangrel")
    marcus = next(n for n in named if n.key == named_key("Old Marcus", "Tremere"))
    # The first spelling given names it.
    assert marcus.name == "Old Marcus" and marcus.clan == "Tremere"
    assert marcus.character_id is None


def test_a_loop_in_the_records_is_cut_so_the_tree_never_cycles() -> None:
    a_id, b_id, c_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    a = person("A", id=a_id, sire_id=c_id)
    b = person("B", id=b_id, sire_id=a_id)
    c = person("C", id=c_id, sire_id=b_id)
    nodes = forest([a, b, c])
    keys = {n.key: n.sire_key for n in nodes}
    # Exactly one link goes, so the three stay one line.
    assert sum(1 for s in keys.values() if s is None) == 1
    for start in keys:
        seen = set()
        at: str | None = start
        while at is not None:
            assert at not in seen
            seen.add(at)
            at = keys[at]


def test_a_sire_outside_the_set_is_drawn_by_name_or_left_out() -> None:
    far = person("Far Away", clan="Toreador")
    unknown = uuid.uuid4()
    anna = person("Anna", sire_id=far.id)
    berit = person("Berit", sire_id=unknown)
    nodes = forest([anna, berit], {far.id: far})
    found = by_name(nodes)
    assert found["Far Away"].kind == "elsewhere"
    assert found["Anna"].sire_key == str(far.id)
    # A sire the caller may not see is never named.
    assert found["Berit"].sire_key is None
    assert set(found) == {"Far Away", "Anna", "Berit"}


def test_a_retired_character_keeps_how_it_left() -> None:
    gone = person("Gone", retired=True, left_reason="final_death")
    childe = person("Childe", sire_id=gone.id)
    found = by_name(forest([gone, childe]))
    assert found["Gone"].retired and found["Gone"].left_reason == "final_death"
    assert found["Childe"].sire_key == str(gone.id)

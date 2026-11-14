"""Summoned allies (issue #827): what a power calls up at a game, each with its own
health levels to tap, gone when dismissed or when the game ends; and items a power
makes for the game, held while their switch is on."""

import uuid
from datetime import UTC, datetime, timedelta

from horatio import play, reference
from horatio.models import PlayEvent
from horatio.reference import Sheet, summons_of

DISCIPLINES = "disciplines"


def sheet(
    disciplines: dict[str, int] | None = None,
    focuses: set[str] | None = None,
    skills: dict[str, int] | None = None,
    others: list[tuple[str, str]] = (),  # type: ignore[assignment]
) -> Sheet:
    disciplines = disciplines or {}
    ratings = {(DISCIPLINES, n): r for n, r in disciplines.items()}
    ratings |= {("skills", n): r for n, r in (skills or {}).items()}
    ratings |= {(c, n): 1 for c, n in others}
    return Sheet(
        ratings=ratings,
        focuses=focuses or set(),
        disciplines=disciplines,
        others=[(c, c, n) for c, n in others],
    )


def found(s: Sheet) -> dict[str, reference.Summon]:
    return {x.key: x for x in summons_of(s, {})}


def test_arms_of_the_abyss_one_per_obtenebration_power_at_most_five() -> None:
    """Core p. 149: one Arm per Obtenebration power, five at most, 4 health levels."""
    arms = found(sheet({"Obtenebration": 3}))["Arms of the Abyss"]
    assert (arms.name, arms.most, arms.health, arms.page) == (
        "Arm of the Abyss",
        3,
        4,
        "pp. 148-149",
    )
    assert "pool 8" in arms.note
    assert found(sheet({"Obtenebration": 5}))["Arms of the Abyss"].most == 5


def test_arms_of_the_abyss_with_the_focus_and_fortitude_have_six_levels() -> None:
    """Core p. 149: the Manipulation focus, with a dot of Fortitude, gives 6 health levels."""
    focused = found(sheet({"Obtenebration": 3}, {"Manipulation"}))["Arms of the Abyss"]
    assert focused.health == 4 and "pool 10" in focused.note
    tough = found(sheet({"Obtenebration": 3, "Fortitude": 1}, {"Manipulation"}))
    assert tough["Arms of the Abyss"].health == 6


def test_zombies_as_many_as_occult_dots() -> None:
    """Core p. 175: as many zombies as Occult dots, 2-point Stock NPCs (3 with Charisma)."""
    zombies = found(sheet({"Necromancy: Bone Path": 3}, skills={"Occult": 4}))
    assert (zombies["Shambling Hordes"].most, zombies["Shambling Hordes"].health) == (4, 2)
    charming = found(sheet({"Necromancy: Bone Path": 3}, {"Charisma"}, {"Occult": 2}))
    assert charming["Shambling Hordes"].health == 3
    # No Occult, no zombies to control.
    assert "Shambling Hordes" not in found(sheet({"Necromancy: Bone Path": 3}))


def test_a_shadow_twin_has_no_health_levels() -> None:
    """Core p. 219: immune to Physical harm, so only out or not."""
    twin = found(sheet(others=[("elder_disciplines", "Obtenebration: Shadow Twin")]))
    assert twin["Shadow Twin"].health == 0 and twin["Shadow Twin"].most == 1


def test_primal_strength_gives_the_beast_spirit_three_more_levels() -> None:
    """Vol. 2 pp. 80 and 84: Spiritus powers set the companion's level; Primal Strength
    adds 3 Healthy levels."""
    base = found(sheet({"Spiritus": 2}))["Tame Spirit"]
    assert base.health == 2 and base.page == "Vol. 2, p. 80"
    strong = found(
        sheet({"Spiritus": 5}, others=[("elder_disciplines", "Spiritus: Primal Strength")])
    )
    # Five Spiritus powers and the elder power itself: 6, and 3 more.
    assert strong["Tame Spirit"].health == 6 + 3


def test_a_use_calls_up_its_summon() -> None:
    """The power's use says which ally it calls up, and whether every one at once."""
    entry = reference.catalogue().power("Obtenebration", "Arms of the Abyss")
    assert entry is not None
    [use] = reference.uses(entry, sheet({"Obtenebration": 3}))
    assert (use.summon, use.summon_all, use.cost) == (
        "Arms of the Abyss",
        True,
        reference.Cost(tracker="blood", amount=1),
    )


ARMS = reference.Summon(
    key="Arms", name="Arm", origin="Obtenebration 3", page="p. 149", health=4, most=2
)
TWIN = reference.Summon(key="Twin", name="Twin", origin="Shadow Twin", page="p. 219")


def limits() -> play.Limits:
    return play.Limits(
        generation=0,
        blood=10,
        blood_per_turn=1,
        starting_blood=10,
        willpower=5,
        health=(("Healthy", 3), ("Injured", 3), ("Incapacitated", 3)),
        morality=5,
        morality_name="Humanity",
        summons=(ARMS, TWIN),
    )


START = datetime(2026, 11, 14, 20, 0, tzinfo=UTC)


def tap(tracker: str, amount: int, n: int = 0) -> PlayEvent:
    return PlayEvent(
        id=uuid.uuid4(),
        kind="change",
        tracker=tracker,
        amount=amount,
        happened_at=START + timedelta(seconds=n),
    )


def test_an_ally_is_called_up_hurt_and_dismissed() -> None:
    found = limits()
    state = found.start()
    assert state["allies"] == []
    assert [a.name for a in found.ally_slots()] == ["Arm 1", "Arm 2", "Twin"]
    # Not out, its health changes nothing.
    assert play.apply(state, found, tap("ally:Arms#1/health", -1)) == (4, 4)
    assert play.apply(state, found, tap("ally:Arms#1", 1)) == (0, 1)
    assert play.apply(state, found, tap("ally:Arms#1/health", -3)) == (4, 1)
    assert play.apply(state, found, tap("ally:Arms#1/health", -3)) == (1, 0)
    assert play.apply(state, found, tap("ally:Arms#2", 1)) == (0, 1)
    assert state["allies"] == ["ally:Arms#1", "ally:Arms#2"]
    assert play.apply(state, found, tap("ally:Arms#1", -1)) == (1, 0)
    # Called up again, it is a new one, every level clear.
    play.apply(state, found, tap("ally:Arms#1", 1))
    assert state["uses"]["ally:Arms#1/health"] == 4
    assert state["allies"] == ["ally:Arms#2", "ally:Arms#1"]


def test_an_ally_with_no_health_levels_is_only_out_or_not() -> None:
    found = limits()
    state = found.start()
    assert play.apply(state, found, tap("ally:Twin#1", 1)) == (0, 1)
    assert found.most("ally:Twin#1/health") is None
    assert play.apply(state, found, tap("ally:Twin#1/health", -1)) is None
    # One past those it can have out is no tracker at all.
    assert play.apply(state, found, tap("ally:Arms#3", 1)) is None


def test_each_game_starts_with_none_out_and_undo_takes_one_back() -> None:
    found = limits()
    events = [tap("ally:Arms#1", 1, 1), tap("ally:Arms#1/health", -2, 2), tap("ally:Arms#2", 1, 3)]
    state = play.replay(found, events).state
    assert state["allies"] == ["ally:Arms#1", "ally:Arms#2"]
    assert state["uses"]["ally:Arms#1/health"] == 2
    undo = PlayEvent(
        id=uuid.uuid4(),
        kind="undo",
        tracker=events[2].tracker,
        amount=0,
        undoes_id=events[2].id,
        happened_at=START + timedelta(seconds=4),
    )
    assert play.replay(found, [*events, undo]).state["allies"] == ["ally:Arms#1"]
    # A new game starts from the sheet: no ally out, every level clear.
    fresh = found.start()
    assert fresh["allies"] == [] and fresh["uses"]["ally:Arms#1/health"] == 4


def test_the_log_says_who_was_called_up_and_dismissed() -> None:
    found = limits()
    assert found.name("ally:Arms#2") == "Arm 2"
    assert found.name("ally:Arms#2/health") == "Arm 2: health"
    up = tap("ally:Arms#2", 1)
    assert play.describe(up, found) == "Called up Arm 2"
    assert play.describe(tap("ally:Twin#1", -1), found) == "Dismissed Twin"
    assert play.known_tracker("ally:Arms#2/health")


def test_items_a_power_makes_are_its_switch() -> None:
    """Core pp. 189-190: the conjured object is held while its switch is on; Twisted
    Metal's quality is picked and kept until replaced (Vol. 2 p. 130)."""
    keys = reference.catalogue().switch_keys
    assert {"Summon the Simple Form", "Magic of the Smith", "Shadowcrafting"} <= keys
    assert "Twisted Metal" in reference.catalogue().kept_keys

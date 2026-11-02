"""Game XP charts (issue #438): a troupe's chart of XP by earned-XP band and
attendance kind, adjustments with monthly limits, the monthly cap, absentee games and
absentee downtimes, and figures set by hand. With nothing set, a game's XP is awarded
as it always was."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import checkin, xp_range
from horatio.models import GameXpAward, XpEntry
from horatio.models import Troupe as TroupeRecord
from tests.api_helpers import Person, Troupe
from tests.test_api_character_search import member
from tests.test_api_checkin import check_in, game, night, past_game, path
from tests.test_api_downtimes import member_character, my_downtime, new_cycle, open_cycle

AIT = [
    {"up_to": 200, "attended": 5, "absentee": 4},
    {"up_to": 300, "attended": 4, "absentee": 3},
    {"up_to": 400, "attended": 3, "absentee": 2},
    {"up_to": 500, "attended": 2, "absentee": 1},
    {"up_to": None, "attended": 1, "absentee": 0},
]


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def configure(troupe: Troupe, **chosen: Any) -> dict[str, Any]:
    response = troupe.storyteller.client.put(f"/troupes/{troupe.id}/game-xp", json=chosen)
    assert response.status_code == 200, response.text
    return response.json()


def award(troupe: Troupe, game_id: str, **body: Any) -> dict[str, Any]:
    response = troupe.assistant.client.post(
        path(troupe, game_id, "/xp"), json={"amount": 8, "reason": "Game", **body}
    )
    assert response.status_code == 200, response.text
    return response.json()


def history(person: Person, character_id: str) -> list[tuple[str, int]]:
    entries = person.client.get(f"/characters/{character_id}/xp").json()
    return [(e["reason"], e["amount"]) for e in entries if e["reason"].startswith("Game")]


def earn(session: Session, character_id: str, amount: int, *, last_month: bool = False) -> None:
    """Earned XP from before: this month, or (`last_month`) not counted against its cap."""
    cid = uuid.UUID(character_id)
    lead = session.scalar(select(XpEntry.entered_by).where(XpEntry.character_id == cid))
    on = checkin.month_start(datetime.now(UTC).date()) - timedelta(days=1)
    session.add(
        XpEntry(
            character_id=cid,
            kind="award",
            amount=amount,
            reason="Earlier games",
            entered_by=lead,
            **({"entered_on": on} if last_month else {}),
        )
    )
    session.flush()


def mark(person: Person, troupe: Troupe, game_id: str, character_id: str) -> Any:
    return person.client.put(path(troupe, game_id, f"/absentee/{character_id}"))


def record(troupe: Troupe) -> TroupeRecord:
    return troupe.session.get_one(TroupeRecord, uuid.UUID(troupe.id))


# --- with nothing set ---------------------------------------------------------------------


def test_with_nothing_set_a_game_is_awarded_as_before(troupe: Troupe, session: Session) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    settings = troupe.player.client.get(f"/troupes/{troupe.id}/game-xp").json()
    assert settings == {
        "bands": [],
        "adjustments": [],
        "cap": "warn",
        "monthly_xp": None,
        "absentee": False,
        "absentee_by_players": False,
        "absentee_downtime": False,
        "absentee_lookback_days": 60,
    }
    tonight = game(troupe, timedelta(minutes=-60))
    assert check_in(troupe.assistant, troupe, tonight, agnes).status_code == 200
    seen = night(troupe, tonight)
    assert seen["monthly_xp"] == 10
    assert [(x["character_name"], x["kind"], x["band"], x["figure"]) for x in seen["xp_lines"]] == [
        ("Agnes", "attended", None, None)
    ]
    earn(session, agnes, 7)
    before = xp_range.figures(session, record(troupe))

    done = award(troupe, tonight, amount=4, reason="Game, 1 November")

    assert done == {"characters": 1, "total": 4, "past_monthly": ["Agnes"], "capped": []}
    # The reason is the note as given, with nothing added.
    assert history(troupe.player, agnes) == [("Game, 1 November", 4)]
    after = xp_range.figures(session, record(troupe))
    assert after.floor - before.floor == 4
    seen = night(troupe, tonight)
    assert seen["xp"]["amount"] == 4
    assert [(g["character_name"], g["amount"], g["band"]) for g in seen["given"]] == [
        ("Agnes", 4, None)
    ]
    # No house rule to show players.
    rules = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()
    assert not [o for o in rules["other"] if "XP" in o["name"] or "Absentee" in o["name"]]


# --- the settings -------------------------------------------------------------------------


def test_storytellers_set_the_chart_and_its_checked_and_logged(troupe: Troupe) -> None:
    saved = configure(
        troupe,
        bands=AIT,
        adjustments=[
            {"name": "Helped", "amount": 1, "per_month": 1},
            {"name": "Not findable", "amount": -1},
        ],
        cap="cap",
        monthly_xp=12,
        absentee=True,
    )
    assert saved["bands"] == AIT
    assert [(a["name"], a["amount"], a["per_month"]) for a in saved["adjustments"]] == [
        ("Helped", 1, 1),
        ("Not findable", -1, None),
    ]
    keys = [a["key"] for a in saved["adjustments"]]
    assert all(keys) and len(set(keys)) == 2
    # Saving again keeps each adjustment's key, so its monthly limit keeps counting.
    again = configure(troupe, bands=AIT, adjustments=saved["adjustments"])
    assert [a["key"] for a in again["adjustments"]] == keys

    url = f"/troupes/{troupe.id}/game-xp"
    for bad in (
        {"bands": [{"up_to": 300, "attended": 5, "absentee": 4}, *AIT[1:]]},
        {"bands": AIT[:-1]},
        {"bands": [{"up_to": None, "attended": 5, "absentee": 4}, *AIT]},
        {"adjustments": [{"name": "Helped", "amount": 1}, {"name": "helped", "amount": 2}]},
        {"adjustments": [{"name": "Nothing", "amount": 0}]},
    ):
        assert troupe.storyteller.client.put(url, json=bad).status_code == 422, bad
    for person in (troupe.assistant, troupe.player):
        assert person.client.put(url, json={"cap": "off"}).status_code == 403

    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert any(
        "set the troupe's game XP: 5 XP a game up to 200 earned XP, 4 up to 300, 3 up to 400,"
        " 2 up to 500, then 1" in m
        for m in log
    ), log
    assert any(
        "monthly XP capped at 12 a month; absentee games recorded by staff" in m for m in log
    )


def test_players_see_the_chart_on_the_house_rules_tab(troupe: Troupe) -> None:
    configure(
        troupe,
        bands=AIT,
        adjustments=[{"name": "Helped", "amount": 1, "per_month": 1}],
        cap="cap",
        absentee=True,
        absentee_downtime=True,
    )
    rules = troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").json()
    shown = {o["name"]: o["text"] for o in rules["other"]}
    assert shown["Game XP, by earned XP"] == (
        "5 XP a game up to 200 earned XP, 4 up to 300, 3 up to 400, 2 up to 500, then 1;"
        " an absentee game 4, 3, 2, 1 and 0"
    )
    assert shown["Game XP adjustment: Helped"] == "Helped +1, once a month"
    assert shown["Monthly XP"] == "Capped at 10 a month"
    assert shown["Absentee games"] == (
        "Recorded by staff; a downtime needs a game attended in the 60 days before its cycle"
        " closes. Payments are not tracked in Horatio"
    )


# --- bands --------------------------------------------------------------------------------


def test_each_character_gets_its_bands_figure_and_moves_band_mid_month(
    troupe: Troupe, session: Session
) -> None:
    configure(troupe, bands=AIT, cap="off")
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    # Agnes has earned 198 XP before this month; Beatrix 450. Starting XP doesn't count.
    earn(session, agnes, 198, last_month=True)
    earn(session, beatrix, 450, last_month=True)
    first = past_game(troupe, session, days_ago=2)
    for c in (agnes, beatrix):
        assert check_in(troupe.assistant, troupe, first, c).status_code == 200
    lines = {x["character_name"]: x for x in night(troupe, first)["xp_lines"]}
    assert (lines["Agnes"]["earned_xp"], lines["Agnes"]["band"], lines["Agnes"]["figure"]) == (
        198,
        "0–200",
        5,
    )
    assert (lines["Beatrix"]["band"], lines["Beatrix"]["figure"]) == ("401–500", 2)

    done = award(troupe, first, reason="Game 9 March 2030")
    assert done["total"] == 7
    assert history(troupe.player, agnes) == [("Game 9 March 2030: attended, 0–200 band", 5)]
    assert history(troupe.player, beatrix) == [("Game 9 March 2030: attended, 401–500 band", 2)]

    # Agnes is at 203 now: her next game this month is in the next band.
    second = game(troupe, timedelta(minutes=-60))
    assert check_in(troupe.assistant, troupe, second, agnes).status_code == 200
    award(troupe, second, reason="Game 23 March 2030")
    assert history(troupe.player, agnes)[-1] == ("Game 23 March 2030: attended, 201–300 band", 4)


def test_a_chart_changed_mid_month_applies_from_the_next_game(
    troupe: Troupe, session: Session
) -> None:
    configure(troupe, bands=AIT, cap="off")
    agnes = member_character(troupe, troupe.player, "Agnes")
    first = past_game(troupe, session, days_ago=2)
    check_in(troupe.assistant, troupe, first, agnes)
    award(troupe, first)
    configure(
        troupe,
        bands=[{"up_to": 100, "attended": 6, "absentee": 5}, {"attended": 3, "absentee": 2}],
        cap="off",
    )
    second = game(troupe, timedelta(minutes=-60))
    check_in(troupe.assistant, troupe, second, agnes)
    award(troupe, second)
    assert [amount for _, amount in history(troupe.player, agnes)] == [5, 6]


def test_the_floor_and_ceiling_rise_by_the_figure_for_a_character_at_the_floor(
    troupe: Troupe, session: Session
) -> None:
    configure(troupe, bands=AIT, cap="cap", monthly_xp=8)
    agnes = member_character(troupe, troupe.player, "Agnes")
    earn(session, agnes, 600, last_month=True)
    troupe_record = record(troupe)
    start = xp_range.figures(session, troupe_record)
    assert start.floor == troupe_record.starting_xp
    first = past_game(troupe, session, days_ago=2)
    check_in(troupe.assistant, troupe, first, agnes)
    award(troupe, first)
    # The floor has earned nothing: the first band's 5, whatever Agnes got (1).
    assert xp_range.figures(session, troupe_record).floor - start.floor == 5
    assert night(troupe, first)["xp"]["amount"] == 5
    assert history(troupe.player, agnes) == [("Game: attended, 501+ band", 1)]
    # Capped at 8 this month: the floor's second game this month adds only 3.
    second = game(troupe, timedelta(minutes=-60))
    check_in(troupe.assistant, troupe, second, agnes)
    award(troupe, second)
    assert xp_range.figures(session, troupe_record).floor - start.floor == 8


# --- the monthly cap ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cap", "monthly", "past", "capped", "given"),
    [
        ("warn", None, ["Agnes"], [], 5),
        ("warn", 20, [], [], 5),
        ("cap", None, [], ["Agnes"], 3),
        ("cap", 9, [], ["Agnes"], 2),
        ("off", None, [], [], 5),
    ],
)
def test_the_monthly_cap_warns_caps_or_is_off(
    troupe: Troupe,
    session: Session,
    cap: str,
    monthly: int | None,
    past: list[str],
    capped: list[str],
    given: int,
) -> None:
    configure(troupe, bands=AIT, cap=cap, monthly_xp=monthly)
    agnes = member_character(troupe, troupe.player, "Agnes")
    earn(session, agnes, 7)
    tonight = game(troupe, timedelta(minutes=-60))
    check_in(troupe.assistant, troupe, tonight, agnes)
    assert night(troupe, tonight)["monthly_xp"] == (monthly or 10)

    done = award(troupe, tonight)

    assert (done["past_monthly"], done["capped"], done["total"]) == (past, capped, given)
    reason, amount = history(troupe.player, agnes)[0]
    assert amount == given
    if capped:
        assert reason == (
            f"Game: attended, 0–200 band, {5 - given} held back by the monthly cap of"
            f" {monthly or 10}"
        )
    else:
        assert reason == "Game: attended, 0–200 band"


def test_a_character_at_the_cap_gets_nothing_and_no_entry(troupe: Troupe, session: Session) -> None:
    configure(troupe, cap="cap")
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    earn(session, agnes, 10)
    tonight = game(troupe, timedelta(minutes=-60))
    for c in (agnes, beatrix):
        check_in(troupe.assistant, troupe, tonight, c)
    done = award(troupe, tonight, amount=4)
    assert done == {"characters": 1, "total": 4, "past_monthly": [], "capped": ["Agnes"]}
    assert history(troupe.player, agnes) == []
    given = {
        g["character_name"]: (g["amount"], g["capped"]) for g in night(troupe, tonight)["given"]
    }
    assert given == {"Agnes": (0, 4), "Beatrix": (4, 0)}


# --- absentee games -----------------------------------------------------------------------


def test_an_absentee_game_gets_the_absentee_figure_and_never_counts_as_there(
    troupe: Troupe, session: Session
) -> None:
    configure(troupe, bands=AIT, absentee=True)
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    over = past_game(troupe, session)
    assert check_in(troupe.assistant, troupe, over, agnes).status_code == 200
    marked = mark(troupe.assistant, troupe, over, beatrix)
    assert marked.status_code == 200, marked.text

    seen = night(troupe, over)
    assert [a["character_name"] for a in seen["attendees"]] == ["Agnes"]
    assert [(a["character_name"], a["kind"]) for a in seen["absentees"]] == [
        ("Beatrix", "absentee")
    ]
    assert [(x["character_name"], x["kind"], x["figure"]) for x in seen["xp_lines"]] == [
        ("Agnes", "attended", 5),
        ("Beatrix", "absentee", 4),
    ]
    past = troupe.assistant.client.get(f"/troupes/{troupe.id}/games/past").json()
    assert past[0]["attended"] == 1
    assert troupe.player.client.get(f"/characters/{beatrix}/attendance").json() == []

    award(troupe, over, reason="Game 9 March 2030")
    assert history(troupe.player, agnes) == [("Game 9 March 2030: attended, 0–200 band", 5)]
    assert history(troupe.player, beatrix) == [("Game 9 March 2030: absentee, 0–200 band", 4)]
    kinds = dict(
        session.execute(
            select(GameXpAward.character_id, GameXpAward.kind).where(
                GameXpAward.game_id == uuid.UUID(over)
            )
        ).all()
    )
    assert kinds == {uuid.UUID(agnes): "attended", uuid.UUID(beatrix): "absentee"}


def test_with_no_chart_an_absentee_game_gets_the_absentee_amount(
    troupe: Troupe, session: Session
) -> None:
    configure(troupe, absentee=True)
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    over = past_game(troupe, session)
    check_in(troupe.assistant, troupe, over, agnes)
    mark(troupe.assistant, troupe, over, beatrix)
    missing = troupe.assistant.client.post(
        path(troupe, over, "/xp"), json={"amount": 5, "reason": "Game"}
    )
    assert missing.status_code == 422
    award(troupe, over, amount=5, absentee_amount=3)
    assert history(troupe.player, agnes) == [("Game", 5)]
    assert history(troupe.player, beatrix) == [("Game: absentee", 3)]


def test_who_marks_a_character_absentee_and_when(troupe: Troupe, session: Session) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    vera = member(troupe, troupe.player, "Vera", "Toreador")
    over = past_game(troupe, session)
    # Not while the troupe doesn't record them.
    assert mark(troupe.assistant, troupe, over, agnes).status_code == 409
    configure(troupe, absentee=True)
    # Its player, only where the troupe lets players.
    assert mark(troupe.player, troupe, over, agnes).status_code == 403
    assert troupe.player.client.get(f"/troupes/{troupe.id}/games/missed").json() == []
    configure(troupe, absentee=True, absentee_by_players=True)
    missed = troupe.player.client.get(f"/troupes/{troupe.id}/games/missed").json()
    assert [(g["game_id"], [c["name"] for c in g["characters"]]) for g in missed] == [
        (over, ["Agnes", "Beatrix"])
    ]
    assert mark(troupe.player, troupe, over, agnes).status_code == 200
    assert mark(troupe.player, troupe, over, agnes).status_code == 200
    missed = troupe.player.client.get(f"/troupes/{troupe.id}/games/missed").json()
    assert missed[0]["absentee"] == [agnes]
    assert mark(troupe.stranger, troupe, over, beatrix).status_code == 403
    # A visitor's home troupe awards it, so it isn't absentee here.
    assert mark(troupe.assistant, troupe, over, vera).status_code == 404
    # Not before the game starts.
    later = game(troupe, timedelta(days=3))
    assert mark(troupe.assistant, troupe, later, beatrix).status_code == 422
    # A character that checked in came.
    assert check_in(troupe.assistant, troupe, over, beatrix).status_code == 200
    assert mark(troupe.assistant, troupe, over, beatrix).status_code == 409
    # Checking an absentee in puts it right: it came after all.
    assert check_in(troupe.assistant, troupe, over, agnes).status_code == 200
    assert [a["character_name"] for a in night(troupe, over)["attendees"]] == ["Agnes", "Beatrix"]
    assert mark(troupe.player, troupe, over, agnes).status_code == 409
    # Taking one back.
    another = past_game(troupe, session, days_ago=1)
    mark(troupe.player, troupe, another, agnes)
    taken = troupe.player.client.delete(path(troupe, another, f"/absentee/{agnes}"))
    assert taken.status_code == 200, taken.text
    assert night(troupe, another)["absentees"] == []
    # Settled once the game's XP is awarded.
    mark(troupe.player, troupe, another, agnes)
    award(troupe, another, absentee_amount=4)
    assert mark(troupe.player, troupe, another, beatrix).status_code == 409
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert any("marked Agnes absentee for the game on" in m for m in log), log
    assert any("took back Agnes's absentee game on" in m for m in log), log


def test_an_absentee_game_isnt_counted_as_checked_in_on_the_games_list(
    troupe: Troupe,
) -> None:
    configure(troupe, absentee=True)
    agnes = member_character(troupe, troupe.player, "Agnes")
    tonight = game(troupe, timedelta(minutes=-60))
    assert mark(troupe.assistant, troupe, tonight, agnes).status_code == 200
    listed = troupe.player.client.get(f"/troupes/{troupe.id}/games").json()
    assert (listed[0]["checked_in"], listed[0]["my_checked_in"]) == (0, [])


# --- absentee downtimes -------------------------------------------------------------------


def submit(person: Person, character_id: str) -> Any:
    return person.client.post(f"/characters/{character_id}/downtime/submit")


def test_an_absentee_downtime_needs_a_game_attended_within_the_lookback(
    troupe: Troupe, session: Session
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    cecily = member_character(troupe, troupe.player, "Cecily")
    dora = member_character(troupe, troupe.player, "Dora")
    configure(troupe, absentee=True, absentee_downtime=True, absentee_lookback_days=60)
    # Agnes came 30 days ago; Beatrix 90 days ago; Cecily was only absentee; Dora never came.
    recent = past_game(troupe, session, days_ago=30)
    old = past_game(troupe, session, days_ago=90)
    check_in(troupe.assistant, troupe, recent, agnes)
    check_in(troupe.assistant, troupe, old, beatrix)
    assert mark(troupe.assistant, troupe, recent, cecily).status_code == 200
    cycle = open_cycle(troupe, new_cycle(troupe))

    assert my_downtime(troupe.player, agnes).json()["closed"] is None
    assert submit(troupe.player, agnes).status_code == 200
    for name, character_id in (("Beatrix", beatrix), ("Cecily", cecily), ("Dora", dora)):
        closed = my_downtime(troupe.player, character_id).json()["closed"]
        assert closed.startswith(f"{name} hasn't attended a game in the 60 days"), closed
        refused = submit(troupe.player, character_id)
        assert refused.status_code == 409
        assert "An absentee game doesn't count" in refused.json()["detail"]
    # A longer lookback reaches Beatrix's game.
    configure(troupe, absentee=True, absentee_downtime=True, absentee_lookback_days=120)
    assert submit(troupe.player, beatrix).status_code == 200
    # A storyteller lets Dora in with Accept late.
    participants = troupe.assistant.client.get(f"/cycles/{cycle['id']}/participants").json()
    dora_part = next(p for p in participants if p["character_name"] == "Dora")
    accepted = troupe.storyteller.client.post(
        f"/cycles/{cycle['id']}/participants/{dora_part['id']}/accept-late"
    )
    assert accepted.status_code < 300, accepted.text
    assert submit(troupe.player, dora).status_code == 200
    # Without absentee downtimes, the downtime is open to everyone as before.
    configure(troupe, absentee=True)
    assert my_downtime(troupe.player, cecily).json()["closed"] is None
    assert submit(troupe.player, cecily).status_code == 200


# --- adjustments and figures set by hand --------------------------------------------------


def test_adjustments_are_ticked_and_kept_to_their_monthly_limits(
    troupe: Troupe, session: Session
) -> None:
    saved = configure(
        troupe,
        bands=AIT,
        adjustments=[
            {"name": "Helped", "amount": 1, "per_month": 1},
            {"name": "Not findable", "amount": -1},
        ],
        cap="off",
    )
    helped, unfindable = (a["key"] for a in saved["adjustments"])
    agnes = member_character(troupe, troupe.player, "Agnes")
    first = past_game(troupe, session, days_ago=2)
    check_in(troupe.assistant, troupe, first, agnes)
    unknown = troupe.assistant.client.post(
        path(troupe, first, "/xp"),
        json={
            "amount": 8,
            "reason": "Game",
            "characters": [{"character_id": agnes, "ticks": ["nonsense"]}],
        },
    )
    assert unknown.status_code == 422
    award(troupe, first, characters=[{"character_id": agnes, "ticks": [helped, unfindable]}])
    assert history(troupe.player, agnes) == [
        ("Game: attended, 0–200 band, Helped +1, Not findable −1", 5)
    ]

    second = game(troupe, timedelta(minutes=-60))
    check_in(troupe.assistant, troupe, second, agnes)
    assert night(troupe, second)["xp_lines"][0]["used"] == {helped: 1, unfindable: 1}
    again = troupe.assistant.client.post(
        path(troupe, second, "/xp"),
        json={
            "amount": 8,
            "reason": "Game",
            "characters": [{"character_id": agnes, "ticks": [helped]}],
        },
    )
    assert again.status_code == 422
    assert again.json()["detail"] == "Agnes has had Helped this month, its limit."
    # Not findable has no limit.
    award(troupe, second, characters=[{"character_id": agnes, "ticks": [unfindable]}])
    assert history(troupe.player, agnes)[-1] == ("Game: attended, 0–200 band, Not findable −1", 4)
    given = night(troupe, second)["given"][0]
    assert given["adjustments"] == ["Not findable −1"]


def test_staff_set_a_figure_by_hand_with_a_reason(troupe: Troupe, session: Session) -> None:
    configure(troupe, bands=AIT, cap="cap")
    agnes = member_character(troupe, troupe.player, "Agnes")
    beatrix = member_character(troupe, troupe.player, "Beatrix")
    earn(session, beatrix, 9)
    tonight = game(troupe, timedelta(minutes=-60))
    for c in (agnes, beatrix):
        check_in(troupe.assistant, troupe, tonight, c)
    no_reason = troupe.assistant.client.post(
        path(troupe, tonight, "/xp"),
        json={
            "amount": 8,
            "reason": "Game",
            "characters": [{"character_id": agnes, "override": 2}],
        },
    )
    assert no_reason.status_code == 422
    stranger = troupe.assistant.client.post(
        path(troupe, tonight, "/xp"),
        json={
            "amount": 8,
            "reason": "Game",
            "characters": [{"character_id": str(uuid.uuid4()), "override": 2}],
        },
    )
    assert stranger.status_code == 422

    done = award(
        troupe,
        tonight,
        characters=[
            {"character_id": agnes, "override": 2, "override_reason": "Left early"},
            # Set by hand, the cap doesn't hold it back.
            {"character_id": beatrix, "override": 5, "override_reason": "Ran a scene"},
        ],
    )
    assert done["total"] == 7
    assert history(troupe.player, agnes) == [
        ("Game: attended, 0–200 band; set by hand to 2: Left early", 2)
    ]
    assert history(troupe.player, beatrix) == [
        ("Game: attended, 0–200 band; set by hand to 5: Ran a scene", 5)
    ]
    given = {g["character_name"]: g for g in night(troupe, tonight)["given"]}
    assert (given["Agnes"]["figure"], given["Agnes"]["override"]) == (5, 2)
    assert given["Agnes"]["override_reason"] == "Left early"

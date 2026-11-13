"""The Vinculum and the Vaulderie log (#666; MET: VTM pp. 433-435, and the Errata's p.
434): ratings from the nights shared, once a night, a false Sabbat's one-way rating,
the errata's lowering of blood bonds, background ties, players' reports, who sees what,
and nothing at all outside a Sabbat troupe that tracks bonds."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.vinculum import rating_of, tie_nights
from tests.api_helpers import Person, Troupe
from tests.test_api_bonds import Scene, named


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


DAY = date(2026, 6, 1)


def every(days: int, count: int, last: date = DAY) -> list[date]:
    return [last - timedelta(days=days * i) for i in range(count)]


# --- ratings, from the nights shared --------------------------------------------------------


def test_the_first_vaulderie_gives_1_and_it_is_permanent() -> None:
    assert rating_of([], DAY) == 0
    assert rating_of([DAY], DAY) == 1
    assert rating_of([DAY], DAY + timedelta(days=3650)) == 1


def test_more_than_once_in_the_past_year_gives_2_which_returns_to_1_after_a_year() -> None:
    nights = [DAY - timedelta(days=1), DAY]
    assert rating_of(nights, DAY) == 2
    assert rating_of(nights, DAY + timedelta(days=360)) == 2
    assert rating_of(nights, DAY + timedelta(days=366)) == 1


def test_more_than_10_in_the_past_year_gives_3() -> None:
    assert rating_of(every(30, 10), DAY) == 2
    assert rating_of(every(30, 11), DAY) == 3


def test_about_weekly_for_three_months_gives_4_missing_at_most_two_weeks() -> None:
    assert rating_of(every(7, 14), DAY) == 4
    # Missing two weeks in a row still counts; missing three doesn't.
    assert rating_of(every(21, 5), DAY) == 4
    assert rating_of(every(22, 5), DAY) == 2
    # Weekly, but only for the last month: not three months of it.
    assert rating_of(every(7, 5), DAY) == 2


def test_every_few_days_for_three_months_gives_5() -> None:
    assert rating_of(every(3, 32), DAY) == 5
    assert rating_of(every(5, 20), DAY) == 4


def test_a_background_tie_thins_with_time_as_the_book_says() -> None:
    # p. 435: a 4 long ago, three months apart, has slipped to a 3.
    for rating in range(1, 6):
        assert rating_of(tie_nights(rating, DAY), DAY) == rating
    assert rating_of(tie_nights(4, DAY), DAY + timedelta(days=95)) == 3


# --- the Vaulderie log ---------------------------------------------------------------------


def vaulderie(scene: Scene, *people: Any, night: str = "2026-10-03", by: Person | None = None):
    return (by or scene.troupe.storyteller).client.post(
        f"/troupes/{scene.troupe.id}/vaulderies",
        json={
            "night": night,
            "participants": [p if isinstance(p, dict) else {"character_id": p} for p in people],
            "source": "game",
        },
    )


def vinculum(scene: Scene, by: Person | None = None) -> dict[str, Any]:
    found = (by or scene.troupe.storyteller).client.get(f"/troupes/{scene.troupe.id}/vinculum")
    assert found.status_code == 200, found.text
    return found.json()


def ratings(scene: Scene, character_id: str, by: Person) -> dict[str, int]:
    found = by.client.get(f"/characters/{character_id}/vinculum")
    assert found.status_code == 200, found.text
    return {r["name"]: r["rating"] for r in found.json()["ratings"]}


def test_staff_record_a_vaulderie_and_both_feel_the_same_rating(scene: Scene) -> None:
    made = vaulderie(scene, scene.agnes, scene.bram, named("Ezra"))
    assert made.status_code == 201, made.text
    assert made.json()["status"] == "recorded"
    assert ratings(scene, scene.agnes, scene.troupe.player) == {"Bram": 1, "Ezra": 1}
    assert ratings(scene, scene.bram, scene.other) == {"Agnes": 1, "Ezra": 1}
    shown = vinculum(scene)
    assert len(shown["vaulderies"]) == 1
    assert {(r["felt_by"], r["toward"], r["rating"]) for r in shown["ratings"]} >= {
        (scene.agnes, scene.bram, 1),
        (scene.bram, scene.agnes, 1),
    }
    assert any("recorded a Vaulderie" in m for m in scene.messages())


def test_two_vaulderies_on_one_night_raise_it_once(scene: Scene) -> None:
    assert vaulderie(scene, scene.agnes, scene.bram).status_code == 201
    assert vaulderie(scene, scene.agnes, scene.bram).status_code == 201
    assert ratings(scene, scene.agnes, scene.troupe.player) == {"Bram": 1}
    assert vaulderie(scene, scene.agnes, scene.bram, night="2026-10-10").status_code == 201
    assert ratings(scene, scene.agnes, scene.troupe.player) == {"Bram": 2}


def test_a_false_sabbat_gains_a_rating_the_others_dont_return(scene: Scene) -> None:
    made = vaulderie(scene, {"character_id": scene.agnes, "false_sabbat": True}, scene.bram)
    assert made.status_code == 201, made.text
    assert ratings(scene, scene.agnes, scene.troupe.player) == {"Bram": 1}
    assert ratings(scene, scene.bram, scene.other) == {}


def test_a_vaulderie_lowers_its_participants_bonds_a_step_once_a_night(scene: Scene) -> None:
    scene.drunk(scene.agnes, scene.vidal, "2026-09-01", "2026-09-08")
    assert vaulderie(scene, scene.agnes, scene.bram).status_code == 201
    bond = next(b for b in scene.bonds() if b["regnant"]["name"] == "Vidal")
    assert (bond["level"], bond["status"]) == (1, "active")
    assert bond["entries"][-1]["kind"] == "vaulderie"
    # A second Vaulderie that night lowers nothing more.
    assert vaulderie(scene, scene.agnes, scene.bram).status_code == 201
    bond = next(b for b in scene.bonds() if b["regnant"]["name"] == "Vidal")
    assert (bond["level"], bond["status"]) == (1, "active")
    # The next night's takes the last drink away: the bond ends.
    assert vaulderie(scene, scene.agnes, scene.bram, night="2026-10-04").status_code == 201
    bond = next(b for b in scene.bonds() if b["regnant"]["name"] == "Vidal")
    assert bond["status"] == "ended"
    # Its thrall took part, so their player sees it at once: no bond left on the card.
    assert scene.card(scene.agnes, scene.troupe.player).json()["bound_to"] == []
    assert any("lowered to one drink by the Vaulderie" in m for m in scene.messages())


def test_taking_a_vaulderie_out_stops_it_counting(scene: Scene) -> None:
    made = vaulderie(scene, scene.agnes, scene.bram).json()
    taken = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/vaulderies/{made['id']}/remove",
        json={"reason": "Entered twice"},
    )
    assert taken.status_code == 200, taken.text
    assert taken.json()["status"] == "removed"
    assert ratings(scene, scene.agnes, scene.troupe.player) == {}


def test_a_vaulderie_needs_two_who_gave_blood_and_vampires_only(scene: Scene) -> None:
    assert vaulderie(scene, scene.agnes).status_code == 422
    assert vaulderie(scene, scene.agnes, scene.agnes).status_code == 422
    assert vaulderie(scene, scene.agnes, scene.ghislaine).status_code == 422
    both_false = vaulderie(
        scene,
        {"character_id": scene.agnes, "false_sabbat": True},
        {"character_id": scene.bram, "false_sabbat": True},
    )
    assert both_false.status_code == 422


def test_staff_enter_a_background_tie(scene: Scene) -> None:
    today = date.today()
    tied = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/vinculum/ties",
        json={
            "one": {"character_id": scene.agnes},
            "other": {"character_id": scene.bram},
            "rating": 4,
            "night": today.isoformat(),
            "reason": "Old packmates",
        },
    )
    assert tied.status_code == 201, tied.text
    assert ratings(scene, scene.agnes, scene.troupe.player) == {"Bram": 4}
    assert ratings(scene, scene.bram, scene.other) == {"Agnes": 4}
    removed = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/vinculum/ties/{tied.json()['id']}/remove",
        json={"reason": "A mistake"},
    )
    assert removed.status_code == 200, removed.text
    assert ratings(scene, scene.agnes, scene.troupe.player) == {}


# --- who sees it ---------------------------------------------------------------------------


def test_only_the_two_and_staff_see_a_rating(scene: Scene) -> None:
    assert vaulderie(scene, scene.agnes, scene.bram).status_code == 201
    assert ratings(scene, scene.agnes, scene.troupe.storyteller) == {"Bram": 1}
    seen = scene.third.client.get(f"/characters/{scene.agnes}/vinculum")
    assert seen.status_code != 200 or seen.json()["ratings"] == []
    assert scene.troupe.player.client.get(f"/troupes/{scene.troupe.id}/vinculum").status_code == 403


def test_the_play_view_shows_what_a_rating_of_2_costs(scene: Scene) -> None:
    for night in ("2026-10-03", "2026-10-10"):
        assert vaulderie(scene, scene.agnes, scene.bram, night=night).status_code == 201
    reference = scene.troupe.player.client.get(f"/characters/{scene.agnes}/play/reference")
    assert reference.status_code == 200, reference.text
    lines = reference.json()["vinculum"]
    assert [(v["toward"], v["rating"]) for v in lines] == [("Bram", 2)]
    assert lines[0]["effects"] == ["Killing Bram costs 1 Willpower (p. 434)."]


@pytest.mark.parametrize("how", ["camarilla", "off"])
def test_nothing_outside_a_sabbat_troupe_that_tracks_bonds(scene: Scene, how: str) -> None:
    assert vaulderie(scene, scene.agnes, scene.bram).status_code == 201
    if how == "camarilla":
        limited = scene.troupe.lead.client.patch(
            f"/troupes/{scene.troupe.id}", json={"allowed_sects": ["Camarilla"]}
        )
        assert limited.status_code == 200, limited.text
    else:
        assert scene.set("off").status_code == 200
    assert (
        scene.troupe.storyteller.client.get(f"/troupes/{scene.troupe.id}/vinculum").status_code
        == 404
    )
    assert vaulderie(scene, scene.agnes, scene.bram).status_code == 404
    assert ratings(scene, scene.agnes, scene.troupe.player) == {}
    reference = scene.troupe.player.client.get(f"/characters/{scene.agnes}/play/reference")
    assert reference.json()["vinculum"] == []


# --- players' reports ----------------------------------------------------------------------


def report(scene: Scene, **body: Any) -> Any:
    return scene.troupe.player.client.post(
        f"/characters/{scene.agnes}/vaulderies",
        json={
            "troupe_id": scene.troupe.id,
            "night": date.today().isoformat(),
            "others": [{"character_id": scene.bram}],
            "source": "game",
            **body,
        },
    )


@pytest.mark.parametrize("mode", ["players_report", "players_manage"])
def test_a_player_reports_a_vaulderie_and_it_waits_for_staff(scene: Scene, mode: str) -> None:
    assert scene.set(mode).status_code == 200
    made = report(scene)
    assert made.status_code == 201, made.text
    assert made.json()["status"] == "pending"
    assert ratings(scene, scene.agnes, scene.troupe.player) == {}
    shown = vinculum(scene)
    assert shown["vaulderies"][0]["status"] == "pending"
    decided = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/vaulderies/{made.json()['id']}/decide",
        json={"approve": True},
    )
    assert decided.status_code == 200, decided.text
    assert ratings(scene, scene.agnes, scene.troupe.player) == {"Bram": 1}


def test_a_declined_vaulderie_never_counts_and_the_player_sees_why(scene: Scene) -> None:
    assert scene.set("players_report").status_code == 200
    made = report(scene).json()
    declined = scene.troupe.storyteller.client.post(
        f"/troupes/{scene.troupe.id}/vaulderies/{made['id']}/decide",
        json={"approve": False, "reason": "Bram wasn't there"},
    )
    assert declined.status_code == 200, declined.text
    card = scene.troupe.player.client.get(f"/characters/{scene.agnes}/vinculum").json()
    assert card["ratings"] == []
    assert [(r["status"], r["reason"]) for r in card["reports"]] == [
        ("declined", "Bram wasn't there")
    ]


def test_players_name_only_player_characters_and_cant_report_under_staff_mode(
    scene: Scene,
) -> None:
    assert report(scene).status_code == 409
    assert scene.set("players_report").status_code == 200
    assert report(scene, others=[{"character_id": scene.vidal}]).status_code == 422
    assert report(scene, others=[{"name": "Vidal"}]).status_code == 201

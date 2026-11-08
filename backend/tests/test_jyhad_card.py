"""A character's Jyhad card (issue #537): its capacity, disciplines and title line,
pinned on a handful of characters so the choice stays explainable, and the API's
who-may-read and who-may-write."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import vtes_symbols
from horatio.jyhad_card import (
    AVERAGE_POINTS,
    BANDS,
    Discipline,
    capacity,
    nearest,
    on_card,
    points,
    title_line,
)
from horatio.models import Character
from horatio.models import Troupe as TroupeRecord
from tests.api_helpers import Troupe, new_character
from tests.test_api_badges import give
from tests.test_api_sect_status import entitle, npc
from tests.test_api_sect_status import member as home_member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def card_points(*dots: int) -> int:
    return points(on_card((f"D{i}", n) for i, n in enumerate(dots)))


# --- capacity ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("who", "generation", "dots", "extra", "expected"),
    [
        # A new neonate's three disciplines, all inferior: 3 points, capacity 4's average.
        ("new neonate, 2/1/1", 1, (2, 1, 1), {}, 4),
        ("neonate with one discipline", 1, (1,), {}, 1),
        ("neonate, two disciplines", 1, (1, 1), {}, 3),
        # Lesser Generation 2 takes it down two.
        ("13th-generation neonate, 2/1/1", 1, (2, 1, 1), {"lesser_generation": 2}, 2),
        # ...never below the band's bottom.
        ("12th-generation neonate, 1", 1, (1,), {"lesser_generation": 1}, 1),
        ("Thin Blooded, whatever it has", 1, (3, 2, 2), {"thin_blooded": True}, 1),
        # One superior: 5 points, capacity 5's 4.7.
        ("ancilla, 4/3/2/1", 2, (4, 3, 2, 1), {}, 5),
        # Twice the troupe's starting XP earned in play moves it up one.
        ("ancilla played a year, 4/3/2/1", 2, (4, 3, 2, 1), {"earned_xp": 60}, 6),
        ("ancilla played a while, 4/3/2/1", 2, (4, 3, 2, 1), {"earned_xp": 59}, 5),
        ("ancilla, 2/2/1, Lesser Generation 1", 2, (2, 2, 1), {"lesser_generation": 1}, 4),
        ("pretender elder, 5/4/3/2/1", 3, (5, 4, 3, 2, 1), {}, 7),
        ("pretender elder, 3/2/1", 3, (3, 2, 1), {}, 6),
        ("master elder, 5/5/4/3/3/2", 4, (5, 5, 4, 3, 3, 2), {}, 8),
        # The band's top already: experience can't take it higher.
        ("master elder played long", 4, (5, 5, 4, 3, 3, 2), {"earned_xp": 500}, 8),
        ("luminary elder, 3/3/3", 5, (3, 3, 3), {}, 8),
        ("luminary elder, 5/5/5/5/4/4", 5, (5, 5, 5, 5, 4, 4), {}, 9),
        # No Generation dots is a neonate.
        ("no Generation, 2/1/1", 0, (2, 1, 1), {}, 4),
    ],
)
def test_capacity_of_example_characters(
    who: str, generation: int, dots: tuple[int, ...], extra: dict[str, Any], expected: int
) -> None:
    assert capacity(generation, card_points(*dots), **extra) == expected, who


def test_every_band_is_in_the_averages_and_they_overlap() -> None:
    assert set(range(1, 12)) == set(AVERAGE_POINTS)
    lows = [BANDS[g][0] for g in sorted(BANDS)]
    highs = [BANDS[g][1] for g in sorted(BANDS)]
    assert lows == [1, 4, 6, 7, 8] and highs == [4, 6, 7, 8, 9]


def test_nearest_stays_in_the_band() -> None:
    assert nearest(0, 1, 4) == 1
    assert nearest(12, 1, 4) == 4
    assert nearest(0, 8, 9) == 8


def test_xp_against_the_troupes_own_starting_xp() -> None:
    assert capacity(2, 5, earned_xp=100, starting_xp=50) == 6
    assert capacity(2, 5, earned_xp=99, starting_xp=50) == 5
    # A troupe starting at nothing doesn't move everyone up.
    assert capacity(2, 5, earned_xp=0, starting_xp=0) == 5


# --- disciplines ---------------------------------------------------------------------------


def test_superior_from_four_dots() -> None:
    assert [Discipline("Auspex", n).superior for n in range(1, 6)] == [
        False,
        False,
        False,
        True,
        True,
    ]


def test_paths_count_as_their_discipline_at_the_highest() -> None:
    shown = on_card(
        [
            ("Auspex", 2),
            ("Thaumaturgy: Path of Blood", 4),
            ("Thaumaturgy: Lure of Flames", 2),
            ("Dominate", 0),
        ]
    )
    assert [(d.name, d.dots, d.superior) for d in shown] == [
        ("Thaumaturgy", 4, True),
        ("Auspex", 2, False),
    ]


def test_at_most_six_highest_first_ties_in_sheet_order() -> None:
    held = [("A", 1), ("B", 3), ("C", 1), ("D", 3), ("E", 2), ("F", 1), ("G", 5)]
    assert [d.name for d in on_card(held)] == ["G", "B", "D", "E", "A", "C"]


# --- title and votes -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sect", "held", "city", "expected"),
    [
        ("Camarilla", ["Prince"], "Asheville", "Camarilla Prince of Asheville: 2 votes"),
        ("Camarilla", ["Harpy", "Primogen"], "", "Camarilla Primogen: 1 vote"),
        ("Camarilla", ["Justicar"], "Asheville", "Camarilla Justicar: 3 votes"),
        ("Camarilla", ["Primogen", "Inner Circle"], "", "Camarilla Inner Circle: 4 votes"),
        ("Sabbat", ["Bishop", "Priscus"], "Leeds", "Sabbat Priscus: 3 votes"),
        ("Sabbat", ["Archbishop"], "Leeds", "Sabbat Archbishop of Leeds: 2 votes"),
        ("Anarch", ["Advocate"], "Leeds", "Anarch Advocate of Leeds: 2 votes"),
        ("Sabbat", ["Ductus"], "Leeds", "Sabbat"),
        (None, ["Prince"], "", "Prince: 2 votes"),
        (None, [], "", None),
    ],
)
def test_title_line(sect: str | None, held: list[str], city: str, expected: str | None) -> None:
    assert title_line(sect, held, city) == expected


# --- the API -------------------------------------------------------------------------------


def with_picture(troupe: Troupe, character_id: str) -> None:
    troupe.session.get_one(Character, uuid.UUID(character_id)).picture_id = uuid.uuid4()
    troupe.session.flush()


def card_of(person: Any, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/jyhad-card")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_prince_s_card(troupe: Troupe) -> None:
    varga = home_member(troupe, "Varga", clan="Tremere")
    give(
        troupe,
        varga,
        ("backgrounds", "Generation", 3, ""),
        ("disciplines", "Auspex", 5, ""),
        ("disciplines", "Dominate", 3, ""),
        ("disciplines", "Thaumaturgy: Path of Blood", 4, ""),
        ("disciplines", "Thaumaturgy: Lure of Flames", 2, ""),
        ("disciplines", "Celerity", 1, ""),
    )
    entitle(troupe, varga, "Prince")
    record = troupe.session.get_one(TroupeRecord, uuid.UUID(troupe.id))
    record.profile = {"setting": {"city": "Asheville"}}
    troupe.session.flush()

    assert card_of(troupe.player, varga)["missing"] == "A Jyhad card needs the character's picture."
    with_picture(troupe, varga)
    card = card_of(troupe.player, varga)

    assert card["missing"] is None
    assert (card["name"], card["clan"]) == ("Varga", "Tremere")
    assert card["sect_line"] == "Camarilla Prince of Asheville: 2 votes"
    assert [(d["name"], d["superior"], d["abbreviation"]) for d in card["disciplines"]] == [
        ("Auspex", True, "aus"),
        ("Thaumaturgy", True, "tha"),
        ("Dominate", False, "dom"),
        ("Celerity", False, "cel"),
    ]
    # 2 + 2 + 1 + 1 = 6 points in Pretender Elder's 6-7: capacity 6's 5.5 is nearest.
    assert card["capacity"] == 6
    # No VTES symbols on the server: the card shows the three letters.
    assert card["clan_symbol"] is None
    assert all(d["symbol"] is None for d in card["disciplines"])
    assert card["capacity_symbol"] is None
    assert card["sect"] == "Camarilla"
    assert card["picture"].startswith(f"/api/characters/{varga}/pictures/")
    assert (card["text"], card["flavour"], card["can_write"]) == ("", "", True)
    # Staff see it; they don't write a player's card.
    assert card_of(troupe.lead, varga)["can_write"] is False
    assert troupe.stranger.client.get(f"/characters/{varga}/jyhad-card").status_code == 404


def test_symbols_show_once_fetched(troupe: Troupe, monkeypatch: pytest.MonkeyPatch) -> None:
    agnes = new_character(troupe, troupe.player, "Agnes", clan="Brujah: True Brujah")
    give(troupe, agnes, ("disciplines", "Potence", 4, ""), ("disciplines", "Presence", 1, ""))
    with_picture(troupe, agnes)
    record = {
        "files": {
            f"{kind}/{group}": names
            for kind in vtes_symbols.KINDS
            for group, names in (
                ("clan", ["truebrujah"]),
                ("disc/inf", ["pre"]),
                ("disc/sup", ["pot"]),
            )
        }
        # KRCG's capacity drop is WebP and PNG only.
        | {f"{kind}/icon": ["capacity"] for kind in ("webp", "png")}
    }
    monkeypatch.setattr(vtes_symbols, "manifest", lambda: record)

    card = card_of(troupe.player, agnes)

    assert card["clan_symbol"] == "/api/vtes-symbols/svg/clan/truebrujah.svg"
    assert [d["symbol"] for d in card["disciplines"]] == [
        "/api/vtes-symbols/svg/disc/sup/pot.svg",
        "/api/vtes-symbols/svg/disc/inf/pre.svg",
    ]
    assert card["capacity_symbol"] == "/api/vtes-symbols/webp/icon/capacity.webp"
    # A neonate with 3 points (one superior): capacity 4's 3.0 is nearest.
    assert card["capacity"] == 4


@pytest.mark.usefixtures("ghoul_rules")
def test_only_a_vampire_has_a_card(troupe: Troupe) -> None:
    domitor = {"name": "Lady Vasquez", "clan": "Toreador"}
    made = troupe.player.client.post(
        "/characters", json={"splat": "ghoul", "name": "Renfield", "domitor": domitor}
    )
    assert made.status_code == 201, made.text
    renfield = made.json()["id"]
    with_picture(troupe, renfield)
    card = card_of(troupe.player, renfield)
    assert card["missing"] == "Only a vampire has a Jyhad card."
    assert (card["capacity"], card["disciplines"]) == (None, [])


def test_thin_blooded_and_lesser_generation(troupe: Troupe) -> None:
    thin = new_character(troupe, troupe.player, "Thin", clan="Caitiff")
    lesser = new_character(troupe, troupe.player, "Lesser", clan="Toreador")
    for who in (thin, lesser):
        with_picture(troupe, who)
        give(
            troupe,
            who,
            ("disciplines", "Auspex", 2, ""),
            ("disciplines", "Celerity", 1, ""),
            ("disciplines", "Presence", 1, ""),
        )
    give(troupe, thin, ("flaws", "Thin Blooded", None, ""))
    give(troupe, lesser, ("flaws", "Lesser Generation 2", None, ""))
    assert card_of(troupe.player, thin)["capacity"] == 1
    assert card_of(troupe.player, lesser)["capacity"] == 2


def test_who_writes_the_card_text(troupe: Troupe) -> None:
    agnes = home_member(troupe, "Agnes")
    url = f"/characters/{agnes}/jyhad-card/text"
    body = {"text": "  +1 bleed.\n Agnes may  hunt twice. ", "flavour": "The night is young."}

    assert troupe.lead.client.put(url, json=body).status_code == 403
    assert troupe.stranger.client.put(url, json=body).status_code == 404
    written = troupe.player.client.put(url, json=body)
    assert written.status_code == 200, written.text
    assert (written.json()["text"], written.json()["flavour"]) == (
        "+1 bleed. Agnes may hunt twice.",
        "The night is young.",
    )
    assert card_of(troupe.lead, agnes)["text"] == "+1 bleed. Agnes may hunt twice."
    too_long = troupe.player.client.put(url, json={"text": "x" * 301, "flavour": ""})
    assert too_long.status_code == 422

    # An NPC's card is its storytellers' to write.
    lucien = npc(troupe, "Lucien", "Camarilla")
    npc_url = f"/characters/{lucien}/jyhad-card/text"
    assert troupe.player.client.put(npc_url, json=body).status_code == 404
    assert troupe.storyteller.client.put(npc_url, json=body).status_code == 200
    assert card_of(troupe.assistant, lucien)["can_write"] is True

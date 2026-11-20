"""Searching everything from the top bar (#1046): for the same word, what a player, the
troupe's Harpy, its staff, a narrator, the lead storyteller of another troupe and the
custodian each find, kind by kind. Nothing shows that its page would refuse them, and
never an email."""

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from horatio.models import User
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_boon_standings import at_home
from tests.test_api_boons import named, row
from tests.test_api_quests import MEDICINE, quests_on, requirement
from tests.test_api_troupe_equipment import DAGGER, given


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


class Court:
    """A troupe keeping a boon ledger and running quests, full of ravens.

    - Ravenna is the player's, at home; Corvin and Ravenscroft are Keeper's (a player
      whose name is Raven Keeper); Hestia, the Harpy, is a fourth player's.
    - The Raven Mocker is an NPC with no title, so not on the Who's Who.
    - Boons: Ravenna owes Corvin (the player sees it: players see what they owe); Lady
      Raven owes Lord Crow, names only (they don't).
    - Raven's Rest is Ravenna's; Ravenwood Hall nobody's.
    - The Raven's errand is sent to Ravenna; Raven hunt is still being built.
    - Ravenna holds a Raven-headed cane; Corvin a Raven feather.
    - News: Ravens over the harbour, published. An announcement, Raven drill, in draft.
    - Another troupe, the Other Court, has its own NPC, Raven Two.
    """

    def __init__(self, troupe: Troupe, session: Session) -> None:
        self.troupe = troupe
        t = troupe.id
        st = troupe.storyteller.client
        self.keeper = sign_up(troupe.client_for, "ravenkeeper")
        self.harpy_player = sign_up(troupe.client_for, "harpy-1046")
        # Someone whose email alone has the word in it.
        self.mail = sign_up(troupe.client_for, "ravenmail")
        mail = session.get_one(User, uuid.UUID(self.mail.id))
        mail.display_name, mail.handle = "Mail Person", "mailperson"
        session.flush()

        self.ravenna = at_home(troupe, troupe.player, "Ravenna", "Toreador")
        self.corvin = at_home(troupe, self.keeper, "Corvin", "Brujah")
        self.ravenscroft = at_home(troupe, self.keeper, "Ravenscroft", "Ventrue")
        self.hestia = at_home(troupe, self.harpy_player, "Hestia", "Toreador")
        at_home(troupe, self.mail, "Postbox", "Brujah")
        self.mocker = ok(
            troupe.lead.client.post(f"/troupes/{t}/npcs", json={"name": "Raven Mocker"}), 201
        )["id"]

        ok(st.put(f"/troupes/{t}/boon-ledger", json={"on": True}))
        ok(st.put(f"/troupes/{t}/boon-harpy", json={"access": "full"}))
        ok(st.put(f"/troupes/{t}/boon-players", json={"see": "owes", "settle": False}))
        ok(st.put(f"/troupes/{t}/characters/{self.hestia}/titles", json={"titles": ["Harpy"]}))
        self.owed, self.names_only = ok(
            st.post(
                f"/troupes/{t}/boons",
                json={
                    "boons": [
                        row(self.ravenna, self.corvin, reason="Passage"),
                        row(named("Lady Raven"), named("Lord Crow"), reason="A word"),
                    ],
                    "note": "",
                },
            ),
            201,
        )

        locations = f"/troupes/{t}/locations"
        place = {"kind": "standard", "rating": 1}
        ok(
            st.post(
                locations,
                json={
                    "name": "Raven's Rest",
                    "control": "character",
                    "controller_id": self.ravenna,
                    **place,
                },
            ),
            201,
        )
        ok(st.post(locations, json={"name": "Ravenwood Hall", **place}), 201)

        quests_on(troupe)
        errand = ok(
            st.post(
                f"/troupes/{t}/quests",
                json={"name": "The Raven's errand", "leader_id": self.ravenna},
            ),
            201,
        )
        requirement(troupe, errand["id"], MEDICINE)
        ok(st.post(f"/quests/{errand['id']}/send"))
        ok(
            st.post(f"/troupes/{t}/quests", json={"name": "Raven hunt", "leader_id": self.ravenna}),
            201,
        )

        given(troupe, self.ravenna, **{**DAGGER, "name": "Raven-headed cane"})
        given(troupe, self.corvin, **{**DAGGER, "name": "Raven feather"})

        agency = ok(st.post(f"/troupes/{t}/agencies", json={"name": "The Herald"}), 201)["id"]
        story = ok(
            st.post(
                f"/troupes/{t}/posts",
                json={"agency_id": agency, "title": "Ravens over the harbour", "body": "Wings."},
            ),
            201,
        )
        ok(st.post(f"/posts/{story['id']}/publish", json={}))
        ok(
            st.post(
                f"/troupes/{t}/posts",
                json={"kind": "announcement", "title": "Raven drill", "body": "At nine."},
            ),
            201,
        )

        self.other_lead = sign_up(troupe.client_for, "otherlead")
        self.other = ok(
            troupe.custodian.client.post(
                "/troupes", json={"name": "Other Court", "lead_handle": self.other_lead.handle}
            ),
            201,
        )["id"]
        self.raven_two = ok(
            self.other_lead.client.post(f"/troupes/{self.other}/npcs", json={"name": "Raven Two"}),
            201,
        )["id"]


@pytest.fixture
def court(client_for: Callable[[], TestClient], session: Session) -> Court:
    return Court(Troupe(client_for, session), session)


def search(person: Person, q: str = "raven", troupe_id: str | None = None) -> dict[str, Any]:
    params = {"q": q, **({"troupe_id": troupe_id} if troupe_id else {})}
    return {g["kind"]: g for g in ok(person.client.get("/search", params=params))["groups"]}


def titles(person: Person, q: str = "raven", troupe_id: str | None = None) -> dict[str, set[str]]:
    return {
        kind: {h["title"] for h in g["hits"]} for kind, g in search(person, q, troupe_id).items()
    }


def links(person: Person, kind: str) -> dict[str, str]:
    return {h["title"]: h["to"] for h in search(person).get(kind, {"hits": []})["hits"]}


# --- each person, each kind ------------------------------------------------------------------


def test_a_player_finds_what_their_pages_show_them(court: Court) -> None:
    found = titles(court.troupe.player)

    # Their own sheet, and Corvin and Ravenscroft as the Who's Who lists them; never the
    # untitled NPC, nor another troupe's.
    assert found["characters"] == {"Ravenna", "Ravenscroft"}
    assert found["players"] == {"ravenkeeper"}
    assert found["boons"] == {"Ravenna owes Corvin a minor boon"}
    assert found["locations"] == {"Raven's Rest"}
    assert found["quests"] == {"The Raven's errand"}
    assert found["equipment"] == {"Raven-headed cane"}
    assert found["news"] == {"Ravens over the harbour"}
    assert "announcements" not in found


def test_a_players_hits_open_their_own_pages(court: Court) -> None:
    player = court.troupe.player
    t = court.troupe.id

    assert links(player, "characters") == {
        "Ravenna": f"/characters/{court.ravenna}",
        "Ravenscroft": f"/troupes/{t}/whos-who#c-{court.ravenscroft}",
    }
    assert links(player, "boons") == {
        "Ravenna owes Corvin a minor boon": f"/play/characters/{court.ravenna}?tab=boons"
    }
    assert links(player, "locations") == {"Raven's Rest": f"/characters/{court.ravenna}"}
    assert links(player, "equipment") == {
        "Raven-headed cane": f"/characters/{court.ravenna}/equipment"
    }
    (quest,) = links(player, "quests").values()
    assert quest.startswith(f"/characters/{court.ravenna}/quests/")


def test_a_player_sees_no_boon_while_the_troupe_shows_players_none(court: Court) -> None:
    ok(
        court.troupe.storyteller.client.put(
            f"/troupes/{court.troupe.id}/boon-players", json={"see": "intake", "settle": False}
        )
    )

    assert "boons" not in titles(court.troupe.player)


def test_the_harpy_finds_every_boon_in_their_ledger(court: Court) -> None:
    harpy = court.harpy_player
    found = titles(harpy)

    assert found["boons"] == {
        "Ravenna owes Corvin a minor boon",
        "Lady Raven owes Lord Crow a minor boon",
    }
    ledger = f"/play/characters/{court.hestia}/ledger?troupe={court.troupe.id}"
    assert links(harpy, "boons")["Lady Raven owes Lord Crow a minor boon"] == (
        f"{ledger}&boon={court.names_only['id']}"
    )
    # Nothing else of staff's: no sheet but those the Who's Who lists, no location.
    assert found["characters"] == {"Ravenna", "Ravenscroft"}
    assert "locations" not in found


def test_a_harpy_with_only_the_review_queue_finds_no_boon(court: Court) -> None:
    ok(
        court.troupe.storyteller.client.put(
            f"/troupes/{court.troupe.id}/boon-harpy", json={"access": "submissions"}
        )
    )

    assert "boons" not in titles(court.harpy_player)


def test_staff_find_everything_of_their_troupe_and_nothing_of_another(court: Court) -> None:
    for person in (court.troupe.lead, court.troupe.storyteller, court.troupe.assistant):
        found = titles(person)

        assert found["characters"] == {"Ravenna", "Ravenscroft", "Raven Mocker"}
        assert found["players"] == {"ravenkeeper"}
        assert found["boons"] == {
            "Ravenna owes Corvin a minor boon",
            "Lady Raven owes Lord Crow a minor boon",
        }
        assert found["locations"] == {"Raven's Rest", "Ravenwood Hall"}
        assert found["quests"] == {"The Raven's errand", "Raven hunt"}
        assert found["equipment"] == {"Raven-headed cane", "Raven feather"}
        assert found["news"] == {"Ravens over the harbour"}
        assert found["announcements"] == {"Raven drill"}

    t = court.troupe.id
    assert links(court.troupe.storyteller, "boons")["Lady Raven owes Lord Crow a minor boon"] == (
        f"/troupes/{t}/boons?boon={court.names_only['id']}"
    )
    assert (
        links(court.troupe.storyteller, "characters")["Raven Mocker"]
        == f"/characters/{court.mocker}"
    )


def test_a_narrator_finds_what_a_narrator_sees(court: Court) -> None:
    found = titles(court.troupe.narrator)

    # No sheets (the Who's Who's names instead), no ledger, locations, items or quests
    # not assigned to them, and no draft.
    assert found["characters"] == {"Ravenna", "Ravenscroft"}
    assert found["news"] == {"Ravens over the harbour"}
    assert set(found) == {"characters", "players", "news"}


def test_another_troupes_lead_finds_only_their_own(court: Court) -> None:
    assert titles(court.other_lead) == {"characters": {"Raven Two"}}


def test_a_stranger_finds_nothing(court: Court) -> None:
    assert titles(court.troupe.stranger) == {}


def test_the_custodian_finds_everything_everywhere(court: Court) -> None:
    found = titles(court.troupe.custodian)

    assert found["characters"] == {"Ravenna", "Ravenscroft", "Raven Mocker", "Raven Two"}
    assert found["players"] == {"ravenkeeper"}
    assert len(found["boons"]) == 2
    assert found["announcements"] == {"Raven drill"}


def test_the_current_troupe_comes_first(court: Court) -> None:
    hits = search(court.troupe.custodian, troupe_id=court.other)["characters"]["hits"]

    assert (hits[0]["title"], hits[0]["troupe"]) == ("Raven Two", "Other Court")
    assert {h["troupe"] for h in hits[1:]} == {"Lords of the Night"}


# --- never an email, and how much it asks --------------------------------------------------


def test_never_an_email(court: Court) -> None:
    for person in (court.troupe.custodian, court.troupe.lead, court.troupe.player):
        found = search(person, "ravenmail")
        assert "players" not in found
        assert "example.com" not in str(found)
    assert titles(court.troupe.player, "@mailperson")["players"] == {"Mail Person"}


def test_a_word_of_one_letter_finds_nothing(court: Court) -> None:
    assert search(court.troupe.custodian, "r") == {}


def test_each_group_shows_five_and_says_there_are_more(court: Court) -> None:
    for n in range(6):
        ok(
            court.troupe.lead.client.post(
                f"/troupes/{court.troupe.id}/npcs", json={"name": f"Crow {n}"}
            ),
            201,
        )

    crows = search(court.troupe.lead, "crow")["characters"]

    assert (len(crows["hits"]), crows["more"]) == (5, True)


@pytest.fixture
def statements(session: Session) -> Iterator[list[str]]:
    """The SQL the session sends, from when it is asked for."""
    sent: list[str] = []

    def keep(*args: Any) -> None:
        sent.append(args[2])

    connection = session.connection()
    event.listen(connection, "before_cursor_execute", keep)
    yield sent
    event.remove(connection, "before_cursor_execute", keep)


def test_a_search_asks_the_database_a_bounded_number_of_times(
    court: Court, statements: list[str]
) -> None:
    for person in (
        court.troupe.player,
        court.harpy_player,
        court.troupe.lead,
        court.troupe.custodian,
    ):
        statements.clear()
        search(person)
        assert len(statements) <= 35, (person.handle, len(statements))

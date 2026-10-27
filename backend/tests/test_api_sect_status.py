"""Sect status on the character (horatio.sect_status): derived from titles, social age
and merits; fleeting and negative status held with its patron, as the troupe's Status
on sheets setting allows; the caps, bans, Disgraced, and negative status ending."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import sect_status
from horatio.models import (
    AuditEvent,
    Character,
    CharacterTrait,
    HeldStatus,
    PlayGame,
    TraitCategory,
    TraitDefinition,
    User,
)
from horatio.renames import add_months
from horatio.sheets import apply_grants
from tests.api_helpers import Person, Troupe, new_character, sign_up


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def choose(person: Person, character_id: str, category: str, name: str) -> None:
    response = person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": None},
    )
    assert response.status_code == 200, response.text


def make_home(troupe: Troupe, player: Person, character_id: str) -> None:
    asked = player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert asked.status_code == 201, asked.text
    approved = troupe.lead.client.post(f"/approvals/{asked.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text


def member(
    troupe: Troupe,
    name: str = "Agnes",
    *,
    sect: str = "Camarilla",
    clan: str = "Ventrue",
    player: Person | None = None,
) -> str:
    """A PC of `sect` whose home troupe is `troupe`."""
    player = player or troupe.player
    character_id = new_character(troupe, player, name, clan=clan)
    choose(player, character_id, "sect", sect)
    make_home(troupe, player, character_id)
    return character_id


def npc(troupe: Troupe, name: str, sect: str) -> str:
    made = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs", json={"name": name, "wizard": False}
    )
    assert made.status_code == 201, made.text
    npc_id: str = made.json()["id"]
    rated = troupe.storyteller.client.put(
        f"/characters/{npc_id}/npc/ratings",
        json={"category": "sect", "name": sect, "rating": None},
    )
    assert rated.status_code == 200, rated.text
    return npc_id


def entitle(troupe: Troupe, character_id: str, *names: str) -> None:
    given = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/characters/{character_id}/titles", json={"titles": list(names)}
    )
    assert given.status_code == 200, given.text


def status(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/status")
    assert response.status_code == 200, response.text
    return response.json()


def add(person: Person, character_id: str, name: str, **body: Any) -> Any:
    body.setdefault("patron_text", "Prince Varga")
    return person.client.post(f"/characters/{character_id}/status", json={"name": name, **body})


def held(person: Person, character_id: str) -> list[str]:
    return [h["name"] for h in status(person, character_id)["held"]]


def held_id(person: Person, character_id: str, name: str) -> str:
    return next(h["id"] for h in status(person, character_id)["held"] if h["name"] == name)


def remove(person: Person, character_id: str, held: str, reason: str = "") -> Any:
    return person.client.post(
        f"/characters/{character_id}/status/{held}/remove", json={"reason": reason}
    )


def put_trait(session: Session, character_id: str, category: str, name: str, rating: int) -> None:
    definition = session.scalars(
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(TraitCategory.key == category, TraitDefinition.name == name)
    ).one()
    session.add(
        CharacterTrait(
            character_id=uuid.UUID(character_id),
            trait_definition_id=definition.id,
            rating=rating,
        )
    )
    session.flush()


def logged(session: Session, character_id: str, action: str) -> list[dict[str, Any]]:
    return [
        e.data
        for e in session.scalars(
            select(AuditEvent)
            .where(AuditEvent.character_id == uuid.UUID(character_id), AuditEvent.action == action)
            .order_by(AuditEvent.created_at)
        )
    ]


# --- who adds and removes it --------------------------------------------------------------------


def test_a_player_keeps_their_own_status_naming_the_patron(troupe: Troupe) -> None:
    agnes = member(troupe)

    assert add(troupe.player, agnes, "Loyal", patron_text="").status_code == 422
    added = add(troupe.player, agnes, "Loyal", story="For holding the door at Elysium.")

    assert added.status_code == 200, added.text
    [loyal] = added.json()["held"]
    assert (loyal["name"], loyal["type"], loyal["patron"]["words"]) == (
        "Loyal",
        "Fleeting",
        "Prince Varga",
    )
    assert loyal["place"] == "Lords of the Night"
    assert loyal["given_on"] == datetime.now(UTC).date().isoformat()
    assert loyal["can_remove"]

    removed = remove(troupe.player, agnes, loyal["id"])

    assert removed.status_code == 200, removed.text
    assert removed.json()["held"] == []
    log = [e["message"] for e in troupe.player.client.get(f"/characters/{agnes}/log").json()]
    assert "player gave Agnes the fleeting status Loyal, from Prince Varga." in log
    assert "player removed Agnes's Loyal (from Prince Varga)." in log


def test_in_a_staff_only_troupe_only_staff_change_status(troupe: Troupe) -> None:
    agnes = member(troupe)
    set_to = troupe.storyteller.client.patch(f"/troupes/{troupe.id}", json={"status_by": "staff"})
    assert set_to.status_code == 200, set_to.text
    assert set_to.json()["status_by"] == "staff"
    assert (
        troupe.assistant.client.patch(
            f"/troupes/{troupe.id}", json={"status_by": "players"}
        ).status_code
        == 403
    )

    refused = add(troupe.player, agnes, "Loyal")
    assert refused.status_code == 409
    assert "Only staff" in refused.json()["detail"]
    assert status(troupe.player, agnes)["acting"] is None

    # Staff say why, for the log.
    assert add(troupe.assistant, agnes, "Loyal").status_code == 422
    assert add(troupe.assistant, agnes, "Loyal", reason="Defended Elysium").status_code == 200
    loyal = held_id(troupe.player, agnes, "Loyal")

    assert remove(troupe.player, agnes, loyal).status_code == 409
    assert remove(troupe.narrator, agnes, loyal).status_code == 404
    assert remove(troupe.assistant, agnes, loyal, reason="Spent at game").status_code == 200
    assert held(troupe.player, agnes) == []
    assert logged(troupe.session, agnes, "status.removed")[0]["reason"] == "Spent at game"


def test_status_is_not_bought_on_the_sheet(troupe: Troupe) -> None:
    agnes = member(troupe)

    bought = troupe.player.client.put(
        f"/characters/{agnes}/traits",
        json={"category": "status_traits", "name": "Loyal", "rating": 1},
    )

    assert bought.status_code == 422
    assert "Status section" in bought.json()["detail"]


def test_only_its_own_sects_status_and_only_while_accepted(troupe: Troupe) -> None:
    agnes = member(troupe)
    unaligned = new_character(troupe, troupe.player, "Bertrand")
    make_home(troupe, troupe.player, unaligned)

    assert add(troupe.player, unaligned, "Loyal").status_code == 409
    assert status(troupe.player, unaligned)["accepted"] is None
    # Devout is the Sabbat's; abiding status comes from titles alone.
    assert add(troupe.player, agnes, "Devout").status_code == 422
    assert add(troupe.player, agnes, "Authority").status_code == 422
    found = status(troupe.player, agnes)
    assert found["accepted"] == "Acknowledged"
    addable = {s["name"] for s in found["addable"]}
    assert {"Loyal", "Warned", "Acclaimed"} <= addable
    assert not addable & {"Devout", "Authority", "Acknowledged"}


def test_changing_sect_clears_held_status(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player, "Agnes", clan="Ventrue")
    choose(troupe.player, agnes, "sect", "Camarilla")
    assert add(troupe.player, agnes, "Loyal").status_code == 200

    choose(troupe.player, agnes, "sect", "Anarch")

    assert held(troupe.player, agnes) == []
    [cleared] = logged(troupe.session, agnes, "status.cleared")
    assert (cleared["statuses"], cleared["sect"]) == ("Loyal", "Anarch")


# --- naming the patron --------------------------------------------------------------------------


def test_the_patron_list_is_the_home_troupes_pcs_and_its_titled_npcs_of_the_sect(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    agnes = member(troupe)
    other = sign_up(client_for, "other")
    elena = member(troupe, "Elena Varga", player=other)
    member(troupe, "Tomas Reyes", player=other)
    entitle(troupe, elena, "Prince")
    sheriff = npc(troupe, "Sheriff Okafor", "Camarilla")
    entitle(troupe, sheriff, "Sheriff")
    npc(troupe, "Untitled Udo", "Camarilla")
    bishop = npc(troupe, "Bishop Rook", "Sabbat")
    entitle(troupe, bishop, "Bishop")

    patrons = troupe.player.client.get(f"/characters/{agnes}/status/patrons").json()

    assert [(p["name"], p["kind"], p["title"]) for p in patrons] == [
        ("Elena Varga", "pc", "Prince"),
        ("Sheriff Okafor", "npc", "Sheriff"),
        ("Tomas Reyes", "pc", ""),
    ]

    # A pick alone, with the title held then kept with the record.
    picked = add(troupe.player, agnes, "Loyal", patron_id=elena, patron_text="")
    assert picked.status_code == 200, picked.text
    [loyal] = picked.json()["held"]
    assert loyal["patron"]["words"] == "Elena Varga (Prince at the time)"
    # Not someone off the list.
    assert add(troupe.player, agnes, "Loyal", patron_id=bishop).status_code == 422

    # A rename shows; the title stays the one held then.
    entitle(troupe, elena)
    troupe.session.get_one(Character, uuid.UUID(elena)).name = "Elena Varga-Sforza"
    troupe.session.flush()
    [loyal] = status(troupe.player, agnes)["held"]
    assert loyal["patron"]["words"] == "Elena Varga-Sforza (Prince at the time)"


# --- derived status -----------------------------------------------------------------------------


def test_a_princes_status_comes_from_the_title_and_an_elders_from_social_age(
    troupe: Troupe,
) -> None:
    prince = member(troupe, "Elena")
    entitle(troupe, prince, "Prince")
    elder = member(troupe, "Old Mother")
    put_trait(troupe.session, elder, "backgrounds", "Generation", 3)

    derived = status(troupe.player, prince)["derived"]
    assert [(d["name"], d["source"], d["kind"]) for d in derived] == [
        ("Authority", "Prince", "title"),
        ("Commander", "Prince", "title"),
        ("Sovereign", "Prince", "title"),
    ]
    assert derived[0]["troupe_name"] == "Lords of the Night"
    derived = status(troupe.player, elder)["derived"]
    assert [(d["name"], d["source"]) for d in derived] == [
        ("Confirmed", "Elder"),
        ("Established", "Elder"),
        ("Privileged", "Elder"),
    ]


def test_a_title_of_another_sect_gives_no_status(troupe: Troupe) -> None:
    baron = member(troupe, "Rook", sect="Sabbat", clan="Lasombra")
    entitle(troupe, baron, "Prince")

    assert status(troupe.player, baron)["derived"] == []


def test_carried_takes_one_abiding_source_and_the_cap(troupe: Troupe) -> None:
    agnes = member(troupe)
    entitle(troupe, agnes, "Seneschal", "Primogen")
    put_trait(troupe.session, agnes, "backgrounds", "Generation", 3)
    for _ in range(2):
        assert add(troupe.player, agnes, "Loyal").status_code == 200
    assert add(troupe.player, agnes, "Warned").status_code == 200
    character = troupe.session.get_one(Character, uuid.UUID(agnes))
    troupe_id = uuid.UUID(troupe.id)

    def carried(**options: Any) -> list[tuple[str, str]]:
        found = sect_status.carried(troupe.session, character, troupe_id, **options)
        return [(c.name, c.source) for c in found]

    # The first title by name, and none of its conditional status.
    assert carried()[:1] == [("Noble", "Primogen")]
    assert [n for n, _ in carried()] == ["Noble", "Warned", "Loyal", "Loyal"]
    assert [n for n, _ in carried(abiding_source="Seneschal", absent={"Prince"})][:2] == [
        "Noble",
        "Authority",
    ]
    assert [n for n, _ in carried(abiding_source="Elder")][:3] == [
        "Confirmed",
        "Established",
        "Privileged",
    ]


# --- caps and bans ------------------------------------------------------------------------------


def test_a_sixth_fleeting_status_asks_which_to_give_up(troupe: Troupe) -> None:
    agnes = member(troupe)
    for name in ("Loyal", "Courteous", "Defender", "Favored", "Honorable"):
        assert add(troupe.player, agnes, name).status_code == 200

    asked = add(troupe.player, agnes, "Triumphant")

    assert asked.status_code == 409
    assert "choose one to give up" in asked.json()["detail"]
    favored = held_id(troupe.player, agnes, "Favored")
    given = add(troupe.player, agnes, "Triumphant", give_up=favored)
    assert given.status_code == 200, given.text
    assert sorted(held(troupe.player, agnes)) == [
        "Courteous",
        "Defender",
        "Honorable",
        "Loyal",
        "Triumphant",
    ]
    assert logged(troupe.session, agnes, "status.given_up")[0]["status"] == "Favored"
    # Negative status has no cap.
    assert add(troupe.player, agnes, "Warned").status_code == 200


def test_a_lesser_ban_caps_fleeting_status_at_3_unless_staff_exempt_it(troupe: Troupe) -> None:
    # The Gangrel are no pillar clan of the Camarilla.
    agnes = member(troupe, clan="Gangrel")
    found = status(troupe.player, agnes)
    assert found["fleeting_cap"] == 3
    pillar = next(b for b in found["bans"] if b["applies_to"].startswith("Not Embraced"))
    assert (pillar["level"], pillar["by_sheet"], pillar["applies"]) == ("lesser", True, True)
    for name in ("Loyal", "Courteous", "Defender"):
        assert add(troupe.player, agnes, name).status_code == 200
    assert add(troupe.player, agnes, "Favored").status_code == 409

    path = f"/characters/{agnes}/status/bans"
    exempt = {"ban": pillar["applies_to"], "mark": "exempt", "reason": "The Prince's word"}
    assert troupe.player.client.put(path, json=exempt).status_code == 409
    assert troupe.storyteller.client.put(path, json={**exempt, "reason": ""}).status_code == 422
    marked = troupe.storyteller.client.put(path, json=exempt)

    assert marked.status_code == 200, marked.text
    assert marked.json()["fleeting_cap"] == 5
    assert add(troupe.player, agnes, "Favored").status_code == 200

    # A ban the sheet cannot show, marked by staff.
    caitiff = {"ban": "Has committed diablerie.", "mark": "applies", "reason": "Witnessed"}
    assert troupe.storyteller.client.put(path, json=caitiff).json()["fleeting_cap"] == 1


def test_disgraced_gains_no_status_unless_staff_override(troupe: Troupe) -> None:
    agnes = member(troupe)
    assert (
        add(troupe.storyteller, agnes, "Disgraced", reason="Broke the Masquerade").status_code
        == 200
    )

    refused = add(troupe.player, agnes, "Loyal")

    assert refused.status_code == 409
    assert "Disgraced" in refused.json()["detail"]
    assert add(troupe.player, agnes, "Warned").status_code == 200
    assert status(troupe.player, agnes)["disgraced"]
    overridden = add(troupe.storyteller, agnes, "Loyal", reason="Pardoned", override=True)
    assert overridden.status_code == 200, overridden.text


def test_disgraced_stops_prestigious_sires_loyal(troupe: Troupe) -> None:
    agnes = member(troupe)
    put_trait(troupe.session, agnes, "merits", "Prestigious Sire", 1)
    character = troupe.session.get_one(Character, uuid.UUID(agnes))
    apply_grants(troupe.session, troupe.session.get_one(User, character.player_id), character)
    derived = status(troupe.player, agnes)["derived"]
    assert [(d["name"], d["kind"], d["source"]) for d in derived] == [
        ("Loyal", "merit", "Prestigious Sire")
    ]

    assert add(troupe.storyteller, agnes, "Disgraced", reason="Diablerie").status_code == 200

    assert status(troupe.player, agnes)["derived"] == []


# --- negative status ends -----------------------------------------------------------------------


def test_warned_shows_its_end_and_goes_after_2_games_and_a_month(troupe: Troupe) -> None:
    agnes = member(troupe)
    today = datetime.now(UTC).date()
    assert add(troupe.storyteller, agnes, "Warned", reason="Fed in Elysium").status_code == 200

    [warned] = status(troupe.player, agnes)["held"]
    ending = warned["ending"]
    assert ending["text"].startswith("2 games or 1 month")
    assert (ending["games_left"], ending["not_before"]) == (2, month_on(today).isoformat())
    # The player cannot take it off early; staff can.
    assert not warned["can_remove"]
    assert remove(troupe.player, agnes, warned["id"]).status_code == 409

    row = troupe.session.get_one(HeldStatus, uuid.UUID(warned["id"]))
    row.given_on = today - timedelta(days=40)
    row.created_at = datetime.now(UTC) - timedelta(days=40)
    play_games(troupe.session, agnes, 1)
    assert status(troupe.player, agnes)["held"][0]["ending"]["games_left"] == 1
    play_games(troupe.session, agnes, 1, start=2)

    assert status(troupe.player, agnes)["held"] == []
    [expired] = logged(troupe.session, agnes, "status.expired")
    assert expired["status"] == "Warned"


def test_a_second_warned_adds_the_same_again(troupe: Troupe) -> None:
    agnes = member(troupe)
    today = datetime.now(UTC).date()
    for _ in range(2):
        assert add(troupe.storyteller, agnes, "Warned", reason="Again").status_code == 200

    endings = [h["ending"] for h in status(troupe.player, agnes)["held"]]

    assert [(e["games_left"], e["not_before"]) for e in endings] == [
        (4, month_on(today, 2).isoformat())
    ] * 2


def test_the_patrons_player_takes_off_the_negative_status_they_gave(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    agnes = member(troupe)
    other = sign_up(client_for, "other")
    elena = member(troupe, "Elena Varga", player=other)
    assert add(troupe.player, agnes, "Warned", patron_id=elena).status_code == 200
    character = troupe.session.get_one(Character, uuid.UUID(agnes))
    patron_player = troupe.session.get_one(User, uuid.UUID(other.id))
    warned = uuid.UUID(held_id(troupe.player, agnes, "Warned"))

    sect_status.remove(troupe.session, patron_player, character, None, warned)

    assert held(troupe.player, agnes) == []


def month_on(day: date, months: int = 1) -> date:
    return add_months(day, months)


def play_games(session: Session, character_id: str, count: int, start: int = 1) -> None:
    """`count` games played and ended, after everything so far."""
    now = datetime.now(UTC)
    for n in range(start, start + count):
        session.add(
            PlayGame(
                character_id=uuid.UUID(character_id),
                number=n,
                started_at=now + timedelta(minutes=n),
                ended_at=now + timedelta(minutes=n, seconds=30),
            )
        )
    session.flush()


# --- the setting and the waiting list ----------------------------------------------------------


def test_status_left_from_before_waits_for_staff_to_resolve(troupe: Troupe) -> None:
    agnes = member(troupe)
    put_trait(troupe.session, agnes, "status_traits", "Noble", 1)

    found = status(troupe.storyteller, agnes)
    assert found["unresolved"] == ["Noble"]
    waiting = troupe.storyteller.client.get(f"/troupes/{troupe.id}/waiting").json()
    line = next(w for w in waiting if w["kind"] == "status_to_resolve")
    assert (line["count"], line["link"]) == (1, f"/characters/{agnes}")

    path = f"/characters/{agnes}/status/resolve"
    assert troupe.player.client.post(path, json={"name": "Noble"}).status_code == 409
    resolved = troupe.storyteller.client.post(path, json={"name": "Noble", "reason": "No title"})

    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["unresolved"] == []


def test_a_loyalist_has_loyalist_status_while_it_holds_no_sabbat_title(troupe: Troupe) -> None:
    rook = member(troupe, "Rook", sect="Sabbat", clan="Lasombra")
    choose(troupe.player, rook, "faction", "Loyalist")

    derived = status(troupe.player, rook)["derived"]
    assert [(d["name"], d["source"], d["kind"]) for d in derived] == [
        ("Loyalist", "Loyalist", "faction")
    ]

    entitle(troupe, rook, "Bishop")
    assert "Loyalist" not in {d["name"] for d in status(troupe.player, rook)["derived"]}


def test_ancilla_and_elder_titles_give_no_status_beside_social_age(troupe: Troupe) -> None:
    elder = member(troupe, "Old Mother")
    put_trait(troupe.session, elder, "backgrounds", "Generation", 3)
    entitle(troupe, elder, "Elder")

    derived = status(troupe.player, elder)["derived"]
    assert sorted(d["name"] for d in derived) == ["Confirmed", "Established", "Privileged"]

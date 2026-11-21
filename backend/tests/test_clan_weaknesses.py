"""Which Tremere weakness a troupe plays (issue #1127): Volume 2's, the default, or the
core book's. What is shown follows the troupe; with no troupe it says both."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import clan_weaknesses
from horatio.models import AuditEvent
from horatio.models import Troupe as TroupeRow
from horatio.rules.store import read_troupe_rules
from tests.api_helpers import Troupe
from tests.test_api_renames import troupe_log
from tests.test_api_troupe_settings_share import apply, exported, ok, second
from tests.test_clan_names import at_home

pytestmark = pytest.mark.usefixtures("without_bank")

VOL2 = "Their blood bonds other vampires only to the first stage; ghouls are bound as usual."
CORE = (
    "Easily bound: their first drink of another vampire's blood counts as two,"
    " so a second binds them fully."
)


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def clans(troupe: Troupe, troupe_id: str | None, path: str = "") -> dict[str, dict[str, Any]]:
    params = {"troupe_id": troupe_id} if troupe_id else {}
    found = ok(troupe.player.client.get(f"/rules/vampire{path}", params=params))
    traits = found["catalogue"]["traits"] if path else found["traits"]
    return {t["name"]: t for t in traits if t["category"] == "clan"}


def set_core(troupe: Troupe, core: list[str], code: int = 200) -> Any:
    return ok(
        troupe.storyteller.client.put(f"/troupes/{troupe.id}/clan-weaknesses", json={"core": core}),
        code,
    )


def logged(session: Session) -> list[str]:
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.action == "house.clan_weaknesses")
        .order_by(AuditEvent.created_at)
    )
    return [e.data["setting"] for e in events]


def test_the_rules_data_keeps_both_and_only_the_tremere_choose(session: Session) -> None:
    rule_set = read_troupe_rules(session, "vampire", None).rule_set

    assert clan_weaknesses.choosable(rule_set) == ["Tremere"]
    later, core = clan_weaknesses.versions(rule_set, "Tremere")
    assert (later.book, later.text, later.page) == ("vol2", VOL2, "Vol. 2, p. 22")
    assert (core.book, core.text, core.page) == ("core", CORE, "64")
    # Telyav has no weakness of its own, so it has both of its clan's.
    assert clan_weaknesses.versions(rule_set, "Tremere: Telyav") == [later, core]
    # Volume 2's page on the Followers of Set leaves their weakness alone.
    assert [(w.book, w.page) for w in clan_weaknesses.versions(rule_set, "Followers of Set")] == [
        ("core", "48")
    ]
    assert clan_weaknesses.versions(rule_set, "Gangrel: Anda")[0].book == "vol2"


def test_a_troupe_plays_volume_2s_until_its_staff_choose(troupe: Troupe) -> None:
    assert troupe.session.get_one(TroupeRow, troupe.id).core_weaknesses == []
    assert ok(troupe.storyteller.client.get(f"/troupes/{troupe.id}/clan-weaknesses")) == {
        "clans": [
            {
                "clan": "Tremere",
                "versions": [
                    {
                        "book": "vol2",
                        "label": "Volume 2",
                        "weakness": VOL2,
                        "page": "Vol. 2, p. 22",
                    },
                    {"book": "core", "label": "Core book", "weakness": CORE, "page": "64"},
                ],
                "chosen": "vol2",
            }
        ]
    }
    shown = clans(troupe, troupe.id)
    for name in ("Tremere", "Tremere: Telyav"):
        assert (shown[name]["weakness"], shown[name]["weakness_page"]) == (VOL2, "Vol. 2, p. 22")
        assert "weaknesses" not in shown[name]


def test_choosing_the_core_books_changes_what_the_troupe_shows_and_is_logged(
    troupe: Troupe,
) -> None:
    chosen = set_core(troupe, ["Tremere"])

    assert chosen["clans"][0]["chosen"] == "core"
    for path in ("", "/browse"):
        shown = clans(troupe, troupe.id, path)
        for name in ("Tremere", "Tremere: Telyav"):
            assert (shown[name]["weakness"], shown[name]["weakness_page"]) == (CORE, "64")
        # Every other clan is as it was.
        assert shown["Brujah"]["weakness_page"] == "45"
    assert logged(troupe.session) == ["the core book's for the Tremere; Volume 2's for the rest"]

    # The same again changes nothing, and logs nothing; going back logs again.
    set_core(troupe, ["Tremere"])
    assert len(logged(troupe.session)) == 1
    set_core(troupe, [])
    assert clans(troupe, troupe.id)["Tremere"]["weakness"] == VOL2
    assert logged(troupe.session)[-1] == "Volume 2's for every clan"
    assert any(
        m.endswith("set the clan weaknesses played here: Volume 2's for every clan.")
        for m in troupe_log(troupe.storyteller, troupe.id)
    )


def test_only_a_clan_with_two_weaknesses_and_only_its_storytellers(troupe: Troupe) -> None:
    refused = set_core(troupe, ["Brujah"], 422)
    assert "Only Tremere has one" in refused["detail"]
    path = f"/troupes/{troupe.id}/clan-weaknesses"
    assert troupe.player.client.put(path, json={"core": ["Tremere"]}).status_code == 403
    assert troupe.player.client.get(path).status_code == 403
    assert troupe.session.get_one(TroupeRow, troupe.id).core_weaknesses == []


def test_with_no_troupe_the_weakness_varies_and_both_are_given(troupe: Troupe) -> None:
    shown = clans(troupe, None)

    for name in ("Tremere", "Tremere: Telyav"):
        assert "weakness" not in shown[name]
        assert shown[name]["weaknesses"] == [
            {"book": "vol2", "label": "Volume 2", "weakness": VOL2, "page": "Vol. 2, p. 22"},
            {"book": "core", "label": "Core book", "weakness": CORE, "page": "64"},
        ]
    assert shown["Brujah"]["weakness_page"] == "45"
    assert "weaknesses" not in shown["Brujah"]
    # The rules browser with no troupe too.
    assert len(clans(troupe, None, "/browse")["Tremere"]["weaknesses"]) == 2


def test_a_characters_play_view_shows_its_troupes(troupe: Troupe) -> None:
    character_id = at_home(troupe, "Etrius", "Tremere")

    def played() -> dict[str, Any]:
        found = ok(troupe.player.client.get(f"/characters/{character_id}/play/reference"))
        return next(t for t in found["traits"] if t["category"] == "clan")

    assert (played()["weakness"], played()["weakness_page"]) == (VOL2, "Vol. 2, p. 22")
    set_core(troupe, ["Tremere"])
    assert (played()["weakness"], played()["weakness_page"]) == (CORE, "64")


def test_its_players_read_it_among_the_house_rules(troupe: Troupe) -> None:
    def other() -> list[dict[str, Any]]:
        return ok(troupe.player.client.get(f"/troupes/{troupe.id}/house-rules"))["other"]

    assert not any(s["name"] == "The Tremere weakness" for s in other())
    set_core(troupe, ["Tremere"])
    setting = next(s for s in other() if s["name"] == "The Tremere weakness")
    assert setting["text"] == f"The core book's: {CORE} (p. 64)"
    assert setting["book_text"] == f"Volume 2's, which replaced it: {VOL2} (Vol. 2, p. 22)"


def test_it_travels_with_the_troupes_settings(troupe: Troupe) -> None:
    assert not any(
        i.get("key") == "core_weaknesses"
        for i in exported(troupe.storyteller, troupe.id)["sections"]["at_game"]
    )
    set_core(troupe, ["Tremere"])
    document = exported(troupe.storyteller, troupe.id)
    assert {"type": "setting", "key": "core_weaknesses", "value": ["Tremere"]} in document[
        "sections"
    ]["at_game"]
    fresh = second(troupe)

    ok(apply(troupe.storyteller, fresh, document, from_troupe_id=troupe.id))

    assert clans(troupe, fresh)["Tremere"]["weakness"] == CORE
    # One of no clan with two weaknesses can't come in.
    document["sections"]["at_game"] = [
        {"type": "setting", "key": "core_weaknesses", "value": ["Ventrue"]}
    ]
    refused = apply(troupe.storyteller, fresh, document)
    assert refused.status_code == 422, refused.text

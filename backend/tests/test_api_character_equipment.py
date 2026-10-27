"""A character's equipment on its own page, its Play View and its printed sheet (issue
#281): each quality with what it does, in full and at the table, and no staff note on
paper."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe
from tests.test_api_downtimes import member_character
from tests.test_api_troupe_equipment import DAGGER, LEGEND, given


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def agnes(troupe: Troupe) -> str:
    return member_character(troupe, troupe.player, "Agnes")


def test_the_player_reads_each_quality_and_what_it_does(troupe: Troupe, agnes: str) -> None:
    assert troupe.player.client.get(f"/characters/{agnes}/equipment").json()["items"] == []
    given(troupe, agnes, **DAGGER, staff_note="Blessed by the priest")

    dagger = troupe.player.client.get(f"/characters/{agnes}/equipment").json()["items"][0]

    assert (dagger["name"], dagger["kind_name"]) == ("Silver Dagger", "Melee weapon")
    concealable, silver = dagger["qualities"]
    assert concealable["play"] == "Hidden until searched"
    assert concealable["effect"].startswith("Can't be seen when hidden")
    assert (silver["play"], silver["page"]) == ("Aggravated damage to werewolves", "517")
    assert dagger["staff_note"] is None


def test_the_printed_sheet_lists_equipment_without_the_staff_note(
    troupe: Troupe, agnes: str
) -> None:
    given(troupe, agnes, **DAGGER, staff_note="Blessed by the priest")
    given(troupe, agnes, by=troupe.assistant, **LEGEND)

    for person in (troupe.player, troupe.storyteller):
        printed = person.client.get(f"/characters/{agnes}/print").json()["equipment"]
        assert [i["name"] for i in printed] == ["Blade of Saulot", "Silver Dagger"]
        assert [i["staff_note"] for i in printed] == [None, None]
        assert not any(i["can_change"] for i in printed)
        assert printed[0]["effects"] == LEGEND["effects"]

    sheets = troupe.storyteller.client.get(f"/troupes/{troupe.id}/print").json()
    agnes_sheet = next(s for s in sheets if s["character_name"] == "Agnes")
    assert [i["name"] for i in agnes_sheet["equipment"]] == ["Blade of Saulot", "Silver Dagger"]
    assert agnes_sheet["equipment"][1]["staff_note"] is None

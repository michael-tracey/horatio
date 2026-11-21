"""A troupe's abbreviation (#1153): the one made from its name, giving way to the name
when it clashes; the one its lead sets, checked and unique on the site; its log; and
carrying it in the troupe's settings."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Troupe as TroupeRecord
from horatio.troupe_abbreviations import GoesBy, Named, choose, initials
from tests.api_helpers import Person, Troupe
from tests.test_api_renames import troupe_log
from tests.test_api_troupe_settings_share import apply, exported, reviewed, second


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def read(person: Person, troupe_id: str) -> dict[str, Any]:
    return ok(person.client.get(f"/troupes/{troupe_id}"))


def abbreviate(person: Person, troupe_id: str, abbreviation: str) -> Any:
    return person.client.patch(f"/troupes/{troupe_id}", json={"abbreviation": abbreviation})


def made(troupe: Troupe, name: str, lead: Person | None = None) -> str:
    """Another troupe, led by the first troupe's lead unless said."""
    lead = lead or troupe.lead
    response = troupe.custodian.client.post(
        "/troupes", json={"name": name, "lead_handle": lead.handle}
    )
    return ok(response, 201)["id"]


# --- the one made from the name ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "abbreviation"),
    [
        ("Court of Ashes", "CoA"),
        ("Land of the Sky", "LotS"),
        ("Lords of the Night", "LotN"),
        # The first word is a capital, small or not.
        ("The Court of Ashes", "TCoA"),
        ("a song for the dead", "ASftD"),
        ("Prince's Court, in the North-East", "PCitNE"),
        ("Elysium", "E"),
        ("Atlanta 1999", "A1"),
        ("Ébène et Sang", "ÉES"),
        ("???", ""),
    ],
)
def test_the_one_made_from_a_name(name: str, abbreviation: str) -> None:
    assert initials(name) == abbreviation


def named(name: str, abbreviation: str | None = None, *, archived: bool = False) -> Named:
    return Named(uuid.uuid4(), name, abbreviation, archived)


def test_a_made_one_that_clashes_gives_way_to_the_name() -> None:
    ashes, circle, sky, own, blank = (
        named("Court of Ashes"),
        named("Circle of Ash"),
        named("Land of the Sky"),
        named("Lords of Sorrow", "LOTS"),
        named("!!!"),
    )

    chosen = {k: v.abbreviation for k, v in choose([ashes, circle, sky, own, blank]).items()}

    # Both would make CoA: neither takes it.
    assert chosen[ashes.id] == "Court of Ashes"
    assert chosen[circle.id] == "Circle of Ash"
    # Another troupe set LOTS: any case clashes.
    assert chosen[sky.id] == "Land of the Sky"
    assert chosen[own.id] == "LOTS"
    # Nothing to make one from.
    assert chosen[blank.id] == "!!!"


def test_an_archived_troupes_made_one_stands_in_nobodys_way() -> None:
    live, gone = named("Court of Ashes"), named("Circle of Ash", archived=True)

    chosen = {k: v.abbreviation for k, v in choose([live, gone]).items()}

    assert chosen[live.id] == "CoA"
    assert chosen[gone.id] == "Circle of Ash"
    # Its own set one still counts.
    kept = named("Circle of Ash", "coa", archived=True)
    assert choose([live, kept])[live.id].abbreviation == "Court of Ashes"


def test_the_default_is_what_it_would_go_by_with_none_set() -> None:
    lords, lantern = named("Lords of the Night", "Lords"), named("Lantern of the North", "LotN")

    chosen = choose([lords, lantern, named("Court of Ashes")])

    # Another troupe set the one it would make.
    assert chosen[lords.id] == GoesBy("Lords", "Lords of the Night")
    # Its own set one is no clash with itself.
    assert chosen[lantern.id] == GoesBy("LotN", "LotN")


def test_the_troupe_says_what_it_goes_by_and_what_was_set(troupe: Troupe) -> None:
    found = read(troupe.player, troupe.id)

    assert (found["abbreviation"], found["abbreviation_set"]) == ("LotN", None)
    assert found["abbreviation_default"] == "LotN"
    other = made(troupe, "Lantern of the North")
    # Both make LotN now: each goes by its name until one is set.
    assert read(troupe.lead, troupe.id)["abbreviation"] == "Lords of the Night"
    assert read(troupe.lead, other)["abbreviation"] == "Lantern of the North"
    listed = {t["id"]: t["abbreviation"] for t in ok(troupe.lead.client.get("/troupes"))}
    assert listed[troupe.id] == "Lords of the Night"

    ok(abbreviate(troupe.lead, other, "Lantern"))

    assert read(troupe.lead, troupe.id)["abbreviation"] == "LotN"
    assert read(troupe.lead, other)["abbreviation"] == "Lantern"


def test_the_profile_shows_it(troupe: Troupe) -> None:
    profile = ok(troupe.player.client.get(f"/troupes/{troupe.id}/profile"))

    assert profile["abbreviation"] == "LotN"


# --- the one its lead sets ----------------------------------------------------------------------


def test_whoever_may_rename_the_troupe_sets_it(troupe: Troupe) -> None:
    for person in (troupe.storyteller, troupe.assistant, troupe.player, troupe.stranger):
        assert abbreviate(person, troupe.id, "Lords").status_code in (403, 404), person.handle

    set_by_lead = ok(abbreviate(troupe.lead, troupe.id, " Lords.N "))
    assert (set_by_lead["abbreviation"], set_by_lead["abbreviation_set"]) == ("Lords.N", "Lords.N")
    by_custodian = ok(abbreviate(troupe.custodian, troupe.id, "LotN_2"))
    assert by_custodian["abbreviation"] == "LotN_2"


@pytest.mark.parametrize("bad", ["Lords Night", "LordsOfNight", "Lords!", "L/N"])
def test_it_is_ten_letters_digits_and_separators_at_most(troupe: Troupe, bad: str) -> None:
    response = abbreviate(troupe.lead, troupe.id, bad)

    assert response.status_code == 422
    assert "1 to 10 letters, digits, hyphens, underscores or full stops" in response.text
    assert read(troupe.lead, troupe.id)["abbreviation_set"] is None


def test_no_two_troupes_have_the_same_whatever_the_case(troupe: Troupe) -> None:
    other = made(troupe, "Court of Ashes")
    ok(abbreviate(troupe.lead, other, "CoA"))

    response = abbreviate(troupe.lead, troupe.id, "coa")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Court of Ashes goes by CoA already: choose another abbreviation."
    )
    # The same troupe may change its case.
    assert ok(abbreviate(troupe.lead, other, "COA"))["abbreviation"] == "COA"


def test_the_database_holds_it_unique_whatever_the_case(troupe: Troupe, session: Session) -> None:
    other = made(troupe, "Court of Ashes")
    ok(abbreviate(troupe.lead, other, "CoA"))
    record = session.get_one(TroupeRecord, uuid.UUID(troupe.id))
    record.abbreviation = "COA"

    with pytest.raises(Exception, match="uq_troupes_abbreviation_lower"):
        session.flush()


def test_clearing_it_goes_back_to_the_one_made_from_the_name(troupe: Troupe) -> None:
    ok(abbreviate(troupe.lead, troupe.id, "Lords"))

    assert read(troupe.lead, troupe.id)["abbreviation_default"] == "LotN"

    cleared = ok(abbreviate(troupe.lead, troupe.id, ""))

    assert (cleared["abbreviation"], cleared["abbreviation_set"]) == ("LotN", None)


def test_each_change_is_in_the_troupes_log(troupe: Troupe) -> None:
    ok(abbreviate(troupe.lead, troupe.id, "Lords"))
    # The same again changes nothing, and isn't logged.
    ok(abbreviate(troupe.lead, troupe.id, "Lords"))
    ok(abbreviate(troupe.lead, troupe.id, ""))

    log = troupe_log(troupe.lead, troupe.id)
    assert log[:2] == [
        "lead cleared the troupe's abbreviation: it goes by LotN now.",
        "lead set the troupe's abbreviation to Lords.",
    ]
    assert sum("abbreviation" in line for line in log) == 2


# --- carried in the troupe's settings ---------------------------------------------------------


LABEL = ("names", "The troupe's abbreviation")


def with_abbreviation(document: dict[str, Any], value: str | None) -> dict[str, Any]:
    names = [i for i in document["sections"]["names"] if i["key"] != "abbreviation"]
    return {
        **document,
        "sections": {
            **document["sections"],
            "names": [*names, {"type": "setting", "key": "abbreviation", "value": value}],
        },
    }


def only_names(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"section": "names", "index": n} for n in range(len(document["sections"]["names"]))]


def test_it_is_exported_once_set(troupe: Troupe) -> None:
    assert not any(
        i["key"] == "abbreviation" for i in exported(troupe.lead, troupe.id)["sections"]["names"]
    )

    ok(abbreviate(troupe.lead, troupe.id, "Lords"))

    names = exported(troupe.lead, troupe.id)["sections"]["names"]
    assert {"type": "setting", "key": "abbreviation", "value": "Lords"} in names


def test_one_another_troupe_has_cant_be_imported(troupe: Troupe) -> None:
    ok(abbreviate(troupe.lead, troupe.id, "Lords"))
    document = exported(troupe.lead, troupe.id)
    fresh = made(troupe, "Court of Ashes")

    found = reviewed(troupe.lead, fresh, document)[LABEL]

    assert found["status"] == "cannot"
    assert (
        found["reason"] == "Lords of the Night goes by Lords already: choose another abbreviation."
    )
    response = apply(troupe.lead, fresh, document, only_names(document))
    assert response.status_code == 422
    assert "The troupe's abbreviation" in response.text
    assert read(troupe.lead, fresh)["abbreviation_set"] is None


def test_one_nobody_has_comes_in_for_whoever_may_rename_the_troupe(troupe: Troupe) -> None:
    document = with_abbreviation(exported(troupe.lead, troupe.id), "Ashes")
    fresh = made(troupe, "Court of Ashes")
    # The first troupe's storyteller is a storyteller there too, not its lead.
    ok(
        troupe.lead.client.put(
            f"/troupes/{fresh}/staff",
            json={"handle": troupe.storyteller.handle, "role": "storyteller"},
        )
    )

    by_storyteller = reviewed(troupe.storyteller, fresh, document)[LABEL]
    assert by_storyteller["status"] == "cannot"
    assert by_storyteller["reason"] == "Only the lead storyteller sets the troupe's abbreviation."
    found = reviewed(troupe.lead, fresh, document)[LABEL]
    assert (found["status"], found["before"], found["after"]) == ("changes", "None", "Ashes")

    ok(apply(troupe.lead, fresh, document, only_names(document)))

    assert read(troupe.lead, fresh)["abbreviation_set"] == "Ashes"
    assert reviewed(troupe.lead, fresh, document)[LABEL]["status"] == "same"


def test_a_bad_one_in_a_file_cant_be_imported(troupe: Troupe) -> None:
    document = with_abbreviation(exported(troupe.lead, troupe.id), "Far too long here")
    fresh = second(troupe)

    found = reviewed(troupe.storyteller, fresh, document)[LABEL]

    assert found["status"] == "cannot"
    assert found["reason"].startswith("Not a value it can have")

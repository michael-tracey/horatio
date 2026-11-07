"""Sharing a troupe's settings: exporting what differs from Horatio's default, and
importing a file, or another troupe's settings, into a troupe, merging."""

import copy
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio import troupe_settings_share as share
from horatio.models import Base
from horatio.models import Troupe as TroupeRecord
from tests.api_helpers import Person, Troupe
from tests.test_api_own_checks import IRON_WILL_FOR_VENTRUE
from tests.test_api_renames import other_troupe, troupe_log

pytestmark = pytest.mark.usefixtures("without_bank")

CHILD = "Child of the Crossroads"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def second(troupe: Troupe, name: str = "Court of Ashes") -> str:
    """Another troupe, which the first troupe's storyteller runs too."""
    troupe_id = other_troupe(troupe, name)
    ok(
        troupe.stranger.client.put(
            f"/troupes/{troupe_id}/staff",
            json={"handle": troupe.storyteller.handle, "role": "storyteller"},
        )
    )
    return troupe_id


def exported(person: Person, troupe_id: str) -> dict[str, Any]:
    return ok(person.client.get(f"/troupes/{troupe_id}/settings-share"))["document"]


def review(person: Person, troupe_id: str, document: dict[str, Any]) -> Any:
    return person.client.post(
        f"/troupes/{troupe_id}/settings-share/review", json={"document": document}
    )


def reviewed(
    person: Person, troupe_id: str, document: dict[str, Any]
) -> dict[tuple[str, str], Any]:
    """Each item reviewed, by section and label."""
    found = ok(review(person, troupe_id, document))
    return {(s["key"], i["label"]): i for s in found["sections"] for i in s["items"]}


def everything(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"section": key, "index": n}
        for key, found in document["sections"].items()
        for n in range(len(found))
    ]


def apply(
    person: Person,
    troupe_id: str,
    document: dict[str, Any],
    items: list[dict[str, Any]] | None = None,
    **source: Any,
) -> Any:
    return person.client.post(
        f"/troupes/{troupe_id}/settings-share/apply",
        json={
            "document": document,
            "items": everything(document) if items is None else items,
            **source,
        },
    )


def picks(document: dict[str, Any], section: str) -> list[dict[str, Any]]:
    return [{"section": section, "index": n} for n in range(len(document["sections"][section]))]


def customise(troupe: Troupe) -> None:
    """Give the troupe a little of everything Customise changes, through its editors."""
    client, base = troupe.storyteller.client, f"/troupes/{troupe.id}"
    ok(client.patch(base, json={"session_xp": 10, "status_by": "staff"}))
    ok(client.put(f"{base}/feeding", json={"feeding": "book", "resonance": True}))
    ok(client.put(f"{base}/diablerie-flaws", json={"setting": "remove"}))
    ok(client.put(f"{base}/clan-rarity", json={"rarities": {"Lasombra": "rare"}}))
    ok(client.put(f"{base}/checks/merits/Calm Heart/1", json={"strength": "note"}))
    ok(client.post(f"{base}/house-checks", json=IRON_WILL_FOR_VENTRUE), 201)
    ok(
        client.post(
            f"{base}/costs",
            json={
                "category": "merits",
                "trait": "Iron Will",
                "scheme": "fixed",
                "rate": 5,
                "text": "Rarer here",
            },
        ),
        201,
    )
    ok(
        client.put(
            f"{base}/creation/skills",
            json={"rules": [{"rating": 4, "picks": 2}, {"rating": 2, "picks": 3}]},
        )
    )
    ok(
        client.post(
            f"{base}/house-traits",
            json={
                "category": "merits",
                "name": CHILD,
                "points": 2,
                "availability": "building",
                "description": "Lords of the Night: knows every back road out of town.",
            },
        ),
        201,
    )
    # Names the house merit, so it must come in after it.
    ok(
        client.post(
            f"{base}/allowances",
            json={
                "action_kind": "general",
                "category": "merits",
                "trait": CHILD,
                "amount": 1,
            },
        ),
        201,
    )
    ok(
        client.put(
            f"{base}/book-traits",
            json={
                "category": "merits",
                "name": "Iron Will",
                "wording": "Lords of the Night: only the Prince's favourites have it.",
                "wording_mode": "replaces",
            },
        )
    )
    ok(
        client.post(
            f"{base}/written-rules",
            json={
                "section": "FAQ",
                "title": "Back roads",
                "body": "Ask the Sheriff.",
                "trait": {"category": "merits", "name": CHILD},
            },
        ),
        201,
    )
    ok(client.put(f"{base}/written-rules-public", json={"public": True}))
    ok(
        client.post(
            f"{base}/teacher-rules",
            json={"category": "skills", "names": ["Lore"], "always": True},
        ),
        201,
    )
    ok(
        client.put(
            f"{base}/specializations/influence_elite_specializations", json={"names": ["Mayor"]}
        )
    )
    ok(
        client.put(
            f"{base}/random-tables", json={"name": "Patrol", "entries": ["Quiet", "[Fight]"]}
        )
    )
    ok(client.post(f"{base}/agencies", json={"name": "The Gazette", "description": "Daily"}), 201)
    ok(client.post(f"{base}/keywords", json={"name": "Hunt", "fields": ["target"], "cost": 2}), 201)
    ok(client.put(f"{base}/languages", json={"mode": "accelerated"}))
    ok(client.put(f"{base}/quest-settings", json={"enabled": True, "requests_per_cycle": 2}))
    ok(client.put(f"{base}/retainer-rules", json={"growth": 2}))
    ok(client.put(f"{base}/location-limit", json={"strength": "note"}))
    ok(
        client.put(
            f"{base}/free-changes",
            json={
                "kind": "date",
                "days": 14,
                "excluded": [{"category": "merits", "name": "Iron Will"}],
            },
        )
    )


# --- exporting ----------------------------------------------------------------------------


def test_only_what_differs_from_the_default_is_exported(troupe: Troupe) -> None:
    fresh = second(troupe)

    found = ok(troupe.storyteller.client.get(f"/troupes/{fresh}/settings-share"))

    document = found["document"]
    assert (document["format"], document["version"]) == ("horatio-troupe-settings", 1)
    assert document["troupe"] == "Court of Ashes"
    assert document["rule_sets"] == {"vampire": document["rule_sets"]["vampire"]}
    assert all(items == [] for items in document["sections"].values())
    assert [s["count"] for s in found["sections"]] == [0] * len(share.SECTIONS)
    assert found["sections"][0] == {
        "key": "who_may_join",
        "label": "Who may join",
        "group": "Troupe settings",
        "count": 0,
    }

    ok(troupe.storyteller.client.patch(f"/troupes/{fresh}", json={"session_xp": 8}))
    assert exported(troupe.storyteller, fresh)["sections"]["xp"] == []
    ok(troupe.storyteller.client.patch(f"/troupes/{fresh}", json={"session_xp": 10}))
    assert exported(troupe.storyteller, fresh)["sections"]["xp"] == [
        {"type": "setting", "key": "session_xp", "value": 10}
    ]


def test_archived_and_retired_items_are_not_exported(troupe: Troupe) -> None:
    client, base = troupe.storyteller.client, f"/troupes/{troupe.id}"
    house = ok(
        client.post(
            f"{base}/house-traits",
            json={"category": "merits", "name": CHILD, "points": 2, "availability": "staff"},
        ),
        201,
    )
    ok(client.put(f"{base}/house-traits/{house['id']}/archived", json={"archived": True}))
    agency = ok(client.post(f"{base}/agencies", json={"name": "The Gazette"}), 201)
    ok(client.post(f"/agencies/{agency['id']}/retire"))
    ok(client.put(f"{base}/keywords/rhetorical/retired", json={"retired": True}))

    sections = exported(troupe.storyteller, troupe.id)["sections"]

    assert (sections["house_traits"], sections["news_agencies"], sections["keywords"]) == (
        [],
        [],
        [],
    )


def test_running_staff_export_and_only_storytellers_import(troupe: Troupe) -> None:
    customise(troupe)
    document = exported(troupe.assistant, troupe.id)
    fresh = second(troupe)

    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/settings-share").status_code == 403
    assert troupe.player.client.get(f"/troupes/{troupe.id}/settings-share").status_code == 403
    assert review(troupe.assistant, troupe.id, document).status_code == 403
    assert review(troupe.narrator, troupe.id, document).status_code == 403
    assert apply(troupe.assistant, troupe.id, document).status_code == 403
    # The storyteller runs both; the lead of the second runs only that one.
    assert troupe.stranger.client.get(f"/troupes/{troupe.id}/settings-share").status_code == 403
    copied = apply(troupe.stranger, fresh, document, from_troupe_id=troupe.id)
    assert copied.status_code == 403
    assert exported(troupe.stranger, fresh)["sections"]["house_traits"] == []


def test_nothing_is_imported_into_an_archived_troupe(troupe: Troupe) -> None:
    document = exported(troupe.storyteller, troupe.id)
    fresh = second(troupe)
    ok(troupe.custodian.client.post(f"/troupes/{fresh}/archive", json={"reason": "Ended"}))

    assert review(troupe.custodian, fresh, document).status_code == 409
    assert apply(troupe.custodian, fresh, document).status_code == 409


# --- importing ------------------------------------------------------------------------------


def test_a_round_trip_gives_the_new_troupe_the_same_rules(troupe: Troupe) -> None:
    customise(troupe)
    document = exported(troupe.storyteller, troupe.id)
    fresh = second(troupe)

    applied = ok(apply(troupe.storyteller, fresh, document, from_troupe_id=troupe.id))

    assert applied["changed"] > 0 and applied["added"] > 0
    copied = exported(troupe.storyteller, fresh)
    assert copied["sections"] == document["sections"]
    assert {i["status"] for i in reviewed(troupe.storyteller, fresh, document).values()} == {"same"}
    # The rules the new troupe's characters play by follow.
    costs = ok(troupe.storyteller.client.get(f"/troupes/{fresh}/costs"))["costs"]
    assert any(c["trait"] == "Iron Will" and c["price_text"] == "5 XP" for c in costs)
    allowances = ok(troupe.storyteller.client.get(f"/troupes/{fresh}/allowances"))["rules"]
    assert any(r["trait"] == CHILD and r["house"] for r in allowances)


def test_the_review_marks_new_changed_same_and_cant_import(troupe: Troupe) -> None:
    customise(troupe)
    document = exported(troupe.storyteller, troupe.id)
    fresh = second(troupe)
    client, base = troupe.storyteller.client, f"/troupes/{fresh}"
    ok(client.patch(base, json={"session_xp": 10}))
    ok(
        client.post(
            f"{base}/house-traits",
            json={"category": "merits", "name": CHILD, "points": 1, "availability": "building"},
        ),
        201,
    )

    found = reviewed(troupe.storyteller, fresh, document)

    assert found[("xp", "Session XP")]["status"] == "same"
    status = found[("status_titles", "Who keeps fleeting and negative status")]
    assert (status["status"], status["before"], status["after"]) == (
        "changes",
        "Players",
        "Staff only",
    )
    child = found[("house_traits", f"★ {CHILD} (house merit)")]
    assert child["status"] == "changes"
    assert "Points: 1" in child["before"] and "Points: 2" in child["after"]
    assert [e["field"] for e in child["editable"]] == ["name", "description", "requirement"]
    assert found[("costs", "Iron Will")]["status"] == "new"
    assert found[("book_traits", "Iron Will")]["editable"][0]["field"] == "wording"


def test_items_that_cant_be_found_here_cant_be_imported(troupe: Troupe) -> None:
    document = {
        "format": "horatio-troupe-settings",
        "version": 1,
        "troupe": "Elsewhere",
        "sections": {
            "costs": [
                {
                    "type": "cost",
                    "category": "merits",
                    "trait": "Sorcerous Pickles",
                    "scheme": "fixed",
                    "rate": 2,
                }
            ],
            "book_traits": [
                {"type": "book_trait", "category": "merits", "name": "Sorcerous Pickles"}
            ],
            "checks": [{"type": "check", "check": "merits/Nope/1", "strength": "off"}],
            "house_traits": [
                {
                    "type": "house_trait",
                    "splat": "werewolf",
                    "category": "merits",
                    "name": "Moon Touched",
                    "points": 1,
                    "availability": "staff",
                }
            ],
            # A setting in the wrong section, and one this Horatio doesn't have.
            "feeding": [
                {"type": "setting", "key": "session_xp", "value": 9},
                {"type": "setting", "key": "moon_phase", "value": "full"},
            ],
        },
    }

    found = reviewed(troupe.storyteller, troupe.id, document)

    assert {k: (i["status"], i["reason"]) for k, i in found.items()} == {
        ("costs", "Sorcerous Pickles"): (
            "cannot",
            "Sorcerous Pickles isn't in this troupe's rule set.",
        ),
        ("book_traits", "Sorcerous Pickles"): (
            "cannot",
            "Sorcerous Pickles isn't in this troupe's rule set.",
        ),
        ("checks", "merits/Nope/1"): ("cannot", "Not a check in this troupe's rule set."),
        ("house_traits", "★ Moon Touched (house merit) for werewolfs"): (
            "cannot",
            "This Horatio has no rules for werewolf characters.",
        ),
        ("feeding", "Session XP"): ("cannot", "It belongs under XP."),
        ("feeding", "moon_phase"): ("cannot", "Not a setting this Horatio has."),
    }
    refused = apply(troupe.storyteller, troupe.id, document, picks(document, "costs"))
    assert refused.status_code == 422
    assert refused.json()["detail"] == (
        "Costs › Sorcerous Pickles: Sorcerous Pickles isn't in this troupe's rule set."
    )


def test_an_import_merges_and_leaves_the_rest_alone(troupe: Troupe) -> None:
    customise(troupe)
    document = exported(troupe.storyteller, troupe.id)
    fresh = second(troupe)
    client, base = troupe.storyteller.client, f"/troupes/{fresh}"
    ok(client.patch(base, json={"downtime_xp": 5}))
    ok(
        client.post(
            f"{base}/house-traits",
            json={
                "category": "flaws",
                "name": "Hearth-bound",
                "points": 1,
                "availability": "staff",
            },
        ),
        201,
    )
    ok(
        client.post(
            f"{base}/costs",
            json={"category": "merits", "trait": "Calm Heart", "scheme": "fixed", "rate": 4},
        ),
        201,
    )
    ok(client.put(f"{base}/random-tables", json={"name": "Patrol", "entries": ["Old"]}))
    ok(client.put(f"{base}/random-tables", json={"name": "Weather", "entries": ["Rain"]}))
    ok(
        client.put(
            f"{base}/specializations/influence_elite_specializations",
            json={"names": ["Police Chief"]},
        )
    )
    ok(client.post(f"{base}/house-checks", json=IRON_WILL_FOR_VENTRUE), 201)

    ok(apply(troupe.storyteller, fresh, document))

    after = exported(troupe.storyteller, fresh)["sections"]
    assert {"type": "setting", "key": "downtime_xp", "value": 5} in after["xp"]
    assert sorted(h["name"] for h in after["house_traits"]) == [CHILD, "Hearth-bound"]
    assert sorted(c["trait"] for c in after["costs"]) == ["Calm Heart", "Iron Will"]
    # A fill table of the same name has the imported entries; another is left be.
    assert {t["name"]: t["entries"] for t in after["fill_tables"]} == {
        "Patrol": ["Quiet", "[Fight]"],
        "Weather": ["Rain"],
    }
    # Specialisations are only added; an identical house check isn't added twice.
    assert [s["name"] for s in after["specialisations"]] == ["Mayor", "Police Chief"]
    assert len(after["checks"]) == len(document["sections"]["checks"])


def test_unticked_items_and_sections_are_left_out(troupe: Troupe) -> None:
    customise(troupe)
    document = exported(troupe.storyteller, troupe.id)
    fresh = second(troupe)
    chosen = [p for p in everything(document) if p["section"] != "book_traits"]

    applied = ok(apply(troupe.storyteller, fresh, document, chosen))

    assert "book_traits" not in [s["key"] for s in applied["sections"]]
    assert exported(troupe.storyteller, fresh)["sections"]["book_traits"] == []


def test_edited_text_is_what_comes_in(troupe: Troupe) -> None:
    customise(troupe)
    document = exported(troupe.storyteller, troupe.id)
    fresh = second(troupe)
    # What the review's find & replace does: the source troupe's name made this one's.
    edited = copy.deepcopy(document)
    for item in edited["sections"]["book_traits"] + edited["sections"]["house_traits"]:
        for field in ("wording", "description"):
            if field in item:
                item[field] = item[field].replace("Lords of the Night", "Court of Ashes")

    ok(apply(troupe.storyteller, fresh, edited))

    traits = ok(troupe.storyteller.client.get(f"/troupes/{fresh}/book-traits"))["changes"]
    iron_will = next(t for t in traits if t["name"] == "Iron Will")
    assert iron_will["wording"] == "Court of Ashes: only the Prince's favourites have it."
    house = exported(troupe.storyteller, fresh)["sections"]["house_traits"][0]
    assert house["description"] == "Court of Ashes: knows every back road out of town."


def test_a_failure_names_the_item_and_saves_nothing(troupe: Troupe) -> None:
    customise(troupe)
    document = exported(troupe.storyteller, troupe.id)
    broken = copy.deepcopy(document)
    broken["sections"]["checks"].append(
        {**IRON_WILL_FOR_VENTRUE, "type": "house_check", "condition": {"clan": ["Martians"]}}
    )
    fresh = second(troupe)

    refused = apply(troupe.storyteller, fresh, broken)

    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == (
        "Checks › Iron Will is for the Ventrue here.: Martians: no such clan in these rules."
    )
    assert (
        exported(troupe.storyteller, fresh)["sections"]
        == exported(troupe.custodian, other_troupe(troupe, "Untouched"))["sections"]
    )


def test_the_log_says_who_imported_what_from_where(troupe: Troupe) -> None:
    customise(troupe)
    document = exported(troupe.storyteller, troupe.id)
    fresh = second(troupe)
    chosen = picks(document, "house_traits") + picks(document, "xp")

    ok(apply(troupe.storyteller, fresh, document, chosen, file_name="lords-settings.json"))

    log = troupe_log(troupe.storyteller, fresh)
    assert log[0] == (
        "storyteller imported settings from lords-settings.json:"
        " XP (1 changed); House merits and flaws (1 added)."
    )
    # One entry for the whole: none for each item.
    assert not any("made a house merit" in m for m in log)


# --- the file -------------------------------------------------------------------------------


def test_a_malformed_or_oversized_file_is_refused(troupe: Troupe) -> None:
    document = exported(troupe.storyteller, troupe.id)

    assert review(troupe.storyteller, troupe.id, {**document, "format": "other"}).status_code == 422
    assert review(troupe.storyteller, troupe.id, {**document, "sneaky": True}).status_code == 422
    sneaky = copy.deepcopy(document)
    sneaky["sections"]["fill_tables"] = [{"type": "fill_table", "name": "X", "id": "1"}]
    assert review(troupe.storyteller, troupe.id, sneaky).status_code == 422
    wrong = copy.deepcopy(document)
    wrong["sections"]["costs"] = [{"type": "house_trait", "name": "X"}]
    assert review(troupe.storyteller, troupe.id, wrong).status_code == 422
    huge = copy.deepcopy(document)
    huge["sections"]["fill_tables"] = [
        {"type": "fill_table", "name": f"Table {n}", "entries": ["x" * 1999] * 10}
        for n in range(120)
    ]
    assert review(troupe.storyteller, troupe.id, huge).status_code == 413
    out_of_range = apply(troupe.storyteller, troupe.id, document, [{"section": "xp", "index": 3}])
    assert out_of_range.status_code == 422


def test_every_troupe_setting_and_table_is_exported_or_said_not_to_be() -> None:
    """A new column on `troupes`, or a new table that belongs to a troupe, must go in a
    section of the export, or on a list of what isn't carried, with why."""
    columns = {c.name for c in TroupeRecord.__table__.columns}
    exported_columns = set(share.SETTINGS)
    assert not exported_columns & set(share.NOT_EXPORTED_COLUMNS)
    assert columns - exported_columns - set(share.NOT_EXPORTED_COLUMNS) == set()
    assert exported_columns | set(share.NOT_EXPORTED_COLUMNS) <= columns

    troupes = TroupeRecord.__table__
    owned = {
        table.name
        for table in Base.metadata.tables.values()
        if table is not troupes
        and any(fk.column.table is troupes for c in table.columns for fk in c.foreign_keys)
    }
    assert not set(share.EXPORTED_TABLES) & set(share.NOT_EXPORTED_TABLES)
    assert owned - set(share.EXPORTED_TABLES) - set(share.NOT_EXPORTED_TABLES) == set()
    assert set(share.EXPORTED_TABLES) | set(share.NOT_EXPORTED_TABLES) <= owned
    assert all(share.NOT_EXPORTED_COLUMNS.values()) and all(share.NOT_EXPORTED_TABLES.values())

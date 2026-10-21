"""Game badges (issue #70): what they show, who prints them, the staff's visible
note, and the clan logos the custodian uploads."""

import tomllib
import uuid
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.badges import wording
from horatio.config import get_settings
from horatio.models import CharacterTrait, TraitCategory, TraitDefinition
from horatio.rules.files import DATA_DIR
from tests.api_helpers import Troupe
from tests.test_api_character_search import member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


def give(troupe: Troupe, character_id: str, *traits: tuple[str, str, int | None, str]) -> None:
    """Put traits straight on the sheet: (category, name, rating, detail)."""
    for category, name, rating, detail in traits:
        definition = troupe.session.scalars(
            select(TraitDefinition)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(TraitCategory.key == category, TraitDefinition.name == name)
        ).one()
        troupe.session.add(
            CharacterTrait(
                character_id=uuid.UUID(character_id),
                trait_definition_id=definition.id,
                rating=rating,
                detail=detail,
            )
        )
    troupe.session.flush()


def logo_png() -> bytes:
    out = BytesIO()
    Image.new("RGBA", (64, 40), (200, 160, 60, 255)).save(out, "PNG")
    return out.getvalue()


def badge_of(troupe: Troupe, name: str, **query: Any) -> dict[str, Any]:
    response = troupe.lead.client.get(f"/troupes/{troupe.id}/badges", params=query)
    assert response.status_code == 200, response.text
    return {b["name"]: b for b in response.json()["badges"]}[name]


def test_a_badge_shows_who_the_character_is(troupe: Troupe) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")
    give(
        troupe,
        agnes,
        ("backgrounds", "Generation", 2, ""),
        ("merits", "Machiavellian Prodigy", None, ""),
        ("status_traits", "Acknowledged", 1, ""),
        ("status_traits", "Loyal", 1, ""),
        ("flaws", "Eerie Presence", None, "cold breeze"),
        ("flaws", "Eerie Presence", None, "glowing eyes"),
        ("merits", "Personal Masquerade", None, ""),
        ("paths", "Caine", 4, ""),
    )
    titled = troupe.lead.client.put(
        f"/troupes/{troupe.id}/characters/{agnes}/titles", json={"titles": ["Harpy"]}
    )
    assert titled.status_code == 200, titled.text

    badge = badge_of(troupe, "Agnes")

    assert badge["clan"] == "Toreador"
    # Generation 2 is an Ancilla; Machiavellian Prodigy treats her as one class higher.
    assert badge["social_age"] == "Elder"
    assert badge["titles"] == ["Harpy"]
    assert badge["status"] == ["Acknowledged", "Loyal"]
    assert sorted(badge["visible"]) == [
        "Appears alive",
        "Eerie Presence: cold breeze",
        "Eerie Presence: glowing eyes",
        "Path of Caine",
    ]
    assert (badge["picture"], badge["logo"]) == (None, None)


def test_humanity_and_hidden_traits_are_not_visible(troupe: Troupe) -> None:
    nell = member(troupe, troupe.player, "Nell", "Giovanni")
    give(troupe, nell, ("merits", "Acute Sense", None, ""))
    give(troupe, nell, ("flaws", "Accused of Heresy", None, ""))
    badge = badge_of(troupe, "Nell")
    assert badge["visible"] == []  # Humanity, a starting trait, does not show
    assert badge["social_age"] == "Neonate"


def test_wording_without_a_detail() -> None:
    assert wording("Eerie Presence: {detail}", "") == "Eerie Presence"
    assert wording("Eerie Presence: {detail}", "chill") == "Eerie Presence: chill"
    assert wording("Appears alive", "anything") == "Appears alive"


def test_every_path_but_humanity_is_visible_in_the_rules_data() -> None:
    data = tomllib.loads((DATA_DIR / "bns_met_vampire_traits.toml").read_text())
    paths = {t["name"]: t.get("properties", {}) for t in data["traits"] if t["category"] == "paths"}
    assert "visible" not in paths.pop("Humanity")
    assert all(p.get("visible", "").startswith("Path of") for p in paths.values()), paths


def test_staff_write_a_visible_note(troupe: Troupe) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")
    url = f"/characters/{agnes}/visible-note"
    assert troupe.player.client.put(url, json={"note": "Smells of roses"}).status_code == 403
    assert troupe.narrator.client.put(url, json={"note": "x"}).status_code == 404
    said = troupe.assistant.client.put(url, json={"note": "  Smells of roses \n\n Wet footprints "})
    assert said.status_code == 200, said.text
    assert said.json()["note"] == "Smells of roses\nWet footprints"
    assert badge_of(troupe, "Agnes")["visible"] == ["Smells of roses", "Wet footprints"]
    assert troupe.player.client.get(url).json()["note"] == "Smells of roses\nWet footprints"
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert not any("badge" in m for m in log)  # visiting: it is not the home troupe's
    character_log = troupe.player.client.get(f"/characters/{agnes}/log").json()
    assert any("badge" in e["message"] for e in character_log)


def test_who_prints_badges(troupe: Troupe, client_for: Callable[[], TestClient]) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")
    nell = member(troupe, troupe.player, "Nell", "Giovanni")
    for nobody in (troupe.narrator, troupe.player, troupe.stranger):
        assert nobody.client.get(f"/troupes/{troupe.id}/badges").status_code == 403
        assert nobody.client.get(f"/troupes/{troupe.id}/staff-badges").status_code == 403
    every = troupe.lead.client.get(f"/troupes/{troupe.id}/badges").json()
    assert [b["name"] for b in every["badges"]] == ["Agnes", "Nell"]
    chosen = troupe.storyteller.client.get(
        f"/troupes/{troupe.id}/badges", params={"characters": [nell, agnes]}
    )
    assert [b["name"] for b in chosen.json()["badges"]] == ["Nell", "Agnes"]
    elsewhere = member(troupe, sign_up_other(client_for), "Ida", "Brujah")
    troupe.session.flush()
    left = troupe.lead.client.get(
        f"/troupes/{troupe.id}/badges", params={"characters": [str(uuid.uuid4())]}
    )
    assert left.status_code == 404
    # One badge from the character's page.
    one = troupe.lead.client.get(f"/characters/{elsewhere}/badge").json()
    assert (one["troupe_name"], [b["name"] for b in one["badges"]]) == (
        "Lords of the Night",
        ["Ida"],
    )
    assert troupe.stranger.client.get(f"/characters/{agnes}/badge").status_code == 404


def sign_up_other(client_for: Callable[[], TestClient]) -> Any:
    from tests.api_helpers import sign_up

    return sign_up(client_for, "other")


def test_storyteller_badges(troupe: Troupe) -> None:
    staff = troupe.assistant.client.get(f"/troupes/{troupe.id}/staff-badges").json()
    assert staff["troupe_name"] == "Lords of the Night"
    assert staff["staff"] == [
        {"name": "lead", "role": "Lead Storyteller"},
        {"name": "storyteller", "role": "Storyteller"},
        {"name": "assistant", "role": "Assistant Storyteller"},
        {"name": "narrator", "role": "Narrator"},
    ]


def test_the_custodian_uploads_clan_logos(troupe: Troupe, kept: Path) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Brujah: True Brujah")
    member(troupe, troupe.player, "Nell", "Giovanni")

    listed = troupe.lead.client.get("/clan-logos").json()
    assert listed["available"] is True
    names = [c["clan"] for c in listed["clans"]]
    assert "Toreador" in names and "Brujah: True Brujah" in names
    assert all(c["logo"] is None for c in listed["clans"])

    files = {"file": ("brujah.png", logo_png(), "image/png")}
    refused = troupe.lead.client.post("/clan-logos", data={"clan": "Brujah"}, files=files)
    assert refused.status_code == 403
    unknown = troupe.custodian.client.post("/clan-logos", data={"clan": "Nope"}, files=files)
    assert unknown.status_code == 404
    made = troupe.custodian.client.post("/clan-logos", data={"clan": "Brujah"}, files=files)
    assert made.status_code == 200, made.text
    logo = made.json()["logo"]

    # Fitted into squares, transparency kept, for anyone signed in.
    for size in (128, 600):
        image = Image.open(BytesIO(troupe.player.client.get(f"{logo[4:]}/{size}.webp").content))
        assert (image.size, image.mode) == ((size, size), "RGBA")
        assert image.getpixel((0, 0))[3] == 0  # type: ignore[index]
    assert troupe.player.client.get(f"{logo[4:]}/secret.webp").status_code == 404

    # The bloodline takes its clan's logo; a clan without one has none.
    assert badge_of(troupe, "Agnes")["logo"] == logo
    assert badge_of(troupe, "Nell")["logo"] is None
    one = troupe.player.client.get(f"/characters/{agnes}/badge").json()["badges"][0]
    assert one["logo"] == logo

    # A new upload replaces it; removing it leaves the name only.
    again = troupe.custodian.client.post("/clan-logos", data={"clan": "Brujah"}, files=files)
    assert again.json()["logo"] != logo
    assert len(list((kept / "clan-logos").iterdir())) == 1
    assert troupe.lead.client.delete(f"/clan-logos/{again.json()['logo_id']}").status_code == 403
    gone = troupe.custodian.client.delete(f"/clan-logos/{again.json()['logo_id']}")
    assert gone.status_code == 204
    assert badge_of(troupe, "Agnes")["logo"] is None
    assert not list((kept / "clan-logos").iterdir())

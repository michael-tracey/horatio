"""Clan crypt card templates for Jyhad cards (#850): finding their layout, matching
a file to its clan and a character to its template, and the custodian's upload,
on templates drawn here like the 2020 ones (the real ones are the Dark Pack's and
never in the repo)."""

import uuid
import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from horatio import crypt_templates
from horatio.config import get_settings
from horatio.crypt_templates import LAYOUT, chosen, detect, key_of, wanted
from horatio.models import Character
from horatio.rules.files import DATA_DIR, load_rule_set
from tests.api_helpers import Person, Troupe
from tests.test_api_audit import messages
from tests.test_api_sect_status import member


def template(colour: tuple[int, int, int] = (60, 70, 50), oval_at: int = 194) -> Image.Image:
    """A stand-in for a 2020 template: the frame, its transparent oval, the light
    line down the sidebar, the pale text box and the red drop where they are."""
    image = Image.new("RGBA", crypt_templates.SIZE, (*colour, 255))
    draw = ImageDraw.Draw(image)
    x, y, w, h = LAYOUT["sidebar"]
    draw.rectangle((x + w, 0, x + w + 4, 1113), fill=(150, 150, 150, 255))
    x, y, w, h = LAYOUT["text"]
    draw.rectangle((x, y, x + w - 1, y + h - 1), fill=(205, 200, 185, 255))
    x, y, w, h = LAYOUT["drop"]
    draw.ellipse((x, y, x + w - 1, y + h - 1), fill=(200, 20, 20, 255))
    _, y, w, h = LAYOUT["oval"]
    draw.ellipse((oval_at, y, oval_at + w - 1, y + h - 1), fill=(0, 0, 0, 0))
    return image


def png(image: Image.Image) -> bytes:
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def zipped(files: dict[str, bytes]) -> bytes:
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


def test_detect_finds_the_layout_the_card_uses() -> None:
    found = detect(template())

    assert found.oval == LAYOUT["oval"]
    assert found.text == LAYOUT["text"]
    assert found.drop == LAYOUT["drop"]
    x, _, w, _ = LAYOUT["sidebar"]
    assert found.sidebar_edge is not None and abs(found.sidebar_edge - (x + w)) <= 1


def test_the_layout_in_millimetres() -> None:
    # The card is 63 × 88 mm inside a 1/8" bleed: the whole template is about 69.35 mm wide.
    assert crypt_templates.to_mm((0, 0, 819, 1114)) == (-3.17, -3.17, 69.37, 94.35)
    assert crypt_templates.to_mm(LAYOUT["oval"]) == (13.26, 9.78, 44.97, 58.35)


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("2020_Crypt_Tzimisce.png", "tzimisce"),
        ("templates/2020_Crypt_BrujahAntitribu.png", "brujahantitribu"),
        ("2020_Crypt_Salubri (1).png", "salubri"),
        ("2020_crypt_blood brother.PNG", "bloodbrother"),
        ("2020_Crypt_DaughterofCacophony.png", "daughterofcacophony"),
        ("2020_Crypt_Unicorn.png", None),
        ("Tzimisce.png", None),
        ("2020_Crypt_Tzimisce.webp", None),
    ],
)
def test_a_file_s_clan_comes_from_its_name(name: str, key: str | None) -> None:
    assert key_of(name) == key


@pytest.mark.parametrize(
    ("clan", "sect", "expected"),
    [
        ("Tremere", "Camarilla", ["tremere"]),
        ("Tremere", "Sabbat", ["tremereantitribu", "tremere"]),
        ("Tremere: Telyav", None, ["tremere"]),
        ("Brujah: True Brujah", "Sabbat", ["truebrujah"]),
        ("Gangrel: Ahrimanes", None, ["ahrimane"]),
        ("Caitiff", "Sabbat", ["pander", "caitiff"]),
        ("Caitiff", "Anarch", ["caitiff"]),
        ("Tzimisce", "Sabbat", ["tzimisce"]),
        ("Cappadocians: Samedi", None, ["samedi"]),
        ("Cappadocians", None, []),
        ("Lhiannan", None, []),
        (None, None, []),
    ],
)
def test_which_templates_a_character_would_use(
    clan: str | None, sect: str | None, expected: list[str]
) -> None:
    assert wanted(clan, sect) == expected


def test_a_sabbat_character_without_the_antitribu_s_template_takes_the_clan_s() -> None:
    assert chosen("Ventrue", "Sabbat", {"ventrue", "ventrueantitribu"}) == "ventrueantitribu"
    assert chosen("Ventrue", "Sabbat", {"ventrue"}) == "ventrue"
    assert chosen("Ventrue", "Sabbat", set()) is None


def test_every_clan_in_the_map_is_in_the_rules_and_has_a_template() -> None:
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    clans = {name for category, name in rule_set.traits if category == "clan"}
    assert set(crypt_templates.CLANS) <= clans
    assert set(crypt_templates.CLANS.values()) <= set(crypt_templates.TEMPLATES)
    # Every antitribu has its clan.
    for key in crypt_templates.TEMPLATES:
        if key.endswith("antitribu"):
            assert key.removesuffix("antitribu") in crypt_templates.TEMPLATES


# --- the custodian's upload and the card ----------------------------------------------------


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "dark-pack"
    monkeypatch.setattr(get_settings(), "dark_pack_dir", str(out))
    return out


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def upload(person: Person, files: list[tuple[str, bytes]], accept: str = "true") -> Any:
    return person.client.post(
        "/tools/crypt-templates",
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
        data={"accept_licence": accept},
    )


def test_the_custodian_uploads_a_zip_and_pngs(troupe: Troupe, folder: Path) -> None:
    assert upload(troupe.player, [("2020_Crypt_Tremere.png", png(template()))]).status_code == 403
    refused = upload(troupe.custodian, [("2020_Crypt_Tremere.png", png(template()))], "false")
    assert refused.status_code == 422

    archive = zipped(
        {
            "crypt/2020_Crypt_Tremere.png": png(template()),
            "crypt/2020_Crypt_Tremere (1).png": png(template()),
            "crypt/2020_Crypt_Unicorn.png": png(template()),
            "crypt/2020_Crypt_Ventrue.png": png(template(oval_at=150)),
            "crypt/readme.txt": b"left out",
        }
    )
    response = upload(
        troupe.custodian,
        [("crypt.zip", archive), ("2020_Crypt_TremereAntitribu.png", png(template()))],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["added"] == ["Tremere", "Tremere antitribu"]
    assert {s["name"]: s["why"] for s in body["skipped"]} == {
        "2020_Crypt_Tremere (1).png": "the same clan as 2020_Crypt_Tremere.png",
        "2020_Crypt_Unicorn.png": "not a 2020_Crypt_<Clan>.png file of a clan Horatio knows",
        "2020_Crypt_Ventrue.png": "its portrait's oval isn't where the 2020 templates have it",
    }
    tool = body["tool"]
    assert [t["key"] for t in tool["templates"]] == ["tremere", "tremereantitribu"]
    assert {m["name"]: m["symbol"] for m in tool["clans"]}["Tremere"] == (
        "Tremere; Sabbat: Tremere antitribu"
    )
    assert "Ventrue" in tool["missing"]
    assert sorted(p.name for p in (folder / "crypt-templates").iterdir()) == [
        "manifest.json",
        "tremere.webp",
        "tremereantitribu.webp",
    ]
    stored = Image.open(folder / "crypt-templates" / "tremere.webp")
    assert stored.size == crypt_templates.SIZE and stored.mode == "RGBA"
    assert "custodian uploaded 2 Jyhad card templates: Tremere, Tremere antitribu." in messages(
        troupe.custodian
    )

    # Another upload adds to them; only a template of a clan already here replaces it.
    again = upload(troupe.custodian, [("2020_Crypt_Ventrue.png", png(template()))])
    assert [t["key"] for t in again.json()["tool"]["templates"]] == [
        "tremere",
        "tremereantitribu",
        "ventrue",
    ]
    nothing = upload(troupe.custodian, [("notes.txt", b"hello")])
    assert nothing.status_code == 422
    assert "None of those is a template" in nothing.json()["detail"]


def test_a_card_is_drawn_on_its_clan_s_template_for_whoever_can_see_it(
    troupe: Troupe, folder: Path
) -> None:
    upload(
        troupe.custodian,
        [
            ("2020_Crypt_Tremere.png", png(template((90, 10, 10)))),
            ("2020_Crypt_TremereAntitribu.png", png(template((10, 10, 90)))),
        ],
    )
    varga = member(troupe, "Varga", clan="Tremere")
    goratrix = member(troupe, "Goratrix", clan="Tremere", sect="Sabbat")
    agnes = member(troupe, "Agnes", clan="Ventrue")
    for character_id in (varga, goratrix, agnes):
        troupe.session.get_one(Character, uuid.UUID(character_id)).picture_id = uuid.uuid4()
    troupe.session.flush()

    def card(character_id: str) -> dict[str, object]:
        response = troupe.player.client.get(f"/characters/{character_id}/jyhad-card")
        assert response.status_code == 200, response.text
        return response.json()

    shown = card(varga)["template"]
    assert isinstance(shown, str)
    assert shown.startswith(f"/api/characters/{varga}/jyhad-card/template.webp?v=")
    # The antitribu's for the Sabbat; Horatio's frame where there is no template.
    assert card(agnes)["template"] is None

    def pixel(character_id: str) -> tuple[int, ...]:
        response = troupe.player.client.get(f"/characters/{character_id}/jyhad-card/template.webp")
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/webp"
        return Image.open(BytesIO(response.content)).convert("RGB").getpixel((100, 100))  # type: ignore[return-value]

    assert pixel(varga)[0] > 60 and pixel(goratrix)[2] > 60
    assert (
        troupe.player.client.get(f"/characters/{agnes}/jyhad-card/template.webp").status_code == 404
    )
    assert (
        troupe.stranger.client.get(f"/characters/{varga}/jyhad-card/template.webp").status_code
        == 404
    )

    removed = troupe.custodian.client.delete("/tools/crypt-templates")
    assert removed.status_code == 200, removed.text
    assert removed.json()["templates"] == []
    assert card(varga)["template"] is None
    assert "custodian removed the Jyhad card templates from the server." in messages(
        troupe.custodian
    )


def test_without_the_dark_pack_folder_there_are_no_templates(
    troupe: Troupe, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "dark_pack_dir", None)
    tool = troupe.custodian.client.get("/tools/crypt-templates").json()
    assert (tool["configured"], tool["templates"]) == (False, [])
    refused = upload(troupe.custodian, [("2020_Crypt_Tremere.png", png(template()))])
    assert refused.status_code == 422

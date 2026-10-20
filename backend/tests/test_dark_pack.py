"""Paradox's Dark Pack resources (issue #92): imported from the kits' zips into a
folder Horatio never ships, then the Dark Pack logo for the About page and the
clans' symbols for badges where the custodian has uploaded none."""

import json
import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from horatio import dark_pack
from horatio.config import get_settings
from horatio.rules.files import DATA_DIR, load_rule_set
from tests.api_helpers import Troupe
from tests.test_api_badges import badge_of, kept, logo_png  # noqa: F401
from tests.test_api_character_search import member

KIT = "World of Darkness Community Assets"
CLANS = f"{KIT}/Vampire The Masquerade/Clans - Vampire The Masquerade"


def png(colour: tuple[int, int, int, int], size: tuple[int, int] = (80, 80)) -> bytes:
    out = BytesIO()
    Image.new("RGBA", size, colour).save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def kit(tmp_path: Path) -> Path:
    """A stand-in for Paradox's kit: the Dark Pack logo, and Brujah's symbol in
    black and white, at the paths the real kit has them."""
    path = tmp_path / f"{KIT}.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{KIT}/Dark Pack/DarkPack_Logo_Color.png", png((180, 20, 20, 255), (900, 900)))
        z.writestr(f"{KIT}/Dark Pack/DarkPack_Logo_BW.png", png((0, 0, 0, 255)))
        z.writestr(f"{CLANS}/Brujah/VTM_Brujah_Symbol.png", png((0, 0, 0, 255)))
        z.writestr(f"{CLANS}/Brujah/VTM_Brujah_Symbol_White.png", png((255, 255, 255, 255)))
        z.writestr(f"{KIT}/Illustrations/Scenes/Scene1.jpg", b"not needed")
    return path


@pytest.fixture
def imported(kit: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "dark-pack"
    dark_pack.import_kits([kit], out)
    monkeypatch.setattr(get_settings(), "dark_pack_dir", str(out))
    return out


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def test_the_import_writes_only_what_horatio_uses(kit: Path, tmp_path: Path) -> None:
    out = tmp_path / "dark-pack"
    record = dark_pack.import_kits([kit], out)

    assert set(record["logos"]) == {"logo.webp", "logo-bw.webp"}
    assert set(record["clans"]) == {"Brujah"}
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    assert files == [
        "clans/brujah/128.webp",
        "clans/brujah/600.webp",
        "clans/brujah/white/128.webp",
        "clans/brujah/white/600.webp",
        "logo-bw.webp",
        "logo.webp",
        "manifest.json",
    ]
    assert Image.open(out / "logo.webp").width == dark_pack.LOGO_WIDTH
    assert json.loads((out / "manifest.json").read_text())["clans"]["Brujah"]["slug"] == "brujah"


def test_the_logo_is_public_and_symbols_need_a_sign_in(
    imported: Path, troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    anyone = client_for()
    about = anyone.get("/dark-pack").json()
    assert about == {"logo": True, "clans": ["Brujah"]}
    assert anyone.get("/dark-pack/logo.webp").headers["content-type"] == "image/webp"
    assert anyone.get("/dark-pack/clans/brujah/600.webp").status_code == 401
    assert troupe.player.client.get("/dark-pack/clans/brujah/600.webp").status_code == 200
    assert troupe.player.client.get("/dark-pack/clans/brujah/white/128.webp").status_code == 200
    # Only names the import writes are looked up.
    for path in ("manifest.json", "clans/brujah/..%2F..%2Fmanifest.json", "clans/BRUJAH/600.webp"):
        assert troupe.player.client.get(f"/dark-pack/{path}").status_code == 404


def test_without_the_folder_there_is_nothing(
    troupe: Troupe, client_for: Callable[[], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "dark_pack_dir", None)
    assert client_for().get("/dark-pack").json() == {"logo": False, "clans": []}
    assert client_for().get("/dark-pack/logo.webp").status_code == 404
    agnes = member(troupe, troupe.player, "Agnes", "Brujah")
    assert agnes
    assert badge_of(troupe, "Agnes")["logo"] is None


def test_badges_use_the_symbol_until_the_custodian_uploads_one(
    imported: Path,
    troupe: Troupe,
    kept: Path,  # noqa: F811
) -> None:
    member(troupe, troupe.player, "Agnes", "Brujah: True Brujah")
    member(troupe, troupe.player, "Nell", "Giovanni")

    # The bloodline takes its clan's symbol; a clan the kit lacks has none.
    agnes = badge_of(troupe, "Agnes")
    assert agnes["logo"] == "/api/dark-pack/clans/brujah"
    assert agnes["logo_white"] == "/api/dark-pack/clans/brujah/white"
    assert badge_of(troupe, "Nell")["logo"] is None
    listed = {c["clan"]: c for c in troupe.custodian.client.get("/clan-logos").json()["clans"]}
    assert listed["Brujah"]["dark_pack"] == "/api/dark-pack/clans/brujah"
    assert listed["Brujah"]["logo"] is None

    files = {"file": ("brujah.png", logo_png(), "image/png")}
    made = troupe.custodian.client.post("/clan-logos", data={"clan": "Brujah"}, files=files)
    assert made.status_code == 200, made.text
    agnes = badge_of(troupe, "Agnes")
    assert agnes["logo"] == made.json()["logo"]
    assert agnes["logo_white"] is None


def test_every_clan_in_the_map_is_in_the_rules() -> None:
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    clans = {name for category, name in rule_set.traits if category == "clan"}
    assert set(dark_pack.CLAN_SYMBOLS) <= clans

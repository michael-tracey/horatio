"""Custodian › Tools (#534): the server fetches the Dark Pack kit and the VTES symbols
itself, from a stand-in for Paradox's Dropbox download and for KRCG. Nothing here
touches the network."""

import io
import json
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from horatio import dark_pack, fetching, vtes_symbols
from horatio.config import get_settings
from horatio.rules.files import DATA_DIR, load_rule_set
from tests.api_helpers import Person, Troupe
from tests.test_api_audit import messages
from tests.test_dark_pack import CLANS, KIT, png

DROPBOX = dark_pack.DEFAULT_ADDRESS
# Where Dropbox sends the shared folder on to: a name of its own for each download.
DOWNLOAD = "https://uc0a1b2c3d4e5f.dl.dropboxusercontent.com/zip_download_get/AbC123"
KRCG = vtes_symbols.DEFAULT_ADDRESS
OLD_KIT = "WoD-Logos-and-Symbols"


def zipped(files: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


def kit_zip() -> bytes:
    """The newer kit: the Dark Pack logo and Brujah's symbol, black and white."""
    return zipped(
        {
            f"{KIT}/Dark Pack/DarkPack_Logo_Color.png": png((180, 20, 20, 255), (900, 900)),
            f"{KIT}/Dark Pack/DarkPack_Logo_BW.png": png((0, 0, 0, 255)),
            f"{CLANS}/Brujah/VTM_Brujah_Symbol.png": png((0, 0, 0, 255)),
            f"{CLANS}/Brujah/VTM_Brujah_Symbol_White.png": png((255, 255, 255, 255)),
        }
    )


def old_kit_zip() -> bytes:
    """The older kit, for a clan the newer lacks."""
    return zipped({f"{OLD_KIT}/Giovanni/Giovanni_Symbol_1.png": png((0, 0, 0, 255))})


def download() -> bytes:
    """Paradox's download as Dropbox gives it: one zip holding the kit's two."""
    return zipped({f"{KIT}.zip": kit_zip(), f"{OLD_KIT}.zip": old_kit_zip()})


class Fake:
    """A stand-in for the places fetched from: each address's answer, and what was
    asked for."""

    def __init__(self) -> None:
        self.answers: dict[str, httpx.Response | Callable[[], httpx.Response]] = {}
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        answer = self.answers.get(str(request.url))
        if answer is None:
            return httpx.Response(404)
        return answer() if callable(answer) else answer


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, connection: Connection) -> Iterator[Fake]:
    """The fake places, each job run straight away in a session of its own inside the
    test's, and no pauses."""
    found = Fake()
    monkeypatch.setattr(fetching, "transport", httpx.MockTransport(found))
    monkeypatch.setattr(fetching, "sleep", lambda seconds: None)
    monkeypatch.setattr(fetching, "launch", lambda work: work())
    monkeypatch.setattr(
        fetching,
        "open_session",
        lambda: Session(bind=connection, join_transaction_mode="create_savepoint"),
    )
    monkeypatch.setattr(dark_pack, "job", fetching.Job("Dark Pack fetch"))
    monkeypatch.setattr(vtes_symbols, "job", fetching.Job("VTES symbols fetch"))
    yield found


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "dark-pack"
    path.mkdir()
    (path / "README.md").write_text("Put the Dark Pack resources here\n")
    monkeypatch.setattr(get_settings(), "dark_pack_dir", str(path))
    return path


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    found = Troupe(client_for, session)
    session.commit()
    return found


def dropbox(fake: Fake, data: bytes) -> None:
    """Dropbox's shared folder, sending on to the zip of it."""
    fake.answers[DROPBOX] = httpx.Response(302, headers={"Location": DOWNLOAD})
    fake.answers[DOWNLOAD] = httpx.Response(200, content=data)


def fetch(person: Person, tool: str, address: str, *, accept: bool = True) -> Any:
    return person.client.post(
        f"/tools/{tool}/fetch", json={"address": address, "accept_licence": accept}
    )


def status(person: Person, tool: str) -> dict[str, Any]:
    response = person.client.get(f"/tools/{tool}")
    assert response.status_code == 200, response.text
    return response.json()


def files(path: Path) -> list[str]:
    return sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())


KIT_FILES = [
    "README.md",
    "clans/brujah/128.webp",
    "clans/brujah/600.webp",
    "clans/brujah/white/128.webp",
    "clans/brujah/white/600.webp",
    "clans/giovanni/128.webp",
    "clans/giovanni/600.webp",
    "logo-bw.webp",
    "logo.webp",
    "manifest.json",
]


# --- the Dark Pack ------------------------------------------------------------------------------


def test_the_server_fetches_the_kit_and_imports_the_zips_inside(
    troupe: Troupe, fake: Fake, folder: Path
) -> None:
    dropbox(fake, download())
    before = status(troupe.custodian, "dark-pack")
    assert before["configured"] and before["writable"]
    assert before["imported"] is False
    assert before["default_address"] == DROPBOX

    response = fetch(troupe.custodian, "dark-pack", DROPBOX)
    assert response.status_code == 202, response.text

    found = status(troupe.custodian, "dark-pack")
    assert found["imported"] is True
    assert found["how"] == "fetched"
    assert found["address"] == DROPBOX
    assert found["sources"] == [f"{KIT}.zip", f"{OLD_KIT}.zip"]
    assert found["logo"] is True
    assert found["clans"] == ["Brujah", "Giovanni"]
    assert "Ventrue" in found["missing"]
    assert found["job"] is None and found["error"] is None
    # Only what Horatio uses: the download and the zips inside it are gone.
    assert files(folder) == KIT_FILES
    assert all(r.headers["user-agent"].startswith("Horatio (") for r in fake.asked)
    assert (
        f"custodian fetched the Dark Pack resources from {DROPBOX}: 2 clan symbols and the"
        " Dark Pack logo." in messages(troupe.custodian)
    )
    # The app uses them at once.
    assert troupe.player.client.get("/dark-pack/clans/giovanni/600.webp").status_code == 200


def test_the_command_reads_the_download_as_it_comes(tmp_path: Path) -> None:
    (tmp_path / "download.zip").write_bytes(download())
    out = tmp_path / "dark-pack"
    record = dark_pack.import_kits([tmp_path / "download.zip"], out)
    assert set(record["clans"]) == {"Brujah", "Giovanni"}
    assert record["how"] == "command"
    assert [p.name for p in out.iterdir() if p.name.startswith(".")] == []


def test_a_failed_fetch_keeps_what_was_imported(
    troupe: Troupe, fake: Fake, folder: Path, tmp_path: Path
) -> None:
    (tmp_path / "kit.zip").write_bytes(kit_zip())
    dark_pack.import_kits([tmp_path / "kit.zip"], folder)
    kept = {p: (folder / p).read_bytes() for p in files(folder)}

    # A dead link,
    fake.answers[DROPBOX] = httpx.Response(404)
    assert fetch(troupe.custodian, "dark-pack", DROPBOX).status_code == 202
    found = status(troupe.custodian, "dark-pack")
    assert found["error"] == f"{DROPBOX} answered 404 Not Found."
    assert found["imported"] and found["clans"] == ["Brujah"]
    # a page in place of the zip,
    dropbox(fake, b"<html>Sign in to Dropbox</html>")
    fetch(troupe.custodian, "dark-pack", DROPBOX)
    assert "isn't a zip file" in status(troupe.custodian, "dark-pack")["error"]
    # and a zip with nothing of the kit's in it all leave the last import alone.
    dropbox(fake, zipped({"Scenes/Scene1.jpg": b"not needed"}))
    fetch(troupe.custodian, "dark-pack", DROPBOX)
    assert status(troupe.custodian, "dark-pack")["error"] == (
        "None of the Dark Pack's logos or clan symbols are in that download."
    )

    assert {p: (folder / p).read_bytes() for p in files(folder)} == kept
    assert not [p for p in folder.iterdir() if p.name.startswith(".")]
    assert (
        f"custodian's fetch of the Dark Pack resources failed, so what was here stays: {DROPBOX}"
        " answered 404 Not Found." in messages(troupe.custodian)
    )


def test_a_download_over_the_cap_is_stopped(
    troupe: Troupe, fake: Fake, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dark_pack, "MAX_DOWNLOAD", 1000)
    dropbox(fake, download())
    fetch(troupe.custodian, "dark-pack", DROPBOX)
    found = status(troupe.custodian, "dark-pack")
    assert "more than the 1,000 bytes allowed" in found["error"]
    assert found["imported"] is False
    assert files(folder) == ["README.md"]
    assert not [p for p in folder.iterdir() if p.name.startswith(".")]

    # Without a length given, it stops once the cap is passed.
    fake.answers[DOWNLOAD] = lambda: httpx.Response(200, content=iter([b"x" * 600] * 3))
    fetch(troupe.custodian, "dark-pack", DROPBOX)
    assert "more than the 1,000 bytes allowed" in status(troupe.custodian, "dark-pack")["error"]
    assert files(folder) == ["README.md"]


def test_only_https_and_only_with_the_licence_accepted(
    troupe: Troupe, fake: Fake, folder: Path
) -> None:
    refused = fetch(troupe.custodian, "dark-pack", "http://example.com/kit.zip")
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Only https addresses can be fetched from."
    unaccepted = fetch(troupe.custodian, "dark-pack", DROPBOX, accept=False)
    assert unaccepted.status_code == 422
    assert "Dark Pack Agreement" in unaccepted.json()["detail"]
    assert fake.asked == []

    # Nor is it sent on to an http address.
    fake.answers[DROPBOX] = httpx.Response(302, headers={"Location": "http://example.com/k.zip"})
    fetch(troupe.custodian, "dark-pack", DROPBOX)
    assert "which isn't https" in status(troupe.custodian, "dark-pack")["error"]


# Addresses on the server's own network, the cloud's metadata service, and places that
# aren't the tool's: none is fetched from.
ELSEWHERE = [
    "https://169.254.169.254/computeMetadata/v1/",
    "https://metadata.google.internal/computeMetadata/v1/",
    "https://127.0.0.1/",
    "https://[::1]/",
    "https://[::ffff:169.254.169.254]/",
    "https://2130706433/",
    "https://10.0.0.1/",
    "https://localhost/",
    "https://localhost:8000/",
    "https://api.localhost/",
    "https://example.com/kit.zip",
    "https://www.dropbox.com.example.com/kit.zip",
    "https://dropbox.com/kit.zip",
    "https://www.dropbox.com:8443/kit.zip",
    "https://www.dropbox.com@169.254.169.254/",
    "https://a.b.dl.dropboxusercontent.com/kit.zip",
]


@pytest.mark.parametrize("address", [*ELSEWHERE, KRCG])
def test_the_kit_is_fetched_only_from_dropbox(
    troupe: Troupe, fake: Fake, folder: Path, address: str
) -> None:
    refused = fetch(troupe.custodian, "dark-pack", address)
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Horatio fetches these only from Dropbox."
    assert fake.asked == []


@pytest.mark.parametrize(
    "to",
    [
        "https://169.254.169.254/computeMetadata/v1/",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://[::1]/kit.zip",
        "https://127.0.0.1:8000/kit.zip",
        "https://localhost/kit.zip",
        "https://example.com/kit.zip",
        "https://uc1.dl.dropboxusercontent.com.example.com/kit.zip",
        "http://uc1.dl.dropboxusercontent.com/kit.zip",
    ],
)
def test_dropbox_is_not_followed_anywhere_else(
    troupe: Troupe, fake: Fake, folder: Path, to: str
) -> None:
    fake.answers[DROPBOX] = httpx.Response(302, headers={"Location": to})
    fake.answers[to] = httpx.Response(200, content=download())
    assert fetch(troupe.custodian, "dark-pack", DROPBOX).status_code == 202
    found = status(troupe.custodian, "dark-pack")
    assert found["error"].startswith("The address sent Horatio on to ")
    assert found["error"].endswith(("which isn't Dropbox.", "which isn't https."))
    assert found["imported"] is False
    # It stopped before asking.
    assert [str(r.url) for r in fake.asked] == [DROPBOX]


def test_the_ip_and_localhost_are_refused_even_if_listed() -> None:
    source = fetching.Source(
        "anywhere", ("127.0.0.1", "::1", "[::1]", "localhost", "a.localhost", "1.2", "*.test")
    )
    for host in ("127.0.0.1", "::1", "[::1]", "localhost", "LOCALHOST", "a.localhost", "1.2"):
        assert not source.allows(host), host
    assert source.allows("files.test")
    assert not source.allows("a.b.test") and not source.allows("test")
    assert dark_pack.SOURCE.allows("www.dropbox.com")
    assert dark_pack.SOURCE.allows("UC0A1B.dl.dropboxusercontent.com")
    assert not dark_pack.SOURCE.allows("dl.dropboxusercontent.com")
    assert vtes_symbols.SOURCE.allows("static.krcg.org")
    assert not vtes_symbols.SOURCE.allows("www.dropbox.com")


def test_one_fetch_at_a_time(troupe: Troupe, fake: Fake, folder: Path) -> None:
    dark_pack.job.claim("someone", "Downloading")
    response = fetch(troupe.custodian, "dark-pack", DROPBOX)
    assert response.status_code == 409
    found = status(troupe.custodian, "dark-pack")
    assert found["job"]["stage"] == "Downloading"
    assert found["job"]["by"] == "someone"


def test_without_a_folder_there_is_nothing_to_fetch_into(
    troupe: Troupe, fake: Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "dark_pack_dir", None)
    assert status(troupe.custodian, "dark-pack")["configured"] is False
    response = fetch(troupe.custodian, "dark-pack", DROPBOX)
    assert response.status_code == 422
    assert "isn't set up here" in response.json()["detail"]


def test_an_import_from_before_says_when_it_was_written(
    troupe: Troupe, folder: Path, tmp_path: Path
) -> None:
    (tmp_path / "kit.zip").write_bytes(kit_zip())
    dark_pack.import_kits([tmp_path / "kit.zip"], folder)
    record = json.loads((folder / "manifest.json").read_text())
    for key in ("imported_at", "how"):
        del record[key]
    (folder / "manifest.json").write_text(json.dumps(record))

    found = status(troupe.custodian, "dark-pack")
    assert found["imported"] and found["how"] == "command"
    assert found["imported_at"] is not None
    assert found["sources"] == ["kit.zip"]


def result_zip(folder: Path, top: str = "dark-pack/") -> bytes:
    """The Dark Pack folder an import wrote, zipped as someone would."""
    return zipped(
        {f"{top}{p}": (folder / p).read_bytes() for p in files(folder)}
        | {f"{top}notes.txt": b"left out"}
    )


def test_the_custodian_can_upload_what_an_import_wrote_elsewhere(
    troupe: Troupe, folder: Path, tmp_path: Path
) -> None:
    (tmp_path / "download.zip").write_bytes(download())
    elsewhere = tmp_path / "elsewhere"
    dark_pack.import_kits([tmp_path / "download.zip"], elsewhere)

    def upload(data: bytes, accept: str = "true") -> Any:
        return troupe.custodian.client.post(
            "/tools/dark-pack/upload",
            files={"file": ("dark-pack.zip", data, "application/zip")},
            data={"accept_licence": accept},
        )

    assert upload(result_zip(elsewhere), accept="false").status_code == 422
    assert upload(b"not a zip").json()["detail"] == "That isn't a zip file that can be read."
    no_manifest = upload(zipped({"logo.webp": b"x"}))
    assert "no manifest.json" in no_manifest.json()["detail"]
    bad_image = zipped({"manifest.json": b'{"clans": {}, "logos": {}}', "logo.webp": b"x"})
    assert "isn't a WebP image" in upload(bad_image).json()["detail"]

    response = upload(result_zip(elsewhere))
    assert response.status_code == 200, response.text
    found = response.json()
    assert found["how"] == "uploaded" and found["address"] is None
    assert found["clans"] == ["Brujah", "Giovanni"] and found["logo"]
    assert files(folder) == KIT_FILES
    assert (
        "custodian uploaded Dark Pack resources imported elsewhere: 2 clan symbols and the Dark"
        " Pack logo." in messages(troupe.custodian)
    )


def test_removing_the_dark_pack_leaves_the_vtes_symbols(
    troupe: Troupe, folder: Path, tmp_path: Path
) -> None:
    (tmp_path / "kit.zip").write_bytes(kit_zip())
    dark_pack.import_kits([tmp_path / "kit.zip"], folder)
    (folder / "vtes").mkdir()
    (folder / "vtes" / "manifest.json").write_text("{}")

    response = troupe.custodian.client.delete("/tools/dark-pack")
    assert response.status_code == 200, response.text
    assert response.json()["imported"] is False
    assert files(folder) == ["README.md", "vtes/manifest.json"]
    assert troupe.player.client.get("/dark-pack/clans/brujah/600.webp").status_code == 404
    assert "custodian removed the Dark Pack resources from the server." in messages(
        troupe.custodian
    )


def test_only_the_custodian_uses_the_tools(troupe: Troupe, fake: Fake, folder: Path) -> None:
    for person in (troupe.lead, troupe.player):
        client = person.client
        for response in (
            client.get("/tools/dark-pack"),
            client.post(
                "/tools/dark-pack/fetch", json={"address": DROPBOX, "accept_licence": True}
            ),
            client.post(
                "/tools/dark-pack/upload",
                files={"file": ("d.zip", b"x", "application/zip")},
                data={"accept_licence": "true"},
            ),
            client.delete("/tools/dark-pack"),
            client.get("/tools/vtes-symbols"),
            client.post(
                "/tools/vtes-symbols/fetch", json={"address": KRCG, "accept_licence": True}
            ),
            client.delete("/tools/vtes-symbols"),
        ):
            assert response.status_code == 403, response.request.url
    assert fake.asked == []


# --- the VTES symbols ---------------------------------------------------------------------------


def svg(colour: str = "black") -> bytes:
    return (
        f'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" fill="{colour}"/>'.encode()
    )


def image(kind: str, *, large: bool = False) -> bytes:
    """A symbol; a large one is noise, which doesn't compress."""
    out = io.BytesIO()
    if large:
        picture = Image.merge("RGBA", [Image.effect_noise((400, 400), 100) for _ in range(4)])
    else:
        picture = Image.new("RGBA", (16, 16), (0, 0, 0, 255))
    picture.save(out, kind.upper())
    return out.getvalue()


def listing(path: str, names: list[str]) -> bytes:
    """A folder listing as KRCG's nginx gives it."""
    rows = "\n".join(f'<a href="{n}">{n}</a>        08-Nov-2026 08:08    1234' for n in names)
    return (
        f"<html><head><title>Index of /{path}</title></head><body><h1>Index of /{path}</h1>"
        f'<hr><pre><a href="../">../</a>\n{rows}\n</pre><hr></body></html>'
    ).encode()


KRCG_FILES = {
    "clan": ["brujah", "banuhaqim", "ministry", "abominations"],
    "disc/inf": ["aus", "cel", "nec", "tha"],
    "disc/sup": ["aus", "cel"],
    "icon": ["blood1", "action"],
    "path": ["caine", "death"],
}
# Some of KRCG's icons have no SVG: the capacity drop is WebP and PNG only.
KRCG_RASTER_ICONS = ["capacity"]


def krcg(
    fake: Fake,
    *,
    large: str | None = None,
    kinds: tuple[str, ...] = vtes_symbols.KINDS,
    paths: bool = True,
) -> None:
    """KRCG's folders, each with a few symbols, the clans with an old one in
    deprecated/; the fonts and the logos. `kinds` and `paths` leave folders out, as an
    older KRCG had none of the white-bordered or path ones."""
    for kind in kinds:
        ext = vtes_symbols.EXTENSION[kind]
        for group, names in KRCG_FILES.items():
            if group == "path" and not paths:
                continue
            if group == "icon" and ext != "svg":
                names = [*names, *KRCG_RASTER_ICONS]
            folder_names = [f"{n}.{ext}" for n in names]
            if group == "clan":
                folder_names = ["deprecated/", *folder_names]
            fake.answers[f"{KRCG}{kind}/{group}/"] = httpx.Response(
                200, content=listing(f"{kind}/{group}/", folder_names)
            )
            for name in names:
                data = svg() if ext == "svg" else image(ext, large=name == large)
                fake.answers[f"{KRCG}{kind}/{group}/{name}.{ext}"] = httpx.Response(
                    200, content=data
                )
        fake.answers[f"{KRCG}{kind}/clan/deprecated/brujah.{ext}"] = httpx.Response(200)
    for font in vtes_symbols.FONTS:
        fake.answers[f"{KRCG}web/{font}"] = httpx.Response(200, content=b"OTTO" + b"\0" * 64)
    fake.answers[f"{KRCG}vtes.svg"] = httpx.Response(200, content=svg())
    fake.answers[f"{KRCG}dark-pack.png"] = httpx.Response(200, content=image("png"))


def test_the_server_fetches_the_vtes_symbols_from_krcg(
    troupe: Troupe, fake: Fake, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pauses: list[float] = []
    monkeypatch.setattr(fetching, "sleep", pauses.append)
    krcg(fake, large="brujah")
    before = status(troupe.custodian, "vtes-symbols")
    assert before["fetched"] is False and before["default_address"] == KRCG

    response = fetch(troupe.custodian, "vtes-symbols", KRCG)
    assert response.status_code == 202, response.text

    found = status(troupe.custodian, "vtes-symbols")
    assert found["fetched"] is True and found["error"] is None
    assert found["address"] == KRCG
    assert found["counts"] == [
        {"kind": kind, "clans": 4, "inferior": 4, "superior": 2, "icons": icons, "paths": 2}
        for kind, icons in (
            ("svg", 2),
            ("webp", 3),
            ("png", 3),
            ("webp_wb", 3),
            ("png_wb", 3),
        )
    ]
    assert found["fonts"] == list(vtes_symbols.FONTS)
    assert found["logos"] == list(vtes_symbols.LOGOS)
    assert found["outdated"] is False
    clans = {c["name"]: c["symbol"] for c in found["clans"]}
    assert clans["Brujah"] == "brujah"
    assert clans["Assamite"] == "banuhaqim"
    assert clans["Followers of Set"] == "ministry"
    assert clans["Ventrue"] is None
    assert clans["Lhiannan"] is None
    disciplines = {d["name"]: d["symbol"] for d in found["disciplines"]}
    assert disciplines["Auspex"] == "aus"
    assert disciplines["Necromancy"] == "nec"
    assert disciplines["Thaumaturgy"] == "tha"
    assert disciplines["Kineticism"] is None
    assert "Necromancy: Ash Path" not in disciplines
    large = {p["path"]: p["size"] for p in found["large_png"]}
    assert set(large) == {"clan/brujah.png", "png_wb/clan/brujah.png"}
    assert min(large.values()) > vtes_symbols.DISCORD_EMOJI

    # Old symbols in deprecated/ are left out; politely, one at a time.
    asked = [str(r.url) for r in fake.asked]
    assert not [u for u in asked if "deprecated" in u]
    assert len(pauses) == len(asked) - 1 and set(pauses) == {vtes_symbols.PAUSE}
    assert all(r.headers["user-agent"].startswith("Horatio (") for r in fake.asked)
    kept = folder / "vtes"
    assert (kept / "svg" / "disc" / "inf" / "aus.svg").read_bytes() == svg()
    assert (kept / "fonts" / "ankha2.otf").is_file()
    assert (kept / "fonts" / "ankha.ttf").is_file()
    # The white-bordered symbols, the paths and the logos (#869).
    assert (kept / "webp_wb" / "disc" / "sup" / "aus.webp").is_file()
    assert (kept / "png_wb" / "disc" / "inf" / "cel.png").is_file()
    assert (kept / "svg" / "path" / "caine.svg").is_file()
    assert (kept / "logos" / "vtes.svg").is_file()
    assert (kept / "logos" / "dark-pack.png").is_file()
    # The capacity drop the Jyhad card shows, which KRCG has in WebP and PNG only.
    assert (kept / "webp" / "icon" / "capacity.webp").is_file()
    assert "capacity" in json.loads((kept / "manifest.json").read_text())["files"]["webp/icon"]
    assert not [p for p in folder.iterdir() if p.name.startswith(".")]
    assert f"custodian fetched the VTES symbols from {KRCG}: 74 symbols and 3 fonts." in messages(
        troupe.custodian
    )


def test_the_symbols_are_served_to_anyone_signed_in(
    troupe: Troupe, fake: Fake, folder: Path, client_for: Callable[[], TestClient]
) -> None:
    krcg(fake)
    fetch(troupe.custodian, "vtes-symbols", KRCG)
    player = troupe.player.client

    shown = player.get("/vtes-symbols/svg/disc/inf/aus.svg")
    assert shown.status_code == 200
    assert shown.headers["content-type"] == "image/svg+xml"
    assert "sandbox" in shown.headers["content-security-policy"]
    assert "max-age" in shown.headers["cache-control"]
    assert player.get("/vtes-symbols/png/clan/brujah.png").headers["content-type"] == "image/png"
    assert player.get("/vtes-symbols/webp/icon/blood1.webp").status_code == 200
    assert player.get("/vtes-symbols/webp/icon/capacity.webp").status_code == 200
    assert player.get("/vtes-symbols/fonts/vtes-clans.otf").status_code == 200
    ttf = player.get("/vtes-symbols/fonts/ankha.ttf")
    assert ttf.status_code == 200 and ttf.headers["content-type"] == "font/ttf"
    # White-bordered (#869): WebP and PNG, as their own kinds.
    edged = player.get("/vtes-symbols/webp_wb/disc/sup/aus.webp")
    assert edged.status_code == 200 and edged.headers["content-type"] == "image/webp"
    assert player.get("/vtes-symbols/png_wb/clan/brujah.png").status_code == 200
    assert player.get("/vtes-symbols/svg/path/caine.svg").status_code == 200
    logo = player.get("/vtes-symbols/logos/vtes.svg")
    assert logo.status_code == 200 and "sandbox" in logo.headers["content-security-policy"]
    assert player.get("/vtes-symbols/logos/dark-pack.png").headers["content-type"] == "image/png"
    assert client_for().get("/vtes-symbols/svg/clan/brujah.svg").status_code == 401
    for path in (
        "svg/clan/brujah.png",
        "svg/clan/../manifest.json",
        "svg/manifest.json",
        "svg/clan/deprecated/brujah.svg",
        "gif/clan/brujah.gif",
        "fonts/ankha.otf",
        "webp_wb/clan/brujah.png",
        "png_wb/clan/brujah.webp",
        "logos/manifest.json",
        "logos/other.svg",
    ):
        assert player.get(f"/vtes-symbols/{path}").status_code == 404, path


def test_a_failed_vtes_fetch_keeps_the_last(troupe: Troupe, fake: Fake, folder: Path) -> None:
    krcg(fake)
    fetch(troupe.custodian, "vtes-symbols", KRCG)
    kept = {p: (folder / p).read_bytes() for p in files(folder)}

    # A file that won't come,
    fake.answers[f"{KRCG}png/icon/action.png"] = httpx.Response(500)
    fetch(troupe.custodian, "vtes-symbols", KRCG)
    error = status(troupe.custodian, "vtes-symbols")["error"]
    assert error == f"{KRCG}png/icon/action.png answered 500 Internal Server Error."
    # an SVG with a script in it,
    krcg(fake)
    fake.answers[f"{KRCG}svg/clan/brujah.svg"] = httpx.Response(
        200, content=b"<svg><script>alert(1)</script></svg>"
    )
    fetch(troupe.custodian, "vtes-symbols", KRCG)
    assert "isn't the SVG image it should be" in status(troupe.custodian, "vtes-symbols")["error"]
    # and somewhere with no symbols all leave the last fetch alone.
    fetch(troupe.custodian, "vtes-symbols", f"{KRCG}moved/")
    assert status(troupe.custodian, "vtes-symbols")["error"] == (
        f"{KRCG}moved/svg/clan/ answered 404 Not Found."
    )

    assert {p: (folder / p).read_bytes() for p in files(folder)} == kept
    assert not [p for p in folder.iterdir() if p.name.startswith(".")]
    assert status(troupe.custodian, "vtes-symbols")["fetched"] is True


def test_an_older_krcg_without_bordered_symbols_or_paths_still_fetches(
    troupe: Troupe, fake: Fake, folder: Path
) -> None:
    """The white-bordered folders and the paths are newer at KRCG: a 404 for one is
    skipped. A fetch without them is "outdated": the Jyhad card wants them (#869)."""
    krcg(fake, kinds=vtes_symbols.PLAIN, paths=False)
    del fake.answers[f"{KRCG}dark-pack.png"]

    fetch(troupe.custodian, "vtes-symbols", KRCG)

    found = status(troupe.custodian, "vtes-symbols")
    assert found["fetched"] is True and found["error"] is None
    assert [c["kind"] for c in found["counts"] if c["clans"]] == list(vtes_symbols.PLAIN)
    assert all(c["paths"] == 0 for c in found["counts"])
    assert found["logos"] == ["vtes.svg"]
    assert found["outdated"] is True
    # A plain folder that's missing still fails the fetch.
    krcg(fake, kinds=vtes_symbols.PLAIN, paths=False)
    del fake.answers[f"{KRCG}webp/icon/"]
    fetch(troupe.custodian, "vtes-symbols", KRCG)
    assert status(troupe.custodian, "vtes-symbols")["error"] == (
        f"{KRCG}webp/icon/ answered 404 Not Found."
    )


@pytest.mark.parametrize("address", [*ELSEWHERE, DROPBOX, "https://krcg.org/"])
def test_the_symbols_are_fetched_only_from_krcg(
    troupe: Troupe, fake: Fake, folder: Path, address: str
) -> None:
    refused = fetch(troupe.custodian, "vtes-symbols", address)
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Horatio fetches these only from KRCG (static.krcg.org)."
    assert fake.asked == []


@pytest.mark.parametrize(
    "to", ["https://169.254.169.254/svg/clan/", "https://[::1]/svg/clan/", "https://krcg.org/"]
)
def test_krcg_is_not_followed_anywhere_else(
    troupe: Troupe, fake: Fake, folder: Path, to: str
) -> None:
    krcg(fake)
    fake.answers[f"{KRCG}svg/clan/"] = httpx.Response(302, headers={"Location": to})
    fetch(troupe.custodian, "vtes-symbols", KRCG)
    found = status(troupe.custodian, "vtes-symbols")
    assert found["error"].startswith("The address sent Horatio on to ")
    assert found["error"].endswith("which isn't KRCG (static.krcg.org).")
    assert found["fetched"] is False
    assert [str(r.url) for r in fake.asked] == [f"{KRCG}svg/clan/"]


def test_a_symbol_over_the_cap_is_refused(
    troupe: Troupe, fake: Fake, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    krcg(fake)
    monkeypatch.setattr(vtes_symbols, "MAX_SYMBOL", 30)
    fetch(troupe.custodian, "vtes-symbols", KRCG)
    found = status(troupe.custodian, "vtes-symbols")
    assert "is more than the 30 bytes allowed" in found["error"]
    assert found["fetched"] is False
    assert files(folder) == ["README.md"]


def test_removing_the_vtes_symbols(troupe: Troupe, fake: Fake, folder: Path) -> None:
    krcg(fake)
    fetch(troupe.custodian, "vtes-symbols", KRCG)
    response = troupe.custodian.client.delete("/tools/vtes-symbols")
    assert response.status_code == 200, response.text
    assert response.json()["fetched"] is False
    assert files(folder) == ["README.md"]
    assert troupe.player.client.get("/vtes-symbols/svg/clan/brujah.svg").status_code == 404
    assert "custodian removed the VTES symbols from the server." in messages(troupe.custodian)


def test_the_name_tables_name_what_the_rules_have() -> None:
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    clans = {name for category, name in rule_set.traits if category == "clan"}
    disciplines = {
        vtes_symbols.discipline_of(name)
        for category, name in rule_set.traits
        if category == "disciplines"
    }
    assert set(vtes_symbols.CLANS) <= clans
    assert set(vtes_symbols.DISCIPLINES) <= disciplines

"""Paradox's Dark Pack resources (issue #92): the Dark Pack logo and the clans'
symbols, which the Dark Pack Agreement lets a free fan app like Horatio use.

Horatio never ships them: the licence is personal and cannot be passed on
under Horatio's AGPL. Each server's operator fetches the kit from
https://www.paradoxinteractive.com/games/world-of-darkness/community/dark-pack-agreement
into the folder HORATIO_DARK_PACK_DIR names (`dark-pack/` beside the code, by
default). On a server, the custodian does it in Custodian › Tools (#534): the
server fetches the kit from Paradox's download (`fetch`), or the custodian uploads
what an import on their own computer wrote (`install_result`). For local
development and scripts, the command imports the zips as downloaded:

    uv run python -m horatio.dark_pack "World of Darkness Community Assets.zip" \\
        WoD-Logos-and-Symbols.zip --out ../dark-pack

Paradox's download is one zip holding the kit's two zips; the import reads either
layout, without unpacking more than the zips inside, and writes only what Horatio
uses, at the sizes it serves:

    dark-pack/
      manifest.json                  what was imported, when, and from where
      logo.webp, logo-bw.webp        the Dark Pack logo (colour, black and white)
      clans/<slug>/128.webp, 600.webp          a clan's symbol, black
      clans/<slug>/white/128.webp, 600.webp    and white, for dark backgrounds
      vtes/                          the VTES symbols, kept apart (horatio.vtes_symbols)

An import is written beside the folder's files and swapped in once it is whole,
so one that fails leaves the last in place.

A clan the custodian has uploaded no logo for uses its symbol here; a bloodline
uses its clan's (horatio.badges).
"""

import argparse
import json
import re
import shutil
import sys
import time
import uuid
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from horatio import fetching, pictures
from horatio.config import get_settings
from horatio.models import User

# Where each clan's symbol is in the kits, newest kit first: a path ending, black
# then white. MET: VTM's clan names come first; the kits use V5's names where
# the clan was renamed (Assamite is Banu Haqim, Followers of Set the Ministry).
CLAN_SYMBOLS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "Assamite": (("Banu Haqim/BanuHaqim_Symbol.png",), ("Banu Haqim/BanuHaqim_Symbol_White.png",)),
    "Brujah": (
        ("Brujah/VTM_Brujah_Symbol.png", "Brujah/VTM_Brujah_icon_black.png"),
        ("Brujah/VTM_Brujah_Symbol_White.png", "Brujah/VTM_Brujah_icon_white.png"),
    ),
    "Caitiff": (("Caitiff/Caitiff_Symbol.png",), ("Caitiff/Caitiff_Symbol_White.png",)),
    "Cappadocians": (("Cappadocian/Cappadocian_Symbol.png",), ()),
    "Cappadocians: Lamia": (("Lamia/Lamia_Symbol_1.png",), ()),
    "Followers of Set": (
        ("The Ministry/TheMinistry_Symbol.png", "The Ministry/MinistrySymbol.png"),
        ("The Ministry/TheMinistry_Symbol_White.png",),
    ),
    "Gangrel": (
        ("Gangrel/Gangrel_Symbol.png", "Gangrel/Gangrel_New1.png"),
        ("Gangrel/Gangrel_Symbol_White.png", "Gangrel/Gangrel_New1_white.png"),
    ),
    "Giovanni": (("Giovanni/Giovanni_Symbol_1.png",), ()),
    "Lasombra": (("Lasombra/Lasombra_Symbol.png",), ("Lasombra/Lasombra_Symbol_White.png",)),
    "Malkavian": (
        ("Malkavian/VTM_Malkavian_Symbol.png", "Malkavian/VTM_Malkavian_icon_black.png"),
        ("Malkavian/VTM_Malkavian_Symbol_White.png",),
    ),
    "Nagaraja": (("Nagaraja/Nagaraja_Symbol_1.png",), ()),
    "Nosferatu": (("Nosferatu/Nosferatu_Symbol.png",), ("Nosferatu/Nosferatu_Symbol_White.png",)),
    "Ravnos": (("Ravnos/Ravnos_Symbol.png",), ("Ravnos/Ravnos_Symbol_White.png",)),
    "Salubri": (("Salubri/Salubri_Symbol.png",), ("Salubri/Salubri_Symbol_White.png",)),
    "Toreador": (("Toreador/Toreador_Symbol.png",), ("Toreador/Toreador_Symbol_White.png",)),
    "Tremere": (("Tremere/Tremere_Symbol.png",), ("Tremere/Tremere_Symbol_White.png",)),
    "Tzimisce": (("Tzimisce/Tzimisce_Symbol.png",), ("Tzimisce/Tzimisce_Symbol_White.png",)),
    "Ventrue": (("Ventrue/Ventrue_Symbol.png",), ("Ventrue/Ventrue_Symbol_White.png",)),
}
LOGOS = {
    "logo.webp": ("Dark Pack/DarkPack_Logo_Color.png", "Dark Pack Logos/DarkPack_Logo2.png"),
    "logo-bw.webp": ("Dark Pack/DarkPack_Logo_BW.png", "Dark Pack Logos/DarkPack_Logo1.png"),
}
LOGO_WIDTH = 600
SIZES = {f"{s}.webp" for s in pictures.LOGOS}


def slug(clan: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", clan.lower()).strip("-")


def folder() -> Path | None:
    """The configured Dark Pack folder, if it has been imported into."""
    setting = get_settings().dark_pack_dir
    if not setting:
        return None
    path = Path(setting)
    return path if (path / "manifest.json").is_file() else None


def manifest() -> dict[str, Any]:
    root = folder()
    if root is None:
        return {}
    try:
        return json.loads((root / "manifest.json").read_text())
    except (OSError, ValueError):
        return {}


def has_logo() -> bool:
    root = folder()
    return root is not None and (root / "logo.webp").is_file()


def clan_logos() -> dict[str, tuple[str, str | None]]:
    """Each clan with a Dark Pack symbol: its address (add "/600.webp"), and its
    white version's, if the kit had one."""
    found: dict[str, tuple[str, str | None]] = {}
    for clan, entry in manifest().get("clans", {}).items():
        base = f"/api/dark-pack/clans/{entry['slug']}"
        found[clan] = (base, f"{base}/white" if entry.get("white") else None)
    return found


def clan_file(clan_slug: str, name: str, white: bool = False) -> Path | None:
    """A symbol's file. Only names the import writes are looked up, so a request
    can never reach outside the folder."""
    root = folder()
    if root is None or name not in SIZES or not re.fullmatch(r"[a-z0-9-]+", clan_slug):
        return None
    path = root / "clans" / clan_slug / ("white" if white else "") / name
    return path if path.is_file() else None


def logo_file(name: str) -> Path | None:
    root = folder()
    if root is None or name not in LOGOS:
        return None
    path = root / name
    return path if path.is_file() else None


class Kits:
    """The kits' zips, read in place: members are found by the end of their path,
    so the kits' own top folders don't matter. A zip inside one (Paradox's download
    holds the kit's two) is unpacked into `scratch` and read the same way."""

    def __init__(self, paths: Sequence[Path], scratch: Path) -> None:
        self.zips: list[tuple[str, zipfile.ZipFile]] = []
        # The zips a file was taken from.
        self.used: list[str] = []
        try:
            for path in paths:
                self._open(path.name, path, scratch)
        except BaseException:
            self.close()
            raise

    def _open(self, name: str, path: Path, scratch: Path, *, nested: bool = False) -> None:
        try:
            kit = zipfile.ZipFile(path)
        except zipfile.BadZipFile as error:
            raise fetching.Failed(f"{name} isn't a zip file that can be read.") from error
        self.zips.append((name, kit))
        if nested:
            return
        inner = [
            e
            for e in kit.infolist()
            if e.filename.lower().endswith(".zip")
            and not e.is_dir()
            and not e.filename.startswith("__MACOSX/")
        ]
        if sum(e.file_size for e in inner) > MAX_INSIDE:
            raise fetching.Failed(
                f"The zips inside {name} come to more than {fetching.megabytes(MAX_INSIDE)}."
            )
        for entry in inner:
            scratch.mkdir(parents=True, exist_ok=True)
            target = scratch / f"{len(self.zips)}.zip"
            with kit.open(entry) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out, fetching.CHUNK)
            self._open(PurePosixPath(entry.filename).name, target, scratch, nested=True)

    def find(self, endings: Sequence[str]) -> tuple[str, bytes] | None:
        for ending in endings:
            for name, kit in self.zips:
                for member in kit.namelist():
                    if member.endswith(f"/{ending}") or member == ending:
                        if name not in self.used:
                            self.used.append(name)
                        return member, kit.read(member)
        return None

    def close(self) -> None:
        for _, kit in self.zips:
            kit.close()


def import_kits(
    paths: Sequence[Path], out: Path, *, how: str = "command", address: str | None = None
) -> dict[str, Any]:
    """Write the Dark Pack logo and the clans' symbols from the kits into `out`,
    replacing what an import before wrote there, once the new set is whole."""
    out.mkdir(parents=True, exist_ok=True)
    work = out / f"{IMPORTING}{uuid.uuid4().hex}"
    new = work / "new"
    new.mkdir(parents=True)
    try:
        kits = Kits(paths, work / "zips")
        record: dict[str, Any] = {"logos": {}, "clans": {}}
        try:
            for name, endings in LOGOS.items():
                found = kits.find(endings)
                if found is None:
                    continue
                image = pictures.read_image(found[1])
                if image.width > LOGO_WIDTH:
                    image = image.resize(
                        (LOGO_WIDTH, round(image.height * LOGO_WIDTH / image.width))
                    )
                image.save(new / name, "WEBP", lossless=True)
                record["logos"][name] = found[0]
            for clan, (black, white) in CLAN_SYMBOLS.items():
                found = kits.find(black)
                if found is None:
                    continue
                directory = new / "clans" / slug(clan)
                pictures.write_logo(directory, pictures.read_image(found[1]))
                entry: dict[str, Any] = {"slug": slug(clan), "from": found[0]}
                light = kits.find(white)
                if light is not None:
                    pictures.write_logo(directory / "white", pictures.read_image(light[1]))
                    entry["white"] = light[0]
                record["clans"][clan] = entry
            sources = kits.used
        finally:
            kits.close()
        if not record["logos"] and not record["clans"]:
            raise fetching.Failed(
                "None of the Dark Pack's logos or clan symbols are in that download."
            )
        record = {
            "sources": sources,
            "imported_at": datetime.now(UTC).isoformat(),
            "how": how,
            **({"address": address} if address else {}),
            **record,
        }
        (new / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
        swap_in(new, out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return record


def swap_in(new: Path | None, root: Path) -> None:
    """Put the import in `new` in place of the one in `root`, or with no `new`,
    take it away. The manifest goes last, as it says there is one. Anything else in
    the folder (the VTES symbols, a README) is left alone."""
    old = root / f"{OLD}{uuid.uuid4().hex}"
    old.mkdir()
    moved: list[str] = []
    placed: list[str] = []
    try:
        for name in KIT_FILES:
            if (root / name).exists():
                (root / name).rename(old / name)
                moved.append(name)
            if new is not None and (new / name).exists():
                (new / name).rename(root / name)
                placed.append(name)
    except BaseException:
        # Put the last import back as it was.
        for name in placed:
            if (root / name).is_dir():
                shutil.rmtree(root / name, ignore_errors=True)
            else:
                (root / name).unlink(missing_ok=True)
        for name in moved:
            (old / name).rename(root / name)
        raise
    finally:
        shutil.rmtree(old, ignore_errors=True)


# --- on the server: Custodian › Tools (#534) ------------------------------------------------------

# Paradox's Dark Pack page has one download, a shared Dropbox folder; with dl=1,
# Dropbox gives the folder as one zip holding the kit's two (checked 2026-11-08).
DEFAULT_ADDRESS = (
    "https://www.dropbox.com/scl/fo/yyn4a7mwo913xe1f8vzs7/AKX0VWS23y5f5CWL-WlPuzU"
    "?rlkey=2x2fn5ic3tfp1zzublmmtkqca&dl=1"
)
AGREEMENT = (
    "https://www.paradoxinteractive.com/games/world-of-darkness/community/dark-pack-agreement"
)
# The download is about 450 MB, the kit's two zips inside it as much again.
MAX_DOWNLOAD = 1024 * 1024 * 1024
MAX_INSIDE = 1024 * 1024 * 1024
# How long the download may take, in seconds.
DOWNLOAD_TIME = 30 * 60
# An upload of what an import wrote: about a megabyte, zipped.
MAX_RESULT = 8 * 1024 * 1024
MAX_RESULT_UNPACKED = 50 * 1024 * 1024
SLUG = re.compile(r"[a-z0-9-]+")
# What an import writes, the manifest last.
KIT_FILES = ("logo.webp", "logo-bw.webp", "clans", "manifest.json")
RESULT_FILE = re.compile(
    r"manifest\.json|logo(-bw)?\.webp|clans/[a-z0-9-]+/(white/)?(128|600)\.webp"
)
# Folders a fetch, an import or an upload works in, swept up if one was stopped.
FETCHING, IMPORTING, UPLOADING, OLD = ".fetch-", ".import-", ".upload-", ".old-"
WORK = (FETCHING, IMPORTING, UPLOADING, OLD)

job = fetching.Job("Dark Pack fetch")


def root() -> Path | None:
    """The configured Dark Pack folder, imported into or not."""
    setting = get_settings().dark_pack_dir
    return Path(setting) if setting else None


def writable_root() -> Path:
    found = root()
    if found is None:
        raise fetching.Failed("The Dark Pack folder isn't set up here (HORATIO_DARK_PACK_DIR).")
    try:
        found.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise fetching.Failed(f"The Dark Pack folder can't be made: {error.strerror}.") from error
    if not fetching.writable(found):
        raise fetching.Failed("The server can't write to the Dark Pack folder.")
    return found


def imported_at(record: dict[str, Any]) -> datetime | None:
    """When the import was made: as its manifest says, or, for one from before the
    manifest said, when the manifest was written."""
    try:
        return datetime.fromisoformat(record["imported_at"])
    except (KeyError, TypeError, ValueError):
        pass
    found = folder()
    if found is None:
        return None
    return datetime.fromtimestamp((found / "manifest.json").stat().st_mtime, UTC)


def fetch(user: User, address: str) -> None:
    """Start fetching the kit from `address` and importing it, in the background."""
    address = fetching.check_address(address)
    into = writable_root()
    user_id = user.id

    def work() -> None:
        try:
            record = fetch_now(into, address)
        except Exception as error:
            fetching.record(
                user_id, "dark_pack.fetch_failed", address=address, error=fetching.message(error)
            )
            raise
        fetching.record(user_id, "dark_pack.fetched", address=address, **counts(record))

    job.start(user.handle, "Starting", work)


def fetch_now(into: Path, address: str) -> dict[str, Any]:
    """Download the kit into a file beside the folder's, import it, and delete it."""
    fetching.sweep(into, WORK)
    work = into / f"{FETCHING}{uuid.uuid4().hex}"
    work.mkdir()
    try:
        download = work / "download.zip"
        deadline = time.monotonic() + DOWNLOAD_TIME
        with fetching.client() as http:
            fetching.download(
                http,
                address,
                download,
                cap=MAX_DOWNLOAD,
                deadline=deadline,
                step=lambda done, total: job.step("Downloading", done, total),
            )
        if not zipfile.is_zipfile(download):
            raise fetching.Failed(
                "What that address gave isn't a zip file. Check it opens Paradox's download."
            )
        job.step("Importing")
        return import_kits([download], into, how="fetched", address=address)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def counts(record: dict[str, Any]) -> dict[str, Any]:
    """An import, for the audit log."""
    logo = "the Dark Pack logo" if "logo.webp" in record.get("logos", {}) else "no Dark Pack logo"
    return {"clans": len(record.get("clans", {})), "logo": logo}


def install_result(user: User, filename: str, data: bytes) -> dict[str, Any]:
    """Put in place what an import on another computer wrote, uploaded as a zip of
    the Dark Pack folder (its files at the top, or in one folder)."""
    into = writable_root()
    found: dict[str, Any] = {}

    def work() -> None:
        found.update(install_now(into, filename, data))

    job.run_now(user.handle, "Uploading", work)
    return found


def install_now(into: Path, filename: str, data: bytes) -> dict[str, Any]:
    if len(data) > MAX_RESULT:
        raise fetching.Failed(
            f"That file is over {fetching.megabytes(MAX_RESULT)}: upload the zipped Dark Pack"
            " folder an import wrote, not Paradox's zips."
        )
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as error:
        raise fetching.Failed("That isn't a zip file that can be read.") from error
    fetching.sweep(into, WORK)
    work = into / f"{UPLOADING}{uuid.uuid4().hex}"
    new = work / "new"
    new.mkdir(parents=True)
    try:
        with archive:
            entries = [e for e in archive.infolist() if not e.is_dir()]
            manifests = sorted(
                (e.filename for e in entries if PurePosixPath(e.filename).name == "manifest.json"),
                key=len,
            )
            if not manifests:
                raise fetching.Failed(
                    "That zip has no manifest.json: zip the Dark Pack folder an import wrote."
                )
            prefix = manifests[0][: -len("manifest.json")]
            kept = [
                (e, e.filename[len(prefix) :])
                for e in entries
                if e.filename.startswith(prefix)
                and RESULT_FILE.fullmatch(e.filename[len(prefix) :])
            ]
            if sum(e.file_size for e, _ in kept) > MAX_RESULT_UNPACKED:
                raise fetching.Failed("That zip unpacks to more than an import writes.")
            for entry, name in kept:
                target = new / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(entry))
        try:
            record = json.loads((new / "manifest.json").read_text())
        except ValueError as error:
            raise fetching.Failed("That zip's manifest.json can't be read.") from error
        if not isinstance(record, dict) or not isinstance(record.get("clans", {}), dict):
            raise fetching.Failed("That zip's manifest.json isn't one an import wrote.")
        for path in new.rglob("*.webp"):
            try:
                with Image.open(path) as image:
                    image.verify()
                    if image.format != "WEBP":
                        raise ValueError
            except Exception as error:
                raise fetching.Failed(
                    f"{path.relative_to(new)} in that zip isn't a WebP image."
                ) from error
        # Only what came: each clan with both its sizes, and the logos here.
        clans: dict[str, Any] = {}
        for clan, entry in record.get("clans", {}).items():
            if not isinstance(entry, dict) or not SLUG.fullmatch(str(entry.get("slug"))):
                continue
            directory = new / "clans" / entry["slug"]
            if not all((directory / s).is_file() for s in SIZES):
                continue
            if entry.get("white") and not all((directory / "white" / s).is_file() for s in SIZES):
                entry = {k: v for k, v in entry.items() if k != "white"}
            clans[clan] = entry
        logos = {n: f for n, f in (record.get("logos") or {}).items() if (new / n).is_file()}
        if not clans and not logos:
            raise fetching.Failed("That zip has none of the Dark Pack's logos or clan symbols.")
        record = {
            **record,
            "imported_at": datetime.now(UTC).isoformat(),
            "how": "uploaded",
            "uploaded": PurePosixPath(filename).name,
            "logos": logos,
            "clans": clans,
        }
        record.pop("address", None)
        (new / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
        swap_in(new, into)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return record


def remove(user: User) -> None:
    """Take the Dark Pack resources off the server. The VTES symbols stay."""
    into = writable_root()
    job.run_now(user.handle, "Removing", lambda: swap_in(None, into))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m horatio.dark_pack",
        description="Import the Dark Pack logo and clan symbols from Paradox's kit zips.",
    )
    parser.add_argument(
        "zips",
        nargs="+",
        type=Path,
        help="the kit's zip files as downloaded, or the one zip holding them",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(get_settings().dark_pack_dir or Path(__file__).parents[3] / "dark-pack"),
        help="the Dark Pack folder (default: HORATIO_DARK_PACK_DIR, or dark-pack/)",
    )
    args = parser.parse_args(argv)
    try:
        record = import_kits(args.zips, args.out)
    except fetching.Failed as error:
        sys.exit(str(error))
    logos = ", ".join(record["logos"]) or "no Dark Pack logo"
    print(f"Imported {logos} and {len(record['clans'])} clan symbols into {args.out}")
    missing = sorted(set(CLAN_SYMBOLS) - set(record["clans"]))
    if missing:
        print(f"Not in these kits: {', '.join(missing)}", file=sys.stderr)


if __name__ == "__main__":
    main()

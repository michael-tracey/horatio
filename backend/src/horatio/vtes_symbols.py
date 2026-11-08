"""The symbols of *Vampire: The Eternal Struggle* (#534), fetched from KRCG
(https://static.krcg.org/): characters' Jyhad cards show them (horatio.jyhad_card), and
later perhaps clan and discipline symbols elsewhere, and Discord emoji.

KRCG's symbols are free to use under the Dark Pack Agreement, so, like the Dark
Pack's (horatio.dark_pack), Horatio never ships them: the custodian fetches them
in Custodian › Tools. **Wherever they are shown, credit KRCG and give Paradox's
notice** ("Portions of the materials are the copyrights and trademarks of Paradox
Interactive AB, and are used with permission."), on the About page with the rest.

KRCG's folders can be listed, so the files are found from the listings, not from
a list kept here: the clans, the disciplines (inferior and superior) and the game's
icons, as SVG, WebP (for places that can't take SVG) and transparent PNG (for
Discord emoji, which must be 256 KB or less), and the two fonts. Old clan symbols
in `clan/deprecated/` are left out. That's a few hundred small files, fetched one
at a time with a short pause between, to be polite. They are kept beside the Dark
Pack's:

    <dark pack folder>/vtes/
      manifest.json                 when, from where, and what came
      svg/clan/brujah.svg, svg/disc/inf/aus.svg, svg/disc/sup/aus.svg, svg/icon/...
      webp/..., png/...             the same in WebP and PNG
      fonts/ankha2.otf, fonts/vtes-clans.otf

A fetch is written into a new folder and swapped in once it is whole, so one that
fails leaves the last in place.
"""

import json
import re
import shutil
import time
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin

from horatio import dark_pack, fetching
from horatio.models import User

DEFAULT_ADDRESS = "https://static.krcg.org/"
KINDS = ("svg", "webp", "png")
GROUPS = ("clan", "disc/inf", "disc/sup", "icon")
# KRCG's fonts, in web/: the disciplines, virtues and card types, and the clans.
FONTS = ("ankha2.otf", "vtes-clans.otf")
MEDIA_TYPES = {"svg": "image/svg+xml", "webp": "image/webp", "png": "image/png"}
NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
HREF = re.compile(r'href="([^"?#]+)"')
MAX_LISTING = 1024 * 1024
MAX_SYMBOL = 2 * 1024 * 1024
MAX_FONT = 5 * 1024 * 1024
# More files than this in one folder is not KRCG's symbols.
MAX_FILES = 400
# Between one request and the next, in seconds; and how long a fetch may take.
PAUSE = 0.2
FETCH_TIME = 30 * 60
# The most a Discord emoji may be.
DISCORD_EMOJI = 256 * 1024
FOLDER = "vtes"
WORK = ".vtes-"

# Horatio's clans and bloodlines (as MET: VTM names them) with a symbol at KRCG,
# by KRCG's name for it. KRCG uses V5's names where the clan was renamed.
CLANS = {
    "Assamite": "banuhaqim",
    "Baali": "baali",
    "Brujah": "brujah",
    "Brujah: True Brujah": "truebrujah",
    "Caitiff": "caitiff",
    "Cappadocians: Samedi": "samedi",
    "Daughters of Cacophony": "daughtersofcacophony",
    "Followers of Set": "ministry",
    "Gangrel": "gangrel",
    "Gangrel: Ahrimanes": "ahrimanes",
    "Gargoyles": "gargoyles",
    "Giovanni": "giovanni",
    "Lasombra": "lasombra",
    "Lasombra: Kiasyd": "kiasyd",
    "Malkavian": "malkavian",
    "Nagaraja": "nagaraja",
    "Nosferatu": "nosferatu",
    "Ravnos": "ravnos",
    "Salubri": "salubri",
    "Toreador": "toreador",
    "Toreador: Ishtarri": "ishtarri",
    "Tremere": "tremere",
    "Tzimisce": "tzimisce",
    "Ventrue": "ventrue",
}
# Horatio's disciplines, by KRCG's three letters. A path of Necromancy or
# Thaumaturgy has its discipline's symbol.
DISCIPLINES = {
    "Animalism": "ani",
    "Auspex": "aus",
    "Celerity": "cel",
    "Chimerstry": "chi",
    "Daimoinon": "dai",
    "Dementation": "dem",
    "Dominate": "dom",
    "Fortitude": "for",
    "Melpominee": "mel",
    "Mytherceria": "myt",
    "Necromancy": "nec",
    "Obeah": "obe",
    "Obfuscate": "obf",
    "Obtenebration": "obt",
    "Potence": "pot",
    "Presence": "pre",
    "Protean": "pro",
    "Quietus": "qui",
    "Serpentis": "ser",
    "Spiritus": "spi",
    "Temporis": "tem",
    "Thanatosis": "thn",
    "Thaumaturgy": "tha",
    "Valeren": "val",
    "Vicissitude": "vic",
    "Visceratika": "vis",
}

job = fetching.Job("VTES symbols fetch")


def folder() -> Path | None:
    """Where the symbols are kept, fetched or not."""
    root = dark_pack.root()
    return root / FOLDER if root is not None else None


def manifest() -> dict[str, Any]:
    found = folder()
    if found is None:
        return {}
    try:
        return json.loads((found / "manifest.json").read_text())
    except (OSError, ValueError):
        return {}


def symbol_file(kind: str, path: str) -> Path | None:
    """A symbol's file, as `svg`, `clan/brujah.svg`. Only names a fetch writes are
    looked up, so a request can never reach outside the folder."""
    found = folder()
    if found is None or kind not in KINDS:
        return None
    group, _, name = path.rpartition("/")
    stem, _, suffix = name.rpartition(".")
    if group not in GROUPS or suffix != kind or not NAME.fullmatch(stem):
        return None
    file = found / kind / group / name
    return file if file.is_file() else None


def font_file(name: str) -> Path | None:
    found = folder()
    if found is None or name not in FONTS:
        return None
    file = found / "fonts" / name
    return file if file.is_file() else None


def discipline_of(name: str) -> str:
    """A path's discipline: "Necromancy: Ash Path" is Necromancy's."""
    return name.split(":")[0].strip()


def symbols(record: dict[str, Any], group: str) -> set[str]:
    """The names fetched in a group, in every kind."""
    files = record.get("files", {})
    found = [set(files.get(f"{kind}/{group}", [])) for kind in KINDS]
    return set.intersection(*found) if found else set()


# --- fetching -----------------------------------------------------------------------------


def listed(page: bytes, kind: str) -> list[str]:
    """The files of a kind in one of KRCG's folder listings (nginx's): names only, so
    folders (`deprecated/`) and anything elsewhere are left out."""
    found: list[str] = []
    for href in HREF.findall(page.decode("utf-8", "replace")):
        name = unquote(href)
        stem, _, suffix = name.rpartition(".")
        if suffix == kind and NAME.fullmatch(stem) and name not in found:
            found.append(name)
    return found


def looks_like(kind: str, data: bytes) -> bool:
    if kind == "svg":
        head = data[:2048].lstrip().lower()
        return (head.startswith(b"<?xml") or head.startswith(b"<svg")) and (
            b"<script" not in data.lower()
        )
    if kind == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if kind == "webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    # A font: OpenType or TrueType.
    return data[:4] in (b"OTTO", b"\x00\x01\x00\x00", b"true")


def fetch(user: User, address: str) -> None:
    """Start fetching the symbols from `address` (KRCG's, by default), in the
    background."""
    address = fetching.check_address(address)
    root = dark_pack.writable_root()
    user_id = user.id

    def work() -> None:
        try:
            record = fetch_now(root, address)
        except Exception as error:
            fetching.record(
                user_id,
                "vtes_symbols.fetch_failed",
                address=address,
                error=fetching.message(error),
            )
            raise
        fetching.record(user_id, "vtes_symbols.fetched", address=address, **counts(record))

    job.start(user.handle, "Starting", work)


def fetch_now(root: Path, address: str) -> dict[str, Any]:
    base = address if address.endswith("/") else f"{address}/"
    fetching.sweep(root, (WORK,))
    new = root / f"{WORK}new-{uuid.uuid4().hex}"
    new.mkdir()
    deadline = time.monotonic() + FETCH_TIME
    try:
        with fetching.client() as http:
            first = True

            def get(url: str, cap: int) -> bytes:
                nonlocal first
                if not first:
                    fetching.sleep(PAUSE)
                first = False
                if time.monotonic() > deadline:
                    raise fetching.Failed("The fetch took too long, and was stopped.")
                return fetching.get(http, url, cap=cap)

            wanted: list[tuple[str, str, str]] = []
            for kind in KINDS:
                for group in GROUPS:
                    job.step("Listing the symbols", len(wanted))
                    names = listed(get(urljoin(base, f"{kind}/{group}/"), MAX_LISTING), kind)
                    if len(names) > MAX_FILES:
                        raise fetching.Failed(
                            f"{urljoin(base, f'{kind}/{group}/')} lists more files than expected."
                        )
                    wanted += [(kind, group, n) for n in names]
            if not any(group == "clan" for _, group, _ in wanted):
                raise fetching.Failed(f"No clan symbols are listed at {base}.")
            total = len(wanted) + len(FONTS)
            record: dict[str, Any] = {"files": {}, "fonts": [], "large_png": {}}
            for done, (kind, group, name) in enumerate(wanted):
                job.step("Fetching the symbols", done, total)
                url = urljoin(base, f"{kind}/{group}/{name}")
                data = get(url, MAX_SYMBOL)
                if not looks_like(kind, data):
                    raise fetching.Failed(f"{url} isn't the {kind.upper()} image it should be.")
                target = new / kind / group / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                record["files"].setdefault(f"{kind}/{group}", []).append(name.rpartition(".")[0])
                if kind == "png" and len(data) > DISCORD_EMOJI:
                    record["large_png"][f"{group}/{name}"] = len(data)
            for done, name in enumerate(FONTS, len(wanted)):
                job.step("Fetching the symbols", done, total)
                url = urljoin(base, f"web/{name}")
                data = get(url, MAX_FONT)
                if not looks_like("font", data):
                    raise fetching.Failed(f"{url} isn't the font it should be.")
                (new / "fonts").mkdir(exist_ok=True)
                (new / "fonts" / name).write_bytes(data)
                record["fonts"].append(name)
        record = {"fetched_at": datetime.now(UTC).isoformat(), "address": address, **record}
        (new / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
        swap_in(new, root / FOLDER)
    finally:
        shutil.rmtree(new, ignore_errors=True)
    return record


def swap_in(new: Path | None, kept: Path) -> None:
    """Put the fetch in `new` in place of the symbols in `kept`, or with no `new`,
    take them away."""
    old = kept.parent / f"{WORK}old-{uuid.uuid4().hex}"
    if kept.exists():
        kept.rename(old)
    try:
        if new is not None:
            new.rename(kept)
    except BaseException:
        if old.exists():
            old.rename(kept)
        raise
    shutil.rmtree(old, ignore_errors=True)


def counts(record: dict[str, Any]) -> dict[str, int]:
    """A fetch, for the audit log."""
    files: dict[str, list[str]] = record.get("files", {})
    return {"symbols": sum(len(n) for n in files.values()), "fonts": len(record.get("fonts", []))}


def remove(user: User) -> None:
    """Take the symbols off the server."""
    root = dark_pack.writable_root()
    job.run_now(user.handle, "Removing", lambda: swap_in(None, root / FOLDER))


def matched(
    names: Iterable[str], table: dict[str, str], have: set[str]
) -> list[tuple[str, str | None]]:
    """Each of Horatio's names with KRCG's symbol for it, if it was fetched."""
    found: list[tuple[str, str | None]] = []
    for name in names:
        krcg = table.get(name)
        found.append((name, krcg if krcg in have else None))
    return found

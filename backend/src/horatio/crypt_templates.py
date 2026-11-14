"""Clan crypt card templates for characters' Jyhad cards (#850): the 2020 Dark Pack
"Community Created Card" frames, one for each clan (and the antitribu), as
`2020_Crypt_<Clan>.png`. They are Paradox's, under the Dark Pack Agreement, so
like the Dark Pack's resources (horatio.dark_pack) Horatio never ships them: the
custodian uploads them in Custodian › Tools, a zip of them or the PNGs, and they
are kept beside the Dark Pack's, converted to WebP:

    <dark pack folder>/crypt-templates/
      manifest.json        when, and which file each came from
      tzimisce.webp, brujahantitribu.webp, ...

A character's card uses its clan's template (a bloodline's own where there is one,
else its clan's), the antitribu's for a Sabbat character where there is one, and
for a Sabbat Caitiff the Panders'. Without one, the card keeps Horatio's own frame
(#560).

Every template has the same layout, 819 × 1114 px: a 63 × 88 mm card with a 1/8"
bleed, at about 300 dpi. The portrait's oval is transparent, so the portrait goes
under the template; the disciplines go down the sidebar on the left, under the
printed clan symbol; the name across the top; the text in the pale box at the
bottom; the capacity on the printed blood drop. `LAYOUT` is where they are, as
`detect` found them on the Tzimisce template (`python -m horatio.crypt_templates
<png>` prints it for any template); the card's own layout
(frontend/src/pages/jyhad/layout.ts) has the same numbers. An upload is checked
against the oval, so a template of another layout is turned away.
"""

import argparse
import json
import re
import shutil
import uuid
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image, ImageStat, UnidentifiedImageError

from horatio import dark_pack, fetching
from horatio.models import User

FOLDER = "crypt-templates"
WORK = ".crypt-"
SIZE = (819, 1114)
# Where things are on a template, in its pixels: (x, y, width, height). The oval,
# text box and drop as `detect` finds them; the name's band (above the oval, left
# of the Dark Pack mark) and the sidebar's top (under the printed clan symbol)
# chosen from the same image.
LAYOUT: dict[str, tuple[int, int, int, int]] = {
    "oval": (194, 153, 531, 689),
    "text": (188, 858, 546, 146),
    "drop": (675, 956, 66, 66),
    "sidebar": (67, 300, 99, 744),
    "name": (78, 76, 640, 64),
}
# How far the oval may be from LAYOUT's on an upload, in pixels.
TOLERANCE = 4
# A file name: "2020_Crypt_Brujah.png", "2020_Crypt_Salubri (1).png" (a second
# download of the same).
NAME = re.compile(r"2020_Crypt_(?P<name>.+?)(?: \(\d+\))?\.png", re.IGNORECASE)
MAX_FILE = 4 * 1024 * 1024
MAX_UPLOAD = 60 * 1024 * 1024
MAX_UNPACKED = 80 * 1024 * 1024
MAX_FILES = 80
QUALITY = 90

# The templates there are, by key (the file's name, lower case, letters only),
# with what to call them.
TEMPLATES = {
    "ahrimane": "Ahrimane",
    "akunanse": "Akunanse",
    "assamite": "Assamite",
    "baali": "Baali",
    "bloodbrother": "Blood Brother",
    "brujah": "Brujah",
    "brujahantitribu": "Brujah antitribu",
    "caitiff": "Caitiff",
    "daughterofcacophony": "Daughter of Cacophony",
    "followerofset": "Follower of Set",
    "gangrel": "Gangrel",
    "gangrelantitribu": "Gangrel antitribu",
    "gargoyle": "Gargoyle",
    "giovanni": "Giovanni",
    "harbingerofskulls": "Harbinger of Skulls",
    "ishtarri": "Ishtarri",
    "kiasyd": "Kiasyd",
    "lasombra": "Lasombra",
    "malkavian": "Malkavian",
    "malkavianantitribu": "Malkavian antitribu",
    "nagaraja": "Nagaraja",
    "nosferatu": "Nosferatu",
    "nosferatuantitribu": "Nosferatu antitribu",
    "osebo": "Osebo",
    "pander": "Pander",
    "ravnos": "Ravnos",
    "salubri": "Salubri",
    "salubriantitribu": "Salubri antitribu",
    "samedi": "Samedi",
    "toreador": "Toreador",
    "toreadorantitribu": "Toreador antitribu",
    "tremere": "Tremere",
    "tremereantitribu": "Tremere antitribu",
    "truebrujah": "True Brujah",
    "tzimisce": "Tzimisce",
    "ventrue": "Ventrue",
    "ventrueantitribu": "Ventrue antitribu",
}
# Horatio's clans and bloodlines (as MET: VTM names them) with a template. Another
# bloodline takes its clan's ("Salubri: Healer" is Salubri's).
CLANS = {
    "Assamite": "assamite",
    "Baali": "baali",
    "Brujah": "brujah",
    "Brujah: True Brujah": "truebrujah",
    "Caitiff": "caitiff",
    "Cappadocians: Samedi": "samedi",
    "Daughters of Cacophony": "daughterofcacophony",
    "Followers of Set": "followerofset",
    "Gangrel": "gangrel",
    "Gangrel: Ahrimanes": "ahrimane",
    "Gargoyles": "gargoyle",
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
SABBAT = "Sabbat"
# The Sabbat's Caitiff are the Panders.
SABBAT_CAITIFF = "pander"

job = fetching.Job("Jyhad card templates upload")


def key_of(filename: str) -> str | None:
    """A template's key from its file's name, if it is one of TEMPLATES."""
    found = NAME.fullmatch(PurePosixPath(filename).name)
    if found is None:
        return None
    key = re.sub(r"[^a-z]", "", found["name"].lower())
    return key if key in TEMPLATES else None


def wanted(clan: str | None, sect: str | None) -> list[str]:
    """The templates a character of this clan and sect would use, best first."""
    if not clan:
        return []
    base = CLANS.get(clan) or CLANS.get(clan.split(":")[0].strip())
    if base is None:
        return []
    if sect == SABBAT:
        if f"{base}antitribu" in TEMPLATES:
            return [f"{base}antitribu", base]
        if base == "caitiff":
            return [SABBAT_CAITIFF, base]
    return [base]


def chosen(clan: str | None, sect: str | None, have: Iterable[str]) -> str | None:
    """The template a card uses, of those on the server."""
    present = set(have)
    return next((key for key in wanted(clan, sect) if key in present), None)


# --- what is on the server ------------------------------------------------------------------


def folder() -> Path | None:
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


def present(record: dict[str, Any] | None = None) -> set[str]:
    """The templates on the server, by key."""
    templates = (record if record is not None else manifest()).get("templates", {})
    return {key for key in templates if key in TEMPLATES}


def template_file(key: str) -> Path | None:
    """A template's file; only keys of TEMPLATES are looked up."""
    found = folder()
    if found is None or key not in TEMPLATES:
        return None
    file = found / f"{key}.webp"
    return file if file.is_file() else None


def version(record: dict[str, Any]) -> str:
    """Changes whenever the templates do, for the address the card asks for."""
    return re.sub(r"[^0-9]", "", str(record.get("uploaded_at", "")))


# --- the layout -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Layout:
    """Where `detect` found things on a template, in its pixels: (x, y, w, h)."""

    oval: tuple[int, int, int, int] | None
    text: tuple[int, int, int, int] | None
    drop: tuple[int, int, int, int] | None
    sidebar_edge: int | None


def oval_of(image: Image.Image) -> tuple[int, int, int, int] | None:
    """The portrait's hole: the box round the template's transparent pixels inside
    the card (not its corners)."""
    if image.mode != "RGBA":
        return None
    alpha = image.getchannel("A").crop((40, 40, image.width - 40, image.height - 40))
    hole = alpha.point([255 if a < 128 else 0 for a in range(256)]).getbbox()
    if hole is None:
        return None
    x0, y0, x1, y1 = hole
    return (x0 + 40, y0 + 40, x1 - x0, y1 - y0)


def _brightness(image: Image.Image, box: tuple[int, int, int, int]) -> float:
    return ImageStat.Stat(image.crop(box).convert("L")).mean[0]


def _edge(values: list[float], start: int, rise: bool) -> int | None:
    """Where a run of brightness steps up (`rise`) or down by the most."""
    best, at = 0.0, None
    for i in range(1, len(values)):
        step = values[i] - values[i - 1]
        step = step if rise else -step
        if step > best:
            best, at = step, start + i
    return at if best > 40 else None


def detect(image: Image.Image) -> Layout:
    """Find the oval, the pale text box, the blood drop and the sidebar's edge on a
    template, the way LAYOUT's numbers were found."""
    image = image.convert("RGBA")
    oval = oval_of(image)
    rgb = image.convert("RGB")
    # The text box: pale against the frame, below the oval. Its sides from a band of
    # rows through it, its top and bottom from a band of columns.
    cols = [_brightness(rgb, (x, 880, x + 1, 960)) for x in range(150, 200)]
    cols_right = [_brightness(rgb, (x, 880, x + 1, 960)) for x in range(700, 780)]
    rows = [_brightness(rgb, (300, y, 600, y + 1)) for y in range(840, 880)]
    rows_bottom = [_brightness(rgb, (300, y, 600, y + 1)) for y in range(980, 1030)]
    left = _edge(cols, 150, rise=True)
    right = _edge(cols_right, 700, rise=False)
    top = _edge(rows, 840, rise=True)
    bottom = _edge(rows_bottom, 980, rise=False)
    text = None
    if left is not None and right is not None and top is not None and bottom is not None:
        text = (left, top, right - left, bottom - top)
    # The drop: its strong red, in the corner it sits in. (Some clans' frames have
    # red of their own nearby: LAYOUT's came from the Tzimisce template's.)
    x0, y0 = 660, 940
    corner = rgb.crop((x0, y0, 760, 1035))
    pixels = corner.load()
    reds = [
        (x, y)
        for y in range(corner.height)
        for x in range(corner.width)
        if (p := pixels[x, y]) and p[0] > 150 and p[1] < 80 and p[2] < 80  # type: ignore[index]
    ]
    drop = None
    if reds:
        xs = [x for x, _ in reds]
        ys = [y for _, y in reds]
        drop = (x0 + min(xs), y0 + min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
    # The sidebar's edge: the light line down the card's left, through the middle.
    edge = [_brightness(rgb, (x, 400, x + 1, 800)) for x in range(140, 200)]
    sidebar_edge = _edge(edge, 140, rise=True)
    return Layout(oval=oval, text=text, drop=drop, sidebar_edge=sidebar_edge)


def to_mm(box: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    """A box in a template's pixels, in the card's millimetres: the card is 63 × 88
    mm inside a 1/8" (3.175 mm) bleed."""
    scale = SIZE[1] / (88 + 2 * 3.175)
    x, y, w, h = box
    return (
        round(x / scale - 3.175, 2),
        round(y / scale - 3.175, 2),
        round(w / scale, 2),
        round(h / scale, 2),
    )


# --- uploading ------------------------------------------------------------------------------


@dataclass
class Skipped:
    name: str
    why: str


def check(name: str, data: bytes) -> tuple[str, Image.Image]:
    """A template's key and image, or Failed saying what's wrong with it."""
    key = key_of(name)
    if key is None:
        raise fetching.Failed("not a 2020_Crypt_<Clan>.png file of a clan Horatio knows")
    if len(data) > MAX_FILE:
        raise fetching.Failed(f"over {fetching.megabytes(MAX_FILE)}")
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as error:
        raise fetching.Failed("not an image that can be read") from error
    if image.format != "PNG":
        raise fetching.Failed("not a PNG")
    if image.size != SIZE:
        raise fetching.Failed(f"{image.width} × {image.height} px, not {SIZE[0]} × {SIZE[1]}")
    oval = oval_of(image.convert("RGBA"))
    expected = LAYOUT["oval"]
    if oval is None or any(abs(a - b) > TOLERANCE for a, b in zip(oval, expected, strict=True)):
        raise fetching.Failed("its portrait's oval isn't where the 2020 templates have it")
    return key, image.convert("RGBA")


def files_of(uploads: Sequence[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """The PNGs uploaded, and those in any zip uploaded, by name."""
    if sum(len(data) for _, data in uploads) > MAX_UPLOAD:
        raise fetching.Failed(
            f"That's over {fetching.megabytes(MAX_UPLOAD)}: upload fewer at a time."
        )
    found: list[tuple[str, bytes]] = []
    for name, data in uploads:
        if not zipfile.is_zipfile(BytesIO(data)):
            found.append((name, data))
            continue
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = [
                e
                for e in archive.infolist()
                if not e.is_dir()
                and e.filename.lower().endswith(".png")
                and not PurePosixPath(e.filename).name.startswith(".")
                and "__MACOSX" not in e.filename
            ]
            if sum(e.file_size for e in entries) > MAX_UNPACKED:
                raise fetching.Failed(f"{name} unpacks to more than the templates are.")
            for entry in entries:
                if entry.file_size > MAX_FILE:
                    found.append((entry.filename, b"\0" * (MAX_FILE + 1)))
                else:
                    found.append((entry.filename, archive.read(entry)))
    if len(found) > MAX_FILES:
        raise fetching.Failed("That's more files than there are templates.")
    if not found:
        raise fetching.Failed("There are no PNG files in that upload.")
    return found


def install(user: User, uploads: Sequence[tuple[str, bytes]]) -> tuple[list[str], list[Skipped]]:
    """Add the templates uploaded to those on the server, replacing any of the same
    clan. Returns the keys added and the files left out, with why."""
    root = dark_pack.writable_root()
    out: dict[str, Any] = {}

    def work() -> None:
        out["result"] = install_now(root, uploads)

    job.run_now(user.handle, "Uploading", work)
    return out["result"]


def install_now(
    root: Path, uploads: Sequence[tuple[str, bytes]]
) -> tuple[list[str], list[Skipped]]:
    files = files_of(uploads)
    added: dict[str, tuple[str, Image.Image]] = {}
    skipped: list[Skipped] = []
    for name, data in files:
        shown = PurePosixPath(name).name
        try:
            key, image = check(name, data)
        except fetching.Failed as error:
            skipped.append(Skipped(shown, str(error)))
            continue
        if key in added:
            skipped.append(Skipped(shown, f"the same clan as {added[key][0]}"))
            continue
        added[key] = (shown, image)
    if not added:
        raise fetching.Failed(
            "None of those is a template: "
            + "; ".join(f"{s.name}: {s.why}" for s in skipped[:5])
            + ("…" if len(skipped) > 5 else "")
        )
    fetching.sweep(root, (WORK,))
    kept = root / FOLDER
    new = root / f"{WORK}new-{uuid.uuid4().hex}"
    new.mkdir()
    try:
        record = {"templates": {}}
        try:
            before = json.loads((kept / "manifest.json").read_text())
        except (OSError, ValueError):
            before = {}
        for key, entry in before.get("templates", {}).items():
            if key in TEMPLATES and key not in added and (kept / f"{key}.webp").is_file():
                shutil.copy2(kept / f"{key}.webp", new / f"{key}.webp")
                record["templates"][key] = entry
        at = datetime.now(UTC).isoformat()
        for key, (shown, image) in added.items():
            image.save(new / f"{key}.webp", "WEBP", quality=QUALITY, method=4)
            record["templates"][key] = {"from": shown, "at": at}
        record = {"uploaded_at": at, **record}
        (new / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
        swap_in(new, kept)
    finally:
        shutil.rmtree(new, ignore_errors=True)
    return sorted(added), skipped


def swap_in(new: Path | None, kept: Path) -> None:
    """Put `new` in place of the templates in `kept`, or with no `new`, take them away."""
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


def remove(user: User) -> None:
    """Take the templates off the server."""
    root = dark_pack.writable_root()
    job.run_now(user.handle, "Removing", lambda: swap_in(None, root / FOLDER))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m horatio.crypt_templates",
        description="Find where the oval, text box, blood drop and sidebar are on a template.",
    )
    parser.add_argument("png", type=Path, help="a 2020_Crypt_<Clan>.png template")
    args = parser.parse_args(argv)
    found = detect(Image.open(args.png))
    out: dict[str, Any] = {}
    for name in ("oval", "text", "drop"):
        box = getattr(found, name)
        out[name] = {"px": box, "mm": to_mm(box) if box else None}
    out["sidebar_edge_px"] = found.sidebar_edge
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

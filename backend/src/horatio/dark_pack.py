"""Paradox's Dark Pack resources (issue #92): the Dark Pack logo and the clans'
symbols, which the Dark Pack Agreement lets a free fan app like Horatio use.

Horatio never ships them: the licence is personal and cannot be passed on
under Horatio's AGPL. Each server's operator downloads the kit from
https://www.paradoxinteractive.com/games/world-of-darkness/community/dark-pack-agreement
and imports it into the folder HORATIO_DARK_PACK_DIR names (`dark-pack/` beside
the code, by default):

    uv run python -m horatio.dark_pack "World of Darkness Community Assets.zip" \\
        WoD-Logos-and-Symbols.zip --out ../dark-pack

The import reads the zips as downloaded, without unpacking them, and writes only
what Horatio uses, at the sizes it serves:

    dark-pack/
      manifest.json                  what was imported, and from where
      logo.webp, logo-bw.webp        the Dark Pack logo (colour, black and white)
      clans/<slug>/128.webp, 600.webp          a clan's symbol, black
      clans/<slug>/white/128.webp, 600.webp    and white, for dark backgrounds

A clan the custodian has uploaded no logo for uses its symbol here; a bloodline
uses its clan's (horatio.badges).
"""

import argparse
import json
import re
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from horatio import pictures
from horatio.config import get_settings

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
    so the kits' own top folders don't matter."""

    def __init__(self, paths: Sequence[Path]) -> None:
        self.zips = [zipfile.ZipFile(p) for p in paths]

    def find(self, endings: Sequence[str]) -> tuple[str, bytes] | None:
        for ending in endings:
            for kit in self.zips:
                for name in kit.namelist():
                    if name.endswith(f"/{ending}") or name == ending:
                        return name, kit.read(name)
        return None

    def close(self) -> None:
        for kit in self.zips:
            kit.close()


def import_kits(paths: Sequence[Path], out: Path) -> dict[str, Any]:
    """Write the Dark Pack logo and the clans' symbols from the kits into `out`."""
    kits = Kits(paths)
    record: dict[str, Any] = {"sources": [p.name for p in paths], "logos": {}, "clans": {}}
    try:
        out.mkdir(parents=True, exist_ok=True)
        for name, endings in LOGOS.items():
            found = kits.find(endings)
            if found is None:
                continue
            image = pictures.read_image(found[1])
            if image.width > LOGO_WIDTH:
                image = image.resize((LOGO_WIDTH, round(image.height * LOGO_WIDTH / image.width)))
            image.save(out / name, "WEBP", lossless=True)
            record["logos"][name] = found[0]
        for clan, (black, white) in CLAN_SYMBOLS.items():
            found = kits.find(black)
            if found is None:
                continue
            directory = out / "clans" / slug(clan)
            pictures.write_logo(directory, pictures.read_image(found[1]))
            entry: dict[str, Any] = {"slug": slug(clan), "from": found[0]}
            light = kits.find(white)
            if light is not None:
                pictures.write_logo(directory / "white", pictures.read_image(light[1]))
                entry["white"] = light[0]
            record["clans"][clan] = entry
    finally:
        kits.close()
    (out / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m horatio.dark_pack",
        description="Import the Dark Pack logo and clan symbols from Paradox's kit zips.",
    )
    parser.add_argument("zips", nargs="+", type=Path, help="the kit's zip files, as downloaded")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(get_settings().dark_pack_dir or Path(__file__).parents[3] / "dark-pack"),
        help="the Dark Pack folder (default: HORATIO_DARK_PACK_DIR, or dark-pack/)",
    )
    args = parser.parse_args(argv)
    record = import_kits(args.zips, args.out)
    logos = ", ".join(record["logos"]) or "no Dark Pack logo"
    print(f"Imported {logos} and {len(record['clans'])} clan symbols into {args.out}")
    missing = sorted(set(CLAN_SYMBOLS) - set(record["clans"]))
    if missing:
        print(f"Not in these kits: {', '.join(missing)}", file=sys.stderr)


if __name__ == "__main__":
    main()

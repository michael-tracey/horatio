"""Pictures people upload (issue #70): characters' pictures, and the clan logos the
custodian adds.

An upload is checked to really be an image (JPEG, PNG, WebP or HEIC, up to 10 MB),
turned the right way up and stripped of its metadata, the GPS location phones add
among it. What is uploaded is never kept as it came: only copies at the sizes
Horatio shows, all WebP, in `HORATIO_UPLOAD_DIR`:

- a character's picture: squares of 48 px (lists, the bell), 128 px (the roster)
  and 512 px (the character's page) cut from its crop; the badge's portrait, a
  4:5 frame around the same crop, at 300 DPI, as WebP and as JPEG for printing;
  and the whole picture up to 2048 px, so the crop can be moved later.
- a clan logo: fitted into squares of 128 and 600 px, keeping its transparency.
- a troupe's portrait (issue #119): the same squares as a character's, and the
  whole picture for moving the crop; its banner, cut 3:1 from the middle, 1500
  and 750 px wide.

- a troupe's post's picture, or a news agency's masthead (issue #510): the whole
  picture, shrunk to 1200 and 600 px wide.
- a news agency's portrait (issue #883), its stories' sender on Discord: the same
  squares as a character's, and the whole picture for moving the crop.
- a troupe's rock, paper or scissors for the Throws tab (issue #670): the whole
  picture, centred on a transparent square of 128 and 512 px, as a clan logo is.
- a blog author's picture (#1159): squares of 96 px (under each article), 256 px
  (their page) and 512 px (link previews), and the whole picture for moving the crop.
- a blog article's hero picture (issue #1156): as a post's, 1200 and 600 px wide.
  Kept apart from any troupe, under `blog/`, so the blog's public pages can show
  them (#1158).
- a picture in a blog article's words (issue #1163): as a post's, 1200 and 600 px
  wide, under `blog-pictures/<article id>/`.

Each upload (and each new crop) is kept in a directory of its own, named by a new
id, so its address changes and no cache ever shows the one it replaced.

A blog article's pictures (#1183) keep each copy's width and height too, so its pages
keep their room before they load: `write_post_picture` returns them, and
`post_picture_sizes` reads them from the files of one kept before.
"""

import math
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pillow_heif
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from horatio.config import get_settings

pillow_heif.register_heif_opener()

MAX_BYTES = 10 * 1024 * 1024
# Bigger than any phone's camera; refused before decoding, so a small file that
# unpacks into an enormous image cannot exhaust the server's memory.
MAX_PIXELS = 50_000_000
# Pillow's names for what can be uploaded. MPO is how some cameras save a JPEG.
FORMATS = {"JPEG", "MPO", "PNG", "WEBP", "HEIF"}

# The whole picture is kept up to this size, for moving the crop later.
KEPT = 2048
SQUARES = (48, 128, 512)
# The badge's portrait (3 × 5 in badge): 1.6 × 2 in at 300 DPI.
PORTRAIT = (480, 600)
LOGOS = (128, 600)
# A troupe's banner: 3 wide by 1 high, at these widths.
BANNERS = (1500, 750)

# The files a character's picture is kept as, and a clan logo's.
PICTURE_FILES = {
    *(f"{s}.webp" for s in SQUARES),
    "portrait.webp",
    "portrait.jpg",
    "full.webp",
}
LOGO_FILES = {f"{s}.webp" for s in LOGOS}
TROUPE_PORTRAIT_FILES = {*(f"{s}.webp" for s in SQUARES), "full.webp"}
BANNER_FILES = {f"{w}.webp" for w in BANNERS}
# A troupe's rock, paper or scissors: 512 px for the Throws tab, 128 px to preview.
THROWS = (128, 512)
THROW_FILES = {f"{s}.webp" for s in THROWS}
# A blog author's picture: under each article, on their page, and in link previews.
AUTHOR_SQUARES = (96, 256, 512)
AUTHOR_FILES = {*(f"{s}.webp" for s in AUTHOR_SQUARES), "full.webp"}
# A post's picture or a masthead, at these widths, keeping its shape.
POST_WIDTHS = (1200, 600)
POST_FILES = {f"{w}.webp" for w in POST_WIDTHS}
# A blog article's hero picture is twice as wide as it is high (#1157).
HERO_RATIO = 2

# Each copy's width and height in pixels, by its file's name: {"1200.webp": [w, h], ...}.
Sizes = dict[str, list[int]]


class PictureError(Exception):
    """An upload Horatio cannot use; the message says why, for the person."""


@dataclass(frozen=True)
class Crop:
    """The square portrait's place in a picture: its left and top edges as
    fractions of the picture's width and height, and its side as a fraction of
    the width. Fractions, so a crop chosen on a scaled-down preview fits the
    picture at any size."""

    x: float
    y: float
    size: float


Box = tuple[int, int, int, int]


def upload_dir() -> Path | None:
    """Where pictures are kept, or None where they are not set up."""
    setting = get_settings().upload_dir
    return Path(setting) if setting else None


def read_image(data: bytes) -> Image.Image:
    """The upload as a clean image: really an image of an allowed kind, the right
    way up, in sRGB, carrying no metadata. Refused with a PictureError otherwise."""
    if len(data) > MAX_BYTES:
        raise PictureError("That picture is over 10 MB. Try a smaller one.")
    try:
        with Image.open(BytesIO(data)) as probe:
            if probe.format not in FORMATS:
                raise PictureError("Only JPEG, PNG, WebP and HEIC pictures can be used.")
            if probe.width * probe.height > MAX_PIXELS:
                raise PictureError("That picture is too large. Try a smaller one.")
            probe.verify()
        image = Image.open(BytesIO(data))
        image.load()
        image = ImageOps.exif_transpose(image)
    except PictureError:
        raise
    except Exception:
        # Whatever a damaged or disguised file makes Pillow raise.
        raise PictureError("That file is not a picture Horatio can read.") from None

    alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
    mode = "RGBA" if alpha else "RGB"
    profile = image.info.get("icc_profile")
    if profile and image.mode in ("RGB", "RGBA"):
        # Phones take pictures in wider colour spaces; screens and printers expect sRGB.
        try:
            converted = ImageCms.profileToProfile(
                image,
                ImageCms.ImageCmsProfile(BytesIO(profile)),
                ImageCms.createProfile("sRGB"),
                outputMode=image.mode,
            )
            if converted is not None:
                image = converted
        except ImageCms.PyCMSError:
            pass
    clean = image.convert(mode)
    # Nothing of the upload's own goes with it: no EXIF (GPS), XMP or profile.
    clean.info = {}
    return clean


def square_box(width: int, height: int, crop: Crop | None) -> Box:
    """The crop in pixels, kept inside the picture; the biggest square in the
    middle when there is none."""
    largest = min(width, height)
    if crop is None:
        side = largest
        left, top = (width - side) // 2, (height - side) // 2
    else:
        side = max(1, min(largest, round(crop.size * width)))
        left = min(max(round(crop.x * width), 0), width - side)
        top = min(max(round(crop.y * height), 0), height - side)
    return (left, top, left + side, top + side)


def portrait_box(width: int, height: int, square: Box) -> Box:
    """The badge's portrait: a 4:5 frame as wide as the square and centred on it,
    moved to stay inside the picture, and narrowed if the picture is too short.
    frontend/src/components/crop.ts draws the same frame while cropping."""
    side = square[2] - square[0]
    frame_w, frame_h = side, side * 5 / 4
    if frame_h > height:
        frame_h = height
        frame_w = height * 4 / 5
    centre_x = (square[0] + square[2]) / 2
    centre_y = (square[1] + square[3]) / 2
    left = min(max(centre_x - frame_w / 2, 0), width - frame_w)
    top = min(max(centre_y - frame_h / 2, 0), height - frame_h)
    return (round(left), round(top), round(left + frame_w), round(top + frame_h))


def _webp(image: Image.Image, path: Path, *, lossless: bool = False) -> None:
    image.save(path, "WEBP", quality=85, method=4, lossless=lossless)


def _flatten(image: Image.Image) -> Image.Image:
    """On white, for JPEG, which has no transparency: badges print on white."""
    if image.mode != "RGBA":
        return image.convert("RGB")
    back = Image.new("RGB", image.size, "white")
    back.paste(image, mask=image.getchannel("A"))
    return back


def _shrunk(image: Image.Image, longest: int) -> Image.Image:
    if max(image.size) <= longest:
        return image.copy()
    copy = image.copy()
    copy.thumbnail((longest, longest), Image.Resampling.LANCZOS)
    return copy


def _squares(
    directory: Path, image: Image.Image, crop: Crop | None, sizes: tuple[int, ...] = SQUARES
) -> Box:
    """Write the whole picture, to crop again later, and its squares into
    `directory`, which must be new. The square's box, in the picture's pixels."""
    directory.mkdir(parents=True)
    full = _shrunk(image, KEPT)
    _webp(full, directory / "full.webp")
    # Cut from the picture as uploaded, not the kept copy, for the sharpest print.
    square = square_box(image.width, image.height, crop)
    face = image.crop(square)
    for size in sizes:
        _webp(face.resize((size, size), Image.Resampling.LANCZOS), directory / f"{size}.webp")
    return square


def write_picture(directory: Path, image: Image.Image, crop: Crop | None) -> None:
    """Write a character's picture's files into `directory`, which must be new."""
    square = _squares(directory, image, crop)
    portrait = image.crop(portrait_box(image.width, image.height, square))
    portrait = ImageOps.fit(portrait, PORTRAIT, Image.Resampling.LANCZOS)
    _webp(portrait, directory / "portrait.webp")
    _flatten(portrait).save(directory / "portrait.jpg", "JPEG", quality=90, optimize=True)


def write_troupe_portrait(directory: Path, image: Image.Image, crop: Crop | None) -> None:
    """Write a troupe's portrait's files into `directory`, which must be new."""
    _squares(directory, image, crop)


def write_agency_portrait(directory: Path, image: Image.Image, crop: Crop | None) -> None:
    """Write a news agency's portrait's files into `directory`, which must be new."""
    _squares(directory, image, crop)


def write_author_picture(directory: Path, image: Image.Image, crop: Crop | None) -> None:
    """Write a blog author's picture's files into `directory`, which must be new."""
    _squares(directory, image, crop, AUTHOR_SQUARES)


def write_banner(directory: Path, image: Image.Image) -> None:
    """Write a troupe's banner's files into `directory`, which must be new."""
    directory.mkdir(parents=True)
    for width in BANNERS:
        wide = ImageOps.fit(image, (width, width // 3), Image.Resampling.LANCZOS)
        _webp(wide, directory / f"{width}.webp")


def write_post_picture(directory: Path, image: Image.Image) -> Sizes:
    """Write a post's picture's (or a masthead's) files into `directory`, which must
    be new: the whole picture at each width, never made bigger, transparency kept.
    Returns each copy's size."""
    directory.mkdir(parents=True)
    sizes: Sizes = {}
    for width in POST_WIDTHS:
        fitted = image
        if image.width > width:
            height = max(1, round(image.height * width / image.width))
            fitted = image.resize((width, height), Image.Resampling.LANCZOS)
        _webp(fitted, directory / f"{width}.webp")
        sizes[f"{width}.webp"] = [fitted.width, fitted.height]
    return sizes


def post_picture_sizes(directory: Path) -> Sizes | None:
    """The size of each copy of a picture kept as a post's is, read from its files;
    None if any of them is missing or unreadable."""
    sizes: Sizes = {}
    for name in sorted(POST_FILES):
        try:
            with Image.open(directory / name) as image:
                sizes[name] = [image.width, image.height]
        except (OSError, UnidentifiedImageError):
            return None
    return sizes


def hero_box(width: int, height: int, crop: Crop | None) -> Box:
    """A blog article's hero picture's frame in pixels (#1157): twice as wide as it is
    high, kept inside the picture, its width `crop.size` of the picture's; the widest
    frame in the middle when there is no crop. frontend/src/components/crop.ts draws
    the same frame while cropping."""
    widest = min(width, height * HERO_RATIO)
    frame_w = widest if crop is None else max(HERO_RATIO, min(widest, round(crop.size * width)))
    frame_h = max(1, min(height, round(frame_w / HERO_RATIO)))
    if crop is None:
        left, top = (width - frame_w) // 2, (height - frame_h) // 2
    else:
        left = min(max(round(crop.x * width), 0), width - frame_w)
        top = min(max(round(crop.y * height), 0), height - frame_h)
    return (left, top, left + frame_w, top + frame_h)


def write_hero_picture(directory: Path, image: Image.Image, crop: Crop | None) -> Sizes:
    """Write a blog article's hero picture's files into `directory`, which must be new:
    its 2:1 frame, as a post's picture is kept (1200 and 600 px wide). Returns each
    copy's size."""
    return write_post_picture(directory, image.crop(hero_box(image.width, image.height, crop)))


def write_logo(directory: Path, image: Image.Image) -> None:
    """Write a clan logo's files into `directory`, which must be new: the whole
    logo, centred on a transparent square."""
    directory.mkdir(parents=True)
    logo = image.convert("RGBA")
    for size in LOGOS:
        fitted = _shrunk(logo, size) if max(logo.size) > size else _grown(logo, size)
        square = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        square.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
        _webp(square, directory / f"{size}.webp", lossless=size <= 128)


def _on_square(image: Image.Image, size: int) -> Image.Image:
    """The whole picture, fitted into a transparent square of `size`, centred."""
    fitted = _shrunk(image, size) if max(image.size) > size else _grown(image, size)
    square = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    square.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    return square


def write_throw_image(directory: Path, image: Image.Image) -> None:
    """Write a troupe's rock, paper or scissors files into `directory`, which must be
    new: the whole picture on a transparent square, so nothing is cut off and a PNG's
    transparency is kept."""
    directory.mkdir(parents=True)
    picture = image.convert("RGBA")
    for size in THROWS:
        _webp(_on_square(picture, size), directory / f"{size}.webp")


def _grown(image: Image.Image, longest: int) -> Image.Image:
    """A small logo scaled up to fill its square (logos are often small files)."""
    scale = longest / max(image.size)
    size = (max(1, math.floor(image.width * scale)), max(1, math.floor(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def character_dir(root: Path, character_id: uuid.UUID) -> Path:
    return root / "characters" / str(character_id)


def picture_dir(root: Path, character_id: uuid.UUID, picture_id: uuid.UUID) -> Path:
    return character_dir(root, character_id) / str(picture_id)


def logo_dir(root: Path, image_id: uuid.UUID) -> Path:
    return root / "clan-logos" / str(image_id)


def troupe_dir(root: Path, troupe_id: uuid.UUID) -> Path:
    return root / "troupes" / str(troupe_id)


def troupe_portrait_dir(root: Path, troupe_id: uuid.UUID, portrait_id: uuid.UUID) -> Path:
    return troupe_dir(root, troupe_id) / "portraits" / str(portrait_id)


def banner_dir(root: Path, troupe_id: uuid.UUID, banner_id: uuid.UUID) -> Path:
    return troupe_dir(root, troupe_id) / "banners" / str(banner_id)


def post_picture_dir(root: Path, troupe_id: uuid.UUID, picture_id: uuid.UUID) -> Path:
    return troupe_dir(root, troupe_id) / "posts" / str(picture_id)


def post_picture_file(
    root: Path, troupe_id: uuid.UUID, picture_id: uuid.UUID, name: str
) -> Path | None:
    if name not in POST_FILES:
        return None
    path = post_picture_dir(root, troupe_id, picture_id) / name
    return path if path.is_file() else None


def blog_picture_dir(root: Path, picture_id: uuid.UUID) -> Path:
    return root / "blog" / str(picture_id)


def blog_picture_file(root: Path, picture_id: uuid.UUID, name: str) -> Path | None:
    if name not in POST_FILES:
        return None
    path = blog_picture_dir(root, picture_id) / name
    return path if path.is_file() else None


def body_picture_dir(root: Path, post_id: uuid.UUID, picture_id: uuid.UUID | None = None) -> Path:
    """A blog article's pictures in its words, or one of them."""
    directory = root / "blog-pictures" / str(post_id)
    return directory if picture_id is None else directory / str(picture_id)


def body_picture_file(
    root: Path, post_id: uuid.UUID, picture_id: uuid.UUID, name: str
) -> Path | None:
    if name not in POST_FILES:
        return None
    path = body_picture_dir(root, post_id, picture_id) / name
    return path if path.is_file() else None


def agency_portrait_dir(root: Path, troupe_id: uuid.UUID, portrait_id: uuid.UUID) -> Path:
    return troupe_dir(root, troupe_id) / "agency-portraits" / str(portrait_id)


def agency_portrait_file(
    root: Path, troupe_id: uuid.UUID, portrait_id: uuid.UUID, name: str
) -> Path | None:
    if name not in TROUPE_PORTRAIT_FILES:
        return None
    path = agency_portrait_dir(root, troupe_id, portrait_id) / name
    return path if path.is_file() else None


def author_picture_dir(root: Path, author_id: uuid.UUID, picture_id: uuid.UUID) -> Path:
    return root / "blog-authors" / str(author_id) / str(picture_id)


def author_picture_file(
    root: Path, author_id: uuid.UUID, picture_id: uuid.UUID, name: str
) -> Path | None:
    if name not in AUTHOR_FILES:
        return None
    path = author_picture_dir(root, author_id, picture_id) / name
    return path if path.is_file() else None


def throw_image_dir(root: Path, troupe_id: uuid.UUID, image_id: uuid.UUID) -> Path:
    return troupe_dir(root, troupe_id) / "throws" / str(image_id)


def throw_image_file(
    root: Path, troupe_id: uuid.UUID, image_id: uuid.UUID, name: str
) -> Path | None:
    if name not in THROW_FILES:
        return None
    path = throw_image_dir(root, troupe_id, image_id) / name
    return path if path.is_file() else None


def picture_file(
    root: Path, character_id: uuid.UUID, picture_id: uuid.UUID, name: str
) -> Path | None:
    """One of a picture's files. Only names a picture's file can have are looked
    up, so a name can never reach outside its directory."""
    if name not in PICTURE_FILES:
        return None
    path = picture_dir(root, character_id, picture_id) / name
    return path if path.is_file() else None


def logo_file(root: Path, image_id: uuid.UUID, name: str) -> Path | None:
    if name not in LOGO_FILES:
        return None
    path = logo_dir(root, image_id) / name
    return path if path.is_file() else None


def troupe_portrait_file(
    root: Path, troupe_id: uuid.UUID, portrait_id: uuid.UUID, name: str
) -> Path | None:
    if name not in TROUPE_PORTRAIT_FILES:
        return None
    path = troupe_portrait_dir(root, troupe_id, portrait_id) / name
    return path if path.is_file() else None


def banner_file(root: Path, troupe_id: uuid.UUID, banner_id: uuid.UUID, name: str) -> Path | None:
    if name not in BANNER_FILES:
        return None
    path = banner_dir(root, troupe_id, banner_id) / name
    return path if path.is_file() else None


def remove(directory: Path | None) -> None:
    """Delete a picture's files, if they are there."""
    if directory is not None:
        shutil.rmtree(directory, ignore_errors=True)


@contextmanager
def writing(directory: Path) -> Iterator[Path]:
    """Write new files into `directory`, removing them again if anything fails
    before the change is saved, so a failed upload leaves nothing behind."""
    try:
        yield directory
    except BaseException:
        remove(directory)
        raise


def picture_url(character_id: uuid.UUID, picture_id: uuid.UUID | None) -> str | None:
    """Where the app finds a character's picture: add "/128.webp" and so on."""
    if picture_id is None:
        return None
    return f"/api/characters/{character_id}/pictures/{picture_id}"


def logo_url(image_id: uuid.UUID) -> str:
    return f"/api/clan-logos/{image_id}"


def troupe_portrait_url(troupe_id: uuid.UUID, portrait_id: uuid.UUID | None) -> str | None:
    """Where the app finds a troupe's portrait: add "/128.webp" and so on."""
    if portrait_id is None:
        return None
    return f"/api/troupes/{troupe_id}/portraits/{portrait_id}"


def banner_url(troupe_id: uuid.UUID, banner_id: uuid.UUID | None) -> str | None:
    """Where the app finds a troupe's banner: add "/1500.webp" or "/750.webp"."""
    if banner_id is None:
        return None
    return f"/api/troupes/{troupe_id}/banners/{banner_id}"


def post_picture_url(troupe_id: uuid.UUID, picture_id: uuid.UUID | None) -> str | None:
    """Where the app finds a post's picture or a masthead: add "/1200.webp" or "/600.webp"."""
    if picture_id is None:
        return None
    return f"/api/troupes/{troupe_id}/post-pictures/{picture_id}"


def blog_picture_url(article_id: uuid.UUID, picture_id: uuid.UUID | None) -> str | None:
    """Where the app finds a blog article's hero picture: add "/1200.webp" or "/600.webp"."""
    if picture_id is None:
        return None
    return f"/api/blog/articles/{article_id}/pictures/{picture_id}"


def body_picture_url(picture_id: uuid.UUID) -> str:
    """Where the app finds a picture in a blog article's words, which its Markdown names
    as `blog-picture:<id>`: add "/1200.webp" or "/600.webp"."""
    return f"/api/blog/body-pictures/{picture_id}"


def agency_portrait_url(agency_id: uuid.UUID, portrait_id: uuid.UUID | None) -> str | None:
    """Where the app finds a news agency's portrait: add "/128.webp" and so on."""
    if portrait_id is None:
        return None
    return f"/api/agencies/{agency_id}/portraits/{portrait_id}"


def throw_image_url(troupe_id: uuid.UUID, image_id: uuid.UUID | None) -> str | None:
    """Where the app finds a troupe's rock, paper or scissors: add "/512.webp" or "/128.webp"."""
    if image_id is None:
        return None
    return f"/api/troupes/{troupe_id}/throw-images/{image_id}"


def author_picture_url(author_id: uuid.UUID, picture_id: uuid.UUID | None) -> str | None:
    """Where anyone finds a blog author's picture: add "/96.webp", "/256.webp" and so on."""
    if picture_id is None:
        return None
    return f"/api/blog/author-pictures/{author_id}/{picture_id}"

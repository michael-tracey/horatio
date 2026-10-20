"""Make Horatio's graphics from its logo, a 1024px JPEG on white.

    python3 branding/make_graphics.py path/to/logo.jpeg

Writes branding/logo.png (the logo cut out of its background, full size) and,
in frontend/public, everything the app serves: the logo for the loading screen
and sign-in page, favicons and app icons (the skull, which still reads at 16px),
and the link preview image. Needs Pillow and NumPy.
"""

import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"
NIGHT = (20, 16, 22)  # --color-night

# In the source image: the skull, the "Horatio" lettering and the subtitle. Their
# highlights are near white but must stay; pure white elsewhere is background.
SKULL = (370, 45, 670, 345)
KEEP = [(400, 60, 640, 350), (250, 320, 780, 630), (290, 620, 730, 770)]


def cut_out(source: Path) -> Image.Image:
    """The logo with its white background made transparent, at the source's size."""
    rgb = np.asarray(Image.open(source).convert("RGB")).astype(np.float64)
    h, w, _ = rgb.shape
    lightest = rgb.min(axis=2)

    # Background: near-white pixels connected to the edge.
    candidate = Image.fromarray(np.where(lightest >= 222, 255, 0).astype(np.uint8))
    padded = Image.new("L", (w + 2, h + 2), 255)
    padded.paste(candidate, (1, 1))
    ImageDraw.floodfill(padded, (0, 0), 128)
    bg = np.asarray(padded)[1:-1, 1:-1] == 128

    # Pockets of background the vines and thorns enclose: pure white areas
    # outside the parts to keep.
    spread = rgb.max(axis=2) - lightest
    white = (lightest >= 236) & (spread <= 12) & ~bg
    seen = np.zeros_like(white)
    for y0, x0 in zip(*np.nonzero(white), strict=True):
        if seen[y0, x0]:
            continue
        queue, pts = deque([(y0, x0)]), []
        seen[y0, x0] = True
        while queue:
            y, x = queue.popleft()
            pts.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and white[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        ys, xs = np.array(pts).T
        cx, cy = xs.mean(), ys.mean()
        kept = any(x1 <= cx <= x2 and y1 <= cy <= y2 for x1, y1, x2, y2 in KEEP)
        if not kept and len(pts) >= 6 and lightest[ys, xs].mean() >= 248.5:
            bg[ys, xs] = True

    # Colour to alpha against white, over the background and a few pixels into
    # the art, so edges and blood spatter blend into any colour behind them.
    near = Image.fromarray((bg * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7))
    near = np.asarray(near) > 0
    alpha = np.ones((h, w))
    alpha[near] = ((255 - rgb).max(axis=2) / 255)[near]
    alpha[alpha < 0.05] = 0
    safe = np.where(alpha > 0, alpha, 1)[..., None]
    colour = np.where(near[..., None], (rgb - 255 * (1 - safe)) / safe, rgb)
    rgba = np.dstack([np.clip(colour, 0, 255), alpha * 255]).round().astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def squared(im: Image.Image, margin: float = 0.04) -> Image.Image:
    """Trimmed to what shows, centred on a transparent square."""
    box = im.getchannel("A").point(lambda a: 255 if a > 25 else 0).getbbox()
    im = im.crop(box)
    side = int(max(im.size) * (1 + margin))
    square = Image.new("RGBA", (side, side))
    square.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    return square


def lone_skull(cut: Image.Image) -> Image.Image:
    """The skull alone: the green shield behind it and anything near the corners
    fade out, leaving the skull and its dark outline."""
    art = cut.crop(SKULL)
    rgba = np.asarray(art).astype(np.float64)
    r, g, b = rgba[..., 0], rgba[..., 1], rgba[..., 2]
    # The shield's marble is green; the skull is grey and its outline near black.
    green = np.clip((g - np.maximum(r, b) - 4) / 14, 0, 1)
    h, w = g.shape
    y, x = np.mgrid[0:h, 0:w]
    # An ellipse around the skull, cranium to fangs, fading over its rim.
    d = np.hypot((x - w * 0.5) / (w * 0.355), (y - h * 0.47) / (h * 0.50))
    edge = np.clip((1.08 - d) / 0.12, 0, 1)
    rgba[..., 3] *= (1 - green) * edge
    return Image.fromarray(rgba.round().astype(np.uint8), "RGBA")


def tile(skull: Image.Image, size: int, scale: float, radius: float) -> Image.Image:
    """The skull on a night square: `scale` of the side, corners rounded by
    `radius` of it (0 for a square the platform rounds itself)."""
    out = Image.new("RGBA", (size, size), (*NIGHT, 255))
    inner = int(size * scale)
    art = skull.resize((inner, inner), Image.LANCZOS)
    out.alpha_composite(art, ((size - inner) // 2, (size - inner) // 2))
    if radius:
        mask = Image.new("L", (size * 4, size * 4))
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, size * 4 - 1, size * 4 - 1), radius=int(size * 4 * radius), fill=255
        )
        out.putalpha(mask.resize((size, size), Image.LANCZOS))
    return out


def main(source: Path) -> None:
    PUBLIC.mkdir(exist_ok=True)
    cut = cut_out(source)
    logo = squared(cut)
    logo.save(ROOT / "branding" / "logo.png", optimize=True)

    # The loading screen and sign-in page show it at up to 256px.
    small = logo.resize((512, 512), Image.LANCZOS)
    small.save(PUBLIC / "logo.webp", quality=88, method=6)
    small.save(PUBLIC / "logo.png", optimize=True)

    skull = lone_skull(cut)
    tile(skull, 48, 1.0, 0.2).save(
        PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)]
    )
    tile(skull, 32, 1.0, 0.2).save(PUBLIC / "favicon-32.png", optimize=True)
    tile(skull, 180, 1.0, 0).save(PUBLIC / "apple-touch-icon.png", optimize=True)
    tile(skull, 192, 1.0, 0.2).save(PUBLIC / "icon-192.png", optimize=True)
    tile(skull, 512, 1.0, 0.2).save(PUBLIC / "icon-512.png", optimize=True)
    # Android crops maskable icons to a circle or squircle: keep the skull
    # inside the middle 80%.
    tile(skull, 512, 0.72, 0).save(PUBLIC / "icon-maskable-512.png", optimize=True)
    # The header shows the skull beside the name.
    tile(skull, 64, 1.0, 0.2).save(PUBLIC / "mark-64.png", optimize=True)

    # Link previews (Discord, Slack, iMessage): the logo on night, 1200 x 630.
    preview = Image.new("RGBA", (1200, 630), (*NIGHT, 255))
    shown = logo.resize((600, 600), Image.LANCZOS)
    preview.alpha_composite(shown, (300, 15))
    preview.convert("RGB").save(PUBLIC / "preview.jpg", quality=85, optimize=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))

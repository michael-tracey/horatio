import type { JyhadCardOut } from "./JyhadCard";
import {
  ART,
  CAPACITY_BASELINE,
  CAPACITY_SIZE,
  CARD,
  CLAN,
  COLOURS,
  DISPLAY,
  DROP,
  DROP_PATH,
  DROP_VIEW,
  FOOTER,
  NAME,
  NOTICE,
  SERIF,
  UNOFFICIAL,
  TEXT,
  canvasMeasure,
  canvasNameMeasure,
  clanLetters,
  disciplineBox,
  font,
  layoutText,
  nameSize,
  type Box,
  type TextStyle,
} from "./layout";

/** Pixels to the millimetre in the image: about 300 dpi, 756 × 1056 px. */
export const SCALE = 12;

function loaded(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

/** An SVG symbol, given a size: KRCG's have only a viewBox, and some browsers won't
 * draw an SVG without one on a canvas. */
async function symbol(src: string): Promise<HTMLImageElement | null> {
  try {
    const response = await fetch(src);
    if (!response.ok) return null;
    const svg = await response.text();
    const sized = /<svg\b[^>]*\swidth=/.test(svg) ? svg : svg.replace(/<svg\b/, '<svg width="512" height="512"');
    const url = URL.createObjectURL(new Blob([sized], { type: "image/svg+xml" }));
    const img = await loaded(url);
    URL.revokeObjectURL(url);
    return img;
  } catch {
    return null;
  }
}

function rounded(ctx: CanvasRenderingContext2D, b: Box, r: number) {
  ctx.beginPath();
  ctx.roundRect(b.x, b.y, b.w, b.h, r);
}

/** An image filling a box, cut to it, as CSS's object-fit: cover at `top` down. */
function cover(ctx: CanvasRenderingContext2D, img: HTMLImageElement, b: Box, top = 0.5) {
  const scale = Math.max(b.w / img.naturalWidth, b.h / img.naturalHeight);
  const w = b.w / scale;
  const h = b.h / scale;
  ctx.drawImage(img, (img.naturalWidth - w) / 2, (img.naturalHeight - h) * top, w, h, b.x, b.y, b.w, b.h);
}

/** An image fitted inside a box, its middle at the box's, at `share` of its size. */
function contain(ctx: CanvasRenderingContext2D, img: HTMLImageElement, b: Box, share: number) {
  const w = img.naturalWidth || 1;
  const h = img.naturalHeight || 1;
  const scale = Math.min((b.w * share) / w, (b.h * share) / h);
  ctx.drawImage(img, b.x + (b.w - w * scale) / 2, b.y + (b.h - h * scale) / 2, w * scale, h * scale);
}

function plate(ctx: CanvasRenderingContext2D, b: Box, round: boolean, ring: string) {
  ctx.beginPath();
  if (round) ctx.arc(b.x + b.w / 2, b.y + b.h / 2, b.w / 2, 0, Math.PI * 2);
  else ctx.roundRect(b.x, b.y, b.w, b.h, 1.2);
  ctx.fillStyle = COLOURS.parchment;
  ctx.fill();
  ctx.lineWidth = 0.7;
  ctx.strokeStyle = ring;
  ctx.stroke();
}

/**
 * Text at `x`, `y` in mm, drawn at the image's own pixels rather than a tiny font
 * scaled up, which spaces its letters unevenly.
 */
function write(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, size: number, style: TextStyle, family = SERIF) {
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.font = font(size * SCALE, style, family);
  ctx.fillText(text, x * SCALE, y * SCALE);
  ctx.restore();
}

function letters(ctx: CanvasRenderingContext2D, text: string, b: Box, size: number, family: string) {
  ctx.fillStyle = COLOURS.ink;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  write(ctx, text, b.x + b.w / 2, b.y + b.h / 2, size, "bold", family);
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
}

/**
 * The card as a PNG: the same layout as the card on screen (layout.ts), drawn on a
 * canvas, since an image of the page itself can't be taken in a browser.
 */
export async function drawCard(card: JyhadCardOut, clanName: string | null, text: string, flavour: string): Promise<Blob> {
  await document.fonts?.load(`700 20px ${DISPLAY}`).catch(() => undefined);
  const [art, clan, ...disciplines] = await Promise.all([
    card.picture ? loaded(`${card.picture}/portrait.webp`) : null,
    card.clan_symbol ? symbol(card.clan_symbol) : null,
    ...card.disciplines.map((d) => (d.symbol ? symbol(d.symbol) : null)),
  ]);
  const canvas = document.createElement("canvas");
  canvas.width = CARD.width * SCALE;
  canvas.height = CARD.height * SCALE;
  const ctx = canvas.getContext("2d")!;
  ctx.scale(SCALE, SCALE);

  rounded(ctx, { x: 0, y: 0, w: CARD.width, h: CARD.height }, CARD.radius);
  ctx.fillStyle = COLOURS.frame;
  ctx.fill();
  if (art) {
    ctx.save();
    rounded(ctx, ART, 1.5);
    ctx.clip();
    cover(ctx, art, ART, 0.3);
    ctx.restore();
  }

  plate(ctx, CLAN, true, COLOURS.gold);
  if (clan) contain(ctx, clan, CLAN, 0.72);
  else letters(ctx, clanLetters(clanName), CLAN, 2.6, DISPLAY);

  card.disciplines.forEach((d, i) => {
    const b = disciplineBox(i);
    plate(ctx, b, !d.superior, d.superior ? COLOURS.gold : COLOURS.ink);
    const symbol = disciplines[i];
    if (symbol) contain(ctx, symbol, b, 0.74);
    else letters(ctx, d.superior ? d.abbreviation.toUpperCase() : d.abbreviation, b, d.superior ? 2.3 : 2.1, SERIF);
  });

  // The name on its plate.
  rounded(ctx, NAME, 1);
  ctx.fillStyle = COLOURS.plate;
  ctx.fill();
  ctx.lineWidth = 0.3;
  ctx.strokeStyle = COLOURS.gold;
  ctx.stroke();
  const named = nameSize(card.name, canvasNameMeasure(ctx));
  ctx.fillStyle = COLOURS.ink;
  ctx.textAlign = "center";
  write(ctx, card.name, NAME.x + NAME.w / 2, NAME.y + NAME.h / 2 + named * 0.36, named, "bold", DISPLAY);

  // The text box and its words.
  rounded(ctx, TEXT, 1);
  ctx.fillStyle = COLOURS.parchment;
  ctx.fill();
  const laid = layoutText(card.sect_line, text, flavour, canvasMeasure(ctx));
  ctx.textAlign = "left";
  ctx.fillStyle = COLOURS.ink;
  for (const line of laid.lines) write(ctx, line.text, line.x, line.y, laid.size, line.style);

  if (card.capacity !== null) {
    ctx.save();
    ctx.translate(DROP.x, DROP.y);
    ctx.scale(DROP.w / DROP_VIEW.w, DROP.h / DROP_VIEW.h);
    const drop = new Path2D(DROP_PATH);
    ctx.fillStyle = COLOURS.blood;
    ctx.fill(drop);
    ctx.lineWidth = 0.4;
    ctx.strokeStyle = COLOURS.ink;
    ctx.stroke(drop);
    ctx.restore();
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    write(ctx, String(card.capacity), DROP.x + DROP.w / 2, DROP.y + DROP.h * CAPACITY_BASELINE, CAPACITY_SIZE, "bold", DISPLAY);
  }

  ctx.fillStyle = COLOURS.footer;
  ctx.textAlign = "center";
  write(ctx, UNOFFICIAL, CARD.width / 2, FOOTER.y1, FOOTER.size, "plain");
  write(ctx, NOTICE, CARD.width / 2, FOOTER.y2, FOOTER.size, "plain");

  return new Promise((resolve, reject) => canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("The image couldn't be made."))), "image/png"));
}

/** Save the card as `<name> Jyhad card.png`. */
export async function downloadCard(card: JyhadCardOut, clanName: string | null, text: string, flavour: string) {
  const blob = await drawCard(card, clanName, text, flavour);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${card.name} Jyhad card.png`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

import { frameSvg, svgUrl, symbolTints, tintedSymbol } from "./frame";
import type { JyhadCardOut } from "./JyhadCard";
import {
  ART,
  CAPACITY,
  CAPACITY_BASELINE,
  CAPACITY_SIZE,
  CARD,
  CLAN,
  COLOURS,
  DISPLAY,
  DROP,
  DROP_PATH,
  DROP_VIEW,
  FACES,
  FOOTER,
  LOOKS,
  NAME,
  NAME_TEXT,
  NOTICE,
  SERIF,
  SYMBOL_SHARE,
  TEXT,
  TEXT_PAD,
  UNOFFICIAL,
  canvasMeasure,
  canvasNameMeasure,
  clanLetters,
  disciplineBox,
  font,
  layoutText,
  lookOf,
  nameFit,
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

/**
 * Text at `x`, `y` in mm, drawn at the image's own pixels rather than a tiny font
 * scaled up, which spaces its letters unevenly.
 */
function write(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  size: number,
  style: TextStyle,
  family = SERIF,
  { outline, squeeze }: { outline?: { colour: string; width: number }; squeeze?: number | null } = {},
) {
  const most = squeeze ? squeeze * SCALE : undefined;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.font = font(size * SCALE, style, family);
  if (outline) {
    ctx.strokeStyle = outline.colour;
    ctx.lineWidth = outline.width * SCALE;
    ctx.lineJoin = "round";
    ctx.strokeText(text, x * SCALE, y * SCALE, most);
  }
  ctx.fillText(text, x * SCALE, y * SCALE, most);
  ctx.restore();
}

function letters(ctx: CanvasRenderingContext2D, text: string, b: Box, size: number, family: string, colour: string) {
  ctx.fillStyle = colour;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  write(ctx, text, b.x + b.w / 2, b.y + b.h / 2, size, "bold", family);
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
}

/**
 * The card as a PNG: the same layout as the card on screen (layout.ts) and the same
 * frame (frame.ts), drawn on a canvas, since an image of the page itself can't be
 * taken in a browser.
 */
export async function drawCard(card: JyhadCardOut, clanName: string | null, text: string, flavour: string): Promise<Blob> {
  await Promise.all(FACES.map((f) => document.fonts?.load(f).catch(() => undefined)));
  const look = lookOf(card.sect);
  const palette = LOOKS[look];
  const tints = symbolTints(look);
  const width = CARD.width * SCALE;
  const height = CARD.height * SCALE;
  const frameOf = { look, superior: card.disciplines.map((d) => d.superior), capacity: card.capacity !== null };
  const tinted = (src: string | null, colour: string) => (src ? tintedSymbol(src, colour).then((url) => (url ? loaded(url) : null)) : null);
  const [art, frame, drop, clan, ...disciplines] = await Promise.all([
    card.picture ? loaded(`${card.picture}/portrait.webp`) : null,
    loaded(svgUrl(frameSvg(frameOf, { w: width, h: height }))),
    card.capacity !== null && card.capacity_symbol ? loaded(card.capacity_symbol) : null,
    tinted(card.clan_symbol, tints.clan),
    ...card.disciplines.map((d) => tinted(d.symbol, tints.discipline)),
  ]);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  ctx.scale(SCALE, SCALE);

  // The portrait, then the frame over it, its window showing the portrait.
  ctx.beginPath();
  ctx.roundRect(0, 0, CARD.width, CARD.height, CARD.radius);
  ctx.fillStyle = COLOURS.edge;
  ctx.fill();
  if (art) cover(ctx, art, ART, 0.3);
  if (frame) {
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(frame, 0, 0, width, height);
    ctx.restore();
  }

  if (clan) contain(ctx, clan, CLAN, SYMBOL_SHARE.clan);
  else letters(ctx, clanLetters(clanName), CLAN, 2.6, DISPLAY, palette.name);
  card.disciplines.forEach((d, i) => {
    const b = disciplineBox(i);
    const symbol = disciplines[i];
    if (symbol) contain(ctx, symbol, b, d.superior ? SYMBOL_SHARE.superior : SYMBOL_SHARE.inferior);
    else letters(ctx, d.superior ? d.abbreviation.toUpperCase() : d.abbreviation, b, d.superior ? 2.3 : 2.4, SERIF, COLOURS.ink);
  });

  const named = nameFit(card.name, canvasNameMeasure(ctx));
  ctx.fillStyle = palette.name;
  ctx.textAlign = "center";
  write(ctx, card.name, NAME_TEXT.x + NAME_TEXT.w / 2, NAME.y + NAME.h / 2 + named.size * 0.36, named.size, "bold", DISPLAY, { squeeze: named.squeeze });

  const laid = layoutText(card.sect_line, text, flavour, canvasMeasure(ctx));
  if (laid.rule !== null) {
    ctx.beginPath();
    ctx.moveTo(TEXT.x + TEXT_PAD, laid.rule);
    ctx.lineTo(TEXT.x + TEXT.w - TEXT_PAD, laid.rule);
    ctx.lineWidth = 0.15;
    ctx.strokeStyle = palette.trim;
    ctx.stroke();
  }
  ctx.textAlign = "left";
  ctx.fillStyle = COLOURS.ink;
  for (const line of laid.lines) write(ctx, line.text, line.x, line.y, laid.size, line.style);

  if (card.capacity !== null) {
    if (drop) ctx.drawImage(drop, CAPACITY.x, CAPACITY.y, CAPACITY.w, CAPACITY.h);
    else {
      ctx.save();
      ctx.translate(DROP.x, DROP.y);
      ctx.scale(DROP.w / DROP_VIEW.w, DROP.h / DROP_VIEW.h);
      const path = new Path2D(DROP_PATH);
      ctx.fillStyle = COLOURS.blood;
      ctx.fill(path);
      ctx.lineWidth = 0.4;
      ctx.strokeStyle = palette.trim;
      ctx.stroke(path);
      ctx.restore();
    }
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    write(ctx, String(card.capacity), CAPACITY.x + CAPACITY.w / 2, CAPACITY.y + CAPACITY.h * CAPACITY_BASELINE, CAPACITY_SIZE, "bold", DISPLAY, {
      outline: { colour: "#2a0008", width: 0.35 },
    });
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

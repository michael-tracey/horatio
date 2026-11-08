/**
 * The Jyhad card's frame (#560): Horatio's own drawing, after a VTES crypt card,
 * as one SVG in the card's millimetres. It copies no card scan, layout file or
 * artwork. It has a hole for the portrait, which goes under it; the symbols and
 * words go over it. The card on screen shows it as an image and the downloaded
 * PNG draws the same image on its canvas, so the two match.
 *
 * It holds no words: an SVG shown as an image can't use the page's fonts.
 */

import {
  ART,
  CAPACITY,
  CARD,
  CLAN,
  COLOURS,
  DISCIPLINES,
  FRAME,
  FRAME_RADIUS,
  LOOKS,
  NAME,
  RIBBON,
  TEXT,
  disciplineBox,
  ribbonEnd,
  type Box,
  type Look,
} from "./layout";

export type FrameOf = {
  look: Look;
  /** Each discipline on the card, highest first: superior or not. */
  superior: boolean[];
  /** Whether it has a capacity (only a card with a sheet does). */
  capacity: boolean;
};

const n = (v: number) => +v.toFixed(3);

function roundedRect(b: Box, r: number): string {
  const { x, y, w, h } = b;
  return `M${n(x + r)} ${n(y)}H${n(x + w - r)}A${r} ${r} 0 0 1 ${n(x + w)} ${n(y + r)}V${n(y + h - r)}A${r} ${r} 0 0 1 ${n(x + w - r)} ${n(y + h)}H${n(x + r)}A${r} ${r} 0 0 1 ${n(x)} ${n(y + h - r)}V${n(y + r)}A${r} ${r} 0 0 1 ${n(x + r)} ${n(y)}Z`;
}

function inset(b: Box, by: number): Box {
  return { x: b.x + by, y: b.y + by, w: b.w - 2 * by, h: b.h - 2 * by };
}

/** A plate with its corners cut off, `cut` deep. */
function cutRect(b: Box, cut: number): string {
  const { x, y, w, h } = b;
  return `M${n(x + cut)} ${n(y)}H${n(x + w - cut)}L${n(x + w)} ${n(y + cut)}V${n(y + h - cut)}L${n(x + w - cut)} ${n(y + h)}H${n(x + cut)}L${n(x)} ${n(y + h - cut)}V${n(y + cut)}Z`;
}

function diamond(cx: number, cy: number, r: number): string {
  return `M${n(cx)} ${n(cy - r)}L${n(cx + r)} ${n(cy)}L${n(cx)} ${n(cy + r)}L${n(cx - r)} ${n(cy)}Z`;
}

/**
 * The frame as SVG markup. `px`, if given, is the size to draw it at (for the
 * canvas); else it fills whatever holds it.
 */
export function frameSvg({ look, superior, capacity }: FrameOf, px?: { w: number; h: number }): string {
  const p = LOOKS[look];
  const size = px ? ` width="${px.w}" height="${px.h}"` : ' width="100%" height="100%" preserveAspectRatio="none"';
  const face = `${roundedRect(FRAME, FRAME_RADIUS)}${roundedRect(ART, 0.6)}`;
  const light = look === "bone";
  const parts: string[] = [];

  parts.push(`<defs>
<filter id="mottle" x="0" y="0" width="${CARD.width}" height="${CARD.height}" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
<feTurbulence type="fractalNoise" baseFrequency="0.11 0.07" numOctaves="4" seed="11" result="clouds"/>
<feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="2" seed="3" result="grain"/>
<feColorMatrix in="clouds" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 ${light ? 2.6 : 3.4} -1.3" result="cloudsA"/>
<feColorMatrix in="grain" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.9 -0.32" result="grainA"/>
<feFlood flood-color="${p.mottle}" result="ink"/>
<feComposite in="ink" in2="cloudsA" operator="in" result="veins"/>
<feFlood flood-color="${p.shade}" result="dark"/>
<feComposite in="dark" in2="grainA" operator="in" result="specks"/>
<feMerge><feMergeNode in="veins"/><feMergeNode in="specks"/></feMerge>
<feComposite in2="SourceAlpha" operator="in"/>
</filter>
<filter id="paper" x="0" y="0" width="${CARD.width}" height="${CARD.height}" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
<feTurbulence type="fractalNoise" baseFrequency="0.5 0.35" numOctaves="3" seed="5" result="n"/>
<feColorMatrix in="n" type="matrix" values="0 0 0 0 0.45  0 0 0 0 0.33  0 0 0 0 0.16  0 0 0 0.5 -0.18"/>
<feComposite in2="SourceAlpha" operator="in"/>
</filter>
<radialGradient id="vignette" cx="50%" cy="45%" r="70%">
<stop offset="70%" stop-color="${p.shade}" stop-opacity="0"/>
<stop offset="100%" stop-color="${p.shade}" stop-opacity="${light ? 0.45 : 0.5}"/>
</radialGradient>
<linearGradient id="plate" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="${p.plate[0]}"/><stop offset="1" stop-color="${p.plate[1]}"/>
</linearGradient>
<radialGradient id="medallion" cx="40%" cy="35%" r="70%">
<stop offset="0" stop-color="${p.plate[0]}"/><stop offset="1" stop-color="${p.plate[1]}"/>
</radialGradient>
<linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#ffffff" stop-opacity="0.16"/><stop offset="0.5" stop-color="#ffffff" stop-opacity="0"/>
</linearGradient>
<linearGradient id="shadeDown" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#000" stop-opacity="0.6"/><stop offset="1" stop-color="#000" stop-opacity="0"/>
</linearGradient>
<linearGradient id="shadeUp" x1="0" y1="1" x2="0" y2="0">
<stop offset="0" stop-color="#000" stop-opacity="0.55"/><stop offset="1" stop-color="#000" stop-opacity="0"/>
</linearGradient>
<linearGradient id="shadeRight" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#000" stop-opacity="0.5"/><stop offset="1" stop-color="#000" stop-opacity="0"/>
</linearGradient>
<linearGradient id="shadeLeft" x1="1" y1="0" x2="0" y2="0">
<stop offset="0" stop-color="#000" stop-opacity="0.5"/><stop offset="1" stop-color="#000" stop-opacity="0"/>
</linearGradient>
<linearGradient id="ribbon" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="${p.ribbon}" stop-opacity="0.92"/><stop offset="0.5" stop-color="${p.ribbon}" stop-opacity="0.8"/><stop offset="1" stop-color="${p.ribbon}" stop-opacity="0.92"/>
</linearGradient>
</defs>`);

  // The card's black edge, and the frame's textured face with a hole for the portrait.
  parts.push(`<path d="${roundedRect({ x: 0, y: 0, w: CARD.width, h: CARD.height }, CARD.radius)}${roundedRect(ART, 0.6)}" fill="${COLOURS.edge}" fill-rule="evenodd"/>`);
  parts.push(`<path d="${face}" fill="${p.face}" fill-rule="evenodd"/>`);
  parts.push(`<path d="${face}" fill="#000" fill-rule="evenodd" filter="url(#mottle)"/>`);
  parts.push(`<path d="${face}" fill="url(#vignette)" fill-rule="evenodd"/>`);
  // The inner border: a fine double line inside the frame's edge, with a diamond at each corner.
  const border = inset(FRAME, 0.55);
  parts.push(`<path d="${roundedRect(border, 1.3)}" fill="none" stroke="${p.trim}" stroke-width="0.28"/>`);
  parts.push(`<path d="${roundedRect(inset(border, 0.45), 0.9)}" fill="none" stroke="${p.trim}" stroke-width="0.1" stroke-opacity="0.7"/>`);
  for (const [cx, cy] of [
    [border.x + 0.25, border.y + border.h - 0.25],
    [border.x + border.w - 0.25, border.y + border.h - 0.25],
  ])
    parts.push(`<path d="${diamond(cx!, cy!, 0.7)}" fill="${p.trim}"/>`);

  // The portrait's window: shaded at its edges, as if set into the frame, and trimmed.
  const s = 1.6;
  parts.push(`<rect x="${ART.x}" y="${ART.y}" width="${ART.w}" height="${s}" fill="url(#shadeDown)"/>`);
  parts.push(`<rect x="${ART.x}" y="${n(ART.y + ART.h - s)}" width="${ART.w}" height="${s}" fill="url(#shadeUp)"/>`);
  parts.push(`<rect x="${ART.x}" y="${ART.y}" width="${s}" height="${ART.h}" fill="url(#shadeRight)"/>`);
  parts.push(`<rect x="${n(ART.x + ART.w - s)}" y="${ART.y}" width="${s}" height="${ART.h}" fill="url(#shadeLeft)"/>`);
  parts.push(`<path d="${roundedRect(ART, 0.6)}" fill="none" stroke="#000" stroke-width="0.5" stroke-opacity="0.8"/>`);
  parts.push(`<path d="${roundedRect(inset(ART, -0.35), 0.9)}" fill="none" stroke="${p.trim}" stroke-width="0.25"/>`);

  // The discipline ribbon, hanging from the name plate, its tail cut in a V.
  if (superior.length) {
    const x = RIBBON.x;
    const w = RIBBON.w;
    const end = ribbonEnd(superior.length);
    const ribbon = `M${x} ${RIBBON.top}H${n(x + w)}V${n(end)}L${n(x + w / 2)} ${n(end - RIBBON.tail)}L${x} ${n(end)}Z`;
    parts.push(`<path d="${ribbon}" fill="url(#ribbon)" stroke="${p.trim}" stroke-width="0.22"/>`);
    parts.push(`<path d="M${n(x + 0.5)} ${RIBBON.top}V${n(end - 0.55)}M${n(x + w - 0.5)} ${RIBBON.top}V${n(end - 0.55)}" stroke="${p.trim}" stroke-width="0.08" stroke-opacity="0.6"/>`);
    // Each discipline's plate: a disc, or a diamond for a superior one.
    superior.forEach((sup, i) => {
      const b = disciplineBox(i);
      const cx = b.x + b.w / 2;
      const cy = b.y + b.h / 2;
      const shape = sup ? `<path d="${diamond(cx, cy, DISCIPLINES.size / 2 + 0.45)}"` : `<circle cx="${n(cx)}" cy="${n(cy)}" r="${n(DISCIPLINES.size / 2)}"`;
      parts.push(`${shape} fill="${COLOURS.parchment}" stroke="${p.trim}" stroke-width="0.3"/>`);
    });
  }

  // The text box: parchment, faintly mottled, trimmed.
  parts.push(`<path d="${roundedRect(TEXT, 0.8)}" fill="${COLOURS.parchment}" stroke="#000" stroke-width="0.5" stroke-opacity="0.6"/>`);
  parts.push(`<path d="${roundedRect(TEXT, 0.8)}" fill="#000" filter="url(#paper)"/>`);
  parts.push(`<path d="${roundedRect(inset(TEXT, -0.35), 1.1)}" fill="none" stroke="${p.trim}" stroke-width="0.25"/>`);
  parts.push(`<path d="${roundedRect(inset(TEXT, 0.5), 0.5)}" fill="none" stroke="${p.trim}" stroke-width="0.1" stroke-opacity="0.55"/>`);

  // The name plate, its ends cut, with a sheen along its top and a fine trim.
  const plate = cutRect(NAME, 1.5);
  parts.push(`<path d="${cutRect(inset(NAME, -0.45), 1.8)}" fill="#000" fill-opacity="0.55"/>`);
  parts.push(`<path d="${plate}" fill="url(#plate)" stroke="${p.trim}" stroke-width="0.35"/>`);
  parts.push(`<path d="${plate}" fill="url(#sheen)"/>`);
  parts.push(`<path d="${cutRect(inset(NAME, 0.55), 1.1)}" fill="none" stroke="${p.trim}" stroke-width="0.1" stroke-opacity="0.6"/>`);

  // The clan medallion, over the plate's left end.
  const cx = CLAN.x + CLAN.w / 2;
  const cy = CLAN.y + CLAN.h / 2;
  parts.push(`<circle cx="${n(cx)}" cy="${n(cy)}" r="${n(CLAN.w / 2 + 0.45)}" fill="#000" fill-opacity="0.6"/>`);
  parts.push(`<circle cx="${n(cx)}" cy="${n(cy)}" r="${n(CLAN.w / 2)}" fill="url(#medallion)" stroke="${p.trim}" stroke-width="0.5"/>`);
  parts.push(`<circle cx="${n(cx)}" cy="${n(cy)}" r="${n(CLAN.w / 2 - 0.65)}" fill="none" stroke="${p.trim}" stroke-width="0.1" stroke-opacity="0.7"/>`);

  // The capacity's seat: a dark ring, trimmed, for the drop over the text box's corner.
  if (capacity) {
    const r = CAPACITY.w / 2;
    const ccx = CAPACITY.x + r;
    const ccy = CAPACITY.y + r;
    parts.push(`<circle cx="${n(ccx)}" cy="${n(ccy)}" r="${n(r + 0.55)}" fill="${COLOURS.edge}" stroke="${p.trim}" stroke-width="0.35"/>`);
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${CARD.width} ${CARD.height}"${size}>${parts.join("")}</svg>`;
}

/** An SVG as a data: URL, for an <img> or a canvas. */
export function svgUrl(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/**
 * One of KRCG's symbols in a colour: they're drawn in `currentColor`, which is
 * black in an image. Given a size too, as some browsers won't draw an SVG with only
 * a viewBox on a canvas.
 */
export function tint(svg: string, colour: string): string {
  const open = /<svg\b[^>]*>/.exec(svg)?.[0];
  if (!open) return svg;
  let tag = open;
  if (!/\swidth=/.test(tag)) tag = tag.replace(/<svg\b/, '<svg width="512" height="512"');
  if (!/\scolor=/.test(tag)) tag = tag.replace(/<svg\b/, `<svg color="${colour}"`);
  if (!/\sfill=/.test(tag)) tag = tag.replace(/<svg\b/, `<svg fill="${colour}"`);
  return svg.replace(open, tag).replace(/currentColor/g, colour);
}

/** A symbol fetched and tinted, as a data: URL; null if it can't be had. */
export async function tintedSymbol(src: string, colour: string): Promise<string | null> {
  try {
    const response = await fetch(src);
    if (!response.ok) return null;
    return svgUrl(tint(await response.text(), colour));
  } catch {
    return null;
  }
}

/** The colours KRCG's symbols are drawn in: the clan's light on its dark medallion,
 * the disciplines' dark on their parchment. */
export function symbolTints(look: Look) {
  return { clan: LOOKS[look].name, discipline: COLOURS.ink };
}

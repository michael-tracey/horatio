/**
 * Where everything sits on a Jyhad card (#537), in millimetres on a card of VTES's
 * size, 63 × 88 mm. The card on screen (CSS, scaled by `--mm`) and the image to
 * download (a canvas) both lay it out from here, so they match. Built from boxes
 * and a drawn drop: no frame scan, nothing of a real card's.
 */

export const CARD = { width: 63, height: 88, radius: 3 };

export type Box = { x: number; y: number; w: number; h: number };

/** The portrait, filling the top of the card inside its black frame. */
export const ART: Box = { x: 2.5, y: 2.5, w: 58, h: 56 };
/** The clan symbol, in a round plate at the top left. */
export const CLAN: Box = { x: 3.5, y: 3.5, w: 8.5, h: 8.5 };
/** The name, on a plate beside the clan symbol. */
export const NAME: Box = { x: 13, y: 4.25, w: 46.5, h: 7 };
/** The disciplines, down the left side of the portrait, highest first. */
export const DISCIPLINES = { x: 4.5, y: 14, size: 6.5, step: 7.25 };
/** The text box, under the portrait. */
export const TEXT: Box = { x: 2.5, y: 58.5, w: 58, h: 22.5 };
export const TEXT_PAD = 1.75;
/** The capacity's blood drop, bottom right in the text box; the text keeps clear of it. */
export const DROP: Box = { x: 51.5, y: 67.5, w: 8, h: 11 };
/** The capacity's number in the drop: its size, and its baseline down the drop. */
export const CAPACITY_SIZE = 4.6;
export const CAPACITY_BASELINE = 0.83;
/** The two lines saying it is not a real card, on the frame below the text box. */
export const FOOTER = { y1: 83.1, y2: 85.3, size: 1.35 };

export const COLOURS = {
  frame: "#0d0b0e",
  plate: "rgba(237, 228, 211, 0.92)",
  parchment: "#ede4d3",
  ink: "#141016",
  blood: "#a3253a",
  gold: "#c9a24a",
  footer: "#b9aebf",
};

export const SERIF = 'Georgia, "Times New Roman", serif';
export const DISPLAY = 'Cinzel, Georgia, serif';

export const UNOFFICIAL = "Unofficial · not a real card · made with Horatio";
export const NOTICE = "Portions © Paradox Interactive AB, used with permission · symbols by KRCG";

/** A blood drop filling a 10 × 14 box, point up, as SVG path data: the same shape on
 * screen (an SVG) and in the image (a Path2D). */
export const DROP_PATH = "M5 0 C5 0 0 6.2 0 9.2 A5 5 0 0 0 10 9.2 C10 6.2 5 0 5 0 Z";
export const DROP_VIEW = { w: 10, h: 14.2 };

/** Where the nth discipline sits. */
export function disciplineBox(n: number): Box {
  return { x: DISCIPLINES.x, y: DISCIPLINES.y + n * DISCIPLINES.step, w: DISCIPLINES.size, h: DISCIPLINES.size };
}

/** How wide a piece of text is, in mm, at a size in mm. */
export type Measure = (text: string, size: number, style: TextStyle) => number;
export type TextStyle = "bold" | "plain" | "italic";

/** Words in lines no wider than `width`; a word too long for a line on its own
 * goes on one anyway. */
export function wrap(text: string, width: number, size: number, style: TextStyle, measure: Measure): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const tried = line ? `${line} ${word}` : word;
    if (line && measure(tried, size, style) > width) {
      lines.push(line);
      line = word;
    } else line = tried;
  }
  if (line) lines.push(line);
  return lines;
}

export type TextLine = { text: string; style: TextStyle; x: number; y: number };
export type TextLayout = { size: number; lineHeight: number; lines: TextLine[] };

/** The text box's sizes, largest first, in mm: about 7pt down to 4.5pt. */
export const TEXT_SIZES = [2.45, 2.3, 2.15, 2.0, 1.9, 1.8, 1.7, 1.6];
const LEADING = 1.2;
// A little space between the title line, the text and the flavour line.
const GAP = 0.6;

/**
 * The text box's lines at the largest size they all fit: the sect and title line
 * in bold across the box, then the text and the italic flavour line, which keep
 * clear of the blood drop on the right. `y` is each line's baseline. At the
 * smallest size, lines that still don't fit are left off.
 */
export function layoutText(sectLine: string | null, text: string, flavour: string, measure: Measure): TextLayout {
  const left = TEXT.x + TEXT_PAD;
  const full = TEXT.w - 2 * TEXT_PAD;
  const beside = DROP.x - left - 0.75;
  const bottom = TEXT.y + TEXT.h - TEXT_PAD;
  let laid: TextLayout | null = null;
  for (const size of TEXT_SIZES) {
    const lineHeight = size * LEADING;
    const lines: TextLine[] = [];
    let y = TEXT.y + TEXT_PAD + size;
    const add = (block: string, style: TextStyle, width: number) => {
      if (!block.trim()) return;
      if (lines.length) y += GAP;
      for (const t of wrap(block, width, size, style, measure)) {
        lines.push({ text: t, style, x: left, y });
        y += lineHeight;
      }
    };
    add(sectLine ?? "", "bold", full);
    add(text, "plain", beside);
    add(flavour, "italic", beside);
    const last = lines.at(-1);
    laid = { size, lineHeight, lines };
    if (!last || last.y + size * 0.25 <= bottom) return laid;
  }
  // Still too much at the smallest: what fits.
  return { ...laid!, lines: laid!.lines.filter((l) => l.y + laid!.size * 0.25 <= bottom) };
}

/** The name's size in mm: as large as fits its plate, from about 10pt down. */
export function nameSize(name: string, measure: Measure): number {
  for (let size = 3.6; size > 1.8; size -= 0.1) if (measure(name, size, "bold") <= NAME.w - 2) return +size.toFixed(2);
  return 1.8;
}

/** A canvas's measure, for the fonts above. */
export function canvasMeasure(ctx: CanvasRenderingContext2D): Measure {
  return (text, size, style) => {
    ctx.font = font(size * 100, style);
    return ctx.measureText(text).width / 100;
  };
}

/** A CSS/canvas font for text at `px` pixels: the name's in Cinzel, the rest serif. */
export function font(px: number, style: TextStyle, family = SERIF): string {
  return `${style === "italic" ? "italic " : ""}${style === "bold" ? "700 " : "400 "}${px}px ${family}`;
}

/** The name's measure, in Cinzel. */
export function canvasNameMeasure(ctx: CanvasRenderingContext2D): Measure {
  return (text, size) => {
    ctx.font = font(size * 100, "bold", DISPLAY);
    return ctx.measureText(text).width / 100;
  };
}

/** Three letters for a clan with no symbol here: "Tre", "Ven". */
export function clanLetters(clan: string | null): string {
  return (clan ?? "?").replace(/^.*: /, "").slice(0, 3);
}

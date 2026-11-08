/**
 * Where everything sits on a Jyhad card (#537), in millimetres on a card of VTES's
 * size, 63 × 88 mm. The card on screen (CSS and SVG, scaled by `--mm`) and the image
 * to download (a canvas) both lay it out from here, so they match. The frame is
 * Horatio's own drawing (frame.ts, #560), after a VTES crypt card: no frame scan,
 * nothing of a real card's.
 */

export const CARD = { width: 63, height: 88, radius: 3 };

export type Box = { x: number; y: number; w: number; h: number };

/** The textured frame, inside the card's black edge; the edge is wider at the
 * bottom, for the lines saying it isn't a real card. */
export const FRAME: Box = { x: 2.2, y: 2.2, w: 58.6, h: 80.2 };
export const FRAME_RADIUS = 1.8;
/** The name plate across the top. */
export const NAME: Box = { x: 3.6, y: 3.5, w: 55.8, h: 7 };
/** Where the name sits on its plate, right of the clan symbol. */
export const NAME_TEXT = { x: 13.2, w: 45.2 };
/** The clan symbol, in a round medallion at the plate's left. */
export const CLAN: Box = { x: 3.4, y: 2.6, w: 8.8, h: 8.8 };
/** The portrait's window, under the plate. */
export const ART: Box = { x: 3.6, y: 11.4, w: 55.8, h: 47.6 };
/** The disciplines, highest first, on a ribbon down the left of the portrait. */
export const DISCIPLINES = { x: 4.8, y: 12.6, size: 6, step: 6.9 };
export const RIBBON = { x: 4.3, w: 7, top: 10, tail: 2.2 };
/** The text box, under the portrait. */
export const TEXT: Box = { x: 3.6, y: 60, w: 55.8, h: 21.2 };
export const TEXT_PAD = 1.6;
/** The capacity, bottom right, over the text box's corner; the text keeps clear of it. */
export const CAPACITY: Box = { x: 50.6, y: 72.2, w: 9.6, h: 9.6 };
/** The capacity's number: its size, and its baseline down the drop. */
export const CAPACITY_SIZE = 4.8;
export const CAPACITY_BASELINE = 0.67;
/** The two lines saying it is not a real card, on the black edge below the frame. */
export const FOOTER = { y1: 84.6, y2: 86.5, size: 1.3 };

/** The frame's two looks: dark for the Camarilla (and a card with no sect), the
 * colour of old bone for the rest. */
export type Look = "night" | "bone";

export function lookOf(sect: string | null | undefined): Look {
  return !sect || sect === "Camarilla" ? "night" : "bone";
}

export type Palette = {
  /** The frame's face, its mottling and its edges' shade. */
  face: string;
  mottle: string;
  shade: string;
  /** The trim: the lines round the frame, the plate, the window and the text box. */
  trim: string;
  /** The name plate and the clan medallion, top to bottom. */
  plate: [string, string];
  ribbon: string;
  /** The name and the clan symbol, on the plate. */
  name: string;
};

export const LOOKS: Record<Look, Palette> = {
  night: {
    face: "#32121a",
    mottle: "#8e3240",
    shade: "#07020a",
    trim: "#c9a24a",
    plate: ["#3d141c", "#120609"],
    ribbon: "#140709",
    name: "#f1e4c4",
  },
  bone: {
    face: "#b9a782",
    mottle: "#5e4b2f",
    shade: "#2c2214",
    trim: "#7a5a24",
    plate: ["#3a3027", "#110d0a"],
    ribbon: "#1c1612",
    name: "#ecdcb6",
  },
};

export const COLOURS = {
  edge: "#0b0a0c",
  parchment: "#ece2c9",
  ink: "#1a1214",
  blood: "#a3253a",
  footer: "#a99fae",
};

/** The card's text: Crimson Pro (index.html loads it with Cinzel), else a serif. */
export const SERIF = '"Crimson Pro", Georgia, "Times New Roman", serif';
export const DISPLAY = 'Cinzel, Georgia, serif';
/** Every face the card uses, to load before measuring or drawing. */
export const FACES = [`700 20px ${DISPLAY}`, `400 20px ${SERIF}`, `700 20px ${SERIF}`, `italic 400 20px ${SERIF}`];

export const UNOFFICIAL = "Unofficial · not a real card · made with Horatio";
export const NOTICE = "Portions © Paradox Interactive AB, used with permission · symbols by KRCG";

/** A blood drop filling a 10 × 14.2 box, point up, as SVG path data: the capacity's
 * without KRCG's symbols, the same on screen (an SVG) and in the image (a Path2D). */
export const DROP_PATH = "M5 0 C5 0 0 6.2 0 9.2 A5 5 0 0 0 10 9.2 C10 6.2 5 0 5 0 Z";
export const DROP_VIEW = { w: 10, h: 14.2 };
/** The drawn drop, in the capacity's circle. */
export const DROP: Box = { x: CAPACITY.x + 1.65, y: CAPACITY.y + 0.3, w: 6.3, h: 8.95 };

/** Where the nth discipline sits. */
export function disciplineBox(n: number): Box {
  return { x: DISCIPLINES.x, y: DISCIPLINES.y + n * DISCIPLINES.step, w: DISCIPLINES.size, h: DISCIPLINES.size };
}

/** How much of its box a symbol fills: KRCG's superior diamond sits inside a parchment one. */
export const SYMBOL_SHARE = { clan: 0.66, inferior: 0.74, superior: 0.8 };

/** Where the ribbon ends, below the last of `n` disciplines, at its tail's tips. */
export function ribbonEnd(n: number): number {
  return DISCIPLINES.y + (n - 1) * DISCIPLINES.step + DISCIPLINES.size + 1.2 + RIBBON.tail;
}

/** How wide a piece of text is, in mm, at a size in mm. */
export type Measure = (text: string, size: number, style: TextStyle) => number;
export type TextStyle = "bold" | "plain" | "italic";

/** Words in lines no wider than `width` (or the nth line no wider than `width(n)`);
 * a word too long for a line on its own goes on one anyway. */
export function wrap(text: string, width: number | ((line: number) => number), size: number, style: TextStyle, measure: Measure): string[] {
  const widthOf = typeof width === "number" ? () => width : width;
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const tried = line ? `${line} ${word}` : word;
    if (line && measure(tried, size, style) > widthOf(lines.length)) {
      lines.push(line);
      line = word;
    } else line = tried;
  }
  if (line) lines.push(line);
  return lines;
}

export type TextLine = { text: string; style: TextStyle; x: number; y: number };
/** `rule` is the y of the hairline under the title line, if there's text below it. */
export type TextLayout = { size: number; lineHeight: number; lines: TextLine[]; rule: number | null };

/** The text box's sizes, largest first, in mm: about 7.5pt down to 4.5pt. Crimson
 * Pro is small on its body, so a little larger than a book face. */
export const TEXT_SIZES = [2.65, 2.5, 2.35, 2.2, 2.1, 2.0, 1.9, 1.8, 1.7, 1.6];
const LEADING = 1.15;
// A little space between the title line, the text and the flavour line.
const GAP = 0.7;

/**
 * The text box's lines at the largest size they all fit: the sect and title line
 * in bold across the box, a hairline, then the text and the italic flavour line,
 * whose lines beside the capacity keep clear of it. `y` is each line's baseline.
 * At the smallest size, lines that still don't fit are left off.
 */
export function layoutText(sectLine: string | null, text: string, flavour: string, measure: Measure): TextLayout {
  const left = TEXT.x + TEXT_PAD;
  const full = TEXT.w - 2 * TEXT_PAD;
  const beside = CAPACITY.x - left - 0.75;
  const bottom = TEXT.y + TEXT.h - TEXT_PAD;
  let laid: TextLayout | null = null;
  for (const size of TEXT_SIZES) {
    const lineHeight = size * LEADING;
    const lines: TextLine[] = [];
    let y = TEXT.y + TEXT_PAD + size * 0.8;
    let rule: number | null = null;
    const add = (block: string, style: TextStyle, width: number) => {
      if (!block.trim()) return;
      if (lines.length) {
        // Under the title line, a hairline across the box.
        if (rule === null && lines.every((l) => l.style === "bold")) {
          rule = y - lineHeight + size * 0.3 + GAP;
          y += GAP * 2;
        } else y += GAP;
      }
      const start = y;
      const widthOf = (n: number) => (start + n * lineHeight + size * 0.3 < CAPACITY.y - 0.6 ? full : width);
      for (const t of wrap(block, widthOf, size, style, measure)) {
        lines.push({ text: t, style, x: left, y });
        y += lineHeight;
      }
    };
    add(sectLine ?? "", "bold", full);
    add(text, "plain", beside);
    add(flavour, "italic", beside);
    const last = lines.at(-1);
    laid = { size, lineHeight, lines, rule };
    if (!last || last.y + size * 0.25 <= bottom) return laid;
  }
  // Still too much at the smallest: what fits.
  const fits = laid!.lines.filter((l) => l.y + laid!.size * 0.25 <= bottom);
  return { ...laid!, lines: fits, rule: fits.some((l) => l.style !== "bold") ? laid!.rule : null };
}

/** How wide the name may be on its plate. */
export const NAME_WIDTH = NAME_TEXT.w - 1.5;

/** The name's size in mm, as large as fits its plate from about 10pt down to 7pt;
 * and its width if even that is too wide, to squeeze it to (else null). */
export function nameFit(name: string, measure: Measure): { size: number; squeeze: number | null } {
  let size = 3.6;
  for (; size > 2.45; size -= 0.1) if (measure(name, size, "bold") <= NAME_WIDTH) return { size: +size.toFixed(2), squeeze: null };
  size = 2.4;
  return { size, squeeze: measure(name, size, "bold") > NAME_WIDTH ? NAME_WIDTH : null };
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

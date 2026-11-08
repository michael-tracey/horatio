import { describe, expect, it } from "vitest";
import { ART, CAPACITY, CARD, FOOTER, FRAME, NAME, TEXT, TEXT_SIZES, clanLetters, disciplineBox, layoutText, lookOf, nameFit, NAME_WIDTH, ribbonEnd, wrap, type Measure } from "./layout";

/** Every letter half its size wide: near enough a serif's average. */
const measure: Measure = (text, size) => text.length * size * 0.5;

describe("the Jyhad card's text box", () => {
  it("wraps words to the width", () => {
    expect(wrap("one two three four", 4.5 * 0.5 * 2, 2, "plain", measure)).toEqual(["one", "two", "three", "four"]);
    expect(wrap("one two three four", 100, 2, "plain", measure)).toEqual(["one two three four"]);
    expect(wrap("", 10, 2, "plain", measure)).toEqual([]);
    // Each line its own width: the first wide, the rest narrow.
    expect(wrap("one two three four", (n) => (n === 0 ? 100 : 6), 2, "plain", measure)).toEqual(["one two three four"]);
    expect(wrap("one two three four five", (n) => (n === 0 ? 8 : 6), 2, "plain", measure)).toEqual(["one two", "three", "four", "five"]);
  });

  it("keeps the text clear of the capacity, and the title line across the box over a hairline", () => {
    const laid = layoutText("Camarilla Prince of Asheville: 2 votes", "Once each turn, Varga may burn a blood to untap. ".repeat(3), "", measure);
    expect(layoutText("Camarilla", "Once each turn, Varga may burn a blood to untap.", "", measure).size).toBe(TEXT_SIZES[0]);
    expect(laid.lines[0]).toMatchObject({ text: "Camarilla Prince of Asheville: 2 votes", style: "bold" });
    for (const line of laid.lines) {
      const right = line.x + measure(line.text, laid.size, line.style);
      expect(right).toBeLessThanOrEqual(TEXT.x + TEXT.w);
      // Beside the capacity, clear of it.
      if (line.y + laid.size * 0.3 >= CAPACITY.y - 0.6) expect(right).toBeLessThanOrEqual(CAPACITY.x);
    }
    expect(laid.lines.some((l) => l.y >= CAPACITY.y)).toBe(true);
    // The hairline is between the title line and the text.
    expect(laid.rule).toBeGreaterThan(laid.lines[0]!.y);
    expect(laid.rule).toBeLessThan(laid.lines[1]!.y - laid.size * 0.7);
  });

  it("draws no hairline under a title line with nothing below it", () => {
    expect(layoutText("Camarilla", "", "", measure).rule).toBeNull();
    expect(layoutText(null, "Some text.", "", measure).rule).toBeNull();
  });

  it("shrinks the text until three hundred letters and a flavour line fit", () => {
    const laid = layoutText("Sabbat Priscus: 3 votes", "word ".repeat(60).trim(), "The night has teeth, and so do I, said the Priscus.", measure);
    expect(laid.size).toBeLessThan(TEXT_SIZES[0]!);
    expect(laid.lines.at(-1)!.style).toBe("italic");
    expect(laid.lines.at(-1)!.y).toBeLessThanOrEqual(TEXT.y + TEXT.h);
  });

  it("is empty with nothing written", () => {
    expect(layoutText(null, "", "", measure).rule).toBeNull();
    expect(layoutText(null, "", "", measure).lines).toEqual([]);
  });

  it("fits a long name on its plate", () => {
    expect(nameFit("Varga", measure)).toEqual({ size: 3.6, squeeze: null });
    expect(nameFit("Celestine du Lac de la Nuit", measure).size).toBeLessThan(3.6);
    expect(nameFit("Celestine du Lac de la Nuit", measure).squeeze).toBeNull();
    // Too long even at the smallest: squeezed to the plate.
    expect(nameFit("Lady Constance Wilhelmina Ravenscroft-Hargreaves", measure)).toEqual({ size: 2.4, squeeze: NAME_WIDTH });
  });

  it("names a clan with no symbol in three letters", () => {
    expect(clanLetters("Tremere")).toBe("Tre");
    expect(clanLetters("Brujah: True Brujah")).toBe("Tru");
    expect(clanLetters(null)).toBe("?");
  });
});

describe("the Jyhad card's frame", () => {
  const inside = (inner: { x: number; y: number; w: number; h: number }, outer: { x: number; y: number; w: number; h: number }) =>
    inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.w <= outer.x + outer.w && inner.y + inner.h <= outer.y + outer.h;

  it("keeps the plate, the portrait and the text box inside the frame, and the frame inside the card", () => {
    expect(inside(FRAME, { x: 0, y: 0, w: CARD.width, h: CARD.height })).toBe(true);
    for (const box of [NAME, ART, TEXT]) expect(inside(box, FRAME)).toBe(true);
    expect(ART.y).toBeGreaterThanOrEqual(NAME.y + NAME.h);
    expect(TEXT.y).toBeGreaterThanOrEqual(ART.y + ART.h);
    // The lines saying it isn't a real card are on the black edge below the frame.
    expect(FOOTER.y1 - 1.3).toBeGreaterThan(FRAME.y + FRAME.h);
    expect(FOOTER.y2).toBeLessThan(CARD.height);
  });

  it("fits six disciplines and the ribbon's tail over the portrait", () => {
    expect(disciplineBox(5).y + disciplineBox(5).h).toBeLessThan(ribbonEnd(6));
    expect(ribbonEnd(6)).toBeLessThanOrEqual(ART.y + ART.h);
  });

  it("is dark for the Camarilla and a card with no sect, bone for the rest", () => {
    expect(lookOf("Camarilla")).toBe("night");
    expect(lookOf(null)).toBe("night");
    expect(lookOf("Sabbat")).toBe("bone");
    expect(lookOf("Anarch")).toBe("bone");
  });
});

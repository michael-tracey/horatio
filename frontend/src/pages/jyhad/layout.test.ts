import { describe, expect, it } from "vitest";
import { ART, CAPACITY, CARD, FOOTER, FRAME, NAME, TEMPLATE_IMAGE, TEMPLATE_PX, TEXT, TEXT_SIZES, T_DROP, T_NAME, T_OVAL, T_SIDEBAR, T_TEXT, clanLetters, disciplineBox, layoutTemplateText, layoutText, lookOf, nameFit, NAME_WIDTH, RIBBON, RIBBON_END, BORDERED, isBordered, stackBox, templateDisciplineBox, templateNameFit, wrap, type Measure } from "./layout";

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

  it("stacks six disciplines up the ribbon from its foot, over the portrait (#869)", () => {
    const six = [false, false, false, false, true, true];
    for (const bordered of [false, true]) {
      const boxes = six.map((_, i) => disciplineBox(i, six, bordered));
      // The lowest ends above the ribbon's tail, the highest below its top.
      expect(boxes.at(-1)!.y + boxes.at(-1)!.h).toBeLessThan(RIBBON_END - RIBBON.tail);
      expect(boxes[0]!.y).toBeGreaterThan(RIBBON.top);
      // Top to bottom, without overlapping.
      for (let i = 1; i < 6; i++) expect(boxes[i]!.y).toBeGreaterThanOrEqual(boxes[i - 1]!.y + boxes[i - 1]!.h - 0.01);
    }
    expect(RIBBON_END).toBeLessThanOrEqual(ART.y + ART.h);
    // The foot stays put: one discipline sits where six's lowest does.
    expect(disciplineBox(0, [true], true).y).toBeCloseTo(disciplineBox(5, six, true).y);
  });

  it("sizes white-bordered symbols as a printed card does: a diamond a little larger than a square", () => {
    const stack = { centre: 10, bottom: 50, size: 6, step: 6.9 };
    const square = stackBox(0, [false, true], true, stack);
    const diamond = stackBox(1, [false, true], true, stack);
    expect([square.w, diamond.w]).toEqual([BORDERED.inferior, BORDERED.superior]);
    // Both centred across the sidebar, the diamond's foot at the stack's.
    expect(square.x + square.w / 2).toBeCloseTo(10);
    expect(diamond.x + diamond.w / 2).toBeCloseTo(10);
    expect(diamond.y + diamond.h).toBeCloseTo(50);
    expect(diamond.y + diamond.h / 2 - (square.y + square.h / 2)).toBeCloseTo(BORDERED.step);
    // Plain symbols are all one size, on their plates.
    expect(stackBox(1, [false, true], false, stack).w).toBe(6);
  });

  it("calls a card white-bordered only when every discipline is", () => {
    expect(isBordered({ disciplines: [{ bordered: true }, { bordered: true }] })).toBe(true);
    expect(isBordered({ disciplines: [{ bordered: true }, { bordered: false }] })).toBe(false);
    expect(isBordered({ disciplines: [] })).toBe(false);
  });

  it("is dark for the Camarilla and a card with no sect, bone for the rest", () => {
    expect(lookOf("Camarilla")).toBe("night");
    expect(lookOf(null)).toBe("night");
    expect(lookOf("Sabbat")).toBe("bone");
    expect(lookOf("Anarch")).toBe("bone");
  });
});

describe("the Jyhad card on a clan's crypt card template (#850)", () => {
  it("keeps where things are as the backend's detect found them on the 2020 templates", () => {
    // horatio.crypt_templates.LAYOUT, in the template's pixels.
    expect(TEMPLATE_PX).toMatchObject({
      width: 819,
      height: 1114,
      oval: { x: 194, y: 153, w: 531, h: 689 },
      text: { x: 188, y: 858, w: 546, h: 146 },
      drop: { x: 675, y: 956, w: 66, h: 66 },
      sidebar: { x: 67, y: 300, w: 99, h: 744 },
      name: { x: 78, y: 76, w: 640, h: 64 },
    });
    // The same in millimetres as `python -m horatio.crypt_templates` prints.
    const round = (b: { x: number; y: number; w: number; h: number }) => [b.x, b.y, b.w, b.h].map((n) => +n.toFixed(2));
    expect(round(T_OVAL)).toEqual([13.26, 9.78, 44.97, 58.35]);
    expect(round(T_TEXT)).toEqual([12.75, 69.49, 46.24, 12.37]);
    expect(round(T_DROP)).toEqual([53.99, 77.79, 5.59, 5.59]);
    // The template's bleed goes past the card's edges, as much on each side.
    expect(round(TEMPLATE_IMAGE)).toEqual([-3.17, -3.17, 69.37, 94.35]);
  });

  it("stacks six disciplines up the sidebar from beside the text box, under the clan symbol (#869)", () => {
    const six = [false, false, false, true, true, true];
    for (const bordered of [false, true]) {
      for (let n = 0; n < 6; n++) {
        const b = templateDisciplineBox(n, six, bordered);
        expect(b.x).toBeGreaterThanOrEqual(T_SIDEBAR.x);
        expect(b.x + b.w).toBeLessThanOrEqual(T_SIDEBAR.x + T_SIDEBAR.w + 0.01);
        expect(b.y).toBeGreaterThanOrEqual(T_SIDEBAR.y);
        expect(b.y + b.h).toBeLessThanOrEqual(T_TEXT.y + T_TEXT.h);
      }
      // The lowest sits beside the text box, as on KRCG's sample card.
      const last = templateDisciplineBox(5, six, bordered);
      expect(last.y + last.h).toBeGreaterThan(T_TEXT.y);
    }
    // The name's band is above the oval.
    expect(T_NAME.y + T_NAME.h).toBeLessThan(T_OVAL.y);
  });

  it("fits the text in the template's box, clear of the drop", () => {
    const laid = layoutTemplateText("Camarilla Prince of Asheville: 2 votes", "Once each turn, Varga may burn a blood to untap. ".repeat(2), "A lie well told.", measure);
    expect(laid.lines[0]).toMatchObject({ style: "bold" });
    for (const line of laid.lines) {
      expect(line.x).toBeGreaterThanOrEqual(T_TEXT.x);
      expect(line.y).toBeLessThanOrEqual(T_TEXT.y + T_TEXT.h);
      // A line level with the drop ends before it.
      if (line.y > T_DROP.y) expect(line.x + measure(line.text, laid.size, line.style)).toBeLessThanOrEqual(T_DROP.x);
    }
    expect(templateNameFit("Varga", measure).size).toBeLessThanOrEqual(3.9);
  });
});

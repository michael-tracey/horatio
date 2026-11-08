import { describe, expect, it } from "vitest";
import { DROP, TEXT, TEXT_SIZES, clanLetters, layoutText, nameSize, wrap, type Measure } from "./layout";

/** Every letter half its size wide: near enough a serif's average. */
const measure: Measure = (text, size) => text.length * size * 0.5;

describe("the Jyhad card's text box", () => {
  it("wraps words to the width", () => {
    expect(wrap("one two three four", 4.5 * 0.5 * 2, 2, "plain", measure)).toEqual(["one", "two", "three", "four"]);
    expect(wrap("one two three four", 100, 2, "plain", measure)).toEqual(["one two three four"]);
    expect(wrap("", 10, 2, "plain", measure)).toEqual([]);
  });

  it("keeps the text clear of the blood drop, and the title line across the box", () => {
    const laid = layoutText("Camarilla Prince of Asheville: 2 votes", "Once each turn, Varga may burn a blood to untap. ".repeat(3), "", measure);
    expect(laid.size).toBe(TEXT_SIZES[0]);
    expect(laid.lines[0]).toMatchObject({ text: "Camarilla Prince of Asheville: 2 votes", style: "bold" });
    for (const line of laid.lines.slice(1)) expect(line.x + measure(line.text, laid.size, line.style)).toBeLessThanOrEqual(DROP.x);
  });

  it("shrinks the text until three hundred letters and a flavour line fit", () => {
    const laid = layoutText("Sabbat Priscus: 3 votes", "word ".repeat(60).trim(), "The night has teeth, and so do I, said the Priscus.", measure);
    expect(laid.size).toBeLessThan(TEXT_SIZES[0]!);
    expect(laid.lines.at(-1)!.style).toBe("italic");
    expect(laid.lines.at(-1)!.y).toBeLessThanOrEqual(TEXT.y + TEXT.h);
  });

  it("is empty with nothing written", () => {
    expect(layoutText(null, "", "", measure).lines).toEqual([]);
  });

  it("fits a long name on its plate", () => {
    expect(nameSize("Varga", measure)).toBe(3.6);
    expect(nameSize("Lady Constance Wilhelmina Ravenscroft-Hargreaves", measure)).toBeLessThan(2);
  });

  it("names a clan with no symbol in three letters", () => {
    expect(clanLetters("Tremere")).toBe("Tre");
    expect(clanLetters("Brujah: True Brujah")).toBe("Tru");
    expect(clanLetters(null)).toBe("?");
  });
});

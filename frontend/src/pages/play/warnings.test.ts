import { describe, expect, it } from "vitest";
import { beastWarning, derangementWarning, triggersAt } from "./warnings";

describe("derangementWarning", () => {
  it("says nothing until one trait short of the edge", () => {
    expect(derangementWarning(0, 3, 0)).toBeNull();
    expect(derangementWarning(1, 3, 1)).toBeNull();
  });

  it("warns at 2 what a third brings", () => {
    const warning = derangementWarning(2, 3, 0)!;
    expect(warning.level).toBe("near");
    expect(warning.title).toBe("One trait from the edge");
    expect(warning.source).toBe("MET: VtM core, p. 267");
  });

  it("at 3, says how a psychotic break plays out and what it clears, 1 for a Malkavian", () => {
    const warning = derangementWarning(3, 3, 0)!;
    expect(warning.level).toBe("at");
    expect(warning.title).toBe("On the edge of a psychotic break");
    expect(warning.lines.join(" ")).toContain("five minutes");
    expect(warning.lines.join(" ")).toContain("cleared, to 0");
    expect(derangementWarning(3, 3, 1)!.lines.join(" ")).toContain("to 1, as a Malkavian always keeps 1");
  });
});

describe("beastWarning", () => {
  const humanity = { name: "Humanity", value: 5 };

  it("says nothing with no Beast traits: no frenzy at all", () => {
    expect(beastWarning(0, 5, humanity)).toBeNull();
  });

  it("names each count's frenzy triggers, its difficulty, and how to play it", () => {
    const titles = [1, 2, 3, 4, 5].map((n) => beastWarning(n, 5, humanity)!.title);
    expect(titles).toEqual(["The Beast has a foothold", "The Beast is awake", "The Beast speaks", "One trait from losing Humanity", "A dot of Humanity is lost"]);

    const one = beastWarning(1, 5, humanity)!;
    expect(one.level).toBe("near");
    expect(one.lines.join(" ")).toContain("You can frenzy now. Test to resist it on a single blow of 4 or more damage (rage); your Blood reaching 0 (hunger)");
    expect(one.lines.join(" ")).toContain("against 11");
    expect(one.lines.join(" ")).toContain("Play it:");

    expect(beastWarning(3, 5, humanity)!.lines.join(" ")).toContain("a single blow of 2 or more damage (rage)");
    expect(beastWarning(3, 5, humanity)!.lines.join(" ")).toContain("against 13");
  });

  it("is at the edge at 4, a dot short of losing Morality, and at 5 says it's lost", () => {
    const four = beastWarning(4, 5, humanity)!;
    expect(four.level).toBe("at");
    expect(four.lines[0]).toBe("One more Beast trait costs a dot of permanent Humanity.");
    expect(four.lines.join(" ")).toContain("any damage at all (rage)");

    const five = beastWarning(5, 5, { name: "Path of Caine", value: 4 })!;
    expect(five.level).toBe("at");
    expect(five.title).toBe("A dot of Path of Caine is lost");
    expect(five.lines.join(" ")).toContain("against 15");
    expect(five.source).toBe("MET: VtM core, pp. 301–303");
  });

  it("adds 5 to resist at Humanity 2 or less", () => {
    expect(beastWarning(2, 5, { name: "Humanity", value: 2 })!.lines.join(" ")).toContain("against 17 (+5 at Humanity 2 or less)");
    expect(beastWarning(2, 5, { name: "Path of Caine", value: 2 })!.lines.join(" ")).toContain("against 12,");
    // The character's own number, counting a merit like Calm Heart, once the sheet is read.
    expect(beastWarning(2, 5, { name: "Humanity", value: 5 }, 10)!.lines.join(" ")).toContain("against 10,");
  });

  it("lists the triggers of the highest count past 4", () => {
    expect(triggersAt(9)).toBe(triggersAt(4));
  });
});

import { describe, expect, it } from "vitest";
import { excerpt, firstShown, monthOrder, nextShown, publishedWhat, rotates } from "./nominations";

const entry = (id: string, order: number) => ({ id, order, text: `Kind word ${id}` });

describe("a month's order", () => {
  const published = [entry("a", 0.71), entry("b", 0.12), entry("c", 0.45), entry("d", 0.93)];

  it("is the order fixed as it was published, however the list arrives", () => {
    const once = monthOrder(published).map((e) => e.id);
    expect(once).toEqual(["b", "c", "a", "d"]);
    expect(monthOrder([...published].reverse()).map((e) => e.id)).toEqual(once);
    expect(monthOrder([published[2]!, published[0]!, published[3]!, published[1]!]).map((e) => e.id)).toEqual(once);
  });

  it("is never reshuffled: asking again gives the same, and the list given is left alone", () => {
    const given = [...published];
    expect(monthOrder(given)).toEqual(monthOrder(given));
    expect(given.map((e) => e.id)).toEqual(["a", "b", "c", "d"]);
  });

  it("keeps those already there in place when more are published", () => {
    const more = [...published, entry("e", 0.3), entry("f", 0.99)];
    const before = monthOrder(published).map((e) => e.id);
    const after = monthOrder(more).map((e) => e.id);
    expect(after.filter((id) => before.includes(id))).toEqual(before);
    expect(after).toEqual(["b", "e", "c", "a", "d", "f"]);
  });
});

describe("the footer's rotation", () => {
  it("starts somewhere new on each page load, within the list", () => {
    expect(firstShown(5, () => 0)).toBe(0);
    expect(firstShown(5, () => 0.5)).toBe(2);
    expect(firstShown(5, () => 0.9999)).toBe(4);
    expect(firstShown(0, () => 0.5)).toBe(0);
  });

  it("goes round, one at a time, back to the first after the last", () => {
    const seen = [3];
    for (let i = 0; i < 5; i++) seen.push(nextShown(seen.at(-1)!, 5));
    expect(seen).toEqual([3, 4, 0, 1, 2, 3]);
    expect(nextShown(0, 1)).toBe(0);
  });

  it("turns by itself only with more than one, unpaused, and for someone who doesn't ask for less motion", () => {
    expect(rotates(3, false, false)).toBe(true);
    expect(rotates(1, false, false)).toBe(false);
    expect(rotates(3, true, false)).toBe(false);
    expect(rotates(3, false, true)).toBe(false);
  });
});

describe("naming a nomination by its start", () => {
  it("keeps a short one whole, on one line, and cuts a long one at its first words", () => {
    expect(excerpt("A fine  duel,\nwell fought")).toBe("A fine duel, well fought");
    expect(excerpt("The court scene was magnificent and everyone in it shone", 20)).toBe("The court scene was…");
  });
});

describe("what one Publish publishes", () => {
  it("names what the troupe uses: nominations, remembrances or both", () => {
    expect(publishedWhat(true, false).button).toBe("Publish nominations");
    expect(publishedWhat(false, true)).toMatchObject({ title: "Remembrances", button: "Publish remembrances", one: "memory" });
    expect(publishedWhat(true, true)).toMatchObject({ title: "Nominations and remembrances", button: "Publish nominations and remembrances", many: "entries" });
  });
});

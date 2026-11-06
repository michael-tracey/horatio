import { describe, expect, it } from "vitest";
import type { CharacterRemembrancesOut } from "../../api/types";
import { shownAt } from "./Remembrances";

const standing = (more: Partial<CharacterRemembrancesOut>): CharacterRemembrancesOut => ({
  on: true,
  state: "none",
  cycle_name: null,
  can_open: false,
  months: [],
  ...more,
});
const month = { cycle_id: "c1", month: "October 2026", published_at: "2026-11-01T00:00:00Z", memories: [{ id: "m1", text: "Kind to the end", edited: false }] };

describe("whether a character's remembrances show", () => {
  it("shows those published, even once the troupe stops using them", () => {
    expect(shownAt(standing({ months: [month] }))).toBe(true);
    expect(shownAt(standing({ on: false, state: "open", months: [month] }))).toBe(true);
  });

  it("while on, shows them asked for or open, or for staff who can open them", () => {
    expect(shownAt(standing({ state: "asked" }))).toBe(true);
    expect(shownAt(standing({ state: "open" }))).toBe(true);
    expect(shownAt(standing({ can_open: true }))).toBe(true);
    expect(shownAt(standing({}))).toBe(false);
  });

  it("shows nothing while off with none published, nor to someone who can't read them", () => {
    expect(shownAt(standing({ on: false, state: "open" }))).toBe(false);
    expect(shownAt(null)).toBe(false);
  });
});

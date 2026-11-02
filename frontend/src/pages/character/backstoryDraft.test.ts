import { describe, expect, it } from "vitest";
import type { BackstoryOut } from "../../api/types";
import { behind, opened, unsaved, writingReducer, type Writing } from "./backstoryDraft";

function backstory(over: Partial<BackstoryOut> = {}): BackstoryOut {
  return {
    read: true,
    write: true,
    review: false,
    text: "Born in 1890.",
    version: 1,
    thread: [],
    edited_sets: [],
    draft: null,
    ...over,
  } as BackstoryOut;
}

const draft = (text: string, based_on: number, saved_at: string) => ({ text, based_on, saved_at, behind: false });

describe("the backstory as its writer has it", () => {
  it("opens the draft if there is one, else the latest version", () => {
    expect(opened(backstory()).text).toBe("Born in 1890.");
    const w = opened(backstory({ version: 3, draft: draft("Born in 1890, in Dublin.", 2, "2026-11-01T21:00:00Z") }));
    expect([w.text, w.basedOn, w.version, behind(w)]).toEqual(["Born in 1890, in Dublin.", 2, 3, true]);
  });

  it("never lets a refetch replace what was typed since the last save", () => {
    let w: Writing = opened(backstory());
    w = writingReducer(w, { type: "edit", text: "Born in 1890, in Cork." });
    expect(unsaved(w)).toBe(true);
    // A draft saved on another device, and a newer version, arrive.
    w = writingReducer(w, { type: "loaded", backstory: backstory({ version: 2, text: "Born in 1900.", draft: draft("Elsewhere", 1, "2026-11-01T22:00:00Z") }) });
    expect(w.text).toBe("Born in 1890, in Cork.");
    expect(w.basedOn).toBe(1);
    // ...and the newer version is known about, to choose between.
    expect(behind(w)).toBe(true);
  });

  it("takes what was saved elsewhere once nothing here is unsaved", () => {
    let w: Writing = opened(backstory());
    w = writingReducer(w, { type: "edit", text: "Mine" });
    w = writingReducer(w, { type: "saved", edit: w.edit, version: 1, draft: draft("Mine", 1, "2026-11-01T21:00:00Z") });
    // The same draft coming back changes nothing, and doesn't restart the editor.
    const same = writingReducer(w, { type: "loaded", backstory: backstory({ draft: draft("Mine", 1, "2026-11-01T21:00:00Z") }) });
    expect(same).toBe(w);
    // A later save from another device is taken, and the editor starts afresh with it.
    const later = writingReducer(w, { type: "loaded", backstory: backstory({ draft: draft("From the laptop", 1, "2026-11-01T21:05:00Z") }) });
    expect(later.text).toBe("From the laptop");
    expect(later.loads).toBe(w.loads + 1);
  });

  it("keeps a save made while typing went on unsaved", () => {
    let w: Writing = opened(backstory());
    w = writingReducer(w, { type: "edit", text: "One" });
    const sent = w.edit;
    w = writingReducer(w, { type: "edit", text: "One two" });
    w = writingReducer(w, { type: "saved", edit: sent, version: 1, draft: draft("One", 1, "2026-11-01T21:00:00Z") });
    expect(unsaved(w)).toBe(true);
  });

  it("keeps the player's draft over a newer version when they choose to", () => {
    let w: Writing = opened(backstory({ version: 2, text: "Theirs", draft: draft("Mine", 1, "2026-11-01T21:00:00Z") }));
    expect(behind(w)).toBe(true);
    w = writingReducer(w, { type: "keep mine", version: 2 });
    expect([w.text, w.basedOn, behind(w), unsaved(w), w.urgent]).toEqual(["Mine", 2, false, true, true]);
  });

  it("starts afresh from the server after submitting or taking theirs", () => {
    let w: Writing = opened(backstory());
    w = writingReducer(w, { type: "edit", text: "Mine" });
    w = writingReducer(w, { type: "reset", backstory: backstory({ version: 2, text: "Mine" }) });
    expect([w.text, w.basedOn, unsaved(w)]).toEqual(["Mine", 2, false]);
  });
});

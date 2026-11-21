import { describe, expect, it } from "vitest";
import { characterOf, currentTroupe, isSearchShortcut, LIMIT, manualSource, searchHere, troupeOf, type LocalSource } from "./search";

const key = (key: string, more: Partial<KeyboardEvent> = {}, tagName = "BODY") =>
  ({ key, ctrlKey: false, metaKey: false, altKey: false, target: { tagName, isContentEditable: false }, ...more }) as unknown as KeyboardEvent;

describe("the search shortcut", () => {
  it("is / outside a text box, and Ctrl+K or ⌘K anywhere", () => {
    expect(isSearchShortcut(key("/"))).toBe(true);
    expect(isSearchShortcut(key("/", {}, "INPUT"))).toBe(false);
    expect(isSearchShortcut(key("/", {}, "TEXTAREA"))).toBe(false);
    expect(isSearchShortcut(key("k", { ctrlKey: true }, "INPUT"))).toBe(true);
    expect(isSearchShortcut(key("K", { metaKey: true }))).toBe(true);
    expect(isSearchShortcut(key("k"))).toBe(false);
    expect(isSearchShortcut(key("/", { ctrlKey: true }))).toBe(false);
  });
});

describe("the troupe a page is of", () => {
  const id = "01a1f972-9b2f-78ce-ad90-4eb19b104d1c";
  it("is in a troupe's pages and its scenes", () => {
    expect(troupeOf(`/troupes/${id}`)).toBe(id);
    expect(troupeOf(`/troupes/${id}/boons`)).toBe(id);
    expect(troupeOf(`/play/troupes/${id}/scenes`)).toBe(id);
    expect(troupeOf("/troupes")).toBeNull();
    expect(troupeOf(`/characters/${id}`)).toBeNull();
  });
});

describe("the troupe searched first", () => {
  const troupe = "01a1f972-9b2f-78ce-ad90-4eb19b104d1c";
  const home = "01a1f972-0000-78ce-ad90-4eb19b104d1c";
  const character = "01a1f972-1111-78ce-ad90-4eb19b104d1c";
  it("finds the character a page is of", () => {
    expect(characterOf(`/characters/${character}`)).toBe(character);
    expect(characterOf(`/characters/${character}/sheet`)).toBe(character);
    expect(characterOf(`/play/characters/${character}/ledger`)).toBe(character);
    expect(characterOf("/characters/import")).toBeNull();
    expect(characterOf(`/troupes/${troupe}`)).toBeNull();
  });

  it("is the troupe whose page it is, or on a character's page its home troupe (#1147)", () => {
    expect(currentTroupe(`/troupes/${troupe}/boons`, home)).toBe(troupe);
    expect(currentTroupe(`/characters/${character}/sheet`, home)).toBe(home);
    expect(currentTroupe(`/characters/${character}`, null)).toBeNull();
    expect(currentTroupe(`/characters/${character}`, undefined)).toBeNull();
    // Only a character's page has one.
    expect(currentTroupe("/characters", home)).toBeNull();
  });
});

describe("searching here", () => {
  const counting = (n: number): LocalSource => ({
    kind: "settings",
    label: "Settings",
    find: async (q) => Array.from({ length: n }, (_, i) => ({ id: `${i}`, title: `${q} ${i}`, detail: "", to: `/x/${i}`, troupe: null, troupe_id: null })),
  });

  it("gives each source a group of its own, five at most, saying when there are more", async () => {
    const [group] = await searchHere("raven", { troupeId: null }, [counting(LIMIT + 1)]);
    if (!group) throw new Error("no group");
    expect(group.kind).toBe("settings");
    expect(group.hits).toHaveLength(LIMIT);
    expect(group.more).toBe(true);
  });

  it("leaves out a source with nothing, and asks nothing of fewer than two letters", async () => {
    expect(await searchHere("raven", { troupeId: null }, [counting(0)])).toEqual([]);
    expect(await searchHere(" r ", { troupeId: null }, [counting(3)])).toEqual([]);
  });

  it("finds the manual's sections, opening each at its heading", async () => {
    const hits = await manualSource.find("boon ledger", { troupeId: null });
    expect(hits.length).toBeGreaterThan(0);
    expect(hits[0]?.to).toMatch(/^\/help(\/[\w-]+)?(#.+)?$/);
    expect(hits.length).toBeLessThanOrEqual(LIMIT + 1);
  });
});

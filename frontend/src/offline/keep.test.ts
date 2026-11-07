import { describe, expect, it } from "vitest";
import type { CharacterListOut } from "../api/types";
import { clearDevice, dropSent, keeping, keepsQuery, keptCharacters, keptFor, markAsked, mineOf, recordKey, setKeeping, setKeptFor, tapsWaiting, waitingTaps, wasAsked } from "./keep";

class MemoryStorage implements Storage {
  private items = new Map<string, string>();
  get length() {
    return this.items.size;
  }
  clear() {
    this.items.clear();
  }
  getItem(key: string) {
    return this.items.get(key) ?? null;
  }
  key(index: number) {
    return [...this.items.keys()][index] ?? null;
  }
  removeItem(key: string) {
    this.items.delete(key);
  }
  setItem(key: string, value: string) {
    this.items.set(key, value);
  }
}

const ME = "11111111-1111-4111-8111-111111111111";
const OTHER = "22222222-2222-4222-8222-222222222222";
const ROSA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const OLD = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const NEW = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const HOME = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";

function character(id: string, changes: Partial<CharacterListOut> = {}): CharacterListOut {
  return {
    id,
    name: id.slice(0, 4),
    player_id: ME,
    kind: "pc",
    status: "active",
    creation_complete: true,
    home_troupe_id: HOME,
    building_troupe_id: null,
    ...changes,
  } as CharacterListOut;
}

const list = [character(ROSA), character(OLD, { status: "retired" }), character(NEW, { creation_complete: false })];

describe("the device's choice", () => {
  it("is off until the person answers, and is theirs alone", () => {
    const storage = new MemoryStorage();
    expect(keeping(ME, storage)).toBeNull();
    setKeeping(ME, "on", storage);
    expect(keeping(ME, storage)).toBe("on");
    expect(keeping(OTHER, storage)).toBeNull();
  });

  it("asks once per device, whoever answers", () => {
    const storage = new MemoryStorage();
    expect(wasAsked(storage)).toBe(false);
    markAsked(storage);
    expect(wasAsked(storage)).toBe(true);
  });

  it("loads someone's kept answers as the app opens only while their choice is on", () => {
    const storage = new MemoryStorage();
    setKeptFor(ME, storage);
    expect(keptFor(storage)).toBeNull();
    setKeeping(ME, "on", storage);
    expect(keptFor(storage)).toBe(ME);
    setKeeping(ME, "off", storage);
    expect(keptFor(storage)).toBeNull();
  });

  it("keeps each person's answers under their own key", () => {
    expect(recordKey(ME)).not.toBe(recordKey(OTHER));
  });
});

describe("what is kept", () => {
  it("is the person's own characters in play: not retired, not still being made, not someone else's", () => {
    const others = [...list, character(OTHER, { player_id: OTHER })];
    expect(keptCharacters(others, ME).map((c) => c.id)).toEqual([ROSA]);
  });

  const mine = mineOf(list, ME);

  it("keeps who the person is and the rules", () => {
    for (const key of [["me"], ["characters"], ["troupes"], ["splats"], ["catalogue", "vampire", HOME]]) expect(keepsQuery(key, mine)).toBe(true);
  });

  it("keeps the sheet, the Play View and its reference for the person's own kept characters", () => {
    for (const what of ["character", "sheet", "play", "play-reference", "character-equipment"]) {
      expect(keepsQuery([what, ROSA], mine)).toBe(true);
      expect(keepsQuery([what, OLD], mine)).toBe(false);
      expect(keepsQuery([what, OTHER], mine)).toBe(false);
    }
  });

  it("keeps the home troupe of a kept character, and no other troupe", () => {
    expect(keepsQuery(["troupe", HOME], mine)).toBe(true);
    expect(keepsQuery(["troupe", OTHER], mine)).toBe(false);
  });

  it("never keeps staff screens, other characters on the Play View, or anything between games", () => {
    for (const key of [["scenes", HOME, false], ["scene", ROSA], ["roster", HOME], ["npcs", HOME], ["check-in", HOME], ["play-others", ROSA], ["xp", ROSA], ["results", ROSA], ["player", ME], ["notifications"]])
      expect(keepsQuery(key, mine)).toBe(false);
  });
});

describe("taps waiting and signing out", () => {
  const tap = (id: string) => ({ id, kind: "change", tracker: "blood", amount: -1 });

  it("counts the taps waiting for every character", () => {
    const storage = new MemoryStorage();
    storage.setItem(`horatio.play.${ROSA}`, JSON.stringify([tap("a"), tap("b")]));
    storage.setItem(`horatio.play.${NEW}`, JSON.stringify([tap("c")]));
    storage.setItem(`horatio.play.reference.${ROSA}`, JSON.stringify({ traits: [] }));
    expect(tapsWaiting(storage)).toBe(3);
    expect(waitingTaps(storage).map((q) => q.characterId).sort()).toEqual([ROSA, NEW].sort());
  });

  it("drops the taps sent, keeping any made since", () => {
    const storage = new MemoryStorage();
    storage.setItem(`horatio.play.${ROSA}`, JSON.stringify([tap("a"), tap("b")]));
    dropSent(ROSA, ["a"], storage);
    expect(waitingTaps(storage)[0]!.taps.map((t) => t.id)).toEqual(["b"]);
    dropSent(ROSA, ["b"], storage);
    expect(storage.getItem(`horatio.play.${ROSA}`)).toBeNull();
  });

  it("clears the taps and what is kept about characters at sign-out, and leaves the device's own settings", () => {
    const storage = new MemoryStorage();
    storage.setItem(`horatio.play.${ROSA}`, JSON.stringify([tap("a")]));
    storage.setItem(`horatio.play.reference.${ROSA}`, "{}");
    storage.setItem(`horatio.play.equipment.${ROSA}`, "{}");
    storage.setItem(`horatio.play.modifiers.${ROSA}`, "[]");
    storage.setItem(`horatio.feed.${ROSA}`, "{}");
    storage.setItem("horatio.feed.sound", "1");
    storage.setItem("horatio.text-size", "large");
    setKeeping(ME, "on", storage);
    setKeptFor(ME, storage);
    markAsked(storage);
    clearDevice(storage);
    expect(tapsWaiting(storage)).toBe(0);
    expect(storage.getItem(`horatio.play.reference.${ROSA}`)).toBeNull();
    expect(storage.getItem(`horatio.play.equipment.${ROSA}`)).toBeNull();
    expect(storage.getItem(`horatio.play.modifiers.${ROSA}`)).toBeNull();
    expect(storage.getItem(`horatio.feed.${ROSA}`)).toBeNull();
    expect(storage.getItem("horatio.feed.sound")).toBe("1");
    expect(keptFor(storage)).toBeNull();
    expect(storage.getItem("horatio.text-size")).toBe("large");
    expect(wasAsked(storage)).toBe(true);
  });
});

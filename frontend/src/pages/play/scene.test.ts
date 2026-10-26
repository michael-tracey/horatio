import { describe, expect, it } from "vitest";
import { findPins, loadOpen, loadScene, pin, saveOpen, saveScene, toggleOpen, unpin } from "./scene";

function memory(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, v),
  };
}

describe("the scene's pins", () => {
  it("keeps one scene per troupe, in the order pinned", () => {
    const storage = memory();
    saveScene("a", ["x", "y"], storage);
    saveScene("b", ["z"], storage);
    expect(loadScene("a", storage)).toEqual(["x", "y"]);
    expect(loadScene("b", storage)).toEqual(["z"]);
    expect(loadScene("c", storage)).toEqual([]);
  });

  it("forgets an emptied scene", () => {
    const storage = memory();
    saveScene("a", ["x"], storage);
    saveScene("a", [], storage);
    expect(storage.length).toBe(0);
  });

  it("reads nothing from damaged storage, and survives storage that throws", () => {
    const storage = memory();
    storage.setItem("horatio.scene.a", "{nope");
    expect(loadScene("a", storage)).toEqual([]);
    storage.setItem("horatio.scene.a", JSON.stringify(["x", 3, "x", null, "y"]));
    expect(loadScene("a", storage)).toEqual(["x", "y"]);
    const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }, removeItem: () => { throw new Error("blocked"); } } as unknown as Storage;
    expect(loadScene("a", broken)).toEqual([]);
    expect(() => saveScene("a", ["x"], broken)).not.toThrow();
  });

  it("pins once and unpins", () => {
    expect(pin(["x"], "y")).toEqual(["x", "y"]);
    expect(pin(["x", "y"], "x")).toEqual(["x", "y"]);
    expect(unpin(["x", "y"], "x")).toEqual(["y"]);
  });

  it("finds names with what was typed, those starting with it first", () => {
    const all = [{ character_name: "Sheriff Ilse" }, { character_name: "Ilona" }, { character_name: "Marcus" }];
    expect(findPins(all, "").map((c) => c.character_name)).toEqual(["Sheriff Ilse", "Ilona", "Marcus"]);
    expect(findPins(all, " IL").map((c) => c.character_name)).toEqual(["Ilona", "Sheriff Ilse"]);
    expect(findPins(all, "zzz")).toEqual([]);
  });

  it("keeps the open sections of each card, several at once", () => {
    const storage = memory();
    saveOpen("a", ["pools", "log"], storage);
    expect(loadOpen("a", storage)).toEqual(["pools", "log"]);
    expect(loadOpen("b", storage)).toEqual([]);
    saveOpen("a", [], storage);
    expect(storage.getItem("horatio.scene.open.a")).toBeNull();
    storage.setItem("horatio.scene.open.a", JSON.stringify(["pools", "bogus", 3]));
    expect(loadOpen("a", storage)).toEqual(["pools"]);
  });

  it("opens a section, or closes it if open", () => {
    expect(toggleOpen(["pools"], "powers")).toEqual(["pools", "powers"]);
    expect(toggleOpen(["pools", "powers"], "pools")).toEqual(["powers"]);
  });
});

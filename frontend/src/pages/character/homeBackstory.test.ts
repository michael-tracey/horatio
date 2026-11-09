import { describe, expect, it } from "vitest";
import { homeBackstory } from "./homeBackstory";

const agnes = { name: "Agnes", kind: "pc" };
const lords = { name: "Lords of the Night", backstory_required: true };

describe("asking a troupe that needs a backstory", () => {
  it("sends the player to write it first when nothing is written", () => {
    expect(homeBackstory(agnes, lords, { write: true, written: false })).toEqual({
      need: "write",
      words: "Lords of the Night needs a backstory to accept Agnes.",
    });
  });

  it("lets the request go with a written backstory, for the troupe to approve", () => {
    expect(homeBackstory(agnes, lords, { write: true, written: true })).toEqual({
      need: "goes",
      words: "Agnes's backstory goes with the request, for Lords of the Night's storytellers to read and approve.",
    });
  });

  it("only says so to someone who can't write it", () => {
    expect(homeBackstory(agnes, lords, { write: false, written: false })?.need).toBe("missing");
  });

  it("says nothing for a troupe that doesn't need one, an NPC, or before the standing is known", () => {
    expect(homeBackstory(agnes, { ...lords, backstory_required: false }, { write: true, written: false })).toBeNull();
    expect(homeBackstory({ name: "Mook", kind: "npc" }, lords, { write: true, written: false })).toBeNull();
    expect(homeBackstory(agnes, lords, undefined)).toBeNull();
    expect(homeBackstory(agnes, undefined, { write: true, written: false })).toBeNull();
  });
});

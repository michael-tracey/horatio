import { describe, expect, it } from "vitest";
import { asksEquipment, charactersFilter, columns, complete, decode, DEFAULT_FILTER, encode, ready, sentence, type Group } from "./filters";

const names = {
  category: (key: string) => ({ clan: "Clan", merits: "Merits" })[key] ?? key,
  player: (id: string) => ({ u1: "Jane" })[id] ?? id,
  character: (id: string) => ({ c1: "Agnes", c2: "Bram" })[id] ?? id,
};

const OCCULT = { what: "trait", which: "skills/Occult", op: "lt", value: 3 } as const;
const CLANS: Group = {
  match: "any",
  items: [
    { what: "choice", which: "clan", op: "is", value: ["Tremere"] },
    { what: "choice", which: "clan", op: "family", value: ["Giovanni"] },
  ],
};

describe("sentence", () => {
  it("reads a compound filter, with sub-groups in brackets", () => {
    const filter: Group = { match: "all", items: [OCCULT, CLANS] };
    expect(sentence(filter, names)).toBe("Occult below 3, and (Clan is Tremere, or Clan is in the Giovanni family)");
  });

  it("reads each kind of condition", () => {
    const read = (item: Group["items"][number]) => sentence({ match: "all", items: [item] }, names);
    expect(read({ what: "status", op: "is_not", value: "retired" })).toBe("Is not retired");
    expect(read({ what: "trait", which: "merits/Acute Sense", op: "has" })).toBe("Has Acute Sense");
    expect(read({ what: "trait", which: "skills/Lore/Kindred", op: "gte", value: 2 })).toBe("Lore: Kindred at least 2");
    expect(read({ what: "choice", which: "clan", op: "is_not", value: ["Brujah", "Gangrel"] })).toBe("Clan is not Brujah or Gangrel");
    expect(read({ what: "title", op: "has", value: null })).toBe("Holds a title");
    expect(read({ what: "title", op: "lacks", value: "Harpy" })).toBe("Does not hold the title Harpy");
    expect(read({ what: "player", op: "is", value: "u1" })).toBe("Player is Jane");
    expect(read({ what: "xp", which: "unspent", op: "gt", value: 5 })).toBe("Unspent XP above 5");
    expect(read({ what: "count", which: "merits", op: "gte", value: 2 })).toBe("Number of merits at least 2");
    expect(read({ what: "character", op: "is", value: ["c1", "c2"] })).toBe("Character is Agnes or Bram");
  });

  it("reads an equipment condition", () => {
    const read = (op: "has" | "lacks", value: object) => sentence({ match: "all", items: [{ what: "equipment", op, value }] }, names);
    expect(read("has", {})).toBe("Has equipment");
    expect(read("has", { kind: "ranged", quality: "Silver Ammunition" })).toBe("Has a ranged weapon with Silver Ammunition");
    expect(read("lacks", { kind: "protective" })).toBe("Lacks protective gear");
    expect(read("has", { quality: "Customized", detail: " hacking " })).toBe("Has equipment with Customized: hacking");
    expect(read("has", { kind: "melee", special: true, name: "stake" })).toBe("Has a special melee weapon named “stake”");
  });
});

describe("equipment links", () => {
  it("knows a filter asking about equipment, in a group or not", () => {
    expect(asksEquipment(DEFAULT_FILTER)).toBe(false);
    expect(asksEquipment({ match: "all", items: [{ match: "any", items: [{ what: "equipment", op: "lacks", value: {} }] }] })).toBe(true);
  });

  it("filters to the characters given, and waits for one", () => {
    expect(charactersFilter(["c1"])).toEqual({ match: "all", items: [{ what: "character", op: "is", value: ["c1"] }] });
    expect(complete({ what: "character", op: "is", value: [] })).toBe(false);
    expect(complete({ what: "equipment", op: "has", value: {} })).toBe(true);
  });
});

describe("ready", () => {
  it("sends only complete conditions, and drops emptied groups", () => {
    const filter: Group = {
      match: "all",
      items: [OCCULT, { what: "trait", which: null, op: "gte", value: 1 }, { match: "any", items: [{ what: "player", op: "is", value: null }] }],
    };
    expect(ready(filter)).toEqual({ match: "all", items: [OCCULT] });
  });

  it("knows what is complete", () => {
    expect(complete({ what: "choice", which: "clan", op: "is", value: [] })).toBe(false);
    expect(complete({ what: "trait", which: "merits/Acute Sense", op: "has" })).toBe(true);
    expect(complete({ what: "trait", which: "skills/", op: "gte", value: 1 })).toBe(false);
    expect(complete({ what: "title", op: "has", value: null })).toBe(true);
  });
});

describe("columns", () => {
  it("lists each number the filter compares once", () => {
    expect(columns({ match: "all", items: [OCCULT, { match: "any", items: [OCCULT, { what: "xp", which: "earned", op: "gte", value: 1 }] }] })).toEqual([
      OCCULT,
      { what: "xp", which: "earned", op: "gte", value: 1 },
    ]);
  });
});

describe("encode and decode", () => {
  it("round-trips", () => {
    const filter: Group = { match: "all", items: [OCCULT, CLANS] };
    expect(decode(encode(filter))).toEqual(filter);
  });

  it("falls back to the default for no filter or a mangled one", () => {
    expect(decode(null)).toBe(DEFAULT_FILTER);
    expect(decode("{nope")).toBe(DEFAULT_FILTER);
  });
});

import { describe, expect, it } from "vitest";
import type { EquipmentItemOut } from "../../api/types";
import { holdersLink, itemsCsv, readSearch, searchQuery, writeSearch } from "./equipmentSearch";

describe("the search in the URL", () => {
  it("starts with held items by holder, and writes nothing for that", () => {
    const start = readSearch(new URLSearchParams());
    expect(start).toMatchObject({ q: "", holders: [], statuses: ["held"], retired: false, sort: "holder" });
    expect(writeSearch(start).toString()).toBe("");
  });

  it("keeps everything it asks across a reload", () => {
    const params = new URLSearchParams("q=silver&holders=c1,c2&kind=melee&quality=Staking&grade=special&show=held,discarded&retired=1&given_by=u1&from=2026-10-01&to=2026-10-31&sort=date");
    const search = readSearch(params);
    expect(search).toEqual({
      q: "silver",
      holders: ["c1", "c2"],
      kind: "melee",
      quality: "Staking",
      grade: "special",
      statuses: ["held", "discarded"],
      retired: true,
      givenBy: "u1",
      from: "2026-10-01",
      to: "2026-10-31",
      sort: "date",
    });
    expect(readSearch(writeSearch(search))).toEqual(search);
  });

  it("ignores what it doesn't know", () => {
    expect(readSearch(new URLSearchParams("show=lost&sort=colour"))).toMatchObject({ statuses: ["held"], sort: "holder" });
  });
});

describe("searchQuery", () => {
  it("asks for the given days whole, on the reader's clock", () => {
    const midnight = (day: string) => new Date(`${day}T00:00:00-05:00`);
    const search = readSearch(new URLSearchParams("from=2026-10-01&to=2026-10-31&holders=c1"));
    expect(searchQuery(search, midnight)).toMatchObject({
      given_after: "2026-10-01T05:00:00.000Z",
      given_before: "2026-11-01T05:00:00.000Z",
      character_id: ["c1"],
      status: ["held"],
      q: undefined,
    });
  });
});

describe("holdersLink", () => {
  it("opens the Equipment tab on those characters", () => {
    expect(holdersLink("t1", ["c1", "c2"], false)).toBe("/troupes/t1/equipment?holders=c1%2Cc2");
    expect(holdersLink("t1", ["c1"], true)).toBe("/troupes/t1/equipment?holders=c1&retired=1");
    expect(holdersLink("t1", [], false)).toBe("/troupes/t1/equipment");
  });
});

describe("itemsCsv", () => {
  const item = {
    name: 'The "Widow"',
    character_name: "Agnes",
    character_kind: "pc",
    player_name: "Jane",
    kind_name: "Melee weapon",
    grade: "special",
    qualities: [{ name: "Staking" }, { name: "Masterwork", detail: "cuts, deep" }],
    effects: [{ name: "Drinks the Blood", effect: "Heal 1." }],
    description: "Line one\nline two",
    status: "discarded",
    given_by_name: "Lead",
    troupe_name: "Lords of the Night",
    given_at: "2026-10-27T20:00:00Z",
    staff_note: "=1+1",
  } as unknown as EquipmentItemOut;

  it("writes a heading and a line an item, quoting where it must", () => {
    const csv = itemsCsv([item], (at) => at.slice(0, 10));
    const [heading, ...rest] = csv.trimEnd().split("\r\n");
    expect(heading).toBe("Item,Held by,Player,Kind,Grade,Qualities,Special effects,Description,Status,Given by,Troupe,Given on,Staff note");
    expect(rest.join("\r\n")).toBe(
      '"The ""Widow""",Agnes,Jane,Melee weapon,Special,"Staking; Masterwork: cuts, deep",Drinks the Blood: Heal 1.,"Line one\nline two",Discarded,Lead,Lords of the Night,2026-10-27,\'=1+1',
    );
  });
});

import { describe, expect, it } from "vitest";
import { aliasText, titleGives, titleGroups, titleStatusWords } from "./titleGroups";

describe("titleGroups", () => {
  it("puts the troupe's sects first, then other sects still held, then any sect", () => {
    const titles = [
      { name: "Soldier", sect: null },
      { name: "Bishop", sect: "Sabbat" },
      { name: "Prince", sect: "Camarilla" },
      { name: "Harpy", sect: "Camarilla" },
    ];
    expect(titleGroups(["Anarch", "Camarilla"], titles).map(([sect, list]) => [sect, list.map((t) => t.name)])).toEqual([
      ["Camarilla", ["Prince", "Harpy"]],
      ["Sabbat", ["Bishop"]],
      [null, ["Soldier"]],
    ]);
  });
});

describe("titleStatusWords", () => {
  it("says what a title gives, choices and absences included", () => {
    expect(titleStatusWords({ status: ["Noble"], choose_one: [], while_absent: [{ title: "Prince", status: ["Authority"], note: "" }] })).toEqual([
      "Noble",
      "Authority while the Prince is away",
    ]);
    expect(titleStatusWords({ status: [], choose_one: ["Blessed", "Enforcer"], while_absent: [] })).toEqual(["Blessed or Enforcer, chosen each game"]);
    expect(titleStatusWords({ status: [], choose_one: [], while_absent: [] })).toEqual([]);
  });
});

describe("titleGives", () => {
  const plain = { alias_of: null, clan: null, gives_none: "", no_rules_yet: false };
  it("says the status a title gives", () => {
    expect(titleGives(["Prominent", "Noble"], plain)).toBe("Gives Prominent · Noble");
  });
  it("says why a title gives none, in the rules' words", () => {
    expect(titleGives([], { ...plain, gives_none: "An Abbot gains no abiding status for the office." })).toBe(
      "An Abbot gains no abiding status for the office",
    );
  });
  it("gives a clan's title its clan", () => {
    expect(titleGives([], { ...plain, clan: "Tremere" })).toBe("A Tremere title: it gives no sect status");
  });
  it("says a title no book describes has no rules yet", () => {
    expect(titleGives([], { ...plain, no_rules_yet: true })).toBe("No rules yet: no book describes it, so it gives no status");
  });
  it("says nothing more of a plain name than that it gives no status", () => {
    expect(titleGives([], plain)).toBe("Gives no status");
  });
});

describe("aliasText", () => {
  it("names the title another name is for", () => {
    expect(aliasText({ alias_of: "Harpy" })).toBe("another name for Harpy");
    expect(aliasText({ alias_of: null })).toBeNull();
  });
});

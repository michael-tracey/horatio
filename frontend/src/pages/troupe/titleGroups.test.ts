import { describe, expect, it } from "vitest";
import { titleGroups, titleStatus } from "./titleGroups";

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

describe("titleStatus", () => {
  it("says what a title gives, choices and absences included", () => {
    expect(titleStatus({ status: ["Noble"], choose_one: [], while_absent: [{ title: "Prince", status: ["Authority"], note: "" }] })).toBe(
      "Noble · Authority while the Prince is away",
    );
    expect(titleStatus({ status: [], choose_one: ["Blessed", "Enforcer"], while_absent: [] })).toBe("Blessed or Enforcer, chosen each game");
    expect(titleStatus({ status: [], choose_one: [], while_absent: [] })).toBe("");
  });
});

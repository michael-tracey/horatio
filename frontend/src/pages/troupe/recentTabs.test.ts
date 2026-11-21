import { describe, expect, it } from "vitest";
import { recentTabs, tabAddress, withOpened } from "./recentTabs";

const base = "/troupes/t1";
const tabs = [
  { to: base, label: "Overview", end: true },
  { to: `${base}/approvals`, label: "Approvals" },
  { to: `${base}/roster`, label: "Roster" },
  { to: `${base}/downtimes`, label: "Downtimes" },
  { to: "/play/troupes/t1/scenes", label: "Scenes ↗" },
];

describe("the tabs opened last (#1048)", () => {
  it("puts the tab just opened first, each once, keeping the open one and three more", () => {
    expect(withOpened([], "/roster")).toEqual(["/roster"]);
    expect(withOpened(["/roster", "", "/approvals"], "/approvals")).toEqual(["/approvals", "/roster", ""]);
    expect(withOpened(["/a", "/b", "/c", "/d"], "/e")).toEqual(["/e", "/a", "/b", "/c"]);
  });

  it("names a tab by its address under the troupe's, and none for one that leaves it", () => {
    expect(tabAddress(tabs[0]!, base)).toBe("");
    expect(tabAddress(tabs[1]!, base)).toBe("/approvals");
    expect(tabAddress(tabs[4]!, base)).toBeUndefined();
  });

  it("shows three at most, not the open one, nor one the person can't open now", () => {
    const open = tabs[3];
    expect(recentTabs(["/downtimes", "/approvals", "/gone", "", "/roster"], tabs, base, open).map((t) => t.label)).toEqual(["Approvals", "Overview", "Roster"]);
    expect(recentTabs([], tabs, base, open)).toEqual([]);
  });
});

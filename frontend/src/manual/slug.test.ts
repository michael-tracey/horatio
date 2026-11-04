import { describe, expect, it } from "vitest";
import { slug, slugger } from "./slug";

describe("slug", () => {
  it("makes GitHub's anchors", () => {
    expect(slug("Spending XP")).toBe("spending-xp");
    expect(slug("Spending XP & approvals")).toBe("spending-xp--approvals");
    expect(slug("Who's Who")).toBe("whos-who");
    expect(slug("Who’s Who")).toBe("whos-who");
    expect(slug("What's a cycle? (and a grace period)")).toBe("whats-a-cycle-and-a-grace-period");
    expect(slug("Customise › Rules › Costs")).toBe("customise--rules--costs");
    expect(slug("snake_case and half-done")).toBe("snake_case-and-half-done");
    expect(slug("  Trimmed  ")).toBe("trimmed");
    expect(slug("Café 2026")).toBe("café-2026");
  });

  it("numbers a heading repeated on a page, as GitHub does", () => {
    const next = slugger();
    expect(["Notes", "Notes", "Notes-1", "Notes"].map(next)).toEqual(["notes", "notes-1", "notes-1-1", "notes-2"]);
  });
});

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ClanWeaknessesOut, WeaknessOut } from "../api/types";
import { ChoiceInfo } from "../pages/character/Info";
import { coreAfter, versionText, weaknessChangeText } from "../pages/troupe/ClanWeaknesses";
import { ClanWeakness, hasWeakness } from "./ClanWeakness";

afterEach(cleanup);

const BOTH: WeaknessOut[] = [
  { book: "vol2", label: "Volume 2", weakness: "Bonds others only to the first stage.", page: "Vol. 2, p. 22" },
  { book: "core", label: "Core book", weakness: "The first drink counts as two.", page: "64" },
];

describe("ClanWeakness", () => {
  it("is the weakness the troupe plays, with its page", () => {
    render(<ClanWeakness trait={{ weakness: "Bonds others only to the first stage.", weakness_page: "Vol. 2, p. 22" }} />);
    expect(document.body.textContent).toBe("Weakness: Bonds others only to the first stage. (Vol. 2, p. 22)");
    cleanup();
    render(<ClanWeakness trait={{ weakness: "Quick to rage.", weakness_page: "45" }} page="plain" />);
    expect(document.body.textContent).toBe("Weakness: Quick to rage. p. 45");
  });

  it("with no troupe, says it varies by troupe and gives each, with its page", () => {
    render(<ClanWeakness trait={{ weaknesses: BOTH }} />);
    expect(document.body.textContent).toContain("Weakness: varies by troupe.");
    expect(screen.getAllByRole("listitem").map((i) => i.textContent)).toEqual([
      "Volume 2: Bonds others only to the first stage. (Vol. 2, p. 22)",
      "Core book: The first drink counts as two. (p. 64)",
    ]);
  });

  it("is nothing for a trait with no weakness", () => {
    expect(hasWeakness({})).toBe(false);
    expect(hasWeakness({ weaknesses: [] })).toBe(false);
    expect(hasWeakness({ weaknesses: BOTH })).toBe(true);
    const { container } = render(<ClanWeakness trait={{ weaknesses: [] }} />);
    expect(container.textContent).toBe("");
  });
});

describe("the clan's ⓘ on a character's title", () => {
  const clan = { category: "clan", category_name: "Clan", note: "" };

  it("gives the clan's weakness as its troupe plays it, or both with no troupe", () => {
    render(<ChoiceInfo choice={clan} shown="Tremere" about={{ in_clan: ["Auspex"], weakness: "The first drink counts as two.", weakness_page: "64" }} />);
    fireEvent.click(screen.getByRole("button", { name: "About Tremere" }));
    expect(document.body.textContent).toContain("Weakness: The first drink counts as two. (p. 64)");
    cleanup();
    render(<ChoiceInfo choice={clan} shown="Tremere" about={{ weaknesses: BOTH }} />);
    fireEvent.click(screen.getByRole("button", { name: "About Tremere" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});

describe("the Clan weaknesses setting", () => {
  const versions = BOTH.map((w) => ({ ...w, page: w.page ?? null }));
  const clans: ClanWeaknessesOut["clans"] = [
    { clan: "Tremere", versions, chosen: "vol2" },
    { clan: "Ventrue", versions, chosen: "core" },
  ];

  it("sends the clans played by the core book's once one changes", () => {
    expect(coreAfter(clans, "Tremere", "core")).toEqual(["Tremere", "Ventrue"]);
    expect(coreAfter(clans, "Ventrue", "vol2")).toEqual([]);
  });

  it("says what changed, and each weakness with its page", () => {
    expect(weaknessChangeText("Tremere", "core")).toBe("The Tremere here play by the core book's weakness now.");
    expect(weaknessChangeText("Tremere", "vol2")).toBe("The Tremere here play by Volume 2's weakness now.");
    expect(versionText(versions[1]!)).toBe("The first drink counts as two. (p. 64)");
  });
});

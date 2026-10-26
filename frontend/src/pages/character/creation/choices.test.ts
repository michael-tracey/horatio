// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { DISCIPLINES_FROM_MERITS } from "./disciplines";
import { BACKGROUND_MERITS, FOCUS_MERITS, SKILL_MERITS } from "./gifts";
import { IN_CLAN_MERITS } from "./inClan";

// Merits and flaws that need the player to choose something (#216): the wizard has to
// offer each choice on the step it changes, and say so until it is made. This reads the
// rules data, so a merit added there with a choice the wizard does not know fails here.
const data = (file: string) => readFileSync(new URL(`../../../../../backend/src/horatio/rules/data/${file}`, import.meta.url), "utf8");

/** The `[[table]]` entries of a TOML file, as their text. */
const entries = (text: string, table: string) =>
  text
    .split(/^\[\[/m)
    .filter((b) => b.startsWith(`${table}]]`))
    .map((b) => b.slice(table.length + 2));
const field = (entry: string, key: string) => entry.match(new RegExp(`^${key} = "([^"]+)"`, "m"))?.[1];
const line = (entry: string, key: string) => entry.match(new RegExp(`^${key} = ([^\\n]*)`, "m"))?.[1] ?? "";

const grants = entries(data("bns_met_vampire_grants.toml"), "grants").map((g) => {
  const source = line(g, "source").match(/category = "(\w+)", name = "([^"]+)"/);
  const target = line(g, "target");
  return {
    category: source?.[1],
    name: source?.[2],
    kind: field(g, "kind"),
    targets: [...target.matchAll(/"(\w+)"/g)].map((m) => m[1]!).filter((c) => !/^[A-Z]/.test(c) && c !== "any"),
    chooses: /\bchoose\b/.test(target),
    fixed: /\bname = "/.test(target),
  };
});
const checks = entries(data("bns_met_vampire_checks.toml"), "checks").map((c) => ({
  category: field(c, "category"),
  name: field(c, "name"),
  complete: field(c, "strength") === "complete",
  text: c,
}));

/** Where the wizard offers a choice that lands in each category. One landing on
 * Merits & flaws (Old Habits' merits) or with no step of its own (Path Adherent's
 * path) is chosen there, beside the merit. */
const STEP_LISTS: Record<string, { category: string; name: string }[] | "merits"> = {
  focus_physicals: FOCUS_MERITS,
  focus_mentals: FOCUS_MERITS,
  focus_socials: FOCUS_MERITS,
  skills: SKILL_MERITS,
  lore_specializations: SKILL_MERITS,
  linguistics_specializations: SKILL_MERITS,
  academics_specializations: SKILL_MERITS,
  backgrounds: BACKGROUND_MERITS,
  disciplines: DISCIPLINES_FROM_MERITS,
  extra_in_clan_disciplines: IN_CLAN_MERITS.map((name) => ({ category: "merits", name })),
  merits: "merits",
  paths: "merits",
};

const key = (t: { category?: string; name?: string }) => `${t.category}/${t.name}`;

describe("merits and flaws that need a choice", () => {
  const choosing = grants.filter((g) => g.chooses);

  it("finds the ones the rules data has", () => {
    // A sanity check on the reading of the data above.
    expect(choosing.map(key)).toEqual(expect.arrayContaining(["merits/Versatile", "merits/Ventrue Royalty", "flaws/Inept", "merits/Bonds of Stolen Vitae", "merits/Path Adherent"]));
  });

  it("are each offered on the step their choice changes", () => {
    const missing = choosing.flatMap((g) =>
      g.targets
        .map((category) => {
          const list = STEP_LISTS[category];
          if (list === "merits") return null;
          if (!list) return `${key(g)}: no step for ${category}`;
          return list.some((t) => key(t) === key(g)) ? null : `${key(g)}: not offered with ${category}`;
        })
        .filter((m): m is string => !!m),
    );
    expect(missing).toEqual([]);
  });

  // An in-clan discipline a merit lets a Caitiff, or anyone, choose: the checks on
  // Extra In-Clan Disciplines name the merit. One that gives a set discipline (Web
  // of Knives' Potence) asks for no choice.
  const inClan = [
    ...new Set(
      checks
        .filter((c) => c.category === "extra_in_clan_disciplines")
        .flatMap((c) => [...c.text.matchAll(/has = \{ category = "merits", name = "([^"]+)" \}/g)].map((m) => m[1]!)),
    ),
  ].filter((name) => !grants.some((g) => g.name === name && g.kind === "add" && g.fixed && g.targets.includes("extra_in_clan_disciplines")));

  it("that open an in-clan discipline to choose are offered on Concept", () => {
    expect(inClan.sort()).toEqual([...IN_CLAN_MERITS].sort());
  });

  it("that open an in-clan discipline hold back finishing until it is chosen", () => {
    // Chosen in the merit's detail, which the server asks for when it is taken (Bonds of
    // Stolen Vitae), or on Concept, with a check that finishing waits on.
    const unchecked = inClan.filter(
      (name) => !grants.some((g) => g.name === name && g.chooses) && !checks.some((c) => c.category === "merits" && c.name === name && c.complete),
    );
    expect(unchecked).toEqual([]);
  });
});

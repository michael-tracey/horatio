import { describe, expect, it } from "vitest";
import type { CreationOut, PoolOut, SheetOut, SheetTraitOut } from "../../../api/types";
import { clanChoiceNeeded, inClanChoice, inClanChoices, inClanOpen, inClanOptions, inClanShortfalls, makesInClanChoice, sheetKey, whenTapped } from "./inClan";
import { disciplinesIntro, ineptChoices, movePick, strayMoves, withoutDotReasons } from "./disciplines";
import { brokenChecks, overBudget, stepNotices, strayPicks, type StepRef } from "./notices";

const STEPS: StepRef[] = [
  { key: "concept", title: "Concept", categories: [], decides: ["clan", "extra_in_clan_disciplines"] },
  { key: "skills", title: "Skills", categories: ["skills"] },
  { key: "disciplines", title: "Disciplines", categories: ["disciplines"] },
  { key: "merits", title: "Merits & flaws", categories: ["merits", "flaws"] },
  { key: "review", title: "Review", categories: [] },
];

function pool(over: Partial<PoolOut>): PoolOut {
  return { category: "disciplines", category_name: "Disciplines", rating: 1, kind: "picks", allowed: 1, used: 0, remaining: 1, restriction: null, options: null, without_dot: [], because: [], traits: [], ...over };
}

function trait(category: string, name: string, over: Partial<SheetTraitOut> = {}): SheetTraitOut {
  return { id: name, category, category_name: category, group: "", name, detail: "", rating: 1, free_rating: 1, min_rating: 0, pending_from: null, granted_rating: 0, granted_by: [], note: "", ...over };
}

function sheet(traits: SheetTraitOut[], problems: SheetOut["problems"] = []): SheetOut {
  return { traits, problems } as SheetOut;
}

const creation = (pools: PoolOut[], needs: CreationOut["needs"] = []): CreationOut => ({ complete: false, pools, needs, path_starts: [], budget_changes: [], given: [], clan_merits: [], rarity_known: false, shortfalls: [] });

describe("strayPicks", () => {
  it("marks a starting dot on a discipline that is no longer in-clan, on Concept and on Disciplines", () => {
    const pools = [pool({ rating: 2, restriction: "in_clan", traits: [{ name: "Celerity", detail: "", pick: 2, fits: false, because: [], freed_by: [] }] })];

    expect(strayPicks({ creation: creation(pools), sheet: sheet([]), steps: STEPS })).toEqual([
      {
        key: "stray/disciplines/Celerity/",
        message: "Your starting dots in Celerity need moving: it is no longer in-clan.",
        on: ["concept", "disciplines"],
        fix: "disciplines",
        trait: { category: "disciplines", name: "Celerity" },
      },
    ]);
  });

  it("names what leaves a discipline without a free dot, and sends the player to it", () => {
    const inept = { category: "flaws", name: "Inept" };
    const pools = [pool({ rating: 1, restriction: "in_clan", traits: [{ name: "Presence", detail: "", pick: 1, fits: false, because: [inept], freed_by: [] }] })];

    expect(strayPicks({ creation: creation(pools), sheet: sheet([]), steps: STEPS })).toEqual([
      {
        key: "stray/disciplines/Presence/",
        message: "Inept: Presence starts without a free dot, so your starting dot in it needs moving.",
        on: ["disciplines", "merits"],
        fix: "disciplines",
        trait: { category: "disciplines", name: "Presence" },
      },
    ]);
  });

  it("says nothing of picks that fit", () => {
    const pools = [pool({ restriction: "in_clan", traits: [{ name: "Auspex", detail: "", pick: 1, fits: true, because: [], freed_by: [] }] })];

    expect(strayPicks({ creation: creation(pools), sheet: sheet([]), steps: STEPS })).toEqual([]);
  });
});

describe("overBudget", () => {
  const thin = [{ category: "flaws", name: "Thin Blooded" }];

  it("keeps a dot at a rating the rules no longer give, and says what took it away", () => {
    const pools = [
      pool({ rating: 2, allowed: 0, used: 1, remaining: -1, because: thin, traits: [{ name: "Celerity", detail: "", pick: 2, fits: true, because: [], freed_by: [] }] }),
      pool({ rating: 1, allowed: 2, used: 2, remaining: 0 }),
    ];

    expect(overBudget({ creation: creation(pools), sheet: sheet([]), steps: STEPS })).toEqual([
      {
        key: "over/disciplines/2",
        message: "Thin Blooded: starting disciplines no longer have a pick at 2. Your dot in Celerity needs moving.",
        on: ["disciplines", "merits"],
        fix: "disciplines",
        trait: { category: "disciplines", name: "Celerity" },
      },
    ]);
  });

  it("counts the picks over at a rating that still has some", () => {
    const inept = [{ category: "flaws", name: "Inept" }];
    const pools = [pool({ rating: 1, allowed: 1, used: 2, remaining: -1, because: inept })];

    expect(overBudget({ creation: creation(pools), sheet: sheet([]), steps: STEPS })[0]?.message).toBe(
      "Inept: starting disciplines have 1 pick at 1 now, and 2 are placed. Take 1 back.",
    );
  });

  it("says to take a pick back where the category has none left (Stolen Potential's focus)", () => {
    const stolen = [{ category: "flaws", name: "Stolen Potential" }];
    const wits = { name: "Wits", detail: "", pick: 1, fits: true, because: [], freed_by: [] };
    const pools = [
      pool({ category: "focus_mentals", category_name: "Mental Focus", allowed: 0, used: 1, remaining: -1, because: stolen, traits: [wits] }),
      pool({ category: "focus_socials", category_name: "Social Focus", allowed: 1, used: 1, remaining: 0 }),
    ];
    const steps = [...STEPS.slice(0, 1), { key: "focuses", title: "Focuses", categories: ["focus_mentals", "focus_socials"] }, ...STEPS.slice(1)];

    expect(overBudget({ creation: creation(pools), sheet: sheet([]), steps })).toEqual([
      {
        key: "over/focus_mentals/1",
        message: "Stolen Potential: no starting mental focus. Take Wits back.",
        on: ["focuses", "merits"],
        fix: "focuses",
        trait: { category: "focus_mentals", name: "Wits" },
      },
    ]);
  });

  it("says nothing while every pick fits", () => {
    expect(overBudget({ creation: creation([pool({ remaining: 0 })]), sheet: sheet([]), steps: STEPS })).toEqual([]);
  });
});

describe("the Disciplines step", () => {
  const usual = [pool({ rating: 2, allowed: 1 }), pool({ rating: 1, allowed: 2 })];

  it("words the budget the pools give", () => {
    expect(disciplinesIntro(creation(usual))).toBe("Starting disciplines are your in-clan ones: one at 2 and two at 1.");
  });

  it("follows Thin Blooded's smaller budget, and says whose it is", () => {
    const thin = { ...creation([pool({ rating: 1, allowed: 2 })]), budget_changes: [{ category: "disciplines", because: [{ category: "flaws", name: "Thin Blooded" }] }] };

    expect(disciplinesIntro(thin)).toBe("Starting disciplines are your in-clan ones: two at 1 (Thin Blooded changes the usual).");
  });

  it("says why a discipline takes no free dot", () => {
    const pools = [pool({ restriction: "in_clan", without_dot: [{ name: "Presence", because: [{ category: "flaws", name: "Inept" }] }] })];

    expect(withoutDotReasons(creation(pools), "disciplines")).toEqual({ Presence: "Inept: Presence starts without a free dot." });
  });

  it("offers Inept the in-clan disciplines, and the one it names", () => {
    const pools = [pool({ restriction: "in_clan", options: ["Celerity", "Potence"] })];

    expect(ineptChoices(creation(pools))).toEqual(["Celerity", "Potence"]);
    expect(ineptChoices(creation(pools), "Presence")).toEqual(["Celerity", "Potence", "Presence"]);
  });
});

describe("brokenChecks", () => {
  const vestiges = {
    category: "merits",
    name: "Vestiges of Greatness",
    strength: "complete",
    message: "Vestiges of Greatness: choose one…",
    looks_at: [{ category: "extra_in_clan_disciplines", name: null }],
  };

  it("shows a check on the steps of what it is about and what it looks at, fixed on the earliest", () => {
    expect(brokenChecks({ creation: creation([]), sheet: sheet([], [vestiges]), steps: STEPS })).toEqual([
      { key: `check/${vestiges.message}`, message: vestiges.message, on: ["concept", "merits"], fix: "concept", inClan: true },
    ]);
  });

  it("marks only a check that wants an in-clan choice as one, for the steps that offer it to say so", () => {
    const clash = { category: "skills", name: "Archaic", strength: "refuse", message: "Archaic and Computer clash.", looks_at: [{ category: "skills", name: "Computer" }] };

    expect(brokenChecks({ creation: creation([]), sheet: sheet([], [clash]), steps: STEPS })[0]).not.toHaveProperty("inClan");
  });

  it("leaves a step's own need, and notes, to the step", () => {
    const generation = { category: "backgrounds", name: "Generation", strength: "complete", message: "Generation, please.", looks_at: [] };
    const skills = { ...generation, category: "skills", name: "Crafts" };
    const note = { ...vestiges, strength: "note" };
    const needs = [{ step: "skills", message: "Generation, please." }];

    expect(brokenChecks({ creation: creation([], needs), sheet: sheet([], [skills, note]), steps: STEPS })).toEqual([]);
  });
});

describe("inClanChoice", () => {
  const caitiff = trait("clan", "Caitiff", { rating: null });

  it("asks a Caitiff for three, and says so", () => {
    const choice = inClanChoice(sheet([caitiff, trait("extra_in_clan_disciplines", "Auspex")]));

    expect(choice.chooses).toBe(3);
    expect(choice.chosen.map((t) => t.name)).toEqual(["Auspex"]);
    expect(choice.lines).toEqual(["Caitiff choose their three in-clan disciplines from the common ones."]);
  });

  it("follows Vestiges of Greatness", () => {
    const choice = inClanChoice(sheet([caitiff, trait("merits", "Vestiges of Greatness", { rating: 3 })]));

    expect(choice.lines).toEqual(["Two from the common ones and one from the uncommon ones (Vestiges of Greatness)."]);
  });

  it("gives any clan one with a merit that adds one, and counts a given one as held", () => {
    const choice = inClanChoice(
      sheet([
        trait("clan", "Brujah", { rating: null }),
        trait("merits", "Additional Uncommon Discipline", { rating: 5 }),
        trait("extra_in_clan_disciplines", "Potence", { granted_rating: 1, granted_by: ["Strength of Honor"] }),
      ]),
    );

    expect(choice.chooses).toBe(1);
    expect(choice.chosen).toEqual([]);
    expect(choice.given.map((t) => t.name)).toEqual(["Potence"]);
    expect(choice.lines).toEqual(["One extra in-clan discipline from the uncommon ones (Additional Uncommon Discipline)."]);
  });

  it("asks nothing of a clan without such a merit", () => {
    expect(inClanChoice(sheet([trait("clan", "Brujah", { rating: null })])).chooses).toBe(0);
  });
});

describe("inClanChoices", () => {
  it("asks for the one a merit adds on Concept and on Merits", () => {
    const traits = [trait("clan", "Brujah", { rating: null }), trait("merits", "Additional Uncommon Discipline", { rating: 5 })];

    expect(inClanChoices({ creation: creation([]), sheet: sheet(traits), steps: STEPS })).toEqual([
      { key: "in-clan/choose", message: "Additional Uncommon Discipline: choose the in-clan discipline it adds.", on: ["concept", "merits"], fix: "concept", inClan: true },
    ]);
  });

  it("counts what a Caitiff has left to choose", () => {
    const traits = [trait("clan", "Caitiff", { rating: null }), trait("extra_in_clan_disciplines", "Auspex")];

    expect(inClanChoices({ creation: creation([]), sheet: sheet(traits), steps: STEPS })[0]?.message).toBe("Choose 2 more in-clan disciplines.");
  });
});

describe("the in-clan picker", () => {
  const COMMON = ["Animalism", "Auspex", "Celerity", "Dominate", "Fortitude", "Obfuscate", "Potence", "Presence"];
  const UNCOMMON = ["Chimerstry", "Dementation", "Obtenebration", "Protean", "Quietus", "Serpentis", "Vicissitude"];
  const INCEPTOR = ["Kineticism", "Necromancy: Mortis Path", "Thaumaturgy: Path of Blood"];
  const ALL = [...COMMON, ...UNCOMMON, ...INCEPTOR, "Spiritus"];
  /** What the server bars whatever is chosen: all but `open`. */
  const barredBut = (open: string[]) => Object.fromEntries(ALL.filter((n) => !open.includes(n)).map((n) => [n, "Not from its list."]));
  /** What it refuses as things stand: each one not held, for `why`. */
  const refusedAll = (held: string[], why: string) => Object.fromEntries(ALL.filter((n) => !held.includes(n)).map((n) => [n, why]));
  const caitiff = trait("clan", "Caitiff", { rating: null });
  const chosen = (...names: string[]) => names.map((n) => trait("extra_in_clan_disciplines", n));
  const three = ["Celerity", "Fortitude", "Obfuscate"];

  it("with Vestiges and three common chosen, shows the uncommon ones, with swaps", () => {
    const choice = inClanChoice(sheet([caitiff, trait("merits", "Vestiges of Greatness", { rating: 3 }), ...chosen(...three)]));
    const options = inClanOptions(ALL, choice, barredBut([...COMMON, ...UNCOMMON]));

    expect(options).toEqual(expect.arrayContaining(UNCOMMON));
    expect(options).not.toContain("Kineticism");
    expect(`${choice.chosen.length} of ${choice.chooses}`).toBe("3 of 3");
    const refused = refusedAll(three, "Caitiff choose three in-clan disciplines. (p. 246)");
    expect(UNCOMMON.map((n) => whenTapped(n, refused))).toEqual(UNCOMMON.map(() => "swap"));
  });

  it("with Inceptor and three chosen, shows Kineticism and the paths, with swaps", () => {
    const choice = inClanChoice(sheet([caitiff, trait("merits", "Inceptor", { rating: 3 }), ...chosen(...three)]));
    const options = inClanOptions(ALL, choice, barredBut([...COMMON, ...INCEPTOR]));

    expect(options).toEqual(expect.arrayContaining(INCEPTOR));
    expect(options).not.toContain("Protean");
    expect(choice.lines).toContain("One of them can be Kineticism, or one path of Thaumaturgy or Necromancy (Inceptor).");
    expect(whenTapped("Kineticism", refusedAll(three, "Caitiff choose three in-clan disciplines. (p. 246)"))).toBe("swap");
  });

  it.each([
    ["Additional Common Discipline", COMMON],
    ["Additional Uncommon Discipline", ["Protean", "Dementation", "Serpentis", "Quietus"]],
    ["Pliable Blood", ["Auspex", "Celerity", "Dementation", "Dominate", "Fortitude", "Presence", "Protean", "Quietus", "Serpentis"]],
  ])("with %s, opens one more slot, empty, with only its list", (merit, list) => {
    const brujah = inClanChoice(sheet([trait("clan", "Brujah", { rating: null }), trait("merits", merit, { rating: 4 })]));
    expect(`${brujah.chosen.length} of ${brujah.chooses}`).toBe("0 of 1");
    expect(inClanOptions(ALL, brujah, barredBut(list)).sort()).toEqual([...list].sort());
    // Chosen straight away: nothing refuses it as things stand.
    expect(whenTapped(list[0]!, {})).toBe("choose");

    const fourth = inClanChoice(sheet([caitiff, trait("merits", merit, { rating: 4 }), ...chosen(...three)]));
    expect(`${fourth.chosen.length} of ${fourth.chooses}`).toBe("3 of 4");
  });

  it("with a troupe's own merit that adds one, opens one more slot and says its list", () => {
    const house = {
      house_trait_id: "h",
      troupe_id: "t",
      troupe_name: "Night Court",
      label: "House merit of Night Court",
      page: "House rule — Night Court",
      availability: "building",
      archived: false,
      summary: "Adds one in-clan discipline, chosen from Auspex or Presence.",
      in_clan: ["Auspex", "Presence"],
    };
    const brujah = inClanChoice(sheet([trait("clan", "Brujah", { rating: null }), trait("merits", "Wide Blood", { rating: 3, house })]));
    expect(`${brujah.chosen.length} of ${brujah.chooses}`).toBe("0 of 1");
    expect(brujah.adding).toBe("Wide Blood");
    expect(brujah.lines).toEqual(["One extra in-clan discipline from Auspex or Presence (Wide Blood)."]);
  });

  it("with Bonds of Stolen Vitae, shows the one its detail chose as held", () => {
    const bonds = trait("extra_in_clan_disciplines", "Protean", { granted_rating: 1, granted_by: ["Bonds of Stolen Vitae"] });
    const choice = inClanChoice(sheet([trait("clan", "Gargoyles", { rating: null }), trait("merits", "Bonds of Stolen Vitae", { rating: 2, detail: "Protean" }), bonds]));

    expect(choice.given.map((t) => t.name)).toEqual(["Protean"]);
    expect(inClanOptions(ALL, choice, barredBut([]))).toEqual(["Protean"]);
  });

  it("with one uncommon chosen under Vestiges, offers a swap for the others, which the server refuses but in its place", () => {
    const held = ["Celerity", "Fortitude", "Protean"];
    const choice = inClanChoice(sheet([caitiff, trait("merits", "Vestiges of Greatness", { rating: 3 }), ...chosen(...held)]));
    const refused = refusedAll(held, "Vestiges of Greatness gives one in-clan discipline from the uncommon list, not more. (p. 246)");

    expect(inClanOptions(ALL, choice, barredBut([...COMMON, ...UNCOMMON]))).toContain("Dementation");
    expect(whenTapped("Dementation", refused)).toBe("swap");
  });
});

describe("inClanChoices, with the merit's own check", () => {
  it("leaves the notice to the check, which has the page", () => {
    const traits = [trait("clan", "Brujah", { rating: null }), trait("merits", "Additional Uncommon Discipline", { rating: 5 })];
    const check = {
      category: "merits",
      name: "Additional Uncommon Discipline",
      strength: "complete",
      message: "Additional Uncommon Discipline: choose the in-clan discipline it adds. (p. 248)",
      looks_at: [{ category: "extra_in_clan_disciplines", name: null }],
    };
    const input = { creation: creation([]), sheet: sheet(traits, [check]), steps: STEPS };

    expect(inClanChoices(input)).toEqual([]);
    expect(stepNotices(input, [inClanChoices, brokenChecks]).map((n) => [n.message, n.on, n.fix])).toEqual([[check.message, ["concept", "merits"], "concept"]]);
  });
});

describe("stepNotices", () => {
  it("gives each message once", () => {
    const twice = () => [{ key: "a", message: "Same.", on: ["concept"], fix: "concept" }];

    expect(stepNotices({ creation: creation([]), sheet: sheet([]), steps: STEPS }, [twice, twice])).toHaveLength(1);
  });
});

describe("inClanOpen", () => {
  const caitiff = trait("clan", "Caitiff", { rating: null });
  const three = ["Celerity", "Fortitude", "Obfuscate"].map((n) => trait("extra_in_clan_disciplines", n));
  const vestiges = trait("merits", "Vestiges of Greatness", { rating: 3 });
  const wantsUncommon = {
    category: "merits",
    name: "Vestiges of Greatness",
    strength: "complete",
    message: "Vestiges of Greatness: choose one…",
    looks_at: [{ category: "extra_in_clan_disciplines", name: null }],
  };

  it("is open while a Caitiff has fewer than three", () => {
    expect(inClanOpen(sheet([caitiff, ...three.slice(0, 2)]))).toBe(true);
    expect(inClanOpen(sheet([caitiff, ...three]))).toBe(false);
  });

  it("is open with three common ones under Vestiges of Greatness, until one is from the uncommon list", () => {
    expect(inClanOpen(sheet([caitiff, ...three, vestiges], [wantsUncommon]))).toBe(true);
    expect(inClanOpen(sheet([caitiff, ...three.slice(0, 2), trait("extra_in_clan_disciplines", "Protean"), vestiges]))).toBe(false);
  });

  it("is open while a merit's extra one is not chosen", () => {
    const brujah = trait("clan", "Brujah", { rating: null });
    expect(inClanOpen(sheet([brujah, trait("merits", "Additional Uncommon Discipline", { rating: 5 })]))).toBe(true);
  });

  it("is not open for another merit's check", () => {
    const other = { ...wantsUncommon, name: "Versatile" };
    expect(inClanOpen(sheet([caitiff, ...three, trait("merits", "Versatile")], [other]))).toBe(false);
  });
});

describe("makesInClanChoice", () => {
  it("knows the book's merits, and a troupe's own that adds an in-clan discipline", () => {
    expect(["Vestiges of Greatness", "Inceptor", "Additional Common Discipline", "Additional Uncommon Discipline", "Pliable Blood", "Bonds of Stolen Vitae"].every((name) => makesInClanChoice({ name }))).toBe(true);
    expect(makesInClanChoice({ name: "Blood of the Moon", house: { in_clan: ["Protean"] } })).toBe(true);
    expect(makesInClanChoice({ name: "Versatile" })).toBe(false);
  });
});

describe("sheetKey", () => {
  it("changes when a merit is taken, and not when the same traits come back in another order", () => {
    const a = [trait("clan", "Caitiff", { rating: null }), trait("extra_in_clan_disciplines", "Celerity")];
    const before = sheetKey(sheet(a));

    expect(sheetKey(sheet([...a].reverse()))).toBe(before);
    expect(sheetKey(sheet([...a, trait("merits", "Vestiges of Greatness", { rating: 3 })]))).not.toBe(before);
    expect(sheetKey(sheet([a[0]!, trait("extra_in_clan_disciplines", "Celerity", { rating: 0 })]))).not.toBe(before);
  });
});

describe("strayMoves", () => {
  const picked = (name: string, pick: number, fits = true, because: { category: string; name: string }[] = []) => ({ name, detail: "", pick, fits, because, freed_by: [] });

  it("offers the dot on a discipline swapped out to the in-clan one with none", () => {
    const options = ["Celerity", "Fortitude", "Protean"];
    const pools = [
      pool({ rating: 2, allowed: 1, restriction: "in_clan", options, traits: [picked("Celerity", 2)] }),
      pool({ rating: 1, allowed: 2, restriction: "in_clan", options, traits: [picked("Fortitude", 1), picked("Obfuscate", 1, false)] }),
    ];

    expect(strayMoves(creation(pools))).toEqual([{ from: "Obfuscate", rating: 1, to: ["Protean"] }]);
  });

  it("leaves a dot that Inept takes the free dot from to be placed by hand", () => {
    const inept = { category: "flaws", name: "Inept" };
    const pools = [pool({ rating: 1, restriction: "in_clan", options: ["Auspex"], traits: [picked("Presence", 1, false, [inept])] })];

    expect(strayMoves(creation(pools))).toEqual([]);
  });

  it("does not offer a discipline that takes no free dot", () => {
    const pools = [
      pool({
        rating: 1,
        restriction: "in_clan",
        options: ["Auspex", "Protean"],
        without_dot: [{ name: "Protean", because: [] }],
        traits: [picked("Obfuscate", 1, false)],
      }),
    ];

    expect(strayMoves(creation(pools))).toEqual([{ from: "Obfuscate", rating: 1, to: ["Auspex"] }]);
  });
});

describe("movePick", () => {
  it("moves the pick to the new discipline at its rating", () => {
    expect(movePick({ Celerity: 2, Fortitude: 1, Obfuscate: 1 }, "Obfuscate", "Protean")).toEqual({ Celerity: 2, Fortitude: 1, Protean: 1 });
  });

  it("leaves the picks alone if there is nothing to move, or the new one has a pick", () => {
    const picks = { Celerity: 2, Fortitude: 1 };
    expect(movePick(picks, "Obfuscate", "Protean")).toBe(picks);
    expect(movePick(picks, "Celerity", "Fortitude")).toBe(picks);
  });
});

describe("clanChoiceNeeded", () => {
  const angelis = (chosen: string | null): CreationOut => ({
    ...creation([]),
    clan_choice: { clan: "Baali: Angelis Ater", choices: ["Potence", "Presence", "Obfuscate"], chosen, page: "72" },
  });

  it("asks for the clan's own in-clan choice on Concept and Disciplines (#312)", () => {
    expect(clanChoiceNeeded({ creation: angelis(null), sheet: sheet([]), steps: STEPS })).toEqual([
      {
        key: "in-clan/clan",
        message: "Baali: Angelis Ater: choose one more in-clan discipline, Potence, Presence or Obfuscate (p. 72).",
        on: ["concept", "disciplines"],
        fix: "concept",
        inClan: true,
      },
    ]);
  });

  it("says nothing once chosen, for a clan without one, or for a ghoul", () => {
    expect(clanChoiceNeeded({ creation: angelis("Presence"), sheet: sheet([]), steps: STEPS })).toEqual([]);
    expect(clanChoiceNeeded({ creation: creation([]), sheet: sheet([]), steps: STEPS })).toEqual([]);
    expect(clanChoiceNeeded({ creation: angelis(null), sheet: sheet([]), steps: STEPS, ghoul: { domitor: true } })).toEqual([]);
  });
});

describe("inClanShortfalls", () => {
  const short = { category: "disciplines", restriction: "in_clan", picks: 3, options: ["Auspex", "Fortitude"], message: "Only 2 in-clan disciplines for 3 starting picks: Valeran is not a discipline Horatio has. Ask your storyteller." };

  it("says on Disciplines why its picks cannot all be placed (#312)", () => {
    const found = inClanShortfalls({ creation: { ...creation([]), shortfalls: [short] }, sheet: sheet([trait("clan", "Salubri", { rating: null })]), steps: STEPS });
    expect(found).toEqual([{ key: "short/disciplines/in_clan", message: short.message, on: ["disciplines"], fix: "disciplines" }]);
  });

  it("leaves it to the in-clan choice while one is open: making it fills the picks", () => {
    const caitiff = sheet([trait("clan", "Caitiff", { rating: null })]);
    expect(inClanShortfalls({ creation: { ...creation([]), shortfalls: [short] }, sheet: caitiff, steps: STEPS })).toEqual([]);
    const angelis = { ...creation([]), shortfalls: [short], clan_choice: { clan: "Baali: Angelis Ater", choices: ["Potence"], chosen: null, page: null } };
    expect(inClanShortfalls({ creation: angelis, sheet: sheet([]), steps: STEPS })).toEqual([]);
  });
});

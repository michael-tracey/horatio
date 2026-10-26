import { describe, expect, it } from "vitest";
import { balanceText, choicesBody, dotsBoughtBack, fromRemoveKey, newDraft, ordinal, removeKey, running, sireMissing, xpText } from "./embrace";

const step = (key: string, xp: number) => ({ key, title: key, lines: [], xp });

describe("a ghoul's Embrace, as the form holds it", () => {
  it("needs a sire with a generation", () => {
    expect(sireMissing({ kind: "linked", choice: null })).toBe("Choose the sire.");
    expect(sireMissing({ kind: "linked", choice: { character_id: "v", name: "Vasquez", kind: "pc", clan: "Toreador", generation: null } })).toMatch(/no generation/);
    expect(sireMissing({ kind: "named", name: "Doctor Mirth", clan: "Malkavian", generation: null })).toBe("Give the sire's generation.");
    expect(sireMissing({ kind: "named", name: "Doctor Mirth", clan: "Malkavian", generation: 10 })).toBeNull();
  });

  it("sends the choices the server plans by", () => {
    const draft = {
      ...newDraft(),
      sire: { kind: "named" as const, name: " Doctor Mirth ", clan: "Malkavian", generation: 10 },
      remove: [removeKey({ category: "merits", name: "Code of Honor", detail: "" })],
      buyBack: { Quietus: 2, Auspex: 0 },
      intoDebt: true,
    };
    expect(choicesBody(draft)).toEqual({
      sire: { character_id: null, name: "Doctor Mirth", clan: "Malkavian", generation: 10 },
      sire_is_domitor: null,
      clan_merits: null,
      two_dots: null,
      caitiff_three: [],
      remove: [{ category: "merits", name: "Code of Honor", detail: "" }],
      buy_back: [{ name: "Quietus", rating: 2 }],
      buy_back_into_debt: true,
      weakness: "",
    });
    expect(fromRemoveKey("flaws/Derangement/Paranoia/Fear")).toEqual({ category: "flaws", name: "Derangement", detail: "Paranoia/Fear" });
  });

  it("counts the lost dots bought back over the starting ones", () => {
    const plan = { disciplines: [{ name: "Auspex", rating: 2, detail: "" }] };
    expect(dotsBoughtBack({ Auspex: 3, Quietus: 2 }, plan)).toBe(3);
    expect(dotsBoughtBack({ Auspex: 2 }, plan)).toBe(0);
  });

  it("follows the XP step by step, into debt", () => {
    // Vivian (p. 299): 2 back, 1 for Generation, 2 back, 12 for Quietus.
    const plan = { balance_before: 0, steps: [step("clan", 2), step("generation", -1), step("finishing", 2), step("debt", -12)] };
    expect(running(plan).map((r) => r.after)).toEqual([2, 1, 3, -9]);
    expect(balanceText(-9)).toBe("9 XP owed");
    expect(balanceText(3)).toBe("3 XP");
    expect([xpText(2), xpText(-12), xpText(0)]).toEqual(["+2 XP", "−12 XP", ""]);
    expect([ordinal(11), ordinal(12), ordinal(21), ordinal(13)]).toEqual(["11th", "12th", "21st", "13th"]);
  });
});

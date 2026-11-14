import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PlayReference } from "../../api/types";
import { PoolRow, SheetTab } from "./ReferenceTabs";

afterEach(cleanup);

type Trait = PlayReference["traits"][number];

function trait(category: string, category_name: string, group: string, name: string, more: Partial<Trait> = {}): Trait {
  return { category, category_name, group, name, detail: "", rating: 1, specialties: [], note: "", wording: "", wording_mode: "added", granted_by: [], ...more };
}

const reference: PlayReference = {
  pools: [],
  frenzy: { parts: [{ label: "Mental", value: 3 }], beast: [], switched_beast: [] },
  other_powers: [],
  notes: [],
  blood_per_turn: 1,
  retainers: [],
  identities: [],
  backgrounds_changed: [],
  bonds: [],
  vinculum: [],
  traits: [
    trait("archetype", "Archetype", "Identity", "Loner", { rating: null, description: "You'd rather work alone." }),
    trait("attributes", "Attributes", "Attributes", "Physical", { rating: 5, description: "Strength, speed and toughness." }),
    trait("focus_physicals", "Physical Focus", "Attributes", "Stamina", { rating: null, description: "Toughness and endurance." }),
    trait("skills", "Skills", "Skills", "Brawl", { rating: 2, description: "Fighting with your body.", page_reference: "93" }),
    trait("skills", "Skills", "Skills", "Dodge", { rating: 1, description: "Getting out of the way.", wording: "Only once a round here.", wording_mode: "replaces" }),
    trait("status_traits", "Sect Status", "Backgrounds", "Acclaimed", { rating: null }),
    trait("disciplines", "Disciplines", "Disciplines", "Celerity", { rating: 1, description: "Supernatural speed." }),
  ],
  disciplines: [
    {
      name: "Celerity",
      rating: 1,
      pool: null,
      versus: null,
      note: "Speed, in steps and actions.",
      focus: null,
      switches: [],
      powers: [{ level: 1, name: "Alacrity", note: "Win ties on initiative.", focus: null, switches: [], uses: [] }],
    },
  ],
};

function sheet(shown: PlayReference = reference) {
  const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  render(
    <QueryClientProvider client={client}>
      <SheetTab reference={shown} />
    </QueryClientProvider>,
  );
}

describe("SheetTab", () => {
  it("shows a background raised for the month from a downtime", () => {
    const crafts = { source: "crafts", delta: 1, starts_at: "2026-11-07T12:00:00Z", ends_at: null, games_left: 0 };
    sheet({ ...reference, backgrounds_changed: [{ trait: "Resources", rating: 2, now: 3, changes: [crafts] }] });
    expect(screen.getByText("Resources 3 (+1 this month, Crafts)")).toBeTruthy();
  });

  it("shows the blood bonds the character feels, with what each does at a game (#664)", () => {
    const full = { regnant: "Bram", level: 3, drinks: "Full bond", effects: ["Resisting Bram's powers: −3 to Social and Mental defence."] };
    sheet({ ...reference, bonds: [full] });
    expect(screen.getByText("Blood bonds")).toBeTruthy();
    expect(screen.getByText("Bram")).toBeTruthy();
    expect(screen.getByText("· Full bond")).toBeTruthy();
    expect(screen.getByText("Resisting Bram's powers: −3 to Social and Mental defence.")).toBeTruthy();
  });

  it("has no blood bonds panel without one", () => {
    sheet();
    expect(screen.queryByText("Blood bonds")).toBeNull();
  });

  it("shows the Vinculum ratings with a rules effect, and what each costs (#666)", () => {
    sheet({ ...reference, vinculum: [{ toward: "Ezra", rating: 2, effects: ["Killing Ezra costs 1 Willpower (p. 434)."] }] });
    expect(screen.getByText("Vinculum")).toBeTruthy();
    expect(screen.getByText("· Vinculum 2")).toBeTruthy();
    expect(screen.getByText("Killing Ezra costs 1 Willpower (p. 434).")).toBeTruthy();
  });

  it("has no Vinculum panel without one, or from an older copy kept offline", () => {
    sheet();
    expect(screen.queryByText("Vinculum")).toBeNull();
    const older: Partial<PlayReference> = { ...reference };
    delete older.vinculum;
    sheet(older as PlayReference);
    expect(screen.queryByText("Vinculum")).toBeNull();
  });

  it("gives a chevron only to a trait with something to say", () => {
    sheet();
    expect(screen.getByRole("button", { name: "Brawl" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Acclaimed" })).toBeNull();
    expect(screen.getByText("Acclaimed")).toBeTruthy();
  });

  it("opens a skill to what it does and its page", () => {
    sheet();
    fireEvent.click(screen.getByRole("button", { name: "Brawl" }));
    expect(screen.getByText("Fighting with your body.")).toBeTruthy();
    expect(screen.getByText("MET: VTM p. 93")).toBeTruthy();
  });

  it("opens an attribute to what its focuses add, and a discipline to its powers", () => {
    sheet();
    fireEvent.click(screen.getByRole("button", { name: /^Physical/ }));
    expect(screen.getByText("Toughness and endurance.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Celerity" }));
    expect(screen.getByText("Speed, in steps and actions.")).toBeTruthy();
    expect(screen.getByText("Alacrity")).toBeTruthy();
    expect(screen.queryByText("Supernatural speed.")).toBeNull();
  });

  it("says what gives a focus the character has from a power (#598)", () => {
    const given = trait("focus_physicals", "Physical Focus", "Attributes", "Dexterity", {
      rating: 1,
      description: "Speed and precision.",
      granted_by: ["Vicissitude: Azhi Dahaka"],
    });
    sheet({ ...reference, traits: [...reference.traits, given] });
    expect(screen.getByText("(Stamina, Dexterity)", { exact: false })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^Physical/ }));
    const line = screen.getByText("Speed and precision.", { exact: false });
    expect(line.textContent).toBe("Dexterity (from Vicissitude: Azhi Dahaka): Speed and precision.");
    // The character's own focus says nothing more.
    expect(screen.getByText("Toughness and endurance.", { exact: false }).textContent).toBe("Stamina: Toughness and endurance.");
  });

  it("opens a trait to the troupe's wording, marked as the troupe's, in place of the book's", () => {
    sheet();
    fireEvent.click(screen.getByRole("button", { name: "Dodge" }));
    expect(screen.getByText("House rule, in place of the book's")).toBeTruthy();
    expect(screen.getByText("Only once a round here.")).toBeTruthy();
    expect(screen.queryByText("Getting out of the way.")).toBeNull();
  });

  it("leaves the archetype to the subheader", () => {
    sheet();
    expect(screen.queryByText("Loner")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Archetype" })).toBeNull();
  });
});

describe("PoolRow", () => {
  const damage = { kind: "power", type: "aggravated" as const, parts: [{ label: "Scourge of Arikel", value: 3 }], total: 3, exceptional: 0, notes: [], switched: [], reducible: true };
  const pool = { key: "power:Scourge of Arikel", name: "Scourge of Arikel", group: "Combat", parts: [], total: 0, versus: null, adds_willpower: false, willpower_floor: 0, variants: [], notes: [], switched: [], switch: "Scourge of Arikel", damage };

  it("shows a power's damage with the challenge it comes from where it has no pool of its own", () => {
    render(
      <ul>
        <PoolRow pool={{ ...pool, challenge: "Any Social challenge you win" }} willpower={0} modifiers={[]} on={["Scourge of Arikel"]} />
      </ul>,
    );
    expect(screen.getByText("Any Social challenge you win")).toBeTruthy();
    expect(screen.getByText("Aggravated damage 3 · exceptional 3")).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("shows a power's pool, what it is against and the damage nothing reduces", () => {
    const assault = { ...pool, key: "power:Psychic Assault", name: "Psychic Assault", parts: [{ label: "Mental", value: 5 }, { label: "Investigation", value: 3 }], total: 8, versus: "Mental + Willpower", damage: { ...damage, type: "normal" as const, total: 4, exceptional: 1, reducible: false } };
    render(
      <ul>
        <PoolRow pool={assault} willpower={0} modifiers={[]} on={["Psychic Assault"]} />
      </ul>,
    );
    expect(screen.getByText("8")).toBeTruthy();
    expect(screen.getByText(/Mental 5 \+ Investigation 3/).textContent).toBe("Mental 5 + Investigation 3 · against Mental + Willpower");
    expect(screen.getByText("Damage 4, nothing reduces it · exceptional 5")).toBeTruthy();
  });

  it("shows an attack against the hunted target, with Brutal, only while Killer Instincts is on (#613)", () => {
    const brawl = {
      ...pool,
      key: "attack:Brawl",
      name: "Unarmed attack",
      switch: null,
      parts: [{ label: "Physical", value: 5 }, { label: "Brawl", value: 3 }],
      total: 8,
      versus: "Physical + Dodge",
      damage: { ...damage, kind: "unarmed", type: "normal" as const, parts: [{ label: "unarmed", value: 1 }], total: 1, exceptional: 1 },
      variants: [{ when: "Against your hunted target", total: 10, parts: [{ label: "Accurate", value: 2 }], instead: false, tracked: [], switch: "Killer Instincts", qualities: [{ name: "Brutal", play: "Win on the larger pool: exceptional success", page: "p. 516" }] }],
    };
    const { rerender } = render(
      <ul>
        <PoolRow pool={brawl} willpower={0} modifiers={[]} on={[]} />
      </ul>,
    );
    expect(screen.getByText("8")).toBeTruthy();
    expect(screen.queryByText(/hunted target/)).toBeNull();
    rerender(
      <ul>
        <PoolRow pool={brawl} willpower={0} modifiers={[]} on={["Killer Instincts"]} />
      </ul>,
    );
    expect(screen.getByText("8")).toBeTruthy();
    expect(screen.getByText(/Against your hunted target/).textContent).toBe("Against your hunted target (+2 Accurate), Brutal");
    expect(screen.getByText("10")).toBeTruthy();
    expect(screen.getByText("Brutal: win on the larger pool: exceptional success (p. 516)")).toBeTruthy();
  });

  it("shows a line against a blood bond's regnant, always, under the defence it lowers (#664)", () => {
    const social = {
      ...pool,
      key: "defense:Social",
      name: "Resisting Social powers",
      switch: null,
      parts: [{ label: "Social", value: 4 }],
      total: 4,
      versus: null,
      damage: null,
      variants: [{ when: "Against Bram's powers", total: 3, parts: [{ label: "Blood bond", value: -1 }], instead: false, tracked: [], switch: null, qualities: [] }],
    };
    render(
      <ul>
        <PoolRow pool={social} willpower={0} modifiers={[]} on={[]} />
      </ul>,
    );
    expect(screen.getByText("4")).toBeTruthy();
    expect(screen.getByText(/Against Bram's powers/).textContent).toBe("Against Bram's powers (−1 Blood bond)");
    expect(screen.getByText("3")).toBeTruthy();
  });

  it("has a Throw button that takes the pool, its total and its parts to the Throws tab (#698)", () => {
    const onThrow = vi.fn();
    const dodge = { ...pool, key: "dodge", name: "Dodge", switch: null, damage: null, parts: [{ label: "Physical", value: 4 }, { label: "Dodge", value: 2 }], total: 6 };
    render(
      <ul>
        <PoolRow pool={dodge} willpower={0} modifiers={[]} on={[]} onThrow={onThrow} />
        <PoolRow pool={{ ...dodge, key: "initiative", name: "Initiative", parts: [{ label: "Physical", value: 4 }], total: 4 }} willpower={0} modifiers={[]} on={[]} onThrow={onThrow} />
      </ul>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Throw Dodge" }));
    expect(onThrow).toHaveBeenCalledWith(dodge, 6, "Physical 4 + Dodge 2");
    // Initiative sets who acts first; it is never thrown.
    expect(screen.queryByRole("button", { name: "Throw Initiative" })).toBeNull();
  });

  it("has no Throw button where the troupe has the Throws tab off", () => {
    render(
      <ul>
        <PoolRow pool={{ ...pool, key: "dodge", name: "Dodge", switch: null, damage: null, parts: [{ label: "Physical", value: 4 }], total: 4 }} willpower={0} modifiers={[]} on={[]} />
      </ul>,
    );
    expect(screen.queryByRole("button", { name: /^Throw/ })).toBeNull();
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { PlayReference } from "../../api/types";
import { SheetTab } from "./ReferenceTabs";

afterEach(cleanup);

type Trait = PlayReference["traits"][number];

function trait(category: string, category_name: string, group: string, name: string, more: Partial<Trait> = {}): Trait {
  return { category, category_name, group, name, detail: "", rating: 1, specialties: [], note: "", ...more };
}

const reference: PlayReference = {
  pools: [],
  other_powers: [],
  notes: [],
  blood_per_turn: 1,
  retainers: [],
  identities: [],
  traits: [
    trait("archetype", "Archetype", "Identity", "Loner", { rating: null, description: "You'd rather work alone." }),
    trait("attributes", "Attributes", "Attributes", "Physical", { rating: 5, description: "Strength, speed and toughness." }),
    trait("focus_physicals", "Physical Focus", "Attributes", "Stamina", { rating: null, description: "Toughness and endurance." }),
    trait("skills", "Skills", "Skills", "Brawl", { rating: 2, description: "Fighting with your body.", page_reference: "93" }),
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
      powers: [{ level: 1, name: "Alacrity", note: "Win ties on initiative.", focus: null }],
    },
  ],
};

function sheet() {
  const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  render(
    <QueryClientProvider client={client}>
      <SheetTab reference={reference} />
    </QueryClientProvider>,
  );
}

describe("SheetTab", () => {
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

  it("leaves the archetype to the subheader", () => {
    sheet();
    expect(screen.queryByText("Loner")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Archetype" })).toBeNull();
  });
});

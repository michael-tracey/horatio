import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { TroupeOut } from "../../api/types";
import { FeaturesList } from "./FeaturesList";
import { features, type FeatureKey } from "./features";

afterEach(cleanup);

// The fields the Features list reads, everything off as a new troupe has it (feeding is on by default).
const TROUPE = {
  id: "t1",
  archived: false,
  whos_who: true,
  boons: false,
  blood_bonds: "off",
  player_nominations: false,
  remembrances: false,
  nominations: false,
  court_history_players: false,
  chronicle_players: false,
  quests_enabled: false,
  quest_requests_per_cycle: 1,
  feeding: "book",
  feeding_resonance: false,
  feeding_territories: false,
  feeding_rack: false,
  golconda_enlightened: false,
  items_expire: false,
  play_tabs_off: [],
} as unknown as TroupeOut;

// Every feature with a switch: the list is the one place each is switched (#784), so one missing fails here.
const SWITCHED: FeatureKey[] = [
  "boons",
  "blood_bonds",
  "nominations",
  "remembrances",
  "court_history",
  "chronicle",
  "quests",
  "feeding",
  "golconda",
  "item_expiry",
];

function show(troupe: TroupeOut, canEdit: boolean) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, enabled: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <FeaturesList troupe={troupe} canEdit={canEdit} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return within(screen.getByRole("list", { name: "Features" }));
}

describe("the Features list (#783)", () => {
  it("lists every feature once, and every feature switch once", () => {
    const keys = features(TROUPE).map((f) => f.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(
      features(TROUPE)
        .filter((f) => f.switchable)
        .map((f) => f.key),
    ).toEqual(SWITCHED);

    const list = show(TROUPE, true);
    expect(list.getAllByRole("listitem")).toHaveLength(keys.length);
    for (const f of features(TROUPE)) {
      const row = within(list.getByRole("listitem", { name: f.name }));
      expect(row.queryAllByRole("switch")).toHaveLength(f.switchable ? 1 : 0);
    }
    expect(list.getAllByRole("switch")).toHaveLength(SWITCHED.length);
  });

  it("shows each switch as it is, and its tab only once it's on", () => {
    let list = show(TROUPE, true);
    expect(list.getByRole("switch", { name: "Boons" }).getAttribute("aria-checked")).toBe("false");
    expect(list.queryByRole("link", { name: "Open Boons" })).toBeNull();
    expect(list.getByRole("switch", { name: "Feeding" }).getAttribute("aria-checked")).toBe("true");
    cleanup();

    list = show(
      {
        ...TROUPE,
        boons: true,
        blood_bonds: "players_manage",
        player_nominations: true,
        nominations: true,
      },
      true,
    );
    expect(list.getByRole("switch", { name: "Boons" }).getAttribute("aria-checked")).toBe("true");
    expect(list.getByRole("link", { name: "Open Boons" }).getAttribute("href")).toBe("/troupes/t1/boons");
    expect(within(list.getByRole("listitem", { name: "Blood bonds" })).getByText("Players manage")).toBeTruthy();
    // A feature with a tab of its own keeps its settings folded at the top of that tab (#784).
    expect(list.getByRole("link", { name: "Settings for Boons" }).getAttribute("href")).toBe("/troupes/t1/boons#settings");
    expect(list.getByRole("link", { name: "Settings for Feeding" }).getAttribute("href")).toBe("#feature-feeding");
    expect(list.getAllByRole("link", { name: "Open Nominations" })).toHaveLength(1);
  });

  it("has no switches for those who may only read the settings, nor links to settings only storytellers see", () => {
    const list = show({ ...TROUPE, boons: true }, false);
    expect(list.queryAllByRole("switch")).toHaveLength(0);
    expect(list.getAllByRole("listitem")).toHaveLength(features(TROUPE).length);
    expect(list.getByRole("link", { name: "Open Boons" })).toBeTruthy();
    expect(list.queryByRole("link", { name: "Settings for Boons" })).toBeNull();
    expect(list.getByRole("link", { name: "Settings for Feeding" })).toBeTruthy();
  });
});

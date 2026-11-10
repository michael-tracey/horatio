import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { CharacterQuestsOut, PlayerQuestOut } from "../../api/types";
import { QuestsTab } from "./QuestsTab";

afterEach(cleanup);

const QUEST: PlayerQuestOut = {
  id: "q1",
  name: "Dude, Where's My Warlord?",
  objective: "Locate Karsh",
  category: "epic",
  difficulty: 2,
  downtime_only: true,
  status: "active",
  role: "leader",
  leader_name: "Morgan",
  party: ["Morgan"],
  requirements: [
    { label: "Gangrel (clan) or Lore (Gangrel) 3", met: true, met_by_name: "Morgan" },
    { label: "Auspex 6", met: false, met_by_name: "" },
  ],
  scenario_count: 2,
  results: [{ number: 1, result: "passed", text: "Asheville.", sent_at: null }],
  ended_on: null,
  finished_by: [],
  close_note: "",
  tale: "",
  tale_approved: false,
  can_join: false,
  can_share: false,
  can_write_tale: false,
};

const FOUND: CharacterQuestsOut = {
  enabled: true,
  limit: 1,
  used: 1,
  cycle_name: "November 2026",
  refusal: null,
  requests: [
    {
      id: "r1",
      kind: "custom",
      objective: "Find Karsh",
      reason: "",
      companions: "",
      status: "answered",
      outcome: "quest",
      note: "",
      created_at: "2026-11-01T12:00:00Z",
      answered_at: "2026-11-02T12:00:00Z",
      quest_id: "q1",
      can_withdraw: false,
    },
  ],
  quests: [QUEST, { ...QUEST, id: "q2", name: "Being Built", status: "draft", requirements: [], results: [] }],
};

/** The tab at `at`, with its answers already fetched and the API never asked. */
function show(at: string, staffOf?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  client.setQueryData(["character-quests", "c1"], FOUND);
  client.setQueryData(["character-quest", "c1", "q1"], QUEST);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/characters/c1/quests/*" element={<QuestsTab characterId="c1" staffOf={staffOf} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("a character's quests, for its home troupe's staff (#614)", () => {
  it("lists them with their requirements met, those being built too, and nothing to ask", () => {
    show("/characters/c1/quests", "t1");
    expect(screen.queryByRole("button", { name: /Ask for a quest/ })).toBeNull();
    expect(screen.getByText(/Epic 2 · Downtime only · Under way · Leader · 1 of 2 requirements met/)).toBeTruthy();
    expect(screen.getByText(/Being built · Leader · No requirements yet/)).toBeTruthy();
    expect(screen.queryByText("Past quests")).toBeNull();
    expect(screen.getByText("Quest requests")).toBeTruthy();
    const link = screen.getByRole("link", { name: "Open the quest in the troupe's Quests" });
    expect(link.getAttribute("href")).toBe("/troupes/t1/quests/q1");
    expect(screen.queryByRole("button", { name: "Withdraw" })).toBeNull();
  });

  it("shows one with each requirement, results not yet sent, and the way to manage it", () => {
    show("/characters/c1/quests/q1", "t1");
    expect(screen.getByText(/Gangrel \(clan\) or Lore \(Gangrel\) 3/).textContent).toContain("(met by Morgan)");
    expect(screen.getByText(/Auspex 6/).textContent).not.toContain("met by");
    expect(screen.getByText(/Scenario 1: passed/).textContent).toContain("(not sent yet)");
    expect(screen.getByRole("link", { name: "Manage it in the troupe's Quests" }).getAttribute("href")).toBe("/troupes/t1/quests/q1");
    expect(screen.queryByRole("button", { name: "Join this quest" })).toBeNull();
  });

  it("is unchanged for its player", () => {
    show("/characters/c1/quests");
    expect(screen.getByText("Your requests")).toBeTruthy();
    expect(screen.getByRole("link", { name: "See the quest" }).getAttribute("href")).toBe("/characters/c1/quests/q1");
    expect(screen.queryByText(/requirements met/)).toBeNull();
    expect(screen.queryByRole("link", { name: "Manage it in the troupe's Quests" })).toBeNull();
  });
});

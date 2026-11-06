import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { EquipmentItemOut, ExpiryOut } from "../../api/types";
import { datesFor } from "../../dates";
import { EquipmentCard } from "../character/EquipmentTab";
import { NO_EXPIRY, expiryBody, expiryText, fromExpiry } from "./expiry";

afterEach(cleanup);

const dates = datesFor({ time_zone: "UTC", date_format: "day_month", clock: "12" });
const NOW = new Date("2026-11-01T12:00:00Z");

function expiry(more: Partial<ExpiryOut>): ExpiryOut {
  return { kind: "games", on: null, games_left: null, cycle_name: null, cycle_closes_at: null, note: "", ...more };
}

describe("expiryText", () => {
  it("says the last day an item is held", () => {
    expect(expiryText(expiry({ kind: "date", on: "2026-11-30" }), dates)).toBe("Expires at the end of 30 Nov 2026");
  });

  it("counts the holder's games left", () => {
    expect(expiryText(expiry({ games_left: 2 }), dates)).toBe("Expires after 2 more games");
    expect(expiryText(expiry({ games_left: 1 }), dates)).toBe("Expires after 1 more game");
  });

  it("names the cycle and its Due, with the time", () => {
    const cycle = expiry({ kind: "cycle", cycle_name: "November 2026", cycle_closes_at: "2026-11-28T23:59:00Z" });
    expect(expiryText(cycle, dates, NOW)).toBe("Expires when the downtime cycle November 2026 closes (due Sat 28 Nov, 11:59 pm)");
  });
});

describe("the editor's expiry", () => {
  it("is never until chosen, and sent as null", () => {
    expect(fromExpiry(null)).toEqual(NO_EXPIRY);
    expect(expiryBody(NO_EXPIRY)).toBeNull();
  });

  it("starts from the games left, and sends the note trimmed", () => {
    const draft = fromExpiry(expiry({ games_left: 2, note: "The blessing fades." }));
    expect(draft).toEqual({ kind: "games", on: "", games: "2", note: "The blessing fades." });
    expect(expiryBody({ ...draft, note: " Gone. " })).toEqual({ kind: "games", games: 2, note: "Gone." });
    expect(expiryBody({ ...draft, kind: "date", on: "2026-12-01" })).toEqual({ kind: "date", on: "2026-12-01", note: "The blessing fades." });
    expect(expiryBody({ ...draft, kind: "cycle" })).toEqual({ kind: "cycle", note: "The blessing fades." });
  });
});

const ITEM: EquipmentItemOut = {
  id: "1",
  character_id: "c",
  character_name: "Agnes",
  character_kind: "pc",
  player_name: "player",
  name: "Blessing of Saulot",
  kind: "miscellaneous",
  kind_name: "Miscellaneous gear",
  grade: "special",
  special: true,
  special_troupe_name: "Lords of the Night",
  qualities: [],
  crafted: false,
  archaic: false,
  effects: [],
  description: "",
  staff_note: null,
  facts: { hands: null, damage: null, shots: null, range: null, aggravated_against: [] },
  modifiers: [],
  status: "held",
  troupe_id: "t",
  troupe_name: "Lords of the Night",
  given_by_name: "storyteller",
  given_at: "2026-11-01T12:00:00Z",
  from_sheet: false,
  can_change: false,
  discarded: null,
  expiry: null,
};

function card(item: EquipmentItemOut) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  render(
    <QueryClientProvider client={client}>
      <ul>
        <EquipmentCard item={item} />
      </ul>
    </QueryClientProvider>,
  );
}

describe("an item that expires, on the sheet", () => {
  it("shows when, and what happens then", () => {
    card({ ...ITEM, expiry: expiry({ games_left: 2, note: "The blessing fades." }) });
    const line = screen.getByLabelText("Expiry");
    expect(line.textContent).toBe("Expires after 2 more games.The blessing fades.");
  });

  it("shows nothing for one that doesn't", () => {
    card(ITEM);
    expect(screen.queryByLabelText("Expiry")).toBeNull();
  });
});

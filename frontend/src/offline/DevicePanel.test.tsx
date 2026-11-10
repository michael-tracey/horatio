import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { CharacterListOut } from "../api/types";
import { datesFor } from "../dates";
import { DevicePanel, partialText, updatedText } from "./DevicePanel";
import { setKeeping } from "./keep";
import { memoryShelf } from "./shelf";
import { save } from "./store";

const ME = "11111111-1111-4111-8111-111111111111";
const ROSA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const dates = datesFor({ time_zone: "Europe/London", date_format: "day_month", clock: "24" });
// 14:05 and 18:20 on 10 November 2026 in London, and the next morning.
const updated = Date.parse("2026-11-10T14:05:00Z");
const tried = Date.parse("2026-11-10T18:20:00Z");
const nextDay = Date.parse("2026-11-11T09:00:00Z");

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("Account › This device: when what's kept was updated (#619)", () => {
  it("says when it was updated, or that it hasn't been", () => {
    expect(updatedText({ refreshedAt: updated }, dates)).toBe("Updated 10 Nov 2026, 14:05");
    expect(updatedText({ refreshedAt: null }, dates)).toBe("Not updated yet");
  });

  it("says nothing more when the last refresh all came", () => {
    expect(partialText({ refreshedAt: updated, partial: null }, dates)).toBeNull();
    expect(partialText({ refreshedAt: updated }, dates)).toBeNull();
  });

  it("says when the last try couldn't refresh some screens, and that they show what was kept before", () => {
    expect(partialText({ refreshedAt: updated, partial: { failed: 2, triedAt: tried } }, dates)).toBe(
      "The last try, at 18:20, couldn't refresh 2 screens; they show what was kept before.",
    );
    expect(partialText({ refreshedAt: updated, partial: { failed: 1, triedAt: tried } }, dates)).toBe("The last try, at 18:20, couldn't refresh 1 screen; it shows what was kept before.");
    // On another day, the day too.
    expect(partialText({ refreshedAt: updated, partial: { failed: 2, triedAt: nextDay } }, dates)).toBe(
      "The last try, at 11 Nov 2026, 09:00, couldn't refresh 2 screens; they show what was kept before.",
    );
    // Never updated in full: nothing from before to show.
    expect(partialText({ refreshedAt: null, partial: { failed: 2, triedAt: tried } }, dates)).toBe("The last try, at 10 Nov 2026, 18:20, couldn't refresh 2 screens.");
  });

  it("shows both on the panel after a partial refresh", async () => {
    const client = new QueryClient();
    client.setQueryData(["me"], { id: ME, preferences: { time_zone: "Europe/London", date_format: "day_month", clock: "24" } });
    client.setQueryData(["characters"], [{ id: ROSA, name: "Rosa", player_id: ME, kind: "pc", status: "active", creation_complete: true } as unknown as CharacterListOut]);
    setKeeping(ME, "on");
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <DevicePanel />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const shelf = memoryShelf();
    // The panel reads what's kept as it opens (nothing, here) before the refreshes are written.
    await act(async () => {});
    await act(async () => {
      await save(client, ME, shelf, { at: updated, failed: 0 });
      await save(client, ME, shelf, { at: tried, failed: 2 });
    });
    const kept = screen.getByRole("group", { name: "Kept on this device" });
    expect(kept.textContent).toContain("Updated 10 Nov 2026, 14:05");
    expect(kept.textContent).toContain("The last try, at 18:20, couldn't refresh 2 screens; they show what was kept before.");
  });
});

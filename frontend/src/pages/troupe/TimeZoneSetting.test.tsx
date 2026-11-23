import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { ToastProvider } from "../../components/Toast";
import { TimeZoneSetting, zoneDefaultText } from "./TimeZoneSetting";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// None of its own: the lead storyteller's.
const TROUPE = {
  id: "t1",
  name: "Court of Ashes",
  time_zone: "America/Chicago",
  time_zone_set: null,
  time_zone_default: "America/Chicago",
  archived: false,
} as unknown as TroupeOut;

function draw(troupe: TroupeOut = TROUPE, canEdit = true) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <ToastProvider>
          <TimeZoneSetting troupe={troupe} canEdit={canEdit} />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return screen.getByRole("region", { name: "Time zone" });
}

describe("the troupe's time zone (#1211)", () => {
  it("says what it uses with none chosen", () => {
    expect(zoneDefaultText(TROUPE)).toBe("Left empty, it uses the lead storyteller's time zone: America/Chicago.");
  });

  it("lets its storytellers choose a zone from the list, saved at once, and clear it", async () => {
    const saved = vi.spyOn(api, "PATCH").mockResolvedValue({ data: TROUPE, response: new Response(null, { status: 200 }) } as never);
    const card = draw();
    expect(card.textContent).toMatch(/Now: America\/Chicago \(C[SD]T\) \(the lead storyteller's\)/);
    const box = within(card).getByRole("combobox", { name: "Time zone" });
    // Half-typed, nothing is saved.
    fireEvent.change(box, { target: { value: "America/New" } });
    expect(saved).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: "America/New_York" } });
    await waitFor(() =>
      expect(saved).toHaveBeenCalledWith("/api/troupes/{troupe_id}", { params: { path: { troupe_id: "t1" } }, body: { time_zone: "America/New_York" } }),
    );

    cleanup();
    const chosen = draw({ ...TROUPE, time_zone: "America/New_York", time_zone_set: "America/New_York" });
    expect(chosen.textContent).not.toContain("the lead storyteller's)");
    fireEvent.click(within(chosen).getByRole("button", { name: "Use the lead storyteller's" }));
    await waitFor(() => expect(saved).toHaveBeenLastCalledWith("/api/troupes/{troupe_id}", { params: { path: { troupe_id: "t1" } }, body: { time_zone: "" } }));
  });

  it("shows other staff the zone, read-only", () => {
    const card = draw({ ...TROUPE, time_zone: "Europe/London", time_zone_set: "Europe/London" }, false);
    expect(within(card).queryByRole("combobox")).toBeNull();
    expect(card.textContent).toMatch(/Now: Europe\/London \((GMT|BST)\)/);
    expect(card.textContent).toContain("The troupe's storytellers change this.");
  });
});

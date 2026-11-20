import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResetGame } from "./PlayPage";
import type { Shown } from "./tracker";
import type { Sync } from "./usePlay";

afterEach(cleanup);

const view = {
  character_id: "c1",
  game: null,
  vitae: false,
  blood_name: "Blood",
  blood: { value: 5, start: 10 },
  willpower: { most: 6, start: 6 },
  derangements: { flaws: [], temporary: [], value: 0, least: 0 },
} as unknown as Shown;

const sync = (waiting: number, online = true): Sync => ({ online, waiting, sending: waiting > 0, error: null, asOf: null });

function shown(s: Sync) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ResetGame view={view} sync={s} onReset={vi.fn()} />
    </QueryClientProvider>,
  );
}

// A tap is sent in the background; Reset must not reach the server before it (#1085).
describe("Reset for next game waits for every tap to be saved", () => {
  it("can't be asked for while a tap waits", () => {
    shown(sync(1));
    expect((screen.getByRole("button", { name: "Reset for next game…" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Resetting waits until every tap is saved.")).toBeTruthy();
  });

  it("can't be confirmed once a tap made while asking waits", () => {
    const { rerender } = shown(sync(0));
    fireEvent.click(screen.getByRole("button", { name: "Reset for next game…" }));
    const confirm = screen.getByRole("button", { name: "Reset for next game" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(false);
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ResetGame view={view} sync={sync(1)} onReset={vi.fn()} />
      </QueryClientProvider>,
    );
    expect((screen.getByRole("button", { name: "Reset for next game" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("can't be asked for offline", () => {
    shown(sync(0, false));
    expect((screen.getByRole("button", { name: "Reset for next game…" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PlayView } from "../../api/types";
import { OnOthers } from "./OnOthers";
import { onOtherTaps } from "./UsePower";
import { onOtherText } from "./tracker";

afterEach(cleanup);

function wrap(children: ReactNode) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

const effect = {
  id: "e1",
  key: "Reshaped by Fleshcraft",
  name: "Fleshcraft: reshaped",
  since: "2026-11-14T00:00:00Z",
  started_by: "player",
  source_character_name: "Velya",
  paused: false,
  options: ["Alien beauty"],
  acknowledged_at: null,
  disputed_at: null,
  dispute_note: "",
};

const made = {
  id: "m1",
  character_id: "c2",
  character_name: "Bram",
  name: "Fleshcraft: reshaped",
  options: ["Ordinary change"],
  since: "2026-11-14T00:00:00Z",
  acknowledged_at: "2026-11-14T00:01:00Z",
  disputed_at: null,
  dispute_note: "",
};

const view = (over: Partial<PlayView>) => ({ character_id: "c1", effects: [], effects_made: [], ...over }) as unknown as PlayView;

describe("powers used on others (#823)", () => {
  it("shows another's effect with Acknowledge and Dispute, and one's own on others with End", () => {
    render(wrap(<OnOthers view={view({ effects: [effect], effects_made: [made] })} online onChange={vi.fn()} />));
    expect(screen.getByRole("list", { name: "On you, from others" }).textContent).toContain("Velya used Fleshcraft: reshaped (Alien beauty) on you");
    expect(screen.getByRole("button", { name: "Acknowledge" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Dispute" })).toBeTruthy();
    const mine = screen.getByRole("list", { name: "Your powers on others" });
    expect(mine.textContent).toContain("Fleshcraft: reshaped (Ordinary change) on Bram");
    expect(mine.textContent).toContain("Acknowledged.");
    expect(screen.getByRole("button", { name: "End Fleshcraft: reshaped on Bram" })).toBeTruthy();
  });

  it("says a dispute, and offers no answer twice", () => {
    const disputed = { ...effect, disputed_at: "2026-11-14T00:02:00Z", dispute_note: "Never agreed." };
    render(wrap(<OnOthers view={view({ effects: [disputed] })} online onChange={vi.fn()} />));
    expect(screen.getByText("Disputed to the storytellers: Never agreed.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Acknowledge" })).toBeNull();
  });

  it("shows nothing when nothing is used on or by the character", () => {
    const own = { ...effect, source_character_name: null };
    const { container } = render(wrap(<OnOthers view={view({ effects: [own] })} online onChange={vi.fn()} />));
    expect(container.textContent).toBe("");
  });

  it("makes the cost tap and the note that carries the use", () => {
    const taps = onOtherTaps({ tracker: "blood", amount: 1 }, "Fleshcraft", { id: "c2", name: "Bram" }, { switch: "Reshaped by Fleshcraft", options: ["Alien beauty"] });
    expect(taps[0]).toMatchObject({ kind: "change", tracker: "blood", amount: -1 });
    expect(taps[1]).toMatchObject({
      kind: "note",
      on_other: { character_id: "c2", character_name: "Bram", power: "Fleshcraft", switch: "Reshaped by Fleshcraft", use: null, options: ["Alien beauty"] },
    });
    const noted = taps[1]!.on_other!;
    expect(onOtherText(noted, { powers: [{ key: "Reshaped by Fleshcraft", name: "Fleshcraft: reshaped" }] } as unknown as PlayView)).toBe("Used Fleshcraft: reshaped (Alien beauty) on Bram");
    const heal = onOtherTaps({ tracker: "blood", amount: 1 }, "Corpore Sano", { id: "c2", name: "Bram" }, { use: "Heal 1 normal" });
    expect(heal[1]!.on_other).toMatchObject({ use: "Heal 1 normal", switch: null });
  });
});

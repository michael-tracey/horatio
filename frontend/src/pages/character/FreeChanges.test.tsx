import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { datesFor } from "../../dates";
import { freeChangesText, FreeChangesText } from "./FreeChanges";

afterEach(cleanup);

const dates = datesFor({ time_zone: "Europe/London", date_format: "day_month", clock: "12" });
const now = new Date("2026-11-14T12:00:00Z");

describe("free changes on the sheet", () => {
  it("says until when, for free changes by date", () => {
    const free = { kind: "date" as const, ends_at: "2026-12-14T19:30:00Z", games_left: null, excluded: [] };
    expect(freeChangesText(free, dates, now)).toBe("Free changes until Mon 14 Dec");
    render(<FreeChangesText free={free} dates={dates} now={now} />);
    expect(screen.getByRole("region", { name: "Free changes" }).textContent).toContain("Free changes until Mon 14 Dec");
    expect(screen.queryByText(/checks in/)).toBeNull();
  });

  it("says how many games are left, for free changes by games played", () => {
    const free = { kind: "games" as const, ends_at: null, games_left: 2, excluded: ["Arcane", "Efficient Learner"] };
    expect(freeChangesText(free, dates, now)).toBe("Free changes: 2 games left");
    expect(freeChangesText({ ...free, games_left: 1 }, dates, now)).toBe("Free changes: 1 game left");
    render(<FreeChangesText free={free} dates={dates} now={now} />);
    const notice = screen.getByRole("region", { name: "Free changes" }).textContent;
    expect(notice).toContain("Free changes: 2 games left");
    expect(notice).toContain("Arcane and Efficient Learner are never refunded so.");
    expect(notice).toContain("A game counts once the character checks in.");
  });
});

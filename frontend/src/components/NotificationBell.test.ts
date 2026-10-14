import { describe, expect, it } from "vitest";
import { timeAgo } from "./NotificationBell";

describe("timeAgo", () => {
  const now = new Date("2026-10-14T12:00:00Z").getTime();
  const ago = (seconds: number) => new Date(now - seconds * 1000).toISOString();

  it("picks the largest whole unit", () => {
    const format = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    expect(timeAgo(ago(30), now)).toBe(format.format(-30, "second"));
    expect(timeAgo(ago(5 * 60), now)).toBe(format.format(-5, "minute"));
    expect(timeAgo(ago(3 * 3600), now)).toBe(format.format(-3, "hour"));
    expect(timeAgo(ago(26 * 3600), now)).toBe(format.format(-1, "day"));
  });
});

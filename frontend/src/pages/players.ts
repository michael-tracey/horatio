import type { Dates } from "../dates";

/** "March 2019 (7 years)": when a player joined, and how long ago. */
export function memberSince(joined: string, dates: Dates, now: Date = new Date()): string {
  const at = new Date(joined);
  const month = dates.month(at);
  const months = (now.getFullYear() - at.getFullYear()) * 12 + now.getMonth() - at.getMonth() - (now.getDate() < at.getDate() ? 1 : 0);
  const years = Math.floor(months / 12);
  const span =
    years >= 1 ? `${years} year${years === 1 ? "" : "s"}` : months >= 1 ? `${months} month${months === 1 ? "" : "s"}` : "new this month";
  return `${month} (${span})`;
}

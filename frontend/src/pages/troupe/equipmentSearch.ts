/**
 * The troupe Equipment tab's item search (issue #284), kept apart from the screen
 * so it can be tested: what it asks, as it travels in the URL (so a reload, Back,
 * a shared link or the Characters list's Show their equipment keep it), as the API
 * takes it, and the items found as a CSV for a game night's armoury sheet.
 */
import type { EquipmentItemOut } from "../../api/types";
import { qualityText } from "./equipment";

export type Sort = "holder" | "name" | "date";
export type Status = "held" | "discarded" | "taken_back";

export type ItemSearch = {
  /** Words anywhere in an item: its name, description, qualities, special effects and staff note. */
  q: string;
  /** Character ids; none for every character. */
  holders: string[];
  kind: string;
  quality: string;
  grade: string;
  statuses: Status[];
  /** Held by retired characters too. */
  retired: boolean;
  /** The id of who gave it. */
  givenBy: string;
  /** Given on or after this day, and on or before that: "2026-10-01". */
  from: string;
  to: string;
  sort: Sort;
};

export const STATUS_NAMES: Record<Status, string> = { held: "Held", discarded: "Discarded", taken_back: "Taken back" };
const SORTS: Sort[] = ["holder", "name", "date"];

export function readSearch(params: URLSearchParams): ItemSearch {
  const list = (key: string) => (params.get(key) ?? "").split(",").filter(Boolean);
  const statuses = list("show").filter((s): s is Status => s in STATUS_NAMES);
  const sort = params.get("sort") as Sort;
  return {
    q: params.get("q") ?? "",
    holders: list("holders"),
    kind: params.get("kind") ?? "",
    quality: params.get("quality") ?? "",
    grade: params.get("grade") ?? "",
    statuses: statuses.length ? statuses : ["held"],
    retired: params.get("retired") === "1",
    givenBy: params.get("given_by") ?? "",
    from: params.get("from") ?? "",
    to: params.get("to") ?? "",
    sort: SORTS.includes(sort) ? sort : "holder",
  };
}

/** The search as URL parameters, leaving out what is as it starts. */
export function writeSearch(s: ItemSearch): URLSearchParams {
  const params = new URLSearchParams();
  const put = (key: string, value: string) => value && params.set(key, value);
  put("q", s.q);
  put("holders", s.holders.join(","));
  put("kind", s.kind);
  put("quality", s.quality);
  put("grade", s.grade);
  if (s.statuses.join(",") !== "held") put("show", s.statuses.join(","));
  if (s.retired) put("retired", "1");
  put("given_by", s.givenBy);
  put("from", s.from);
  put("to", s.to);
  if (s.sort !== "holder") put("sort", s.sort);
  return params;
}

/** The day after "2026-10-31": "2026-11-01". */
function nextDay(day: string): string {
  const [y = 0, m = 1, d = 1] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
}

/** What the API takes. `midnight` reads a day's start on the reader's clock. */
export function searchQuery(s: ItemSearch, midnight: (day: string) => Date) {
  return {
    q: s.q.trim() || undefined,
    character_id: s.holders.length ? s.holders : undefined,
    kind: (s.kind || undefined) as "melee" | "ranged" | "protective" | "miscellaneous" | undefined,
    quality: s.quality || undefined,
    grade: (s.grade || undefined) as "cheap" | "standard" | "special" | undefined,
    status: s.statuses,
    retired: s.retired || undefined,
    given_by: s.givenBy || undefined,
    given_after: s.from ? midnight(s.from).toISOString() : undefined,
    // Up to the end of the last day.
    given_before: s.to ? midnight(nextDay(s.to)).toISOString() : undefined,
    sort: s.sort,
  };
}

/** The Equipment tab showing these characters' items; retired ones' too if any is. */
export function holdersLink(troupeId: string, holders: string[], retired: boolean): string {
  const params = new URLSearchParams();
  if (holders.length) params.set("holders", holders.join(","));
  if (retired) params.set("retired", "1");
  const query = params.toString();
  return `/troupes/${troupeId}/equipment${query ? `?${query}` : ""}`;
}

/** A cell, quoted where it must be, and kept from being read as a formula. */
function cell(value: string): string {
  const safe = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
  return /[",\n\r]/.test(safe) ? `"${safe.replaceAll('"', '""')}"` : safe;
}

const HEADINGS = ["Item", "Held by", "Player", "Kind", "Grade", "Qualities", "Special effects", "Description", "Status", "Given by", "Troupe", "Given on", "Staff note"];

/** The items as a CSV, one a line. `day` writes the date given: "2026-10-27". */
export function itemsCsv(items: EquipmentItemOut[], day: (at: string) => string): string {
  const rows = items.map((i) => [
    i.name,
    i.character_name,
    i.character_kind === "npc" ? "NPC" : (i.player_name ?? ""),
    i.kind_name,
    i.grade.charAt(0).toUpperCase() + i.grade.slice(1),
    i.qualities.map(qualityText).join("; "),
    i.effects.map((e) => `${e.name}: ${e.effect}`).join("; "),
    i.description,
    STATUS_NAMES[i.status],
    i.given_by_name ?? "",
    i.troupe_name,
    day(i.given_at),
    i.staff_note ?? "",
  ]);
  return [HEADINGS, ...rows].map((row) => row.map(cell).join(",")).join("\r\n") + "\r\n";
}

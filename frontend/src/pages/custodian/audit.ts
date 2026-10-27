import type { components } from "../../api/schema";

export type AuditEntry = components["schemas"]["AuditEntry"];
export type AuditCharacter = components["schemas"]["AuditCharacter"];
export type AuditGroup = components["schemas"]["AuditGroup"];

/** The audit search as the custodian fills it in, and as it sits in the page's address. */
export type AuditFilters = {
  /** Who did it: a handle. */
  person: string;
  character: string;
  troupe: string;
  group: string;
  /** Days, "2026-10-27", from the first to the last, both included. */
  from: string;
  to: string;
  words: string;
};

export const NO_FILTERS: AuditFilters = { person: "", character: "", troupe: "", group: "", from: "", to: "", words: "" };

const KEYS = Object.keys(NO_FILTERS) as (keyof AuditFilters)[];

export function filtersFrom(params: URLSearchParams): AuditFilters {
  return Object.fromEntries(KEYS.map((k) => [k, params.get(k) ?? ""])) as AuditFilters;
}

/** The filters set, for the page's address. */
export function toParams(filters: AuditFilters): Record<string, string> {
  return Object.fromEntries(KEYS.filter((k) => filters[k].trim()).map((k) => [k, filters[k].trim()]));
}

/** The day after "2026-10-31": "2026-11-01". */
export function nextDay(day: string): string {
  const [year = 0, month = 1, date = 1] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date + 1)).toISOString().slice(0, 10);
}

/**
 * The filters as the API takes them. Days start at midnight on the custodian's
 * own clock (`fromInput`, from `useDates`), and the last day is included.
 */
export function auditQuery(filters: AuditFilters, fromInput: (value: string) => Date) {
  const f = filters;
  return {
    person: f.person.trim() || undefined,
    character_id: f.character || undefined,
    troupe_id: f.troupe || undefined,
    group: (f.group || undefined) as AuditGroup | undefined,
    since: f.from ? fromInput(`${f.from}T00:00`).toISOString() : undefined,
    until: f.to ? fromInput(`${nextDay(f.to)}T00:00`).toISOString() : undefined,
    q: f.words.trim() || undefined,
  };
}

/** Where the CSV of what the filters find downloads from. */
export function exportHref(query: ReturnType<typeof auditQuery>): string {
  const params = new URLSearchParams(Object.entries(query).filter((e): e is [string, string] => !!e[1]));
  const search = params.toString();
  return `/api/audit/export${search ? `?${search}` : ""}`;
}

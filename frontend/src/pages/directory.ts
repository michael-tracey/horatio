/**
 * The troupe directory (#1192), at /find-a-troupe: what it searches for, kept in the
 * address so a search can be shared or come back to, and the way to ask a troupe to
 * take a character from its public profile.
 */
import type { CharacterOut, TroupeOut } from "../api/types";

/** Where the directory is: /troupes is the signed-in Troupes page. */
export const DIRECTORY = "/find-a-troupe";

// As many as the API puts on a page (public_troupes.PAGE_SIZE).
export const TROUPES_PAGE_SIZE = 12;

// As GET /api/public/troupes takes them (api/public_troupes.py).
export type Day = "monday" | "tuesday" | "wednesday" | "thursday" | "friday" | "saturday" | "sunday";
export type Frequency = "weekly" | "fortnightly" | "monthly";
type Query = { page: number; name?: string; place?: string; day?: Day; frequency?: Frequency; new_players?: boolean; age?: number };

export const DAYS: { day: Day; label: string }[] = [
  { day: "monday", label: "Monday" },
  { day: "tuesday", label: "Tuesday" },
  { day: "wednesday", label: "Wednesday" },
  { day: "thursday", label: "Thursday" },
  { day: "friday", label: "Friday" },
  { day: "saturday", label: "Saturday" },
  { day: "sunday", label: "Sunday" },
];

export const FREQUENCIES: { frequency: Frequency; label: string }[] = [
  { frequency: "weekly", label: "Weekly" },
  { frequency: "fortnightly", label: "Fortnightly" },
  { frequency: "monthly", label: "Monthly" },
];

/** What the directory searches for. Empty text, or null, leaves that out. */
export type Search = {
  name: string;
  place: string;
  day: Day | null;
  frequency: Frequency | null;
  /** Only troupes welcoming new players. */
  welcoming: boolean;
  /** Only troupes a player of this age may join. */
  age: number | null;
};

export const NO_SEARCH: Search = { name: "", place: "", day: null, frequency: null, welcoming: false, age: null };

/** An age a profile can give: a whole number from 0 to 99, or null. */
export function ageFrom(raw: string | null): number | null {
  if (!raw || !/^\d{1,2}$/.test(raw.trim())) return null;
  return Number(raw.trim());
}

/** The search in the address's `?name=&place=&day=&often=&new=&age=`; what it doesn't know is left out. */
export function searchFrom(params: URLSearchParams): Search {
  const day = params.get("day");
  const often = params.get("often");
  return {
    name: params.get("name") ?? "",
    place: params.get("place") ?? "",
    day: DAYS.find((d) => d.day === day)?.day ?? null,
    frequency: FREQUENCIES.find((f) => f.frequency === often)?.frequency ?? null,
    welcoming: params.get("new") === "1",
    age: ageFrom(params.get("age")),
  };
}

/** The page of results asked for in the address, counting from 1. */
export function pageFrom(params: URLSearchParams): number {
  const page = Number(params.get("page"));
  return Number.isInteger(page) && page >= 1 ? page : 1;
}

/** `params` with the search written in, and the page `page` (1 is left out). */
export function withSearch(params: URLSearchParams, search: Search, page = 1): URLSearchParams {
  const next = new URLSearchParams(params);
  const set = (key: string, value: string | null) => (value ? next.set(key, value) : next.delete(key));
  set("name", search.name.trim() || null);
  set("place", search.place.trim() || null);
  set("day", search.day);
  set("often", search.frequency);
  set("new", search.welcoming ? "1" : null);
  set("age", search.age === null ? null : String(search.age));
  set("page", page > 1 ? String(page) : null);
  return next;
}

/** Whether anything is searched for. */
export function searching(search: Search): boolean {
  return !!search.name.trim() || !!search.place.trim() || !!search.day || !!search.frequency || search.welcoming || search.age !== null;
}

/** The API's query for the search and page. */
export function apiQuery(search: Search, page: number): Query {
  return {
    page,
    ...(search.name.trim() && { name: search.name.trim() }),
    ...(search.place.trim() && { place: search.place.trim() }),
    ...(search.day && { day: search.day }),
    ...(search.frequency && { frequency: search.frequency }),
    ...(search.welcoming && { new_players: true }),
    ...(search.age !== null && { age: search.age }),
  };
}

/**
 * Where "Request to join" on a troupe's public profile leads once signed in
 * (/troupes/<id>/join, `joinPath`): the ask-to-join flow, with the troupe chosen.
 * Someone with no character to bring builds a new one for it; someone with one, or
 * already in it (on its staff, at home or asking), goes to its page, whose Play here
 * card offers each character to ask with, or says what waits.
 */
export function joinPath(troupe: Pick<TroupeOut, "id" | "my_role" | "archived" | "allowed_splats">, characters: CharacterOut[]): string {
  const page = `/troupes/${troupe.id}`;
  if (troupe.my_role || troupe.archived) return page;
  const active = characters.filter((c) => c.status === "active");
  if (active.some((c) => c.home_troupe_id === troupe.id || c.asking_troupe_id === troupe.id)) return page;
  const bring = active.some((c) => !c.home_troupe_id && !c.asking_troupe_id && troupe.allowed_splats.includes(c.splat));
  return bring ? page : `/characters?troupe=${troupe.id}`;
}

/** The address "Request to join" leads to: signed out, through signing up to it. */
export function requestToJoin(troupeId: string): string {
  return `/troupes/${troupeId}/join`;
}

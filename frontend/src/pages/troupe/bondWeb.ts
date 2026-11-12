import type { BondWebOut, WebBondOut, WebPersonOut } from "../../api/types";
import { clanKey } from "../../charts/clans";

/*
 * The troupe's blood bonds as a web (#708): who is shown, which bonds link them,
 * and what the web says (chains of bonds, who holds the most thralls), as plain
 * functions the chart draws and the tests check.
 */

export type WebFilters = {
  // Everyone, or only those still in play (and names only).
  who: "active" | "everyone";
  // Only full bonds.
  full: boolean;
  // Ended and broken bonds too, drawn faintly.
  ended: boolean;
  // Only bonds with someone of this clan on either side.
  clan: string | null;
  // Only bonds with a title holder on either side.
  titled: boolean;
};

export const DEFAULT_FILTERS: WebFilters = { who: "active", full: false, ended: false, clan: null, titled: false };

export type WebLink = WebBondOut & { open: boolean };
export type WebNode = WebPersonOut & { thralls: number; boundTo: number };
export type Web = { nodes: WebNode[]; links: WebLink[] };

/** Still felt: active, or fading after its regnant's Final Death. */
export const feltStatus = (status: string) => status === "active" || status === "fading";

/** The bonds the filters keep, and everyone on either side of them, with how many open bonds each holds and is held by. */
export function bondWeb(data: Pick<BondWebOut, "people" | "bonds">, filters: WebFilters): Web {
  const people = new Map(data.people.map((p) => [p.key, p]));
  const kept = data.bonds.filter((b) => {
    const thrall = people.get(b.thrall);
    const regnant = people.get(b.regnant);
    if (!thrall || !regnant) return false;
    const sides = [thrall, regnant];
    if (!filters.ended && !feltStatus(b.status)) return false;
    if (filters.full && b.level < 3) return false;
    if (filters.who === "active" && sides.some((p) => p.standing !== "active")) return false;
    if (filters.clan !== null && !sides.some((p) => clanKey(p.clan) === filters.clan)) return false;
    if (filters.titled && !sides.some((p) => p.titles.length > 0)) return false;
    return true;
  });
  const links: WebLink[] = kept.map((b) => ({ ...b, open: feltStatus(b.status) }));
  const nodes = new Map<string, WebNode>();
  for (const l of links) {
    for (const key of [l.thrall, l.regnant]) {
      if (!nodes.has(key)) nodes.set(key, { ...people.get(key)!, thralls: 0, boundTo: 0 });
    }
    if (l.open) {
      nodes.get(l.regnant)!.thralls += 1;
      nodes.get(l.thrall)!.boundTo += 1;
    }
  }
  return { nodes: [...nodes.values()].sort((a, b) => a.name.localeCompare(b.name)), links };
}

/** Those both bound to someone and holding thralls of their own: where bonds run in a chain. */
export function chains(web: Web): { person: WebNode; regnants: string[]; thralls: string[] }[] {
  const byKey = new Map(web.nodes.map((n) => [n.key, n]));
  const open = web.links.filter((l) => l.open);
  return web.nodes
    .filter((n) => n.boundTo > 0 && n.thralls > 0)
    .map((person) => ({
      person,
      regnants: open
        .filter((l) => l.thrall === person.key)
        .map((l) => byKey.get(l.regnant)!.name)
        .sort((a, b) => a.localeCompare(b)),
      thralls: open
        .filter((l) => l.regnant === person.key)
        .map((l) => byKey.get(l.thrall)!.name)
        .sort((a, b) => a.localeCompare(b)),
    }));
}

/** The regnants with the most thralls still bound to them, most first, and how many of those bonds are full. */
export function mostThralls(web: Web, top = 5): { person: WebNode; thralls: number; full: number }[] {
  return web.nodes
    .filter((n) => n.thralls > 0)
    .map((person) => ({
      person,
      thralls: person.thralls,
      full: web.links.filter((l) => l.open && l.regnant === person.key && l.level >= 3).length,
    }))
    .sort((a, b) => b.thralls - a.thralls || b.full - a.full || a.person.name.localeCompare(b.person.name))
    .slice(0, top);
}

/** The clans of everyone on either side of any bond, for the clan filter. */
export function webClans(people: readonly WebPersonOut[]): string[] {
  return [...new Set(people.map((p) => clanKey(p.clan)))].sort((a, b) => a.localeCompare(b));
}

/** How someone stands, as the web says it. */
export function standingText(standing: string): string {
  switch (standing) {
    case "active":
      return "In play";
    case "final_death":
      return "Final Death";
    case "off_field":
      return "Off-field";
    case "inactive":
      return "Inactive";
    default:
      return "Retired";
  }
}

/** A bond's state, as the web says it. */
export function linkStatusText(link: Pick<WebBondOut, "status">): string {
  switch (link.status) {
    case "fading":
      return "Fading";
    case "ended":
      return "Ended";
    case "broken":
      return "Broken";
    default:
      return "Active";
  }
}

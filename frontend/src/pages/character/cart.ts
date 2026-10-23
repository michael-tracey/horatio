/**
 * The cart: changes to a sheet gathered on the Sheet tab, saved nowhere until
 * Spend XP (or Apply picks, during creation) sends them all at once. It is
 * kept in this browser, one per character, so it survives a reload.
 */

import { useSyncExternalStore } from "react";
import type { components } from "../../api/schema";

/** A change asked of the home troupe's staff as an exception to the rules: why, and whether at no XP cost. */
export type Exception = { reason: string; free: boolean };

export type CartLine =
  /** A rating from `from` (as saved) to `to`: a raise, a lower, a new trait (from 0) or a removal (to 0). */
  | { kind: "set"; category: string; name: string; detail: string; from: number; to: number; teacher?: string; fixed?: boolean; exception?: Exception }
  | { kind: "swap"; category: string; from_name: string; to_name: string }
  | { kind: "pick"; category: string; name: string; detail: string; rating: number }
  | { kind: "unpick"; category: string; name: string; detail: string };

export type CartChange = components["schemas"]["CartIn"]["changes"][number];

type Trait = { category: string; name: string; detail: string };

const same = (a: Trait, b: Trait) => a.category === b.category && a.name === b.name && a.detail === b.detail;

/** The order the changes are made in: picks taken back and ratings lowered
 * first, so what they free or refund is there for the rest; then as added. */
function rank(line: CartLine): number {
  if (line.kind === "unpick") return 0;
  if (line.kind === "set" && line.to < line.from) return 1;
  return 2;
}

export function ordered(lines: CartLine[]): CartLine[] {
  return lines
    .map((line, i) => [line, i] as const)
    .sort(([a, i], [b, j]) => rank(a) - rank(b) || i - j)
    .map(([line]) => line);
}

/** Set a trait's rating in the cart. Back to where it was saved, it leaves the cart. */
export function setRating(
  lines: CartLine[],
  trait: Trait & { rating: number; teacher?: string; fixed?: boolean; exception?: Exception },
  to: number,
): CartLine[] {
  const found = lines.find((l): l is Extract<CartLine, { kind: "set" }> => l.kind === "set" && same(l, trait));
  const from = found?.from ?? trait.rating;
  const rest = lines.filter((l) => l !== found);
  if (to === from) return rest;
  const line: CartLine = {
    kind: "set",
    category: trait.category,
    name: trait.name,
    detail: trait.detail,
    from,
    to,
    ...((trait.teacher ?? found?.teacher) ? { teacher: trait.teacher ?? found?.teacher } : {}),
    ...((trait.fixed ?? found?.fixed) ? { fixed: true } : {}),
    // Asked as an exception: it stays asked at the new rating, which is judged again when spent.
    ...((trait.exception ?? found?.exception) && to > from ? { exception: trait.exception ?? found?.exception } : {}),
  };
  return found ? lines.map((l) => (l === found ? line : l)) : [...lines, line];
}

/** Ask staff for a line the rules refuse, as an exception. */
export function askException(lines: CartLine[], line: CartLine, exception: Exception): CartLine[] {
  return lines.map((l) => (l === line && l.kind === "set" ? { ...l, exception } : l));
}

/** Swap a trait for another in the cart; swapping it again replaces the first. */
export function swap(lines: CartLine[], category: string, fromName: string, toName: string): CartLine[] {
  const rest = lines.filter((l) => !(l.kind === "swap" && l.category === category && l.from_name === fromName));
  return fromName === toName ? rest : [...rest, { kind: "swap", category, from_name: fromName, to_name: toName }];
}

/** Place a creation pick in the cart; placing it again replaces the first. */
export function pick(lines: CartLine[], trait: Trait, rating: number): CartLine[] {
  return [...lines.filter((l) => !(l.kind === "pick" && same(l, trait))), { kind: "pick", ...trait, rating }];
}

/** Take a creation pick back: one only in the cart just leaves it. */
export function unpick(lines: CartLine[], trait: Trait): CartLine[] {
  if (lines.some((l) => l.kind === "pick" && same(l, trait))) return lines.filter((l) => !(l.kind === "pick" && same(l, trait)));
  if (lines.some((l) => l.kind === "unpick" && same(l, trait))) return lines;
  return [...lines, { kind: "unpick", ...trait }];
}

/** What the API is sent for a line. */
export function toChange(line: CartLine): CartChange {
  switch (line.kind) {
    case "set":
      return {
        kind: "set",
        category: line.category,
        name: line.name,
        detail: line.detail,
        rating: line.to,
        from_rating: line.from,
        teacher: line.teacher ?? "",
        ...(line.exception ? { exception: line.exception } : {}),
      };
    case "swap":
      return line;
    case "pick":
      return { kind: "pick", category: line.category, name: line.name, detail: line.detail, rating: line.rating };
    case "unpick":
      return { kind: "unpick", category: line.category, name: line.name, detail: line.detail };
  }
}

const named = (t: Trait) => (t.detail ? `${t.name}: ${t.detail}` : t.name);

/** How a line reads in the cart: "Brawl 2 → 3", "Add Dominate 1". */
export function describe(line: CartLine): string {
  switch (line.kind) {
    case "set":
      if (line.from === 0) return line.fixed ? `Add ${named(line)}` : `Add ${named(line)} ${line.to}`;
      if (line.to === 0) return `Remove ${named(line)}`;
      return `${named(line)} ${line.from} → ${line.to}`;
    case "swap":
      return `${line.from_name} → ${line.to_name}`;
    case "pick":
      return `Pick ${named(line)} at ${line.rating}`;
    case "unpick":
      return `Take back the pick on ${named(line)}`;
  }
}

/** A line's cost as the cart shows it: "4 XP", "2 XP back", or nothing for none. */
export function costText(cost: number | null | undefined): string {
  if (cost == null || cost === 0) return "";
  return cost > 0 ? `${cost} XP` : `${-cost} XP back`;
}

/** The rating a trait would have after the cart, if the cart changes it. */
export function plannedRating(lines: CartLine[], trait: Trait): number | null {
  const line = lines.find((l) => l.kind === "set" && same(l, trait));
  return line?.kind === "set" ? line.to : null;
}

/** What the cart would swap a trait for. */
export function swappedTo(lines: CartLine[], category: string, name: string): string | null {
  const line = lines.find((l) => l.kind === "swap" && l.category === category && l.from_name === name);
  return line?.kind === "swap" ? line.to_name : null;
}

/** Traits the cart adds that the saved sheet does not hold. */
export function added(lines: CartLine[], held: Trait[]) {
  return lines.filter((l): l is Extract<CartLine, { kind: "set" }> => l.kind === "set" && l.from === 0 && !held.some((h) => same(h, l)));
}

// --- kept in this browser ------------------------------------------------------

const PREFIX = "horatio.cart.";

function isLine(value: unknown): value is CartLine {
  return !!value && typeof value === "object" && ["set", "swap", "pick", "unpick"].includes((value as { kind?: unknown }).kind as string);
}

/** The cart kept for a character; empty if there is none, or storage is out of reach. */
export function loadCart(characterId: string): CartLine[] {
  try {
    const raw = localStorage.getItem(PREFIX + characterId);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(isLine) : [];
  } catch {
    return [];
  }
}

function saveCart(characterId: string, lines: CartLine[]) {
  try {
    if (lines.length) localStorage.setItem(PREFIX + characterId, JSON.stringify(lines));
    else localStorage.removeItem(PREFIX + characterId);
  } catch {
    // Kept for this visit only, then.
  }
}

const carts = new Map<string, CartLine[]>();
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

function subscribe(listener: () => void) {
  listeners.add(listener);
  // Another tab changed a cart.
  const onStorage = (e: StorageEvent) => {
    if (e.key?.startsWith(PREFIX)) {
      carts.delete(e.key.slice(PREFIX.length));
      listener();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function read(characterId: string): CartLine[] {
  let lines = carts.get(characterId);
  if (!lines) {
    lines = loadCart(characterId);
    carts.set(characterId, lines);
  }
  return lines;
}

export type Cart = {
  lines: CartLine[];
  update: (change: (lines: CartLine[]) => CartLine[]) => void;
  remove: (line: CartLine) => void;
  clear: () => void;
};

/** A character's cart, shared by everything on the page that shows it. */
export function useCart(characterId: string): Cart {
  const lines = useSyncExternalStore(subscribe, () => read(characterId));
  const write = (next: CartLine[]) => {
    carts.set(characterId, next);
    saveCart(characterId, next);
    notify();
  };
  return {
    lines,
    update: (change) => write(ordered(change(read(characterId)))),
    remove: (line) => write(read(characterId).filter((l) => l !== line)),
    clear: () => write([]),
  };
}

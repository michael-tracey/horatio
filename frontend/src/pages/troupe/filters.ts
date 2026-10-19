/**
 * The troupe Characters list's filter (issue #36), kept apart from the screen so
 * it can be tested. A filter is a tree the server evaluates
 * (horatio/character_filter.py): a group matches all, or any, of its items, each
 * a condition or another group.
 */

export type What = "status" | "trait" | "choice" | "title" | "player" | "xp" | "count";
export type Op = "is" | "is_not" | "family" | "lt" | "lte" | "eq" | "gte" | "gt" | "has" | "lacks";
export type Condition = { what: What; which?: string | null; op: Op; value?: number | string | string[] | null };
export type Group = { match: "all" | "any"; items: Item[] };
export type Item = Group | Condition;

export const isGroup = (item: Item): item is Group => "items" in item;

export const STATUSES: Record<string, string> = {
  active: "Active",
  retired: "Retired",
  home: "Home here",
  visiting: "Visiting",
  waiting: "Asking to make this home",
  creating: "Still in creation",
  approvals: "Has approvals waiting",
  pc: "Player character",
  npc: "NPC",
};

export const WHATS: Record<What, string> = {
  status: "Status",
  trait: "Trait",
  choice: "Clan, sect, focus…",
  title: "Title",
  player: "Player",
  xp: "Experience",
  count: "How many",
};

export const COMPARE: Op[] = ["lt", "lte", "eq", "gte", "gt"];
export const OP_LABELS: Record<Op, string> = {
  is: "is",
  is_not: "is not",
  family: "is in the family of",
  lt: "below",
  lte: "at most",
  eq: "exactly",
  gte: "at least",
  gt: "above",
  has: "has",
  lacks: "lacks",
};

/** What a new condition of each kind starts as. */
export function blank(what: What): Condition {
  switch (what) {
    case "status":
      return { what, op: "is", value: "active" };
    case "trait":
      return { what, which: null, op: "gte", value: 1 };
    case "choice":
      return { what, which: "clan", op: "is", value: [] };
    case "title":
      return { what, op: "has", value: null };
    case "player":
      return { what, op: "is", value: null };
    case "xp":
      return { what, which: "earned", op: "gte", value: 0 };
    case "count":
      return { what, which: "merits", op: "gte", value: 1 };
  }
}

/** Shown until someone changes it: retired characters stay in their troupes, but out of sight. */
export const DEFAULT_FILTER: Group = { match: "all", items: [{ what: "status", op: "is", value: "active" }] };

/** Whether a condition says enough to send; half-built ones wait. */
export function complete(c: Condition): boolean {
  switch (c.what) {
    case "status":
      return typeof c.value === "string";
    case "trait":
      return traitName(c.which) !== "" && (c.op === "has" || c.op === "lacks" || typeof c.value === "number");
    case "choice":
      return !!c.which && Array.isArray(c.value) && c.value.length > 0;
    case "title":
      return true;
    case "player":
      return typeof c.value === "string" && c.value !== "";
    case "xp":
    case "count":
      return !!c.which && typeof c.value === "number";
  }
}

/** The filter to send: complete conditions only, and no empty groups. */
export function ready(group: Group): Group {
  const items = group.items
    .map((item) => (isGroup(item) ? ready(item) : item))
    .filter((item) => (isGroup(item) ? item.items.length > 0 : complete(item)));
  return { match: group.match, items };
}

/** The key a condition's number comes back under, as the server writes it. */
export function columnOf(c: Condition): string | null {
  return c.what === "trait" || c.what === "xp" || c.what === "count" ? `${c.what}:${c.which}` : null;
}

export function columns(group: Group): Condition[] {
  const seen = new Set<string>();
  const found: Condition[] = [];
  for (const item of group.items) {
    for (const c of isGroup(item) ? columns(item) : [item]) {
      const key = columnOf(c);
      if (key && !seen.has(key)) {
        seen.add(key);
        found.push(c);
      }
    }
  }
  return found;
}

/** Names the sentence needs: categories by key, players by id. */
export type Names = { category: (key: string) => string; player: (id: string) => string };

/** "trait:skills/Occult" → "Occult"; a detail shows after a colon. */
export function traitName(which: string | null | undefined): string {
  const [, name = "", detail] = (which ?? "").split("/");
  return detail ? `${name}: ${detail}` : name;
}

export function columnLabel(c: Condition, names: Names): string {
  if (c.what === "trait") return traitName(c.which);
  if (c.what === "xp") return c.which === "unspent" ? "Unspent XP" : "XP earned";
  return names.category(c.which ?? "");
}

function list(values: string[], last: string): string {
  return values.length < 2 ? (values[0] ?? "") : `${values.slice(0, -1).join(", ")} ${last} ${values.at(-1)}`;
}

/** One condition as words: "Occult below 3", "Clan is Tremere or Giovanni". */
export function describe(c: Condition, names: Names): string {
  const op = OP_LABELS[c.op];
  switch (c.what) {
    case "status":
      return `${c.op === "is" ? "Is" : "Is not"} ${(STATUSES[String(c.value)] ?? String(c.value)).toLowerCase()}`;
    case "trait":
      return c.op === "has" || c.op === "lacks" ? `${c.op === "has" ? "Has" : "Lacks"} ${traitName(c.which)}` : `${traitName(c.which)} ${op} ${c.value}`;
    case "choice": {
      const values = Array.isArray(c.value) ? c.value : [];
      if (c.op === "family") return `${names.category(c.which ?? "")} is in the ${list(values, "or")} family`;
      return `${names.category(c.which ?? "")} ${c.op === "is" ? "is" : "is not"} ${list(values, "or")}`;
    }
    case "title":
      if (!c.value) return c.op === "has" ? "Holds a title" : "Holds no title";
      return `${c.op === "has" ? "Holds" : "Does not hold"} the title ${c.value}`;
    case "player":
      return `Player ${op} ${names.player(String(c.value ?? ""))}`;
    case "xp":
      return `${c.which === "unspent" ? "Unspent XP" : "XP earned"} ${op} ${c.value}`;
    case "count":
      return `Number of ${names.category(c.which ?? "").toLowerCase()} ${op} ${c.value}`;
  }
}

/** The whole filter as a sentence; sub-groups in brackets. */
export function sentence(group: Group, names: Names, nested = false): string {
  const parts = group.items.map((item) => (isGroup(item) ? sentence(item, names, true) : describe(item, names)));
  const joined = parts.join(group.match === "all" ? ", and " : ", or ");
  return nested && parts.length > 1 ? `(${joined})` : joined;
}

/** The filter as it travels in the URL, so a reload, Back or a shared link keep it. */
export function encode(group: Group): string {
  return JSON.stringify(group);
}

export function decode(text: string | null): Group {
  if (text === null) return DEFAULT_FILTER;
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && "items" in parsed && Array.isArray((parsed as Group).items)) return parsed as Group;
  } catch {
    // A mangled link falls back to the default.
  }
  return DEFAULT_FILTER;
}

import type { BoonEventOut, BoonOut, BoonKindCount } from "./api/types";

/** Where the book has boons: what they are, their kinds, and boon breakers. */
export const BOON_PAGE = "MET: VTM pp. 395-397";

export type BoonKind = BoonOut["kind"];
export type SettledHow = NonNullable<BoonOut["settled_how"]>;
export type BoonView = "open" | "departed" | "settled" | "void" | "pending" | "all";
export type Party = BoonOut["debtor"];

/** The five kinds, lightest first, each with what it is for (pp. 396-397). */
export const KINDS: { value: BoonKind; label: string; meaning: string }[] = [
  {
    value: "trivial",
    label: "Trivial",
    meaning: "A small favour, an introduction or a faux pas forgiven: repaid in a night.",
  },
  {
    value: "minor",
    label: "Minor",
    meaning: "Real time or effort at little risk: repaid within two games or a month.",
  },
  {
    value: "major",
    label: "Major",
    meaning: "A large debt of time, resources or standing: repaid within six games or three months.",
  },
  {
    value: "blood",
    label: "Blood",
    meaning: "Repaid only by shedding blood, or risking all, for the creditor.",
  },
  {
    value: "life",
    label: "Life",
    meaning: "For saving the debtor's life: rare, and owed until a life is saved in return.",
  },
];

export const SETTLED: { value: SettledHow; label: string; meaning: string }[] = [
  {
    value: "called_in",
    label: "Called in",
    meaning: "The creditor called it in and the debtor repaid it.",
  },
  {
    value: "forgiven",
    label: "Forgiven",
    meaning: "The creditor forgave it.",
  },
  {
    value: "ignored",
    label: "Formally ignored",
    meaning: "The debtor formally ignored it, which costs status for a major boon or greater (p. 397).",
  },
];

/** The ledger's views, as its tabs. Pending boons come with review (#687), so that tab shows only when there are some. */
export const VIEWS: { value: BoonView; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "departed", label: "Departed" },
  { value: "settled", label: "Settled" },
  { value: "void", label: "Void" },
  { value: "pending", label: "Pending" },
  { value: "all", label: "All" },
];

const STANDINGS: Record<NonNullable<Party["standing"]>, string> = {
  active: "Active",
  final_death: "Final Death",
  off_field: "Off-field",
  inactive: "Inactive",
  retired: "Retired",
};

export function kindName(kind: BoonKind): string {
  return KINDS.find((k) => k.value === kind)?.label ?? kind;
}

/** A party's name, with how it left play when it has: "Mercer (Final Death)". A name only is just the name. */
export function partyName(party: Party): string {
  if (!party.standing || party.standing === "active") return party.name;
  return `${party.name} (${STANDINGS[party.standing]})`;
}

/** "Agnes owes Bram". */
export function owes(boon: Pick<BoonOut, "debtor" | "creditor">): string {
  return `${boon.debtor.name} owes ${boon.creditor.name}`;
}

/** Where a boon stands now, for its row: "Settled: called in", "Void", or "" while it stands. */
export function stateText(boon: Pick<BoonOut, "state" | "settled_how" | "departed">): string {
  if (boon.state === "settled") return `Settled: ${(SETTLED.find((s) => s.value === boon.settled_how)?.label ?? "").toLowerCase()}`;
  if (boon.state === "void") return "Void";
  if (boon.state === "pending") return "Pending";
  return boon.departed ? "Involves someone departed" : "";
}

const EVENTS: Record<BoonEventOut["kind"], string> = {
  registered: "Registered",
  edited: "Edited",
  traded: "Traded",
  passed_on: "Passed on",
  settled: "Settled",
  voided: "Made void",
  reopened: "Reopened",
};

export function eventName(kind: BoonEventOut["kind"]): string {
  return EVENTS[kind];
}

const FIELDS: Record<string, string> = {
  debtor: "Debtor",
  creditor: "Creditor",
  kind: "Kind",
  made_on: "Date",
  reason: "Reason",
  conditions: "Conditions",
  notify_on_trade: "Tell the debtor if traded",
  staff_note: "Staff note",
  state: "State",
};

/** One change in a boon's log: "Kind: Minor → Major". Empty text reads "(none)". */
export function changeText(change: { field: string; before: string; after: string }): string {
  const label = FIELDS[change.field] ?? change.field;
  return `${label}: ${change.before || "(none)"} → ${change.after || "(none)"}`;
}

/** A summary of standing boons by kind, lightest first: "2 minor, 1 major", or "none". */
export function countsText(counts: BoonKindCount[]): string {
  if (counts.length === 0) return "none";
  return counts.map((c) => `${c.count} ${kindName(c.kind).toLowerCase()}`).join(", ");
}

/** The actions a boon allows in its state: a standing one is traded, passed on, settled or voided; a closed one reopened. */
export function actionsFor(state: BoonOut["state"]): ("edit" | "trade" | "pass" | "settle" | "void" | "reopen")[] {
  if (state === "registered") return ["edit", "trade", "pass", "settle", "void"];
  if (state === "pending") return ["edit", "void"];
  if (state === "settled") return ["edit", "void", "reopen"];
  return ["edit", "reopen"];
}

/** A row of the quick entry, as the form holds it. */
export type EntryRow = {
  debtor: { who: string; name: string };
  creditor: { who: string; name: string };
  kind: BoonKind;
  made_on: string;
  reason: string;
  conditions: string;
  notify_on_trade: boolean;
  count: number;
};

export function emptyRow(madeOn: string): EntryRow {
  return {
    debtor: { who: "", name: "" },
    creditor: { who: "", name: "" },
    kind: "minor",
    made_on: madeOn,
    reason: "",
    conditions: "",
    notify_on_trade: false,
    count: 1,
  };
}

/** Whether a row names someone: an untouched row is left out of what is registered. */
export function rowStarted(row: EntryRow): boolean {
  return Boolean(row.debtor.who || row.creditor.who || row.reason.trim() || row.conditions.trim());
}

/** How many boons the rows make, counting each row's count. */
export function rowsTotal(rows: EntryRow[]): number {
  return rows.filter(rowStarted).reduce((n, r) => n + Math.max(1, r.count || 1), 0);
}

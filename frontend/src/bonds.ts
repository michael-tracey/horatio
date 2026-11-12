import type { BondOut, BondReportOut, TroupeOut } from "./api/types";

/** Where the book has the blood bond's three drinks. */
export const BOND_PAGE = "MET: VTM p. 295";

export type BondSetting = TroupeOut["blood_bonds"];
export type BondSource = BondOut["entries"][number]["source"];

/** The troupe's Blood bonds setting, each with what it means. */
export const BOND_SETTINGS: { value: NonNullable<BondSetting>; label: string; meaning: string }[] = [
  { value: "off", label: "Off", meaning: "Horatio doesn't track blood bonds: no Bonds card on sheets and no Bonds screen." },
  { value: "staff", label: "Staff manages", meaning: "Running staff record each drink, enter bonds that already stand and break them." },
  {
    value: "players_report",
    label: "Players report and staff approves",
    meaning: "Players report their characters' drinks, from the sheet or the Play View; each waits in Approvals until staff approve it.",
  },
  {
    value: "players_manage",
    label: "Players manage",
    meaning:
      "Players record the drinks their characters take, and they count at once. One the regnant's player records waits for the thrall's player to confirm. Staff can still change or remove any drink.",
  },
];

/** Where a player says a drink happened. */
export const PLAYER_SOURCES: { value: BondReportOut["source"]; label: string }[] = [
  { value: "game", label: "At a game" },
  { value: "downtime", label: "In a downtime" },
];

/** A reported drink, as its line reads: "Agnes drank Bram's blood on 3 Nov 2026"; or a meeting (#665): "Agnes and Bram met on 3 Nov 2026". */
export function reportLine(report: Pick<BondReportOut, "thrall" | "regnant"> & { kind?: BondReportOut["kind"] }, night: string): string {
  if (report.kind === "meeting") return `${report.thrall.name} and ${report.regnant.name} met on ${night}`;
  return `${report.thrall.name} drank ${report.regnant.name}'s blood on ${night}`;
}

/** Where a reported drink stands, for the player who sees it. */
export function reportState(report: Pick<BondReportOut, "status" | "waiting_on" | "thrall" | "reason">): string {
  if (report.status === "approved") return "Counted";
  if (report.status === "withdrawn") return "Withdrawn";
  if (report.status === "declined") return report.reason ? `Declined: ${report.reason}` : "Declined";
  return report.waiting_on === "staff" ? "Waiting for the storytellers" : `Waiting for ${report.thrall.name}'s player to confirm`;
}

/** What became of a drink just reported, for the toast. */
export function reportedText(outcome: "recorded" | "staff" | "thrall", level: number | null, thrall: string): string {
  if (outcome === "recorded") return `Recorded: ${levelName(level ?? 1).toLowerCase()}.`;
  if (outcome === "staff") return "Sent to the storytellers to approve.";
  return `Sent to ${thrall}'s player to confirm.`;
}

export const SOURCES: { value: BondSource; label: string }[] = [
  { value: "game", label: "At a game" },
  { value: "downtime", label: "In a downtime" },
  { value: "staff", label: "Told to staff" },
];

const LEVELS: Record<number, { name: string; feel: string; effect: string }> = {
  1: { name: "First drink", feel: "you're drawn to them", effect: "No effect in play, but play the pull." },
  2: {
    name: "Second drink",
    feel: "you can't easily turn against them",
    effect: "−1 to Social defence against their powers. Harming them costs 1 Willpower an hour.",
  },
  3: {
    name: "Full bond",
    feel: "they come before everyone else",
    effect: "−3 to Social and Mental defence against their powers. Acting against their wishes costs 1 Willpower; harming them, 3 Willpower an hour.",
  },
};

/** A bond's level as its thrall feels it: "Second drink: you can't easily turn against them", and what it does in play. */
export function levelText(level: number): { line: string; effect: string } {
  const l = LEVELS[Math.min(Math.max(level, 1), 3)]!;
  return { line: `${l.name}: ${l.feel}`, effect: l.effect };
}

/** A bond's level, short: "First drink", "Full bond". */
export function levelName(level: number): string {
  return LEVELS[Math.min(Math.max(level, 1), 3)]!.name;
}

/** What became of a bond no longer felt, or that it's still felt. */
export function statusText(bond: Pick<BondOut, "status" | "ended_reason">): string {
  if (bond.status === "broken") return `Broken: ${bond.ended_reason}`;
  if (bond.status === "ended") return bond.ended_reason ? `Ended: ${bond.ended_reason}` : "Ended";
  if (bond.status === "fading") return "Fading";
  return "Active";
}

export const isOpen = (bond: Pick<BondOut, "status">) => bond.status === "active" || bond.status === "fading";

/** A faded bond whose thrall's player isn't told yet: their sheet still shows it (#662). */
export const untold = (bond: Pick<BondOut, "status" | "fade_reason" | "thrall_told">) => bond.status === "ended" && !!bond.fade_reason && !bond.thrall_told;

/** A bond staff still have something to watch: one felt, one a player still sees as it was. */
export const watched = (bond: Pick<BondOut, "status" | "fade_reason" | "thrall_told" | "kept_for_regnant">) =>
  isOpen(bond) || untold(bond) || !!bond.kept_for_regnant;

/** The bonds grouped under each thrall, or each regnant, by name; open bonds first in each group. */
export function groupBonds(bonds: BondOut[], by: "thrall" | "regnant"): { name: string; bonds: BondOut[] }[] {
  const groups = new Map<string, { name: string; bonds: BondOut[] }>();
  for (const bond of bonds) {
    const side = bond[by];
    const key = side.character_id ?? `name:${side.name.toLowerCase()}`;
    const group = groups.get(key) ?? { name: side.name, bonds: [] };
    group.bonds.push(bond);
    groups.set(key, group);
  }
  const other = by === "thrall" ? "regnant" : "thrall";
  return [...groups.values()]
    .map((g) => ({ ...g, bonds: [...g.bonds].sort((a, b) => Number(isOpen(b)) - Number(isOpen(a)) || a[other].name.localeCompare(b[other].name)) }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** A side of a bond as the web of bonds keys it (#708): the character's id, or "name:" and the name in lower case. */
export const partyKey = (party: { character_id: string | null; name: string }) => party.character_id ?? `name:${party.name.trim().toLowerCase()}`;

/** A side picked in WhoPicker ("c:<id>" or "name"), as the API takes it; null until one is. */
export function partyIn(who: string, name: string): { character_id?: string; name: string } | null {
  if (who.startsWith("c:")) return { character_id: who.slice(2), name: "" };
  if (who === "name" && name.trim()) return { name: name.trim() };
  return null;
}

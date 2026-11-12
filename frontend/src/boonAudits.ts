import type { BoonAuditOut } from "./api/types";

/**
 * Audits of a character's boons (#690): what the troupe's ledger held of them on a
 * night, kept as it was. Standing is as the court knows it: departed only as the
 * Who's Who lists them, with why only for Final Death or Off-field.
 */
export type CourtStanding = NonNullable<BoonAuditOut["standing"]>;
export type AuditLine = BoonAuditOut["owes"][number];

export const COURT_STANDING: Record<CourtStanding, string> = {
  active: "Active",
  final_death: "Final Death",
  off_field: "Off-field",
  gone: "No longer with us",
};

export const AUDIT_STATUS: Record<AuditLine["status"], string> = {
  standing: "Standing",
  settled: "Settled",
  departed: "Departed",
};

/** A weight as the standings show it: "4", "1.5". */
export function weight(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
}

/** "owes 2 (weighing 4) · is owed 1 (weighing 5)", as the registry's audits head a page. */
export function auditCounts(audit: Pick<BoonAuditOut, "owes_count" | "owed_count" | "owes_weight" | "owed_weight">): string {
  const side = (count: number, w: number) => `${count}${count ? ` (weighing ${weight(w)})` : ""}`;
  return `owes ${side(audit.owes_count, audit.owes_weight)} · is owed ${side(audit.owed_count, audit.owed_weight)}`;
}

/** What became of a boon, as an audit lists it: "Settled (called in)". */
export function lineStatus(line: AuditLine): string {
  const how = { called_in: "called in", forgiven: "forgiven", ignored: "formally ignored" };
  return line.status === "settled" && line.settled_how ? `Settled (${how[line.settled_how]})` : AUDIT_STATUS[line.status];
}

/** Who and what the audit is of, in one line: "Active · Toreador · Neonate". */
export function auditWho(audit: Pick<BoonAuditOut, "standing" | "clan" | "age">): string {
  return [audit.standing ? COURT_STANDING[audit.standing] : null, audit.clan, audit.age].filter(Boolean).join(" · ");
}

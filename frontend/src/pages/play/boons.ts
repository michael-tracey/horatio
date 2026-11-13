import type { PlayBoonIn, PlayBoonOut, PlayReportOut } from "../../api/types";
import { kindName, SETTLED } from "../../boons";

/** How a creditor's player may settle a boon in the Play View (#686): formally ignoring one is its debtor's doing (p. 397). */
export type PlayerSettles = "called_in" | "forgiven";

export const playerSettles = SETTLED.filter((s): s is (typeof SETTLED)[number] & { value: PlayerSettles } => s.value === "called_in" || s.value === "forgiven");

/** "a minor boon", "3 major boons": every kind starts with a consonant. */
export function aBoon(kind: PlayBoonIn["kind"], count: number): string {
  const name = kindName(kind).toLowerCase();
  return count === 1 ? `a ${name} boon` : `${count} ${name} boons`;
}

/** A side's boons: those standing, then those settled, each as the server sends them (newest first). */
export function standingFirst(boons: readonly PlayBoonOut[]): { standing: PlayBoonOut[]; settled: PlayBoonOut[] } {
  return { standing: boons.filter((b) => b.state === "registered"), settled: boons.filter((b) => b.state === "settled") };
}

/** "Settled: called in, Sat 3 Oct 2026. For influence." */
export function settledText(boon: Pick<PlayBoonOut, "settled_how" | "settled_at" | "settled_note">, day: (at: string) => string): string {
  const how = (SETTLED.find((s) => s.value === boon.settled_how)?.label ?? "").toLowerCase();
  const when = boon.settled_at ? `, ${day(boon.settled_at)}` : "";
  const note = boon.settled_note ? ` ${boon.settled_note.replace(/[.\s]*$/, "")}.` : "";
  return `Settled${how ? `: ${how}` : ""}${when}.${note}`;
}

/**
 * The toast after a report: "Reported to Elysium's ledger: Agnes owes Bram a minor
 * boon." Where the troupe holds reports for review (#687): "Sent to Elysium's staff
 * for review: …".
 */
export function reportedText(
  name: string,
  other: string,
  direction: PlayBoonIn["direction"],
  kind: PlayBoonIn["kind"],
  count: number,
  troupe: string,
  waits = false,
): string {
  const [debtor, creditor] = direction === "owes" ? [name, other] : [other, name];
  const where = waits ? `Sent to ${troupe}'s staff for review` : `Reported to ${troupe}'s ledger`;
  return `${where}: ${debtor} owes ${creditor} ${aBoon(kind, count)}.`;
}

/** A report of the player's that waits for review or wasn't accepted (#687): "Agnes owes Bram a minor boon, 3 Oct 2026." */
export function reportLine(report: Pick<PlayReportOut, "direction" | "other" | "kind">, name: string): string {
  const [debtor, creditor] = report.direction === "owes" ? [name, report.other] : [report.other, name];
  return `${debtor} owes ${creditor} ${aBoon(report.kind, 1)}`;
}

import type { Attendee } from "../../api/types";

/**
 * Game-night check-in (issue #421): the door's code, the link its QR code holds, and
 * the book's XP guidance for the award.
 */

/** Where a door's code leads: the check-in page, which sends a signed-out person to sign in first and back. */
export function checkInPath(code: string): string {
  return `/check-in/${encodeURIComponent(code)}`;
}

/** The link the door's QR code holds, on this site. */
export function checkInUrl(origin: string, code: string): string {
  return `${origin}${checkInPath(code)}`;
}

/** A code as a sign shows it, in two halves to read aloud: "ABC DEF". */
export function spacedCode(code: string): string {
  return code.length > 3 ? `${code.slice(0, 3)} ${code.slice(3)}` : code;
}

/** A code as typed, in capitals, without spaces or dashes. */
export function tidyCode(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

/** The characters at the game an award of `amount` would give XP to: those whose home is this troupe. */
export function toAward(attendees: Attendee[]): Attendee[] {
  return attendees.filter((a) => a.home);
}

/** Those an award of `amount` would take past the book's monthly guidance, by name. */
export function pastMonthly(attendees: Attendee[], amount: number, monthly: number): string[] {
  return toAward(attendees)
    .filter((a) => a.month_xp + amount > monthly)
    .map((a) => a.character_name);
}

/** "Agnes", "Agnes and Bram", "Agnes, Bram and Cleo". */
export function names(list: string[]): string {
  if (list.length <= 1) return list.join("");
  return `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`;
}

/** How many came, for a line beside a game: "Nobody checked in yet", "1 checked in", "3 checked in". */
export function checkedInText(count: number): string {
  return count === 0 ? "Nobody checked in yet" : `${count} checked in`;
}

/** The squares of a QR code, as one SVG path: a 1×1 square for each dark module. */
export function qrPath(modules: boolean[][]): string {
  const parts: string[] = [];
  modules.forEach((row, y) =>
    row.forEach((dark, x) => {
      if (dark) parts.push(`M${x} ${y}h1v1h-1z`);
    }),
  );
  return parts.join("");
}

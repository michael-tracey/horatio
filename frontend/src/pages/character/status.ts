import type { DerivedOut, EndingOut, PatronChoiceOut, SuppressionOut } from "../../api/types";

/** "2 more games", "1 more game". */
function games(n: number): string {
  return `${n} more game${n === 1 ? "" : "s"}`;
}

/**
 * When a held status ends, in a line: "Ends after 2 more games, and not before 26
 * Nov 2026", "Ends with the game it was given at", "Lasts while Warned is held; then
 * after 2 more games". `day` writes an API day ("2026-11-26").
 */
export function endingText(ending: EndingOut, day: (d: string) => string): string {
  if (ending.this_game) return ending.games_left ? "Ends with the game it was given at" : "Ends now";
  const after = [
    ending.games_left ? `after ${games(ending.games_left)}` : "",
    ending.not_before ? `not before ${day(ending.not_before)}` : "",
  ].filter(Boolean);
  const then = after.length ? after.join(", and ") : "once nothing else holds it";
  if (ending.while_held) return `Lasts while ${ending.while_held} is held; then ends ${then}`;
  return after.length ? `Ends ${then}` : "Ends now";
}

/**
 * What suppresses the fleeting status, and when it comes back: "Fleeting status
 * suppressed for defying a Commander (Defied the Prince): back after 2 more games,
 * and not before 26 Nov 2026."
 */
export function suppressedText(s: Pick<SuppressionOut, "text" | "reason" | "ending">, day: (d: string) => string): string {
  const why = `Fleeting status suppressed ${s.text}${s.reason ? ` (${s.reason})` : ""}`;
  if (!s.ending) return `${why}.`;
  const back = s.ending.this_game ? "back when the game ends" : endingText(s.ending, day).replace(/^Ends /, "back ");
  return `${why}: ${back}.`;
}

/**
 * Why the fleeting cap is what it is, when it is not the usual 5: "Cap: a lesser
 * ban: 3 · Tainted Embrace: 1 less". Empty when nothing changes it.
 */
export function capText(why: string[] | undefined): string {
  return why?.length ? `Cap: ${why.join(" · ")}` : "";
}

/** A character no sect has Accepted, holding a sect's fleeting status through a merit. */
export function outsiderText(s: { outsider_sect?: string | null; outsider_through?: string | null }): string {
  return `Accepted by no sect. As ${s.outsider_through ?? "a merit"} allows, it holds fleeting ${s.outsider_sect} status.`;
}

/** A source of derived status and what it gives: "Prince: Authority, Commander, Sovereign". */
export type DerivedSource = { key: string; source: string; kind: DerivedOut["kind"]; troupe: string | null; status: DerivedOut[] };

/** Derived status grouped by where it comes from, in the order given. */
export function bySource(derived: DerivedOut[]): DerivedSource[] {
  const found = new Map<string, DerivedSource>();
  for (const d of derived) {
    const key = `${d.kind}/${d.troupe_id ?? ""}/${d.source}`;
    const group = found.get(key) ?? { key, source: d.source, kind: d.kind, troupe: d.troupe_name, status: [] };
    group.status.push(d);
    found.set(key, group);
  }
  return [...found.values()];
}

/** A patron as the list shows it: "Elena Varga (Prince)", or the name alone. */
export function patronLabel(choice: Pick<PatronChoiceOut, "name" | "title">): string {
  return choice.title ? `${choice.name} (${choice.title})` : choice.name;
}

/** The patrons matching what was typed, by name or title, those starting with it first. */
export function findPatrons<T extends Pick<PatronChoiceOut, "name" | "title">>(choices: T[], typed: string): T[] {
  const q = typed.trim().toLocaleLowerCase();
  if (!q) return choices;
  const found = choices.filter((c) => patronLabel(c).toLocaleLowerCase().includes(q));
  const starts = (c: T) => (c.name.toLocaleLowerCase().startsWith(q) ? 0 : 1);
  return [...found].sort((a, b) => starts(a) - starts(b));
}

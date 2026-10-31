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

/** The kinds of status, in the order the Status & Titles tab lists them. */
const TYPES = ["Accepted", "Abiding", "Innate", "Fleeting", "Negative"];

/** Where a status's type comes in the list: unknown types last. */
export function typeOrder(type: string): number {
  const i = TYPES.indexOf(type);
  return i < 0 ? TYPES.length : i;
}

/**
 * Where a derived status comes from, in words: "the title Seneschal (while the
 * Prince is absent)", "the social age Elder", "the Loyalist faction", or the merit
 * that gives it. `home` is the home troupe's name: a title held elsewhere says where.
 */
export function sourceText(d: Pick<DerivedOut, "kind" | "source" | "condition" | "troupe_name">, home: string | null): string {
  const where = d.troupe_name && d.troupe_name !== home ? ` in ${d.troupe_name}` : "";
  const what =
    d.kind === "title"
      ? `the title ${d.source}${where}`
      : d.kind === "social_age"
        ? `the social age ${d.source}`
        : d.kind === "faction"
          ? `the ${d.source} faction`
          : d.source;
  return d.condition ? `${what} (${d.condition})` : what;
}

/** A status the character's title, social age, faction or merits give, with every source of it. */
export type DerivedLine = { name: string; type: string; sources: string[] };

/**
 * Derived status as the list shows it, a line per status: the same status from a
 * title and a social age is one line naming both. Abiding before innate, and
 * otherwise in the order given.
 */
export function derivedLines(derived: DerivedOut[], home: string | null): DerivedLine[] {
  const found = new Map<string, DerivedLine>();
  for (const d of derived) {
    const key = `${d.type}/${d.name}`;
    const line = found.get(key) ?? { name: d.name, type: d.type, sources: [] };
    const source = sourceText(d, home);
    if (!line.sources.includes(source)) line.sources.push(source);
    found.set(key, line);
  }
  return [...found.values()].sort((a, b) => typeOrder(a.type) - typeOrder(b.type));
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

import type { TitleOut } from "../../api/types";

/** Titles in groups by sect: the troupe's sects in order, then any other sect a
 * title is still held in, then the titles of any sect (null). Empty groups are left out. */
export function titleGroups<T extends Pick<TitleOut, "sect">>(sects: string[], titles: T[]): [string | null, T[]][] {
  const others = [...new Set(titles.map((t) => t.sect).filter((s): s is string => !!s && !sects.includes(s)))].sort();
  return [...sects, ...others, null]
    .map((sect): [string | null, T[]] => [sect, titles.filter((t) => t.sect === sect)])
    .filter(([, list]) => list.length > 0);
}

type Gives = Pick<TitleOut, "status" | "choose_one" | "while_absent">;

/** The status a title gives, a phrase each: "Authority", "Blessed or Enforcer, chosen each game". */
export function titleStatusWords(t: Gives): string[] {
  return [
    ...t.status,
    ...(t.choose_one.length ? [`${t.choose_one.join(" or ")}, chosen each game`] : []),
    ...t.while_absent.map((a) => `${a.status.join(", ")} while the ${a.title} is away`),
  ];
}

/** What a title is, beyond the status it gives. */
export type TitleWhat = Pick<TitleOut, "alias_of" | "clan" | "gives_none" | "no_rules_yet">;

/**
 * What a title gives, in a line: "Gives Prominent · Noble · Guardian"; or why it
 * gives none, in the rules' words; "A Tremere title: no sect status"; or "No rules
 * yet" for a title no book describes (the Independent Alliance's). `words` is the
 * status it gives, as `titleStatusWords` or the API word it.
 */
export function titleGives(words: string[], t: TitleWhat): string {
  if (t.no_rules_yet) return "No rules yet: no book describes it, so it gives no status";
  if (words.length) return `Gives ${words.join(" · ")}`;
  if (t.gives_none) return t.gives_none.replace(/\.$/, "");
  if (t.clan) return `A ${t.clan} title: it gives no sect status`;
  return "Gives no status";
}

/** A title's other name, after its name: "another name for Harpy". */
export const aliasText = (t: Pick<TitleOut, "alias_of">) => (t.alias_of ? `another name for ${t.alias_of}` : null);

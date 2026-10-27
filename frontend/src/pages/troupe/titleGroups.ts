import type { TitleOut } from "../../api/types";

/** Titles in groups by sect: the troupe's sects in order, then any other sect a
 * title is still held in, then the titles of any sect (null). Empty groups are left out. */
export function titleGroups<T extends Pick<TitleOut, "sect">>(sects: string[], titles: T[]): [string | null, T[]][] {
  const others = [...new Set(titles.map((t) => t.sect).filter((s): s is string => !!s && !sects.includes(s)))].sort();
  return [...sects, ...others, null]
    .map((sect): [string | null, T[]] => [sect, titles.filter((t) => t.sect === sect)])
    .filter(([, list]) => list.length > 0);
}

/** What a title gives, in words: "Authority · Commander", "Blessed or Enforcer, chosen each game". */
export function titleStatus(t: Pick<TitleOut, "status" | "choose_one" | "while_absent">): string {
  return [
    ...t.status,
    ...(t.choose_one.length ? [`${t.choose_one.join(" or ")}, chosen each game`] : []),
    ...t.while_absent.map((a) => `${a.status.join(", ")} while the ${a.title} is away`),
  ].join(" · ");
}

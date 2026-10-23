import type { SharedBackgroundOut, SharedEntryOut } from "../../api/types";

export const dotsText = (dots: number) => (dots === 1 ? "1 dot" : `${dots} dots`);

/** What an entry did: "put in 2 dots", "took out 1 dot", "drew on it". */
export function actionText(entry: Pick<SharedEntryOut, "kind" | "dots">): string {
  if (entry.kind === "use") return "drew on it";
  return `${entry.kind === "contribution" ? "put in" : "took out"} ${dotsText(entry.dots ?? 0)}`;
}

export const entryText = (entry: Pick<SharedEntryOut, "kind" | "dots" | "name">) => `${entry.name} ${actionText(entry)}`;

/** The group's rating: "3 of 5 dots", or "5 of 5 dots, from 7 put in" when more are in than count. */
export function totalText(shared: Pick<SharedBackgroundOut, "total" | "put_in" | "most">): string {
  const total = `${shared.total} of ${shared.most} dots`;
  return shared.put_in > shared.total ? `${total}, from ${shared.put_in} put in` : total;
}

/** "Sharing it: Agnes 2 dots, Bram 1 dot. Took their dots out: Cora." */
export function sharersText(sharers: Pick<SharedBackgroundOut["sharers"][number], "name" | "dots">[]): string {
  const sharing = sharers.filter((s) => s.dots > 0);
  const out = sharers.filter((s) => s.dots <= 0);
  const parts = [sharing.length ? `Sharing it: ${sharing.map((s) => `${s.name} ${dotsText(s.dots)}`).join(", ")}.` : "No one has dots in it now."];
  if (out.length) parts.push(`Took their dots out: ${out.map((s) => s.name).join(", ")}.`);
  return parts.join(" ");
}

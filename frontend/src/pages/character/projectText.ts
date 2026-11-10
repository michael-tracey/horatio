import type { ProjectOut } from "../../api/types";

export const PROJECT_KINDS: Record<ProjectOut["kind"], string> = { path_change: "Path change", research: "Research", other: "Other" };

const STATUSES: Record<string, string> = { proposed: "Proposed", active: "Under way", finished: "Finished", dropped: "Stopped" };

export const projectStatus = (status: string) => STATUSES[status] ?? status;

const actions = (n: number) => `${n} ${n === 1 ? "action" : "actions"}`;

/** "Research · 4 of 9 actions · at least 1 a month · started over once": its kind and where it stands. */
export function projectLine(p: ProjectOut): string {
  const parts = [PROJECT_KINDS[p.kind], `${p.progress} of ${actions(p.target)}`];
  if (p.kind === "path_change") parts.push(p.with_teacher ? "with a teacher" : "without a teacher");
  if (p.monthly_minimum) parts.push(`at least ${p.monthly_minimum} a month`);
  if (p.restarts) parts.push(`started over ${p.restarts === 1 ? "once" : `${p.restarts} times`}`);
  return parts.join(" · ");
}

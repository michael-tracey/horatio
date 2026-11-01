import type { Role } from "../../api/types";

const LABELS: Record<Role, string> = {
  lead_storyteller: "Lead Storyteller",
  storyteller: "Storyteller",
  assistant_storyteller: "Assistant Storyteller",
  narrator: "Narrator",
};

export function roleLabel(role: Role): string {
  return LABELS[role];
}

/** What each role may do, in a line, from CONTEXT.md. */
export const ROLE_LINES: Record<Role, string> = {
  lead_storyteller: "The troupe's one owner: everything a storyteller does, and renames, describes or archives the troupe.",
  storyteller: "Runs the troupe: manages its staff, house rules, connectors and profile, and everything an assistant does.",
  assistant_storyteller: "Everything a storyteller does except manage staff, house rules and connectors, or edit the profile.",
  narrator: "Answers the downtime actions assigned to them or to any narrator. Never sees character sheets.",
};

/** What a role may do in a troupe; mirrors horatio/permissions.py for showing the right screens. */
export function abilities(role: Role | null | undefined, isCustodian: boolean) {
  const lead = isCustodian || role === "lead_storyteller";
  const storyteller = lead || role === "storyteller";
  const running = storyteller || role === "assistant_storyteller";
  const staff = running || role === "narrator";
  return { lead, storyteller, running, staff };
}

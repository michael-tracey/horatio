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

/** What a role may do in a troupe; mirrors horatio/permissions.py for showing the right screens. */
export function abilities(role: Role | null | undefined, isCustodian: boolean) {
  const lead = isCustodian || role === "lead_storyteller";
  const storyteller = lead || role === "storyteller";
  const running = storyteller || role === "assistant_storyteller";
  const staff = running || role === "narrator";
  return { lead, storyteller, running, staff };
}

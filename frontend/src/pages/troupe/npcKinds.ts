import type { components } from "../../api/schema";

export type NpcKind = components["schemas"]["NpcKindOut"];
export type Npc = components["schemas"]["NpcOut"];
export type NpcForm = "sheeted" | "stock";

/** How the kinds are grouped in the New NPC form, in order. */
export const KIND_GROUPS: [string, string][] = [
  ["vampire", "Vampires and ghouls"],
  ["mortal", "Mortals"],
  ["hunter", "Vampire hunters"],
  ["supernatural", "Other supernaturals"],
  ["bloodline", "Vampire bloodlines"],
  ["custom", "Other"],
];

export const FORM_NAMES: Record<NpcForm, string> = { sheeted: "Sheeted", stock: "Stock" };

/** The kinds in each group, leaving out empty groups. */
export function groupedKinds(kinds: NpcKind[]): { label: string; kinds: NpcKind[] }[] {
  return KIND_GROUPS.map(([key, label]) => ({ label, kinds: kinds.filter((k) => k.group === key) })).filter((g) => g.kinds.length);
}

/** "Rage 10, up to 3 a turn, regains 1 every five turns"; "Blood 5, cannot be spent". */
export function resourceText(resource: NpcKind["resource"]): string {
  const spend = resource.per_turn === 0 ? "cannot be spent" : resource.per_turn === 1 ? "1 a turn" : `up to ${resource.per_turn} a turn`;
  return [`${resource.name} ${resource.size}`, spend, resource.regains && `regains ${resource.regains}`].filter(Boolean).join(", ");
}

/** "pp. 494–495" or "p. 505". */
export function kindPages(kind: Pick<NpcKind, "page" | "to_page">): string {
  return kind.to_page ? `pp. ${kind.page}–${kind.to_page}` : `p. ${kind.page}`;
}

export type NpcFilter = { kind: string; form: "" | NpcForm };

/** The NPCs a filter shows: "" for any kind or form. */
export function filterNpcs<T extends Pick<Npc, "npc_kind" | "npc_form">>(npcs: T[], filter: NpcFilter): T[] {
  return npcs.filter((n) => (!filter.kind || n.npc_kind === filter.kind) && (!filter.form || n.npc_form === filter.form));
}

/** The kinds among some NPCs, each once, by name: what the kind filter offers. */
export function kindsIn(npcs: Pick<Npc, "npc_kind" | "npc_kind_name">[]): [string, string][] {
  const found = new Map<string, string>();
  for (const n of npcs) if (n.npc_kind && !found.has(n.npc_kind)) found.set(n.npc_kind, n.npc_kind === "custom" ? "Custom" : (n.npc_kind_name ?? n.npc_kind));
  return [...found].sort((a, b) => a[1].localeCompare(b[1]));
}

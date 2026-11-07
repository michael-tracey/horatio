import type { FeedingIn, KeywordChoiceOut, PatrolIn } from "../../api/types";

/** An action's extra fields, as the form keeps them. */
type Fields = Record<string, unknown> | undefined;

/** Where each field a keyword asks for is kept in an answer's fields (backend: horatio.keywords). */
export const FIELD_KEYS: Record<string, string[]> = {
  character: [],
  target: ["subject"],
  territory: ["territory"],
  trait: ["learn", "owed_action_id"],
  teacher: ["teacher"],
  item: ["item"],
};

/** What each field is called where a player is warned it will go. */
const FIELD_WORDS: Record<string, string> = {
  subject: "what it is aimed at",
  territory: "the territory",
  learn: "what to learn",
  owed_action_id: "what to learn",
  teacher: "the teacher",
  item: "the item wanted",
};

export function keywordOf(fields: Fields): string | null {
  const raw = fields?.keyword;
  return typeof raw === "string" && raw ? raw : null;
}

export function textOf(fields: Fields, key: string): string {
  const raw = fields?.[key];
  return typeof raw === "string" ? raw : "";
}

/** The fields with `key` set, or left out when `value` is empty. */
export function withText(fields: Fields, key: string, value: string): Record<string, unknown> {
  const { [key]: _old, ...rest } = fields ?? {};
  return value ? { ...rest, [key]: value } : rest;
}

/** The keyword-held fields `fields` has that `keyword` doesn't ask for: what changing to it drops. */
export function dropped(fields: Fields, keyword: KeywordChoiceOut): string[] {
  const kept = new Set(keyword.fields.flatMap((f) => FIELD_KEYS[f] ?? []));
  const all = Object.values(FIELD_KEYS).flat();
  const gone = all.filter((k) => !kept.has(k) && fields?.[k] != null && fields[k] !== "");
  return [...new Set(gone.map((k) => FIELD_WORDS[k] ?? k))];
}

/**
 * The fields with the keyword changed: the description stays, as do who it is aimed at
 * and the project it counts toward; fields the new keyword doesn't ask for go. A
 * Cancel or Observe is marked by its keyword, so the counter goes too.
 */
export function withKeyword(fields: Fields, keyword: KeywordChoiceOut): Record<string, unknown> {
  const kept = new Set(keyword.fields.flatMap((f) => FIELD_KEYS[f] ?? []));
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(fields ?? {})) {
    if (k === "keyword" || k === "counter") continue;
    if (Object.values(FIELD_KEYS).flat().includes(k) && !kept.has(k)) continue;
    out[k] = v;
  }
  // One character for a keyword that asks for one.
  if (keyword.fields.includes("character") && Array.isArray(out.aimed_at) && out.aimed_at.length > 1) out.aimed_at = out.aimed_at.slice(0, 1);
  return { ...out, keyword: keyword.key };
}

/**
 * What an answer costs before a Haven's Location doubles it: its keyword's cost, or
 * nothing for a Learn action standing for what is already off the allowance, or for
 * feeding in a territory, which stands in for a feeding action.
 */
export function baseCost(fields: Fields, keywords: KeywordChoiceOut[]): number {
  const key = keywordOf(fields);
  const keyword = key ? keywords.find((k) => k.key === key) : undefined;
  if (!keyword) return 1;
  if (keyword.effect === "learn" && textOf(fields, "owed_action_id")) return 0;
  if (keyword.effect === "feed" && textOf(fields, "territory")) return 0;
  return keyword.cost;
}

export type KeywordFeeding = {
  actions: number | null;
  territory: string | null;
  patrols: PatrolIn[] | null;
};

/** The Feeding section's actions, territory and patrols as Feed and Patrol answers give them; null for what none give. */
export function feedingFromAnswers(answers: Fields[], keywords: KeywordChoiceOut[]): KeywordFeeding {
  const effect = (f: Fields) => keywords.find((k) => k.key === keywordOf(f))?.effect;
  const feeds = answers.filter((f) => effect(f) === "feed");
  const inTerritory = feeds.filter((f) => textOf(f, "territory"));
  const patrols = new Map<string, number>();
  for (const f of answers.filter((a) => effect(a) === "patrol" && textOf(a, "territory"))) {
    const t = textOf(f, "territory");
    patrols.set(t, (patrols.get(t) ?? 0) + 1);
  }
  return {
    actions: feeds.length ? feeds.length - inTerritory.length : null,
    territory: feeds.length ? (inTerritory[0] ? textOf(inTerritory[0], "territory") : "") : null,
    patrols: patrols.size
      ? [...patrols].map(([territory_id, actions]) => ({
          territory_id,
          actions,
        }))
      : null,
  };
}

/** The Feeding section as the server will keep it, with what the Feed and Patrol answers give in place of its own. */
export function withKeywordFeeding(value: FeedingIn, fed: KeywordFeeding): FeedingIn {
  return {
    ...value,
    ...(fed.actions != null ? { actions: fed.actions, territory: fed.territory ?? "" } : {}),
    ...(fed.patrols != null ? { patrols: fed.patrols } : {}),
  };
}

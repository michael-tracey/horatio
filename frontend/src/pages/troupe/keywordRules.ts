import type { KeywordsOut, TroupeKeywordOut } from "../../api/types";

/** What a keyword asks for besides the description, in words: "A feeding territory". */
export function keywordFields(keyword: TroupeKeywordOut, data: KeywordsOut): string {
  return (keyword.fields ?? []).map((f) => data.fields.find((x) => x.key === f)?.label.split(":")[0] ?? f).join(", ");
}

/** What a keyword is spent from, in words: "Downtime action", "The Computer skill's action". */
export function keywordKinds(keyword: TroupeKeywordOut, data: KeywordsOut): string {
  if (keyword.computers_only) return "The Computer skill's action";
  if (!keyword.action_kinds?.length) return keyword.effect === "quest" ? "The form's Quest action" : "Nothing";
  return keyword.action_kinds.map((k) => data.action_kinds[k] ?? k).join(", ");
}

/** The keys with the one at `index` moved `by` places. */
export function moved(keys: string[], index: number, by: number): string[] {
  const to = index + by;
  if (to < 0 || to >= keys.length) return keys;
  const next = [...keys];
  const [key] = next.splice(index, 1);
  next.splice(to, 0, key!);
  return next;
}

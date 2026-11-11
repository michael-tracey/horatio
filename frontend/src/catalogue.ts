import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "./api/client";
import { RULES_QUERY } from "./hooks";

/** How long the catalogue is used as it came before it is asked for again, and kept
 * once no screen shows it: an hour, as the rules browser. It changes only with the
 * rules, and a change to them in the app (useRulesAction) asks for it again at once. */
export const CATALOGUE_MS = 60 * 60_000;

/**
 * The key of a rule set's catalogue (`/api/rules/{splat}`) as played in a troupe: one
 * shape for every screen, so screens showing the same rules share one answer (#644).
 * No troupe (null, undefined or "") is the rule set as written. With `category`, only
 * that category's traits: its own answer, under the whole one's key.
 */
export function catalogueKey(splat: string, troupeId: string | null | undefined, category?: string) {
  return ["catalogue", splat, troupeId || null, ...(category ? [category] : [])] as const;
}

/** Ask for a rule set's catalogue, as catalogueKey names it. */
export function fetchCatalogue(splat: string, troupeId: string | null | undefined, category?: string) {
  return unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat }, query: { troupe_id: troupeId || undefined, category } } }));
}

/**
 * A rule set's categories and traits, with `troupeId`'s house rules; without one, as the
 * book has them (what a troupe's own prices and settings are set against). Asked for once
 * and kept: a change in the app asks for it again only if it changes the rules
 * (RULES_QUERY, useRulesAction). `category` asks for that category's traits alone:
 * only for a screen that needs nothing else and is seldom beside one that needs it all.
 */
export function useCatalogue(splat: string, troupeId: string | null | undefined, options: { category?: string; enabled?: boolean } = {}) {
  const { category, enabled } = options;
  return useQuery({
    queryKey: catalogueKey(splat, troupeId, category),
    queryFn: () => fetchCatalogue(splat, troupeId, category),
    meta: RULES_QUERY,
    staleTime: CATALOGUE_MS,
    gcTime: CATALOGUE_MS,
    // Left to the client's default unless said: `enabled: undefined` would override it.
    ...(enabled === undefined ? {} : { enabled }),
  });
}

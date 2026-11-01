import { partialMatchKey, useIsMutating, useMutation, useQueries, useQuery, useQueryClient, type Query, type QueryKey } from "@tanstack/react-query";
import { useMemo } from "react";
import { api, ApiError, unwrap } from "./api/client";
import type { Me, Preferences } from "./api/types";
import type { components } from "./api/schema";

type RefusalOut = components["schemas"]["RefusalOut"];

/** The signed-in user, or null when signed out. */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async (): Promise<Me | null> => {
      try {
        return await unwrap(api.GET("/api/auth/me"));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
  });
}

/** Every setting's default, as the server has them, for before anyone signs in. */
export const DEFAULT_PREFERENCES: Preferences = {
  ratings: "numbers",
  time_zone: null,
  date_format: "day_month",
  clock: "12",
  paper: "letter",
  badge_size: "3x5",
  quick_notes: true,
  keep_awake: true,
  play_tab: "tracker",
  text_size: "normal",
  email_downtime: false,
  email_downtime_reminders: false,
  email_approvals: false,
  email_troupe_requests: false,
  email_renames: false,
  email_pictures: false,
  email_titles: false,
  email_digest: "at_once",
  whos_who_handle: false,
};

/** The signed-in person's settings (horatio.preferences), or the defaults. */
export function usePreferences(): Preferences {
  const me = useMe();
  return me.data?.preferences ?? DEFAULT_PREFERENCES;
}

const PREFERENCES = ["preferences"];

/** Whether a change to the settings is still on its way to the server. The
 * server merges each change into what it read, so two at once could lose one. */
export function useSavingPreferences(): boolean {
  return useIsMutating({ mutationKey: PREFERENCES }) > 0;
}

/** Change some settings. Takes effect at once: the page shows them before the
 * server answers, and goes back if it refuses. */
export function useSetPreferences() {
  const client = useQueryClient();
  return useMutation({
    mutationKey: PREFERENCES,
    mutationFn: (changes: Partial<Preferences>) => unwrap(api.PATCH("/api/preferences", { body: changes })),
    onMutate: async (changes) => {
      await client.cancelQueries({ queryKey: ["me"] });
      const before = client.getQueryData<Me | null>(["me"]);
      if (before) client.setQueryData<Me>(["me"], { ...before, preferences: { ...before.preferences, ...changes } });
      return { before };
    },
    onError: (_error, _changes, context) => {
      if (context?.before) client.setQueryData(["me"], context.before);
    },
    onSuccess: (kept) => {
      const now = client.getQueryData<Me | null>(["me"]);
      if (now) client.setQueryData<Me>(["me"], { ...now, preferences: kept });
    },
  });
}

/**
 * A change that, when it succeeds, refreshes everything on screen. Horatio's
 * data is small and interlinked (a purchase changes the sheet, the XP, the
 * approval queue), so refetching all of it is simpler and never stale.
 *
 * `first` names the queries that show the change itself (the sheet, after Spend
 * XP). They are asked again before the rest, on their own: the API is one process,
 * and an answer asked for alongside twenty others waits behind all of them.
 */
export function useAction<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>, first: QueryKey[] = []) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      // A query still on its first load is not restarted by invalidation alone: it
      // keeps the request it started before this change, and shows stale data. One
      // keyed by the sheet it is for (`of` in useUnavailable) is asked afresh under a
      // new key once the sheet changes: asking again under the old one is wasted.
      const changed = (q: Query) => !q.meta?.bySheet;
      const leading = (q: Query) => first.some((key) => partialMatchKey(q.queryKey, key));
      if (first.length) await client.invalidateQueries({ predicate: (q) => changed(q) && leading(q) });
      const rest = { predicate: (q: Query) => changed(q) && !leading(q) };
      await client.cancelQueries(rest);
      await client.invalidateQueries(rest);
    },
  });
}

/**
 * The signed-in person's bell: tasks waiting on them and their messages. Checked
 * every minute and whenever the window comes back into focus; any change made
 * in the app refreshes it at once (see useAction).
 */
export function useNotifications(enabled: boolean) {
  return useQuery({
    queryKey: ["notifications"],
    queryFn: () => unwrap(api.GET("/api/notifications")),
    enabled,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

/**
 * Traits in a category the character cannot take, and why (the rule set's checks).
 * `of` keys the answer to the sheet it is for (inClan's `sheetKey`, and the rules it
 * is built by): once either changes, the answer from before is only a placeholder
 * (`isPlaceholderData`) until the new one comes, never shown as now's from the cache.
 * A change made in the app (useAction) leaves it be: the new key asks again.
 */
export function useUnavailable(characterId: string, category: string, enabled = true, as?: UnavailableAs, of?: string) {
  const query = { category, as_if: as?.asIf, picks: as?.picks };
  return useQuery({
    queryKey: ["unavailable", characterId, category, as?.asIf ?? "sheet", as?.picks ?? [], ...(of ? [of] : [])],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/unavailable", { params: { path: { character_id: characterId }, query } })),
    enabled: enabled && !!category,
    meta: of ? { bySheet: true } : undefined,
    // Keep showing the last answer while ticks change, rather than flashing everything open.
    placeholderData: (previous) => previous,
  });
}

/** As useUnavailable, with the traits held elsewhere on the sheet that each refusal
 * is because of (Archaic: the Computer picked on Skills). */
export function useRefusals(characterId: string, category: string, enabled = true, as?: UnavailableAs) {
  const query = { category, as_if: as?.asIf, picks: as?.picks };
  return useQuery({
    queryKey: ["refusals", characterId, category, as?.asIf ?? "sheet", as?.picks ?? []],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/refusals", { params: { path: { character_id: characterId }, query } })),
    enabled: enabled && !!category,
    placeholderData: (previous) => previous,
  });
}

/**
 * As useRefusals, for a pick at each of `ratings`: every trait of a rated category tried at
 * that many dots, those held too. Where a pick of one rating clashes and another does not
 * (Generation 3 for a Thin Blooded vampire; Physical 7 for a Childlike one). With `asIf`
 * "empty", each is tried alone in its category (a ghoul's discipline, against its domitor's).
 */
export function useRatingRefusals(characterId: string, category: string, ratings: number[], enabled = true, asIf?: "empty") {
  const results = useQueries({
    queries: ratings.map((rating) => ({
      queryKey: ["refusals", characterId, category, "rating", rating, ...(asIf ? [asIf] : [])],
      queryFn: () =>
        unwrap(api.GET("/api/characters/{character_id}/refusals", { params: { path: { character_id: characterId }, query: { category, rating, as_if: asIf } } })),
      enabled: enabled && !!category,
      placeholderData: (previous: Record<string, RefusalOut> | undefined) => previous,
    })),
  });
  const key = JSON.stringify([ratings, results.map((r) => r.data)]);
  return useMemo(() => {
    const [asked, found] = JSON.parse(key) as [number[], (Record<string, RefusalOut> | null)[]];
    return Object.fromEntries(asked.map((rating, i) => [rating, found[i] ?? {}])) as Record<number, Record<string, RefusalOut>>;
  }, [key]);
}

/**
 * For each category, the traits the character cannot take and why, with the sheet
 * as the cart's changes would leave it: a discipline dot in the cart opens the
 * techniques that need it.
 */
export function usePlannedUnavailable(characterId: string, categories: string[], changes: components["schemas"]["CartIn"]["changes"], enabled = true) {
  return useQuery({
    queryKey: ["unavailable", characterId, "planned", categories, changes],
    queryFn: () =>
      unwrap(
        api.POST("/api/characters/{character_id}/unavailable", {
          params: { path: { character_id: characterId } },
          body: { categories, changes },
        }),
      ),
    enabled: enabled && categories.length > 0,
    // While the cart changes, keep the last answer for the same categories rather than flashing everything open.
    placeholderData: (previous, query) => (JSON.stringify(query?.queryKey[3]) === JSON.stringify(categories) ? previous : undefined),
  });
}

/**
 * For each category, the powers a merit opens past the character's Generation (Hard
 * as Steel), and what each costs through it ("Hard as Steel: 20 XP"), with the sheet
 * as the cart's changes would leave it.
 */
export function usePlannedOpened(characterId: string, categories: string[], changes: components["schemas"]["CartIn"]["changes"], enabled = true) {
  return useQuery({
    queryKey: ["opened", characterId, "planned", categories, changes],
    queryFn: () =>
      unwrap(
        api.POST("/api/characters/{character_id}/opened", {
          params: { path: { character_id: characterId } },
          body: { categories, changes },
        }),
      ),
    enabled: enabled && categories.length > 0,
    placeholderData: (previous, query) => (JSON.stringify(query?.queryKey[3]) === JSON.stringify(categories) ? previous : undefined),
  });
}

/**
 * Work the list out as if the category held only `picks` (a wizard step's ticks
 * before they are saved), or nothing at all (what no choice there could allow).
 */
export type UnavailableAs = { asIf: "picks"; picks: string[] } | { asIf: "empty"; picks?: undefined };

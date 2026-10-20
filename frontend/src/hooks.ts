import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, unwrap } from "./api/client";
import type { Me, Preferences } from "./api/types";

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
  keep_awake: false,
  play_tab: "tracker",
  text_size: "normal",
};

/** The signed-in person's settings (horatio.preferences), or the defaults. */
export function usePreferences(): Preferences {
  const me = useMe();
  return me.data?.preferences ?? DEFAULT_PREFERENCES;
}

/** Change some settings. Takes effect at once: the page shows them before the
 * server answers, and goes back if it refuses. */
export function useSetPreferences() {
  const client = useQueryClient();
  return useMutation({
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
 */
export function useAction<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      // A query still on its first load is not restarted by invalidation alone: it
      // keeps the request it started before this change, and shows stale data.
      await client.cancelQueries();
      await client.invalidateQueries();
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

/** Traits in a category the character cannot take, and why (the rule set's checks). */
export function useUnavailable(characterId: string, category: string, enabled = true, as?: UnavailableAs) {
  const query = { category, as_if: as?.asIf, picks: as?.picks };
  return useQuery({
    queryKey: ["unavailable", characterId, category, as?.asIf ?? "sheet", as?.picks ?? []],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/unavailable", { params: { path: { character_id: characterId }, query } })),
    enabled: enabled && !!category,
    // Keep showing the last answer while ticks change, rather than flashing everything open.
    placeholderData: (previous) => previous,
  });
}

/**
 * Work the list out as if the category held only `picks` (a wizard step's ticks
 * before they are saved), or nothing at all (what no choice there could allow).
 */
export type UnavailableAs = { asIf: "picks"; picks: string[] } | { asIf: "empty"; picks?: undefined };

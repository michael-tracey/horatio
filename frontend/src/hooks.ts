import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, unwrap } from "./api/client";
import type { Me } from "./api/types";

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
export function useUnavailable(characterId: string, category: string, enabled = true) {
  return useQuery({
    queryKey: ["unavailable", characterId, category],
    queryFn: () =>
      unwrap(api.GET("/api/characters/{character_id}/unavailable", { params: { path: { character_id: characterId }, query: { category } } })),
    enabled: enabled && !!category,
  });
}

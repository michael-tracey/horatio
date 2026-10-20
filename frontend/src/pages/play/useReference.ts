import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { PlayReference } from "../../api/types";

const KEY = "horatio.play.reference.";

function stored(characterId: string): PlayReference | undefined {
  try {
    const raw = localStorage.getItem(KEY + characterId);
    return raw ? (JSON.parse(raw) as PlayReference) : undefined;
  } catch {
    return undefined;
  }
}

/**
 * The Sheet and Pools tabs' reference: loaded once when the Play View opens,
 * never again while it stays open (it changes only between games), and kept on
 * the phone so it still shows at a game with no signal.
 */
export function useReference(characterId: string) {
  const query = useQuery({
    queryKey: ["play-reference", characterId],
    queryFn: async () => {
      const data = await unwrap(api.GET("/api/characters/{character_id}/play/reference", { params: { path: { character_id: characterId } } }));
      try {
        localStorage.setItem(KEY + characterId, JSON.stringify(data));
      } catch {
        // Not kept in a private window; it still shows now.
      }
      return data;
    },
    placeholderData: () => stored(characterId),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 2,
  });
  // Offline, the copy kept from last time stands in.
  return { reference: query.data ?? stored(characterId), error: query.error, loading: query.isPending && !stored(characterId) };
}

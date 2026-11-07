import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";

/**
 * The Sheet and Pools tabs' reference: loaded once when the Play View opens,
 * never again while it stays open (it changes only between games). Kept on the
 * phone for a game with no signal when the player keeps their characters there
 * (offline/keep.ts).
 */
export function useReference(characterId: string) {
  const query = useQuery({
    queryKey: ["play-reference", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/play/reference", { params: { path: { character_id: characterId } } })),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 2,
  });
  return { reference: query.data, error: query.error, loading: query.isPending };
}

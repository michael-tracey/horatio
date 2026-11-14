import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
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

/**
 * Ask the reference again when another character's power starts or ends an effect
 * on this one (#823): what it does to the pools comes with the reference, which is
 * otherwise loaded once. `foreign` names those effects' switches, as the Play View has them.
 */
export function useForeignReference(characterId: string, foreign: string | undefined) {
  const client = useQueryClient();
  const last = useRef(foreign);
  useEffect(() => {
    if (foreign === undefined || last.current === foreign) return;
    const first = last.current === undefined;
    last.current = foreign;
    if (!first) void client.invalidateQueries({ queryKey: ["play-reference", characterId] });
  }, [client, characterId, foreign]);
}

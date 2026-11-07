import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";

/**
 * The Equipment tab's items: loaded when the Play View opens, asked again after any
 * change made in the app (a give or discard, #282). The same query as the character
 * page's tab, kept on the phone for a game with no signal when the player keeps
 * their characters there (offline/keep.ts).
 */
export function useEquipment(characterId: string) {
  const query = useQuery({
    queryKey: ["character-equipment", characterId],
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_id}/equipment", {
          params: { path: { character_id: characterId } },
        }),
      ),
    refetchOnWindowFocus: false,
    retry: 2,
  });
  return { equipment: query.data, error: query.error };
}

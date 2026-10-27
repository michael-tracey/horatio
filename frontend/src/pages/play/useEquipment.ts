import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { CharacterEquipmentOut } from "../../api/types";

const KEY = "horatio.play.equipment.";

function stored(characterId: string): CharacterEquipmentOut | undefined {
  try {
    const raw = localStorage.getItem(KEY + characterId);
    return raw ? (JSON.parse(raw) as CharacterEquipmentOut) : undefined;
  } catch {
    return undefined;
  }
}

/**
 * The Equipment tab's items: loaded when the Play View opens, asked again after any
 * change made in the app (a give or discard, #282), and kept on the phone so they
 * still show at a game with no signal. The same query as the character page's tab.
 */
export function useEquipment(characterId: string) {
  const query = useQuery({
    queryKey: ["character-equipment", characterId],
    queryFn: async () => {
      const data = await unwrap(
        api.GET("/api/characters/{character_id}/equipment", {
          params: { path: { character_id: characterId } },
        }),
      );
      try {
        localStorage.setItem(KEY + characterId, JSON.stringify(data));
      } catch {
        // Not kept in a private window; it still shows now.
      }
      return data;
    },
    placeholderData: () => stored(characterId),
    refetchOnWindowFocus: false,
    retry: 2,
  });
  // Offline, the copy kept from last time stands in.
  return { equipment: query.data ?? stored(characterId), error: query.error };
}

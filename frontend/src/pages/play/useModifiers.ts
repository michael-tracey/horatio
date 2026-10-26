import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { PoolModifier } from "../../api/types";

const KEY = "horatio.play.modifiers.";

function stored(characterId: string): PoolModifier[] | undefined {
  try {
    const raw = localStorage.getItem(KEY + characterId);
    return raw ? (JSON.parse(raw) as PoolModifier[]) : undefined;
  } catch {
    return undefined;
  }
}

function keep(characterId: string, list: PoolModifier[]) {
  try {
    localStorage.setItem(KEY + characterId, JSON.stringify(list));
  } catch {
    // Not kept in a private window; they still show now.
  }
}

export type ModifierFields = { label: string; amount: number; pools: string; when: string };

/**
 * The player's own modifiers to the character's pools: switched on and off at the
 * table, so each change goes to the server and its answer is the list. The last
 * list is kept on the phone, to show at a game with no signal.
 */
export function useModifiers(characterId: string) {
  const client = useQueryClient();
  const path = { character_id: characterId };
  const queryKey = ["play-modifiers", characterId];
  const query = useQuery({
    queryKey,
    queryFn: async () => {
      const list = await unwrap(api.GET("/api/characters/{character_id}/play/modifiers", { params: { path } }));
      keep(characterId, list);
      return list;
    },
    placeholderData: () => stored(characterId),
    retry: 1,
  });
  const saved = (list: PoolModifier[]) => {
    keep(characterId, list);
    client.setQueryData(queryKey, list);
  };
  const add = useMutation({
    mutationFn: async (body: ModifierFields) => unwrap(api.POST("/api/characters/{character_id}/play/modifiers", { params: { path }, body: { ...body, on: true } })),
    onSuccess: saved,
  });
  const change = useMutation({
    mutationFn: async ({ id, ...body }: { id: string } & Partial<ModifierFields & { on: boolean }>) =>
      unwrap(api.PATCH("/api/characters/{character_id}/play/modifiers/{modifier_id}", { params: { path: { ...path, modifier_id: id } }, body })),
    onSuccess: saved,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => unwrap(api.DELETE("/api/characters/{character_id}/play/modifiers/{modifier_id}", { params: { path: { ...path, modifier_id: id } } })),
    onSuccess: saved,
  });
  return { modifiers: query.data ?? stored(characterId) ?? [], add, change, remove };
}

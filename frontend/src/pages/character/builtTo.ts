import type { CharacterOut } from "../../api/types";

/**
 * Whose rules a character with no home troupe is built to (issue #569): the troupe it
 * is built for, until that troupe accepts it, or the book's. A character with a home
 * troupe plays by its home's rules, said where its home is shown, so this is null.
 */
export type BuiltTo =
  | { kind: "troupe"; troupeId: string; name: string }
  /** Built for a troupe that has since closed (archived): it isn't listed any more. */
  | { kind: "closed" }
  | { kind: "book" }
  | null;

export function builtTo(
  character: Pick<CharacterOut, "home_troupe_id" | "building_troupe_id">,
  troupes: readonly { id: string; name: string }[],
): BuiltTo {
  if (character.home_troupe_id) return null;
  if (!character.building_troupe_id) return { kind: "book" };
  const troupe = troupes.find((t) => t.id === character.building_troupe_id);
  return troupe ? { kind: "troupe", troupeId: troupe.id, name: troupe.name } : { kind: "closed" };
}

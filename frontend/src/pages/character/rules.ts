import type { CharacterOut } from "../../api/types";

/** Whose rules the character plays by: its home troupe's, else the troupe it is being built for (horatio.sheets.rules_troupe). */
export function rulesTroupe(character: CharacterOut): string | undefined {
  return character.home_troupe_id ?? character.building_troupe_id ?? undefined;
}

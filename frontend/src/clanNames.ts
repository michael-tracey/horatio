import type { TroupeOut } from "./api/types";

/**
 * What a troupe calls the clan the rules store as "Assamite" (#430): "Banu Haqim",
 * its later name and the default, or "Assamite", the books'. Only what is shown
 * changes: the rules, the sheets and whatever is sent back keep "Assamite".
 */
export type ClanName = TroupeOut["assamite_name"];

/** For a troupe that has not said, and a character outside any troupe. */
export const DEFAULT_CLAN_NAME: ClanName = "Banu Haqim";

// Banu Haqim is the same in the plural, and takes "a", not "an".
const ARTICLE = /\b([Aa])n Assamite\b/g;
const NAME = /\bAssamites?\b/g;

/**
 * `text`, which names the clan as the rules store it, as a troupe calling it `name`
 * reads it: "Assamite: Vizier" is "Banu Haqim: Vizier", "Kiss of the Asp
 * (Assamite)" is "Kiss of the Asp (Banu Haqim)", "the Assamites" are "the Banu
 * Haqim" and "an Assamite" is "a Banu Haqim". The backend's horatio.clan_names
 * does the same for the text it sends, such as notifications.
 */
export function clanNamed(text: string, name: ClanName): string {
  if (name !== "Banu Haqim" || !text.includes("Assamite")) return text;
  return text.replace(ARTICLE, "$1 Banu Haqim").replace(NAME, "Banu Haqim");
}

/** `text` with every name the clan goes by, to search: either name finds it, whichever the troupe uses. */
export function withClanNames(text: string): string {
  return text.includes("Assamite") ? `${text} ${clanNamed(text, "Banu Haqim")}` : text;
}

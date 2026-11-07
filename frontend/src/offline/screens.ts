/**
 * What a screen is called when it says it needs a connection (#502): "The Downtime
 * tab needs a connection." Only a player's own characters' sheets and Play Views
 * work with no signal; any other screen names itself and offers the way back to them.
 */

const CHARACTER_TABS: Record<string, string> = {
  downtime: "The Downtime tab",
  results: "The Results tab",
  xp: "The Experience tab",
  quests: "The Quests tab",
  influence: "The Influence tab",
  troupes: "The Troupes tab",
  backstory: "The Backstory tab",
  log: "The Log tab",
  status: "The Status & Titles tab",
  shared: "The Shared backgrounds tab",
  equipment: "The Equipment tab",
  sheet: "This character's sheet",
  create: "Character creation",
};

const ID = "[^/]+";

/** The screen at `pathname`, as a sentence starts: "The Downtime tab", "This scene". */
export function screenName(pathname: string): string {
  const path = pathname.replace(/\/+$/, "") || "/";
  const tab = new RegExp(`^/characters/${ID}/([^/]+)`).exec(path);
  if (tab) return CHARACTER_TABS[tab[1]!] ?? "This screen";
  if (new RegExp(`^/characters/${ID}$`).test(path)) return "This character's sheet";
  if (path === "/characters" || path === "/") return "The Characters page";
  if (new RegExp(`^/play/characters/${ID}`).test(path)) return "This Play View";
  if (new RegExp(`^/play/troupes/${ID}/scenes/${ID}`).test(path)) return "This scene";
  if (new RegExp(`^/play/troupes/${ID}/scenes?$`).test(path)) return "The Scenes page";
  if (path.startsWith("/check-in")) return "Check-in";
  if (path.startsWith("/cycles/")) return "The downtime cycle";
  if (path === "/troupes") return "The Troupes page";
  if (path.startsWith("/troupes/")) return "The troupe's page";
  if (path.startsWith("/custodian")) return "The Custodian page";
  if (path.startsWith("/account")) return "Your account";
  if (path.startsWith("/players/")) return "A player's profile";
  if (path.startsWith("/rules")) return "The rules reference";
  if (path.startsWith("/print/")) return "Printing";
  return "This screen";
}

/** The character a screen is about, if it is a character's page or Play View. */
export function characterOf(pathname: string): string | null {
  const found = /^\/(?:play\/)?characters\/([0-9a-f-]{36})/.exec(pathname);
  return found ? found[1]! : null;
}

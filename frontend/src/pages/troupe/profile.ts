/**
 * A troupe's profile (issue #119), as its page shows it: which links it has, in
 * what order, and whether there is anything to show at all.
 */
import type { ProfileLinks, TroupeProfileIn, TroupeProfileOut } from "../../api/types";

export type LinkKind = keyof ProfileLinks;

/** The links a profile can have, in the order they show, with their names. */
export const LINKS: { kind: LinkKind; label: string; placeholder: string }[] = [
  { kind: "website", label: "Website", placeholder: "https://" },
  { kind: "discord", label: "Discord invite", placeholder: "https://discord.gg/…" },
  { kind: "facebook", label: "Facebook", placeholder: "https://facebook.com/…" },
  { kind: "instagram", label: "Instagram", placeholder: "https://instagram.com/…" },
  { kind: "join", label: "How to join", placeholder: "https://" },
];

/** The links it has, in order. */
export function linksOf(links: ProfileLinks): { kind: LinkKind; label: string; url: string }[] {
  return LINKS.flatMap(({ kind, label }) => {
    const url = links[kind];
    return url ? [{ kind, label, url }] : [];
  });
}

/** "Welcoming new players", "Not taking new players right now", or nothing. */
export function newPlayersText(status: TroupeProfileOut["new_players"]): string | null {
  if (status === "welcoming") return "Welcoming new players";
  if (status === "closed") return "Not taking new players right now";
  return null;
}

/** Whether a part of the profile has anything in it. */
export const filled = (...values: (string | number | null | undefined)[]) => values.some((v) => v !== null && v !== undefined && v !== "");

/** Whether the profile says anything beyond the troupe's name and description. */
export function hasProfile(p: TroupeProfileOut): boolean {
  return (
    !!p.portrait ||
    linksOf(p.links).length > 0 ||
    filled(p.schedule, p.new_players, p.min_age, p.content_notes, p.contact?.id) ||
    p.games.length > 0 ||
    filled(p.venue.region, p.venue.name, p.venue.address, p.venue.access) ||
    p.venue.address_hidden ||
    filled(p.setting.chronicle, p.setting.city, p.setting.era, p.setting.tone)
  );
}

/** The profile as the editor starts it: what is saved, ready to change. */
export function editable(p: TroupeProfileOut): TroupeProfileIn {
  return {
    public: p.public,
    contact_id: p.contact?.id ?? null,
    links: Object.fromEntries(LINKS.map(({ kind }) => [kind, p.links[kind] ?? ""])) as ProfileLinks,
    schedule: p.schedule,
    venue: { region: p.venue.region, name: p.venue.name, address: p.venue.address ?? "", access: p.venue.access },
    setting: { ...p.setting },
    new_players: p.new_players,
    min_age: p.min_age,
    content_notes: p.content_notes,
  };
}

/** Where anyone can see a troupe's profile once it is public. */
export function publicPath(troupeId: string): string {
  return `/t/${troupeId}`;
}

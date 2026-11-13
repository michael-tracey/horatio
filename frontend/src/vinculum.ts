import type { TroupeVinculumOut, VaulderieOut } from "./api/types";

/** Where the book has the Vaulderie and the Vinculum, and the errata's changes to them. */
export const VINCULUM_PAGE = "MET: VTM pp. 433–435; Errata p. 434";

/** What a Vinculum rating feels like, in a few words (p. 434). */
export const RATING_NAMES: Record<number, string> = {
  1: "Kinship",
  2: "Friendship",
  3: "Close friendship",
  4: "Integral",
  5: "Infatuation",
};

export function ratingName(rating: number): string {
  return RATING_NAMES[Math.min(Math.max(rating, 1), 5)] ?? "";
}

/** How the ratings are worked out, for the staff screen's help. */
export const RATING_RULES: string[] = [
  "1 after the first Vaulderie together, for good.",
  "2 if more than once in the past year.",
  "3 if more than 10 times in the past year.",
  "4 if about weekly for the past three months, never missing more than two weeks in a row.",
  "5 if every few days for the past three months.",
];

/** Who took part, as a list of names: "Agnes, Bram and Ezra (false Sabbat)". */
export function participantsText(v: Pick<VaulderieOut, "participants">): string {
  const names = v.participants.map((p) => (p.false_sabbat ? `${p.who.name} (false Sabbat)` : p.who.name));
  if (names.length <= 2) return names.join(" and ");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** Where a Vaulderie stands, for its list. */
export function vaulderieState(v: Pick<VaulderieOut, "status" | "reason">): string {
  switch (v.status) {
    case "pending":
      return "Waiting for the storytellers";
    case "declined":
      return v.reason ? `Declined: ${v.reason}` : "Declined";
    case "removed":
      return v.reason ? `Taken out: ${v.reason}` : "Taken out";
    case "withdrawn":
      return "Withdrawn";
    default:
      return "Counts";
  }
}

/**
 * The matrix of ratings for the staff screen: the people in it (everyone, or those of
 * one Vaulderie's circle, to see a pack), and the rating each feels toward each other.
 */
export function matrix(
  data: Pick<TroupeVinculumOut, "people" | "ratings" | "vaulderies">,
  circle: string | null,
): { people: TroupeVinculumOut["people"]; rating: (from: string, to: string) => number } {
  const ratings = new Map(data.ratings.map((r) => [`${r.felt_by}→${r.toward}`, r.rating]));
  const chosen = circle ? data.vaulderies.find((v) => v.id === circle) : undefined;
  const keys = chosen ? new Set(chosen.participants.map((p) => p.who.character_id ?? `name:${p.who.name.trim().toLowerCase()}`)) : null;
  const people = keys ? data.people.filter((p) => keys.has(p.key)) : data.people;
  return { people, rating: (from, to) => ratings.get(`${from}→${to}`) ?? 0 };
}

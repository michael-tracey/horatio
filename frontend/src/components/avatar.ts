/** "Agnes Moreau" → "AM"; "Lord Byron the Third" → "LT"; one name → its first letter. */
export function initials(name: string): string {
  const words = name
    .replace(/[^\p{L}\p{N}\s'-]/gu, " ")
    .split(/\s+/)
    .filter((w) => w && /\p{L}|\p{N}/u.test(w));
  if (words.length === 0) return "?";
  const first = words[0]!;
  const last = words.length > 1 ? words[words.length - 1]! : "";
  return (first[0]! + (last[0] ?? "")).toUpperCase();
}

/**
 * Each clan's colour for placeholders, deep enough for parchment text. Bloodlines
 * ("Brujah: True Brujah") take their clan's. A clan not listed gets one from its
 * name, always the same; no clan yet is ash.
 */
const CLAN_COLOURS: Record<string, string> = {
  Assamite: "#5a2a2a",
  Baali: "#3d1f33",
  Brujah: "#7a2e1f",
  Caitiff: "#4a4a52",
  Cappadocians: "#4f4636",
  "Daughters of Cacophony": "#6b2f5a",
  "Followers of Set": "#6b5418",
  Gangrel: "#3f5a2a",
  Gargoyles: "#535b63",
  Giovanni: "#2f3d52",
  Lasombra: "#24243a",
  Lhiannan: "#2f5a45",
  Malkavian: "#4b2f6b",
  Nagaraja: "#3a3a2a",
  Nosferatu: "#3b4a3a",
  Ravnos: "#6b3a1f",
  Salubri: "#2f4f6b",
  Toreador: "#7a2a4a",
  Tremere: "#5c1f2a",
  Tzimisce: "#4a2a3d",
  Ventrue: "#1f3a5c",
};
const SPARE = ["#5a3a2a", "#2a4a5a", "#4a5a2a", "#5a2a4a", "#2a5a4a", "#4a2a5a"];

export function clanColour(clan: string | null | undefined): string {
  if (!clan) return "#2c2531";
  const family = clan.split(":")[0]!.trim();
  const known = CLAN_COLOURS[family];
  if (known) return known;
  let hash = 0;
  for (const c of family) hash = (hash * 31 + c.charCodeAt(0)) >>> 0;
  return SPARE[hash % SPARE.length]!;
}

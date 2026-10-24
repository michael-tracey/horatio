/**
 * What a tracker's count brings if the character goes on, in our own words with
 * the page, for TrackerWarning. Warnings only: nothing here stops a tap. Beast
 * traits and frenzy follow MET: VtM core, pp. 301–303, with the Vol. II Issue 1
 * update's riding the wave (pp. 94–95) and its roleplay for each count (pp. 97–98).
 */

export type Warning = { level: "near" | "at"; title: string; lines: string[]; source: string };

/**
 * Derangement traits (MET: VtM core, p. 267): at 3 the character is on the edge
 * of a psychotic break, and the next trigger of any of their derangements brings
 * a severe response that clears them. One short of that, a warning of what's next.
 */
export function derangementWarning(value: number, most: number, least: number): Warning | null {
  const cleared = least ? `to ${least}, as a Malkavian always keeps ${least}` : "to 0";
  if (value >= most)
    return {
      level: "at",
      title: "On the edge of a psychotic break",
      lines: [
        "The next time any of your derangements is triggered, you can't hold it back: you must play a severe response.",
        "A severe response lasts five minutes. Play the derangement at its most frightening and unstable, as its type describes (pp. 268–269), and play it seriously, never for laughs (p. 266).",
        `Afterwards every Derangement trait is cleared, ${cleared}. Tap Severe response when it's over.`,
      ],
      source: "MET: VtM core, pp. 266–269",
    };
  if (value === most - 1)
    return {
      level: "near",
      title: "One trait from the edge",
      lines: [
        "One more Derangement trait puts you on the edge of a psychotic break: the next trigger after that can't be resisted, and brings a severe response.",
        `You can choose a severe response at any trigger instead, and clear them all now, ${cleared}.`,
      ],
      source: "MET: VtM core, p. 267",
    };
  return null;
}

/** What each count of Beast traits makes a frenzy test of (MET: VtM core, p. 302), by type. */
export const FRENZY_TRIGGERS: { beast: number; rage: string[]; hunger: string[]; fear: string[] }[] = [
  {
    beast: 1,
    rage: ["a single blow of 4 or more damage"],
    hunger: ["your Blood reaching 0"],
    fear: ["being engulfed by a large fire", "full exposure to bright sunlight"],
  },
  {
    beast: 2,
    rage: ["a single blow of 3 or more damage"],
    hunger: ["your Blood down to a third of its most"],
    fear: ["any damage from fire or sunlight"],
  },
  {
    beast: 3,
    rage: ["a single blow of 2 or more damage"],
    hunger: ["your Blood down to half"],
    fear: ["being within three feet of sunlight, or of a fire bigger than a torch"],
  },
  {
    beast: 4,
    rage: ["any damage at all"],
    hunger: ["your Blood below its most", "seeing or smelling mortals or their blood"],
    fear: ["seeing sunlight, or a fire bigger than a lighter"],
  },
];

/** "a blow of 3 or more (rage), …": what makes a frenzy test at this many Beast traits, with every lower count's too. */
export function triggersAt(beast: number): string {
  // A lower count's trigger still counts; the newest is the widest of its kind.
  const row = FRENZY_TRIGGERS[Math.min(beast, 4) - 1]!;
  const listed = [...row.rage.map((t) => `${t} (rage)`), ...row.hunger.map((t) => `${t} (hunger)`), ...row.fear.map((t) => `${t} (fear)`)];
  return listed.join("; ");
}

/** How the Beast feels at each count, to play (Vol. II Issue 1 update, pp. 97–98). */
const ROLEPLAY = [
  "Play it: a voice starts to echo in your mind, urging you to shrug off remorse, and there's a thrill in giving in.",
  "Play it: the Beast whispers at every choice, pushing the easy way; your cheeks flush and your dead heart races.",
  "Play it: the Beast speaks plainly and urges you on at every turn; mortals take you for drunk and dangerous, and vampires see it in your face.",
  "Play it: the Beast is a constant voice and right and wrong blur; your skin turns pale and waxy, your eyes reddish, and mortals keep away.",
];

/**
 * Beast traits (MET: VtM core, pp. 301–302): each one widens what makes the
 * character test to resist frenzy, and five cost a dot of permanent Morality.
 * From the first, what now makes a frenzy test and how to play it.
 */
export function beastWarning(value: number, most: number, morality: { name: string; value: number } | null): Warning | null {
  if (value <= 0) return null;
  const name = morality?.name ?? "Humanity";
  // Humanity 2 or less: +5 to resist every frenzy (p. 303).
  const low = morality?.name === "Humanity" && morality.value <= 2 ? 5 : 0;
  const resist = `Resist with Mental + Willpower against ${10 + Math.min(value, most) + low}${low ? " (+5 at Humanity 2 or less)" : ""}, or spend a Willpower to hold frenzy off for a scene, three turns in combat.`;
  if (value >= most)
    return {
      level: "at",
      title: `A dot of ${name} is lost`,
      lines: [
        `Five Beast traits cost a dot of permanent ${name}, and every five more another; your storytellers put it on the sheet.`,
        `Every trigger counts now: ${triggersAt(4)}.`,
        resist,
        "A day's sleep lulls the Beast and clears every Beast trait.",
      ],
      source: "MET: VtM core, pp. 301–303",
    };
  const titles = ["The Beast has a foothold", "The Beast is awake", "The Beast speaks", `One trait from losing ${name}`];
  return {
    level: value === most - 1 ? "at" : "near",
    title: titles[value - 1]!,
    lines: [
      ...(value === most - 1 ? [`One more Beast trait costs a dot of permanent ${name}.`] : []),
      value === 1 ? `You can frenzy now. Test to resist it on ${triggersAt(value)}.` : `Test to resist frenzy on ${triggersAt(value)}, on top of the triggers before.`,
      resist,
      ROLEPLAY[value - 1]!,
    ],
    source: "MET: VtM core, pp. 301–302; Vol. II Issue 1 update, pp. 97–98",
  };
}

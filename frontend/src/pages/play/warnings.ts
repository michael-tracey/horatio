/**
 * What a tracker's count brings if the character goes on, in our own words with
 * the page, for TrackerWarning. Warnings only: nothing here stops a tap.
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

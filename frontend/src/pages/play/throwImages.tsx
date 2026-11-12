import type { ReactNode } from "react";
import { THROW_NAMES, type Throw } from "./throws";

/**
 * A set of rock, paper and scissors pictures for the Throws tab. Horatio's own
 * are drawn here; a troupe's uploaded set (#670) and the person's choice of set in
 * Settings (#671) plug in as another `ThrowImages`, so the tab never knows which.
 */
export type ThrowImages = {
  /** The set's name, as Settings will offer it. */
  name: string;
  /**
   * One throw's picture, square, filling the box it is put in. The throw's word
   * and its label go with it in `ThrowFace`, so the picture is for the eye alone.
   */
  picture: (which: Throw) => ReactNode;
};

/**
 * One throw as the other player sees it across a table: the picture, with its
 * word under it for anyone who can't make it out, read out as the word.
 */
export function ThrowFace({ images, which }: { images: ThrowImages; which: Throw }) {
  return (
    <div role="img" aria-label={THROW_NAMES[which]} className="flex flex-col items-center">
      <div aria-hidden="true" className="aspect-square w-[min(68vw,18rem)] text-parchment">
        {images.picture(which)}
      </div>
      <span aria-hidden="true" className="mt-1 font-display text-5xl text-gold sm:text-6xl">
        {THROW_NAMES[which]}
      </span>
    </div>
  );
}

// --- Horatio's own ----------------------------------------------------------------
//
// Drawn in the page's text colour (`currentColor`), with flat fills of the same at
// lower opacity for light and shade, and one touch of gold or blood, so each reads
// as a bold silhouette on Dark, Ultra goth and Light alike. Thick strokes, no fine
// detail: they are meant to be seen at arm's length.

const LINE = { fill: "none", stroke: "currentColor", strokeLinecap: "round", strokeLinejoin: "round" } as const;

function Picture({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 120 120" className="h-full w-full" focusable="false">
      {children}
    </svg>
  );
}

/** A faceted stone, lit from the upper left. */
function Rock() {
  const outline = "M18 92 L28 58 L48 34 L76 28 L98 48 L104 80 L92 98 L36 101 Z";
  return (
    <Picture>
      <ellipse cx="60" cy="106" rx="46" ry="5" fill="currentColor" opacity="0.2" />
      <path d={outline} className="fill-dusk" />
      <path d={outline} fill="currentColor" fillOpacity="0.1" />
      <path d="M48 34 L76 28 L98 48 L82 62 L58 58 Z" fill="currentColor" fillOpacity="0.45" />
      <path d="M18 92 L28 58 L48 34 L58 58 L36 101 Z" fill="currentColor" fillOpacity="0.22" />
      <path d="M48 34 L58 58 L82 62 L98 48 M58 58 L36 101 M82 62 L92 98" {...LINE} strokeWidth="3" />
      <path d="M66 74 l6 7 -4 6 5 6" {...LINE} strokeWidth="2.5" opacity="0.7" />
      <path d={outline} {...LINE} strokeWidth="5" />
    </Picture>
  );
}

/** A sheet of parchment, its corner turned down, written on and sealed in blood-red wax. */
function Paper() {
  const sheet = "M32 14 H74 L90 30 V106 H32 Z";
  return (
    <Picture>
      <g transform="rotate(-6 60 60)">
        <path d={sheet} className="fill-dusk" />
        <path d={sheet} fill="currentColor" fillOpacity="0.14" />
        <path d="M74 14 V30 H90 Z" fill="currentColor" fillOpacity="0.4" />
        <path d="M42 44 H80 M42 56 H80 M42 68 H70" {...LINE} strokeWidth="3.5" opacity="0.65" />
        <path d={sheet} {...LINE} strokeWidth="5" />
        <path d="M74 14 V30 H90" {...LINE} strokeWidth="3.5" />
        <path d="M66 96 l-5 14 6 -3 3 6 3 -15" className="fill-blood" />
        <circle cx="72" cy="90" r="11" className="fill-blood" />
        <circle cx="72" cy="90" r="5.5" fill="none" stroke="currentColor" strokeWidth="2" opacity="0.75" />
      </g>
    </Picture>
  );
}

/** Open shears, crossed at a gold pivot. */
function Scissors() {
  // Each blade's handle is on the other side, as on real scissors.
  const back = "M70 74 L36 14 C33 9 27 12 29 18 L50 69 Z";
  const front = "M50 74 L84 14 C87 9 93 12 91 18 L70 69 Z";
  return (
    <Picture>
      <path d="M64 72 L77 82" {...LINE} strokeWidth="7" />
      <circle cx="86" cy="95" r="13" {...LINE} strokeWidth="6" />
      <path d={back} className="fill-dusk" />
      <path d={back} fill="currentColor" fillOpacity="0.25" />
      <path d={back} {...LINE} strokeWidth="4" />
      <path d="M56 72 L43 82" {...LINE} strokeWidth="7" />
      <circle cx="34" cy="95" r="13" {...LINE} strokeWidth="6" />
      <path d={front} className="fill-dusk" />
      <path d={front} fill="currentColor" fillOpacity="0.4" />
      <path d={front} {...LINE} strokeWidth="4" />
      <circle cx="60" cy="68" r="5" className="fill-gold" />
    </Picture>
  );
}

const HORATIO_PICTURES: Record<Throw, () => ReactNode> = { rock: Rock, paper: Paper, scissors: Scissors };

/** Horatio's own set, the one every player has. */
export const HORATIO_IMAGES: ThrowImages = {
  name: "Horatio",
  picture: (which) => {
    const Drawn = HORATIO_PICTURES[which];
    return <Drawn />;
  },
};

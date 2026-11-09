import { useId } from "react";
import type { ComponentType } from "react";
import type { Motif } from "./motifs";

/*
 * The loading animations the custodian chooses between (#568): each a small SVG,
 * drawn and moved by loaders.css, with no picture to download, so it shows at once
 * and offline. Each comes in three sizes (LoaderMark) and has a still version for
 * "reduce motion". Adding one is a component here, its entry in `loaders`, and
 * its styles in loaders.css (and its name in the API's list, horatio.api.appearance).
 *
 * They are rendered once more, to plain HTML, for index.html's loading screen
 * (splash.tsx), so they use no state, effects or context: useId alone.
 */

const BLOOD = "#a3253a";
const BLOOD_BRIGHT = "#c8384f";
const BLOOD_DARK = "#5e1220";
const GOLD = "#c9a24a";
const GOLD_LIGHT = "#e8c97a";
const GOLD_DARK = "#8c6d2c";

/** A unique id for a gradient or clip, safe in a url(#…) reference. */
function useSvgId(): (name: string) => string {
  const base = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  return (name) => `loader-${base}-${name}`;
}

/** A: a drop gathers, stretches, falls and lands in a small pool that ripples. */
function Drip() {
  const id = useSvgId();
  return (
    <svg viewBox="0 0 40 84" className="loader-art" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id={id("drop")} cx="0.38" cy="0.62" r="0.7">
          <stop offset="0" stopColor={BLOOD_BRIGHT} />
          <stop offset="0.6" stopColor={BLOOD} />
          <stop offset="1" stopColor={BLOOD_DARK} />
        </radialGradient>
      </defs>
      <ellipse className="drip-pool" cx="20" cy="78" rx="10" ry="2.6" fill={BLOOD} />
      <ellipse className="drip-ripple" cx="20" cy="78" rx="10" ry="2.6" />
      <ellipse className="drip-ripple drip-ripple-late" cx="20" cy="78" rx="10" ry="2.6" />
      <circle className="drip-splash drip-splash-left" cx="20" cy="76" r="1.1" fill={BLOOD_BRIGHT} />
      <circle className="drip-splash drip-splash-right" cx="20" cy="76" r="0.9" fill={BLOOD_BRIGHT} />
      <g className="drip-fall">
        <path d="M20 2C20 2 12.5 13.6 12.5 18.6a7.5 7.5 0 0 0 15 0C27.5 13.6 20 2 20 2Z" fill={`url(#${id("drop")})`} />
        <path d="M16.6 15.2c-.9 1.3-1.5 2.6-1.6 3.9" stroke="#ede4d3" strokeOpacity="0.55" strokeWidth="1.1" strokeLinecap="round" fill="none" />
      </g>
      <ellipse className="drip-bead" cx="20" cy="1.6" rx="3.6" ry="1.8" fill={BLOOD} />
    </svg>
  );
}

/** B: blood rises in a chalice, then drains, like feeding's finish on the Play View. */
function Rising() {
  const id = useSvgId();
  return (
    <svg viewBox="0 0 48 66" className="loader-art" aria-hidden="true" focusable="false">
      <defs>
        <clipPath id={id("bowl")}>
          <path d="M7 11C7 26.6 14.6 34.6 24 34.6S41 26.6 41 11Z" />
        </clipPath>
        <linearGradient id={id("blood")} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={BLOOD_BRIGHT} />
          <stop offset="0.5" stopColor={BLOOD} />
          <stop offset="1" stopColor={BLOOD_DARK} />
        </linearGradient>
        <linearGradient id={id("gold")} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor={GOLD_DARK} />
          <stop offset="0.45" stopColor={GOLD_LIGHT} />
          <stop offset="1" stopColor={GOLD_DARK} />
        </linearGradient>
      </defs>
      <path d="M7 11C7 26.6 14.6 34.6 24 34.6S41 26.6 41 11Z" fill="#141016" fillOpacity="0.55" />
      <g clipPath={`url(#${id("bowl")})`}>
        <g className="rising-level">
          <path className="rising-wave" d="M-24 3q6-3 12 0t12 0t12 0t12 0t12 0t12 0t12 0t12 0V40H-24Z" fill={`url(#${id("blood")})`} />
        </g>
      </g>
      <path d="M6 11C6 27.4 14 36 24 36s18-8.6 18-25" stroke={`url(#${id("gold")})`} strokeWidth="1.8" fill="none" />
      <path d="M10.4 16c.6 6.6 3.4 11.6 7.4 14.2" stroke="#ede4d3" strokeOpacity="0.3" strokeWidth="1" strokeLinecap="round" fill="none" />
      <ellipse className="rising-rim" cx="24" cy="11" rx="18" ry="3" stroke={GOLD_LIGHT} strokeWidth="1.4" fill="none" />
      <path d="M24 36v17" stroke={GOLD} strokeWidth="2.6" />
      <ellipse cx="24" cy="44" rx="3.2" ry="1.7" fill={GOLD} />
      <path d="M12.5 61C15.5 56 20.5 53.4 24 53.4S32.5 56 35.5 61Z" fill={`url(#${id("gold")})`} />
      <ellipse cx="24" cy="61" rx="11.5" ry="2.2" fill={GOLD_DARK} />
    </svg>
  );
}

/** C: a candle's flame flickers and its light breathes, as a drop of red wax runs down. */
function Candle() {
  const id = useSvgId();
  return (
    <svg viewBox="0 0 40 80" className="loader-art" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id={id("glow")}>
          <stop offset="0" stopColor="#f3c969" stopOpacity="0.6" />
          <stop offset="0.45" stopColor={GOLD} stopOpacity="0.18" />
          <stop offset="1" stopColor={GOLD} stopOpacity="0" />
        </radialGradient>
        <linearGradient id={id("flame")} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#d9692b" />
          <stop offset="0.35" stopColor="#f0a83a" />
          <stop offset="1" stopColor="#f8dc8a" />
        </linearGradient>
        <linearGradient id={id("wax")} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#a8987d" />
          <stop offset="0.35" stopColor="#ede4d3" />
          <stop offset="0.7" stopColor="#e2d5bc" />
          <stop offset="1" stopColor="#9a8b72" />
        </linearGradient>
      </defs>
      <circle className="candle-glow" cx="20" cy="20" r="20" fill={`url(#${id("glow")})`} />
      <g className="candle-flame">
        <path d="M20 4.5C23.6 11.2 27 15.4 27 21.6a7 7 0 0 1-14 0C13 15.4 16.4 11.2 20 4.5Z" fill={`url(#${id("flame")})`} />
        <path className="candle-core" d="M20 13.6c1.8 3.4 3.4 5.4 3.4 8.4a3.4 3.4 0 0 1-6.8 0c0-3 1.6-5 3.4-8.4Z" fill="#fff6e0" />
      </g>
      <path d="M20 26.4v4.4" stroke="#2c2531" strokeWidth="1.3" strokeLinecap="round" />
      <rect x="12" y="30" width="16" height="48" rx="1.6" fill={`url(#${id("wax")})`} />
      <ellipse cx="20" cy="30.6" rx="8" ry="1.7" fill="#f6efe2" />
      <path d="M14.2 30.6v4.2a1.4 1.4 0 0 0 2.8 0v-4.2Z" fill="#e6dac4" />
      <path className="candle-drip" d="M25.6 30.6v11a2 2 0 0 1-4 0v-11Z" fill={BLOOD} />
    </svg>
  );
}

/** D: a heartbeat traced across, two beats and a pause; full screen, the logo pulses with it. */
function Heartbeat() {
  const line = "M0 22H30L33 19L36 22H40L43 26L47 5L51 34L54 22H58L61 25L64 11L67 30L70 22H76L80 17L85 22H120";
  return (
    <svg viewBox="0 0 120 40" className="loader-art" aria-hidden="true" focusable="false">
      <path className="heart-trace" d={line} pathLength={100} />
      <path className="heart-sweep" d={line} pathLength={100} />
    </svg>
  );
}

export type Loader = {
  /** Its name, as the custodian picks it. */
  label: string;
  /** What it does, in a line. */
  about: string;
  Art: ComponentType;
};

/** Every loading animation, by the name the API keeps it under. */
export const loaders: Record<Motif, Loader> = {
  drip: { label: "Blood drip", about: "A drop gathers, falls and ripples in a small pool.", Art: Drip },
  rising: { label: "Rising blood", about: "A chalice fills with blood, then drains.", Art: Rising },
  candle: { label: "Candle", about: "A flame flickers as red wax runs down the candle.", Art: Candle },
  heartbeat: { label: "Heartbeat", about: "Two beats and a pause; full screen, the logo pulses with them.", Art: Heartbeat },
};

export type LoaderSize = "full" | "block" | "compact";

/** A motif's animation, at a size: full screen under the logo, in a card, or beside a line of text. */
export function LoaderMark({ motif, size }: { motif: Motif; size: LoaderSize }) {
  const { Art } = loaders[motif];
  return (
    <span className={`loader loader-${size} loader-${motif}`} aria-hidden="true">
      <Art />
    </span>
  );
}

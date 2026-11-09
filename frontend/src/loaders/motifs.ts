import type { components } from "../api/schema";

/** A loading animation, as the custodian chooses it (Custodian › Settings). */
export type Motif = components["schemas"]["AppearanceOut"]["loading_animation"][string];
/** The loading animation by splat: "default" for every splat without its own. */
export type MotifsBySplat = components["schemas"]["AppearanceOut"]["loading_animation"];

export const DEFAULT_MOTIF: Motif = "drip";

/** Every motif, in the order the custodian is offered them. */
export const MOTIFS: readonly Motif[] = ["drip", "rising", "candle", "heartbeat"];

/**
 * Where the last motif seen is kept on this device, for the loading screen in
 * index.html, which shows before the app (and the API's answer) arrives.
 */
export const MOTIF_KEY = "horatio.loader";

export function isMotif(value: unknown): value is Motif {
  return typeof value === "string" && (MOTIFS as readonly string[]).includes(value);
}

/** The motif for a splat: its own where it has one, else the default. */
export function motifFor(bySplat: MotifsBySplat | undefined, splat = "default"): Motif {
  const chosen = bySplat?.[splat] ?? bySplat?.default;
  return isMotif(chosen) ? chosen : DEFAULT_MOTIF;
}

/** The motif last seen on this device, or the default. */
export function cachedMotif(storage: Storage | undefined = globalThis.localStorage): Motif {
  try {
    const kept = storage?.getItem(MOTIF_KEY);
    return isMotif(kept) ? kept : DEFAULT_MOTIF;
  } catch {
    return DEFAULT_MOTIF;
  }
}

export function rememberMotif(motif: Motif, storage: Storage | undefined = globalThis.localStorage): void {
  try {
    storage?.setItem(MOTIF_KEY, motif);
  } catch {
    // Only a convenience: the loading screen falls back to the default.
  }
}

/**
 * The script index.html runs as it loads, before the app: it marks the loading
 * screen with the motif last seen here, so that one shows (loaders.css).
 */
export function chooseOnLoad(): string {
  return `(function(){var m=${JSON.stringify(DEFAULT_MOTIF)};try{var k=localStorage.getItem(${JSON.stringify(MOTIF_KEY)});if(${JSON.stringify(MOTIFS)}.indexOf(k)>=0)m=k}catch(e){}var s=document.querySelector("#root>.splash");if(s)s.setAttribute("data-motif",m)})();`;
}

import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { cachedMotif, motifFor, rememberMotif, type Motif } from "./motifs";

/** How Horatio looks, as the custodian chose: anyone may ask, signed in or not. */
export function useAppearance() {
  return useQuery({
    queryKey: ["appearance"],
    queryFn: async () => {
      const appearance = await unwrap(api.GET("/api/appearance"));
      // For index.html's loading screen next time, which shows before anything is asked.
      rememberMotif(motifFor(appearance.loading_animation));
      return appearance;
    },
    staleTime: 10 * 60_000,
  });
}

/** The loading animation to show: the custodian's choice, or until that is known,
 * the one last seen on this device. A splat may have its own (none do yet). */
export function useMotif(splat?: string): Motif {
  const appearance = useAppearance();
  return appearance.data ? motifFor(appearance.data.loading_animation, splat) : cachedMotif();
}

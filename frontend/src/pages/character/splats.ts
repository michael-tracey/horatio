import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { SplatOut, TroupeOut } from "../../api/types";

/** What a character can be: the splats there are rules for, vampires first (`GET /rules`). */
export function useSplats() {
  return useQuery({
    queryKey: ["splats"],
    queryFn: () => unwrap(api.GET("/api/rules")),
    staleTime: 5 * 60_000,
  });
}

/** The splats a new character can be when built for `troupe`: those it takes, or every one with no troupe. */
export function splatsFor(splats: SplatOut[], troupe: Pick<TroupeOut, "allowed_splats"> | undefined): SplatOut[] {
  return troupe ? splats.filter((s) => troupe.allowed_splats.includes(s.splat)) : splats;
}

/** Whether a character of `splat` is bound to a domitor, whose clan it takes: a ghoul. */
export function useHasDomitor(splat: string): boolean | undefined {
  const splats = useSplats();
  return splats.data ? !!splats.data.find((s) => s.splat === splat)?.has_domitor : undefined;
}

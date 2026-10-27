import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { useSplats } from "../character/splats";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * Which splat's house rules are shown: a troupe keeps its prices, starting
 * points and downtime actions for each splat apart. Vampire always; any other
 * splat the troupe takes, such as Ghoul. The choice is in the address (`?splat=`),
 * so Costs, Starting points and Downtime actions keep it between them.
 */
export function useHouseSplat(troupeId: string): { splat: string; picker: ReactNode } {
  const [params, setParams] = useSearchParams();
  const splats = useSplats();
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  const offered = (splats.data ?? []).filter((s) => s.splat === "vampire" || troupe.data?.allowed_splats.includes(s.splat));
  const wanted = params.get("splat") ?? "vampire";
  const splat = offered.some((s) => s.splat === wanted) ? wanted : "vampire";
  const choose = (next: string) =>
    setParams(
      (p) => {
        if (next === "vampire") p.delete("splat");
        else p.set("splat", next);
        return p;
      },
      { replace: true },
    );
  const picker =
    offered.length > 1 ? (
      <div className="flex flex-wrap items-center gap-2 text-sm" role="group" aria-label="House rules for">
        <span className="text-mist">House rules for</span>
        {offered.map((s) => (
          <button
            key={s.splat}
            type="button"
            aria-pressed={s.splat === splat}
            onClick={() => choose(s.splat)}
            className={cx("min-h-10 rounded-full border px-4", s.splat === splat ? "border-gold bg-gold/10 text-gold" : "border-ash text-mist hover:text-parchment")}
          >
            {s.label}
          </button>
        ))}
      </div>
    ) : null;
  return { splat, picker };
}

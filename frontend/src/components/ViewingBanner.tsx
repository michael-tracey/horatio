import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, unwrap } from "../api/client";
import { useDates } from "../dates";
import { useAction } from "../hooks";

/** On every page while the custodian views Horatio as someone: whom, that it is
 * read-only, and Stop. The page reloads when the viewing ends by itself. */
export function ViewingBanner() {
  const viewing = useQuery({ queryKey: ["view-as"], queryFn: () => unwrap(api.GET("/api/view-as")), staleTime: 60_000 });
  const dates = useDates();
  const stop = useAction(async () => {
    await unwrap(api.POST("/api/view-as/stop"));
    window.location.assign("/custodian/people");
  });
  const endsAt = viewing.data?.ends_at;

  useEffect(() => {
    if (!endsAt) return;
    const timer = window.setTimeout(() => window.location.reload(), Math.max(new Date(endsAt).getTime() - Date.now(), 0) + 1000);
    return () => window.clearTimeout(timer);
  }, [endsAt]);

  if (!viewing.data) return null;
  return (
    <div role="status" className="border-b border-gold/60 bg-gold/20 text-sm print:hidden">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-3 gap-y-1 px-4 py-2">
        <p>
          <strong>Viewing as @{viewing.data.handle}, read-only.</strong> <span className="text-mist">Until {dates.time(viewing.data.ends_at)}.</span>
        </p>
        <button type="button" className="rounded-md border border-gold/60 px-3 py-1 hover:bg-gold/20" disabled={stop.isPending} onClick={() => stop.mutate(undefined)}>
          Stop
        </button>
      </div>
    </div>
  );
}

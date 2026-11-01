import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, unwrap } from "../../api/client";
import { Badge, Empty, ErrorText, Loading, RichText } from "../../components/ui";
import { useDates } from "../../dates";
import { resultParts } from "./results";
import { isNew, markSeen, seenUpTo } from "./resultsSeen";

/**
 * Delivered downtime results, newest cycle first. The newest is open, and older
 * ones fold away under their name and date; one that is new to the player since
 * they last looked on this device is marked so, and open too. Each response sits
 * under the action it answers.
 */
export function ResultsTab({ characterId }: { characterId: string }) {
  const results = useQuery({
    queryKey: ["results", characterId],
    queryFn: () =>
      unwrap(api.GET("/api/characters/{character_id}/downtime/results", { params: { path: { character_id: characterId } } })),
  });
  const dates = useDates();
  // What was seen when the tab opened: marking these seen below mustn't unmark them here.
  const [seen] = useState(() => seenUpTo(characterId));
  const [now] = useState(() => Date.now());
  // Shown here, so no longer new on the tab's count.
  useEffect(() => {
    const newest = (results.data ?? []).map((r) => r.delivered_at).filter((d) => d !== null)
      .sort((a, b) => Date.parse(a) - Date.parse(b))
      .at(-1);
    if (newest) markSeen(characterId, newest);
  }, [characterId, results.data]);
  if (results.isPending) return <Loading />;
  if (results.error) return <ErrorText error={results.error} />;
  if (!results.data.length) return <Empty>No downtime results have been delivered yet.</Empty>;
  return (
    <div className="flex flex-col gap-4">
      {results.data.map((r, i) => {
        const fresh = r.delivered_at !== null && isNew(r.delivered_at, seen, now);
        return (
          <details key={r.cycle_id} open={i === 0 || fresh} className="group rounded-lg border border-ash bg-dusk">
            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 p-4 sm:px-5 [&::-webkit-details-marker]:hidden">
              <span aria-hidden className="text-mist transition-transform group-open:rotate-90">
                ›
              </span>
              <h2 className="text-lg text-gold">{r.cycle_name}</h2>
              {r.delivered_at && (
                <span className="text-sm text-mist">
                  {r.updated ? "Updated" : "Delivered"} <time dateTime={r.delivered_at}>{dates.date(r.delivered_at)}</time>
                </span>
              )}
              {fresh && <Badge tone="gold">New</Badge>}
            </summary>
            <div className="px-4 pb-4 sm:px-5 sm:pb-5">
              <Result message={r.message} />
            </div>
          </details>
        );
      })}
    </div>
  );
}

/** One cycle's results: each response under the action it answers, or the message as
 * it is when it isn't in Horatio's own shape. */
function Result({ message }: { message: string }) {
  const parts = resultParts(message);
  if (!parts) return <RichText text={message} />;
  return (
    <div className="flex flex-col divide-y divide-ash/60">
      {parts.map((p, i) => (
        <section key={i} className="py-3 first:pt-0 last:pb-0">
          <h3 className="text-sm font-semibold text-parchment">{p.heading}</h3>
          {p.action && (
            <div className="mt-2 border-l-2 border-line pl-3 text-mist">
              <p className="text-xs">{p.actionLabel}</p>
              <RichText text={p.action} />
            </div>
          )}
          {p.result && (
            <div className="mt-2">
              <p className="text-xs text-gold">Result</p>
              <RichText text={p.result} />
            </div>
          )}
        </section>
      ))}
    </div>
  );
}

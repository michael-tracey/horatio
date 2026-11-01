import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { WaitingLine } from "../../api/types";
import { useDates } from "../../dates";
import { dueText } from "./waiting";

/** What waits on the signed-in staff member in a troupe: one request, shared by its tabs, its About page and the home page. */
export function useWaiting(troupeId: string, enabled = true) {
  return useQuery({
    queryKey: ["waiting", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/waiting", { params: { path: { troupe_id: troupeId } } })),
    enabled,
    refetchInterval: 60_000,
  });
}

/** One line per kind of work, each a link straight to it: the open cycle with when it is due, then the rest with their counts. */
export function WaitingList({ lines, label }: { lines: WaitingLine[]; label: string }) {
  const dates = useDates();
  const today = dates.toInput(new Date()).slice(0, 10);
  return (
    <ul className="divide-y divide-ash" aria-label={label}>
      {lines.map((line) => (
        <li key={`${line.kind} ${line.link}`}>
          <Link to={line.link} className="flex items-center justify-between gap-3 py-2 text-sm hover:text-gold">
            <span>
              {line.label}
              {line.due_at && <span className="whitespace-nowrap text-mist"> · {dueText(today, dates.toInput(line.due_at).slice(0, 10))}</span>}
            </span>
            {line.count !== null && (
              <span className="min-w-8 rounded-full border border-gold/50 px-2 py-0.5 text-center text-xs text-gold tabular-nums">{line.count}</span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}

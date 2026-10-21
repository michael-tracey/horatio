import { Link } from "react-router";
import type { LogEntry } from "../api/types";
import { useDates } from "../dates";

/** A log, newest first: when, who, and what, on every line. */
export function LogList({ entries, linkTo }: { entries: LogEntry[]; linkTo?: (entry: LogEntry) => string | null }) {
  const dates = useDates();
  return (
    <ol className="divide-y divide-ash/50 text-sm">
      {entries.map((entry) => {
        const link = linkTo?.(entry);
        return (
          <li key={entry.id} className="flex flex-col gap-0.5 py-2 sm:flex-row sm:gap-4">
            <span className="flex shrink-0 gap-3 text-xs text-mist sm:w-80 sm:text-sm">
              <time dateTime={entry.at} className="whitespace-nowrap sm:w-48">
                {dates.dateTime(entry.at)}
              </time>
              {entry.actor_id && entry.actor_name ? (
                <Link className="truncate hover:text-gold" to={`/players/${entry.actor_id}`}>
                  {entry.actor_name}
                </Link>
              ) : (
                <span className="truncate">{entry.actor_name ?? "Horatio"}</span>
              )}
            </span>
            <span>
              {link ? (
                <Link className="hover:text-gold" to={link}>
                  {entry.message}
                </Link>
              ) : (
                entry.message
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

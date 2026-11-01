import { Link } from "react-router";
import type { LogEntry } from "../api/types";
import { useDates } from "../dates";

/** Where a log line names who did it, so it does once: as the sentence's own first
 * words ("jane raised…"), as "by jane" after a sentence that leaves them out, or
 * nowhere more when the sentence names them elsewhere or no one did it. `rest` is
 * the sentence after the name, when it leads. */
export function actorPlace(entry: Pick<LogEntry, "actor_name" | "message">): {
  actor: "lead" | "after" | null;
  rest: string;
} {
  const name = entry.actor_name;
  if (!name) return { actor: null, rest: entry.message };
  if (entry.message.startsWith(`${name} `)) return { actor: "lead", rest: entry.message.slice(name.length) };
  const named = new RegExp(`(?<!\\w)${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?!\\w)`).test(entry.message);
  return { actor: named ? null : "after", rest: entry.message };
}

/** A log, newest first: when, and what, with who did it named once. */
export function LogList({ entries, linkTo }: { entries: LogEntry[]; linkTo?: (entry: LogEntry) => string | null }) {
  const dates = useDates();
  return (
    <ol className="divide-y divide-ash/50 text-sm">
      {entries.map((entry) => {
        const link = linkTo?.(entry);
        const { actor, rest } = actorPlace(entry);
        const who =
          entry.actor_id && entry.actor_name ? (
            <Link className="font-medium hover:text-gold" to={`/players/${entry.actor_id}`}>
              {entry.actor_name}
            </Link>
          ) : (
            entry.actor_name
          );
        return (
          <li key={entry.id} className="flex flex-col gap-0.5 py-2 sm:flex-row sm:gap-4">
            <time dateTime={entry.at} className="shrink-0 text-xs whitespace-nowrap text-mist sm:w-48 sm:text-sm">
              {dates.dateTime(entry.at)}
            </time>
            <span>
              {actor === "lead" && who}
              {link ? (
                <Link className="hover:text-gold" to={link}>
                  {rest}
                </Link>
              ) : (
                rest
              )}
              {actor === "after" && <span className="text-mist"> · by {who}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

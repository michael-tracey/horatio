import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { InfluenceEntryOut } from "../../api/types";
import { Button, ErrorText } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

/** The discovery blocks answers added to an entry, each of which can be taken off again if it was a mistake. */
export function BlockSources({ entry }: { entry: InfluenceEntryOut }) {
  const dates = useDates();
  const remove = useAction((id: string) => unwrap(api.DELETE("/api/influence-blocks/{block_id}", { params: { path: { block_id: id } } })));
  if (!entry.blocked_by?.length) return null;
  return (
    <div>
      <ul className="flex flex-col gap-1 text-xs text-mist" aria-label={`Blocks on ${entry.short_id}`}>
        {entry.blocked_by.map((b) => (
          <li key={b.id} className="flex flex-wrap items-center gap-x-2">
            <span>
              Blocked by {b.character_name ?? "a downtime answer since removed"}
              {b.cycle_name && b.cycle_id && (
                <>
                  {" "}
                  in{" "}
                  <Link to={`/cycles/${b.cycle_id}`} className="hover:text-gold">
                    {b.cycle_name}
                  </Link>
                </>
              )}
              , accepted by {b.added_by_name} on {dates.date(b.added_at)}
            </span>
            <Button
              variant="ghost"
              className="min-h-6 px-2 py-0"
              onClick={() => {
                if (window.confirm(`Take this block off ${entry.short_id}?`)) remove.mutate(b.id);
              }}
            >
              Take it off
            </Button>
          </li>
        ))}
      </ul>
      <ErrorText error={remove.error} />
    </div>
  );
}

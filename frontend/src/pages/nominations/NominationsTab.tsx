import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { EntryOut, MonthOut } from "../../api/types";
import { Button, Card, Empty, ErrorText, Loading } from "../../components/ui";
import { useAction } from "../../hooks";
import { monthOrder } from "./nominations";

/**
 * The troupe's Player Nominations (#470), for its players and staff: each month
 * published, newest first, its nominations in the order shuffled once as they were
 * published, without their authors. Running staff can unstar one from here, which
 * takes it out of the footer.
 */
export function NominationsTab({ troupeId, canStar }: { troupeId: string; canStar: boolean }) {
  const months = useQuery({
    queryKey: ["nominations", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/nominations", { params: { path: { troupe_id: troupeId } } })),
  });
  if (months.isPending) return <Loading />;
  if (months.error) return <ErrorText error={months.error} />;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        Kind words from the troupe’s players about each other’s roleplaying, written in their downtimes. The storytellers read them first, and publish them each month
        without names. ★ marks those starred for the foot of the troupe’s pages.
      </p>
      {months.data.length === 0 ? <Empty>No Player Nominations are published yet.</Empty> : months.data.map((m) => <Month key={m.cycle_id} month={m} canStar={canStar} />)}
    </div>
  );
}

function Month({ month, canStar }: { month: MonthOut; canStar: boolean }) {
  return (
    <Card title={month.name}>
      {month.nominations.length === 0 ? (
        <p className="text-sm text-mist">None this month.</p>
      ) : (
        <ul aria-label={`${month.name}'s Player Nominations`} className="divide-y divide-ash">
          {monthOrder(month.nominations).map((n) => (
            <Entry key={n.id} entry={n} canStar={canStar} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function Entry({ entry: n, canStar }: { entry: EntryOut; canStar: boolean }) {
  const unstar = useAction(() => unwrap(api.PUT("/api/nominations/{nomination_id}/star", { params: { path: { nomination_id: n.id } }, body: { starred: false } })));
  return (
    <li className="flex items-start gap-3 py-3">
      <span className="w-4 shrink-0 text-gold" aria-hidden="true">
        {n.starred ? "★" : ""}
      </span>
      <div className="min-w-0 flex-1">
        <p className="whitespace-pre-line wrap-anywhere">{n.text}</p>
        {(n.about || n.starred || n.edited) && (
          <p className="mt-1 text-xs text-mist">
            {[n.about && `About ${n.about}`, n.starred && "Starred", n.edited && "Edited by staff"].filter(Boolean).join(" · ")}
          </p>
        )}
        <ErrorText error={unstar.error} />
      </div>
      {canStar && n.starred && (
        <Button variant="ghost" className="shrink-0" disabled={unstar.isPending} onClick={() => unstar.mutate(undefined)}>
          Unstar
        </Button>
      )}
    </li>
  );
}

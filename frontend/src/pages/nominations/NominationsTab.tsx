import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { EntryOut, MonthOut, RememberedOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { Button, Card, Empty, ErrorText, Loading } from "../../components/ui";
import { useAction } from "../../hooks";
import { monthOrder } from "./nominations";

/**
 * The troupe's Player Nominations (#470) and Remembrances (#471), as it uses them,
 * for its players and staff: each month published, newest first, those remembered
 * that month above its nominations, each in the order shuffled once as they were
 * published, without their authors. Running staff can unstar a nomination from
 * here, which takes it out of the footer.
 */
export function NominationsTab({
  troupeId,
  canStar,
  nominations = true,
  remembrances = false,
}: {
  troupeId: string;
  canStar: boolean;
  nominations?: boolean;
  remembrances?: boolean;
}) {
  const months = useQuery({
    queryKey: ["nominations", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/nominations", { params: { path: { troupe_id: troupeId } } })),
  });
  if (months.isPending) return <Loading />;
  if (months.error) return <ErrorText error={months.error} />;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        {nominations && "Kind words from the troupe’s players about each other’s roleplaying, written in their downtimes. "}
        {remembrances && "Memories of those who have left play, asked for in the downtime after they left. "}
        The storytellers read them first, and publish them each month without names.
        {nominations && " ★ marks the nominations starred for the foot of the troupe’s pages."}
      </p>
      {months.data.length === 0 ? (
        <Empty>Nothing is published yet.</Empty>
      ) : (
        months.data.map((m) => <Month key={m.cycle_id} month={m} canStar={canStar} nominations={nominations} />)
      )}
    </div>
  );
}

function Month({ month, canStar, nominations }: { month: MonthOut; canStar: boolean; nominations: boolean }) {
  const remembered = month.remembrances ?? [];
  return (
    <Card title={month.name}>
      {remembered.length > 0 && (
        <section aria-label={`Remembrances in ${month.name}`} className="mb-4 flex flex-col gap-4">
          <h3 className="text-sm tracking-wide text-mist uppercase">Remembrances</h3>
          {remembered.map((r) => (
            <Remembered key={r.character_id} remembered={r} />
          ))}
        </section>
      )}
      {nominations &&
        (month.nominations.length === 0 ? (
          <p className="text-sm text-mist">No nominations this month.</p>
        ) : (
          <>
            {remembered.length > 0 && <h3 className="text-sm tracking-wide text-mist uppercase">Player Nominations</h3>}
            <ul aria-label={`${month.name}'s Player Nominations`} className="divide-y divide-ash">
              {monthOrder(month.nominations).map((n) => (
                <Entry key={n.id} entry={n} canStar={canStar} />
              ))}
            </ul>
          </>
        ))}
    </Card>
  );
}

/** Someone remembered: their portrait and why they left, and the troupe's memories of them, without names. */
function Remembered({ remembered: r }: { remembered: RememberedOut }) {
  return (
    <div className="flex gap-3">
      <Avatar name={r.name} picture={r.picture} clan={r.clan} size="md" />
      <div className="min-w-0 flex-1">
        <p className="font-display text-base text-parchment">{r.name}</p>
        {r.reason && <p className="text-xs text-mist">{r.reason}</p>}
        <ul aria-label={`Memories of ${r.name}`} className="mt-1 divide-y divide-ash">
          {monthOrder(r.memories).map((m) => (
            <li key={m.id} className="py-2">
              <p className="whitespace-pre-line wrap-anywhere">{m.text}</p>
              {m.edited && <p className="mt-0.5 text-xs text-mist">Edited by staff</p>}
            </li>
          ))}
        </ul>
      </div>
    </div>
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

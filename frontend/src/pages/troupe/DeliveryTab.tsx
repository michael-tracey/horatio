import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CycleOut, DeliveryOut, ParticipantDeliveries } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Loading, Notice } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { deliveredText, deliveryPlan } from "./delivery";

const CHANNEL_NAMES: Record<string, string> = { horatio: "In Horatio", discord: "Discord", email: "Email" };
export const channelName = (channel: string) => CHANNEL_NAMES[channel] ?? channel;

/**
 * Delivering a closed cycle's results, and how each participant's went out on
 * each channel: in Horatio, and on each of the troupe's connectors. By default
 * only downtimes with every response written go; a downtime delivered before
 * and changed since goes again as an update. Copies on connectors are sent in
 * the background; a failure can be retried, or marked as sent by someone who
 * sent it themselves.
 */
export function DeliveryTab({ cycle }: { cycle: CycleOut }) {
  const status = useQuery({
    queryKey: ["deliveries", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/deliveries", { params: { path: { cycle_id: cycle.id } } })),
    // Copies still waiting are sent in the background; keep the page up to date.
    refetchInterval: (query) =>
      query.state.data?.participants.some((p) => Object.values(p.deliveries).some((d) => d?.status === "pending")) ? 5_000 : false,
  });
  if (status.isPending) return <Loading />;
  if (status.error) return <ErrorText error={status.error} />;
  const { channels, participants } = status.data;
  const closed = cycle.status === "closed" || cycle.status === "complete";

  return (
    <div className="flex flex-col gap-6">
      {closed ? <DeliverCard cycle={cycle} participants={participants} /> : <Notice>After closing, results go out from here.</Notice>}
      <Card title="Delivery">
        <p className="mb-4 text-sm text-mist">
          Results always appear in Horatio. {channels.length > 1 ? "Each connector the troupe has on gets a copy." : "The troupe has no connectors on; "}
          {channels.length === 1 && (
            <>
              <Link to={`/troupes/${cycle.troupe_id}/connectors`} className="underline">
                set one up
              </Link>{" "}
              to send copies to Discord or email.
            </>
          )}
        </p>
        {participants.length === 0 ? (
          <Empty>Nothing submitted to deliver.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ash text-left text-xs text-mist">
                  <th className="py-2 pr-4 font-normal">Character</th>
                  <th className="py-2 pr-4 font-normal">Written</th>
                  {channels.map((c) => (
                    <th key={c} className="py-2 pr-4 font-normal">
                      {channelName(c)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-ash">
                {participants.map((p) => (
                  <tr key={p.character_id}>
                    <td className="py-2.5 pr-4 align-top text-parchment">
                      <span className="flex flex-col items-start gap-1">
                        {p.character_name}
                        {p.changed && <Badge tone="gold">changed since delivery</Badge>}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 align-top whitespace-nowrap">
                      {p.answered} of {p.to_answer}
                    </td>
                    {channels.map((c) => (
                      <td key={c} className="py-2.5 pr-4 align-top">
                        <DeliveryCell delivery={p.deliveries[c]} who={p.character_name} channel={c} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

/** Before delivering, what will go: the finished downtimes, and the partly
 * written ones only if asked. */
function DeliverCard({ cycle, participants }: { cycle: CycleOut; participants: ParticipantDeliveries[] }) {
  const [partial, setPartial] = useState(false);
  const [done, setDone] = useState<{ delivered: number; updated: number; queued: number } | null>(null);
  const deliver = useAction(async () =>
    setDone(await unwrap(api.POST("/api/cycles/{cycle_id}/deliver", { params: { path: { cycle_id: cycle.id } }, body: { partial } }))),
  );
  const plan = deliveryPlan(participants);
  const going = plan.ready.length + (partial ? plan.partial.length : 0);
  const names = (list: ParticipantDeliveries[], detail?: (p: ParticipantDeliveries) => string) =>
    list.map((p) => `${p.character_name}${detail ? ` (${detail(p)})` : ""}`).join(", ");

  return (
    <Card title="Deliver results">
      <p className="text-sm">
        {plan.finished} of {participants.length} downtime{participants.length === 1 ? " has" : "s have"} every response written.
      </p>
      <ul className="mt-2 flex flex-col gap-1 text-sm">
        {plan.ready.length > 0 && (
          <li>
            <span className="text-mist">Ready:</span> {names(plan.ready, (p) => (p.delivered ? "update" : "new"))}
          </li>
        )}
        {plan.partial.length > 0 && (
          <li>
            <span className="text-mist">Partly written:</span> {names(plan.partial, (p) => `${p.answered} of ${p.to_answer}${p.delivered ? ", update" : ""}`)}
          </li>
        )}
        {plan.current.length > 0 && (
          <li>
            <span className="text-mist">Delivered, nothing changed since:</span> {names(plan.current)}
          </li>
        )}
        {plan.unwritten.length > 0 && (
          <li>
            <span className="text-mist">Nothing written yet:</span> {names(plan.unwritten)}
          </li>
        )}
      </ul>
      {plan.partial.length > 0 && (
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={partial} onChange={(e) => setPartial(e.target.checked)} />
          Also deliver the {plan.partial.length} partly written, with what's written so far
        </label>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button disabled={going === 0 || deliver.isPending} onClick={() => deliver.mutate(undefined)}>
          {going === 0 ? "Nothing to deliver" : `Deliver ${going} downtime${going === 1 ? "" : "s"}`}
        </Button>
        {going > 0 && cycle.status === "complete" && <span className="text-xs text-mist">The cycle is complete; these are the last results.</span>}
      </div>
      {done !== null && (
        <Notice>
          {deliveredText(done.delivered, done.updated)}
          {done.queued > 0 && ` ${done.queued} ${done.queued === 1 ? "copy is" : "copies are"} on the way through the troupe's connectors.`}
        </Notice>
      )}
      <ErrorText error={deliver.error} />
    </Card>
  );
}

function DeliveryCell({ delivery, who, channel }: { delivery: DeliveryOut | undefined; who: string; channel: string }) {
  const path = { params: { path: { delivery_id: delivery?.id ?? "" } } };
  const retry = useAction(() => unwrap(api.POST("/api/deliveries/{delivery_id}/retry", path)));
  const mark = useAction(() => unwrap(api.POST("/api/deliveries/{delivery_id}/mark-sent", path)));
  const dates = useDates();
  if (!delivery) return <span className="text-mist">—</span>;
  const label = `${who}'s ${channelName(channel)} delivery`;
  return (
    <div className="flex flex-col items-start gap-1">
      <span className="flex flex-wrap items-center gap-1.5">
        <Badge tone={delivery.status === "sent" ? "mist" : delivery.status === "failed" ? "blood" : "gold"}>
          {delivery.status === "sent" ? (delivery.marked_by ? "sent by hand" : "sent") : delivery.status === "failed" ? "failed" : "waiting"}
        </Badge>
        {delivery.test_mode && <Badge>test</Badge>}
      </span>
      {delivery.marked_by && <span className="text-xs text-mist">marked by {delivery.marked_by}</span>}
      {delivery.status === "pending" && delivery.attempts > 0 && (
        <span className="text-xs text-mist">
          {delivery.attempts} {delivery.attempts === 1 ? "try" : "tries"} so far
          {delivery.next_attempt_at && `; next at ${dates.time(delivery.next_attempt_at)}`}
        </span>
      )}
      {delivery.last_error && delivery.status !== "sent" && <span className="text-xs text-blood-bright">{delivery.last_error}</span>}
      {delivery.status !== "sent" && (
        <span className="flex flex-wrap gap-1">
          {delivery.status === "failed" && (
            <Button variant="secondary" className="min-h-8 px-2 text-xs" aria-label={`Retry ${label}`} onClick={() => retry.mutate(undefined)}>
              Retry
            </Button>
          )}
          <Button variant="ghost" className="min-h-8 px-2 text-xs" aria-label={`Mark ${label} as sent`} onClick={() => mark.mutate(undefined)}>
            Mark as sent manually
          </Button>
        </span>
      )}
      <ErrorText error={retry.error ?? mark.error} />
    </div>
  );
}

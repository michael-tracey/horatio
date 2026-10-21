import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { DeliveryOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Loading } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

const CHANNEL_NAMES: Record<string, string> = { horatio: "In Horatio", discord: "Discord", email: "Email" };
export const channelName = (channel: string) => CHANNEL_NAMES[channel] ?? channel;

/**
 * How each participant's results went out on each channel: in Horatio, and on
 * each of the troupe's connectors. Copies on connectors are sent in the
 * background; a failure can be retried, or marked as sent by someone who sent it
 * themselves.
 */
export function DeliveryTab({ cycleId, troupeId }: { cycleId: string; troupeId: string }) {
  const status = useQuery({
    queryKey: ["deliveries", cycleId],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/deliveries", { params: { path: { cycle_id: cycleId } } })),
    // Copies still waiting are sent in the background; keep the page up to date.
    refetchInterval: (query) =>
      query.state.data?.participants.some((p) => Object.values(p.deliveries).some((d) => d?.status === "pending")) ? 5_000 : false,
  });
  if (status.isPending) return <Loading />;
  if (status.error) return <ErrorText error={status.error} />;
  const { channels, participants } = status.data;

  return (
    <Card title="Delivery">
      <p className="mb-4 text-sm text-mist">
        Results always appear in Horatio. {channels.length > 1 ? "Each connector the troupe has on gets a copy." : "The troupe has no connectors on; "}
        {channels.length === 1 && (
          <>
            <Link to={`/troupes/${troupeId}/connectors`} className="underline">
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
                  <td className="py-2.5 pr-4 align-top text-parchment">{p.character_name}</td>
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

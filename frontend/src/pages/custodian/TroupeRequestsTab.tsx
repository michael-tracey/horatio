import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeRequestOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Loading, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { requestStatus, when } from "../troupeRequests";

export function useTroupeRequests(enabled = true) {
  return useQuery({ queryKey: ["troupe-requests"], queryFn: () => unwrap(api.GET("/api/troupe-requests")), enabled });
}

/** New troupes people have asked for: approve one to make it, led by whoever asked. */
export function TroupeRequestsTab() {
  const requests = useTroupeRequests();
  if (requests.isPending) return <Loading />;
  const waiting = requests.data?.filter((r) => r.status === "pending") ?? [];
  const done = requests.data?.filter((r) => r.status !== "pending") ?? [];

  return (
    <div className="flex flex-col gap-6">
      <Card title="Waiting">
        {waiting.length ? (
          <ul className="divide-y divide-ash">
            {waiting.map((r) => (
              <Waiting key={r.id} request={r} />
            ))}
          </ul>
        ) : (
          <Empty>Nobody is waiting for a troupe.</Empty>
        )}
        <ErrorText error={requests.error} />
      </Card>
      {done.length > 0 && (
        <Card title="Decided">
          <ul className="divide-y divide-ash text-sm">
            {done.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>
                  {r.troupe_id ? (
                    <Link to={`/troupes/${r.troupe_id}`} className="text-gold hover:underline">
                      {r.name}
                    </Link>
                  ) : (
                    r.name
                  )}{" "}
                  <span className="text-mist">for {r.requester_name}</span>
                  {r.reason && <span className="block text-xs text-mist">{r.reason}</span>}
                </span>
                <span className="flex items-center gap-2 text-xs text-mist">
                  {r.decided_at && when(r.decided_at)}
                  <Badge tone={r.status === "approved" ? "gold" : "mist"}>{requestStatus(r.status)}</Badge>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function Waiting({ request: r }: { request: TroupeRequestOut }) {
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const approve = useAction(() => unwrap(api.POST("/api/troupe-requests/{request_id}/approve", { params: { path: { request_id: r.id } } })));
  const decline = useAction(() =>
    unwrap(api.POST("/api/troupe-requests/{request_id}/decline", { params: { path: { request_id: r.id } }, body: { reason } })),
  );
  const busy = approve.isPending || decline.isPending;

  return (
    <li className="flex flex-col gap-2 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-parchment">{r.name}</h3>
        <span className="text-xs text-mist">
          asked by{" "}
          <Link to={`/players/${r.requester_id}`} className="text-gold hover:underline">
            {r.requester_name}
          </Link>
          , {when(r.created_at)}
        </span>
      </div>
      {r.description && <p className="text-sm whitespace-pre-line">{r.description}</p>}
      {r.note && (
        <p className="border-l-2 border-ash pl-3 text-sm whitespace-pre-line text-mist">
          <span className="sr-only">Their note: </span>
          {r.note}
        </p>
      )}
      {declining ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            decline.mutate(undefined);
          }}
        >
          <Field label="Why not? (optional)" hint={`${r.requester_name} sees this.`}>
            <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" variant="danger" disabled={busy}>
              Decline
            </Button>
            <Button type="button" variant="ghost" onClick={() => setDeclining(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" disabled={busy} onClick={() => approve.mutate(undefined)}>
            Approve and make the troupe
          </Button>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => setDeclining(true)}>
            Decline…
          </Button>
          <span className="text-xs text-mist">Approving makes {r.requester_name} its lead storyteller.</span>
        </div>
      )}
      <ErrorText error={approve.error ?? decline.error} />
    </li>
  );
}

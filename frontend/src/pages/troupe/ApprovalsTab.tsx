import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { QueuedApproval } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Loading, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { describeDifference, settlementLabel } from "../../settlements";

type State = "pending" | "approved" | "declined" | "withdrawn";


export function ApprovalsTab({ troupeId }: { troupeId: string }) {
  const [state, setState] = useState<State>("pending");
  const queue = useQuery({
    queryKey: ["approvals", troupeId, state],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/approvals", { params: { path: { troupe_id: troupeId }, query: { state } } })),
  });

  return (
    <>
      <div className="mb-4 flex gap-2">
        {(["pending", "approved", "declined"] as State[]).map((s) => (
          <Button key={s} variant={s === state ? "secondary" : "ghost"} onClick={() => setState(s)} className="capitalize">
            {s}
          </Button>
        ))}
      </div>
      {queue.isPending ? (
        <Loading />
      ) : queue.data?.length ? (
        <div className="flex flex-col gap-4">
          {queue.data.map((a) => (
            <ApprovalCard key={a.id} approval={a} />
          ))}
        </div>
      ) : (
        <Empty>Nothing {state}.</Empty>
      )}
      <ErrorText error={queue.error} />
    </>
  );
}

function ApprovalCard({ approval }: { approval: QueuedApproval }) {
  const [note, setNote] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const decide = useAction((approve: boolean) =>
    unwrap(
      api.POST(approve ? "/api/approvals/{approval_id}/approve" : "/api/approvals/{approval_id}/decline", {
        params: { path: { approval_id: approval.id } },
        body: {
          note,
          settlements: Object.entries(overrides).map(([item_id, settlement]) => ({
            item_id,
            settlement: settlement as "keep_price",
          })),
        },
      }),
    ),
  );
  const pending = approval.status === "pending";
  const joining = approval.kind === "home_troupe_change";

  return (
    <Card
      title={
        <Link to={`/characters/${approval.character_id}`} className="hover:underline">
          {approval.character_name}
        </Link>
      }
      actions={<Badge tone={joining ? "gold" : "mist"}>{joining ? "joining as home troupe" : "sheet changes"}</Badge>}
    >
      {approval.player_note && <p className="mb-3 text-sm italic">"{approval.player_note}"</p>}
      {approval.changes.length > 0 && (
        <ul className="mb-3 text-sm">
          {approval.changes.map((c) => (
            <li key={`${c.category}/${c.name}/${c.detail}`}>
              {c.name}
              {c.detail && `: ${c.detail}`} — {c.approved_rating ?? "new"} → {c.rating ?? "removed"}
            </li>
          ))}
        </ul>
      )}
      {joining && (
        <div className="mb-3 flex flex-col gap-2">
          {approval.reconciliation.length === 0 && <p className="text-sm text-mist">Nothing to reconcile.</p>}
          {approval.reconciliation.map((r) => (
            <Field
              key={r.id}
              label={`${r.trait}${r.detail ? `: ${r.detail}` : ""} — ${describeDifference(r, "here")}`}
            >
              {pending ? (
                <Select value={overrides[r.id] ?? r.proposed_settlement} onChange={(e) => setOverrides({ ...overrides, [r.id]: e.target.value })}>
                  {r.allowed_settlements.map((key) => (
                    <option key={key} value={key}>
                      {settlementLabel(key, r)}
                      {key === r.proposed_settlement ? " (player's choice)" : ""}
                    </option>
                  ))}
                </Select>
              ) : (
                <span className="text-sm">{settlementLabel(r.settlement ?? r.proposed_settlement, r)}</span>
              )}
            </Field>
          ))}
        </div>
      )}
      {pending ? (
        <>
          <Field label="Note to the player">
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <ErrorText error={decide.error} />
          <div className="mt-3 flex gap-2">
            <Button onClick={() => decide.mutate(true)} disabled={decide.isPending}>
              Approve
            </Button>
            <Button variant="danger" onClick={() => decide.mutate(false)} disabled={decide.isPending}>
              Decline
            </Button>
          </div>
        </>
      ) : (
        approval.staff_note && <p className="text-sm text-mist">Note: {approval.staff_note}</p>
      )}
    </Card>
  );
}

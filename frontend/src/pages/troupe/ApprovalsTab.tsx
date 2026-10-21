import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { QueuedApproval, XpReviewOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { describeDifference, settlementLabel } from "../../settlements";
import { joining, type XpChoice } from "./xpRange";

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
  const [xp, setXp] = useState<XpChoice & { extra_reason: string }>({ self_entered: "keep", top_up: null, above_ceiling: "keep", extra: 0, extra_reason: "" });
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
          ...(approval.xp ? { xp } : {}),
        },
      }),
    ),
  );
  const pending = approval.status === "pending";
  const joining = approval.kind === "home_troupe_change";
  const d = approval.discipline;

  return (
    <Card
      title={
        <Link to={`/characters/${approval.character_id}`} className="inline-flex items-center gap-2 hover:underline">
          <Avatar name={approval.character_name} picture={approval.picture} clan={approval.clan} size="xs" />
          {approval.character_name}
        </Link>
      }
      actions={<Badge tone={joining ? "gold" : "mist"}>{joining ? "asking to make this home" : approval.kind === "discipline" ? "discipline" : approval.kind === "review" ? "rule review" : "sheet changes"}</Badge>}
    >
      {approval.player_note && <p className="mb-3 text-sm italic">"{approval.player_note}"</p>}
      {d && (
        <p className="mb-3 text-sm">
          {d.name}
          {d.detail && `: ${d.detail}`} {d.from_rating} → {d.to_rating}, for {d.cost} XP.{" "}
          {d.teacher && <>Taught by {d.teacher}. </>}
          <span className="text-mist">The XP is spent; declining refunds it and takes the dots back.</span>
        </p>
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
      {joining && approval.xp && <XpReview review={approval.xp} pending={pending} choice={xp} onChange={setXp} />}
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

/**
 * The joining character's XP against this troupe's floor and ceiling. Staff
 * accept or remove self-entered XP, top up below the floor (as the player asked,
 * unless changed), keep or remove XP above the ceiling, and may give extra.
 */
function XpReview({
  review: r,
  pending,
  choice,
  onChange,
}: {
  review: XpReviewOut;
  pending: boolean;
  choice: XpChoice & { extra_reason: string };
  onChange: (choice: XpChoice & { extra_reason: string }) => void;
}) {
  const plan = joining(r, choice);
  const intro = (
    <p className="text-sm">
      Given {r.given} XP{r.self_entered > 0 && <>, {r.self_entered} of it self-entered by the player</>}. This troupe's floor is {r.floor} and its
      ceiling {r.ceiling}.
    </p>
  );
  if (!pending) {
    const done = [
      r.self_entered_removed ? `${r.self_entered_removed} self-entered XP removed` : null,
      r.topped_up ? `topped up by ${r.topped_up} XP` : null,
      r.above_ceiling_removed ? `${r.above_ceiling_removed} XP above the ceiling removed` : null,
      r.extra ? `${r.extra} extra XP given` : null,
    ].filter(Boolean);
    return (
      <div className="mb-3 flex flex-col gap-1">
        <h3 className="font-sans text-xs text-mist uppercase">Experience</h3>
        {intro}
        <p className="text-sm text-mist">{done.length ? `On joining: ${done.join(", ")}.` : "Nothing was changed on joining."}</p>
      </div>
    );
  }
  return (
    <div className="mb-3 flex flex-col gap-2">
      <h3 className="font-sans text-xs text-mist uppercase">Experience</h3>
      {intro}
      {r.self_entered > 0 && (
        <Field label={`Self-entered XP: ${r.self_entered}`}>
          <Select value={choice.self_entered} onChange={(e) => onChange({ ...choice, self_entered: e.target.value as "keep" | "remove" })}>
            <option value="keep">Accept it</option>
            <option value="remove">Remove it ({r.self_entered} XP)</option>
          </Select>
        </Field>
      )}
      {plan.below > 0 && (
        <Field label={`Below the floor by ${plan.below} XP`}>
          <Select
            value={String(choice.top_up ?? r.top_up_asked)}
            onChange={(e) => onChange({ ...choice, top_up: e.target.value === "true" })}
          >
            <option value="true">Top up to the floor (+{plan.below} XP){r.top_up_asked ? " (player's choice)" : ""}</option>
            <option value="false">Leave it below the floor{r.top_up_asked ? "" : " (player's choice)"}</option>
          </Select>
        </Field>
      )}
      {plan.above > 0 && (
        <div className="rounded-md border border-blood/60 bg-blood/10 p-2">
          <Field label={`Above the ceiling by ${plan.above} XP`}>
            <Select value={choice.above_ceiling} onChange={(e) => onChange({ ...choice, above_ceiling: e.target.value as "keep" | "remove" })}>
              <option value="keep">Keep it</option>
              <option value="remove">Remove the {plan.above} XP above the ceiling</option>
            </Select>
          </Field>
        </div>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Extra XP">
          <Input
            type="number"
            min={0}
            value={choice.extra}
            onChange={(e) => onChange({ ...choice, extra: Math.max(0, Number(e.target.value) || 0) })}
            className="w-24"
          />
        </Field>
        <div className="min-w-48 flex-1">
          <Field label="Why the extra">
            <Input
              maxLength={500}
              placeholder="Returning player"
              value={choice.extra_reason}
              onChange={(e) => onChange({ ...choice, extra_reason: e.target.value })}
            />
          </Field>
        </div>
      </div>
      <p className="text-xs text-mist">After joining it will have been given {plan.after} XP. Each change is its own entry in its XP history.</p>
    </div>
  );
}

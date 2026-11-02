import { useQuery } from "@tanstack/react-query";
import { HouseMark } from "../../components/HouseMark";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { QueuedApproval, XpReviewOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { useClanName } from "../../components/ClanNames";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { adjusted, DiablerieAdjustFields, DiablerieEffects, type DiablerieAdjust } from "../character/Diablerie";
import { describeDifference, settlementLabel } from "../../settlements";
import { joining, type XpChoice } from "./xpRange";
import { useBackstoryStanding } from "../character/BackstoryTab";
import { ApprovalBackstory } from "./ApprovalBackstory";
import { askedLine } from "./approvals";
import { generationText } from "../../generation";

type State = "pending" | "approved" | "declined" | "withdrawn";
const STATE_NAMES: Record<State, string> = { pending: "Pending", approved: "Approved", declined: "Declined", withdrawn: "Withdrawn" };
type Kind = "home_troupe_change" | "discipline" | "review" | "exception" | "diablerie" | "merit_flaw";

const KINDS: Record<Kind, string> = {
  home_troupe_change: "Home troupe requests",
  discipline: "Disciplines",
  review: "Rule reviews",
  exception: "Exceptions",
  diablerie: "Diablerie",
  merit_flaw: "Merits and flaws",
};

export function ApprovalsTab({ troupeId }: { troupeId: string }) {
  const [state, setState] = useState<State>("pending");
  const [kind, setKind] = useState<Kind | "">("");
  const queue = useQuery({
    queryKey: ["approvals", troupeId, state, kind],
    queryFn: () =>
      unwrap(api.GET("/api/troupes/{troupe_id}/approvals", { params: { path: { troupe_id: troupeId }, query: { state, kind: kind || undefined } } })),
  });

  return (
    <>
      <div className="mb-4 flex flex-wrap gap-2">
        {(["pending", "approved", "declined"] as State[]).map((s) => (
          <Button key={s} variant={s === state ? "secondary" : "ghost"} onClick={() => setState(s)}>
            {STATE_NAMES[s]}
          </Button>
        ))}
        <Select aria-label="Kind" value={kind} onChange={(e) => setKind(e.target.value as Kind | "")} className="w-auto">
          <option value="">Every kind</option>
          {(Object.keys(KINDS) as Kind[]).map((k) => (
            <option key={k} value={k}>
              {KINDS[k]}
            </option>
          ))}
        </Select>
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
  const named = useClanName();
  const [note, setNote] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [xp, setXp] = useState<XpChoice & { extra_reason: string }>({ self_entered: "keep", top_up: null, above_ceiling: "keep", extra: 0, extra_reason: "" });
  const dates = useDates();
  const navigate = useNavigate();
  const [victim, setVictim] = useState("");
  const [adjust, setAdjust] = useState<DiablerieAdjust>({});
  const decide = useAction(({ approve, atCost = false }: { approve: boolean; atCost?: boolean }) =>
    unwrap(
      api.POST(approve ? "/api/approvals/{approval_id}/approve" : "/api/approvals/{approval_id}/decline", {
        params: { path: { approval_id: approval.id } },
        body: {
          note,
          at_cost: atCost,
          settlements: Object.entries(overrides).map(([item_id, settlement]) => ({
            item_id,
            settlement: settlement as "keep_price",
          })),
          ...(approval.xp ? { xp } : {}),
          ...(approve && approval.diablerie?.plan
            ? {
                diablerie: {
                  victim,
                  humanity_lowered: adjust.humanity ?? approval.diablerie.plan.humanity_lowered,
                  beast_traits: adjust.beast ?? approval.diablerie.plan.beast_traits,
                },
              }
            : {}),
        },
      }),
    ),
  );
  const pending = approval.status === "pending";
  const joining = approval.kind === "home_troupe_change";
  // A troupe that requires it accepts a character only with its backstory approved.
  const backstory = useBackstoryStanding(approval.character_id, joining && pending);
  const needsBackstory = joining && pending && !!backstory.data?.required && !backstory.data.approved;
  const d = approval.discipline;
  const ex = approval.exception;
  const dia = approval.diablerie;
  const merit = approval.kind === "merit_flaw" ? d : null;
  const quest = approval.quest;
  // Tied to a quest still under way: the quest decides it.
  const questing = !!quest && (quest.status === "draft" || quest.status === "active");

  return (
    <Card
      title={
        <Link to={`/characters/${approval.character_id}`} className="inline-flex items-center gap-2 hover:underline">
          <Avatar name={approval.character_name} picture={approval.picture} clan={approval.clan} size="xs" />
          {approval.character_name}
        </Link>
      }
      actions={
        <Badge tone={joining || ex ? "gold" : "mist"}>
          {joining
            ? "Asking to make this home"
            : approval.kind === "discipline"
              ? "Discipline"
              : approval.kind === "review"
                ? "Rule review"
                : approval.kind === "exception"
                  ? ex?.free
                    ? "Exception, free"
                    : "Exception"
                  : approval.kind === "diablerie"
                    ? "Diablerie"
                    : approval.kind === "merit_flaw"
                      ? merit?.category === "flaws"
                        ? "Flaw"
                        : "Merit"
                      : "Sheet changes"}
        </Badge>
      }
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-mist" title={approval.asked_at ? dates.dateTime(approval.asked_at) : undefined}>
          {askedLine(approval)}
        </p>
        <Link to={`/characters/${approval.character_id}`}>
          <Button variant="secondary" tabIndex={-1} className="min-h-8 px-3">
            Open sheet
          </Button>
        </Link>
      </div>
      {approval.player_note && <p className="mb-3 text-sm italic">"{approval.player_note}"</p>}
      {d && ex && (
        <div className="mb-3 flex flex-col gap-1 text-sm">
          <p>
            {named(d.name)}
            {d.detail && `: ${d.detail}`}
            {d.house && <HouseMark label={d.house} />} {d.from_rating} → {d.to_rating},{" "}
            {ex.free
              ? `asked for free${ex.normal_cost != null ? ` (at normal cost, ${ex.normal_cost} XP)` : " (it has no normal cost)"}.`
              : `for ${d.cost} XP.`}
          </p>
          {ex.breaks.length > 0 && <p className="text-blood-bright">Against the rules: {named(ex.breaks.join(" "))}</p>}
          {pending && (
            <p className="text-mist">
              It is on the sheet, waiting on you. Approving keeps it, and the sheet stops flagging these rules for it; declining takes it back
              {ex.free ? "" : " and refunds the XP"}.
            </p>
          )}
        </div>
      )}
      {merit && <MeritFlawAsk ask={merit} pending={pending} />}
      {quest && (
        <p className="mb-3 text-sm">
          Answered with the quest{" "}
          <Link to={`/troupes/${approval.troupe_id}/quests/${quest.id}`} className="text-gold hover:text-parchment">
            {quest.name}
          </Link>{" "}
          ({quest.status}).{" "}
          {questing && <span className="text-mist">Completing it approves this; failing or closing it declines it and refunds any XP held.</span>}
        </p>
      )}
      {d && !ex && !merit && (
        <p className="mb-3 text-sm">
          {named(d.name)}
          {d.detail && `: ${d.detail}`}
          {d.house && <HouseMark label={d.house} />} {d.from_rating} → {d.to_rating}, for {d.cost} XP.{" "}
          {d.teacher && <>Taught by {d.teacher}. </>}
          <span className="text-mist">The XP is spent; declining refunds it and takes the dots back.</span>
        </p>
      )}
      {dia && (
        <div className="mb-3 flex flex-col gap-2 text-sm">
          <p>
            Says {approval.character_name} committed diablerie on {dates.day(dia.committed_on)}.
          </p>
          {pending && dia.plan?.refused && <p className="text-blood-bright">{dia.plan.refused}</p>}
          {pending && dia.plan && !dia.plan.refused && (
            <>
              <Field label="Who was diablerized" hint="Optional. Only staff see it.">
                <Input maxLength={200} value={victim} onChange={(e) => setVictim(e.target.value)} />
              </Field>
              <DiablerieAdjustFields plan={dia.plan} adjust={adjust} onChange={setAdjust} />
              <div className="rounded-md border border-ash p-2">
                <p className="mb-1 text-xs text-mist">Approving will:</p>
                <DiablerieEffects effects={adjusted(dia.plan, adjust)} />
              </div>
              <p className="text-xs text-mist">Declining changes nothing on the sheet.</p>
            </>
          )}
          {!pending && dia.victim && <p className="text-xs text-mist">Diablerized: {dia.victim}</p>}
          {!pending && dia.done && <DiablerieEffects effects={dia.done} done />}
        </div>
      )}
      {joining && approval.locks.length > 0 && (
        <p className="mb-3 text-sm">
          Accepting at{" "}
          {approval.locks
            .map((l) => (l.name === "Generation" ? generationText(l.rating ?? 0, l.generation, true) : `${l.name} ${l.rating ?? ""}`.trim()))
            .join(", ")}
          .{" "}
          <span className="text-mist">Accepting locks it: after that the player can't change it.</span>
        </p>
      )}
      {joining && approval.free_choices.length > 0 && (
        <div className="mb-3 flex flex-col gap-1" data-free-choices>
          <h3 className="font-sans text-xs text-mist uppercase">Free traits the player chose</h3>
          <ul className="text-sm">
            {approval.free_choices.map((f) => (
              <li key={f.merit}>
                {f.merit}:{" "}
                {f.picks.length === 0 ? <span className="text-gold">nothing chosen yet</span> : f.picks.join(", ")}
                {f.picks.length > 0 && !f.complete && <span className="text-gold"> (not all chosen)</span>}
              </li>
            ))}
          </ul>
          {pending && <p className="text-xs text-mist">Accepting confirms them: after that the player can't change them.</p>}
        </div>
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
      {joining && pending && <ApprovalBackstory characterId={approval.character_id} />}
      {pending && questing ? null : pending ? (
        <>
          <Field label="Note to the player">
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <ErrorText error={decide.error} />
          {needsBackstory && <p className="mt-2 text-sm text-mist">Approve the backstory first: this troupe needs it approved before accepting the character.</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button onClick={() => decide.mutate({ approve: true })} disabled={decide.isPending || needsBackstory}>
              Approve
            </Button>
            {ex?.free && (
              <Button variant="secondary" onClick={() => decide.mutate({ approve: true, atCost: true })} disabled={decide.isPending}>
                Approve, at normal cost
              </Button>
            )}
            {approval.quest_suggestion && (
              <Button variant="secondary" onClick={() => navigate(`/troupes/${approval.troupe_id}/quests/new?approval=${approval.id}`)}>
                Answer with a quest
              </Button>
            )}
            <Button variant="danger" onClick={() => decide.mutate({ approve: false })} disabled={decide.isPending}>
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

/** A merit or flaw asked to be added or removed: what it changes and what happens to the XP. */
function MeritFlawAsk({ ask: m, pending }: { ask: NonNullable<QueuedApproval["discipline"]>; pending: boolean }) {
  const flaw = m.category === "flaws";
  const adding = m.to_rating > m.from_rating;
  const named = useClanName();
  const name = (
    <>
      {named(m.name)}
      {m.detail && `: ${m.detail}`}
      {m.house && <HouseMark label={m.house} />}
    </>
  );
  const points = adding ? m.to_rating : m.from_rating;
  return (
    <div className="mb-3 flex flex-col gap-1 text-sm">
      <p>
        {adding ? (flaw ? "Take on the flaw " : "Add the merit ") : flaw ? "Buy off the flaw " : "Remove the merit "}
        {name} ({points} {points === 1 ? "point" : "points"})
        {adding && !flaw && `, for ${m.cost} XP`}
        {adding && flaw && `, which gives ${-m.cost} XP`}
        {!adding && flaw && `, for ${m.cost} XP: twice what it gave`}
        {!adding && !flaw && ", with no XP back (MET: VTM p. 236)"}.
      </p>
      {pending && (
        <p className="text-mist">
          It isn't on the sheet yet. Approving {adding ? "puts it on the sheet" : "takes it off the sheet"}
          {(adding && !flaw) || (!adding && !flaw) ? " and takes a downtime action" : ""}
          {m.cost > 0 ? "; declining refunds the XP held." : "; declining leaves the sheet as it is."}
        </p>
      )}
    </div>
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

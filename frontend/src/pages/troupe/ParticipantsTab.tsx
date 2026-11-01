import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CycleOut, ParticipantOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { chaseSummary, nameList, notSubmitted, playersToRemind, standing } from "./cycles";
import { LogInfluenceButton } from "./LogInfluence";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

const SHOWS = ["all", "not-submitted", "submitted"] as const;
type Show = (typeof SHOWS)[number];
const SHOW_NAMES: Record<Show, string> = { all: "All", "not-submitted": "Not submitted", submitted: "Submitted" };

/**
 * Who takes part in a cycle, for chasing submissions while it is open: each
 * character's player, where its downtime stands and when it was last saved,
 * filtered to those not submitted, with a reminder to send them. Staff add a
 * character who joined the troupe after the cycle opened from here too. Each
 * row's ⋯ holds the rest: its actions, adjusting them, logging influence.
 */
export function ParticipantsTab({ cycle }: { cycle: CycleOut }) {
  const path = { params: { path: { cycle_id: cycle.id } } };
  const started = cycle.status !== "draft";
  const participants = useQuery({
    queryKey: ["participants", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/participants", path)),
    enabled: started,
  });
  const reminders = useQuery({
    queryKey: ["reminders", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/reminders", path)),
    enabled: started,
  });
  const [params, setParams] = useSearchParams();
  const asked = params.get("show") as Show | null;
  const show: Show = asked && SHOWS.includes(asked) ? asked : "all";
  const [panel, setPanel] = useState<"remind" | "add" | null>(null);
  const dates = useDates();

  if (!started) return <Empty>Participants are fixed when the cycle opens.</Empty>;
  if (participants.isPending) return <Loading />;
  if (participants.error) return <ErrorText error={participants.error} />;
  const all = participants.data;
  const waiting = notSubmitted(all);
  const submitted = all.filter((p) => standing(p) === "submitted");
  const lists: Record<Show, ParticipantOut[]> = { all, "not-submitted": waiting, submitted };
  const shown = lists[show];
  const open = cycle.status === "open";
  const last = reminders.data?.[0];
  const toggle = (which: "remind" | "add") => setPanel(panel === which ? null : which);

  return (
    <Card
      title="Participants"
      actions={
        open && (
          <div className="flex flex-wrap gap-2">
            {waiting.length > 0 && (
              <Button variant="secondary" aria-expanded={panel === "remind"} onClick={() => toggle("remind")}>
                Remind those not submitted
              </Button>
            )}
            <Button variant="secondary" aria-expanded={panel === "add"} onClick={() => toggle("add")}>
              Add a character
            </Button>
          </div>
        )
      }
    >
      <p className="text-sm">{chaseSummary(all)}</p>
      {last && (
        <p className="mt-1 text-xs text-mist">
          Last reminded {dates.dateTime(last.at)} by {last.by}, {plural(last.players, "player", "players")}.
        </p>
      )}
      {panel === "remind" && open && waiting.length > 0 && <RemindPanel cycle={cycle} participants={all} onDone={() => setPanel(null)} />}
      {panel === "add" && open && <AddPanel cycle={cycle} onDone={() => setPanel(null)} />}

      {all.length > 0 && (
        <div role="group" aria-label="Show" className="mt-4 flex flex-wrap gap-2">
          {SHOWS.map((s) => (
            <Button
              key={s}
              variant={s === show ? "secondary" : "ghost"}
              aria-pressed={s === show}
              onClick={() => setParams(s === "all" ? {} : { show: s }, { replace: true })}
            >
              {SHOW_NAMES[s]} ({lists[s].length})
            </Button>
          ))}
        </div>
      )}

      {all.length === 0 ? (
        <EmptyState title="No one is taking part.">{open && "Add a character whose home is this troupe to start."}</EmptyState>
      ) : shown.length === 0 ? (
        <p className="mt-4 text-sm text-mist">{show === "not-submitted" ? "Every downtime is submitted." : "Nothing submitted yet."}</p>
      ) : (
        <table className="mt-3 w-full text-sm">
          <thead className="max-sm:sr-only">
            <tr className="border-b border-ash text-left text-xs text-mist">
              <th className="py-2 pr-3 font-normal">Character</th>
              <th className="hidden py-2 pr-3 font-normal sm:table-cell">Player</th>
              <th className="py-2 pr-3 font-normal">Status</th>
              <th className="hidden py-2 pr-3 font-normal sm:table-cell">Last saved</th>
              <th className="py-2 font-normal">
                <span className="sr-only">More</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ash">
            {shown.map((p) => (
              <ParticipantRow key={p.id} cycle={cycle} participant={p} />
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function StandingBadge({ participant: p }: { participant: ParticipantOut }) {
  const s = standing(p);
  return (
    <Badge tone={s === "submitted" ? "gold" : s === "removed" ? "blood" : "mist"}>
      {s}
      {p.submitted_late ? " (late)" : ""}
    </Badge>
  );
}

function ParticipantRow({ cycle, participant: p }: { cycle: CycleOut; participant: ParticipantOut }) {
  const [open, setOpen] = useState(false);
  const dates = useDates();
  const submitted = standing(p) === "submitted";
  const savedAt = submitted ? p.submitted_at : p.saved_at;
  return (
    <>
      <tr className={p.removed ? "text-mist" : undefined}>
        <td className="py-2.5 pr-3 align-top">
          <Link to={`/characters/${p.character_id}`} className="inline-flex items-center gap-2 text-parchment hover:underline">
            <Avatar name={p.character_name} picture={p.picture} clan={p.clan} size="xs" />
            {p.character_name}
          </Link>
          {/* On a phone, the player and the time fold in under the name. */}
          <span className="mt-0.5 block text-xs text-mist sm:hidden">
            @{p.player_handle}
            {savedAt && ` · ${submitted ? "submitted" : "saved"} ${dates.dateTime(savedAt)}`}
          </span>
          {Object.entries(p.shortfall).map(([k, n]) => (
            <span key={k} className="mt-0.5 block text-xs text-blood-bright">
              Short {n} {k.replace(/_/g, " ")}
            </span>
          ))}
        </td>
        <td className="hidden py-2.5 pr-3 align-top text-mist sm:table-cell">@{p.player_handle}</td>
        <td className="py-2.5 pr-3 align-top">
          <StandingBadge participant={p} />
        </td>
        <td className="hidden py-2.5 pr-3 align-top whitespace-nowrap text-mist sm:table-cell">{savedAt ? dates.dateTime(savedAt) : "—"}</td>
        <td className="py-1 text-right align-top">
          <Button variant="ghost" className="px-3" aria-label={`More for ${p.character_name}`} aria-expanded={open} onClick={() => setOpen(!open)}>
            ⋯
          </Button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} className="pb-4">
            <ParticipantDetail cycle={cycle} participant={p} />
          </td>
        </tr>
      )}
    </>
  );
}

/** A participant's actions, and what staff can do about them. */
function ParticipantDetail({ cycle, participant }: { cycle: CycleOut; participant: ParticipantOut }) {
  const path = { params: { path: { cycle_id: cycle.id, participant_id: participant.id } } };
  const [adjust, setAdjust] = useState({ action_kind: "general", delta: 1, reason: "" });
  const remove = useAction(() => unwrap(api.DELETE("/api/cycles/{cycle_id}/participants/{participant_id}", path)));
  const late = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/participants/{participant_id}/accept-late", path)));
  const add = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/participants/{participant_id}/adjustments", { ...path, body: adjust })));
  const running = !participant.removed && cycle.status === "open";

  return (
    <div className="rounded-md border border-ash bg-night/40 p-3">
      <p>
        {Object.entries(participant.allowance)
          .filter(([, n]) => n > 0)
          .map(([k, n]) => `${n} ${k.replace(/_/g, " ")}`)
          .join(" · ") || "No actions"}
        {participant.completion_xp_awarded != null && <span className="text-mist"> · earned {participant.completion_xp_awarded} XP for completing</span>}
      </p>
      {participant.adjustments.map((a, i) => (
        <p key={i} className="text-xs text-mist">
          {a.delta > 0 ? "+" : ""}
          {a.delta} {a.action_kind}: {a.reason}
        </p>
      ))}
      {Object.entries(participant.shortfall).map(([k, n]) => (
        <p key={k} className="text-xs text-blood-bright">
          Short {n} {k.replace(/_/g, " ")}: more was taken off than the allowance, which stops at 0.
        </p>
      ))}
      {running && (
        <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_5rem_2fr_auto]">
          <Select aria-label="Action kind" value={adjust.action_kind} onChange={(e) => setAdjust({ ...adjust, action_kind: e.target.value })}>
            {Object.keys(participant.allowance).map((k) => (
              <option key={k} value={k}>
                {k.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
          <Input aria-label="Change" type="number" value={adjust.delta} onChange={(e) => setAdjust({ ...adjust, delta: Number(e.target.value) })} />
          <Input aria-label="Reason" placeholder="Reason" value={adjust.reason} onChange={(e) => setAdjust({ ...adjust, reason: e.target.value })} />
          <Button variant="secondary" disabled={!adjust.reason} onClick={() => add.mutate(undefined)}>
            Adjust
          </Button>
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {/* For actions the player reported outside the form. */}
        <LogInfluenceButton troupeId={cycle.troupe_id} characterId={participant.character_id} cycleId={cycle.id} label={`Log influence for ${participant.character_name}`} />
        {running && !participant.late_accepted && (
          <Button variant="secondary" onClick={() => late.mutate(undefined)}>
            Accept late
          </Button>
        )}
        {running && (
          <Button variant="danger" onClick={() => remove.mutate(undefined)}>
            Remove from cycle
          </Button>
        )}
      </div>
      <ErrorText error={remove.error ?? late.error ?? add.error} />
    </div>
  );
}

/** Before reminding, who it reaches and how. */
function RemindPanel({ cycle, participants, onDone }: { cycle: CycleOut; participants: ParticipantOut[]; onDone: () => void }) {
  const toast = useToast();
  const remind = useAction(async () => {
    const sent = await unwrap(api.POST("/api/cycles/{cycle_id}/reminders", { params: { path: { cycle_id: cycle.id } } }));
    toast({ message: `Reminded ${plural(sent.players, "player", "players")}.` });
    onDone();
  });
  const waiting = notSubmitted(participants);
  const reach = plural(playersToRemind(participants), "player", "players");

  return (
    <section aria-label="Remind players?" className="mt-4 rounded-md border border-gold/60 p-3">
      <p className="font-medium">Remind {reach}?</p>
      <ul className="mt-1 text-sm">
        <li>
          {nameList(waiting.map((p) => p.character_name))} {waiting.length === 1 ? "isn't" : "aren't"} submitted.
        </li>
        <li>Each player gets a notification in Horatio, and an email too if they've chosen to.</li>
      </ul>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button disabled={remind.isPending} onClick={() => remind.mutate(undefined)}>
          Yes, remind {reach}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
      <ErrorText error={remind.error} />
    </section>
  );
}

/** Adding a character to the open cycle: one whose home troupe this is, not already taking part. */
function AddPanel({ cycle, onDone }: { cycle: CycleOut; onDone: () => void }) {
  const choices = useQuery({
    queryKey: ["participant-choices", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/participant-choices", { params: { path: { cycle_id: cycle.id } } })),
  });
  const toast = useToast();
  const [picked, setPicked] = useState("");
  const add = useAction(async () => {
    await unwrap(api.POST("/api/cycles/{cycle_id}/participants", { params: { path: { cycle_id: cycle.id } }, body: { character_id: picked } }));
    const name = choices.data?.find((c) => c.character_id === picked)?.name ?? "The character";
    toast({ message: `Added ${name} to ${cycle.name}.` });
    onDone();
  });

  return (
    <section aria-label="Add a character" className="mt-4 rounded-md border border-ash p-3">
      <p className="font-medium">Add a character</p>
      <p className="mt-1 text-xs text-mist">Active characters whose home is this troupe can take part. Their actions are worked out from the sheet as it is now.</p>
      {choices.isPending ? (
        <Loading />
      ) : choices.error ? (
        <ErrorText error={choices.error} />
      ) : choices.data.length === 0 ? (
        <p className="mt-3 text-sm">Every active character whose home is this troupe is taking part already.</p>
      ) : (
        <form
          className="mt-3 flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate(undefined);
          }}
        >
          <Field label="Character">
            <Select value={picked} onChange={(e) => setPicked(e.target.value)}>
              <option value="">Choose a character</option>
              {choices.data.map((c) => (
                <option key={c.character_id} value={c.character_id}>
                  {c.name} (@{c.player_handle}){c.removed ? ", removed earlier" : ""}
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={!picked || add.isPending}>
              Add to the cycle
            </Button>
            <Button type="button" variant="ghost" onClick={onDone}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      <ErrorText error={add.error} />
    </section>
  );
}

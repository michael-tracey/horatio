import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterFeedingOut, CycleOut, CycleFeedingOut, HumorOut } from "../../api/types";
import { EmptyState } from "../../components/EmptyState";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { staffTallyText } from "../../feeding";
import { useAction } from "../../hooks";

type Clan = CycleFeedingOut["clans"][number];
type Result = "full" | "half" | "other";
type Humor = HumorOut["key"];

const RESULTS: [Result, string][] = [
  ["full", "Full Blood next game"],
  ["half", "Half Blood next game"],
  ["other", "Other"],
];

/**
 * Feeding in a cycle, for storytellers and assistant storytellers: each clan's
 * number this cycle, each character's number, what they put towards it, and the
 * answer. The tally only suggests full or half; staff decide.
 */
export function FeedingTab({ cycle }: { cycle: CycleOut }) {
  const feeding = useQuery({
    queryKey: ["feeding", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/feeding", { params: { path: { cycle_id: cycle.id } } })),
    enabled: cycle.feeding !== false,
  });
  if (cycle.feeding === false)
    return (
      <EmptyState
        title="This troupe doesn't track feeding."
        action={
          <Link to={`/troupes/${cycle.troupe_id}/settings`} className="text-sm text-mist underline hover:text-parchment">
            Troupe settings
          </Link>
        }
      >
        Its storytellers can switch it on in Troupe settings. What was recorded before is kept.
      </EmptyState>
    );
  if (feeding.isPending) return <Loading />;
  if (feeding.error) return <ErrorText error={feeding.error} />;
  const { clans, characters } = feeding.data;
  const inPlay = clans.filter((c) => c.characters > 0 || c.amount !== 1 || c.reason);
  const others = clans.filter((c) => !inPlay.includes(c));
  const editable = cycle.status !== "complete";

  return (
    <div className="flex flex-col gap-6">
      <Card title="Feeding by clan">
        <p className="mb-3 text-sm text-mist">Feeding actions each clan needs this cycle. The next cycle starts with these numbers.</p>
        <ClanRows clans={inPlay} cycleId={cycle.id} editable={editable} />
        {others.length > 0 && (
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer text-mist">Other clans ({others.length})</summary>
            <div className="mt-2">
              <ClanRows clans={others} cycleId={cycle.id} editable={editable} />
            </div>
          </details>
        )}
      </Card>
      {cycle.status === "draft" ? (
        <Empty>Each character's feeding shows here once the cycle opens.</Empty>
      ) : characters.length === 0 ? (
        <Empty>No one taking part feeds.</Empty>
      ) : (
        characters.map((c) => <CharacterFeeding key={c.participant_id} cycle={cycle} character={c} humors={feeding.data.humors ?? []} />)
      )}
    </div>
  );
}

function ClanRows({ clans, cycleId, editable }: { clans: Clan[]; cycleId: string; editable: boolean }) {
  return (
    <ul className="flex flex-col divide-y divide-ash">
      {clans.map((c) => (
        <ClanRow key={c.clan} clan={c} cycleId={cycleId} editable={editable} />
      ))}
    </ul>
  );
}

function ClanRow({ clan, cycleId, editable }: { clan: Clan; cycleId: string; editable: boolean }) {
  const [amount, setAmount] = useState(clan.amount);
  const [reason, setReason] = useState(clan.reason);
  const save = useAction(() =>
    unwrap(api.PUT("/api/cycles/{cycle_id}/feeding/clans/{clan}", { params: { path: { cycle_id: cycleId, clan: clan.clan } }, body: { amount, reason } })),
  );
  const changed = amount !== clan.amount || reason !== clan.reason;
  return (
    <li className="grid items-center gap-2 py-2 text-sm sm:grid-cols-[10rem_5rem_1fr_auto]">
      <span>
        {clan.clan}
        {clan.characters > 0 && <span className="text-mist"> · {clan.characters} taking part</span>}
      </span>
      <Input aria-label={`Feeding for ${clan.clan}`} type="number" min={0} max={10} disabled={!editable} value={amount} onChange={(e) => setAmount(Math.max(0, Number(e.target.value) || 0))} />
      <Input aria-label={`Reason for ${clan.clan}`} placeholder="Reason" disabled={!editable} value={reason} onChange={(e) => setReason(e.target.value)} />
      {editable && (
        <Button variant="secondary" disabled={!changed || save.isPending} onClick={() => save.mutate(undefined)}>
          Save
        </Button>
      )}
      {save.error && (
        <span className="sm:col-span-4">
          <ErrorText error={save.error} />
        </span>
      )}
    </li>
  );
}

function CharacterFeeding({ cycle, character: c, humors }: { cycle: CycleOut; character: CharacterFeedingOut; humors: HumorOut[] }) {
  const path = { params: { path: { cycle_id: cycle.id, participant_id: c.participant_id } } };
  const [result, setResult] = useState<Result>(c.result ?? (c.tally.enough ? "full" : "half"));
  const [reply, setReply] = useState(c.reply);
  // With Blood Resonance: what it fed on, starting from what the player hunted for.
  const [humor, setHumor] = useState<Humor | "">(c.result ? (c.resonance ?? "") : c.answer.resonance || "");
  const [dyscrasia, setDyscrasia] = useState(c.dyscrasia ?? "");
  const chosen = humors.find((h) => h.key === humor);
  const carried = chosen?.dyscrasias.find((d) => d.name === dyscrasia);
  const [adjust, setAdjust] = useState({ delta: 1, reason: "" });
  const [table, setTable] = useState("");
  const tables = useQuery({
    queryKey: ["tables", cycle.troupe_id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/random-tables", { params: { path: { troupe_id: cycle.troupe_id } } })),
    staleTime: 60_000,
  });
  const answer = useAction((value: Result | null) =>
    unwrap(
      api.PUT("/api/cycles/{cycle_id}/participants/{participant_id}/feeding-answer", {
        ...path,
        // Without Blood Resonance, the answer leaves any Resonance given before as it was.
        body: { result: value, reply, resonance: humor || null, dyscrasia: humor ? dyscrasia : "" },
      }),
    ),
  );
  const adjustment = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/participants/{participant_id}/feeding-adjustments", { ...path, body: adjust })));
  const roll = useAction(async (name: string) => {
    const rolled = await unwrap(api.POST("/api/troupes/{troupe_id}/random-tables/{name}/roll", { params: { path: { troupe_id: cycle.troupe_id, name } } }));
    setReply((r) => (r ? `${r} ${rolled.text}` : rolled.text));
  });
  const submitted = c.submission_status === "submitted";
  const answerable = submitted && cycle.status !== "complete";

  return (
    <Card
      title={c.character_name}
      actions={
        <span className="flex flex-wrap gap-2">
          <Badge tone={submitted ? "gold" : "mist"}>{c.submission_status === "submitted" ? "Submitted" : c.submission_status === "draft" ? "Draft" : "Not started"}</Badge>
          {c.result && <Badge tone="gold">{RESULTS.find(([r]) => r === c.result)?.[1]}</Badge>}
        </span>
      }
    >
      <p className="text-sm">
        Needs <strong className="text-gold">{c.need.needed}</strong> feeding: {c.need.lines.map((l) => l.text).join(" · ")}.
        {c.herd > 0 && <span className="text-mist"> Has Herd {c.herd}.</span>}
      </p>
      <p className="mt-1 text-sm">{c.summary || <span className="text-mist">No feeding entered.</span>}</p>
      {c.received.map((r) => (
        <p key={r.character_id} className="text-sm">
          {r.character_name} gave {r.amount} Herd.{!r.submitted && <span className="text-mist"> (Not submitted, so not counted.)</span>}
        </p>
      ))}
      <p className={`mt-1 text-sm ${c.tally.enough ? "text-gold" : "text-mist"}`} aria-label={`${c.character_name}'s tally`}>
        {staffTallyText(c.tally)}
      </p>

      {c.result && c.resonance && (
        <p className="mt-2 text-sm">
          Fed on {c.resonance} blood{c.dyscrasia ? `, with the Dyscrasia ${c.dyscrasia}` : ", with no Dyscrasia"}.
        </p>
      )}
      {c.result && c.working && <p className="mt-2 text-xs text-mist">How it was worked out: {c.working}</p>}
      {answerable ? (
        <form
          className="mt-3 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            answer.mutate(result);
          }}
        >
          <div className="flex flex-wrap gap-4 text-sm" role="radiogroup" aria-label={`${c.character_name}'s feeding answer`}>
            {RESULTS.map(([value, label]) => (
              <label key={value} className="flex items-center gap-2">
                <input type="radio" name={`feeding-${c.participant_id}`} checked={result === value} onChange={() => setResult(value)} />
                {label}
              </label>
            ))}
          </div>
          {humors.length > 0 && (
            <div className="grid gap-2 sm:grid-cols-2">
              <Field label="Resonance fed on">
                <Select
                  value={humor}
                  onChange={(e) => {
                    setHumor(e.target.value as Humor | "");
                    setDyscrasia("");
                  }}
                >
                  <option value="">None given</option>
                  {humors.map((h) => (
                    <option key={h.key} value={h.key}>
                      {h.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Dyscrasia" hint={carried ? carried.summary : chosen ? "A one-time benefit for the next game, if the vessel had one (Vol. 2, pp. 296-297)." : undefined}>
                <Select value={dyscrasia} disabled={!chosen} onChange={(e) => setDyscrasia(e.target.value)}>
                  <option value="">None</option>
                  {chosen?.dyscrasias.map((d) => (
                    <option key={d.name} value={d.name}>
                      {d.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          )}
          <Field label={result === "other" ? "What happens instead" : "Flavour (optional)"}>
            <Input value={reply} onChange={(e) => setReply(e.target.value)} />
          </Field>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={answer.isPending || (result === "other" && !reply.trim())}>
              {c.result ? "Change answer" : "Answer"}
            </Button>
            {!!tables.data?.length && (
              <>
                <Select aria-label="Fill table" className="w-auto" value={table} onChange={(e) => setTable(e.target.value)}>
                  <option value="">Fill table…</option>
                  {tables.data.map((t) => (
                    <option key={t.id} value={t.name}>
                      {t.name}
                    </option>
                  ))}
                </Select>
                <Button type="button" variant="secondary" disabled={!table} onClick={() => roll.mutate(table)}>
                  Roll
                </Button>
              </>
            )}
            {c.result && (
              <Button type="button" variant="ghost" onClick={() => answer.mutate(null)}>
                Take the answer back
              </Button>
            )}
          </div>
          {c.delivered && <p className="text-xs text-mist">Already delivered: a change goes out as an update with the next delivery.</p>}
        </form>
      ) : (
        !submitted && <p className="mt-2 text-xs text-mist">Answered once the downtime is submitted.</p>
      )}
      {c.reply && !answerable && <p className="mt-2 text-sm">{c.reply}</p>}

      {c.adjustments.map((a, i) => (
        <p key={i} className="mt-1 text-xs text-mist">
          {a.delta > 0 ? "+" : ""}
          {a.delta} feeding: {a.reason}
        </p>
      ))}
      {cycle.status === "open" && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-mist">Adjust {c.character_name}'s feeding</summary>
          <div className="mt-2 grid gap-2 sm:grid-cols-[5rem_1fr_auto]">
            <Input aria-label="Change" type="number" value={adjust.delta} onChange={(e) => setAdjust({ ...adjust, delta: Number(e.target.value) })} />
            <Input aria-label="Reason" placeholder="Reason" value={adjust.reason} onChange={(e) => setAdjust({ ...adjust, reason: e.target.value })} />
            <Button variant="secondary" disabled={!adjust.reason || !adjust.delta} onClick={() => adjustment.mutate(undefined)}>
              Adjust
            </Button>
          </div>
        </details>
      )}
      <ErrorText error={answer.error ?? adjustment.error ?? roll.error} />
    </Card>
  );
}

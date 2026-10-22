import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { WorkItemOut } from "../api/types";
import { useDates } from "../dates";
import { useAction } from "../hooks";
import { entryLabel, lookupTexts } from "../influenceLookups";
import { Button, ErrorText, Field, Select, Textarea } from "./ui";

/** Another of the character's answers taking the same lookup, and what its response will say. */
export type Combined = { id: string; label: string; text: string };

/**
 * Fill a Gossip and Insider Trading or Word on the Street answer from the influence
 * log. The result goes on the last of the character's answers taking it this cycle,
 * and the others say they are combined with it; staff can change any before saving.
 */
export function LookupFill({ item, onFill }: { item: WorkItemOut; onFill: (own: string, others: Combined[]) => void }) {
  const dates = useDates();
  // Only reads: nothing to refresh afterwards.
  const fill = useMutation({
    mutationFn: async () => {
      const lookup = await unwrap(api.GET("/api/responses/{response_id}/lookup", { params: { path: { response_id: item.id } } }));
      const texts = lookupTexts(lookup, dates);
      const others = lookup.answers.filter((a) => a.response_id !== item.id).map((a) => ({ id: a.response_id, label: a.answer, text: texts[a.response_id] ?? "" }));
      onFill(texts[item.id] ?? "", others);
    },
  });
  return (
    <>
      <Button variant="secondary" onClick={() => fill.mutate(undefined)} disabled={fill.isPending}>
        Fill from the log
      </Button>
      {fill.error && <ErrorText error={fill.error} />}
    </>
  );
}

/** The character's other answers taking the lookup, filled in, saved with this response. */
export function CombinedAnswers({ others, onChange }: { others: Combined[]; onChange: (others: Combined[]) => void }) {
  if (!others.length) return null;
  return (
    <div className="flex flex-col gap-2 border-l-2 border-ash pl-3">
      <p className="text-xs text-mist">Their other answers taking this action, saved with this one:</p>
      {others.map((o) => (
        <Field key={o.id} label={o.label}>
          <Textarea
            aria-label={`Combined response: ${o.label}`}
            value={o.text}
            onChange={(e) => onChange(others.map((x) => (x.id === o.id ? { ...x, text: e.target.value } : x)))}
          />
        </Field>
      ))}
    </div>
  );
}

/**
 * A discovery block answer: staff choose the entry it hides, from either type, and
 * accept it, which adds one to the entry's blocks and says so in the response. Or
 * they refuse it with a reason, and nothing in the log changes.
 */
export function DiscoveryBlock({ item, onWrite }: { item: WorkItemOut; onWrite: (text: string) => void }) {
  const dates = useDates();
  const path = { params: { path: { response_id: item.id } } };
  const state = useQuery({
    queryKey: ["discovery-block", item.id],
    queryFn: () => unwrap(api.GET("/api/responses/{response_id}/discovery-block", path)),
  });
  const [chosen, setChosen] = useState<string | null>(null);
  const accept = useAction(async (entryId: string) => {
    const written = await unwrap(api.POST("/api/responses/{response_id}/discovery-block", { ...path, body: { entry_id: entryId } }));
    onWrite(written.body);
  });
  const undo = useAction(() => unwrap(api.DELETE("/api/responses/{response_id}/discovery-block", path)));

  if (!state.data) return state.error ? <ErrorText error={state.error} /> : null;
  const { block, picked, whose, window, choices } = state.data;
  if (block)
    return (
      <div className="flex flex-wrap items-center gap-2 text-sm text-mist">
        <span>
          Blocked <strong className="text-gold">{block.entry.short_id}</strong> (now {block.entry.blocks}).
        </span>
        <Button variant="ghost" className="px-2" onClick={() => undo.mutate(undefined)} disabled={undo.isPending}>
          Take the block off
        </Button>
        <ErrorText error={undo.error} />
      </div>
    );

  const entryId = chosen ?? picked?.id ?? "";
  const options = picked && !choices.some((c) => c.id === picked.id) ? [picked, ...choices] : choices;
  const hint =
    whose === "own" && picked
      ? `They picked their own ${picked.short_id}.`
      : whose === "own"
        ? "They say it is their own; find it below."
        : whose === "other"
          ? "Someone else's: they describe it in their answer."
          : null;
  // A short reason to choose, and what the response then says.
  const refusals = [
    ["No such action", "Refused: there is no such action to hide."],
    ["Too long ago", `Refused: that action is more than ${window.days} days old, so there is nothing left to hide.`],
  ];
  return (
    <div className="flex flex-col gap-2">
      <Field label="Entry to block" hint={[hint, `Either type, since ${dates.date(window.since)}.`].filter(Boolean).join(" ")}>
        <Select className="w-full min-w-0" value={entryId} onChange={(e) => setChosen(e.target.value)}>
          <option value="">Choose…</option>
          {options.map((c) => (
            <option key={c.id} value={c.id}>
              {entryLabel(c, dates)}
            </option>
          ))}
        </Select>
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => accept.mutate(entryId)} disabled={!entryId || accept.isPending}>
          Accept the block
        </Button>
        <Select aria-label="Refuse the block" className="w-auto" value="" onChange={(e) => e.target.value && onWrite(e.target.value)}>
          <option value="">Refuse…</option>
          {refusals.map(([reason, text]) => (
            <option key={reason} value={text}>
              {reason}
            </option>
          ))}
        </Select>
      </div>
      <ErrorText error={accept.error} />
    </div>
  );
}

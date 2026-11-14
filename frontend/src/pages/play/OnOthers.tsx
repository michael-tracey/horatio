import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { EffectMadeOut, PlayEffectOut, PlayView } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, ErrorText, Loader, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

const COUNTS = ["none", "one", "two", "three", "four"];

/** What a power used on another character did, with what was picked: "Fleshcraft: reshaped (Alien beauty)". */
function named(name: string, options: string[]): string {
  return options.length ? `${name} (${options.join(", ")})` : name;
}

/** A character a power can be used on (#823): of the user's home troupe. */
export type Picked = { id: string; name: string };

/**
 * Pick whom to use a power on (#823): a character of the home troupe, and, for a
 * power with its own options, what it does. The list needs a connection; the use
 * itself is a tap, so it waits with the rest while offline.
 */
export function OnOtherPicker({
  characterId,
  open,
  title,
  options = [],
  count = 0,
  confirm,
  online,
  onClose,
  onPick,
}: {
  characterId: string;
  open: boolean;
  title: string;
  /** The power's own options, picked each use, and how many. */
  options?: { name: string; play?: string }[];
  count?: number;
  /** The button's words: "Use · 1 Blood". */
  confirm: string;
  online: boolean;
  onClose: () => void;
  onPick: (target: Picked, options: string[]) => void;
}) {
  const [who, setWho] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const targets = useQuery({
    queryKey: ["play-targets", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/play/targets", { params: { path: { character_id: characterId } } })),
    enabled: open && online,
    staleTime: 60_000,
  });
  const target = (targets.data ?? []).find((t) => t.id === who);
  const enough = options.length === 0 || (picked.length >= 1 && picked.length <= count);
  const toggle = (name: string) =>
    setPicked((now) => (now.includes(name) ? now.filter((n) => n !== name) : count === 1 ? [name] : [...now, name].slice(-count)));
  return (
    <Dialog title={title} open={open} onClose={onClose}>
      <div className="flex flex-col gap-3 text-sm">
        <p className="text-mist">A character of your home troupe. It counts on their Play View at once: they acknowledge it, or dispute it to the storytellers.</p>
        {!online && !targets.data && <p className="text-mist">Picking someone needs a connection.</p>}
        {targets.isPending && online && <Loader compact />}
        {targets.error && <ErrorText error={targets.error} />}
        {targets.data && targets.data.length === 0 && <p className="text-mist">No one else of your home troupe to pick.</p>}
        {targets.data && targets.data.length > 0 && (
          <label className="flex flex-col gap-1">
            <span className="text-xs text-mist">On whom</span>
            <Select value={who} onChange={(e) => setWho(e.target.value)} aria-label="On whom">
              <option value="">Pick a character…</option>
              {targets.data.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                  {t.kind === "npc" ? " (NPC)" : ""}
                </option>
              ))}
            </Select>
          </label>
        )}
        {options.length > 0 && (
          <fieldset className="flex flex-col gap-1">
            <legend className="text-xs text-mist">What it does: pick {COUNTS[count] ?? count}</legend>
            {options.map((o) => (
              <label key={o.name} className="flex min-h-10 items-start gap-2">
                <input
                  type={count === 1 ? "radio" : "checkbox"}
                  name="on-other-option"
                  className="mt-0.5 h-5 w-5 accent-[var(--color-gold)]"
                  checked={picked.includes(o.name)}
                  onChange={() => toggle(o.name)}
                />
                <span>
                  {o.name}
                  {o.play && <span className="block text-xs text-mist">{o.play}</span>}
                </span>
              </label>
            ))}
          </fieldset>
        )}
        <div className="mt-2 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="danger"
            disabled={!target || !enough}
            onClick={() => {
              if (!target) return;
              onPick({ id: target.id, name: target.name }, picked);
              setWho("");
              setPicked([]);
            }}
          >
            {confirm}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function When({ effect }: { effect: Pick<PlayEffectOut, "acknowledged_at" | "disputed_at" | "dispute_note"> }) {
  if (effect.disputed_at) return <span className="block text-xs text-gold">Disputed to the storytellers: {effect.dispute_note}</span>;
  if (effect.acknowledged_at) return <span className="block text-xs text-mist">Acknowledged.</span>;
  return null;
}

/** An effect another character's power left on this one (#823), with Acknowledge and Dispute. */
function FromOther({ view, effect, online, onChange }: { view: PlayView; effect: PlayEffectOut; online: boolean; onChange: (view: PlayView) => Promise<void> }) {
  const [disputing, setDisputing] = useState(false);
  const [note, setNote] = useState("");
  const path = { params: { path: { character_id: view.character_id, effect_id: effect.id } } };
  const acknowledge = useAction(async () => onChange(await unwrap(api.POST("/api/characters/{character_id}/play/effects/{effect_id}/acknowledge", path))));
  const dispute = useAction(async () => {
    await onChange(await unwrap(api.POST("/api/characters/{character_id}/play/effects/{effect_id}/dispute", { ...path, body: { note } })));
    setDisputing(false);
  });
  const answered = effect.acknowledged_at || effect.disputed_at;
  return (
    <li className="py-2">
      <p>
        <strong className="font-semibold text-gold">{effect.source_character_name}</strong> used {named(effect.name, effect.options ?? [])} on you
        {effect.paused && <span className="text-xs text-gold"> (paused while in a form)</span>}
      </p>
      <span className="block text-xs text-mist">It counts until {effect.source_character_name} or the storytellers end it.</span>
      <When effect={effect} />
      {(acknowledge.error || dispute.error) && <ErrorText error={acknowledge.error ?? dispute.error} />}
      {!answered && !disputing && (
        <div className="mt-1 flex flex-wrap gap-2">
          <Button type="button" variant="secondary" className="min-h-10 px-3" disabled={!online || acknowledge.isPending} onClick={() => acknowledge.mutate(undefined)}>
            Acknowledge
          </Button>
          <Button type="button" variant="ghost" className="min-h-10 px-3" disabled={!online} onClick={() => setDisputing(true)}>
            Dispute
          </Button>
          {!online && <span className="self-center text-xs text-mist">Answering needs a connection.</span>}
        </div>
      )}
      {!effect.disputed_at && disputing && (
        <div className="mt-1 flex flex-col gap-2">
          <Textarea aria-label="Why, for the storytellers" placeholder="Why, for the storytellers" maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2">
            <Button type="button" variant="danger" className="min-h-10 px-3" disabled={!note.trim() || dispute.isPending || !online} onClick={() => dispute.mutate(undefined)}>
              Dispute it
            </Button>
            <Button type="button" variant="ghost" className="min-h-10 px-3" onClick={() => setDisputing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

/** An effect this character's power left on another (#823), which its player can end. */
function MadeOn({ view, effect, online, onChange }: { view: PlayView; effect: EffectMadeOut; online: boolean; onChange: (view: PlayView) => Promise<void> }) {
  const end = useAction(async () =>
    onChange(await unwrap(api.POST("/api/characters/{character_id}/play/effects-made/{effect_id}/end", { params: { path: { character_id: view.character_id, effect_id: effect.id } } }))),
  );
  return (
    <li className="flex items-start justify-between gap-3 py-2">
      <div className="min-w-0">
        <p>
          {named(effect.name, effect.options ?? [])} on <strong className="font-semibold text-gold">{effect.character_name}</strong>
        </p>
        <When effect={effect} />
        {end.error && <ErrorText error={end.error} />}
      </div>
      <Button
        type="button"
        variant="ghost"
        className="min-h-10 shrink-0 px-3"
        disabled={!online || end.isPending}
        title={online ? undefined : "Ending it needs a connection"}
        aria-label={`End ${effect.name} on ${effect.character_name}`}
        onClick={() => end.mutate(undefined)}
      >
        End
      </Button>
    </li>
  );
}

/**
 * Powers used on others (#823): what other characters' powers have left on this one,
 * acknowledged or disputed here, and what this one's powers have left on others, ended
 * here. Both come with the Play View's refresh, every 15 seconds.
 */
export function OnOthers({ view, online, onChange }: { view: PlayView; online: boolean; onChange: (view: PlayView) => Promise<void> }) {
  const from = (view.effects ?? []).filter((e) => e.source_character_name);
  const made = view.effects_made ?? [];
  if (from.length === 0 && made.length === 0) return null;
  return (
    <section className="rounded-lg border border-line bg-dusk px-3 py-2 text-sm" aria-label="Powers used on others">
      {from.length > 0 && (
        <>
          <h2 className="text-xs tracking-wide text-mist uppercase">On you, from others</h2>
          <ul className="divide-y divide-ash/60" aria-label="On you, from others">
            {from.map((e) => (
              <FromOther key={e.id} view={view} effect={e} online={online} onChange={onChange} />
            ))}
          </ul>
        </>
      )}
      {made.length > 0 && (
        <>
          <h2 className={`text-xs tracking-wide text-mist uppercase ${from.length ? "mt-2" : ""}`}>Your powers on others</h2>
          <ul className="divide-y divide-ash/60" aria-label="Your powers on others">
            {made.map((e) => (
              <MadeOn key={e.id} view={view} effect={e} online={online} onChange={onChange} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

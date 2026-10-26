import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, RetainerOut } from "../../api/types";
import { Button, ErrorText, Input, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { LOST_NOTE, LOST_WORDS, mismatch } from "./retainers";

export function useRetainers(characterId: string) {
  return useQuery({
    queryKey: ["retainers", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/retainers", { params: { path: { character_id: characterId } } })),
  });
}

type Draft = {
  id: string | null;
  name: string;
  dots: number;
  description: string;
  from_merit: string;
  lost: string;
  lost_on: string;
  npc_id: string;
};

const blank: Draft = { id: null, name: "", dots: 1, description: "", from_merit: "", lost: "", lost_on: "", npc_id: "" };

const draftOf = (r: RetainerOut): Draft => ({
  id: r.id,
  name: r.name,
  dots: r.dots,
  description: r.description,
  from_merit: r.from_merit,
  lost: r.lost ?? "",
  lost_on: r.lost_on ?? "",
  npc_id: r.npc_id ?? "",
});

/** A Retainer's links to its NPC's sheet and Play View, for staff who can see it. */
export function NpcLinks({ retainer }: { retainer: RetainerOut }) {
  if (!retainer.npc_id) return null;
  return (
    <span className="ml-1 text-xs">
      <Link className="text-gold underline" to={`/characters/${retainer.npc_id}`}>
        {retainer.npc_name ?? "NPC"}
      </Link>
      {" · "}
      <Link className="text-gold underline" to={`/play/characters/${retainer.npc_id}`}>
        Play View
      </Link>
    </span>
  );
}

/** Retainers listed read-only, as on the Play View's Sheet tab. */
export function RetainerLines({ retainers }: { retainers: RetainerOut[] }) {
  const dates = useDates();
  return (
    <ul className="mt-1 text-sm" aria-label="Retainers">
      {retainers.map((r) => (
        <li key={r.id} className="border-b border-ash/60 py-1 last:border-0">
          <span className={r.lost ? "text-mist line-through" : ""}>{r.name}</span>
          <span className="text-gold"> · {r.dots}</span>
          {r.from_merit && <span className="text-mist"> · from {r.from_merit}</span>}
          {r.lost && (
            <span className="text-blood-bright">
              {" "}
              · {LOST_WORDS[r.lost]?.toLowerCase()}
              {r.lost_on ? ` ${dates.date(r.lost_on)}` : ""}
            </span>
          )}
          <NpcLinks retainer={r} />
          {r.description && <p className="text-xs text-mist">{r.description}</p>}
        </li>
      ))}
    </ul>
  );
}

/**
 * The character's Retainers under the background on the sheet: each with its
 * dots, a warning while they and the background's rating disagree, and (for the
 * player and staff) a way to edit. Staff alone link an NPC.
 */
export function RetainersPanel({ character, merits }: { character: CharacterOut; merits: string[] }) {
  const data = useRetainers(character.id);
  const [draft, setDraft] = useState<Draft[] | null>(null);
  const dates = useDates();
  const npcs = useQuery({
    queryKey: ["npcs", character.home_troupe_id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/npcs", { params: { path: { troupe_id: character.home_troupe_id! } } })),
    enabled: !!data.data?.can_link && !!draft && !!character.home_troupe_id,
  });
  const save = useAction((rows: Draft[]) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/retainers", {
        params: { path: { character_id: character.id } },
        body: {
          retainers: rows.map((d) => ({
            id: d.id,
            name: d.name.trim(),
            dots: d.dots,
            description: d.description,
            from_merit: d.from_merit,
            lost: d.lost || null,
            lost_on: d.lost ? d.lost_on || null : null,
            npc_id: d.npc_id || null,
          })),
        },
      }),
    ),
  );
  if (!data.data) return null;
  const { retainers, rating, total, can_edit, can_link } = data.data;
  const warning = mismatch(rating, total);
  if (retainers.length === 0 && !can_edit && !warning) return null;

  const change = (i: number, patch: Partial<Draft>) => setDraft((d) => d!.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <div className="mb-1 ml-3 border-l border-ash pl-3 text-xs" aria-label="Retainers list">
      {!draft && (
        <>
          <RetainerLines retainers={retainers} />
          {retainers.some((r) => r.lost) && <p className="mt-1 text-mist">{LOST_NOTE}</p>}
        </>
      )}
      {warning && (
        <p className="mt-1 text-gold" role="status">
          {warning}
        </p>
      )}
      {!draft && can_edit && (
        <button className="mt-1 rounded border border-dashed border-mist/60 px-1.5 text-mist hover:border-gold hover:text-gold" onClick={() => setDraft(retainers.length ? retainers.map(draftOf) : [blank])}>
          {retainers.length ? "Edit Retainers" : "+ List Retainers"}
        </button>
      )}
      {draft && (
        <form
          className="mt-1 flex flex-col gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            await save.mutateAsync(draft);
            setDraft(null);
          }}
        >
          {draft.map((d, i) => (
            <fieldset key={d.id ?? `new${i}`} className="flex flex-col gap-1.5 rounded border border-ash bg-night/50 p-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <Input aria-label="Retainer name" value={d.name} onChange={(e) => change(i, { name: e.target.value })} placeholder="Name" className="min-h-7 w-48 py-0.5 text-xs" />
                <Select aria-label={`Dots for ${d.name || "Retainer"}`} value={d.dots} onChange={(e) => change(i, { dots: Number(e.target.value) })} className="min-h-7 w-20 py-0.5 text-xs">
                  {Array.from({ length: d.from_merit ? 10 : 5 }, (_, n) => (
                    <option key={n + 1} value={n + 1}>
                      {n + 1} {n ? "dots" : "dot"}
                    </option>
                  ))}
                </Select>
                <Select aria-label={`Source of ${d.name || "Retainer"}`} value={d.from_merit} onChange={(e) => change(i, { from_merit: e.target.value, dots: Math.min(d.dots, e.target.value ? 10 : 5) })} className="min-h-7 w-44 py-0.5 text-xs">
                  <option value="">The background</option>
                  {merits.map((m) => (
                    <option key={m} value={m}>
                      From {m}
                    </option>
                  ))}
                </Select>
                <button type="button" aria-label={`Remove ${d.name || "Retainer"}`} className="text-mist hover:text-blood-bright" onClick={() => setDraft((rows) => rows!.filter((_, j) => j !== i))}>
                  ×
                </button>
              </div>
              <Input aria-label={`About ${d.name || "Retainer"}`} value={d.description} onChange={(e) => change(i, { description: e.target.value })} placeholder="Who they are, what they do" className="min-h-7 py-0.5 text-xs" />
              <div className="flex flex-wrap items-center gap-1.5">
                <Select aria-label={`Status of ${d.name || "Retainer"}`} value={d.lost} onChange={(e) => change(i, { lost: e.target.value, lost_on: e.target.value ? d.lost_on || new Date().toISOString().slice(0, 10) : "" })} className="min-h-7 w-32 py-0.5 text-xs">
                  <option value="">Serving</option>
                  <option value="released">Released</option>
                  <option value="killed">Killed</option>
                </Select>
                {d.lost && <Input type="date" aria-label={`Lost on, ${d.name || "Retainer"}`} value={d.lost_on} onChange={(e) => change(i, { lost_on: e.target.value })} className="min-h-7 w-40 py-0.5 text-xs" />}
                {can_link && (
                  <Select aria-label={`NPC for ${d.name || "Retainer"}`} value={d.npc_id} onChange={(e) => change(i, { npc_id: e.target.value })} className="min-h-7 w-48 py-0.5 text-xs">
                    <option value="">No NPC linked</option>
                    {(npcs.data ?? []).map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.name}
                      </option>
                    ))}
                  </Select>
                )}
              </div>
              {d.lost && <p className="text-mist">{d.lost_on ? `${LOST_WORDS[d.lost]} ${dates.date(d.lost_on)}. ` : ""}{LOST_NOTE}</p>}
            </fieldset>
          ))}
          <div className="flex flex-wrap items-center gap-1.5">
            <Button type="button" variant="secondary" className="min-h-7 px-2 py-0.5 text-xs" onClick={() => setDraft((rows) => [...rows!, blank])}>
              + Add a Retainer
            </Button>
            <Button type="submit" className="min-h-7 px-2 py-0.5 text-xs" disabled={save.isPending || draft.some((d) => !d.name.trim())}>
              Save Retainers
            </Button>
            <Button type="button" variant="ghost" className="min-h-7 px-2 py-0.5 text-xs" onClick={() => setDraft(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      <ErrorText error={save.error} />
    </div>
  );
}

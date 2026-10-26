import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, RetainerOut } from "../../api/types";
import { Button, ErrorText, Input, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { backText, LOST_NOTE, LOST_WORDS, retainerName, retainerSource } from "./retainers";

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
  // Bought on the sheet: its name and dots are the sheet's.
  bought: boolean;
  description: string;
  from_merit: string;
  lost: string;
  lost_on: string;
  npc_id: string;
  ghoul: boolean;
  specialties: string[];
  discipline: string;
};

const blank = (merit: string): Draft => ({ id: null, name: "", dots: 1, bought: false, description: "", from_merit: merit, lost: "", lost_on: "", npc_id: "", ghoul: false, specialties: [], discipline: "" });

const draftOf = (r: RetainerOut): Draft => ({
  id: r.id,
  name: r.name,
  dots: r.dots,
  bought: r.bought,
  description: r.description,
  from_merit: r.from_merit,
  lost: r.lost ?? "",
  lost_on: r.lost_on ?? "",
  npc_id: r.npc_id ?? "",
  ghoul: r.ghoul,
  specialties: r.specialties,
  discipline: r.discipline,
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
      {retainers.map((r, i) => (
        <li key={r.id ?? `bought/${r.name}/${i}`} className="border-b border-ash/60 py-1 last:border-0">
          <span className={r.lost ? "text-mist line-through" : r.name ? "" : "text-mist"}>{retainerName(r)}</span>
          <span className="text-gold"> · {r.dots}</span>
          {r.ghoul && <span className="text-mist"> · ghoul</span>}
          {retainerSource(r) && <span className="text-mist"> · {retainerSource(r)}</span>}
          {specialtiesOf(r) && <span className="text-mist"> · {specialtiesOf(r)}</span>}
          {r.lost && (
            <span className="text-blood-bright">
              {" "}
              · {LOST_WORDS[r.lost]?.toLowerCase()}
              {r.lost_on ? ` ${dates.date(r.lost_on)}` : ""}
            </span>
          )}
          <NpcLinks retainer={r} />
          {backText(r, dates.date) && <p className="text-xs text-blood-bright">{backText(r, dates.date)}</p>}
          {r.description && <p className="text-xs text-mist">{r.description}</p>}
        </li>
      ))}
    </ul>
  );
}

/**
 * The character's Retainers under the background on the sheet. Each Retainer is
 * bought there on its own, with its name and dots; here the player and staff say
 * who each one is and whether it is lost, list those a merit gives, and (staff
 * alone) link an NPC.
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
            ghoul: d.ghoul,
            specialties: d.specialties,
            discipline: d.ghoul ? d.discipline : "",
          })),
        },
      }),
    ),
  );
  if (!data.data) return null;
  const { retainers, can_edit, can_link, skills, disciplines } = data.data;
  if (retainers.length === 0 && !can_edit) return null;
  // One held without a name has nothing kept for it until it is named on the sheet.
  const unnamed = retainers.filter((r) => r.bought && !r.name).length;

  const change = (i: number, patch: Partial<Draft>) => setDraft((d) => d!.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <div className="mb-1 ml-3 border-l border-ash pl-3 text-xs" aria-label="Retainers list">
      {!draft && (
        <>
          <RetainerLines retainers={retainers} />
          {retainers.some((r) => r.lost) && <p className="mt-1 text-mist">{LOST_NOTE}</p>}
        </>
      )}
      {!draft && can_edit && (
        <button
          className="mt-1 rounded border border-dashed border-mist/60 px-1.5 text-mist hover:border-gold hover:text-gold"
          onClick={() => setDraft(retainers.filter((r) => !r.bought || r.name).map(draftOf))}
        >
          Edit Retainers
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
          {draft.map((d, i) => {
            const label = d.name || "Retainer";
            return (
              <fieldset key={d.id ?? `new${i}`} className="flex flex-col gap-1.5 rounded border border-ash bg-night/50 p-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  {d.bought ? (
                    <span className="text-sm text-parchment">
                      {d.name} <span className="text-gold">· {d.dots}</span>
                    </span>
                  ) : (
                    <>
                      <Input aria-label="Retainer name" value={d.name} onChange={(e) => change(i, { name: e.target.value })} placeholder="Name" className="min-h-7 w-48 py-0.5 text-xs" />
                      <Select aria-label={`Dots for ${label}`} value={d.dots} onChange={(e) => change(i, { dots: Number(e.target.value) })} className="min-h-7 w-20 py-0.5 text-xs">
                        {Array.from({ length: d.from_merit ? 10 : 5 }, (_, n) => (
                          <option key={n + 1} value={n + 1}>
                            {n + 1} {n ? "dots" : "dot"}
                          </option>
                        ))}
                      </Select>
                      {d.from_merit || !d.id ? (
                        <Select aria-label={`Source of ${label}`} value={d.from_merit} onChange={(e) => change(i, { from_merit: e.target.value })} className="min-h-7 w-44 py-0.5 text-xs">
                          {merits.map((m) => (
                            <option key={m} value={m}>
                              From {m}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <span className="text-mist">{retainerSource(d)}</span>
                      )}
                      <button type="button" aria-label={`Remove ${label}`} className="text-mist hover:text-blood-bright" onClick={() => setDraft((rows) => rows!.filter((_, j) => j !== i))}>
                        ×
                      </button>
                    </>
                  )}
                </div>
                <Specialties draft={d} label={label} skills={skills} disciplines={disciplines} onChange={(patch) => change(i, patch)} />
                <Input aria-label={`About ${label}`} value={d.description} onChange={(e) => change(i, { description: e.target.value })} placeholder="Who they are, what they do" className="min-h-7 py-0.5 text-xs" />
                <div className="flex flex-wrap items-center gap-1.5">
                  <Select aria-label={`Status of ${label}`} value={d.lost} onChange={(e) => change(i, { lost: e.target.value, lost_on: e.target.value ? d.lost_on || new Date().toISOString().slice(0, 10) : "" })} className="min-h-7 w-32 py-0.5 text-xs">
                    <option value="">Serving</option>
                    <option value="released">Released</option>
                    <option value="killed">Killed</option>
                  </Select>
                  {d.lost && <Input type="date" aria-label={`Lost on, ${label}`} value={d.lost_on} onChange={(e) => change(i, { lost_on: e.target.value })} className="min-h-7 w-40 py-0.5 text-xs" />}
                  {can_link && (
                    <Select aria-label={`NPC for ${label}`} value={d.npc_id} onChange={(e) => change(i, { npc_id: e.target.value })} className="min-h-7 w-48 py-0.5 text-xs">
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
            );
          })}
          <p className="text-mist">
            Each Retainer is bought on the sheet on its own, with its own name and dots: add another under Backgrounds.
            {unnamed > 0 && " Name the one without a name on the sheet to say more about it here."}
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            {merits.length > 0 && (
              <Button type="button" variant="secondary" className="min-h-7 px-2 py-0.5 text-xs" onClick={() => setDraft((rows) => [...rows!, blank(merits[0]!)])}>
                + Add a Retainer from a merit
              </Button>
            )}
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

/** A Retainer's specialties in short: "Brawl, Stealth, Obfuscate". */
function specialtiesOf(r: Pick<RetainerOut, "specialties" | "discipline">): string {
  return [...r.specialties, ...(r.discipline ? [r.discipline] : [])].join(", ");
}

/**
 * Whether a Retainer is a ghoul, and its specialties: one a dot, each a skill
 * (+5 to its pool), or for a ghoul one discipline in-clan for the character it
 * serves, which gives it that discipline's powers up to its dots (p. 105).
 */
function Specialties({
  draft,
  label,
  skills,
  disciplines,
  onChange,
}: {
  draft: Draft;
  label: string;
  skills: string[];
  disciplines: string[];
  onChange: (patch: Partial<Draft>) => void;
}) {
  const taken = draft.specialties.length + (draft.ghoul && draft.discipline ? 1 : 0);
  const full = taken >= draft.dots;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <label className="flex items-center gap-1 text-mist">
        <input type="checkbox" aria-label={`${label} is a ghoul`} checked={draft.ghoul} onChange={(e) => onChange({ ghoul: e.target.checked, discipline: e.target.checked ? draft.discipline : "" })} />
        Ghoul
      </label>
      <span className={taken > draft.dots ? "text-blood-bright" : "text-mist"}>
        Specialties {taken} of {draft.dots}:
      </span>
      {draft.specialties.map((skill) => (
        <span key={skill} className="inline-flex items-center gap-1 rounded border border-ash px-1">
          {skill}
          <button type="button" aria-label={`Remove ${skill} from ${label}`} className="text-mist hover:text-blood-bright" onClick={() => onChange({ specialties: draft.specialties.filter((x) => x !== skill) })}>
            ×
          </button>
        </span>
      ))}
      {!full && (
        <Select
          aria-label={`Add a specialty for ${label}`}
          value=""
          onChange={(e) => e.target.value && onChange({ specialties: [...draft.specialties, e.target.value] })}
          className="min-h-7 w-36 py-0.5 text-xs"
        >
          <option value="">+ A skill…</option>
          {skills
            .filter((x) => !draft.specialties.includes(x))
            .map((x) => (
              <option key={x}>{x}</option>
            ))}
        </Select>
      )}
      {draft.ghoul && (
        <Select aria-label={`Discipline for ${label}`} value={draft.discipline} onChange={(e) => onChange({ discipline: e.target.value })} className="min-h-7 w-40 py-0.5 text-xs" disabled={full && !draft.discipline}>
          <option value="">No discipline</option>
          {disciplines.map((x) => (
            <option key={x}>{x}</option>
          ))}
        </Select>
      )}
    </div>
  );
}

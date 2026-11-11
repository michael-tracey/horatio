import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, RetainerOut, RetainersOut } from "../../api/types";
import { DateInput } from "../../components/DateInput";
import { Button, ErrorText, Input, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { pageLabel } from "../../components/TraitInfo";
import { backText, growthText, LOST_NOTE, LOST_WORDS, neglectText, retainerName, retainerSource } from "./retainers";

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
  // Given by its merit's rules: its dots, kind and being a ghoul are the merit's.
  given: boolean;
  kind: string;
  given_disciplines: string[];
};

const blank = (merit: string): Draft => ({
  id: null,
  name: "",
  dots: 1,
  bought: false,
  description: "",
  from_merit: merit,
  lost: "",
  lost_on: "",
  npc_id: "",
  ghoul: false,
  specialties: [],
  discipline: "",
  given: false,
  kind: "",
  given_disciplines: [],
});

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
  given: r.given ?? false,
  kind: r.kind ?? "",
  given_disciplines: r.given_disciplines ?? [],
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
  return (
    <ul className="mt-1 text-sm" aria-label="Retainers">
      {retainers.map((r, i) => (
        <li key={r.id ?? `bought/${r.name}/${i}`} className="border-b border-ash/60 py-1 last:border-0">
          <RetainerLine retainer={r} />
        </li>
      ))}
    </ul>
  );
}

/** One Retainer in a list; staff can clear a neglect with `onClear`. */
function RetainerLine({ retainer: r, onClear }: { retainer: RetainerOut; onClear?: (retainerId: string) => void }) {
  const dates = useDates();
  return (
    <>
      <span className={r.lost ? "text-mist line-through" : r.name ? "" : "text-mist"}>{retainerName(r)}</span>
      <span className="text-gold"> · {r.dots}</span>
      {r.given && r.name && r.kind && <span className="text-mist"> · {r.kind.toLowerCase()}</span>}
      {r.ghoul && !(r.given && /ghoul/i.test(r.kind ?? "")) && <span className="text-mist"> · ghoul</span>}
      {retainerSource(r) && <span className="text-mist"> · {retainerSource(r)}</span>}
      {specialtiesOf(r) && <span className="text-mist"> · {specialtiesOf(r)}</span>}
      {r.lost && (
        <span className="text-blood-bright">
          {" "}
          · {LOST_WORDS[r.lost]?.toLowerCase()}
          {r.lost_on ? ` ${dates.date(r.lost_on)}` : ""}
        </span>
      )}
      {r.upkeep && <span className="text-mist"> · upkeep {r.upkeep}</span>}
      <NpcLinks retainer={r} />
      {backText(r, dates.date) && <p className="text-xs text-blood-bright">{backText(r, dates.date)}</p>}
      {neglectText(r, dates.date) && (
        <p className="text-xs text-blood-bright">
          {neglectText(r, dates.date)}
          {onClear && r.id && (
            <button type="button" className="ml-2 text-gold underline" aria-label={`Clear the neglect of ${retainerName(r)}`} onClick={() => onClear(r.id!)}>
              Clear
            </button>
          )}
        </p>
      )}
      {growthText(r) && <p className="text-xs text-mist">{growthText(r)}</p>}
      {r.description && <p className="text-xs text-mist">{r.description}</p>}
      {r.given && r.note && (
        <p className="text-xs text-mist">
          {r.note}
          {pageLabel(r.page) && ` ${pageLabel(r.page)}.`}
        </p>
      )}
    </>
  );
}

/**
 * The Retainers under one row of the sheet: the one bought there, or those its merit
 * gives. Each is edited on its own, by the player and staff: who it is and whether it
 * is lost, and (staff alone) its NPC. Under a merit with `merit`, one more can be added
 * by hand; another Retainer of the background is bought on the sheet, not here.
 */
export function RetainerSection({ character, retainers, label, merit }: { character: CharacterOut; retainers: RetainerOut[]; label: string; merit?: string }) {
  const data = useRetainers(character.id);
  // Which one is being edited, by its place in the list; "new" for one added from the merit.
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const clear = useAction((retainerId: string) =>
    unwrap(api.DELETE("/api/characters/{character_id}/retainers/{retainer_id}/neglected", { params: { path: { character_id: character.id, retainer_id: retainerId } } })),
  );
  if (!data.data) return null;
  const { can_edit, can_link } = data.data;
  if (retainers.length === 0 && !(can_edit && merit)) return null;
  // One held without a name has nothing kept for it until it is named on the sheet.
  const unnamed = retainers.some((r) => r.bought && !r.name);
  const editor = (draft: Draft) => <RetainerEditor character={character} draft={draft} onDone={() => setEditing(null)} />;
  return (
    <div className="mb-1 ml-3 border-l border-ash pl-3 text-xs" aria-label={label}>
      <ul className="mt-1 text-sm" aria-label="Retainers">
        {retainers.map((r, i) => (
          <li key={r.id ?? `bought/${r.name}/${i}`} className="border-b border-ash/60 py-1 last:border-0">
            {editing === i ? (
              editor(draftOf(r))
            ) : (
              <>
                <RetainerLine retainer={r} onClear={can_link ? (id) => clear.mutate(id) : undefined} />
                {can_edit && editing === null && (r.name || !r.bought) && (
                  <button
                    type="button"
                    aria-label={`Edit ${retainerName(r)}`}
                    className="ml-2 rounded border border-dashed border-mist/60 px-1.5 text-xs text-mist hover:border-gold hover:text-gold"
                    onClick={() => setEditing(i)}
                  >
                    Edit
                  </button>
                )}
              </>
            )}
          </li>
        ))}
        {editing === "new" && merit && <li className="py-1">{editor(blank(merit))}</li>}
      </ul>
      <ErrorText error={clear.error} />
      {retainers.some((r) => r.lost) && editing === null && <p className="mt-1 text-mist">{LOST_NOTE}</p>}
      {unnamed && can_edit && <p className="mt-1 text-mist">Name it on the sheet to say more about it here.</p>}
      {merit && can_edit && editing === null && (
        <button type="button" className="mt-1 rounded border border-dashed border-mist/60 px-1.5 text-mist hover:border-gold hover:text-gold" onClick={() => setEditing("new")}>
          + Add a Retainer from {merit}
        </button>
      )}
    </div>
  );
}

/** Under the last Retainers row: what a Retainer's dots are, and (with `onBuy`) buying another. */
export function BuyAnotherRetainer({ onBuy }: { onBuy?: () => void }) {
  return (
    <p className="mb-1 ml-3 pl-3 text-xs text-mist">
      Each Retainer is bought on its own; its dots are how capable it is.
      {onBuy && (
        <button type="button" className="ml-2 rounded border border-dashed border-mist/60 px-1.5 hover:border-gold hover:text-gold" onClick={onBuy}>
          Buy another Retainer
        </button>
      )}
    </p>
  );
}

/** One Retainer's editor: saved on its own, leaving the character's others as they are. */
function RetainerEditor({ character, draft: first, onDone }: { character: CharacterOut; draft: Draft; onDone: () => void }) {
  const data = useRetainers(character.id);
  const [d, setDraft] = useState(first);
  const dates = useDates();
  const can_link = !!data.data?.can_link;
  const npcs = useQuery({
    queryKey: ["npcs", character.home_troupe_id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/npcs", { params: { path: { troupe_id: character.home_troupe_id! } } })),
    enabled: can_link && !!character.home_troupe_id,
  });
  const client = useQueryClient();
  // The list as saved comes back at once, so the others under the rows show it.
  const done = (saved: RetainersOut) => {
    client.setQueryData(["retainers", character.id], saved);
    onDone();
  };
  const save = useAction(() =>
    unwrap(
      api.PATCH("/api/characters/{character_id}/retainers", {
        params: { path: { character_id: character.id } },
        body: {
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
          discipline: d.ghoul || d.given_disciplines.length ? d.discipline : "",
        },
      }),
    ),
  );
  const remove = useAction((retainerId: string) =>
    unwrap(api.DELETE("/api/characters/{character_id}/retainers/{retainer_id}", { params: { path: { character_id: character.id, retainer_id: retainerId } } })),
  );
  const change = (patch: Partial<Draft>) => setDraft((was) => ({ ...was, ...patch }));
  const label = d.name || "Retainer";
  // Its name and dots are the sheet's for one bought, and the merit's for one its rules give.
  const byHand = !d.bought && !d.given;
  return (
    <form
      className="flex flex-col gap-1.5 rounded border border-ash bg-night/50 p-2 text-xs"
      aria-label={`Editing ${label}`}
      onSubmit={async (e) => {
        e.preventDefault();
        done(await save.mutateAsync(undefined));
      }}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        {d.bought ? (
          <span className="text-sm text-parchment">
            {d.name} <span className="text-gold">· {d.dots}</span>
          </span>
        ) : (
          <>
            <Input aria-label="Retainer name" value={d.name} onChange={(e) => change({ name: e.target.value })} placeholder={d.given ? `Name the ${d.kind.toLowerCase()}` : "Name"} className="min-h-7 w-48 py-0.5 text-xs" />
            {d.given ? (
              <span className="text-gold">· {d.dots}</span>
            ) : (
              <Select aria-label={`Dots for ${label}`} value={d.dots} onChange={(e) => change({ dots: Number(e.target.value) })} className="min-h-7 w-20 py-0.5 text-xs">
                {Array.from({ length: d.from_merit ? 10 : 5 }, (_, n) => (
                  <option key={n + 1} value={n + 1}>
                    {n + 1} {n ? "dots" : "dot"}
                  </option>
                ))}
              </Select>
            )}
            <span className="text-mist">{d.given ? `${d.kind.toLowerCase()} from ${d.from_merit}` : retainerSource(d)}</span>
          </>
        )}
      </div>
      <Specialties draft={d} label={label} skills={data.data?.skills ?? []} disciplines={data.data?.disciplines ?? []} onChange={change} />
      <Input aria-label={`About ${label}`} value={d.description} onChange={(e) => change({ description: e.target.value })} placeholder="Who they are, what they do" className="min-h-7 py-0.5 text-xs" />
      <div className="flex flex-wrap items-center gap-1.5">
        <Select aria-label={`Status of ${label}`} value={d.lost} onChange={(e) => change({ lost: e.target.value, lost_on: e.target.value ? d.lost_on || new Date().toISOString().slice(0, 10) : "" })} className="min-h-7 w-32 py-0.5 text-xs">
          <option value="">Serving</option>
          <option value="released">Released</option>
          <option value="killed">Killed</option>
        </Select>
        {d.lost && <DateInput aria-label={`Lost on, ${label}`} value={d.lost_on} onChange={(e) => change({ lost_on: e.target.value })} className="min-h-7 w-40 py-0.5 text-xs" />}
        {can_link && (
          <Select aria-label={`NPC for ${label}`} value={d.npc_id} onChange={(e) => change({ npc_id: e.target.value })} className="min-h-7 w-48 py-0.5 text-xs">
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
      <div className="flex flex-wrap items-center gap-1.5">
        <Button type="submit" className="min-h-7 px-2 py-0.5 text-xs" disabled={save.isPending || !d.name.trim()}>
          Save Retainer
        </Button>
        <Button type="button" variant="ghost" className="min-h-7 px-2 py-0.5 text-xs" onClick={onDone}>
          Cancel
        </Button>
        {byHand && d.id && (
          <Button
            type="button"
            variant="ghost"
            className="ml-auto min-h-7 px-2 py-0.5 text-xs"
            aria-label={`Remove ${label}`}
            disabled={remove.isPending}
            onClick={async () => {
              if (window.confirm(`Remove ${label} from ${character.name}'s Retainers?`)) done(await remove.mutateAsync(d.id!));
            }}
          >
            Remove
          </Button>
        )}
      </div>
      <ErrorText error={save.error ?? remove.error} />
    </form>
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
  // A Retainer a merit gives can have the discipline specialty its merit says (Walking Dead's).
  const choices = draft.given_disciplines.length ? draft.given_disciplines : disciplines;
  const withDiscipline = draft.ghoul || draft.given_disciplines.length > 0;
  const taken = draft.specialties.length + (withDiscipline && draft.discipline ? 1 : 0);
  const full = taken >= draft.dots;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <label className="flex items-center gap-1 text-mist">
        <input
          type="checkbox"
          aria-label={`${label} is a ghoul`}
          checked={draft.ghoul}
          disabled={draft.given}
          onChange={(e) => onChange({ ghoul: e.target.checked, discipline: e.target.checked ? draft.discipline : "" })}
        />
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
      {withDiscipline && (
        <Select aria-label={`Discipline for ${label}`} value={draft.discipline} onChange={(e) => onChange({ discipline: e.target.value })} className="min-h-7 w-40 py-0.5 text-xs" disabled={full && !draft.discipline}>
          <option value="">No discipline</option>
          {choices.map((x) => (
            <option key={x}>{x}</option>
          ))}
        </Select>
      )}
    </div>
  );
}

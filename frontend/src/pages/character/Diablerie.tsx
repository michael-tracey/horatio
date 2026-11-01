import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, DiablerieEffectsOut, DiablerieEffectsPlanOut, DiablerieListOut } from "../../api/types";
import { DateInput } from "../../components/DateInput";
import { Button, ErrorText, Field, Input, Notice, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { dots, generationText } from "../../generation";

/** What staff change from the form's fill-in: Humanity lowered, and Beast traits for the next game. */
export type DiablerieAdjust = { humanity?: number; beast?: number };

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** What a diablerie does to the sheet, line by line: Generation, techniques, the flaw. */
export function DiablerieEffects({ effects, done = false }: { effects: DiablerieEffectsOut; done?: boolean }) {
  const lost = effects.techniques.reduce((n, t) => n + t.refund, 0);
  return (
    <ul className="flex flex-col gap-1 text-sm">
      <li>
        {generationText(effects.from_generation)} → {dots(effects.to_generation)}, as a free dot. Earlier buys keep what they cost.
      </li>
      {effects.techniques.map((t) => (
        <li key={`${t.name}/${t.detail}`}>
          {done ? "Lost" : "Loses"} {t.name}
          {t.detail && `: ${t.detail}`}
          {t.refund > 0 ? `, with ${t.refund} XP back.` : "."}
        </li>
      ))}
      {effects.techniques.length > 1 && lost > 0 && <li className="text-mist">{lost} XP back in all, a line for each.</li>}
      {effects.caitiff && <li>A Caitiff may have more than 2 dots of Generation this way.</li>}
      {effects.humanity_lowered > 0 && (
        <li>
          {effects.morality} {done ? "went" : "goes"} down {effects.humanity_lowered}, with no XP back.
        </li>
      )}
      {effects.beast_traits > 0 && (
        <li>
          {plural(effects.beast_traits, "Beast trait", "Beast traits")} {done ? "added to" : "go on"} the next game on the Play View.
        </li>
      )}
      {effects.flaw && <FlawLine effects={effects} />}
    </ul>
  );
}

/** What the troupe's setting does to a Lesser Generation or Thin Blooded flaw the character holds. */
function FlawLine({ effects }: { effects: DiablerieEffectsOut }) {
  const flaw = effects.flaw!;
  if (flaw.setting === "leave")
    return (
      <li className="rounded-md border border-blood/60 bg-blood/10 px-2 py-1 text-blood-bright">
        {flaw.name} stays on the sheet: this troupe leaves the flaw when a holder commits diablerie. Staff can change that in the troupe's house rules.
      </li>
    );
  if (flaw.setting === "keep_xp")
    return (
      <li>
        {flaw.name} comes off the sheet, and the {flaw.gave} XP it gave stays.
      </li>
    );
  return (
    <li>
      {flaw.name} comes off the sheet
      {flaw.gave === 0
        ? ", and it gave no XP to take back."
        : flaw.taken < flaw.gave
          ? `, and ${flaw.taken} of the ${flaw.gave} XP it gave is taken back: that is all the character has unspent.`
          : `, and the ${flaw.gave} XP it gave is taken back.`}
    </li>
  );
}

/** The fill-in staff can change before confirming. */
export function DiablerieAdjustFields({
  plan,
  adjust,
  onChange,
}: {
  plan: DiablerieEffectsPlanOut;
  adjust: DiablerieAdjust;
  onChange: (adjust: DiablerieAdjust) => void;
}) {
  const humanity = adjust.humanity ?? plan.humanity_lowered;
  const beast = adjust.beast ?? plan.beast_traits;
  return (
    <div className="flex flex-wrap items-end gap-3">
      <Field label={`${plan.morality ?? "Humanity"} lowered by`} hint={plan.on_path ? "A Path takes Beast traits instead." : "Free, with no XP back."}>
        <Input
          type="number"
          min={0}
          max={plan.morality_rating}
          value={humanity}
          onChange={(e) => onChange({ ...adjust, humanity: Math.max(0, Number(e.target.value) || 0) })}
          className="w-24"
        />
      </Field>
      <Field label="Beast traits at the next game" hint="Added on the Play View.">
        <Input type="number" min={0} max={5} value={beast} onChange={(e) => onChange({ ...adjust, beast: Math.max(0, Number(e.target.value) || 0) })} className="w-24" />
      </Field>
    </div>
  );
}

/** A plan, filled in with what staff changed, the way the sheet will read it. */
export function adjusted(plan: DiablerieEffectsPlanOut, adjust: DiablerieAdjust): DiablerieEffectsPlanOut {
  return { ...plan, humanity_lowered: adjust.humanity ?? plan.humanity_lowered, beast_traits: adjust.beast ?? plan.beast_traits };
}

/** The diablerie on a character (MET: VTM p. 306): what is recorded, whether the viewer can record or ask, and any request waiting. */
export function useDiablerie(character: CharacterOut) {
  return useQuery({
    queryKey: ["diablerie", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/diablerie", { params: { path: { character_id: character.id } } })),
    // Only a PC can have one recorded, or asked for.
    enabled: character.kind === "pc",
  });
}

/** What the ⋯ menu offers: staff record a diablerie, the player asks staff to. */
export function diablerieAction(list: DiablerieListOut | undefined): string | null {
  if (list?.can_record) return "Record diablerie…";
  if (list?.can_ask) return "Ask staff: I committed diablerie…";
  return null;
}

/** On the sheet, only while a diablerie the player asked for waits on the storytellers; the player can withdraw it. */
export function DiablerieWaiting({ character, mine }: { character: CharacterOut; mine: boolean }) {
  const dates = useDates();
  const list = useDiablerie(character);
  const withdraw = useAction(() => unwrap(api.DELETE("/api/characters/{character_id}/diablerie/ask", { params: { path: { character_id: character.id } } })));
  const d = list.data;
  if (!d?.waiting) return null;
  const on = d.waiting_on ? ` on ${dates.day(d.waiting_on)}` : "";
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-3">
        <Notice>
          {mine ? `Diablerie${on} waits for the storytellers.` : `${character.name}'s player says it committed diablerie${on}. It waits for the storytellers.`}
        </Notice>
        {mine && (
          <Button variant="ghost" className="min-h-8 px-2" onClick={() => withdraw.mutate(undefined)} disabled={withdraw.isPending}>
            Withdraw
          </Button>
        )}
      </div>
      <ErrorText error={withdraw.error} />
    </div>
  );
}

/** Behind the ⋯ menu: the diablerie already recorded, then the form to record one (staff) or ask for one (the player). */
export function DiablerieForm({ character, list, onClose }: { character: CharacterOut; list: DiablerieListOut; onClose: () => void }) {
  return (
    <div className="flex flex-col gap-4">
      {list.entries.length > 0 && <DiablerieEntries list={list} />}
      {list.can_record ? <RecordForm character={character} onClose={onClose} /> : list.can_ask && <AskForm character={character} onClose={onClose} />}
    </div>
  );
}

/** Each diablerie recorded: its date, note, what it did, and for staff who was diablerized. */
function DiablerieEntries({ list }: { list: DiablerieListOut }) {
  const dates = useDates();
  return (
    <ul aria-label="Diablerie" className="flex flex-col gap-3 rounded-md border border-ash p-2 text-sm">
      {list.entries.map((e) => (
        <li key={e.id}>
          <p className="text-parchment">Diablerie: {dates.day(e.committed_on)}</p>
          {e.note && <p className="text-xs text-mist">{e.note}</p>}
          {e.victim && <p className="text-xs text-mist">Diablerized (staff only): {e.victim}</p>}
          {e.effects && (
            <div className="mt-1 text-xs text-mist">
              <DiablerieEffects effects={e.effects} done />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function today(dates: ReturnType<typeof useDates>) {
  return dates.toInput(new Date()).slice(0, 10);
}

/** Staff record a diablerie: the date, who was diablerized, a note, and what it does to the sheet. */
function RecordForm({ character, onClose }: { character: CharacterOut; onClose: () => void }) {
  const dates = useDates();
  const [when, setWhen] = useState(today(dates));
  const [victim, setVictim] = useState("");
  const [note, setNote] = useState("");
  const [adjust, setAdjust] = useState<DiablerieAdjust>({});
  const plan = useQuery({
    queryKey: ["diablerie-plan", character.id, adjust.humanity, adjust.beast],
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_id}/diablerie/plan", {
          params: { path: { character_id: character.id }, query: { humanity_lowered: adjust.humanity, beast_traits: adjust.beast } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
  const record = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/diablerie", {
        params: { path: { character_id: character.id } },
        body: {
          committed_on: when,
          victim,
          note,
          humanity_lowered: adjust.humanity ?? plan.data?.humanity_lowered,
          beast_traits: adjust.beast ?? plan.data?.beast_traits,
        },
      }),
    );
    onClose();
  });
  const p = plan.data;
  return (
    <form
      aria-label="Record diablerie"
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        record.mutate(undefined);
      }}
    >
      <p className="text-xs text-mist">
        Record that {character.name} committed diablerie. The player is told. Generation goes up one, free; the rest follows p. 306.
      </p>
      <div className="flex flex-wrap gap-3">
        <Field label="Date" hint="The night it happened.">
          <DateInput required value={when} onChange={(e) => setWhen(e.target.value)} className="w-44" />
        </Field>
        <div className="min-w-48 flex-1">
          <Field label="Who was diablerized" hint="Optional. Only staff see it.">
            <Input maxLength={200} value={victim} onChange={(e) => setVictim(e.target.value)} />
          </Field>
        </div>
      </div>
      <Field label="Note">
        <Textarea rows={2} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {p && !p.refused && (
        <>
          <DiablerieAdjustFields plan={p} adjust={adjust} onChange={setAdjust} />
          <div className="rounded-md border border-ash p-2">
            <p className="mb-1 text-xs text-mist">Confirming will:</p>
            <DiablerieEffects effects={adjusted(p, adjust)} />
          </div>
        </>
      )}
      {p?.refused && <ErrorText error={new Error(p.refused)} />}
      <ErrorText error={plan.error ?? record.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={record.isPending || !when || !p || !!p.refused}>
          Record diablerie
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** The player says their character committed diablerie: the storytellers decide. */
function AskForm({ character, onClose }: { character: CharacterOut; onClose: () => void }) {
  const dates = useDates();
  const [when, setWhen] = useState(today(dates));
  const [note, setNote] = useState("");
  const ask = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/diablerie/ask", { params: { path: { character_id: character.id } }, body: { committed_on: when, note } }),
    );
    onClose();
  });
  return (
    <form
      aria-label="Ask staff about diablerie"
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        ask.mutate(undefined);
      }}
    >
      <p className="text-xs text-mist">
        Tell the home troupe's storytellers {character.name} committed diablerie. Nothing changes on the sheet until they approve it; then Generation goes up one, free, and
        the rest follows p. 306.
      </p>
      <Field label="Date" hint="The night it happened.">
        <DateInput required value={when} onChange={(e) => setWhen(e.target.value)} className="w-44" />
      </Field>
      <Field label="Note">
        <Textarea rows={2} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <ErrorText error={ask.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={ask.isPending || !when}>
          Ask staff
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

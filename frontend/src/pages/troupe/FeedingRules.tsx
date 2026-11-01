import { useState } from "react";
import type { CharacterFeedingOut, CycleFeedingOut, CycleOut, FeedingCardOut, HumorOut, TerritoryUseOut } from "../../api/types";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText, Field, Input, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { MASQUERADE, MOOD, suggestedCards, throwChallenges, type Masquerade, type Mood } from "./feedingRules";

type Rack = NonNullable<CycleFeedingOut["rack"]>;
type Humor = HumorOut["key"];

const SOURCES: [FeedingCardOut["source"], string][] = [
  ["rack", "On the Rack"],
  ["territory", "In feeding territories"],
  ["herd", "Dealt for Herd"],
  ["hunt", "Dealt for hunting outside the Rack"],
];

/** "91 · sanguine · Manic High (a jogger)": a Feeding Card in a line. */
export function cardLine(card: FeedingCardOut): string {
  const text = `${card.number} · ${card.resonance} · ${card.dyscrasia || "no Dyscrasia"}`;
  return card.descriptor ? `${text} (${card.descriptor})` : text;
}

/**
 * The cycle's Rack, for staff: lay out cards at random, as many as the book suggests
 * for those taking part and the mood of the domain or as many as staff choose, then
 * change any card. Each territory gets its own cards, and each character with Herd a
 * card for each dot, the first time.
 */
export function RackCard({ cycle, rack, humors }: { cycle: CycleOut; rack: Rack; humors: HumorOut[] }) {
  const [masquerade, setMasquerade] = useState<Masquerade>("none");
  const [mood, setMood] = useState<Mood>("none");
  const [count, setCount] = useState<number | null>(null);
  const [share, setShare] = useState(50);
  const suggested = suggestedCards(rack.players, masquerade, mood);
  const laying = count ?? suggested;
  const deal = useAction(async () => {
    await unwrap(api.POST("/api/cycles/{cycle_id}/rack", { params: { path: { cycle_id: cycle.id } }, body: { count: laying, share } }));
    setCount(null);
  });
  const editable = cycle.status !== "complete";
  const onRack = rack.cards.filter((c) => c.source === "rack");
  const left = onRack.filter((c) => !c.taken_by).length;

  return (
    <Card title="The Rack">
      <p className="mb-3 text-sm text-mist">
        Each character takes one vessel, first come, first served (Vol. 2, pp. 298-303). {onRack.length ? `${left} of ${onRack.length} left on the Rack.` : "Nothing is laid out yet."}
      </p>
      {editable && (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            deal.mutate(undefined);
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Masquerade">
              <Select value={masquerade} onChange={(e) => setMasquerade(e.target.value as Masquerade)}>
                {MASQUERADE.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Mood of the domain">
              <Select value={mood} onChange={(e) => setMood(e.target.value as Mood)}>
                {MOOD.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Cards to lay out" hint={`The book suggests ${suggested} for ${rack.players} taking part (p. 306).`}>
              <Input type="number" min={0} max={200} value={laying} onChange={(e) => setCount(Math.max(0, Number(e.target.value) || 0))} />
            </Field>
            <Field label="Cards with a Dyscrasia, in 100" hint="Not every vessel need have one (p. 300).">
              <Input type="number" min={0} max={100} value={share} onChange={(e) => setShare(Math.min(100, Math.max(0, Number(e.target.value) || 0)))} />
            </Field>
          </div>
          <Button type="submit" className="self-start" disabled={deal.isPending}>
            {onRack.length ? `Lay out ${laying} more` : `Lay out ${laying} cards`}
          </Button>
          <p className="text-xs text-mist">Dealt at random; change any card below. Territories get their own cards and characters with Herd one per dot, the first time.</p>
          <ErrorText error={deal.error} />
        </form>
      )}
      {SOURCES.map(([source, label]) => {
        const cards = rack.cards.filter((c) => c.source === source);
        if (!cards.length) return null;
        return (
          <details key={source} className="mt-3 text-sm">
            <summary className="cursor-pointer text-mist">
              {label} ({cards.length}, {cards.filter((c) => c.taken_by).length} taken)
            </summary>
            <ul className="mt-2 flex flex-col divide-y divide-ash">
              {cards.map((c) => (
                <CardRow key={c.id} cycleId={cycle.id} card={c} humors={humors} editable={editable} />
              ))}
            </ul>
          </details>
        );
      })}
    </Card>
  );
}

function CardRow({ cycleId, card, humors, editable }: { cycleId: string; card: FeedingCardOut; humors: HumorOut[]; editable: boolean }) {
  const [humor, setHumor] = useState<Humor>(card.resonance);
  const [dyscrasia, setDyscrasia] = useState(card.dyscrasia);
  const [descriptor, setDescriptor] = useState(card.descriptor);
  const path = { params: { path: { cycle_id: cycleId, card_id: card.id } } };
  const save = useAction(() => unwrap(api.PUT("/api/cycles/{cycle_id}/rack/{card_id}", { ...path, body: { resonance: humor, dyscrasia, descriptor } })));
  const remove = useAction(() => unwrap(api.DELETE("/api/cycles/{cycle_id}/rack/{card_id}", path)));
  const changed = humor !== card.resonance || dyscrasia !== card.dyscrasia || descriptor !== card.descriptor;
  const who = [card.territory_name, card.dealt_to && `for ${card.dealt_to}`, card.taken_by && `taken by ${card.taken_by}`].filter(Boolean).join(" · ");
  return (
    <li className="grid items-center gap-2 py-2 sm:grid-cols-[3rem_8rem_10rem_1fr_auto]" aria-label={`Feeding Card ${card.number}`}>
      <span className="text-gold">{card.number}</span>
      <Select
        aria-label="Resonance"
        disabled={!editable}
        value={humor}
        onChange={(e) => {
          setHumor(e.target.value as Humor);
          setDyscrasia("");
        }}
      >
        {humors.map((h) => (
          <option key={h.key} value={h.key}>
            {h.name}
          </option>
        ))}
      </Select>
      <Select aria-label="Dyscrasia" disabled={!editable} value={dyscrasia} onChange={(e) => setDyscrasia(e.target.value)}>
        <option value="">No Dyscrasia</option>
        {humors
          .find((h) => h.key === humor)
          ?.dyscrasias.map((d) => (
            <option key={d.name} value={d.name}>
              {d.name}
            </option>
          ))}
      </Select>
      <Input aria-label="Who the vessel is" placeholder="Who the vessel is" disabled={!editable} value={descriptor} onChange={(e) => setDescriptor(e.target.value)} />
      {editable && (
        <span className="flex gap-1">
          {changed && (
            <Button variant="secondary" disabled={save.isPending} onClick={() => save.mutate(undefined)}>
              Save
            </Button>
          )}
          {!card.taken_by && (
            <Button variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
              Remove
            </Button>
          )}
        </span>
      )}
      {who && <span className="text-xs text-mist sm:col-span-5">{who}</span>}
      <span className="sm:col-span-5">
        <ErrorText error={save.error ?? remove.error} />
      </span>
    </li>
  );
}

/** The troupe's feeding territories this cycle: who feeds in each, against the vessels it holds, and who patrols it. */
export function TerritoriesThisCycle({ territories, rack }: { territories: TerritoryUseOut[]; rack: boolean }) {
  if (!territories.length) return null;
  return (
    <Card title="Feeding territories">
      <ul className="flex flex-col divide-y divide-ash text-sm">
        {territories.map((t) => {
          const crowded = !rack && (t.feeding?.length ?? 0) > t.vessels;
          return (
            <li key={t.id} className="py-2">
              <p>
                <strong>{t.name}</strong>
                <span className="text-mist">
                  {" "}
                  · {t.size_name}, {t.vessels} vessels · {t.holders.length ? `held by ${t.holders.join(", ")}` : "unassigned"}
                  {t.held_by && ` (${t.held_by})`}
                </span>
              </p>
              {!rack && (
                <p className={crowded ? "text-blood-bright" : ""}>
                  {t.feeding?.length ? `Feeding here: ${t.feeding.join(", ")}` : "No one feeds here this cycle."}
                  {crowded && `, more than its ${t.vessels} vessels`}
                </p>
              )}
              {!!t.patrols?.length && <p className="text-mist">Patrolled by {t.patrols.map((p) => `${p.character_name} (${p.actions})`).join(", ")}</p>}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/** Poaching: the patrols where the character poached, and which caught it. Horatio can throw the simple challenges; staff can change any. */
export function PoachingControls({ character: c, caught, onChange }: { character: CharacterFeedingOut; caught: string[]; onChange: (caught: string[]) => void }) {
  if (!c.poaching) return null;
  const patrols = c.patrols ?? [];
  return (
    <fieldset className="flex flex-col gap-1 border-t border-ash pt-2 text-sm">
      <legend className="sr-only">Poaching in {c.poaching}</legend>
      <p>
        Poaching in <strong>{c.poaching}</strong>.{" "}
        <span className="text-mist">{patrols.length ? "A simple challenge for each action spent patrolling it (Vol. 2, p. 305):" : "No one patrolled it, so no one caught them."}</span>
      </p>
      {patrols.map((p) => (
        <label key={p.character_id} className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={caught.includes(p.character_id)}
            onChange={(e) => onChange(e.target.checked ? [...caught, p.character_id] : caught.filter((i) => i !== p.character_id))}
          />
          Caught by {p.character_name} ({p.actions} {p.actions === 1 ? "action" : "actions"} patrolling)
        </label>
      ))}
      {patrols.length > 0 && (
        <Button type="button" variant="secondary" className="self-start" onClick={() => onChange(throwChallenges(patrols))}>
          Throw the challenges
        </Button>
      )}
    </fieldset>
  );
}

/** A character's feeding restriction with the Rack, such as Prey Exclusion or the Ventrue clan weakness: the card numbers, by last digit, it may only or never take (p. 301). */
export function RestrictionEditor({ cycleId, character: c }: { cycleId: string; character: CharacterFeedingOut }) {
  const [mode, setMode] = useState<"only" | "never">(c.restriction?.mode ?? "never");
  const [endings, setEndings] = useState<number[]>(c.restriction?.endings ?? []);
  const save = useAction((rule: { mode: "only" | "never"; endings: number[] } | null) =>
    unwrap(
      api.PUT("/api/cycles/{cycle_id}/participants/{participant_id}/feeding-numbers", {
        params: { path: { cycle_id: cycleId, participant_id: c.participant_id } },
        body: { rule: rule && { ...rule, text: "" } },
      }),
    ),
  );
  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer text-mist">{c.restriction ? `Feeding restriction: ${c.restriction.text}` : `Set a feeding restriction for ${c.character_name}`}</summary>
      <div className="mt-2 flex flex-col gap-2">
        <p className="text-xs text-mist">For Prey Exclusion or the Ventrue clan weakness: the card numbers it may take, by their last digit. Its Herd's cards always suit it.</p>
        <Select aria-label="Restriction" className="w-auto self-start" value={mode} onChange={(e) => setMode(e.target.value as "only" | "never")}>
          <option value="never">Never cards ending in</option>
          <option value="only">Only cards ending in</option>
        </Select>
        <div className="flex flex-wrap gap-3" role="group" aria-label="Last digits">
          {Array.from({ length: 10 }, (_, d) => (
            <label key={d} className="flex items-center gap-1">
              <input type="checkbox" checked={endings.includes(d)} onChange={(e) => setEndings(e.target.checked ? [...endings, d] : endings.filter((x) => x !== d))} />
              {d}
            </label>
          ))}
        </div>
        <span className="flex gap-2">
          <Button variant="secondary" disabled={!endings.length || save.isPending} onClick={() => save.mutate({ mode, endings })}>
            Save restriction
          </Button>
          {c.restriction && (
            <Button variant="ghost" disabled={save.isPending} onClick={() => save.mutate(null)}>
              Remove it
            </Button>
          )}
        </span>
        <ErrorText error={save.error} />
      </div>
    </details>
  );
}

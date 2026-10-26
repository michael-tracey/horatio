import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, CharacterOut, EmbraceOut, EmbracePlanOut, EmbraceStepOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, Card, ErrorText, Field, Input, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { listed } from "./creation/notices";
import { useDomitor } from "./Domitor";
import { CAITIFF_CHOOSES, caitiffChoices, clansOf } from "./domitor";
import { BUY_BACK_DOTS, balanceText, choicesBody, dotsBoughtBack, fromRemoveKey, newDraft, ordinal, removeKey, running, sireMissing, type EmbraceDraft, xpText } from "./embrace";

/**
 * A ghoul's Embrace on its sheet (MET: VTM pp. 297–299): for the home troupe's
 * storytellers and assistants, "Embrace…", which walks them through it; once it is
 * done, what it did.
 */
export function EmbraceCard({ character, catalogue }: { character: CharacterOut; catalogue?: CatalogueOut }) {
  const dates = useDates();
  const [open, setOpen] = useState(false);
  const list = useQuery({
    queryKey: ["embrace", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/embrace", { params: { path: { character_id: character.id } } })),
  });
  if (!list.data || (!list.data.entries.length && !list.data.can_embrace)) return null;
  return (
    <Card
      dense
      title="Embrace"
      actions={
        list.data.can_embrace && catalogue ? (
          <Button variant="secondary" className="min-h-8 px-2" onClick={() => setOpen(true)}>
            Embrace…
          </Button>
        ) : undefined
      }
    >
      {list.data.entries.length === 0 && <p className="text-sm text-mist">If {character.name} is Embraced in play, its player chooses: it dies, or it becomes a vampire.</p>}
      <ul aria-label="Embrace" className="flex flex-col gap-3 text-sm">
        {list.data.entries.map((e) => (
          <EmbraceEntry key={e.id} entry={e} day={dates.day(e.embraced_on)} />
        ))}
      </ul>
      {catalogue && (
        <Dialog title={`Embrace ${character.name}`} open={open} onClose={() => setOpen(false)} wide>
          <EmbraceForm character={character} catalogue={catalogue} onClose={() => setOpen(false)} />
        </Dialog>
      )}
    </Card>
  );
}

function EmbraceEntry({ entry, day }: { entry: EmbraceOut; day: string }) {
  const sire = entry.sire_id ? (
    <Link className="text-gold underline" to={`/characters/${entry.sire_id}`}>
      {entry.sire_name}
    </Link>
  ) : (
    entry.sire_name
  );
  if (entry.result === "died")
    return (
      <li>
        <p className="text-parchment">
          Died in the Embrace, {day}
          {entry.sire_name && <>, by {sire}</>}.
        </p>
        {entry.note && <p className="text-xs text-mist">{entry.note}</p>}
      </li>
    );
  return (
    <li>
      <p className="text-parchment">
        Embraced {day} by {sire}, of {entry.sire_clan}
        {entry.sire_generation ? `, ${ordinal(entry.sire_generation)} generation` : ""}.
      </p>
      {entry.note && <p className="text-xs text-mist">{entry.note}</p>}
      <details className="mt-1 text-xs text-mist">
        <summary className="cursor-pointer">What it did</summary>
        <StepList steps={entry.steps} />
      </details>
    </li>
  );
}

/** Each step's lines with their XP. */
function StepList({ steps }: { steps: EmbraceStepOut[] }) {
  return (
    <ol className="mt-1 flex flex-col gap-2">
      {steps.map((s) => (
        <li key={s.key}>
          <p className="text-parchment">
            {s.title} {s.xp !== 0 && <span className="font-mono text-xs">{xpText(s.xp)}</span>}
          </p>
          <StepLines step={s} />
        </li>
      ))}
    </ol>
  );
}

function StepLines({ step }: { step: EmbraceStepOut }) {
  return (
    <ul className="flex flex-col gap-0.5 text-xs text-mist">
      {step.lines.map((l, i) => (
        <li key={i} className="flex justify-between gap-3">
          <span>{l.text}</span>
          {l.xp !== 0 && <span className={`shrink-0 font-mono ${l.xp < 0 ? "text-blood-bright" : "text-gold"}`}>{xpText(l.xp)}</span>}
        </li>
      ))}
    </ul>
  );
}

const PAGES = ["What happens", "Sire", "Clan and rarity", "Generation", "Disciplines", "Skills and backgrounds", "Finishing touches", "XP debt", "Confirm"] as const;
// Which plan step each page shows.
const STEP_OF: Partial<Record<(typeof PAGES)[number], string>> = {
  "Clan and rarity": "clan",
  Generation: "generation",
  Disciplines: "disciplines",
  "Skills and backgrounds": "reprice",
  "Finishing touches": "finishing",
  "XP debt": "debt",
};

function today(dates: ReturnType<typeof useDates>) {
  return dates.toInput(new Date()).slice(0, 10);
}

/**
 * The Embrace, a page a step: the player's choice, then for a new vampire the sire,
 * and each step of the conversion with what it does to the XP, then a last look
 * before confirming. Nothing changes until then.
 */
function EmbraceForm({ character, catalogue, onClose }: { character: CharacterOut; catalogue: CatalogueOut; onClose: () => void }) {
  const dates = useDates();
  const [page, setPage] = useState(0);
  const [outcome, setOutcome] = useState<"vampire" | "died">("vampire");
  const [when, setWhen] = useState(today(dates));
  const [note, setNote] = useState("");
  const [draft, setDraft] = useState<EmbraceDraft>(newDraft);
  const missing = sireMissing(draft.sire);
  const body = choicesBody(draft);
  const plan = useQuery({
    queryKey: ["embrace-plan", character.id, JSON.stringify(body)],
    queryFn: () => unwrap(api.POST("/api/characters/{character_id}/embrace/plan", { params: { path: { character_id: character.id } }, body })),
    enabled: outcome === "vampire" && !missing,
    placeholderData: keepPreviousData,
  });
  const embrace = useAction(async () => {
    await unwrap(api.POST("/api/characters/{character_id}/embrace", { params: { path: { character_id: character.id } }, body: { ...body, embraced_on: when, note } }));
    onClose();
  });
  const died = useAction(async () => {
    const sireName = draft.sire.kind === "linked" ? (draft.sire.choice?.name ?? "") : draft.sire.name;
    await unwrap(api.POST("/api/characters/{character_id}/embrace/died", { params: { path: { character_id: character.id } }, body: { embraced_on: when, sire_name: sireName, note } }));
    onClose();
  });
  const p = missing ? undefined : plan.data;
  const name = PAGES[page] ?? PAGES[0];
  const last = page === PAGES.length - 1;
  const set = (change: Partial<EmbraceDraft>) => setDraft({ ...draft, ...change });

  if (outcome === "died" && page > 0) {
    return (
      <form
        aria-label="Dies in the Embrace"
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          died.mutate(undefined);
        }}
      >
        <p className="text-sm">
          {character.name} dies in the attempted Embrace. It is retired, kept with its full history, and its log says why. Its player is told.
        </p>
        <ErrorText error={died.error} />
        <div className="flex gap-2">
          <Button type="submit" disabled={died.isPending}>
            Confirm: {character.name} dies
          </Button>
          <Button type="button" variant="ghost" onClick={() => setPage(0)}>
            Back
          </Button>
        </div>
      </form>
    );
  }

  return (
    <form
      aria-label="Embrace"
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (last) embrace.mutate(undefined);
        else setPage(page + 1);
      }}
    >
      <ol aria-label="Steps" className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {PAGES.map((title, i) => (
          <li key={title} aria-current={i === page ? "step" : undefined} className={i === page ? "text-gold" : i < page ? "text-parchment" : "text-mist"}>
            {i + 1}. {title}
          </li>
        ))}
      </ol>
      <h3 className="font-display text-lg text-parchment">{name}</h3>

      {name === "What happens" && (
        <>
          <p className="text-sm text-mist">When a ghoul is Embraced in play, its player chooses whether it dies in the attempt or becomes a vampire (p. 297).</p>
          <fieldset className="flex flex-col gap-1 text-sm">
            <legend className="sr-only">What happens</legend>
            <label className="flex items-center gap-2">
              <input type="radio" name="embrace-outcome" checked={outcome === "vampire"} onChange={() => setOutcome("vampire")} />
              {character.name} becomes a vampire
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name="embrace-outcome" checked={outcome === "died"} onChange={() => setOutcome("died")} />
              {character.name} dies in the Embrace
            </label>
          </fieldset>
          <div className="flex flex-wrap gap-3">
            <Field label="Date" hint="The night it happened.">
              <Input type="date" required value={when} onChange={(e) => setWhen(e.target.value)} className="w-44" />
            </Field>
          </div>
          <Field label="Note" hint="For the log.">
            <Textarea rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        </>
      )}

      {name === "Sire" && <SirePage character={character} catalogue={catalogue} draft={draft} set={set} plan={p} />}

      {name === "Clan and rarity" && p && (
        <>
          {p.sire_is_domitor ? (
            <p className="text-sm text-mist">The sire was the domitor, so {character.name} already has the right clan and rarity merits.</p>
          ) : (
            <>
              <p className="text-sm text-mist">
                Its domitor's clan and rarity merits are stripped, and their XP refunded. It buys the merits {p.sire_clan} needs in the setting: its rarity, and the bloodline merit if
                the setting has one.
              </p>
              <fieldset className="grid gap-1 text-sm sm:grid-cols-2">
                <legend className="mb-1 text-mist">The sire's clan and rarity merits</legend>
                {p.clan_merit_choices.map((merit) => {
                  const chosen = (draft.clanMerits ?? p.clan_merits).includes(merit);
                  return (
                    <label key={merit} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={chosen}
                        onChange={() => {
                          const now = draft.clanMerits ?? p.clan_merits;
                          set({ clanMerits: chosen ? now.filter((m) => m !== merit) : [...now, merit] });
                        }}
                      />
                      {merit}
                    </label>
                  );
                })}
              </fieldset>
            </>
          )}
        </>
      )}

      {name === "Generation" && p && p.generation && (
        <p className="text-sm text-mist">
          One weaker than the sire's {ordinal(p.sire_generation ?? 0)}: the {ordinal(p.generation)} generation, {p.generation_dots} {p.generation_dots === 1 ? "dot" : "dots"} of Generation, a {p.title}.
          Bought at a background's price, an exception to Generation never being bought in play
          {p.lesser_flaw ? `; ${p.lesser_flaw} shows the weaker blood (p. 263)` : ""}.
        </p>
      )}

      {name === "Disciplines" && p && (
        <>
          <p className="text-sm text-mist">Every ghoul dot is lost. The new vampire has 2 dots in one in-clan discipline and 1 in each of the others, free.</p>
          {p.caitiff && (
            <div className="grid gap-3 sm:grid-cols-3">
              {Array.from({ length: CAITIFF_CHOOSES }, (_, i) => (
                <Field key={i} label={`In-clan discipline ${i + 1}`} hint={i === 0 ? "A Caitiff chooses its three (p. 246)." : undefined}>
                  <Select value={draft.caitiffThree[i] ?? ""} onChange={(e) => set({ caitiffThree: draft.caitiffThree.map((d, j) => (j === i ? e.target.value : d)) })}>
                    <option value="">Choose…</option>
                    {caitiffChoices(catalogue).map((d) => (
                      <option key={d}>{d}</option>
                    ))}
                  </Select>
                </Field>
              ))}
            </div>
          )}
          {p.in_clan.length > 0 && (
            <Field label="2 dots in">
              <Select value={draft.twoDots ?? p.two_dots ?? ""} onChange={(e) => set({ twoDots: e.target.value })} className="w-64">
                {p.in_clan.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </Select>
            </Field>
          )}
        </>
      )}

      {name === "Skills and backgrounds" && p && (
        <p className="text-sm text-mist">What {character.name} bought in play is priced again at the new Generation; the difference is owed. What it had free, or bought at creation, stays.</p>
      )}

      {name === "Finishing touches" && p && (
        <>
          <Field label="Clan weakness" hint={`As the player takes it for ${p.sire_clan}: a Malkavian's derangement, say.`}>
            <Input maxLength={1000} value={draft.weakness} onChange={(e) => set({ weakness: e.target.value })} />
          </Field>
          <fieldset className="flex flex-col gap-1 text-sm">
            <legend className="mb-1 text-mist">
              Merits and flaws the Storyteller lets change. Merits: {p.merit_points} of {p.merit_limit} points.
            </legend>
            {p.removable.length === 0 && <p className="text-mist">None to take off.</p>}
            {[...p.removable, ...removedNow(draft, p)].map((r) => {
              const key = removeKey(r);
              const chosen = draft.remove.includes(key);
              return (
                <label key={key} className="flex items-center gap-2">
                  <input type="checkbox" checked={chosen} onChange={() => set({ remove: chosen ? draft.remove.filter((k) => k !== key) : [...draft.remove, key] })} />
                  Take off {r.name}
                  {r.detail && `: ${r.detail}`} {r.rating > 0 && `(${r.rating})`}
                  <span className="text-xs text-mist">{xpText(r.xp) || "no XP"}</span>
                </label>
              );
            })}
          </fieldset>
        </>
      )}

      {name === "XP debt" && p && <DebtPage draft={draft} set={set} plan={p} />}

      {name === "Confirm" && p && (
        <>
          <StepList steps={p.steps} />
          <p className="text-sm">
            {balanceText(p.balance_before)} before; {balanceText(p.balance_after)} after.
            {p.debt > 0 && ` All the XP ${character.name} earns goes to its debt of ${p.debt} until it is paid off.`}
          </p>
          {p.notes.length > 0 && (
            <ul className="text-xs text-mist">
              {p.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
          <p className="text-xs text-mist">Confirming makes {character.name} a vampire of {p.clan}, by the vampire rules, with no domitor. Every step goes in its log, and its player is told.</p>
        </>
      )}

      {page > 0 && p && STEP_OF[name] && <PlanStep plan={p} step={STEP_OF[name]!} />}
      {page > 0 && missing && <p className="text-xs text-mist">{missing}</p>}
      {page > 1 && p?.refused && <ErrorText error={new Error(p.refused)} />}
      {page > 1 && p?.dies && (
        <p className="text-sm">
          <button type="button" className="text-gold underline" onClick={() => setOutcome("died")}>
            Record that {character.name} dies in the Embrace
          </button>
        </p>
      )}
      <ErrorText error={plan.error ?? embrace.error} />
      <div className="flex gap-2">
        {page > 0 && (
          <Button type="button" variant="ghost" onClick={() => setPage(page - 1)}>
            Back
          </Button>
        )}
        <Button type="submit" disabled={(page > 0 && outcome === "vampire" && (!!missing || !p)) || (last && (!!p?.refused || embrace.isPending))}>
          {last ? `Embrace ${character.name}` : "Next"}
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Merits and flaws already chosen to come off, which the plan no longer lists as on the sheet. */
function removedNow(draft: EmbraceDraft, plan: EmbracePlanOut) {
  const listedKeys = new Set(plan.removable.map(removeKey));
  return draft.remove
    .filter((key) => !listedKeys.has(key))
    .map((key) => ({ ...fromRemoveKey(key), rating: 0, xp: 0 }));
}

/** One step of the plan, with its XP and what the character has after it. */
function PlanStep({ plan, step }: { plan: EmbracePlanOut; step: string }) {
  const found = running(plan).find((r) => r.step.key === step);
  if (!found) return null;
  return (
    <div className="rounded-md border border-ash p-2" aria-label="This step">
      <StepLines step={found.step} />
      <p className="mt-2 flex justify-between border-t border-ash pt-1 text-xs">
        <span>
          This step: <span className="font-mono">{xpText(found.step.xp) || "no XP"}</span>
        </span>
        <span>After it: {balanceText(found.after)}</span>
      </p>
    </div>
  );
}

/** Who the sire is: a vampire in Horatio, or one named with its clan and generation. */
function SirePage({
  character,
  catalogue,
  draft,
  set,
  plan,
}: {
  character: CharacterOut;
  catalogue: CatalogueOut;
  draft: EmbraceDraft;
  set: (change: Partial<EmbraceDraft>) => void;
  plan?: EmbracePlanOut;
}) {
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const found = useQuery({
    queryKey: ["embrace-sires", character.id, q],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/embrace/sires", { params: { path: { character_id: character.id }, query: { q } } })),
    enabled: draft.sire.kind === "linked",
    placeholderData: (previous) => previous,
  });
  const domitor = useDomitor(character);
  const sire = draft.sire;
  const named = sire.kind === "named" ? sire : { kind: "named" as const, name: "", clan: "", generation: null };
  return (
    <>
      <fieldset className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <legend className="mb-1 text-mist">Where is the sire?</legend>
        <label className="flex items-center gap-2">
          <input type="radio" name="sire-kind" checked={sire.kind === "linked"} onChange={() => set({ sire: { kind: "linked", choice: null }, clanMerits: null })} />
          A vampire in Horatio
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="sire-kind" checked={sire.kind === "named"} onChange={() => set({ sire: named, clanMerits: null })} />
          Not in Horatio
        </label>
      </fieldset>
      {sire.kind === "linked" ? (
        <>
          <Field label="Find a vampire" hint="PCs and NPCs whose sheets you see, with a clan.">
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name…" />
          </Field>
          {found.data && found.data.length === 0 && <p className="text-sm text-mist">No vampire found.</p>}
          {found.data && found.data.length > 0 && (
            <ul aria-label="Vampires found" className="flex flex-col gap-1">
              {found.data.map((c) => (
                <li key={c.character_id}>
                  <label className={`flex items-center gap-2 rounded px-2 py-1.5 text-sm ${sire.choice?.character_id === c.character_id ? "bg-ash/60" : "hover:bg-ash/40"}`}>
                    <input type="radio" name="sire-choice" checked={sire.choice?.character_id === c.character_id} onChange={() => set({ sire: { kind: "linked", choice: c }, clanMerits: null })} />
                    <span className="text-parchment">{c.name}</span>
                    <span className="text-mist">
                      {c.clan} · {c.generation ? `${ordinal(c.generation)} generation` : "no Generation"} · {c.kind === "npc" ? "NPC" : "PC"}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <ErrorText error={found.error} />
        </>
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Sire's name">
            <Input maxLength={200} value={named.name} onChange={(e) => set({ sire: { ...named, name: e.target.value } })} />
          </Field>
          <Field label="Sire's clan">
            <Select value={named.clan} onChange={(e) => set({ sire: { ...named, clan: e.target.value }, clanMerits: null })}>
              <option value="">Choose…</option>
              {clansOf(catalogue).map((clan) => (
                <option key={clan}>{clan}</option>
              ))}
            </Select>
          </Field>
          <Field label="Sire's generation" hint="12 for the 12th.">
            <Input type="number" min={5} max={12} value={named.generation ?? ""} onChange={(e) => set({ sire: { ...named, generation: e.target.value ? Number(e.target.value) : null } })} />
          </Field>
        </div>
      )}
      {/* Where both are in Horatio, Horatio knows whether they are one. */}
      {(sire.kind === "named" || !domitor.data?.character_id) && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={draft.sireIsDomitor ?? plan?.sire_is_domitor ?? false} onChange={(e) => set({ sireIsDomitor: e.target.checked })} />
          The sire was {character.name}'s domitor
        </label>
      )}
      {plan?.generation && (
        <p className="text-sm text-mist">
          {character.name} would be a vampire of {plan.clan}, {ordinal(plan.generation)} generation. In-clan: {listed(plan.in_clan)}.
        </p>
      )}
    </>
  );
}

/** What is left over or owed, and the lost dots bought back. */
function DebtPage({ draft, set, plan }: { draft: EmbraceDraft; set: (change: Partial<EmbraceDraft>) => void; plan: EmbracePlanOut }) {
  const bought = dotsBoughtBack(draft.buyBack, plan);
  const starting = new Map(plan.disciplines.map((d) => [d.name, d.rating]));
  return (
    <>
      <p className="text-sm text-mist">
        Refunds and saved XP pay the costs first. What they cannot pay is XP debt: all the XP it earns goes to the debt until it is paid off, and nothing new is bought till
        then. Up to {BUY_BACK_DOTS} lost discipline dots can be bought back with what is left over, at what they now cost, with no teacher.
      </p>
      {plan.lost.length > 0 && (
        <fieldset className="grid gap-3 sm:grid-cols-3">
          <legend className="mb-1 text-sm text-mist">Lost dots bought back: {bought} of {BUY_BACK_DOTS}</legend>
          {plan.lost.map((d) => {
            const from = starting.get(d.name) ?? 0;
            return (
              <Field key={d.name} label={`${d.name}, was ${d.rating}`}>
                <Select value={draft.buyBack[d.name] ?? from} onChange={(e) => set({ buyBack: { ...draft.buyBack, [d.name]: Number(e.target.value) } })}>
                  {Array.from({ length: d.rating - from + 1 }, (_, i) => from + i).map((n) => (
                    <option key={n} value={n}>
                      {n === from ? `${n}, as it starts` : n}
                    </option>
                  ))}
                </Select>
              </Field>
            );
          })}
        </fieldset>
      )}
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft.intoDebt} onChange={(e) => set({ intoDebt: e.target.checked })} />
        The Storyteller lets lost dots be bought back into XP debt, now or later from the cart
      </label>
    </>
  );
}

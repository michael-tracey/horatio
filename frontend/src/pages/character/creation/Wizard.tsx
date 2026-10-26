import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../../../api/client";
import type { CatalogueOut, CharacterOut, CreationOut, SheetOut, TraitOut, TraitRefOut } from "../../../api/types";
import { Button, Card, ErrorText, Field, Input, Loading, Notice, Select, Textarea } from "../../../components/ui";
import { useAction, useRatingRefusals, useRefusals, useUnavailable } from "../../../hooks";
import { BuildFor } from "../BuildFor";
import { useCart } from "../cart";
import { FinishCreation } from "../CartPanel";
import { rulesTroupe } from "../rules";
import { quickPicks } from "../traitFilter";
import { DotGrid, PointsList, type Held, type RatingBar } from "./DotGrid";
import { Because } from "./Because";
import { FreeChoicesStep, withFreeChoices } from "./FreeChoicesStep";
import { BACKGROUND_MERITS, FOCUS_MERITS, SKILL_MERITS, freedPicks, givenIn, unchosenFree } from "./gifts";
import { detailNeed, fieldSkills } from "../fields";
import { SetField } from "../Specializations";
import { CUSTOM_ARCHETYPE, fieldProblems, identityChoices, keyed, traitOf, type Allowed, type Picks } from "./logic";
import { FromMerits } from "./FromMerits";
import { EXTRA_IN_CLAN, IN_CLAN_MERITS, inClanChoices } from "./inClan";
import { InClanPicker } from "./InClanPicker";
import { DISCIPLINES_FROM_MERITS, INEPT, disciplinesIntro, ineptChoices, withoutDotReasons } from "./disciplines";
import { brokenChecks, listed, overBudget, stepFor, stepNotices, strayPicks, type NoticeSource, type StepNotice, type StepRef } from "./notices";

/** A step: the categories it places picks in, and those it decides without picks. */
type Step = StepRef & { intro?: string };

/** Where cross-step notices come from (notices.ts): a step that needs a new kind adds its source here. */
const NOTICE_SOURCES: NoticeSource[] = [inClanChoices, strayPicks, overBudget, freedPicks, unchosenFree, brokenChecks];

/** Merits and flaws that change a step, offered on it as well as on Merits & flaws (#192). */
const FROM_MERITS: Record<string, { category: string; name: string }[]> = {
  concept: IN_CLAN_MERITS.map((name) => ({ category: "merits", name })),
  focuses: FOCUS_MERITS,
  skills: SKILL_MERITS,
  backgrounds: BACKGROUND_MERITS,
  disciplines: DISCIPLINES_FROM_MERITS,
};

/** Wizard steps, in the order a player builds a character. Any category with
 * creation picks that no step names gets a step of its own before merits. */
const ORDER: Step[] = [
  { key: "attributes", title: "Attributes", categories: ["attributes"], intro: "Rank Physical, Social and Mental: tap 7, 5 or 3 for each. Tapping a taken rating swaps them." },
  { key: "focuses", title: "Focuses", categories: ["focus_physicals", "focus_mentals", "focus_socials"], intro: "Choose one focus for each attribute. Some merits give more; they show below." },
  { key: "skills", title: "Skills", categories: ["skills"], intro: "Tap the dot for each skill's rating. The counters show what is left." },
  { key: "backgrounds", title: "Backgrounds", categories: ["backgrounds"] },
  { key: "disciplines", title: "Disciplines", categories: ["disciplines"] },
  { key: "merits", title: "Merits & flaws", categories: ["merits", "flaws"], intro: "Each comes from its own budget of points. Both are optional." },
];

function buildSteps(creation: CreationOut, catalogue: CatalogueOut): Step[] {
  const present = new Set(creation.pools.map((p) => p.category));
  const known = new Set(ORDER.flatMap((s) => s.categories));
  // A category of specialisations is shown under the skill or background it is for, so a free one (Chosen of Cappadocius) lands there.
  const specialising = (s: Step) => catalogue.categories.filter((c) => c.specializes && s.categories.includes(c.specializes.category ?? "")).map((c) => c.key);
  const steps = ORDER.map((s) => ({ ...s, categories: s.categories.filter((c) => present.has(c)) }))
    .filter((s) => s.categories.length)
    .map((s) => ({ ...s, decides: specialising(s) }));
  const extra = [...present]
    .filter((c) => !known.has(c))
    .map((c) => ({ key: c, title: creation.pools.find((p) => p.category === c)!.category_name, categories: [c], decides: [] as string[] }));
  const merits = steps.findIndex((s) => s.key === "merits");
  steps.splice(merits === -1 ? steps.length : merits, 0, ...extra);
  // Concept decides the unrated choices (clan, sect…) and the extra in-clan disciplines.
  const decides = [...catalogue.categories.filter((c) => !c.rated).map((c) => c.key), EXTRA_IN_CLAN];
  return [{ key: "concept", title: "Concept", categories: [], decides }, ...steps, { key: "review", title: "Review", categories: [] }];
}

/** The picks already saved, and the detail saved with each (a merit's choice, a
 * skill's field), by category then pick (see logic's `copyKey`). */
function saved(creation: CreationOut): { picks: Record<string, Picks>; details: Record<string, Record<string, string>> } {
  const picks: Record<string, Picks> = {};
  const details: Record<string, Record<string, string>> = {};
  for (const category of new Set(creation.pools.map((p) => p.category))) {
    const kept = keyed(creation.pools.filter((p) => p.category === category).flatMap((p) => p.traits));
    picks[category] = kept.picks;
    details[category] = kept.details;
  }
  return { picks, details };
}

function allowedFor(creation: CreationOut, category: string): Allowed {
  return Object.fromEntries(creation.pools.filter((p) => p.category === category).map((p) => [p.rating, p.allowed]));
}

export function CreationWizard({ character }: { character: CharacterOut }) {
  const { step: stepKey = "concept" } = useParams();
  const navigate = useNavigate();
  const path = { params: { path: { character_id: character.id } } };
  const creation = useQuery({ queryKey: ["creation", character.id], queryFn: () => unwrap(api.GET("/api/characters/{character_id}/creation", path)) });
  const sheet = useQuery({ queryKey: ["sheet", character.id], queryFn: () => unwrap(api.GET("/api/characters/{character_id}/sheet", path)) });
  const catalogue = useQuery({
    queryKey: ["catalogue", character.splat, rulesTroupe(character)],
    queryFn: () =>
      unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: character.splat }, query: { troupe_id: rulesTroupe(character) } } })),
    staleTime: 5 * 60_000,
  });

  if (character.creation_complete) return <Navigate to={`/characters/${character.id}`} replace />;
  if (creation.isPending || sheet.isPending || catalogue.isPending) return <Loading />;
  if (!creation.data || !sheet.data || !catalogue.data) {
    return <ErrorText error={creation.error ?? sheet.error ?? catalogue.error} />;
  }

  const steps = buildSteps(creation.data, catalogue.data);
  const notices = stepNotices({ creation: creation.data, sheet: sheet.data, steps }, NOTICE_SOURCES);
  const index = Math.max(0, steps.findIndex((s) => s.key === stepKey));
  // The first step that still needs something (a vampire's Generation): no going past it.
  const needs = creation.data.needs;
  const stuck = steps.findIndex((s) => needs.some((n) => s.categories.includes(n.step)));
  const go = (i: number) => navigate(`/characters/${character.id}/create/${steps[i]!.key}`);

  return (
    <div className="grid gap-6 lg:grid-cols-[12rem_minmax(0,1fr)]">
      {/* min-w-0: without it the step list's sideways scroller widens the page on phones. */}
      <nav aria-label="Creation steps" className="min-w-0">
        {/* relative: so the screen-reader-only marks past the right edge are clipped here, not left to widen the page. */}
        <ol className="relative flex gap-1 overflow-x-auto lg:flex-col">
          {steps.map((s, i) => (
            <li key={s.key}>
              {stuck !== -1 && i > stuck ? (
                <span
                  aria-disabled="true"
                  title={`Finish ${steps[stuck]!.title} first`}
                  className="block cursor-not-allowed rounded px-3 py-1.5 text-sm whitespace-nowrap text-ash"
                >
                  {i + 1}. {s.title}
                </span>
              ) : (
              <Link
                to={`/characters/${character.id}/create/${s.key}`}
                aria-current={i === index ? "step" : undefined}
                className={`block rounded px-3 py-1.5 text-sm whitespace-nowrap ${i === index ? "bg-dusk text-gold" : "text-mist hover:text-parchment"}`}
              >
                {i + 1}. {s.title}
                {notices.some((n) => n.on.includes(s.key)) && (
                  <>
                    <span aria-hidden className="ml-1.5 text-blood-bright" title="Something here needs a look">
                      •
                    </span>
                    <span className="sr-only"> (needs a look)</span>
                  </>
                )}
              </Link>
              )}
            </li>
          ))}
        </ol>
      </nav>
      <StepView
        key={steps[index]!.key}
        character={character}
        step={steps[index]!}
        creation={creation.data}
        sheet={sheet.data}
        catalogue={catalogue.data}
        onBack={index > 0 ? () => go(index - 1) : undefined}
        onNext={index < steps.length - 1 ? () => go(index + 1) : undefined}
        steps={steps}
        notices={notices}
      />
    </div>
  );
}

function StepView({
  character,
  step,
  creation,
  sheet,
  catalogue,
  onBack,
  onNext,
  steps,
  notices,
}: {
  character: CharacterOut;
  step: Step;
  creation: CreationOut;
  sheet: SheetOut;
  catalogue: CatalogueOut;
  onBack?: () => void;
  onNext?: () => void;
  steps: Step[];
  notices: StepNotice[];
}) {
  // Keyed by content, so a refetch that brings back the same saved picks (as the last
  // step's save does) doesn't wipe taps on this step that aren't saved yet.
  const savedKey = JSON.stringify(saved(creation));
  const { picks: before, details: savedDetail } = useMemo(() => JSON.parse(savedKey) as ReturnType<typeof saved>, [savedKey]);
  const [picks, setPicks] = useState<Record<string, Picks>>(before);
  useEffect(() => setPicks(before), [before]);
  const [details, setDetails] = useState(savedDetail);
  useEffect(() => setDetails(savedDetail), [savedDetail]);
  // A Crafts, Performance or Science with no field, a Retainer with no name, or two
  // with one field or name: by category, then pick. A Retainer saved without a name,
  // from before each was named, may stay so.
  const detailNeeds = new Map(catalogue.traits.map((t) => [`${t.category}/${t.name}`, detailNeed(t)]));
  const problems = Object.fromEntries(
    step.categories.map((c) => {
      const found = fieldProblems(picks[c] ?? {}, details[c] ?? {}, (name) => detailNeeds.get(`${c}/${name}`) ?? null);
      const unnamedBefore = (key: string) => !found[key]?.twice && key in (before[c] ?? {}) && !(savedDetail[c]?.[key] ?? "") && detailNeeds.get(`${c}/${traitOf(key)}`)?.kind === "name";
      return [c, Object.fromEntries(Object.entries(found).filter(([key]) => !unnamedBefore(key)))];
    }),
  );

  // The categories whose picks or fields differ from those saved.
  const changed = step.categories.filter((category) => {
    const mine = picks[category] ?? {};
    const detail = details[category] ?? {};
    return !(
      JSON.stringify(Object.entries(mine).sort()) === JSON.stringify(Object.entries(before[category] ?? {}).sort()) &&
      Object.keys(mine).every((key) => (detail[key] ?? "").trim() === (savedDetail[category]?.[key] ?? ""))
    );
  });
  const client = useQueryClient();
  const save = useAction(async () => {
    let now: CreationOut | undefined;
    for (const category of changed) {
      const detail = details[category] ?? {};
      now = await unwrap(
        api.PUT("/api/characters/{character_id}/creation/categories/{category}", {
          params: { path: { character_id: character.id, category } },
          body: { picks: Object.entries(picks[category] ?? {}).map(([key, rating]) => ({ name: traitOf(key), rating, detail: (detail[key] ?? "").trim() })) },
        }),
      );
    }
    // The last save says what the step still needs. Shown at once (the notice below),
    // not once every query on the page has been asked again.
    client.setQueryData(["creation", character.id], now);
    return now!.needs.filter((n) => step.categories.includes(n.step));
  });
  const needs = creation.needs.filter((n) => step.categories.includes(n.step));
  // Stay on the step if saving fails (save.error shows why), and going forward
  // while the step still needs something, such as a skill's field (the notice,
  // and the row, say what). Two picks of one skill with one field cannot be saved.
  const twice = Object.values(problems).some((p) => Object.values(p).some((why) => why.twice));
  const move = (to: (() => void) | undefined, forward: boolean) => {
    if (twice) return;
    // Nothing to save: what the step needs is shown already, so there is nothing to wait for.
    if (!changed.length) return forward && needs.length ? undefined : to?.();
    save.mutate(undefined, { onSuccess: (left) => (forward && left.length ? undefined : to?.()) });
  };

  // The Disciplines step's budget is the pools', which Thin Blooded and Inept change.
  const intro = step.key === "disciplines" ? disciplinesIntro(creation) : step.intro;
  // A house merit given by staff only, or archived, is not the player's to pick; one held stays listed.
  const traitsOf = (category: string) =>
    catalogue.traits.filter(
      (t) => t.category === category && (t.house?.offered !== false || sheet.traits.some((h) => h.category === category && h.name === t.name)),
    );
  // Inept names one of the in-clan disciplines now, not any discipline there is.
  const narrowed = (category: string, traits: TraitOut[]) =>
    category === "flaws" ? traits.map((t) => (t.name === INEPT ? { ...t, choices: ineptChoices(creation, details.flaws?.[INEPT]) } : t)) : traits;
  const nameOf = (category: string) => catalogue.categories.find((c) => c.key === category)?.name ?? category;
  // This step's notices, but for what it already holds the wizard to (its needs, below).
  const here = notices.filter((n) => n.on.includes(step.key) && !needs.some((need) => need.message === n.message));
  // Picks kept on traits they no longer fit, by category then trait: marked where they are.
  const strays: Record<string, Record<string, string>> = {};
  for (const n of here) if (n.trait && n.fix === step.key) (strays[n.trait.category] ??= {})[n.trait.name] = n.message;

  return (
    <Card title={step.title} className="min-w-0">
      {intro && <p className="mb-4 text-sm text-mist">{intro}</p>}
      {step.key !== "review" && <StepNotices character={character} notices={here} step={step} steps={steps} />}
      {step.key === "concept" && <ConceptStep character={character} creation={creation} sheet={sheet} catalogue={catalogue} />}
      {step.key === "review" && <ReviewStep character={character} creation={creation} catalogue={catalogue} steps={steps} notices={notices} />}
      {FROM_MERITS[step.key] && step.key !== "concept" && (
        <div className="mb-6">
          <FromMerits
            character={character}
            creation={creation}
            sheet={sheet}
            catalogue={catalogue}
            traits={FROM_MERITS[step.key]!}
            choices={step.key === "disciplines" ? { [INEPT]: ineptChoices(creation) } : undefined}
            steps={steps}
            step={step}
          />
        </div>
      )}
      {step.key === "disciplines" && (
        <div className="mb-6">
          <InClanNow creation={creation} />
        </div>
      )}
      {step.key === "merits" && <FreeTraitsToChoose character={character} sheet={sheet} />}
      {/* Held while saving: the save reloads the picks, which would drop a tap made meanwhile. */}
      <fieldset disabled={save.isPending} className="flex min-w-0 flex-col gap-8">
        {step.categories.map((category) => {
          const pools = creation.pools.filter((p) => p.category === category);
          const mine = picks[category] ?? {};
          const set = (next: Picks) => setPicks({ ...picks, [category]: next });
          if (pools[0]?.kind === "points") {
            return (
              <CheckedPointsList
                key={category}
                characterId={character.id}
                category={category}
                title={nameOf(category)}
                traits={narrowed(category, traitsOf(category))}
                budget={pools[0].allowed}
                picks={mine}
                onChange={set}
                quick={quickPicks(traitsOf(category), sheet.traits)}
                details={details[category] ?? {}}
                onDetail={(name, value) => setDetails({ ...details, [category]: { ...details[category], [name]: value } })}
                steps={steps}
                step={step}
              />
            );
          }
          let traits = traitsOf(category);
          // Picks restricted to some traits (in-clan disciplines) offer only those the
          // server says fit now, and any already placed that no longer do (marked).
          const restricted = pools.find((p) => p.options);
          const withoutDot = withoutDotReasons(creation, category);
          if (restricted) {
            // The in-clan ones, those that take no free dot (shown, with why), and any already placed.
            const fit = new Set([...restricted.options!, ...Object.keys(withoutDot)]);
            const placed = new Set(Object.keys(mine).map(traitOf));
            traits = traits.filter((t) => fit.has(t.name) || placed.has(t.name));
          }
          if (traits.length === 0 && restricted?.restriction === "in_clan") {
            return (
              <Notice key={category}>
                Starting {nameOf(category).toLowerCase()} must be in-clan. Choose a clan on the Concept step first.
              </Notice>
            );
          }
          return (
            <CheckedDotGrid
              key={category}
              characterId={character.id}
              category={category}
              title={nameOf(category)}
              showTitle={step.categories.length > 1}
              traits={traits}
              allowed={allowedFor(creation, category)}
              picks={mine}
              onChange={set}
              details={details[category] ?? {}}
              onDetail={(name, value) => setDetails({ ...details, [category]: { ...details[category], [name]: value } })}
              marks={strays[category]}
              barredFor={withoutDot}
              held={givenIn(creation, category)}
              steps={steps}
              step={step}
              sections={
                traits.some((t) => t.attribute)
                  ? { order: ["Physical", "Social", "Mental"], of: (t: TraitOut) => t.attribute }
                  : undefined
              }
            />
          );
        })}
      </fieldset>
      {needs.length > 0 && (
        <div className="mt-6">
          <Notice>Before moving on: {needs.map((n) => n.message).join(" ")}</Notice>
        </div>
      )}
      <ErrorText error={save.error} />
      <div className="mt-6 flex justify-between gap-2 border-t border-ash pt-4">
        <Button variant="secondary" disabled={!onBack || save.isPending} onClick={() => move(onBack, false)}>
          Back
        </Button>
        {onNext && (
          <Button disabled={save.isPending} onClick={() => move(onNext, true)}>
            Save and continue
          </Button>
        )}
      </div>
    </Card>
  );
}

function ConceptStep({ character, creation, sheet, catalogue }: { character: CharacterOut; creation: CreationOut; sheet: SheetOut; catalogue: CatalogueOut }) {
  const choose = useAction((body: { category: string; name: string }) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/traits", {
        params: { path: { character_id: character.id } },
        body: { ...body, detail: "", rating: null, teacher: "" },
      }),
    ),
  );
  // "Other…" waits for its name and description before it is saved.
  const [makingOwn, setMakingOwn] = useState(false);
  const choices = identityChoices(catalogue, sheet);
  return (
    <div className="flex flex-col gap-4">
      <BuildForCharacter character={character} />
      <p className="text-sm text-mist">Who is {character.name}? Clan matters most: it decides which disciplines are in-clan.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {choices.map((c) => (
          <Field key={c.key} label={c.name}>
            <Select
              value={c.key === "archetype" && makingOwn ? CUSTOM_ARCHETYPE : (sheet.traits.find((t) => t.category === c.key)?.name ?? "")}
              onChange={(e) => {
                if (!e.target.value) return;
                const own = c.key === "archetype" && e.target.value === CUSTOM_ARCHETYPE;
                if (c.key === "archetype") setMakingOwn(own);
                if (!own) choose.mutate({ category: c.key, name: e.target.value });
              }}
            >
              <option value="">Choose…</option>
              {catalogue.traits
                .filter((t) => t.category === c.key)
                .map((t) => (
                  <option key={t.name}>{t.name}</option>
                ))}
            </Select>
          </Field>
        ))}
      </div>
      <ErrorText error={choose.error} />
      {(makingOwn || sheet.traits.some((t) => t.category === "archetype" && t.name === CUSTOM_ARCHETYPE)) && (
        <OwnArchetype character={character} sheet={sheet} onSaved={() => setMakingOwn(false)} />
      )}
      {clanOf(sheet) && <InClanNow creation={creation} />}
      {clanOf(sheet) && <InClanPicker character={character} sheet={sheet} catalogue={catalogue} />}
      {clanOf(sheet) && <FromMerits character={character} creation={creation} sheet={sheet} catalogue={catalogue} traits={FROM_MERITS.concept!} />}
    </div>
  );
}

/** The disciplines in-clan now, as the server works them out: the clan's, or those a
 * merit sets in their place, and the extra ones. Starting dots go on these. */
function InClanNow({ creation }: { creation: CreationOut }) {
  const options = creation.pools.find((p) => p.restriction === "in_clan")?.options;
  if (!options?.length) return null;
  return <p className="text-sm text-mist">In-clan now: {listed(options)}.</p>;
}

/** An archetype of the player's own (p. 86): a name, and what it means for the character. */
function OwnArchetype({ character, sheet, onSaved }: { character: CharacterOut; sheet: SheetOut; onSaved: () => void }) {
  const held = sheet.traits.find((t) => t.category === "archetype" && t.name === CUSTOM_ARCHETYPE);
  const [name, setName] = useState(held?.detail ?? "");
  const [meaning, setMeaning] = useState(held?.note ?? "");
  const save = useAction(() =>
    unwrap(
      api.PUT("/api/characters/{character_id}/traits", {
        params: { path: { character_id: character.id } },
        body: { category: "archetype", name: CUSTOM_ARCHETYPE, detail: name.trim(), note: meaning.trim(), rating: null, teacher: "" },
      }),
    ),
  );
  return (
    <fieldset className="flex flex-col gap-3 rounded-md border border-ash p-3">
      <legend className="px-1 text-sm text-parchment">Your own archetype</legend>
      <Field label="Archetype's name">
        <Input maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="What it means for the character">
        <Textarea rows={3} maxLength={1000} value={meaning} onChange={(e) => setMeaning(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <div>
        <Button disabled={!name.trim() || save.isPending} onClick={() => save.mutate(undefined, { onSuccess: onSaved })}>
          Save archetype
        </Button>
      </div>
    </fieldset>
  );
}

function clanOf(sheet: SheetOut): string | undefined {
  return sheet.traits.find((t) => t.category === "clan")?.name;
}

function ReviewStep({
  character,
  creation,
  catalogue,
  steps,
  notices,
}: {
  character: CharacterOut;
  creation: CreationOut;
  catalogue: CatalogueOut;
  steps: Step[];
  notices: StepNotice[];
}) {
  const navigate = useNavigate();
  // Picks placed on the Sheet tab wait in the cart; finishing asks what to do with them.
  const cart = useCart(character.id);
  const stepFor = (category: string) => steps.find((s) => s.categories.includes(category));
  const open = creation.pools.filter((p) => p.kind === "picks" && p.remaining > 0);
  // Picks of Crafts, Performance or Science still without a field, while the rules
  // (as the troupe plays them) need one: given one here.
  const needsField = fieldSkills(catalogue);
  const fieldsNeeded = creation.needs.some((n) => n.step === "skills");
  const unfielded = creation.pools.flatMap((p) =>
    p.traits.filter((t) => fieldsNeeded && needsField.has(t.name) && !t.detail).map((t) => ({ category: p.category, name: t.name })),
  );

  return (
    <div className="flex flex-col gap-4">
      {notices.length > 0 && (
        <section aria-label="Still to settle" className="flex flex-col gap-1">
          <h3 className="text-sm text-gold">Still to settle</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {notices.map((n) => {
              const at = steps.find((s) => s.key === n.fix);
              return (
                <li key={n.key} className="flex gap-2">
                  <span aria-hidden className="text-blood-bright">
                    •
                  </span>
                  <span>
                    {n.message}
                    {at && (
                      <>
                        {" "}
                        <Link className="text-gold underline" to={`/characters/${character.id}/create/${at.key}`}>
                          Go to {at.title}
                        </Link>
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}
      {creation.path_starts.length > 0 && (
        <section aria-label="Morality" className="flex flex-col gap-1">
          <h3 className="text-sm text-gold">Morality</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {creation.path_starts.map((s) => (
              <li key={`${s.category}/${s.name}`}>
                {listed(s.because.map((b) => b.name!))}: your path starts at {s.rating}
                {s.page ? ` (p. ${s.page})` : ""}.
              </li>
            ))}
          </ul>
        </section>
      )}
      <ul className="flex flex-col gap-2 text-sm">
        {creation.pools.map((p) => {
          const done = p.kind === "points" || p.remaining === 0;
          const step = stepFor(p.category);
          return (
            <li key={`${p.category}/${p.rating}`} className="flex flex-wrap items-baseline gap-x-2">
              <span className={done ? "text-gold" : "text-blood-bright"}>{done ? "✓" : "•"}</span>
              <span className="w-44 text-mist">
                {p.category_name}
                {p.kind === "picks" ? ` at ${p.rating}` : ""}
              </span>
              <span>
                {p.traits.map((t) => (t.detail ? `${t.name}: ${t.detail}` : t.name)).join(", ") || "—"}
                {p.kind === "points" ? ` (${p.used} of ${p.allowed} points)` : p.remaining ? ` (${p.remaining} left)` : ""}
              </span>
              {!done && step && (
                <Link className="text-gold underline" to={`/characters/${character.id}/create/${step.key}`}>
                  fix
                </Link>
              )}
            </li>
          );
        })}
      </ul>
      {unfielded.length > 0 && (
        <section aria-label="Fields to give" className="flex flex-col gap-1">
          <ul className="flex flex-col gap-1">
            {unfielded.map((t) => (
              <li key={`${t.category}/${t.name}`}>
                <SetField character={character} trait={t} />
              </li>
            ))}
          </ul>
          {stepFor("skills") && (
            <Link className="self-start text-sm text-gold underline" to={`/characters/${character.id}/create/${stepFor("skills")!.key}`}>
              Back to {stepFor("skills")!.title}
            </Link>
          )}
        </section>
      )}
      {open.length > 0 ? (
        <Notice>Place every pick to finish. Merit and flaw points are optional.</Notice>
      ) : unfielded.length > 0 ? (
        <Notice>Everything is placed. Give each skill above its field to finish.</Notice>
      ) : notices.some((n) => !n.canWait) ? (
        <Notice>Everything is placed. Settle what is listed above to finish.</Notice>
      ) : (
        <Notice>Everything is placed. After finishing, new dots come from experience.</Notice>
      )}
      <FinishCreation
        character={character}
        cart={cart}
        disabled={open.length > 0 || unfielded.length > 0}
        className="self-start"
        onFinished={() => navigate(`/characters/${character.id}`)}
      >
        Finish creation
      </FinishCreation>
    </div>
  );
}

/** This step's cross-step notices, each linking to where it is put right. */
function StepNotices({ character, notices, step, steps }: { character: CharacterOut; notices: StepNotice[]; step: Step; steps: Step[] }) {
  if (!notices.length) return null;
  return (
    <div aria-label="Changed by other steps" role="group" className="mb-6 flex flex-col gap-2">
      {notices.map((n) => {
        const at = n.fix !== step.key ? steps.find((s) => s.key === n.fix) : undefined;
        return (
          <Notice key={n.key}>
            {n.message}
            {at && (
              <>
                {" "}
                <Link className="text-gold underline" to={`/characters/${character.id}/create/${at.key}`}>
                  Go to {at.title}
                </Link>
              </>
            )}
          </Notice>
        );
      })}
    </div>
  );
}

/**
 * A merits or flaws list whose greying follows the ticks as they change, before the
 * step is saved. A refusal because of a pick on an earlier step names that pick and
 * links to its step (rule 5 of #192).
 */
function CheckedPointsList({
  characterId,
  category,
  steps,
  step,
  ...props
}: { characterId: string; category: string; steps: Step[]; step: Step } & Parameters<typeof PointsList>[0]) {
  const refusals = useRefusals(characterId, category, true, { asIf: "picks", picks: Object.keys(props.picks).sort() }).data ?? {};
  const barred = useUnavailable(characterId, category, true, { asIf: "empty" });
  const unavailable = Object.fromEntries(Object.entries(refusals).map(([name, r]) => [name, r.message]));
  const before = steps.indexOf(step);
  const why = (name: string): ReactNode => {
    const earlier = new Map<Step, TraitRefOut[]>();
    for (const t of refusals[name]?.because ?? []) {
      const at = stepFor(steps, t.category) as Step | undefined;
      if (!at || !t.name || steps.indexOf(at) >= before) continue;
      earlier.set(at, [...(earlier.get(at) ?? []), t]);
    }
    if (!earlier.size) return null;
    return [...earlier].map(([at, refs], i) => (
      <Fragment key={at.key}>
        {i > 0 && "; "}
        Refused while you {refs.every((t) => t.category === "clan") ? "are" : "have"} {listed(refs.map((t) => t.name!))} (
        <Link className="text-gold underline" to={`/characters/${characterId}/create/${at.key}`}>
          {at.title}
        </Link>
        )
      </Fragment>
    ));
  };
  return <PointsList {...props} unavailable={unavailable} barred={barred.data} why={why} />;
}

/** The merits taken that give free traits the player chooses, with the fields to choose them. */
function FreeTraitsToChoose({ character, sheet }: { character: CharacterOut; sheet: SheetOut }) {
  const merits = withFreeChoices(sheet);
  if (!merits.length) return null;
  return (
    <section aria-label="Free traits to choose" className="mb-6 flex flex-col gap-3 rounded-md border border-ash p-3">
      <h3 className="text-sm text-parchment">Free traits to choose</h3>
      {merits.map((t) => (
        <div key={`${t.category}/${t.name}/${t.detail}`} className="flex flex-col gap-1.5">
          <p className="text-sm text-parchment">{t.name}</p>
          <FreeChoicesStep character={character} trait={t} />
        </div>
      ))}
    </section>
  );
}

/** Where a pick of some rating can clash, so the dots are checked at each rating (Childlike's Physical, Thin Blooded's Generation). */
const CHECKED_BY_RATING = ["attributes", "skills", "backgrounds"];

function CheckedDotGrid({
  characterId,
  category,
  barredFor = {},
  steps,
  step,
  ...props
}: { characterId: string; category: string; barredFor?: Record<string, string>; held?: Record<string, Held>; steps: Step[]; step: Step } & Parameters<typeof DotGrid>[0]) {
  const byRating = CHECKED_BY_RATING.includes(category);
  const ratings = Object.keys(props.allowed).map(Number);
  const named = useRefusals(characterId, category, !byRating).data ?? {};
  const atRating = useRatingRefusals(characterId, category, byRating ? ratings : [], byRating);
  // Barred at every rating it can be picked at: barred outright. At some: those dots only.
  const refusals: typeof named = byRating ? {} : named;
  const bars: Record<string, RatingBar[]> = {};
  if (byRating) {
    const note = (name: string, rating: number) => {
      const r = atRating[rating]![name]!;
      return { message: r.message, because: r.because };
    };
    for (const name of new Set(ratings.flatMap((r) => Object.keys(atRating[r] ?? {})))) {
      const at = ratings.filter((r) => atRating[r]?.[name]).sort((a, b) => a - b);
      if (at.length === ratings.length) {
        refusals[name] = atRating[at[0]!]![name]!;
        continue;
      }
      const groups = new Map<string, number[]>();
      for (const r of at) groups.set(note(name, r).message, [...(groups.get(note(name, r).message) ?? []), r]);
      bars[name] = [...groups].map(([message, rs]) => ({
        ratings: rs,
        note: (
          <>
            {message}
            <Because characterId={characterId} refs={note(name, rs[0]!).because} steps={steps} step={step} />
          </>
        ),
      }));
    }
  }
  const unavailable = { ...Object.fromEntries(Object.entries(refusals).map(([name, r]) => [name, r.message])), ...barredFor };
  const why = (name: string) => (refusals[name] ? <Because characterId={characterId} refs={refusals[name].because} steps={steps} step={step} /> : null);
  return <DotGrid {...props} unavailable={unavailable} why={why} barredAt={bars} />;
}

/** Change which troupe's rules the character is built by, until a troupe accepts it. */
function BuildForCharacter({ character }: { character: CharacterOut }) {
  const change = useAction((troupe_id: string | null) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/building-troupe", {
        params: { path: { character_id: character.id } },
        body: { troupe_id },
      }),
    ),
  );
  return (
    <div className="flex flex-col gap-1">
      <BuildFor value={character.building_troupe_id} onChange={(t) => change.mutate(t)} disabled={change.isPending || character.home_troupe_id !== null} />
      <ErrorText error={change.error} />
    </div>
  );
}

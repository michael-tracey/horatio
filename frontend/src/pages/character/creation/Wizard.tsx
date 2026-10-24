import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../../../api/client";
import type { CatalogueOut, CharacterOut, CreationOut, SheetOut, TraitOut } from "../../../api/types";
import { Button, Card, ErrorText, Field, Input, Loading, Notice, Select, Textarea } from "../../../components/ui";
import { useAction, useUnavailable } from "../../../hooks";
import { BuildFor } from "../BuildFor";
import { useCart } from "../cart";
import { FinishCreation } from "../CartPanel";
import { rulesTroupe } from "../rules";
import { quickPicks } from "../traitFilter";
import { DotGrid, PointsList } from "./DotGrid";
import { fieldSkills } from "../fields";
import { SetField } from "../Specializations";
import { CUSTOM_ARCHETYPE, fieldProblems, identityChoices, keyed, traitOf, type Allowed, type Picks } from "./logic";

type Step = { key: string; title: string; categories: string[]; intro?: string };

/** Wizard steps, in the order a player builds a character. Any category with
 * creation picks that no step names gets a step of its own before merits. */
const ORDER: Step[] = [
  { key: "attributes", title: "Attributes", categories: ["attributes"], intro: "Rank Physical, Social and Mental: tap 7, 5 or 3 for each. Tapping a taken rating swaps them." },
  { key: "focuses", title: "Focuses", categories: ["focus_physicals", "focus_mentals", "focus_socials"], intro: "Choose one focus for each attribute." },
  { key: "skills", title: "Skills", categories: ["skills"], intro: "Tap the dot for each skill's rating. The counters show what is left." },
  { key: "backgrounds", title: "Backgrounds", categories: ["backgrounds"] },
  { key: "disciplines", title: "Disciplines", categories: ["disciplines"], intro: "Starting disciplines are your clan's in-clan ones: one at 2, the others at 1." },
  { key: "merits", title: "Merits & flaws", categories: ["merits", "flaws"], intro: "Each comes from its own budget of points. Both are optional." },
];

function buildSteps(creation: CreationOut): Step[] {
  const present = new Set(creation.pools.map((p) => p.category));
  const known = new Set(ORDER.flatMap((s) => s.categories));
  const steps = ORDER.map((s) => ({ ...s, categories: s.categories.filter((c) => present.has(c)) })).filter((s) => s.categories.length);
  const extra = [...present]
    .filter((c) => !known.has(c))
    .map((c) => ({ key: c, title: creation.pools.find((p) => p.category === c)!.category_name, categories: [c] }));
  const merits = steps.findIndex((s) => s.key === "merits");
  steps.splice(merits === -1 ? steps.length : merits, 0, ...extra);
  return [{ key: "concept", title: "Concept", categories: [] }, ...steps, { key: "review", title: "Review", categories: [] }];
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

  const steps = buildSteps(creation.data);
  const index = Math.max(0, steps.findIndex((s) => s.key === stepKey));
  // The first step that still needs something (a vampire's Generation): no going past it.
  const needs = creation.data.needs;
  const stuck = steps.findIndex((s) => needs.some((n) => s.categories.includes(n.step)));
  const go = (i: number) => navigate(`/characters/${character.id}/create/${steps[i]!.key}`);

  return (
    <div className="grid gap-6 lg:grid-cols-[12rem_minmax(0,1fr)]">
      {/* min-w-0: without it the step list's sideways scroller widens the page on phones. */}
      <nav aria-label="Creation steps" className="min-w-0">
        <ol className="flex gap-1 overflow-x-auto lg:flex-col">
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
}: {
  character: CharacterOut;
  step: Step;
  creation: CreationOut;
  sheet: SheetOut;
  catalogue: CatalogueOut;
  onBack?: () => void;
  onNext?: () => void;
  steps: Step[];
}) {
  // Keyed by content, so a refetch that brings back the same saved picks (as the last
  // step's save does) doesn't wipe taps on this step that aren't saved yet.
  const savedKey = JSON.stringify(saved(creation));
  const { picks: before, details: savedDetail } = useMemo(() => JSON.parse(savedKey) as ReturnType<typeof saved>, [savedKey]);
  const [picks, setPicks] = useState<Record<string, Picks>>(before);
  useEffect(() => setPicks(before), [before]);
  const [details, setDetails] = useState(savedDetail);
  useEffect(() => setDetails(savedDetail), [savedDetail]);
  // A Crafts, Performance or Science with no field, or two with one field: by category, then pick.
  const needsField = fieldSkills(catalogue);
  const problems = Object.fromEntries(
    step.categories.map((c) => [c, fieldProblems(picks[c] ?? {}, details[c] ?? {}, (name) => needsField.has(name))]),
  );

  const save = useAction(async () => {
    for (const category of step.categories) {
      const mine = picks[category] ?? {};
      const detail = details[category] ?? {};
      const same =
        JSON.stringify(Object.entries(mine).sort()) === JSON.stringify(Object.entries(before[category] ?? {}).sort()) &&
        Object.keys(mine).every((key) => (detail[key] ?? "").trim() === (savedDetail[category]?.[key] ?? ""));
      if (same) continue;
      await unwrap(
        api.PUT("/api/characters/{character_id}/creation/categories/{category}", {
          params: { path: { character_id: character.id, category } },
          body: { picks: Object.entries(mine).map(([key, rating]) => ({ name: traitOf(key), rating, detail: (detail[key] ?? "").trim() })) },
        }),
      );
    }
    // What this step still needs, now that it is saved.
    const now = await unwrap(api.GET("/api/characters/{character_id}/creation", { params: { path: { character_id: character.id } } }));
    return now.needs.filter((n) => step.categories.includes(n.step));
  });
  const needs = creation.needs.filter((n) => step.categories.includes(n.step));
  // Stay on the step if saving fails (save.error shows why), and going forward
  // while the step still needs something, such as a skill's field (the notice,
  // and the row, say what). Two picks of one skill with one field cannot be saved.
  const twice = Object.values(problems).some((p) => Object.values(p).some((why) => why.twice));
  const move = (to: (() => void) | undefined, forward: boolean) => {
    if (twice) return;
    save.mutate(undefined, { onSuccess: (left) => (forward && left.length ? undefined : to?.()) });
  };

  const traitsOf = (category: string) => catalogue.traits.filter((t) => t.category === category);
  const nameOf = (category: string) => catalogue.categories.find((c) => c.key === category)?.name ?? category;
  const clan = sheet.traits.find((t) => t.category === "clan")?.name;
  const inClan = new Set([
    ...(catalogue.traits.find((t) => t.category === "clan" && t.name === clan)?.in_clan ?? []),
    ...sheet.traits.filter((t) => t.category === "extra_in_clan_disciplines").map((t) => t.name),
  ]);

  return (
    <Card title={step.title} className="min-w-0">
      {step.intro && <p className="mb-4 text-sm text-mist">{step.intro}</p>}
      {step.key === "concept" && <ConceptStep character={character} sheet={sheet} catalogue={catalogue} />}
      {step.key === "review" && <ReviewStep character={character} creation={creation} catalogue={catalogue} steps={steps} />}
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
                traits={traitsOf(category)}
                budget={pools[0].allowed}
                picks={mine}
                onChange={set}
                quick={quickPicks(traitsOf(category), sheet.traits)}
                details={details[category] ?? {}}
                onDetail={(name, value) => setDetails({ ...details, [category]: { ...details[category], [name]: value } })}
              />
            );
          }
          let traits = traitsOf(category);
          // Picks restricted to in-clan disciplines offer only those.
          if (pools.some((p) => p.restriction === "in_clan")) traits = traits.filter((t) => inClan.has(t.name));
          if (traits.length === 0 && pools.some((p) => p.restriction === "in_clan")) {
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

function ConceptStep({ character, sheet, catalogue }: { character: CharacterOut; sheet: SheetOut; catalogue: CatalogueOut }) {
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
      {clanOf(sheet) === "Caitiff" && <ExtraInClan character={character} sheet={sheet} catalogue={catalogue} />}
    </div>
  );
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

/** A Caitiff has no clan disciplines: the player picks three, from the common ones (p. 246). */
function ExtraInClan({ character, sheet, catalogue }: { character: CharacterOut; sheet: SheetOut; catalogue: CatalogueOut }) {
  const unavailable = useUnavailable(character.id, "extra_in_clan_disciplines").data ?? {};
  const held = new Set(sheet.traits.filter((t) => t.category === "extra_in_clan_disciplines").map((t) => t.name));
  const toggle = useAction((body: { name: string; on: boolean }) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/traits", {
        params: { path: { character_id: character.id } },
        body: { category: "extra_in_clan_disciplines", name: body.name, detail: "", rating: body.on ? 1 : 0, teacher: "" },
      }),
    ),
  );
  const options = catalogue.traits.filter(
    (t) => t.category === "extra_in_clan_disciplines" && (held.has(t.name) || !(t.name in unavailable)) && !t.name.includes(":"),
  );
  return (
    <fieldset className="flex flex-col gap-2 rounded-md border border-ash p-3">
      <legend className="px-1 text-sm text-parchment">In-clan disciplines ({held.size} of 3)</legend>
      <p className="text-xs text-mist">Caitiff choose their three in-clan disciplines from the common ones.</p>
      <div className="grid grid-cols-2 gap-1 sm:grid-cols-4">
        {options.map((t) => (
          <label key={t.name} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={held.has(t.name)}
              disabled={toggle.isPending || (!held.has(t.name) && held.size >= 3)}
              onChange={(e) => toggle.mutate({ name: t.name, on: e.target.checked })}
            />
            {t.name}
          </label>
        ))}
      </div>
      <ErrorText error={toggle.error} />
    </fieldset>
  );
}

function ReviewStep({
  character,
  creation,
  catalogue,
  steps,
}: {
  character: CharacterOut;
  creation: CreationOut;
  catalogue: CatalogueOut;
  steps: Step[];
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
              <SetField key={`${t.category}/${t.name}`} character={character} trait={t} />
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

/** A points list that greys out what the rules do not allow this character. */
/** A merits or flaws list whose greying follows the ticks as they change, before the step is saved. */
function CheckedPointsList({ characterId, category, ...props }: { characterId: string; category: string } & Parameters<typeof PointsList>[0]) {
  const unavailable = useUnavailable(characterId, category, true, { asIf: "picks", picks: Object.keys(props.picks).sort() });
  const barred = useUnavailable(characterId, category, true, { asIf: "empty" });
  return <PointsList {...props} unavailable={unavailable.data ?? {}} barred={barred.data} />;
}

function CheckedDotGrid({ characterId, category, ...props }: { characterId: string; category: string } & Parameters<typeof DotGrid>[0]) {
  const unavailable = useUnavailable(characterId, category);
  return <DotGrid {...props} unavailable={unavailable.data ?? {}} />;
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

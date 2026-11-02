import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../../../api/client";
import type { CatalogueOut, CharacterOut, CreationOut, SheetOut, TraitOut, TraitRefOut } from "../../../api/types";
import { useClanName } from "../../../components/ClanNames";
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
import { BACKGROUND_MERITS, FOCUS_MERITS, SKILL_MERITS, freedPicks, givenIn, takenAway, unchosenFree } from "./gifts";
import { detailNeed, fieldSkills } from "../fields";
import { SetField } from "../Specializations";
import { CUSTOM_ARCHETYPE, fieldProblems, identityChoices, keyed, spent, traitOf, type Allowed, type Picks } from "./logic";
import { FromMerits } from "./FromMerits";
import { ClanMerits } from "./ClanMerits";
import { clanMeritsLine, clanPoints, comesWithClan } from "./clanMerits";
import { EXTRA_IN_CLAN, IN_CLAN_MERITS, clanChoiceNeeded, clanChoiceOpen, inClanChoices, inClanOpen, inClanShortfalls, makesInClanChoice } from "./inClan";
import { ClanChoice, InClanPicker, MoveStartingDots } from "./InClanPicker";
import { DISCIPLINES_FROM_MERITS, INEPT, disciplinesIntro, ineptChoices, withoutDotReasons } from "./disciplines";
import { brokenChecks, listed, overBudget, stepFor, stepNotices, strayPicks, type NoticeSource, type StepNotice, type StepRef } from "./notices";
import { useHasDomitor } from "../splats";
import { pageText } from "../../troupe/bookPage";
import { DomitorPanel, DomitorSummary, useDomitor } from "../Domitor";
import { generationText } from "../../../generation";
import { domitorNeeded, dotBudget, ghoulDisciplinesIntro, savedDots } from "./ghoul";

/** A step: the categories it places picks in, and those it decides without picks. */
type Step = StepRef & { intro?: string };

/** Where cross-step notices come from (notices.ts): a step that needs a new kind adds its source here. */
const NOTICE_SOURCES: NoticeSource[] = [domitorNeeded, inClanChoices, clanChoiceNeeded, inClanShortfalls, strayPicks, overBudget, freedPicks, unchosenFree, brokenChecks];

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
  {
    key: "backgrounds",
    title: "Backgrounds",
    categories: ["backgrounds"],
    intro: "What the character has in the world: allies, contacts, money, fame and the like. Tap the dot for each one's rating; the counters show the ratings left to place.",
  },
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

/** Added to the Backgrounds intro where the rules have Generation (not a ghoul's). */
const GENERATION_INTRO =
  "Generation is a background too, and a vampire needs at least 1 dot of it to go on. It is the strength of the blood: 1 dot is the 11th generation, with 10 Blood, spending 1 a turn; each dot more holds and spends more (pp. 100-101).";

/** How long after the last tap a step saves itself. */
const AUTOSAVE_AFTER = 1000;

/** Whether a category's picks, or the fields given them, differ from those of another time. */
function differs(picks: Picks, details: Record<string, string>, otherPicks: Picks, otherDetails: Record<string, string>): boolean {
  const entries = (p: Picks) => JSON.stringify(Object.entries(p).sort());
  return entries(picks) !== entries(otherPicks) || Object.keys(picks).some((key) => (details[key] ?? "").trim() !== (otherDetails[key] ?? ""));
}

function allowedFor(creation: CreationOut, category: string): Allowed {
  return Object.fromEntries(creation.pools.filter((p) => p.category === category).map((p) => [p.rating, p.allowed]));
}

export function CreationWizard({ character }: { character: CharacterOut }) {
  const { step: stepKey = "concept" } = useParams();
  const navigate = useNavigate();
  const named = useClanName();
  const path = { params: { path: { character_id: character.id } } };
  const creation = useQuery({ queryKey: ["creation", character.id], queryFn: () => unwrap(api.GET("/api/characters/{character_id}/creation", path)) });
  const sheet = useQuery({ queryKey: ["sheet", character.id], queryFn: () => unwrap(api.GET("/api/characters/{character_id}/sheet", path)) });
  const catalogue = useQuery({
    queryKey: ["catalogue", character.splat, rulesTroupe(character)],
    queryFn: () =>
      unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: character.splat }, query: { troupe_id: rulesTroupe(character) } } })),
    staleTime: 5 * 60_000,
  });
  // A ghoul takes its clan and in-clan disciplines from its domitor, chosen on Concept.
  const hasDomitor = useHasDomitor(character.splat);
  const domitor = useDomitor(character, !!hasDomitor);

  if (character.creation_complete) return <Navigate to={`/characters/${character.id}`} replace />;
  if (creation.isPending || sheet.isPending || catalogue.isPending || hasDomitor === undefined) return <Loading />;
  if (!creation.data || !sheet.data || !catalogue.data) {
    return <ErrorText error={creation.error ?? sheet.error ?? catalogue.error} />;
  }

  const steps = buildSteps(creation.data, catalogue.data);
  const ghoul = hasDomitor ? { domitor: domitor.data !== null, linked: !!domitor.data?.character_id } : undefined;
  const notices = stepNotices({ creation: creation.data, sheet: sheet.data, steps, ghoul }, NOTICE_SOURCES);
  const index = Math.max(0, steps.findIndex((s) => s.key === stepKey));
  // The first step that still needs something (a vampire's Generation): no going past it.
  const needs = creation.data.needs;
  const stuck = steps.findIndex((s) => needs.some((n) => s.categories.includes(n.step)));
  // Said in words under the list, as a hover title never shows on a phone.
  const lockedWhy =
    stuck !== -1 && stuck < steps.length - 1
      ? `Finish ${steps[stuck]!.title} to open the steps after it: ${needs
          .filter((n) => steps[stuck]!.categories.includes(n.step))
          .map((n) => named(n.message))
          .join(" ")}`
      : null;
  const go = (i: number) => navigate(`/characters/${character.id}/create/${steps[i]!.key}`);

  return (
    <div className="grid gap-6 lg:grid-cols-[12rem_minmax(0,1fr)]">
      {/* min-w-0: without it the step list's sideways scroller widens the page on phones. */}
      <nav aria-label="Creation steps" className="min-w-0">
        <StepProgress steps={steps} index={index} stuck={stuck} />
        {/* relative: so the screen-reader-only marks past the right edge are clipped here, not left to widen the page. */}
        <StepList index={index}>
          {steps.map((s, i) => (
            <li key={s.key} data-current={i === index || undefined}>
              {stuck !== -1 && i > stuck ? (
                <span
                  aria-disabled="true"
                  aria-describedby="locked-why"
                  title={`Finish ${steps[stuck]!.title} first`}
                  className="flex cursor-not-allowed items-center gap-1 rounded px-3 py-1.5 text-sm whitespace-nowrap text-line"
                >
                  <Lock />
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
        </StepList>
        {lockedWhy && (
          <p id="locked-why" className="mt-2 flex gap-1.5 px-3 text-xs text-mist">
            <Lock />
            <span>{lockedWhy}</span>
          </p>
        )}
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
        ghoul={ghoul}
      />
    </div>
  );
}

/**
 * Where the player is, for a phone, whose step list scrolls sideways out of view:
 * "Step 2 of 8 · Attributes", over a bar of a segment a step. Steps done or here are
 * gold, those open grey, and those locked (as the line under the list says why) dark.
 */
function StepProgress({ steps, index, stuck }: { steps: Step[]; index: number; stuck: number }) {
  const locked = stuck === -1 ? 0 : steps.length - 1 - stuck;
  const where = `Step ${index + 1} of ${steps.length}`;
  return (
    <div className="mb-3 px-3 lg:hidden">
      <p className="flex items-center gap-1.5 text-sm text-mist">
        <span>
          {where} · <span className="text-parchment">{steps[index]!.title}</span>
        </span>
        {locked > 0 && (
          <span className="ml-auto flex items-center gap-1 text-xs">
            <Lock />
            {locked} locked
          </span>
        )}
      </p>
      <div
        role="progressbar"
        aria-label="Creation progress"
        aria-valuemin={1}
        aria-valuemax={steps.length}
        aria-valuenow={index + 1}
        aria-valuetext={`${where}: ${steps[index]!.title}`}
        className="mt-1.5 flex gap-1"
      >
        {steps.map((s, i) => (
          <span key={s.key} className={`h-1 flex-1 rounded-full ${i <= index ? "bg-gold" : stuck !== -1 && i > stuck ? "bg-ash" : "bg-line"}`} />
        ))}
      </div>
    </div>
  );
}

/** The steps, a column on a wide screen and a sideways scroller on a phone, kept
 * scrolled to the step the player is on. */
function StepList({ index, children }: { index: number; children: ReactNode }) {
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const ol = list.current;
    const here = ol?.querySelector<HTMLElement>("[data-current]");
    // Sideways only: scrollIntoView would move the page too.
    if (ol && here && ol.scrollWidth > ol.clientWidth) ol.scrollLeft = here.offsetLeft - (ol.clientWidth - here.offsetWidth) / 2;
  }, [index]);
  return (
    <ol ref={list} className="relative flex gap-1 overflow-x-auto lg:flex-col">
      {children}
    </ol>
  );
}

/** A small padlock, for a step not open yet. */
function Lock() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden className="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="7" width="10" height="7" rx="1.5" />
      <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
    </svg>
  );
}

/** For a ghoul: whether it has a domitor yet, and whether that one is in Horatio. */
type Ghoul = { domitor: boolean; linked: boolean };

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
  ghoul,
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
  ghoul?: Ghoul;
}) {
  const named = useClanName();
  // Keyed by content, so a refetch that brings back the same saved picks (as the last
  // step's save does) doesn't wipe taps on this step that aren't saved yet.
  const savedKey = JSON.stringify(saved(creation));
  const { picks: before, details: savedDetail } = useMemo(() => JSON.parse(savedKey) as ReturnType<typeof saved>, [savedKey]);
  const [picks, setPicks] = useState<Record<string, Picks>>(before);
  const [details, setDetails] = useState(savedDetail);
  // The picks the server last had, as loaded or as last sent. New saved picks replace a
  // category's only where nothing was tapped since: a tap made while a save is on its
  // way is kept, and saved next.
  const synced = useRef({ picks: before, details: savedDetail });
  useEffect(() => {
    const was = synced.current;
    synced.current = { picks: before, details: savedDetail };
    const untouched = (c: string) => !differs(picks[c] ?? {}, details[c] ?? {}, was.picks[c] ?? {}, was.details[c] ?? {});
    const categories = new Set([...Object.keys(picks), ...Object.keys(before)]);
    setPicks(Object.fromEntries([...categories].map((c) => [c, untouched(c) ? (before[c] ?? {}) : (picks[c] ?? {})])));
    // A field typed with a space at its end keeps it: only what was saved is trimmed.
    const typed = (c: string) =>
      Object.fromEntries(Object.entries(savedDetail[c] ?? {}).map(([key, value]) => [key, details[c]?.[key]?.trim() === value ? details[c]![key]! : value]));
    setDetails(Object.fromEntries([...categories].map((c) => [c, untouched(c) ? typed(c) : (details[c] ?? {})])));
    // Only new saved picks start this; the taps it reads are those of the same render.
  }, [before, savedDetail]);
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
  const changed = step.categories.filter((c) => differs(picks[c] ?? {}, details[c] ?? {}, before[c] ?? {}, savedDetail[c] ?? {}));
  const trimmed = (category: string) => Object.fromEntries(Object.entries(details[category] ?? {}).map(([key, value]) => [key, value.trim()]));
  const put = (category: string) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/creation/categories/{category}", {
        params: { path: { character_id: character.id, category } },
        body: { picks: Object.entries(picks[category] ?? {}).map(([key, rating]) => ({ name: traitOf(key), rating, detail: (details[category]?.[key] ?? "").trim() })) },
        // Kept going if the page is closed meanwhile.
        keepalive: true,
      }),
    );
  const client = useQueryClient();
  const [savedAt, setSavedAt] = useState<Date>();
  const save = useAction(async () => {
    const sent = changed.map((c) => [c, picks[c] ?? {}, trimmed(c)] as const);
    if (!sent.length) return needs;
    let now: CreationOut | undefined;
    for (const [category] of sent) now = await put(category);
    synced.current = {
      picks: { ...synced.current.picks, ...Object.fromEntries(sent.map(([c, p]) => [c, p])) },
      details: { ...synced.current.details, ...Object.fromEntries(sent.map(([c, , d]) => [c, d])) },
    };
    // The last save says what the step still needs. Shown at once (the notice below),
    // not once every query on the page has been asked again.
    client.setQueryData(["creation", character.id], now);
    setSavedAt(new Date());
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

  // Each step saves itself a moment after the last tap, as Concept does, and on being
  // left by any route: the step list, Back, another page, or the tab closing or hidden.
  // Two picks of one trait with one field, or none yet, wait until they differ.
  const clash = step.categories.some((c) => {
    const seen = new Set<string>();
    return Object.keys(picks[c] ?? {}).some((key) => {
      const one = `${traitOf(key)}/${(details[c]?.[key] ?? "").trim().toLowerCase()}`;
      return seen.has(one) || !seen.add(one);
    });
  });
  const draft = JSON.stringify(step.categories.map((c) => [picks[c] ?? {}, trimmed(c)])) + savedKey;
  // A draft already tried against these saved picks (refused, or saved as something
  // else) is not sent again until it or they change.
  const tried = useRef("");
  const ready = changed.length > 0 && !clash;
  const { mutate: send, isPending: saving } = save;
  useEffect(() => {
    if (!ready || saving || tried.current === draft) return;
    const timer = setTimeout(() => {
      tried.current = draft;
      send(undefined);
    }, AUTOSAVE_AFTER);
    return () => clearTimeout(timer);
  }, [ready, saving, draft, send]);
  const leaving = useRef<(how: "hidden" | "gone" | "closing") => void>(undefined);
  leaving.current = (how) => {
    const dirty = step.categories.filter((c) => differs(picks[c] ?? {}, details[c] ?? {}, synced.current.picks[c] ?? {}, synced.current.details[c] ?? {}));
    if (!dirty.length || clash) return;
    // A page being closed has no time for one save after another.
    if (how === "closing") for (const c of dirty) put(c).catch(() => undefined);
    else if (how === "gone" || !saving) send(undefined);
  };
  useEffect(() => {
    const hidden = () => document.visibilityState === "hidden" && leaving.current?.("hidden");
    const closing = () => leaving.current?.("closing");
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("pagehide", closing);
    return () => {
      document.removeEventListener("visibilitychange", hidden);
      window.removeEventListener("pagehide", closing);
      leaving.current?.("gone");
    };
  }, []);

  // Taking a merit that makes an in-clan choice (Vestiges of Greatness) saves the step at
  // once, so the choice is offered under it rather than only on Concept (#216).
  const inClanTaken =
    step.key === "merits" && !ghoul
      ? Object.keys(picks.merits ?? {})
          .map(traitOf)
          .filter((name) => !(name in (before.merits ?? {})) && catalogue.traits.some((t) => t.category === "merits" && t.name === name && makesInClanChoice(t)))
          .join("|")
      : "";
  const triedSaving = useRef("");
  useEffect(() => {
    if (!inClanTaken || inClanTaken === triedSaving.current || save.isPending || twice) return;
    triedSaving.current = inClanTaken;
    save.mutate(undefined);
  }, [inClanTaken, save, twice]);
  const heldMerit = (name: string) => sheet.traits.some((t) => t.category === "merits" && t.name === name && (t.rating ?? 0) > 0);
  const inClanUnder =
    step.key === "merits" && !ghoul
      ? (name: string) => {
          const trait = catalogue.traits.find((t) => t.category === "merits" && t.name === name);
          if (!trait || !makesInClanChoice(trait)) return null;
          return (
            <div className="mt-1 mb-2 ml-6 flex flex-col gap-2">
              {heldMerit(name) ? (
                <>
                  <InClanPicker character={character} sheet={sheet} catalogue={catalogue} />
                  <MoveStartingDots character={character} creation={creation} picks={before.disciplines ?? {}} />
                </>
              ) : (
                <p className="text-xs text-mist">{save.isPending ? "Saving, to offer its in-clan choice…" : "Save to choose its in-clan discipline."}</p>
              )}
            </div>
          );
        }
      : undefined;
  // On Disciplines, the in-clan choice while it is open, and once open, kept in view for
  // the swap's starting dots to be moved (#216).
  const inClanHere = useRef(false);
  if (step.key === "disciplines" && !ghoul && inClanOpen(sheet)) inClanHere.current = true;
  // The clan's own choice (Angelis Ater), the same way.
  const clanChoiceHere = useRef(false);
  if (step.key === "disciplines" && !ghoul && clanChoiceOpen(creation)) clanChoiceHere.current = true;
  // The steps that offer the in-clan choice themselves say so, rather than sending the player to Concept.
  const choosesHere = (step.key === "merits" && !!inClanUnder) || inClanHere.current || clanChoiceHere.current;

  const ghoulDots = ghoul && step.key === "disciplines" ? dotBudget(creation, "disciplines") : undefined;
  // The Disciplines step's budget is the pools', which Thin Blooded and Inept change.
  // Its dots left unplaced, as tapped so far: saved for later.
  const savedNote = ghoulDots && savedDots(ghoulDots.allowed - spent(picks.disciplines ?? {}));
  const hasGeneration = catalogue.traits.some((t) => t.category === "backgrounds" && t.name === "Generation");
  const intro = ghoulDots ? ghoulDisciplinesIntro(ghoulDots, ghoul!.linked) : step.key === "disciplines" ? disciplinesIntro(creation) : step.intro;
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
  // What a trait held leaves this step without (Stolen Potential: the focus in its attribute).
  const away = takenAway(creation, catalogue, ORDER.find((s) => s.key === step.key)?.categories.filter((c) => !step.categories.includes(c)) ?? []);

  return (
    <Card title={step.title} className="min-w-0">
      {intro && <p className="mb-4 text-sm text-mist">{intro}</p>}
      {step.key === "backgrounds" && hasGeneration && <p className="mb-4 text-sm text-mist">{GENERATION_INTRO}</p>}
      {step.key !== "review" && <StepNotices character={character} notices={here} step={step} steps={steps} choosesHere={choosesHere} />}
      {away.length > 0 && (
        <div className="mb-6 flex flex-col gap-2">
          {away.map((why) => (
            <Notice key={why}>{named(why)}</Notice>
          ))}
        </div>
      )}
      {step.key === "concept" && <ConceptStep character={character} creation={creation} sheet={sheet} catalogue={catalogue} ghoul={ghoul} />}
      {step.key === "review" && (
        <ReviewStep character={character} creation={creation} sheet={sheet} catalogue={catalogue} steps={steps} notices={notices} ghoul={ghoul} />
      )}
      {step.key === "disciplines" && !ghoul && (
        <div className="mb-6 flex flex-col gap-2 empty:hidden">
          {clanChoiceHere.current && <ClanChoice character={character} creation={creation} catalogue={catalogue} />}
          {inClanHere.current && <InClanPicker character={character} sheet={sheet} catalogue={catalogue} />}
          <MoveStartingDots character={character} creation={creation} picks={picks.disciplines ?? {}} />
        </div>
      )}
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
      {/* Not held while saving: a tap made meanwhile is kept, and saved next. */}
      <fieldset className="flex min-w-0 flex-col gap-8">
        {step.categories.map((category) => {
          const pools = creation.pools.filter((p) => p.category === category);
          const mine = picks[category] ?? {};
          const set = (next: Picks) => setPicks({ ...picks, [category]: next });
          // Picks from one budget of dots (a ghoul's disciplines).
          const budget = dotBudget(creation, category);
          if (pools[0]?.kind === "points" && !budget) {
            // The merits the clan gives are the clan's, not picks (#313).
            const clan = category === "merits" ? creation.clan_merits : [];
            return (
              <CheckedPointsList
                key={category}
                characterId={character.id}
                category={category}
                title={nameOf(category)}
                traits={narrowed(category, traitsOf(category)).filter((t) => category !== "merits" || !comesWithClan(t.name, creation))}
                budget={pools[0].allowed}
                given={<ClanMerits character={character} merits={clan} catalogue={catalogue} />}
                givenPoints={clanPoints({ clan_merits: clan })}
                picks={mine}
                onChange={set}
                quick={quickPicks(traitsOf(category), sheet.traits)}
                details={details[category] ?? {}}
                onDetail={(name, value) => setDetails({ ...details, [category]: { ...details[category], [name]: value } })}
                fields={fieldSkills(catalogue)}
                steps={steps}
                step={step}
                under={category === "merits" ? inClanUnder : undefined}
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
                Starting {nameOf(category).toLowerCase()} must be in-clan. Choose {ghoul ? "the domitor" : "a clan"} on the Concept step first.
              </Notice>
            );
          }
          const maxRating = catalogue.categories.find((c) => c.key === category)?.max_rating ?? budget?.allowed ?? 0;
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
              budget={budget && { dots: budget.allowed, max: Math.min(maxRating, budget.allowed) }}
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
      {savedNote && <p className="mt-4 text-sm text-mist">{savedNote}</p>}
      {needs.length > 0 && (
        <div className="mt-6">
          <Notice>Before moving on: {needs.map((n) => named(n.message)).join(" ")}</Notice>
        </div>
      )}
      <ErrorText error={save.error} />
      <div className="mt-6 flex items-center justify-between gap-2 border-t border-ash pt-4">
        <Button variant="secondary" disabled={!onBack || save.isPending} onClick={() => move(onBack, false)}>
          Back
        </Button>
        {step.categories.length > 0 && (
          <p className="ml-auto text-xs text-mist" aria-live="polite">
            {save.isPending ? "Saving…" : savedAt && !changed.length ? `Saved ${savedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""}
          </p>
        )}
        {onNext && (
          <Button disabled={save.isPending} onClick={() => move(onNext, true)}>
            Save and continue
          </Button>
        )}
      </div>
    </Card>
  );
}

function ConceptStep({
  character,
  creation,
  sheet,
  catalogue,
  ghoul,
}: {
  character: CharacterOut;
  creation: CreationOut;
  sheet: SheetOut;
  catalogue: CatalogueOut;
  ghoul?: Ghoul;
}) {
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
  const named = useClanName();
  const identity = identityChoices(catalogue, sheet);
  // Clan first, the biggest choice, with what it means under it. A ghoul's clan is its
  // domitor's, set with the domitor.
  const clanChoice = ghoul ? undefined : identity.find((c) => c.key === "clan");
  const others = identity.filter((c) => c.key !== "clan");
  const clan = clanOf(sheet);
  const field = (c: (typeof identity)[number]) => (
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
            <option key={t.name} value={t.name}>
              {named(t.name)}
            </option>
          ))}
      </Select>
    </Field>
  );
  // Open from the start once one of its merits is taken, so it isn't hidden.
  const meritTaken = FROM_MERITS.concept!.some((m) => sheet.traits.some((t) => t.category === m.category && t.name === m.name && (t.rating ?? 0) > 0));
  return (
    <div className="flex flex-col gap-4">
      {ghoul ? (
        <>
          <p className="text-sm text-mist">
            Who is {character.name}? The domitor matters most: a ghoul takes its domitor's clan and bloodline, and its in-clan disciplines.
          </p>
          <section aria-label="Domitor" className="flex flex-col gap-2">
            <h3 className="text-base text-gold">Domitor</h3>
            <DomitorPanel character={character} sheet={sheet} catalogue={catalogue} canChange openWhenNone />
          </section>
          {clan && <InClanNow creation={creation} />}
        </>
      ) : (
        <p className="text-sm text-mist">Who is {character.name}? Clan matters most: it decides which disciplines are in-clan.</p>
      )}
      {clanChoice && field(clanChoice)}
      {clan && !ghoul && <ClanCard clan={clan} creation={creation} catalogue={catalogue} />}
      {clan && !ghoul && <ClanChoice character={character} creation={creation} catalogue={catalogue} />}
      {clan && !ghoul && <InClanPicker character={character} sheet={sheet} catalogue={catalogue} />}
      <div className="grid gap-3 sm:grid-cols-2">{others.map(field)}</div>
      <ErrorText error={choose.error} />
      {(makingOwn || sheet.traits.some((t) => t.category === "archetype" && t.name === CUSTOM_ARCHETYPE)) && (
        <OwnArchetype character={character} sheet={sheet} onSaved={() => setMakingOwn(false)} />
      )}
      <BuildForCharacter character={character} />
      {clan && !ghoul && (
        <details open={meritTaken}>
          <summary className="cursor-pointer py-1 text-sm text-gold pointer-coarse:py-2.5">Optional: in-clan disciplines from merits (costs merit points)</summary>
          <div className="mt-2">
            <FromMerits character={character} creation={creation} sheet={sheet} catalogue={catalogue} traits={FROM_MERITS.concept!} />
          </div>
        </details>
      )}
    </div>
  );
}

/** What the clan chosen means: its in-clan disciplines (as they are now, with any
 * merit's change), its weakness from the rules data with the book's page, and any
 * merit it takes. */
function ClanCard({ clan, creation, catalogue }: { clan: string; creation: CreationOut; catalogue: CatalogueOut }) {
  const about = catalogue.traits.find((t) => t.category === "clan" && t.name === clan);
  const merits = clanMeritsLine(creation);
  const named = useClanName();
  return (
    <section aria-label={`About ${named(clan)}`} className="flex flex-col gap-1.5 rounded-md border border-ash bg-night/40 p-3 text-sm">
      <InClanNow creation={creation} />
      {about?.weakness && (
        <p className="text-mist">
          <span className="text-parchment">Weakness:</span> {named(about.weakness)}
          {about.weakness_page && <span className="text-gold"> ({pageText(about.weakness_page)})</span>}
        </p>
      )}
      {merits && <p className="text-mist">{named(merits)}</p>}
    </section>
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
  sheet,
  catalogue,
  steps,
  notices,
  ghoul,
}: {
  character: CharacterOut;
  creation: CreationOut;
  sheet: SheetOut;
  catalogue: CatalogueOut;
  steps: Step[];
  notices: StepNotice[];
  ghoul?: Ghoul;
}) {
  const navigate = useNavigate();
  const shown = useClanName();
  const domitor = useDomitor(character, !!ghoul);
  // An in-clan choice still to make (Vestiges of Greatness) is made here, not only on Concept (#216).
  const [choosing, setChoosing] = useState(false);
  // A ghoul's discipline dots left unplaced: saved for later.
  const ghoulDots = ghoul && dotBudget(creation, "disciplines");
  const savedNote = ghoulDots && savedDots(ghoulDots.allowed - ghoulDots.used);
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
      {domitor.data && (
        <section aria-label="Domitor" className="flex flex-col gap-1">
          <h3 className="text-sm text-gold">Domitor</h3>
          <DomitorSummary domitor={domitor.data} />
        </section>
      )}
      <CharacterSummary character={character} creation={creation} sheet={sheet} catalogue={catalogue} ghoul={ghoul} />
      {open.length > 0 && (
        <section aria-label="Picks left" className="flex flex-col gap-1">
          <h3 className="text-sm text-gold">Picks left</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {open.map((p) => {
              const step = stepFor(p.category);
              return (
                <li key={`${p.category}/${p.rating}`} className="flex gap-2">
                  <span aria-hidden className="text-blood-bright">
                    •
                  </span>
                  <span>
                    {p.category_name} at {p.rating}: {p.remaining} left.
                    {step && (
                      <>
                        {" "}
                        <Link className="text-gold underline" to={`/characters/${character.id}/create/${step.key}`}>
                          Go to {step.title}
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
                    {shown(n.message)}
                    {at && (
                      <>
                        {" "}
                        <Link className="text-gold underline" to={`/characters/${character.id}/create/${at.key}`}>
                          Go to {at.title}
                        </Link>
                      </>
                    )}
                    {n.inClan && !choosing && !ghoul && (
                      <>
                        {" "}
                        <Button variant="secondary" className="ml-1 px-2 py-0.5 text-xs" onClick={() => setChoosing(true)}>
                          Choose here
                        </Button>
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}
      {choosing && !ghoul && (
        <section aria-label="In-clan choice" className="flex flex-col gap-2">
          <ClanChoice character={character} creation={creation} catalogue={catalogue} />
          <InClanPicker character={character} sheet={sheet} catalogue={catalogue} />
        </section>
      )}
      {!ghoul && <MoveStartingDots character={character} creation={creation} picks={saved(creation).picks.disciplines ?? {}} />}
      {creation.path_starts.length > 0 && (
        <section aria-label="Morality" className="flex flex-col gap-1">
          <h3 className="text-sm text-gold">Morality</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {creation.path_starts.map((s) => (
              <li key={`${s.category}/${s.name}`}>
                {shown(listed(s.because.map((b) => b.name!)))}: your path starts at {s.rating}
                {s.page ? ` (${pageText(s.page)})` : ""}.
              </li>
            ))}
          </ul>
        </section>
      )}
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
      {savedNote && <p className="text-sm text-mist">{savedNote}</p>}
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
        disabled={open.length > 0 || unfielded.length > 0 || (!!ghoul && !ghoul.domitor)}
        className="self-start"
        onFinished={() => navigate(`/characters/${character.id}`)}
      >
        Finish creation
      </FinishCreation>
    </div>
  );
}

/** Which focus category goes with each attribute. */
const FOCUSES: Record<string, string> = { Physical: "focus_physicals", Social: "focus_socials", Mental: "focus_mentals" };

/** How many skills the summary names; the rest are counted. */
const TOP_SKILLS = 5;

/**
 * The character so far, for the Review step: clan and the other choices, attributes
 * with their focuses, the top skills, disciplines, backgrounds, and merits and flaws
 * with their points. From the sheet, so what merits give counts too.
 */
function CharacterSummary({
  character,
  creation,
  sheet,
  catalogue,
  ghoul,
}: {
  character: CharacterOut;
  creation: CreationOut;
  sheet: SheetOut;
  catalogue: CatalogueOut;
  ghoul?: Ghoul;
}) {
  const shown = useClanName();
  const named = (t: { name: string; detail: string }) => (t.detail ? `${t.name}: ${t.detail}` : t.name);
  const held = (category: string) =>
    sheet.traits.filter((t) => t.category === category && (t.rating ?? 0) > 0).sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0) || a.name.localeCompare(b.name));
  const rated = (category: string) => held(category).map((t) => `${named(t)} ${t.rating}`);
  const has = (category: string) => creation.pools.some((p) => p.category === category);
  const rows: [string, string][] = [];

  // A ghoul's clan is its domitor's, shown above.
  for (const c of identityChoices(catalogue, sheet).filter((c) => !ghoul || c.key !== "clan")) {
    const chosen = sheet.traits.find((t) => t.category === c.key);
    const name = chosen?.name === CUSTOM_ARCHETYPE ? chosen.detail || chosen.name : chosen?.name;
    const inClan = c.key === "clan" ? creation.pools.find((p) => p.restriction === "in_clan")?.options : undefined;
    rows.push([c.name, name ? (inClan?.length ? `${name}. In-clan: ${listed(inClan)}.` : name) : "Not chosen yet"]);
  }
  if (has("attributes")) {
    const focuses = (attribute: string) => sheet.traits.filter((t) => t.category === FOCUSES[attribute]).map(named);
    rows.push(["Attributes", held("attributes").map((t) => `${t.name} ${t.rating}${focuses(t.name).length ? ` (${focuses(t.name).join(", ")})` : ""}`).join(", ")]);
  }
  if (has("skills")) {
    const skills = rated("skills");
    const more = skills.length - TOP_SKILLS;
    rows.push(["Top skills", `${skills.slice(0, TOP_SKILLS).join(", ")}${more > 0 ? `, and ${more} more` : ""}`]);
  }
  if (has("disciplines")) {
    const budget = ghoul && dotBudget(creation, "disciplines");
    const dotsPlaced = budget ? ` (${budget.used} of ${budget.allowed} dots placed${budget.remaining > 0 ? `, ${budget.remaining} saved for later` : ""})` : "";
    rows.push(["Disciplines", rated("disciplines").join(", ") + dotsPlaced]);
  }
  if (has("backgrounds")) rows.push(["Backgrounds", held("backgrounds").map((t) => (t.name === "Generation" ? generationText(t.rating!) : `${named(t)} ${t.rating}`)).join(", ")]);
  // Merits and flaws as their points are spent: those the clan takes, then those picked.
  for (const p of ["merits", "flaws"].flatMap((c) => creation.pools.filter((p) => p.kind === "points" && p.category === c))) {
    const names = [...(p.category === "merits" ? creation.clan_merits.map(named) : []), ...p.traits.map(named)];
    rows.push([p.category_name, `${names.join(", ") || "None"} (${p.used} of ${p.allowed} points)`]);
  }

  return (
    <section aria-label="Summary" className="flex flex-col gap-2">
      <h3 className="text-sm text-gold">{character.name} so far</h3>
      <dl className="grid gap-x-4 gap-y-1.5 text-sm sm:grid-cols-[9rem_minmax(0,1fr)]">
        {rows.map(([label, value]) => (
          <Fragment key={label}>
            <dt className="text-mist">{label}</dt>
            <dd className="mb-1.5 sm:mb-0">{shown(value) || "None yet"}</dd>
          </Fragment>
        ))}
      </dl>
    </section>
  );
}

/** This step's cross-step notices, each linking to where it is put right. */
function StepNotices({
  character,
  notices,
  step,
  steps,
  choosesHere,
}: {
  character: CharacterOut;
  notices: StepNotice[];
  step: Step;
  steps: Step[];
  /** This step offers the in-clan choice itself (Merits, under the merit; Disciplines, at the top). */
  choosesHere?: boolean;
}) {
  const named = useClanName();
  if (!notices.length) return null;
  return (
    <div aria-label="Changed by other steps" role="group" className="mb-6 flex flex-col gap-2">
      {notices.map((n) => {
        const here = choosesHere && n.inClan;
        const at = n.fix !== step.key && !here ? steps.find((s) => s.key === n.fix) : undefined;
        return (
          <Notice key={n.key}>
            {named(n.message)}
            {here && ` Choose it ${step.key === "merits" ? "under the merit, below" : "below"}.`}
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
  const named = useClanName();
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
        Refused while you {refs.every((t) => t.category === "clan") ? "are" : "have"} {named(listed(refs.map((t) => t.name!)))} (
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
  const named = useClanName();
  if (!merits.length) return null;
  return (
    <section aria-label="Free traits to choose" className="mb-6 flex flex-col gap-3 rounded-md border border-ash p-3">
      <h3 className="text-sm text-parchment">Free traits to choose</h3>
      {merits.map((t) => (
        <div key={`${t.category}/${t.name}/${t.detail}`} className="flex flex-col gap-1.5">
          <p className="text-sm text-parchment">{named(t.name)}</p>
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
  // Dots from a budget (a ghoul's disciplines) are checked at each rating too, each
  // alone: against its domitor's, while the budget keeps the total.
  const byRating = CHECKED_BY_RATING.includes(category) || !!props.budget;
  const ratings = props.budget ? Array.from({ length: props.budget.max }, (_, i) => i + 1) : Object.keys(props.allowed).map(Number);
  const named = useRefusals(characterId, category, !byRating).data ?? {};
  const atRating = useRatingRefusals(characterId, category, byRating ? ratings : [], byRating, props.budget ? "empty" : undefined);
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
      <BuildFor value={character.building_troupe_id} onChange={(t) => change.mutate(t)} disabled={change.isPending || character.home_troupe_id !== null} splat={character.splat} />
      <ErrorText error={change.error} />
    </div>
  );
}

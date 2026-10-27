import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../api/client";
import type { PoolModifier, PrintedSheet, TestPool } from "../api/types";
import { Pips } from "../components/ui";
import { useDates } from "../dates";
import { HEALTH_RULE, healthRows } from "../health";
import { DEFAULT_PREFERENCES, useMe, usePreferences } from "../hooks";
import { PAPERS, pageRule } from "../paper";
import { choiceName } from "./character/creation/logic";
import { backText, retainerName, retainerSource } from "./character/retainers";
import { NO_WILLPOWER, poolLine } from "./play/retainerPools";
import { changing, damageShort, total } from "./play/pools";
import { printedRatings } from "../ratings";
import { bracketed, fitsInline, specialtiesByParent, specialtyName } from "./printSpecialties";
import { factsText, kindText, playText } from "./troupe/equipment";

type Trait = PrintedSheet["traits"][number];

/**
 * A character sheet laid out for paper, in the order of the official BNS sheet:
 * identity, attributes with focuses, skills, then backgrounds / disciplines /
 * merits and flaws, then blood / willpower / morality, then health and status.
 * Black on white, sized for the person's paper (US Letter or A4) and fitting one
 * page of it, and readable on screen before printing.
 */
export function PrintPage() {
  const { characterId = "" } = useParams();
  const [params] = useSearchParams();
  const sheet = useQuery({
    queryKey: ["print", characterId, params.toString()],
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_id}/print", {
          params: {
            path: { character_id: characterId },
            query: { troupe_id: params.get("troupe") ?? undefined },
          },
        }),
      ),
  });

  const pips = usePrintedPips();
  if (sheet.isPending || pips === undefined) return <p className="p-8 text-black">Loading…</p>;
  if (sheet.error) return <p className="p-8 text-black">{sheet.error.message}</p>;
  return (
    <AsPips.Provider value={pips}>
      <PrintShell back={`/characters/${characterId}`}>
        <Sheet sheet={sheet.data} />
      </PrintShell>
    </AsPips.Provider>
  );
}

/**
 * Several of a troupe's sheets in one document, each starting on a new page:
 * those named in `?characters=`, in that order, or every character in the troupe.
 */
export function TroupePrintPage() {
  const { troupeId = "" } = useParams();
  const [params] = useSearchParams();
  const ids = params.get("characters")?.split(",").filter(Boolean);
  const sheets = useQuery({
    queryKey: ["print-troupe", troupeId, params.toString()],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/print", { params: { path: { troupe_id: troupeId }, query: { characters: ids } } })),
  });

  const pips = usePrintedPips();
  if (sheets.isPending || pips === undefined) return <p className="p-8 text-black">Loading…</p>;
  if (sheets.error) return <p className="p-8 text-black">{sheets.error.message}</p>;
  return (
    <AsPips.Provider value={pips}>
      <PrintShell back={`/troupes/${troupeId}/characters`} count={sheets.data.length}>
        {sheets.data.map((sheet, i) => (
          <div key={i} className={i > 0 ? "mt-6 break-before-page print:mt-0" : ""}>
            <Sheet sheet={sheet} />
          </div>
        ))}
      </PrintShell>
    </AsPips.Provider>
  );
}

/** The grey desk the paper sits on, with Back and Print above it; only the paper
 * prints, on the person's paper size. Back is a link to where the sheets came
 * from, since they often open in a tab of their own, with no history to go back
 * through. */
function PrintShell({ back, count, children }: { back: string; count?: number; children: ReactNode }) {
  const paper = usePreferences().paper;
  return (
    <div className="min-h-screen bg-neutral-200 py-6 text-black print:min-h-0 print:bg-white print:py-0">
      <style>{pageRule(paper, "0.45in")}</style>
      <div className="mx-auto mb-4 flex items-center justify-between gap-4 px-4 print:hidden" style={{ maxWidth: `${PAPERS[paper].width}in` }}>
        <Link to={back} className="text-sm underline">
          ← Back
        </Link>
        {count !== undefined && <span className="text-sm">{count === 1 ? "1 sheet" : `${count} sheets`}</span>}
        <span className="flex items-center gap-3">
          <span className="text-sm text-neutral-600">For {PAPERS[paper].name}</span>
          <button onClick={() => window.print()} className="rounded bg-black px-4 py-1.5 text-sm text-white">
            Print
          </button>
        </span>
      </div>
      {children}
    </div>
  );
}

function by(traits: Trait[], ...categories: string[]) {
  return traits.filter((t) => categories.includes(t.category));
}

function one(traits: Trait[], category: string): string {
  const found = traits.find((t) => t.category === category);
  return found ? choiceName(found) : "";
}

function rating(traits: Trait[], category: string, name: string): number {
  return traits.find((t) => t.category === category && t.name === name)?.rating ?? 0;
}

function label(t: Trait) {
  if (t.specializes) return specialtyName(t);
  return t.detail ? `${t.name}: ${t.detail}` : t.name;
}

/** Whether ratings print as pips, like the paper sheet, or as numbers, which take
 * less room: as the person's setting shows them, unless `?ratings=pips` or
 * `?ratings=numbers` asks for the other way this once. */
const AsPips = createContext(false);

/** Whether to print pips; undefined until the person's settings have loaded, so
 * the sheet never prints one way and then changes. */
function usePrintedPips(): boolean | undefined {
  const [params] = useSearchParams();
  const me = useMe();
  if (me.isPending) return undefined;
  return printedRatings(params.get("ratings"), (me.data?.preferences ?? DEFAULT_PREFERENCES).ratings) === "pips";
}

/** A rating: a number, or filled and empty pips, five to a group, like the paper sheet. */
function Dots({ value, of = 5 }: { value: number; of?: number }) {
  const pips = useContext(AsPips);
  if (!pips) {
    return (
      <span className="text-[11px] font-semibold whitespace-nowrap tabular-nums" aria-label={`${value} dots`}>
        {value}
      </span>
    );
  }
  return <Pips value={value} of={of} className="text-[11px]" />;
}

/** Boxes to tick in play: blood, willpower, health. */
function Boxes({ count, numbered = false, label, className = "" }: { count: number; numbered?: boolean; label?: string; className?: string }) {
  return (
    <span className={`inline-flex flex-wrap gap-0.5 ${className}`} role={label ? "img" : undefined} aria-label={label}>
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className="grid h-4 w-4 place-items-center border border-black text-[8px] leading-none">
          {numbered ? i + 1 : ""}
        </span>
      ))}
    </span>
  );
}

function Section({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={`break-inside-avoid ${className}`}>
      <h2 className="mb-1 border-b-2 border-black text-center font-display text-sm tracking-widest uppercase">{title}</h2>
      {children}
    </section>
  );
}

/**
 * Traits with their dots, a skill or background's specialisations in brackets
 * after it: on its line when they fit, else on a smaller line under it.
 */
function TraitList({
  traits,
  empty = 3,
  specialties = () => [],
  identities = [],
}: {
  traits: Trait[];
  empty?: number;
  specialties?: (t: Trait) => string[];
  /** What each Alternate Identity's rating means, under its row. */
  identities?: PrintedSheet["identities"];
}) {
  const blanks = Math.max(0, empty - traits.length);
  const identityOf = (name: string) => identities.find((i) => i.name === name);
  return (
    <ul className="text-[11px] leading-5">
      {traits.map((t) => {
        const brackets = bracketed(specialties(t));
        const inline = fitsInline(label(t), brackets);
        return (
          <li key={`${t.category}/${t.name}/${t.detail}`} className="border-b border-dotted border-neutral-400">
            <div className="flex items-baseline justify-between gap-2">
              <span className="min-w-0">
                {label(t)}
                {brackets && inline && ` ${brackets}`}
                {t.pending_from !== null && <em className="ml-1 text-neutral-500">(awaiting approval from {t.pending_from})</em>}
                {t.house && <em className="ml-1 text-neutral-500">★ {t.house}</em>}
              </span>
              {t.rating !== null && t.specializes === null && <Dots value={t.rating} />}
            </div>
            {brackets && !inline && <p className="pb-0.5 pl-3 text-[9px] leading-3">{brackets}</p>}
            {t.category === "backgrounds" && t.name === "Alternate Identity" && identityOf(t.detail) && (
              <p className="pb-0.5 pl-3 text-[9px] leading-3">
                {identityOf(t.detail)!.line}
                {identityOf(t.detail)!.accepted_by && ` Accepted by ${identityOf(t.detail)!.accepted_by}.`}
              </p>
            )}
          </li>
        );
      })}
      {Array.from({ length: blanks }, (_, i) => (
        <li key={`blank${i}`} className="h-5 border-b border-dotted border-neutral-400" />
      ))}
    </ul>
  );
}

/** One Retainer as the NPC it is (MET: VtM core p. 105), with boxes for its health and Blood. */
function PrintedRetainer({ retainer: r }: { retainer: PrintedSheet["retainers"][number] }) {
  const source = retainerSource(r);
  const dates = useDates();
  return (
    <article className="break-inside-avoid text-[10px] leading-4" aria-label={`Retainer: ${retainerName(r)}`}>
      <p className="border-b border-dotted border-neutral-400 text-[11px]">
        <strong>{retainerName(r)}</strong> · Retainer {r.dots}
        {r.ghoul && " · ghoul"}
        {source && ` · ${source}`}
        {r.lost && ` · ${r.lost}`}
      </p>
      {r.description && <p className="text-neutral-600">{r.description}</p>}
      {backText(r, dates.date) && <p>{backText(r, dates.date)}</p>}
      <p>{poolLine(r)}</p>
      {r.discipline && (
        <p>
          {r.discipline} to {r.dots}: {r.powers.map((p) => p.name).join(", ")}
        </p>
      )}
      <p className="flex flex-wrap items-center gap-x-1">
        Health <Boxes count={r.health} label={`${retainerName(r)}: ${r.health} health levels`} />
      </p>
      {r.blood > 0 && (
        <p className="flex flex-wrap items-center gap-x-1">
          Blood <Boxes count={r.blood} /> <span className="text-neutral-600">1 a round; and 5 mortal Blood it cannot spend</span>
        </p>
      )}
      <p className="text-neutral-600">{NO_WILLPOWER}</p>
    </article>
  );
}

/** One item of equipment: what it is, its facts, and what each quality and special effect does at the table. */
function PrintedItem({ item }: { item: PrintedSheet["equipment"][number] }) {
  const facts = factsText(item.facts);
  return (
    <li className="break-inside-avoid border-b border-dotted border-neutral-400 py-0.5">
      <p className="text-[11px]">
        <strong>{item.name}</strong> · {kindText(undefined, item)}
        {facts && ` · ${facts}`}
      </p>
      {item.qualities.length > 0 && <p>{item.qualities.map(playText).join("; ")}</p>}
      {item.effects.map((e) => (
        <p key={e.name}>
          ★ {e.name}: {e.effect}
        </p>
      ))}
    </li>
  );
}

const SHOWN_ELSEWHERE = new Set([
  "clan", "archetype", "sect", "faction", "attributes",
  "focus_physicals", "focus_mentals", "focus_socials", "skills", "backgrounds",
  "disciplines", "merits", "flaws", "paths", "health_levels", "willpower_sources", "status_traits",
]);

/** The modifiers the player has switched on that change a pool, printed beside it: "(+2 Fame)". */
function Changes({ pool, modifiers }: { pool: TestPool; modifiers: PoolModifier[] }) {
  const found = changing(pool, modifiers);
  if (found.length === 0) return null;
  return <em className="ml-1 text-neutral-600">({found.map((m) => `${m.amount < 0 ? "−" : "+"}${Math.abs(m.amount)} ${m.label}`).join(", ")})</em>;
}

function Sheet({ sheet }: { sheet: PrintedSheet }) {
  const paper = usePreferences().paper;
  const dates = useDates();
  const t = sheet.traits;
  // The server works Blood out (by Generation, or a ghoul's vitae and human Blood).
  const blood = sheet.blood;
  const willpower = rating(t, "willpower_sources", "Willpower");
  const path = by(t, "paths")[0];
  const physical = rating(t, "attributes", "Physical");
  const mental = rating(t, "attributes", "Mental");
  const initiative = sheet.pools.find((p) => p.key === "initiative");
  const skills = by(t, "skills").sort((a, b) => a.name.localeCompare(b.name));
  const third = Math.ceil(skills.length / 3);
  // Specialisations print after their skill or background; only any whose parent
  // is missing keep a section of their own.
  const specialties = specialtiesByParent(t);
  const others = t.filter((x) => !SHOWN_ELSEWHERE.has(x.category) && (x.specializes === null || specialties.orphans.includes(x)));
  const otherGroups = new Map<string, Trait[]>();
  for (const x of others) otherGroups.set(x.category_name, [...(otherGroups.get(x.category_name) ?? []), x]);

  return (
    <article
      className="mx-auto flex flex-col gap-3 bg-white p-[0.45in] font-serif shadow print:p-0 print:shadow-none"
      style={{ maxWidth: `${PAPERS[paper].width}in` }}
    >
      <header className="grid grid-cols-[1fr_auto] items-start gap-4 border-b-2 border-black pb-2">
        <dl className="grid grid-cols-[auto_1fr_auto_1fr] gap-x-2 text-[12px]">
          <dt className="font-bold">Character</dt>
          <dd className="border-b border-black">{sheet.character_name}</dd>
          <dt className="font-bold">Player</dt>
          <dd className="border-b border-black">{sheet.player_name}</dd>
          <dt className="font-bold">Clan</dt>
          <dd className="border-b border-black">
            {one(t, "clan")}
            {sheet.domitor && <span className="text-[10px]"> (domitor {sheet.domitor})</span>}
          </dd>
          <dt className="font-bold">Archetype</dt>
          <dd className="border-b border-black">{one(t, "archetype")}</dd>
          <dt className="font-bold">Sect</dt>
          <dd className="border-b border-black">{one(t, "sect")}</dd>
          <dt className="font-bold">Title</dt>
          <dd className="border-b border-black">{sheet.titles.join(", ")}</dd>
        </dl>
        <div className="flex items-start gap-3 text-right">
          <div>
            <p className="font-display text-2xl tracking-widest uppercase">{sheet.splat}</p>
            <p className="flex items-center justify-end gap-1 text-[10px]">
              {sheet.troupe_portrait && <img src={`${sheet.troupe_portrait}/48.webp`} alt="" className="h-[0.2in] w-[0.2in] rounded-full border border-black object-cover" />}
              {sheet.kind === "npc"
                ? `NPC of ${sheet.troupe_name}`
                : sheet.home
                  ? `Home troupe: ${sheet.troupe_name}`
                  : sheet.troupe_name
                    ? `Visiting ${sheet.troupe_name}`
                    : "No home troupe yet"}
            </p>
            {sheet.diablerie.length > 0 && <p className="text-[10px]">Diablerie: {sheet.diablerie.map((d) => dates.day(d)).join(", ")}</p>}
          </div>
          {sheet.picture && <img src={`${sheet.picture}/128.webp`} alt="" className="h-[0.8in] w-[0.8in] rounded-full border border-black object-cover" />}
        </div>
      </header>

      <Section title="Attributes">
        <div className="grid grid-cols-3 gap-4 text-[12px]">
          {(
            [
              ["Physical", "focus_physicals"],
              ["Social", "focus_socials"],
              ["Mental", "focus_mentals"],
            ] as const
          ).map(([name, focus]) => (
            <div key={name} className="flex items-baseline justify-between gap-2">
              {/* Focuses in brackets, like skills' specialties: "Physical (Dexterity, Stamina)". */}
              <span>
                <span className="font-bold">{name}</span> {bracketed(by(t, focus).map((f) => f.name))}
              </span>
              <span className="font-bold">
                <Dots value={rating(t, "attributes", name)} of={10} />
              </span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Skills">
        <div className="grid grid-cols-3 gap-x-4">
          {[0, 1, 2].map((col) => (
            <TraitList key={col} traits={skills.slice(col * third, (col + 1) * third)} empty={col === 2 ? 2 : 0} specialties={specialties.of} />
          ))}
        </div>
      </Section>

      <div className="grid grid-cols-3 gap-4">
        <Section title="Backgrounds">
          <TraitList traits={by(t, "backgrounds")} empty={4} specialties={specialties.of} identities={sheet.identities} />
        </Section>
        <Section title="Disciplines">
          <TraitList traits={by(t, "disciplines")} empty={4} />
        </Section>
        <Section title="Merits & Flaws">
          <TraitList traits={by(t, "merits", "flaws")} empty={4} />
        </Section>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Section title="Blood">
          {!blood.pool ? (
            <>
              <p className="mb-1 text-center text-[10px]">
                {blood.most} blood · {blood.per_turn} per turn
              </p>
              <div className="flex justify-center">
                <Boxes count={blood.most} />
              </div>
            </>
          ) : (
            // A ghoul's pool (MET: VtM core p. 297): vitae to spend, the rest human Blood.
            <>
              <p className="mb-1 text-center text-[10px]">
                Vitae: up to {blood.most} · {blood.per_turn} per turn
              </p>
              <div className="flex justify-center">
                <Boxes count={blood.most} label={`Vitae: ${blood.most} boxes`} />
              </div>
              <p className="mt-1 mb-1 text-center text-[10px]">Human Blood: can't be spent</p>
              <div className="flex justify-center">
                <Boxes count={blood.pool - blood.most} label={`Human Blood: ${blood.pool - blood.most} boxes`} />
              </div>
            </>
          )}
        </Section>
        <Section title="Willpower">
          <div className="flex justify-center">
            <Boxes count={willpower} numbered />
          </div>
        </Section>
        <Section title="Morality">
          <p className="mb-1 text-center text-[11px]">{path?.name ?? "—"}</p>
          <div className="flex justify-center">
            <Boxes count={path?.rating ?? 0} numbered />
          </div>
        </Section>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Section title="Health Levels">
          <p className="mb-1 text-center text-[10px]">{HEALTH_RULE}</p>
          <ul className="text-[12px] leading-6">
            {healthRows(t).map((h) => (
              <li key={h.name} className="flex flex-wrap items-center justify-between gap-x-2">
                {h.name} <Boxes count={h.boxes} className="ml-auto justify-end" label={`${h.name}: ${h.boxes} boxes`} />
              </li>
            ))}
          </ul>
        </Section>
        <Section title="Status">
          <ul className="text-[11px] leading-5">
            {sheet.status.map((name, i) => (
              <li key={`${name}/${i}`} className="border-b border-dotted border-neutral-400">
                {name}
              </li>
            ))}
            {Array.from({ length: Math.max(0, 3 - sheet.status.length) }, (_, i) => (
              <li key={`blank${i}`} className="h-5 border-b border-dotted border-neutral-400" />
            ))}
          </ul>
        </Section>
        <Section title="Test Pools">
          <p className="text-[12px]">
            Initiative: <strong>{Math.max(physical, mental)}</strong>
            {initiative && <Changes pool={initiative} modifiers={sheet.modifiers} />}
          </p>
          <ul className="mt-1 text-[10px] leading-4">
            {sheet.pools
              .filter((p) => p.key !== "initiative" && (p.group === "Combat" || p.group === "Defence"))
              .map((p) => (
                <li key={p.key} className="flex flex-wrap items-baseline justify-between gap-x-2 border-b border-dotted border-neutral-400">
                  <span>
                    {p.name}
                    <Changes pool={p} modifiers={sheet.modifiers} />
                    {p.damage && <span className="block text-neutral-600">{damageShort(p.damage)}</span>}
                  </span>
                  <strong>
                    {total(p, 0, sheet.modifiers)}
                    {p.adds_willpower && " + Willpower"}
                  </strong>
                </li>
              ))}
            <li className="h-4 border-b border-dotted border-neutral-400" />
          </ul>
        </Section>
      </div>

      {otherGroups.size > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {[...otherGroups].map(([name, traits]) => (
            <Section key={name} title={name}>
              <TraitList traits={traits} empty={0} />
            </Section>
          ))}
        </div>
      )}

      {sheet.equipment.length > 0 && (
        <Section title="Equipment">
          <ul className="grid grid-cols-2 gap-x-4 text-[10px] leading-4" aria-label="Equipment">
            {sheet.equipment.map((item) => (
              <PrintedItem key={item.id} item={item} />
            ))}
          </ul>
        </Section>
      )}

      {sheet.retainers.length > 0 && (
        <Section title="Retainers">
          <div className="grid grid-cols-3 gap-x-4 gap-y-2" aria-label="Retainers">
            {sheet.retainers.map((r, i) => (
              <PrintedRetainer key={r.id ?? `bought${i}`} retainer={r} />
            ))}
          </div>
        </Section>
      )}

      <footer className="mt-auto border-t border-black pt-1 text-center text-[9px] text-neutral-600">
        Printed from Horatio {dates.date(new Date())}
        {sheet.home && sheet.accepted_at && ` · accepted ${dates.date(sheet.accepted_at)} by ${sheet.accepted_by}`}
        <br />
        Unofficial fan-made material under Paradox Interactive's Dark Pack Agreement. Portions © Paradox Interactive AB, used with permission.
      </footer>
    </article>
  );
}

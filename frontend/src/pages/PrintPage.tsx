import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../api/client";
import type { PrintedSheet } from "../api/types";

type Trait = PrintedSheet["traits"][number];

/**
 * A character sheet laid out for paper, in the order of the official BNS sheet:
 * identity, attributes with focuses, skills, then backgrounds / disciplines /
 * merits and flaws, then blood / willpower / morality, then health and status.
 * Black on white, sized for US Letter, and readable on screen before printing.
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

  if (sheet.isPending) return <p className="p-8 text-black">Loading…</p>;
  if (sheet.error) return <p className="p-8 text-black">{sheet.error.message}</p>;
  return <Sheet sheet={sheet.data} />;
}

function by(traits: Trait[], ...categories: string[]) {
  return traits.filter((t) => categories.includes(t.category));
}

function one(traits: Trait[], category: string): string {
  return traits.find((t) => t.category === category)?.name ?? "";
}

function rating(traits: Trait[], category: string, name: string): number {
  return traits.find((t) => t.category === category && t.name === name)?.rating ?? 0;
}

function label(t: Trait) {
  return t.detail ? `${t.name}: ${t.detail}` : t.name;
}

/** Filled and empty dots, five to a group, like the paper sheet. */
function Dots({ value, of = 5 }: { value: number; of?: number }) {
  const total = Math.max(of, value);
  return (
    <span className="font-mono text-[11px] tracking-[-0.05em] whitespace-nowrap" aria-label={`${value} dots`}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={i > 0 && i % 5 === 0 ? "ml-1" : undefined}>
          {i < value ? "●" : "○"}
        </span>
      ))}
    </span>
  );
}

/** Boxes to tick in play: blood, willpower, health. */
function Boxes({ count, numbered = false }: { count: number; numbered?: boolean }) {
  return (
    <span className="inline-flex flex-wrap gap-0.5">
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

function TraitList({ traits, empty = 3 }: { traits: Trait[]; empty?: number }) {
  const blanks = Math.max(0, empty - traits.length);
  return (
    <ul className="text-[11px] leading-5">
      {traits.map((t) => (
        <li key={`${t.category}/${t.name}/${t.detail}`} className="flex items-baseline justify-between gap-2 border-b border-dotted border-neutral-400">
          <span>
            {label(t)}
            {t.pending_from !== null && <em className="ml-1 text-neutral-500">(awaiting approval from {t.pending_from})</em>}
          </span>
          {t.rating !== null && <Dots value={t.rating} />}
        </li>
      ))}
      {Array.from({ length: blanks }, (_, i) => (
        <li key={`blank${i}`} className="h-5 border-b border-dotted border-neutral-400" />
      ))}
    </ul>
  );
}

/** Max blood and blood per turn by Generation dots, from the BNS sheet. */
const BLOOD = [
  [10, 1],
  [10, 1],
  [12, 2],
  [15, 3],
  [20, 4],
  [30, 5],
] as const;

const SHOWN_ELSEWHERE = new Set([
  "clan", "archetype", "sect", "faction", "attributes",
  "focus_physicals", "focus_mentals", "focus_socials", "skills", "backgrounds",
  "disciplines", "merits", "flaws", "paths", "health_levels", "willpower_sources", "status_traits",
]);

function Sheet({ sheet }: { sheet: PrintedSheet }) {
  const t = sheet.traits;
  const generation = rating(t, "backgrounds", "Generation");
  const [maxBlood, perTurn] = BLOOD[Math.min(generation, 5)]!;
  const willpower = rating(t, "willpower_sources", "Willpower");
  const path = by(t, "paths")[0];
  const physical = rating(t, "attributes", "Physical");
  const mental = rating(t, "attributes", "Mental");
  const skills = by(t, "skills").sort((a, b) => a.name.localeCompare(b.name));
  const third = Math.ceil(skills.length / 3);
  const others = t.filter((x) => !SHOWN_ELSEWHERE.has(x.category));
  const otherGroups = new Map<string, Trait[]>();
  for (const x of others) otherGroups.set(x.category_name, [...(otherGroups.get(x.category_name) ?? []), x]);

  return (
    <div className="min-h-screen bg-neutral-200 py-6 text-black print:min-h-0 print:bg-white print:py-0">
      <div className="mx-auto mb-4 flex max-w-[8.5in] justify-between px-4 print:hidden">
        <button onClick={() => window.history.back()} className="text-sm underline">
          ← Back
        </button>
        <button onClick={() => window.print()} className="rounded bg-black px-4 py-1.5 text-sm text-white">
          Print
        </button>
      </div>
      <article className="mx-auto flex max-w-[8.5in] flex-col gap-3 bg-white p-[0.45in] font-serif shadow print:max-w-none print:p-0 print:shadow-none">
        <header className="grid grid-cols-[1fr_auto] items-start gap-4 border-b-2 border-black pb-2">
          <dl className="grid grid-cols-[auto_1fr_auto_1fr] gap-x-2 text-[12px]">
            <dt className="font-bold">Character</dt>
            <dd className="border-b border-black">{sheet.character_name}</dd>
            <dt className="font-bold">Player</dt>
            <dd className="border-b border-black">{sheet.player_name}</dd>
            <dt className="font-bold">Clan</dt>
            <dd className="border-b border-black">{one(t, "clan")}</dd>
            <dt className="font-bold">Archetype</dt>
            <dd className="border-b border-black">{one(t, "archetype")}</dd>
            <dt className="font-bold">Sect</dt>
            <dd className="border-b border-black">{one(t, "sect")}</dd>
            <dt className="font-bold">Title</dt>
            <dd className="border-b border-black">{sheet.titles.join(", ")}</dd>
          </dl>
          <div className="text-right">
            <p className="font-display text-2xl tracking-widest uppercase">{sheet.splat}</p>
            <p className="text-[10px]">
              {sheet.kind === "npc"
                ? `NPC of ${sheet.troupe_name}`
                : sheet.home
                  ? `Home troupe: ${sheet.troupe_name}`
                  : sheet.troupe_name
                    ? `Visiting ${sheet.troupe_name}`
                    : "No home troupe yet"}
            </p>
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
              <div key={name}>
                <div className="flex items-baseline justify-between font-bold">
                  {name} <Dots value={rating(t, "attributes", name)} of={10} />
                </div>
                <p className="text-[11px]">Focus: {by(t, focus).map((f) => f.name).join(", ") || "—"}</p>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Skills">
          <div className="grid grid-cols-3 gap-x-4">
            {[0, 1, 2].map((col) => (
              <TraitList key={col} traits={skills.slice(col * third, (col + 1) * third)} empty={col === 2 ? 2 : 0} />
            ))}
          </div>
        </Section>

        <div className="grid grid-cols-3 gap-4">
          <Section title="Backgrounds">
            <TraitList traits={by(t, "backgrounds")} empty={4} />
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
            <p className="mb-1 text-center text-[10px]">
              {maxBlood} blood · {perTurn} per turn
            </p>
            <div className="flex justify-center">
              <Boxes count={maxBlood} />
            </div>
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
            <ul className="text-[12px] leading-6">
              {by(t, "health_levels")
                .sort((a, b) => ["Healthy", "Injured", "Incapacitated"].indexOf(a.name) - ["Healthy", "Injured", "Incapacitated"].indexOf(b.name))
                .map((h) => (
                  <li key={h.name} className="flex items-center justify-between">
                    {h.name} <Boxes count={h.rating ?? 0} />
                  </li>
                ))}
            </ul>
          </Section>
          <Section title="Status">
            <TraitList traits={by(t, "status_traits")} empty={3} />
          </Section>
          <Section title="Test Pools">
            <p className="text-[12px]">
              Initiative: <strong>{Math.max(physical, mental)}</strong>
            </p>
            <ul className="mt-1 text-[11px] leading-5">
              {[0, 1, 2].map((i) => (
                <li key={i} className="h-5 border-b border-dotted border-neutral-400" />
              ))}
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

        <footer className="mt-auto border-t border-black pt-1 text-center text-[9px] text-neutral-600">
          Printed from Horatio {new Date().toLocaleDateString()}
          {sheet.home && sheet.accepted_at && ` · accepted ${new Date(sheet.accepted_at).toLocaleDateString()} by ${sheet.accepted_by}`}
        </footer>
      </article>
    </div>
  );
}

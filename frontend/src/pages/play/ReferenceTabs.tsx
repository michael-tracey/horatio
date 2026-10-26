import type { ReactNode } from "react";
import type { DisciplinePowers, PlayReference, PoolModifier, PowerSwitch, TestPool } from "../../api/types";
import { Rating } from "../../components/ui";
import { pipsOf } from "../../ratings";
import { RetainerLines } from "../character/Retainers";
import { ModifiersPanel } from "./Modifiers";
import { breakdown, damageText, exceptionalText, grouped, switchedDamage, total } from "./pools";
import { PowersList } from "./Powers";
import type { makeTap } from "./tracker";
import { useModifiers } from "./useModifiers";

type Trait = PlayReference["traits"][number];

function Panel({ title, aside, children }: { title: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-ash bg-dusk p-3">
      <header className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-base text-gold">{title}</h2>
        {aside}
      </header>
      {children}
    </section>
  );
}

// Each attribute's focuses, shown beside it rather than as parts of their own.
const FOCUSES: Record<string, string> = { Physical: "focus_physicals", Social: "focus_socials", Mental: "focus_mentals" };

/** The brackets after a trait: an attribute's focuses, a skill's specialties. */
function brackets(t: Trait, traits: Trait[]): string[] {
  if (t.category === "attributes" && FOCUSES[t.name]) return traits.filter((f) => f.category === FOCUSES[t.name]).map((f) => f.name);
  return t.specialties;
}

/** The sheet to look things up in at a game: every part laid out, nothing folded away. */
export function SheetTab({ reference }: { reference: PlayReference }) {
  const groups = new Map<string, Trait[]>();
  for (const t of reference.traits) {
    if (Object.values(FOCUSES).includes(t.category)) continue;
    groups.set(t.category_name, [...(groups.get(t.category_name) ?? []), t]);
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {[...groups].map(([name, traits]) => (
        <Panel key={name} title={name}>
          <ul className="text-sm">
            {traits.map((t) => (
              <li key={`${t.category}/${t.name}/${t.detail}`} className="border-b border-ash/60 py-1 last:border-0">
                <div className="flex items-baseline justify-between gap-3">
                <span>
                  {t.detail ? `${t.name}: ${t.detail}` : t.name}
                  {brackets(t, reference.traits).length > 0 && <span className="text-mist"> ({brackets(t, reference.traits).join(", ")})</span>}
                </span>
                {t.rating !== null && <Rating value={t.rating} of={pipsOf(t.category)} className="shrink-0 font-display text-base text-gold" />}
                </div>
                {t.category === "backgrounds" && t.name === "Retainers" && reference.retainers.length > 0 && <RetainerLines retainers={reference.retainers} />}
              </li>
            ))}
          </ul>
        </Panel>
      ))}
    </div>
  );
}

function PoolRow({ pool, willpower, modifiers, on }: { pool: TestPool; willpower: number; modifiers: PoolModifier[]; on: string[] }) {
  const hurt = pool.damage ? switchedDamage(pool.damage, on) : [];
  return (
    <li className="border-b border-ash/60 py-2 last:border-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-parchment">{pool.name}</span>
        <strong className="font-display text-2xl leading-none text-parchment">{total(pool, willpower, modifiers, on)}</strong>
      </div>
      <p className="text-xs text-mist">
        {breakdown(pool, willpower, modifiers, on)}
        {pool.versus && <> · against {pool.versus}</>}
      </p>
      {pool.damage && (
        <p className="mt-0.5 text-sm text-parchment">
          {damageText(pool.damage, hurt)}
          <span className="block text-xs text-mist">{exceptionalText(pool.damage, hurt)}</span>
          {pool.damage.notes.map((n) => (
            <span key={n} className="block text-xs text-mist">
              {n}
            </span>
          ))}
        </p>
      )}
      {pool.variants.length > 0 && (
        <ul className="mt-1 flex flex-col gap-0.5 text-sm">
          {pool.variants.map((v) => (
            <li key={v.when} className="flex items-baseline justify-between gap-3 pl-3">
              <span className="text-mist">
                {v.when}
                <span className="text-xs"> ({v.parts.map((p) => `${p.value >= 0 ? "+" : "−"}${Math.abs(p.value)} ${p.label}`).join(", ")})</span>
              </span>
              <strong className="text-gold">{v.total + (total(pool, willpower, modifiers, on) - pool.total)}</strong>
            </li>
          ))}
        </ul>
      )}
      {pool.notes.map((n) => (
        <p key={n} className="mt-0.5 pl-3 text-xs text-mist">
          {n}
        </p>
      ))}
    </li>
  );
}

function Discipline({ discipline }: { discipline: DisciplinePowers }) {
  return (
    <Panel title={discipline.name} aside={<Rating value={discipline.rating} className="font-display text-lg text-gold" />}>
      <p className="mb-2 text-xs text-mist">
        {discipline.pool ? `${discipline.pool} against ${discipline.versus}.` : null} {discipline.note}
      </p>
      {discipline.focus && <p className="mb-2 text-xs text-gold">Your focus: {discipline.focus}</p>}
      <ol className="flex flex-col gap-2 text-sm">
        {discipline.powers.map((p) => (
          <li key={p.level}>
            <p>
              <Rating value={p.level} of={p.level} className="min-w-5 text-gold" /> <strong className="font-semibold">{p.name}</strong>
            </p>
            <p className="text-mist">{p.note}</p>
            {p.focus && <p className="text-xs text-gold">Your focus: {p.focus}</p>}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

/**
 * Test pools worked out from the sheet, with what changes them, and what each
 * power does. Defence counts current Willpower, so it follows the tracker.
 * "Forms and powers in use" switches on what the sheet's powers change while
 * active, from the rules, beside the player's own modifiers (issue #200): the
 * pools count whatever is on.
 */
export function PoolsTab({
  reference,
  willpower,
  characterId,
  powers,
  tap,
}: {
  reference: PlayReference;
  willpower: number;
  characterId: string;
  powers: PowerSwitch[];
  tap: (what: Parameters<typeof makeTap>[0]) => void;
}) {
  const modifiers = useModifiers(characterId);
  const on = powers.filter((p) => p.on).map((p) => p.key);
  return (
    <div className="flex flex-col gap-3">
      <section className="flex flex-col gap-3 rounded-lg border border-ash bg-dusk p-3" aria-label="Forms and powers in use">
        <h2 className="text-base text-gold">Forms and powers in use</h2>
        <PowersList powers={powers} tap={tap} />
        <ModifiersPanel pools={reference.pools} modifiers={modifiers} />
      </section>
      <div className="grid gap-3 md:grid-cols-2">
        {grouped(reference.pools).map(([group, pools]) => (
          <Panel key={group} title={group} aside={group === "Defence" ? <span className="text-xs text-mist">Willpower now: {willpower}</span> : undefined}>
            <ul>
              {pools.map((p) => (
                <PoolRow key={p.key} pool={p} willpower={willpower} modifiers={modifiers.modifiers} on={on} />
              ))}
            </ul>
          </Panel>
        ))}
      </div>
      {reference.notes.length > 0 && (
        <Panel title="Also">
          <ul className="list-disc pl-5 text-sm text-mist">
            {reference.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Panel>
      )}
      {reference.disciplines.length > 0 && <h2 className="mt-2 text-lg text-gold">Powers</h2>}
      <div className="grid gap-3 md:grid-cols-2">
        {reference.disciplines.map((d) => (
          <Discipline key={d.name} discipline={d} />
        ))}
      </div>
      {reference.other_powers.length > 0 && (
        <Panel title="Techniques and elder powers">
          <ul className="flex flex-col gap-1.5 text-sm">
            {reference.other_powers.map((o) => (
              <li key={`${o.category_name}/${o.name}`}>
                <strong className="font-semibold">{o.name}</strong> <span className="text-xs text-mist">{o.category_name}</span>
                {o.note && <p className="text-mist">{o.note}</p>}
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

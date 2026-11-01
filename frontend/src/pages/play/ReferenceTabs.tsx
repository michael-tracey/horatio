import { useState, type ReactNode } from "react";
import type { DisciplinePowers, PlayItem, PlayReference, PowerSwitch, TestPool } from "../../api/types";
import { HouseMark } from "../../components/HouseMark";
import { TraitInfo } from "../../components/TraitInfo";
import { Rating } from "../../components/ui";
import { pipsOf } from "../../ratings";
import { IdentityNote } from "../character/Identities";
import { RetainerLines } from "../character/Retainers";
import { givingMerits } from "../character/retainers";
import { equipmentModifiers } from "./equipped";
import { bloodNote, breakdown, damageText, grouped, OTHER_TESTS, situations, switchedDamage, total, withAttribute, type Modifier } from "./pools";
import { SwitchesDrawer } from "./SwitchesDrawer";
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

/**
 * What opens under a trait's name, beyond its description: an attribute's
 * focuses and what each adds, or a discipline's pool, note and the powers the
 * character has of it, as the Pools tab lists them (in place of its description).
 */
function TraitLine({ trait: t, reference }: { trait: Trait; reference: PlayReference }) {
  const discipline = t.category === "disciplines" ? reference.disciplines.find((d) => d.name === t.name) : undefined;
  const focuses = t.category === "attributes" && FOCUSES[t.name] ? reference.traits.filter((f) => f.category === FOCUSES[t.name] && f.description) : [];
  const shown = brackets(t, reference.traits);
  return (
    <TraitInfo
      name={t.detail ? `${t.name}: ${t.detail}` : t.name}
      after={
        <>
          {shown.length > 0 && <span className="text-mist"> ({shown.join(", ")})</span>}
          {t.house && <HouseMark label={t.house} summary={t.house_summary} short />}
        </>
      }
      description={discipline ? [discipline.pool && `${discipline.pool} against ${discipline.versus}.`, discipline.note ?? t.description].filter(Boolean).join(" ") : t.description}
      more={
        discipline ? (
          <PowerList discipline={discipline} />
        ) : focuses.length > 0 ? (
          focuses.map((f) => (
            <p key={f.name} className="mt-0.5">
              <span className="text-parchment">{f.name}:</span> {f.description}
            </p>
          ))
        ) : null
      }
      summary={t.house_summary}
      page={t.page_reference}
    />
  );
}

/**
 * The powers the character has of a discipline, by dot, with what its focus adds:
 * under the discipline's name here, and on the character's Sheet tab.
 */
export function PowerList({ discipline }: { discipline: DisciplinePowers }) {
  return (
    <>
      {discipline.focus && <p className="text-gold">Your focus: {discipline.focus}</p>}
      <ol className="mt-1 flex flex-col gap-1">
        {discipline.powers.map((p) => (
          <li key={p.level}>
            <Rating value={p.level} of={p.level} className="min-w-5 text-gold" /> <span className="text-parchment">{p.name}</span> {p.note}
            {p.focus && <span className="block text-gold">Your focus: {p.focus}</span>}
          </li>
        ))}
      </ol>
    </>
  );
}

/**
 * The sheet to look things up in at a game: every part laid out, nothing folded
 * away but what each trait does, which opens under its name. The clan, archetype
 * and sect are in the subheader instead.
 */
export function SheetTab({ reference }: { reference: PlayReference }) {
  // The Retainers listed once, under the last Retainer bought; with none bought, under
  // the first merit that gives one.
  const giving = givingMerits(reference.retainers);
  const retainersUnder =
    reference.traits.filter((t) => t.category === "backgrounds" && t.name === "Retainers").at(-1) ??
    reference.traits.find((t) => t.category === "merits" && giving.includes(t.name));
  const groups = new Map<string, Trait[]>();
  for (const t of reference.traits) {
    // The clan, archetype, sect and faction are in the subheader.
    if (t.group === "Identity" || Object.values(FOCUSES).includes(t.category)) continue;
    groups.set(t.category_name, [...(groups.get(t.category_name) ?? []), t]);
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {/* A ghoul's domitor, whose clan it takes, and the weakness it plays for roleplay only (MET: VtM core p. 297). */}
      {reference.domitor && (
        <Panel title="Domitor">
          <p className="text-sm text-parchment">
            {reference.domitor.name}
            {reference.domitor.clan && <span className="text-mist"> · {reference.domitor.clan}</span>}
          </p>
          {reference.domitor.weakness && <p className="mt-1 text-xs text-mist">Weakness: {reference.domitor.weakness}</p>}
        </Panel>
      )}
      {[...groups].map(([name, traits]) => (
        <Panel key={name} title={name}>
          <ul className="text-sm">
            {traits.map((t) => (
              <li key={`${t.category}/${t.name}/${t.detail}`} className="border-b border-ash/60 py-1 last:border-0">
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3">
                  <TraitLine trait={t} reference={reference} />
                  {t.rating !== null && <Rating value={t.rating} of={pipsOf(t.category)} className="shrink-0 font-display text-base text-gold" />}
                </div>
                {t === retainersUnder && reference.retainers.length > 0 && <RetainerLines retainers={reference.retainers} />}
                {t.category === "backgrounds" && t.name === "Alternate Identity" && <IdentityLine reference={reference} detail={t.detail} />}
              </li>
            ))}
          </ul>
        </Panel>
      ))}
    </div>
  );
}

/** An Alternate Identity's rating line, and who has Accepted it. */
function IdentityLine({ reference, detail }: { reference: PlayReference; detail: string }) {
  const identity = (reference.identities ?? []).find((i) => i.name === detail);
  return identity ? <IdentityNote identity={identity} /> : null;
}

export function PoolRow({ pool, willpower, modifiers, on }: { pool: TestPool; willpower: number; modifiers: Modifier[]; on: string[] }) {
  const hurt = pool.damage ? switchedDamage(pool.damage, on) : [];
  const now = total(pool, willpower, modifiers, on);
  const variants = [
    ...pool.variants.map((v) => ({ when: v.when, parts: v.parts, total: v.total + (now - pool.total) })),
    // An equipped item's bonus that counts only sometimes: "Against firearms (+3 Flak Vest: Ballistic)".
    ...situations(pool, modifiers).map((s) => ({ when: s.when.charAt(0).toUpperCase() + s.when.slice(1), parts: s.parts, total: now + s.parts.reduce((sum, p) => sum + p.value, 0) })),
  ];
  return (
    <li className="border-b border-ash/60 py-2 last:border-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-parchment">{pool.name}</span>
        <strong className="font-display text-2xl leading-none text-parchment">{now}</strong>
      </div>
      <p className="text-xs text-mist">
        {breakdown(pool, willpower, modifiers, on)}
        {pool.versus && <> · against {pool.versus}</>}
      </p>
      {pool.damage && (
        <p className="mt-0.5 text-sm text-parchment">
          {damageText(pool.damage, hurt)}
          {pool.damage.notes.map((n) => (
            <span key={n} className="block text-xs text-mist">
              {n}
            </span>
          ))}
        </p>
      )}
      {variants.length > 0 && (
        <ul className="mt-1 flex flex-col gap-0.5 text-sm">
          {variants.map((v) => (
            <li key={v.when} className="flex items-baseline justify-between gap-3 pl-3">
              <span className="text-mist">
                {v.when}
                <span className="text-xs"> ({v.parts.map((p) => `${p.value >= 0 ? "+" : "−"}${Math.abs(p.value)} ${p.label}`).join(", ")})</span>
              </span>
              <strong className="text-gold">{v.total}</strong>
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

const ATTRIBUTES = ["Physical", "Social", "Mental"] as const;

/**
 * Every other skill the character has, as attribute + skill (MET: VtM core p. 272;
 * issue #371). The storyteller names the attribute, so each starts with the one the
 * skill is listed under, and one tap counts them all on another.
 */
function OtherTests({ pools, reference, willpower, modifiers, on }: { pools: TestPool[]; reference: PlayReference; willpower: number; modifiers: Modifier[]; on: string[] }) {
  const [attribute, setAttribute] = useState<string | null>(null);
  const rating = (name: string) => reference.traits.find((t) => t.category === "attributes" && t.name === name)?.rating ?? 0;
  const shown = attribute ? pools.map((p) => withAttribute(p, attribute, rating(attribute))) : pools;
  return (
    <Panel title={OTHER_TESTS}>
      <p className="text-xs text-mist">Attribute + skill. Your storyteller names the attribute; each skill starts with the one it's listed under.</p>
      <div className="mt-2 flex flex-wrap gap-1" role="group" aria-label="Attribute for other tests">
        {[null, ...ATTRIBUTES].map((a) => (
          <button
            key={a ?? "listed"}
            type="button"
            aria-pressed={attribute === a}
            onClick={() => setAttribute(a)}
            className={`min-h-9 rounded-full border px-3 text-xs pointer-coarse:min-h-11 ${attribute === a ? "border-gold/60 bg-gold/10 text-gold" : "border-line text-mist hover:text-parchment"}`}
          >
            {a ?? "As listed"}
          </button>
        ))}
      </div>
      <ul>
        {shown.map((p) => (
          <PoolRow key={p.key} pool={p} willpower={willpower} modifiers={modifiers} on={on} />
        ))}
      </ul>
    </Panel>
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
 * The switches for what the sheet's powers change while active, from the rules,
 * the equipment (issue #306) and the player's own modifiers (issue #200), are in a
 * drawer from a button at the foot (issue #211): the pools count whatever is on.
 */
export function PoolsTab({
  reference,
  willpower,
  characterId,
  powers,
  items = [],
  equipped = [],
  tap,
}: {
  reference: PlayReference;
  willpower: number;
  characterId: string;
  powers: PowerSwitch[];
  items?: PlayItem[];
  equipped?: string[];
  tap: (what: Parameters<typeof makeTap>[0]) => void;
}) {
  const modifiers = useModifiers(characterId);
  const on = powers.filter((p) => p.on).map((p) => p.key);
  // The player's own, then what the items equipped make (issue #306).
  const counting = [...modifiers.modifiers, ...equipmentModifiers(items, equipped)];
  return (
    <div className="flex flex-col gap-3 pb-20">
      <div className="grid gap-3 md:grid-cols-2">
        {grouped(reference.pools).map(([group, pools]) =>
          group === OTHER_TESTS ? (
            <OtherTests key={group} pools={pools} reference={reference} willpower={willpower} modifiers={counting} on={on} />
          ) : (
            <Panel key={group} title={group} aside={group === "Defence" ? <span className="text-xs text-mist">Willpower now: {willpower}</span> : undefined}>
              {group === "Combat" && reference.blood_per_turn > 0 && <p className="text-xs text-mist">{bloodNote(reference.blood_per_turn)}</p>}
              <ul>
                {pools.map((p) => (
                  <PoolRow key={p.key} pool={p} willpower={willpower} modifiers={counting} on={on} />
                ))}
              </ul>
            </Panel>
          ),
        )}
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
      <SwitchesDrawer pools={reference.pools} powers={powers} items={items} equipped={equipped} modifiers={modifiers} tap={tap} />
    </div>
  );
}

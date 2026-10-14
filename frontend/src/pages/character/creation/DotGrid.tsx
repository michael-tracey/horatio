import { useMemo, useState } from "react";
import type { TraitOut } from "../../../api/types";
import { Badge, Input, Select } from "../../../components/ui";
import { canTap, left, spent, tap, togglePoints, type Allowed, type Picks } from "./logic";

const SEARCH_FROM = 12; // Long lists get a search box.

function useFiltered(traits: TraitOut[], picks: Picks) {
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return traits.filter((t) => !q || t.name.toLowerCase().includes(q) || t.name in picks);
  }, [traits, picks, query]);
  return { query, setQuery, shown };
}

/**
 * Every trait in a category, each with a row of dots. Tap a dot to set that
 * rating; tap it again to clear. Only ratings with picks can be tapped, and a
 * rating with none left greys out (a single pick swaps instead).
 */
export function DotGrid({
  title,
  traits,
  allowed,
  picks,
  onChange,
  tag,
  showTitle = true,
  sections,
}: {
  title: string;
  showTitle?: boolean;
  /** Split the rows under headings, such as skills by attribute. Traits no
   * section claims go last, under "Other". */
  sections?: { order: string[]; of: (trait: TraitOut) => string | null };
  traits: TraitOut[];
  allowed: Allowed;
  picks: Picks;
  onChange: (picks: Picks) => void;
  tag?: (trait: TraitOut) => string | null;
}) {
  const ratings = Object.keys(allowed)
    .map(Number)
    .sort((a, b) => b - a);
  const maxDots = Math.max(...ratings);
  const { query, setQuery, shown } = useFiltered(traits, picks);
  const groups: [string | null, TraitOut[]][] = sections
    ? [...sections.order, "Other"]
        .map((h): [string, TraitOut[]] => [
          h,
          shown.filter((t) => (h === "Other" ? !sections.order.includes(sections.of(t) ?? "") : sections.of(t) === h)),
        ])
        .filter(([, ts]) => ts.length > 0)
    : [[null, shown]];
  const row = (trait: TraitOut) => {
    const rating = picks[trait.name] ?? 0;
    const label = tag?.(trait);
    return (
      <li key={trait.name} className="flex items-center justify-between gap-3 py-1.5">
        <span className="min-w-0 text-sm">
          <span className={rating ? "text-parchment" : "text-mist"}>{trait.name}</span>
          {label && <span className="ml-2 text-xs text-gold">{label}</span>}
        </span>
        <span className="flex shrink-0 gap-0.5">
          {Array.from({ length: maxDots }, (_, i) => i + 1).map((dot) => {
            const pickable = dot in allowed;
            const enabled = pickable && canTap(picks, allowed, trait.name, dot);
            const filled = dot <= rating;
            return (
              <button
                key={dot}
                type="button"
                aria-label={`${trait.name} ${dot}`}
                aria-pressed={rating === dot}
                disabled={!enabled}
                onClick={() => onChange(tap(picks, allowed, trait.name, dot))}
                className={[
                  "grid h-8 w-7 place-items-center rounded text-lg leading-none",
                  pickable ? "hover:bg-ash" : "cursor-default",
                  filled ? "text-blood-bright" : pickable ? "text-mist" : "text-ash",
                  !enabled && pickable && !filled ? "opacity-30" : "",
                ].join(" ")}
              >
                {filled ? "●" : pickable ? "○" : "·"}
              </button>
            );
          })}
        </span>
      </li>
    );
  };

  return (
    <section aria-label={title} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {showTitle ? <h3 className="text-base text-gold">{title}</h3> : <span />}
        <ul className="flex flex-wrap gap-1.5" aria-label={`${title} picks left`}>
          {ratings.map((r) => {
            const n = left(picks, allowed, r);
            return (
              <li key={r}>
                <Badge tone={n > 0 ? "gold" : "mist"}>
                  {n} at {r} left
                </Badge>
              </li>
            );
          })}
        </ul>
      </div>
      {traits.length >= SEARCH_FROM && (
        <Input aria-label={`Search ${title}`} placeholder="Search…" value={query} onChange={(e) => setQuery(e.target.value)} />
      )}
      {groups.map(([heading, traitsIn]) => (
        <div key={heading ?? "all"}>
          {heading && <h4 className="mt-2 mb-1 font-sans text-xs tracking-wide text-mist uppercase">{heading}</h4>}
          <ul className="divide-y divide-ash/60">{traitsIn.map(row)}</ul>
        </div>
      ))}
    </section>
  );
}

/** Merits or flaws: tick traits against a budget of points. */
export function PointsList({
  title,
  traits,
  budget,
  picks,
  onChange,
  unavailable = {},
  details = {},
  onDetail,
}: {
  title: string;
  traits: TraitOut[];
  budget: number;
  picks: Picks;
  onChange: (picks: Picks) => void;
  /** Traits the rules do not allow this character, and why. */
  unavailable?: Record<string, string>;
  /** The choice made for picks that grant something chosen (Personal Cult: which background). */
  details?: Record<string, string>;
  onDetail?: (name: string, detail: string) => void;
}) {
  const { query, setQuery, shown } = useFiltered(traits, picks);
  const used = spent(picks);
  const visible = query.trim() ? shown : shown.filter((t) => t.name in picks).concat(shown.filter((t) => !(t.name in picks)).slice(0, 40));

  return (
    <section aria-label={title} className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-base text-gold">{title}</h3>
        <Badge tone={used < budget ? "gold" : "mist"}>
          {used} of {budget} points
        </Badge>
      </div>
      <div className="h-1.5 overflow-hidden rounded bg-ash">
        <div className="h-full bg-gold" style={{ width: `${(100 * used) / budget}%` }} />
      </div>
      <Input aria-label={`Search ${title}`} placeholder={`Search ${traits.length} ${title.toLowerCase()}…`} value={query} onChange={(e) => setQuery(e.target.value)} />
      <ul className="flex flex-col gap-1">
        {visible.map((t) => {
          const points = t.fixed_rating ?? 1;
          const chosen = t.name in picks;
          const barred = chosen ? undefined : unavailable[t.name];
          const affordable = chosen || (used + points <= budget && !barred);
          return (
            <li key={t.name}>
              <label className={`flex items-start gap-2 rounded px-2 py-1.5 text-sm ${chosen ? "bg-ash/60" : "hover:bg-ash/40"} ${affordable ? "" : "opacity-40"}`}>
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={chosen}
                  disabled={!affordable}
                  onChange={() => onChange(togglePoints(picks, budget, t.name, points))}
                />
                <span className="min-w-0">
                  <span className="text-parchment">{t.name}</span> <span className="text-gold">({points})</span>
                  {barred && <span className="mt-0.5 block text-xs text-blood-bright">{barred}</span>}
                  {chosen && t.choices && onDetail && (
                    <Select
                      aria-label={`${t.name}: which?`}
                      className="mt-1 h-8 py-0"
                      value={details[t.name] ?? ""}
                      onChange={(e) => onDetail(t.name, e.target.value)}
                    >
                      <option value="">Which?</option>
                      {t.choices.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </Select>
                  )}
                  {t.description && <span className="mt-0.5 block text-xs text-mist">{t.description}</span>}
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      {!query.trim() && shown.length > visible.length && (
        <p className="text-xs text-mist">Search to see all {traits.length}.</p>
      )}
    </section>
  );
}

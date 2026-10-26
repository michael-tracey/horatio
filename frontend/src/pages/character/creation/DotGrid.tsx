import { useMemo, useState, type ReactNode } from "react";
import { HouseMark, HouseSummary } from "../../../components/HouseMark";
import type { TraitOut } from "../../../api/types";
import { Badge, Input, Select } from "../../../components/ui";
import { applyFilter, filterChoices } from "../traitFilter";
import { detailNeed } from "../fields";
import { canTap, canTapDots, clear, fieldProblems, keysOf, left, traitOf, nextCopy, spent, tap, tapDots, togglePoints, type Allowed, type Picks } from "./logic";

// Long lists get a search box.
const SEARCH_FROM = 12;

function useFiltered(traits: TraitOut[], picks: Picks) {
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const picked = new Set(Object.keys(picks).map(traitOf));
    return traits.filter((t) => !q || t.name.toLowerCase().includes(q) || picked.has(t.name));
  }, [traits, picks, query]);
  return { query, setQuery, shown };
}

/** Holds the counters in view while a long list scrolls under them (on a phone, the page). */
const STICKY = "sticky top-0 z-10 -mx-2 bg-dusk/95 px-2 py-2 backdrop-blur";

/** Ratings at which a trait cannot be picked, and why: Generation 2 for a Thin Blooded vampire. */
export type RatingBar = { ratings: number[]; note: ReactNode };

/** A trait a merit gives, held without a pick: the dots it has, and a line saying whose they are. */
export type Held = { rating: number; text: string };

/**
 * Every trait in a category, each with a row of dots. Tap a dot to set that
 * rating; tap it again, or Clear, to take it back. Only ratings with picks can
 * be tapped, and a rating with none left greys out (in a ranking, such as
 * attributes, tapping a taken rating swaps instead). With a `budget`, the dots
 * are shared out from it instead, as many on a trait as it likes.
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
  details = {},
  onDetail,
  unavailable = {},
  marks = {},
  why,
  barredAt = {},
  held = {},
  budget,
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
  /** The field each picked Crafts, Performance or Science is for, by pick (see logic's `copyKey`). */
  details?: Record<string, string>;
  onDetail?: (name: string, detail: string) => void;
  /** Traits the rules do not allow this character, and why. */
  unavailable?: Record<string, string>;
  /** Picks kept where they no longer fit, and what to do (a starting dot on a
   * discipline that is no longer in-clan): marked on their row, never dropped. */
  marks?: Record<string, string>;
  /** More on why a trait is refused: the traits it is because of, and where they are. */
  why?: (name: string) => ReactNode;
  /** Ratings a trait cannot be picked at, by trait: the dots are greyed and the reason shown. */
  barredAt?: Record<string, RatingBar[]>;
  /** Traits merits give, held without a pick (a focus, Diva's Fame 2): shown filled, and no pick goes on them. */
  held?: Record<string, Held>;
  /** Dots to share out in place of picks at each rating (a ghoul's 5 discipline dots),
   * up to `max` on one trait; those left are saved for later. */
  budget?: { dots: number; max: number };
}) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (name: string) => {
    const next = new Set(open);
    if (!next.delete(name)) next.add(name);
    setOpen(next);
  };
  const ratings = Object.keys(allowed)
    .map(Number)
    .sort((a, b) => b - a);
  const maxDots = budget ? budget.max : Math.max(...ratings);
  const pickableAt = (dot: number) => (budget ? dot <= budget.max : dot in allowed);
  const tappable = (key: string, dot: number) => (budget ? canTapDots(picks, budget.dots, key, dot) : canTap(picks, allowed, key, dot));
  const { query, setQuery, shown } = useFiltered(traits, picks);
  const groups: [string | null, TraitOut[]][] = sections
    ? [...sections.order, "Other"]
        .map((h): [string, TraitOut[]] => [
          h,
          shown.filter((t) => (h === "Other" ? !sections.order.includes(sections.of(t) ?? "") : sections.of(t) === h)),
        ])
        .filter(([, ts]) => ts.length > 0)
    : [[null, shown]];
  // Another field of a skill (Performance: Dance beside Singing), added but not yet tapped.
  const [added, setAdded] = useState<string[]>([]);
  // The field box to focus when it appears: the one just tapped or added.
  const [focus, setFocus] = useState<string | null>(null);
  const problems = onDetail ? fieldProblems(picks, details, (name) => detailNeed(traits.find((t) => t.name === name))) : {};

  /** One row of dots, for a trait or for one more field of it (`key` then names that field's pick). */
  const line = (trait: TraitOut, key: string) => {
    const copy = key !== trait.name;
    const rating = picks[key] ?? 0;
    const label = copy ? null : tag?.(trait);
    const barred = rating || copy ? undefined : unavailable[trait.name];
    const gift = rating || copy ? undefined : held[trait.name];
    const bars = copy ? [] : (barredAt[trait.name] ?? []);
    const marked = rating && !copy ? marks[trait.name] : undefined;
    const about = !copy && trait.description ? `about-${title}-${trait.name}`.replace(/\W+/g, "-") : undefined;
    const shown = open.has(trait.name);
    const need = detailNeed(trait);
    const fielded = need && onDetail && (rating > 0 || copy);
    const remove = () => {
      onChange(clear(picks, key));
      setAdded(added.filter((k) => k !== key));
    };
    return (
      <div key={key} className={copy ? "mt-1.5" : undefined}>
        <div className="flex items-center justify-between gap-3">
          <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            {about ? (
              <button
                type="button"
                aria-expanded={shown}
                aria-controls={about}
                aria-label={`About ${trait.name}`}
                onClick={() => toggle(trait.name)}
                className="-ml-1 grid h-7 w-6 place-items-center rounded text-mist hover:bg-ash hover:text-parchment"
              >
                <Chevron open={shown} />
              </button>
            ) : (
              <span className="w-5" aria-hidden />
            )}
            <span className={rating ? "text-parchment" : barred ? "text-ash" : "text-mist"}>{trait.name}</span>
            {label && <span className="text-xs text-gold">{label}</span>}
            {fielded && (
              <Input
                aria-label={`${key} ${need.kind}`}
                placeholder={need.placeholder}
                autoFocus={focus === key}
                value={details[key] ?? ""}
                onChange={(e) => onDetail(key, e.target.value)}
                className="h-8 w-40 py-0"
              />
            )}
          </span>
          <span className="flex shrink-0 items-center gap-0.5">
            {Array.from({ length: maxDots }, (_, i) => i + 1).map((dot) => {
              const pickable = pickableAt(dot);
              const clashes = picks[key] !== dot && bars.some((b) => b.ratings.includes(dot));
              const enabled = pickable && !barred && !gift && !clashes && tappable(key, dot);
              const filled = dot <= (rating || gift?.rating || 0);
              return (
                <button
                  key={dot}
                  type="button"
                  aria-label={`${key} ${dot}`}
                  aria-pressed={rating === dot}
                  disabled={!enabled}
                  onClick={() => {
                    if (!rating && need) setFocus(key);
                    onChange(budget ? tapDots(picks, budget.dots, key, dot) : tap(picks, allowed, key, dot));
                  }}
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
            {/* Kept in place when hidden, so every row's dots line up. */}
            <button
              type="button"
              aria-label={`Clear ${key}`}
              disabled={!rating && !copy}
              onClick={remove}
              className={`ml-1 h-8 rounded px-2 text-xs text-mist hover:bg-ash hover:text-parchment ${rating || copy ? "" : "invisible"}`}
            >
              Clear
            </button>
          </span>
        </div>
        {barred && (
          <p className="mt-0.5 pl-6 text-xs text-blood-bright">
            {barred}
            {why?.(trait.name)}
          </p>
        )}
        {gift && <p className="mt-0.5 pl-6 text-xs text-gold">{gift.text}</p>}
        {bars.map((bar) => (
          <p key={bar.ratings.join(",")} className="mt-0.5 pl-6 text-xs text-blood-bright">
            Not at {bar.ratings.length > 1 ? `${bar.ratings.slice(0, -1).join(", ")} or ${bar.ratings.at(-1)}` : bar.ratings[0]}: {bar.note}
          </p>
        ))}
        {marked && <p className="mt-0.5 pl-6 text-xs text-blood-bright">{marked} Clear it and place it on another.</p>}
        {problems[key] && <p className="mt-0.5 pl-6 text-xs text-blood-bright">{problems[key].message}</p>}
        {about && (
          <p id={about} hidden={!shown} className="mt-1 pl-6 text-xs leading-relaxed text-mist">
            {trait.description}
          </p>
        )}
      </div>
    );
  };

  const row = (trait: TraitOut) => {
    const need = detailNeed(trait);
    const fields = need && onDetail;
    const copies = fields
      ? [...new Set([...keysOf(picks, trait.name), ...added.filter((k) => traitOf(k) === trait.name)])].filter((k) => k !== trait.name)
      : [];
    const more = () => {
      const key = nextCopy([...Object.keys(picks), ...added], trait.name);
      setAdded([...added, key]);
      setFocus(key);
    };
    return (
      <li key={trait.name} className="py-1.5">
        {line(trait, trait.name)}
        {copies.map((key) => line(trait, key))}
        {fields && keysOf(picks, trait.name).length > 0 && (
          <button type="button" onClick={more} className="mt-1 ml-6 text-xs text-gold underline hover:text-parchment">
            {need.another}
          </button>
        )}
      </li>
    );
  };

  return (
    <section aria-label={title} className="flex flex-col gap-3">
      <div className={`flex flex-wrap items-center justify-between gap-2 ${STICKY}`}>
        {showTitle ? <h3 className="text-base text-gold">{title}</h3> : <span />}
        {budget ? (
          <DotsLeft title={title} budget={budget.dots} used={spent(picks)} />
        ) : (
          <ul className="flex flex-wrap gap-1.5" aria-label={`${title} picks left`}>
            {ratings.map((r) => {
              const n = left(picks, allowed, r);
              return (
                <li key={r}>
                  <Badge tone={n > 0 ? "gold" : n < 0 ? "blood" : "mist"}>
                    {n < 0 ? `${-n} too many at ${r}` : `${n} at ${r} left`}
                  </Badge>
                </li>
              );
            })}
          </ul>
        )}
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

/** How much of a budget of dots is placed, and what is saved for later. */
function DotsLeft({ title, budget, used }: { title: string; budget: number; used: number }) {
  const saved = budget - used;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label={`${title} dots placed`}>
      <li>
        <Badge tone={saved < 0 ? "blood" : "mist"}>
          {used} of {budget} placed
        </Badge>
      </li>
      {saved > 0 && (
        <li>
          <Badge tone="gold">{saved} saved for later</Badge>
        </li>
      )}
    </ul>
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
  barred,
  quick = [],
  details = {},
  onDetail,
  why,
}: {
  title: string;
  traits: TraitOut[];
  budget: number;
  picks: Picks;
  onChange: (picks: Picks) => void;
  /** Traits the rules do not allow this character with these picks, and why. */
  unavailable?: Record<string, string>;
  /** What no choice here could allow: left out of "What this character can take". */
  barred?: Record<string, string>;
  /** One-tap filters: the character's clan and sect. */
  quick?: { value: string; label: string }[];
  /** The choice made for picks that grant something chosen (Personal Cult: which background). */
  details?: Record<string, string>;
  onDetail?: (name: string, detail: string) => void;
  /** More on why a trait is refused: the earlier pick it is refused for. */
  why?: (name: string) => ReactNode;
}) {
  const filterable = traits.some((t) => t.kind || t.requirement);
  const [filter, setFilter] = useState("can");
  // Picks stay listed whatever the filter, so they can be unticked.
  const filtered = filterable ? applyFilter(traits, filter, barred ?? unavailable) : traits;
  const listed = filtered.concat(traits.filter((t) => t.name in picks && !filtered.includes(t)));
  const { query, setQuery, shown } = useFiltered(listed, picks);
  const used = spent(picks);
  const visible = query.trim() ? shown : shown.filter((t) => t.name in picks).concat(shown.filter((t) => !(t.name in picks)).slice(0, 40));

  return (
    <section aria-label={title} className="flex flex-col gap-3">
      <div className={`flex flex-col gap-2 ${STICKY}`}>
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-base text-gold">{title}</h3>
          <Badge tone={used < budget ? "gold" : "mist"}>
            {used} of {budget} points
          </Badge>
        </div>
        <div className="h-1.5 overflow-hidden rounded bg-ash">
          <div className="h-full bg-gold" style={{ width: `${(100 * used) / budget}%` }} />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {filterable && <QuickPicks picks={quick} filter={filter} onFilter={setFilter} title={title} />}
        {filterable && (
          <Select aria-label={`Show ${title}`} value={filter} onChange={(e) => setFilter(e.target.value)} className="w-auto">
            {filterChoices(traits, true).map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </Select>
        )}
        <Input
          aria-label={`Search ${title}`}
          placeholder={`Search ${listed.length} ${title.toLowerCase()}…`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="min-w-40 flex-1"
        />
      </div>
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
                  {t.requirement && <span className="ml-2 text-xs text-mist">{t.requirement}</span>}
                  {t.house && <HouseMark label={t.house.label} summary={t.house.summary} />}
                  {barred && <span className="mt-0.5 block text-xs text-blood-bright">{barred}</span>}
                  {barred && why?.(t.name) && <span className="mt-0.5 block text-xs text-mist">{why(t.name)}</span>}
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
                  <HouseSummary summary={t.house?.summary} />
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      {!query.trim() && shown.length > visible.length && (
        <p className="text-xs text-mist">Search to see all {listed.length}.</p>
      )}
    </section>
  );
}

/** Points right when closed, down when open. */
function Chevron({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={`h-4 w-4 transition-transform ${open ? "rotate-90" : ""}`}>
      <path d="M7.5 4.5 13 10l-5.5 5.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Buttons for the character's own clan and sect; tapping the one in use goes back to "can take". */
export function QuickPicks({
  picks,
  filter,
  onFilter,
  title,
}: {
  picks: { value: string; label: string }[];
  filter: string;
  onFilter: (filter: string) => void;
  title: string;
}) {
  if (!picks.length) return null;
  return (
    <div role="group" aria-label={`Quick picks for ${title}`} className="flex flex-wrap items-center gap-1.5">
      {picks.map((p) => {
        const on = filter === p.value;
        return (
          <button
            key={p.value}
            type="button"
            aria-pressed={on}
            onClick={() => onFilter(on ? "can" : p.value)}
            className={`h-10 rounded-full border px-3 text-sm ${on ? "border-gold bg-gold/15 text-gold" : "border-ash text-mist hover:border-mist hover:text-parchment"}`}
          >
            {p.label} {title.toLowerCase()}
          </button>
        );
      })}
    </div>
  );
}

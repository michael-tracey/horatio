import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { withClanNames } from "../../../clanNames";
import { useClanName } from "../../../components/ClanNames";
import type { TraitOut } from "../../../api/types";
import { Input, Rating } from "../../../components/ui";
import { usePreferences } from "../../../hooks";
import { HouseWording } from "../../../components/TroupeChange";
import { bookSummary } from "../../../houseWording";
import { detailNeed } from "../fields";
import { choose, clear, fieldProblems, isRanking, picksLeft, seatPicks, traitOf, type Allowed, type Picks } from "./logic";
import type { Held, RatingBar } from "./DotGrid";

/** Picks at one rating that a trait held took away, and why (Thin Blooded's discipline at 2). */
export type Lost = { rating: number; picks: number; why: ReactNode };

/** "a skill", "an attribute", "a physical focus": one of a category, for its empty slots. */
export function oneOf(title: string): string {
  const lower = title.toLowerCase();
  const one = lower.endsWith("ies") ? `${lower.slice(0, -3)}y` : lower.endsWith("s") && !/(us|ss)$/.test(lower) ? lower.slice(0, -1) : lower;
  return `${/^[aeiou]/.test(one) ? "an" : "a"} ${one}`;
}

/**
 * A category's creation picks laid out as the book words them (core p. 84): a row
 * for each rating, with a slot for each pick at it, and each slot a searchable
 * choice of the category's traits. "Skills: one at 4, two at 3, three at 2, four at
 * 1" is four rows of one, two, three and four slots.
 *
 * A slot offers only what it can take: a trait picked in another slot, or held
 * without a pick (a merit's free dots), is left out, and one the rules refuse is
 * there, greyed, saying why. In a ranking (attributes' 7 / 5 / 3, a focus) every
 * trait is offered, and choosing one placed in another slot swaps the two. Picks
 * the rules no longer give a slot for are kept, after the slots, marked to move;
 * a slot a trait held took away says what took it.
 */
export function SlotGrid({
  title,
  showTitle = true,
  traits,
  allowed,
  picks,
  onChange,
  sections,
  details = {},
  onDetail,
  unavailable = {},
  why,
  barredAt = {},
  held = {},
  marks = {},
  lost = [],
}: {
  title: string;
  showTitle?: boolean;
  traits: TraitOut[];
  allowed: Allowed;
  picks: Picks;
  onChange: (picks: Picks) => void;
  /** Group each slot's choices under headings, such as skills by attribute. */
  sections?: { order: string[]; of: (trait: TraitOut) => string | null };
  /** The field each picked Crafts, Performance or Science is for, by pick (see logic's `copyKey`). */
  details?: Record<string, string>;
  onDetail?: (name: string, detail: string) => void;
  /** Traits the rules do not allow this character, and why. */
  unavailable?: Record<string, string>;
  /** More on why a trait is refused: the traits it is because of, and where they are. */
  why?: (name: string) => ReactNode;
  /** Ratings a trait cannot be picked at, by trait: refused in those slots, saying why. */
  barredAt?: Record<string, RatingBar[]>;
  /** Traits merits give, held without a pick: not offered, and listed under the slots. */
  held?: Record<string, Held>;
  /** Picks kept where they no longer fit, and what to do: marked in their slot, never dropped. */
  marks?: Record<string, string>;
  /** Picks a trait held took away, by rating. */
  lost?: Lost[];
}) {
  const named = useClanName();
  // Where each pick sits, by rating, so choosing one doesn't shuffle the rest.
  const [seats, setSeats] = useState<Record<number, (string | null)[]>>({});
  // The field box to focus when it appears: that of the pick just chosen.
  const [focus, setFocus] = useState<string | null>(null);
  // Those marked to move go last, so a rating with too many keeps the ones that fit in its slots.
  const placedAt = (rating: number) =>
    Object.keys(picks)
      .filter((k) => picks[k] === rating)
      .sort((a, b) => Number(!!marks[traitOf(a)]) - Number(!!marks[traitOf(b)]));
  const ratings = [...new Set([...Object.keys(allowed).map(Number), ...Object.values(picks), ...lost.map((l) => l.rating)])].sort((a, b) => b - a);
  const layout = Object.fromEntries(ratings.map((r) => [r, seatPicks(seats[r] ?? [], placedAt(r), allowed[r] ?? 0)])) as Record<number, (string | null)[]>;
  const ranking = isRanking(allowed);
  const byName = new Map(traits.map((t) => [t.name, t]));
  const needOf = (name: string) => detailNeed(byName.get(name));
  const problems = onDetail ? fieldProblems(picks, details, needOf) : {};
  const one = oneOf(title);
  // Every row's slots start at one place: past the widest rating, as a number or pips.
  const { ratings: shown } = usePreferences();
  const widest = Math.max(1, ...Object.keys(allowed).map(Number), ...lost.map((l) => l.rating), ...Object.values(picks));
  const labelWidth = shown === "pips" ? pipsWidth(widest) : 1.5;
  const indent = { paddingLeft: `${labelWidth + 0.75}rem` };

  const place = (rating: number, slot: number, holder: string | null, name: string) => {
    const fielded = !!(onDetail && needOf(name));
    const chosen = choose(picks, allowed, rating, holder, name, fielded);
    if (chosen.picks === picks) return;
    const next = { ...layout, [rating]: layout[rating]!.map((k, i) => (i === slot ? chosen.key : k)) };
    // A ranked trait chosen from another slot leaves that slot to the one it swapped with.
    if (ranking && name in picks && picks[name] !== rating) next[picks[name]!] = (layout[picks[name]!] ?? []).map((k) => (k === name ? holder : k));
    setSeats(next);
    if (fielded && chosen.key) setFocus(chosen.key);
    onChange(chosen.picks);
  };

  /** What a slot at `rating` holding `holder` offers. */
  const options = (rating: number, holder: string | null): Choice[] =>
    traits.flatMap((t): Choice[] => {
      const mine = holder !== null && traitOf(holder) === t.name;
      const elsewhere = Object.keys(picks).filter((k) => traitOf(k) === t.name && k !== holder);
      if (!mine && held[t.name] && !elsewhere.length) return [];
      const fielded = !!(onDetail && detailNeed(t));
      let hint: string | undefined;
      if (!mine && elsewhere.length) {
        if (ranking) hint = `At ${picks[elsewhere[0]!]}: swaps`;
        else if (fielded) hint = "Another field";
        else return [];
      }
      const bars = (barredAt[t.name] ?? []).filter((b) => b.ratings.includes(rating));
      const refused = mine ? undefined : unavailable[t.name];
      const note: ReactNode = refused ? (
        <>
          {named(refused)}
          {why?.(t.name)}
        </>
      ) : !mine && bars.length ? (
        bars.map((b, i) => <span key={i}>{b.note}</span>)
      ) : undefined;
      return [{ trait: t, label: named(t.name), group: sections ? (sections.of(t) ?? "Other") : null, current: mine, disabled: !!note, note, hint }];
    });

  const left = picksLeft(picks, allowed);
  const toMove = ratings.some((r) => layout[r]!.length > (allowed[r] ?? 0));
  // Somewhere to move a pick to: not so for a category a trait held left with no picks (Stolen Potential's focus).
  const anywhere = Object.values(allowed).some((n) => n > 0);
  const move = anywhere ? " Clear it and place it on another." : "";
  const heldHere = Object.entries(held).filter(([name]) => !Object.keys(picks).some((k) => traitOf(k) === name));

  return (
    <section aria-label={title} className="flex flex-col gap-3">
      {showTitle && <h3 className="text-base text-gold">{title}</h3>}
      {ratings.map((rating) => {
        const slots = allowed[rating] ?? 0;
        const row = layout[rating]!;
        const extras = row.length - slots;
        const gone = lost.filter((l) => l.rating === rating);
        const ghosts = Math.max(0, gone.reduce((n, l) => n + l.picks, 0) - extras);
        return (
          <div key={rating} role="group" aria-label={`${title} at ${rating}`} className="flex items-start gap-3">
            <span className="shrink-0 pt-3 text-right text-gold" style={{ width: `${labelWidth}rem` }}>
              <Rating value={rating} of={rating} className={shown === "pips" ? "text-sm leading-none" : "font-display text-base leading-none"} />
            </span>
            <ul className="grid min-w-0 flex-1 grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-2">
              {row.map((key, i) => {
                const name = key === null ? null : traitOf(key);
                const need = name ? needOf(name) : null;
                const mark = name ? marks[name] : undefined;
                const label = `${title} at ${rating}${slots > 1 ? `, pick ${i + 1} of ${slots}` : ""}`;
                if (i >= slots) {
                  return (
                    <li key={`extra-${key}`} className="col-span-full flex flex-col gap-1">
                      <div className="flex min-h-10 max-w-xs items-center justify-between gap-2 rounded-md border border-blood bg-night py-1 pr-1 pl-3 text-sm text-parchment">
                        <span className="min-w-0 truncate">{named(name!)}</span>
                        <ClearButton pick={key!} onClear={() => onChange(clear(picks, key!))} />
                      </div>
                      <p className="text-xs text-blood-bright">
                        {mark ? `${named(mark)}${move}` : `No pick at ${rating} for it now.${move}`}
                      </p>
                    </li>
                  );
                }
                return (
                  <li key={`slot-${i}`} className="flex min-w-0 flex-col gap-1">
                    <TraitChoice
                      label={label}
                      placeholder={`Choose ${one}`}
                      value={name ? named(name) : ""}
                      marked={!!mark}
                      choices={options(rating, key)}
                      onChoose={(chosen) => place(rating, i, key, chosen)}
                      onClear={key ? () => onChange(clear(picks, key)) : undefined}
                      pick={key}
                    />
                    {key && need && onDetail && (
                      <Input
                        aria-label={`${key} ${need.kind}`}
                        placeholder={need.placeholder}
                        autoFocus={focus === key}
                        value={details[key] ?? ""}
                        onChange={(e) => onDetail(key, e.target.value)}
                        className="h-9 min-h-9 py-0 text-sm"
                      />
                    )}
                    {mark && <p className="text-xs text-blood-bright">{`${named(mark)}${move}`}</p>}
                    {key && problems[key] && <p className="text-xs text-blood-bright">{problems[key].message}</p>}
                  </li>
                );
              })}
              {Array.from({ length: ghosts }, (_, i) => (
                <li key={`lost-${i}`} className="flex min-h-10 flex-col justify-center rounded-md border border-dashed border-line px-3 py-1.5 text-xs text-mist">
                  <span className="text-parchment">Taken away</span>
                  {gone[0]?.why}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      <p className="text-sm text-mist" style={indent} aria-live="polite">
        {left ?? (anywhere && !toMove ? "Every pick placed." : null)}
      </p>
      {heldHere.length > 0 && (
        <ul aria-label={`${title} held without a pick`} className="flex flex-col gap-1" style={indent}>
          {heldHere.map(([name, gift]) => (
            <li key={name} className="flex items-baseline gap-2 text-xs text-gold">
              <span className="text-sm text-parchment">{named(name)}</span>
              <Rating value={gift.rating} of={gift.rating} className="text-xs text-parchment" />
              <span>{gift.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** How wide `n` pips are at text-sm, in rem: 0.7em each, 0.12em apart, and 0.35em between fives (ui.tsx's Pips). */
function pipsWidth(n: number): number {
  const fives = Math.ceil(n / 5);
  return (n * 0.7 + (n - fives) * 0.12 + (fives - 1) * 0.35) * 0.875 + 0.05;
}

/** One trait a slot offers: greyed with `note` saying why when it can't be chosen. */
type Choice = { trait: TraitOut; label: string; group: string | null; current: boolean; disabled: boolean; note?: ReactNode; hint?: string };

function ClearButton({ pick, onClear }: { pick: string; onClear: () => void }) {
  return (
    <button
      type="button"
      aria-label={`Clear ${pick}`}
      onClick={onClear}
      className="grid h-8 w-8 shrink-0 place-items-center rounded text-mist hover:bg-ash hover:text-parchment pointer-coarse:h-10 pointer-coarse:w-10"
    >
      <span aria-hidden>×</span>
    </button>
  );
}

/**
 * A slot's choice: a box that opens a list of the traits as soon as it is tapped,
 * typing narrowing it. Traits that can't be chosen stay listed, greyed, saying why;
 * each one's description opens from the list. The list fits the screen's width, so
 * it works on a phone.
 */
function TraitChoice({
  label,
  placeholder,
  value,
  marked,
  choices,
  onChoose,
  onClear,
  pick: held,
}: {
  label: string;
  placeholder: string;
  value: string;
  marked: boolean;
  choices: Choice[];
  onChoose: (name: string) => void;
  onClear?: () => void;
  /** The pick in the slot (see logic's `copyKey`), which Clear takes back. */
  pick: string | null;
}) {
  const named = useClanName();
  const listId = useId();
  const inputId = `${listId}-box`;
  const list = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  // What is typed while the list is open; the choice shows otherwise.
  const [typed, setTyped] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const [about, setAbout] = useState<string | null>(null);
  const [place, setPlace] = useState<CSSProperties>({});
  const closing = useRef<ReturnType<typeof setTimeout>>(undefined);
  const q = (typed ?? "").trim().toLowerCase();
  const shown = choices.filter((c) => !q || withClanNames(c.trait.name).toLowerCase().includes(q) || c.label.toLowerCase().includes(q));
  const pickable = shown.filter((c) => !c.disabled);
  const groups = [...new Set(shown.map((c) => c.group))];

  const show = () => {
    clearTimeout(closing.current);
    setOpen(true);
  };
  const close = () => {
    setOpen(false);
    setTyped(null);
    setActive(-1);
    setAbout(null);
  };
  const pick = (c: Choice) => {
    if (c.disabled) return;
    close();
    if (!c.current) onChoose(c.trait.name);
  };

  // As wide as the screen allows, and kept on it: a slot at the right of a row opens leftwards.
  useLayoutEffect(() => {
    const box = open ? document.getElementById(inputId)?.getBoundingClientRect() : undefined;
    if (!box) return;
    const width = Math.min(352, window.innerWidth - 32);
    setPlace({ width, left: Math.min(0, window.innerWidth - 16 - (box.left + width)) });
  }, [open, inputId]);
  useEffect(() => {
    if (open) list.current?.scrollIntoView?.({ block: "nearest" });
  }, [open]);
  useEffect(() => {
    if (active >= 0) document.getElementById(`${listId}-${active}`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, listId]);

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) return show();
      if (!pickable.length) return;
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((active + step + pickable.length) % pickable.length);
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      const c = pickable[active] ?? (pickable.length === 1 ? pickable[0] : undefined);
      if (c) pick(c);
    } else if (e.key === "Escape") {
      close();
    }
  };

  return (
    <div className="relative">
      <Input
        id={inputId}
        role="combobox"
        aria-label={label}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        spellCheck={false}
        enterKeyHint="done"
        placeholder={placeholder}
        value={typed ?? value}
        title={value || undefined}
        className={`text-sm ${held ? "pr-10" : "pr-8"} ${marked ? "border-blood" : value ? "" : "border-dashed"}`}
        onChange={(e) => {
          setTyped(e.target.value);
          setActive(-1);
          show();
        }}
        onFocus={(e) => {
          show();
          e.currentTarget.select();
        }}
        onClick={show}
        // Late enough that a tap in the list lands first; coming back to the box keeps it open.
        onBlur={() => {
          closing.current = setTimeout(close, 150);
        }}
        onKeyDown={onKeyDown}
      />
      <span className="absolute top-1/2 right-1 flex -translate-y-1/2 items-center">
        {onClear && held ? (
          <ClearButton pick={held} onClear={onClear} />
        ) : (
          <span aria-hidden className="pointer-events-none px-1.5 text-xs text-mist">
            ▾
          </span>
        )}
      </span>
      {open && (
        <div
          ref={list}
          style={place}
          // Keeps the box focused while the list is tapped or scrolled.
          onMouseDown={(e) => e.preventDefault()}
          className="absolute z-20 mt-1 max-h-80 overflow-y-auto rounded-md border border-ash bg-dusk py-1 shadow-lg"
        >
          <ul id={listId} role="listbox" aria-label={label}>
            {groups.map((group) => (
              <li key={group ?? "all"} role="presentation">
                {group && groups.length > 1 && <p className="px-3 pt-2 pb-1 font-sans text-xs tracking-wide text-mist uppercase">{group}</p>}
                <ul role="presentation">
                  {shown
                    .filter((c) => c.group === group)
                    .map((c) => {
                      const index = pickable.indexOf(c);
                      const described = !!(bookSummary(c.trait.description, c.trait.changed) || c.trait.changed);
                      const opened = about === c.trait.name;
                      const aboutId = `${listId}-about-${c.trait.name}`.replace(/\W+/g, "-");
                      const noteId = `${listId}-why-${c.trait.name}`.replace(/\W+/g, "-");
                      return (
                        <li key={c.trait.name} role="presentation" data-choice={c.trait.name} className="flex flex-wrap items-start">
                          <div
                            id={index >= 0 ? `${listId}-${index}` : undefined}
                            role="option"
                            aria-label={c.label}
                            aria-selected={c.current}
                            aria-disabled={c.disabled || undefined}
                            aria-describedby={c.note ? noteId : undefined}
                            onClick={() => pick(c)}
                            className={`min-w-0 flex-1 px-3 py-2 text-sm pointer-coarse:py-2.5 ${
                              c.disabled ? "cursor-not-allowed text-line" : index === active ? "cursor-pointer bg-gold/20 text-gold" : "cursor-pointer hover:bg-night"
                            }`}
                          >
                            <span className={c.current ? "text-gold" : c.disabled ? "" : "text-parchment"}>
                              {c.label}
                              {c.current && <span className="sr-only"> (chosen)</span>}
                            </span>
                            {c.hint && <span className="ml-2 text-xs text-mist">{c.hint}</span>}
                          </div>
                          {described && (
                            <button
                              type="button"
                              aria-label={`About ${c.label}`}
                              aria-expanded={opened}
                              aria-controls={aboutId}
                              onClick={() => setAbout(opened ? null : c.trait.name)}
                              className="mt-1 mr-1 grid h-8 w-8 place-items-center rounded text-mist hover:bg-ash hover:text-parchment pointer-coarse:h-10 pointer-coarse:w-10"
                            >
                              <svg viewBox="0 0 20 20" aria-hidden className={`h-4 w-4 transition-transform ${opened ? "rotate-90" : ""}`}>
                                <path d="M7.5 4.5 13 10l-5.5 5.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            </button>
                          )}
                          {/* Beside the option, not in it: its links (to the step a refusal is because of) stay links. */}
                          {c.note && (
                            <p id={noteId} className="-mt-1.5 basis-full px-3 pb-2 text-xs text-blood-bright">
                              {c.note}
                            </p>
                          )}
                          {opened && (
                            <div id={aboutId} className="basis-full px-3 pb-2 text-xs leading-relaxed text-mist">
                              {bookSummary(c.trait.description, c.trait.changed) && <p>{named(c.trait.description!)}</p>}
                              <HouseWording change={c.trait.changed} className="mt-1" />
                            </div>
                          )}
                        </li>
                      );
                    })}
                </ul>
              </li>
            ))}
          </ul>
          {shown.length === 0 && <p className="px-3 py-2 text-sm text-mist">Nothing by that name here.</p>}
        </div>
      )}
    </div>
  );
}

import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { withClanNames } from "../../../clanNames";
import { useClanName } from "../../../components/ClanNames";
import type { TraitOut } from "../../../api/types";
import { Input, Rating } from "../../../components/ui";
import { usePreferences } from "../../../hooks";
import { HouseWording } from "../../../components/TroupeChange";
import { bookSummary } from "../../../houseWording";
import { detailNeed } from "../fields";
import { choose, clear, fieldProblems, move, picksLeft, seatPicks, traitOf, type Allowed, type Picks } from "./logic";
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
 * A slot offers only what it can take: a trait held without a pick (a merit's free
 * dots) is left out, and one the rules refuse is there, greyed, saying why. A trait
 * picked at another rating is offered marked with where it is, "Brawl (at 3)", and
 * choosing it moves it: the trait in the slot goes to the one it left when it fits
 * there (a swap), or is taken off, saying so. A pick with dots bought on top can't
 * move, and one that no longer meets its restriction (in-clan) isn't offered
 * elsewhere. Picks the rules no longer give a slot for are kept, after the slots,
 * marked to move; a slot a trait held took away says what took it.
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
  bought = new Set(),
  misfits = new Set(),
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
  /** Picks with dots bought on top, by key: they can't move until those are undone. */
  bought?: Set<string>;
  /** Traits whose picks no longer meet their restriction (in-clan): kept, but not offered in other slots. */
  misfits?: Set<string>;
}) {
  const named = useClanName();
  // Where each pick sits, by rating, so choosing one doesn't shuffle the rest.
  const [seats, setSeats] = useState<Record<number, (string | null)[]>>({});
  // The field box to focus when it appears: that of the pick just chosen.
  const [focus, setFocus] = useState<string | null>(null);
  // What a move did that wasn't asked for (a pick taken off), under the slot it was made in.
  const [said, setSaid] = useState<{ rating: number; slot: number; text: string } | null>(null);
  // Those marked to move go last, so a rating with too many keeps the ones that fit in its slots.
  const placedAt = (rating: number) =>
    Object.keys(picks)
      .filter((k) => picks[k] === rating)
      .sort((a, b) => Number(!!marks[traitOf(a)]) - Number(!!marks[traitOf(b)]));
  const ratings = [...new Set([...Object.keys(allowed).map(Number), ...Object.values(picks), ...lost.map((l) => l.rating)])].sort((a, b) => b - a);
  const layout = Object.fromEntries(ratings.map((r) => [r, seatPicks(seats[r] ?? [], placedAt(r), allowed[r] ?? 0)])) as Record<number, (string | null)[]>;
  const byName = new Map(traits.map((t) => [t.name, t]));
  const needOf = (name: string) => detailNeed(byName.get(name));
  const problems = onDetail ? fieldProblems(picks, details, needOf) : {};
  const one = oneOf(title);
  // A pick by its trait, and its field when it has one: "Performance: Singing".
  const pickName = (key: string) => named(details[key]?.trim() ? `${traitOf(key)}: ${details[key]!.trim()}` : traitOf(key));
  const undoFirst = (key: string) => `Undo the dots bought for ${named(traitOf(key))} first.`;
  // Where a trait the move displaces could go: allowed, and not barred at that rating.
  const fitsAt = (name: string, rating: number) =>
    !misfits.has(name) && !unavailable[name] && !(barredAt[name] ?? []).some((b) => b.ratings.includes(rating));

  const place = (rating: number, slot: number, holder: string | null, value: string) => {
    const [how, chosen] = [value.slice(0, value.indexOf(":")), value.slice(value.indexOf(":") + 1)];
    const next = { ...layout };
    let result: { picks: Picks; key: string | null };
    if (how === "move") {
      const from = picks[chosen]!;
      const moved = move(picks, allowed, rating, holder, chosen, fitsAt);
      if (moved.picks === picks) return;
      // The slot the pick left takes the one it swapped with, or is left empty.
      next[from] = (layout[from] ?? []).map((k) => (k === chosen ? (moved.holder === "swapped" ? holder : null) : k));
      setSaid(
        moved.holder === "off"
          ? { rating, slot, text: `${pickName(holder!)} can't go at ${from}, so it is taken off, and the slot at ${from} is left empty.` }
          : null,
      );
      result = moved;
    } else {
      const fielded = !!(onDetail && needOf(chosen));
      result = choose(picks, allowed, rating, holder, chosen, fielded);
      if (result.picks === picks) return;
      if (fielded && result.key) setFocus(result.key);
      setSaid(null);
    }
    next[rating] = next[rating]!.map((k, i) => (i === slot ? result.key : k));
    setSeats(next);
    onChange(result.picks);
  };
  const takeBack = (key: string) => {
    setSaid(null);
    onChange(clear(picks, key));
  };

  /** What a slot at `rating` holding `holder` offers. */
  const options = (rating: number, holder: string | null): Choice[] =>
    traits.flatMap((t): Choice[] => {
      const mine = holder !== null && traitOf(holder) === t.name;
      const others = Object.keys(picks).filter((k) => traitOf(k) === t.name && k !== holder);
      if (!mine && held[t.name] && !others.length) return [];
      const fielded = !!(onDetail && detailNeed(t));
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
      const group = sections ? (sections.of(t) ?? "Other") : null;
      // Each pick of it at another rating, to move here; not one in this row's other slots.
      const moves = mine || misfits.has(t.name) ? [] : others.filter((k) => picks[k] !== rating);
      const choices = moves.map(
        (k): Choice => ({
          value: `move:${k}`,
          name: t.name,
          trait: t,
          label: pickName(k),
          at: picks[k],
          group,
          current: false,
          disabled: !!note || bought.has(k),
          note: note ?? (bought.has(k) ? undoFirst(k) : undefined),
        }),
      );
      // A new pick: of a trait not picked yet, or another field of one that is.
      if (mine || !others.length || fielded) {
        const hint = !mine && others.length ? "Another field" : undefined;
        choices.push({ value: `pick:${t.name}`, name: t.name, trait: t, label: named(t.name), group, current: mine, disabled: !!note, note, hint });
      }
      return choices;
    });

  const left = picksLeft(picks, allowed);
  const toMove = ratings.some((r) => layout[r]!.length > (allowed[r] ?? 0));
  // Somewhere to move a pick to: not so for a category a trait held left with no picks (Stolen Potential's focus).
  const anywhere = Object.values(allowed).some((n) => n > 0);
  const moveIt = anywhere ? " Clear it and place it on another." : "";
  const heldHere = Object.entries(held).filter(([name]) => !Object.keys(picks).some((k) => traitOf(k) === name));
  const widest = Math.max(1, ...Object.keys(allowed).map(Number), ...lost.map((l) => l.rating), ...Object.values(picks));

  return (
    <SlotRows
      title={title}
      showTitle={showTitle}
      widest={widest}
      rows={ratings.map((rating) => {
        const slots = allowed[rating] ?? 0;
        const row = layout[rating]!;
        const extras = row.length - slots;
        const gone = lost.filter((l) => l.rating === rating);
        const ghosts = Math.max(0, gone.reduce((n, l) => n + l.picks, 0) - extras);
        return {
          rating,
          slots: (
            <>
              {row.map((key, i) => {
                const name = key === null ? null : traitOf(key);
                const need = name ? needOf(name) : null;
                const mark = name ? marks[name] : undefined;
                if (i >= slots) {
                  return (
                    <ExtraPick key={`extra-${key}`} value={named(name!)} pick={key!} onClear={() => takeBack(key!)}>
                      {mark ? `${named(mark)}${moveIt}` : `No pick at ${rating} for it now.${moveIt}`}
                    </ExtraPick>
                  );
                }
                return (
                  <Slot
                    key={`slot-${i}`}
                    label={`${title} at ${rating}${slots > 1 ? `, pick ${i + 1} of ${slots}` : ""}`}
                    placeholder={`Choose ${one}`}
                    value={name ? named(name) : ""}
                    marked={!!mark}
                    choices={options(rating, key)}
                    locked={key && bought.has(key) ? undoFirst(key) : undefined}
                    onChoose={(value) => place(rating, i, key, value)}
                    onClear={key ? () => takeBack(key) : undefined}
                    pick={key}
                  >
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
                    {mark && <p className="text-xs text-blood-bright">{`${named(mark)}${moveIt}`}</p>}
                    {key && problems[key] && <p className="text-xs text-blood-bright">{problems[key].message}</p>}
                    {said?.rating === rating && said.slot === i && <p className="text-xs text-mist">{said.text}</p>}
                  </Slot>
                );
              })}
              {Array.from({ length: ghosts }, (_, i) => (
                <li key={`lost-${i}`} className="flex min-h-10 flex-col justify-center rounded-md border border-dashed border-line px-3 py-1.5 text-xs text-mist">
                  <span className="text-parchment">Taken away</span>
                  {gone[0]?.why}
                </li>
              ))}
            </>
          ),
        };
      })}
      after={(indent) => (
        <>
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
        </>
      )}
    />
  );
}

/**
 * Rows of slots, one for each rating, the rating beside each as Settings shows
 * ratings (a number or pips). Every row's slots start at one place, past the widest
 * rating; `after` lines up under them. Each row's `slots` are its `Slot`s.
 */
export function SlotRows({
  title,
  showTitle = true,
  label = title,
  heading = true,
  widest,
  rows,
  after,
}: {
  title: string;
  showTitle?: boolean;
  /** Whether the title is a heading: not where the page has headings by that name (an NPC's sheet has a Skills card). */
  heading?: boolean;
  /** What the rows are called, for a screen reader, where the title alone would be ambiguous. */
  label?: string;
  widest: number;
  rows: { rating: number; slots: ReactNode }[];
  after?: (indent: CSSProperties) => ReactNode;
}) {
  const { ratings: shown } = usePreferences();
  const labelWidth = shown === "pips" ? pipsWidth(widest) : 1.5;
  return (
    <section aria-label={label} className="flex flex-col gap-3">
      {showTitle && (heading ? <h3 className="text-base text-gold">{title}</h3> : <p className="text-base text-gold">{title}</p>)}
      {rows.map(({ rating, slots }) => (
        <div key={rating} role="group" aria-label={`${title} at ${rating}`} className="flex items-start gap-3">
          <span className="shrink-0 pt-3 text-right text-gold" style={{ width: `${labelWidth}rem` }}>
            <Rating value={rating} of={rating} className={shown === "pips" ? "text-sm leading-none" : "font-display text-base leading-none"} />
          </span>
          <ul className="grid min-w-0 flex-1 grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-2">{slots}</ul>
        </div>
      ))}
      {after?.({ paddingLeft: `${labelWidth + 0.75}rem` })}
    </section>
  );
}

/** One slot in a row: its choice, and what goes under it (a field, a note). */
export function Slot({ children, ...choice }: Parameters<typeof TraitChoice>[0] & { children?: ReactNode }) {
  return (
    <li className="flex min-w-0 flex-col gap-1">
      <TraitChoice {...choice} />
      {children}
    </li>
  );
}

/** A pick beyond a row's slots (the rules give fewer now): kept, to be moved or cleared, and why. */
export function ExtraPick({ value, pick, onClear, clearLabel, children }: { value: string; pick: string; onClear: () => void; clearLabel?: string; children: ReactNode }) {
  return (
    <li className="col-span-full flex flex-col gap-1">
      <div className="flex min-h-10 max-w-xs items-center justify-between gap-2 rounded-md border border-blood bg-night py-1 pr-1 pl-3 text-sm text-parchment">
        <span className="min-w-0 truncate">{value}</span>
        <ClearButton label={clearLabel ?? `Clear ${pick}`} onClear={onClear} />
      </div>
      <p className="text-xs text-blood-bright">{children}</p>
    </li>
  );
}

/** How wide `n` pips are at text-sm, in rem: 0.7em each, 0.12em apart, and 0.35em between fives (ui.tsx's Pips). */
function pipsWidth(n: number): number {
  const fives = Math.ceil(n / 5);
  return (n * 0.7 + (n - fives) * 0.12 + (fives - 1) * 0.35) * 0.875 + 0.05;
}

/**
 * One trait a slot offers: greyed with `note` saying why when it can't be chosen.
 * `value` is what choosing it gives the slot's `onChoose`; `at` is the rating the
 * trait is picked at elsewhere, shown as "Brawl (at 3)", for a choice that moves it.
 */
export type Choice = {
  value: string;
  /** The trait's name, which typing finds it by. */
  name: string;
  label: string;
  group: string | null;
  current: boolean;
  disabled: boolean;
  note?: ReactNode;
  hint?: ReactNode;
  at?: number;
  /** The trait, for its description. */
  trait?: TraitOut;
};

function ClearButton({ label, onClear, disabled }: { label: string; onClear: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClear}
      disabled={disabled}
      className="grid h-8 w-8 shrink-0 place-items-center rounded text-mist hover:bg-ash hover:text-parchment disabled:opacity-50 pointer-coarse:h-10 pointer-coarse:w-10"
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
export function TraitChoice({
  label,
  placeholder,
  value,
  marked = false,
  choices,
  onChoose,
  onClear,
  clearLabel,
  pick: held,
  locked,
  disabled = false,
}: {
  label: string;
  placeholder: string;
  value: string;
  marked?: boolean;
  choices: Choice[];
  onChoose: (value: string) => void;
  onClear?: () => void;
  /** What the clear button says; "Clear Brawl" unless told. */
  clearLabel?: string;
  /** The pick in the slot (see logic's `copyKey`), which Clear takes back. */
  pick: string | null;
  /** Why the pick in the slot can't change now: every other choice is greyed, saying so. */
  locked?: string;
  disabled?: boolean;
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
  const offered = locked ? choices.map((c) => (c.current ? c : { ...c, disabled: true, note: undefined })) : choices;
  const shown = offered.filter((c) => !q || withClanNames(c.name).toLowerCase().includes(q) || c.label.toLowerCase().includes(q));
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
    if (!c.current) onChoose(c.value);
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
        disabled={disabled}
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
          <ClearButton label={clearLabel ?? `Clear ${held}`} onClear={onClear} disabled={disabled} />
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
          {locked && <p className="border-b border-ash px-3 py-2 text-xs text-blood-bright">{locked}</p>}
          <ul id={listId} role="listbox" aria-label={label}>
            {groups.map((group) => (
              <li key={group ?? "all"} role="presentation">
                {group && groups.length > 1 && <p className="px-3 pt-2 pb-1 font-sans text-xs tracking-wide text-mist uppercase">{group}</p>}
                <ul role="presentation">
                  {shown
                    .filter((c) => c.group === group)
                    .map((c) => {
                      const index = pickable.indexOf(c);
                      const trait = c.trait;
                      const described = !!trait && !!(bookSummary(trait.description, trait.changed) || trait.changed);
                      const opened = about === c.value;
                      const aboutId = `${listId}-about-${c.value}`.replace(/\W+/g, "-");
                      const noteId = `${listId}-why-${c.value}`.replace(/\W+/g, "-");
                      const name = c.at === undefined ? c.label : `${c.label} (at ${c.at})`;
                      return (
                        <li key={c.value} role="presentation" data-choice={c.name} className="flex flex-wrap items-start">
                          <div
                            id={index >= 0 ? `${listId}-${index}` : undefined}
                            role="option"
                            aria-label={name}
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
                            {c.at !== undefined && <span className={`ml-1 ${c.disabled ? "" : "text-mist"}`}>(at {c.at})</span>}
                            {c.hint && <span className="ml-2 text-xs text-mist">{c.hint}</span>}
                          </div>
                          {described && (
                            <button
                              type="button"
                              aria-label={`About ${c.label}`}
                              aria-expanded={opened}
                              aria-controls={aboutId}
                              onClick={() => setAbout(opened ? null : c.value)}
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
                          {opened && trait && (
                            <div id={aboutId} className="basis-full px-3 pb-2 text-xs leading-relaxed text-mist">
                              {bookSummary(trait.description, trait.changed) && <p>{named(trait.description!)}</p>}
                              <HouseWording change={trait.changed} className="mt-1" />
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

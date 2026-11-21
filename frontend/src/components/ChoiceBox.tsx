import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import type { TraitOut } from "../api/types";
import { withClanNames } from "../clanNames";
import { bookSummary, wordingOf } from "../houseWording";
import { AboutButton, AboutTrait, hasAbout } from "./AboutTrait";
import { useClanName } from "./ClanNames";
import { ClanWeakness } from "./ClanWeakness";
import { Input } from "./ui";
import { pageLabel } from "./TraitInfo";

/**
 * One choice in a `ChoiceBox`. `note` says why the character can't usually take it:
 * the choice is greyed, saying so under its name. A `disabled` one can't be chosen
 * (a player's); one that isn't still can be (staff building an NPC need no one's
 * approval). `mark` is a short word beside it, such as "in-clan".
 */
export type BoxChoice = {
  value: string;
  label: string;
  /** The trait's own name, which typing finds it by too, where the label is more ("Performance: Singing"). */
  name?: string;
  /** The trait, for its line under the name and its detail. */
  trait?: TraitOut;
  /** Its line under the name, in place of the trait's. */
  summary?: string | null;
  group?: string | null;
  mark?: string;
  /** Why it can't usually be taken, under its name; it may link to where (the step a refusal is because of). */
  note?: ReactNode;
  disabled?: boolean;
  /** The choice made, where the label alone doesn't say (two picks of one trait). */
  current?: boolean;
  /** The rating it is picked at elsewhere, for one that moves from there: "Brawl (at 3)". */
  at?: number;
  /** A short aside after its name: a fixed rating, what it needs, the troupe's mark. */
  hint?: ReactNode;
  /** What opens it to the character, in gold in place of its line: "Hard as Steel: 20 XP". */
  offer?: string;
  /** Something to do with one that can't be chosen, under its note: "Ask staff". Enter does it too. */
  action?: { label: string; run: () => void };
  /** The discipline dots its detail gives the powers of: the next dot, or those a pick at a rating gives. */
  dots?: { from: number; to?: number };
};

/** A choice's name as the list shows it and a screen reader says it: "Brawl (at 3)". */
const nameOf = (c: BoxChoice, named: (name: string) => string) => (c.at === undefined ? named(c.label) : `${named(c.label)} (at ${c.at})`);

/**
 * What a trait does in one line, for the list to choose from: the troupe's own
 * summary, else the book's (unless the troupe's wording replaces it), else the
 * troupe's wording; for a clan, its in-clan disciplines.
 */
export function oneLine(trait: TraitOut | undefined): string | null {
  if (!trait) return null;
  if (trait.in_clan?.length) return `In-clan: ${trait.in_clan.join(", ")}`;
  return trait.house?.summary || bookSummary(trait.description, trait.changed) || wordingOf(trait.changed)?.wording || null;
}

/**
 * A searchable drop-down that explains each choice while picking (#1039): a box that
 * opens its list when tapped, typing narrowing it; each choice with what it does in
 * a line under its name and its page, and the highlighted one's detail (the same as
 * `AboutTrait` shows: the book's summary, the troupe's wording and house rule, a
 * discipline's powers; a clan's in-clan disciplines and weakness) under the list.
 * Arrow keys move the highlight and Enter chooses; on a touch screen each choice's
 * chevron shows its detail without choosing it. The list is as wide as a phone's
 * screen allows.
 *
 * With `value`, it shows the choice made, as a select does; without, it is a search
 * to add, emptied once a choice is made. It is the one way of choosing a trait from
 * a list: the NPC editor's, the creation wizard's slots and Concept's choices, the
 * sheet's Add panel and staff's Give panel.
 */
export function ChoiceBox({
  id,
  label,
  placeholder,
  value,
  choices,
  onChoose,
  onOpen,
  splat,
  troupeId,
  notice,
  footer,
  empty = "Nothing by that name here.",
  onType,
  trailing,
  disabled = false,
  className = "",
  inputClassName = "",
  "aria-describedby": describedBy,
}: {
  id?: string;
  /** Its name, where no `Field` labels it. */
  label?: string;
  placeholder: string;
  /** The label of the choice made; leave it out for a search to add. */
  value?: string;
  choices: BoxChoice[];
  onChoose: (value: string) => void;
  /** Told when the list opens and closes, so the caller can ask what is refused only then. */
  onOpen?: (open: boolean) => void;
  /** The rule set's splat, for a discipline's powers. */
  splat?: string;
  /** The troupe whose written rules about a trait are linked. */
  troupeId?: string | null;
  /** A line above the list, such as why the choice made can't change now. */
  notice?: ReactNode;
  /** What goes under the list, in it: a search's "found in another category", or that it is still checking. */
  footer?: ReactNode;
  /** What shows when nothing matches; null for nothing, where `footer` says it. */
  empty?: ReactNode;
  /** Told what is typed as it is, and "" once the list closes. */
  onType?: (typed: string) => void;
  /** In place of the ▾ at the box's right: a button to clear the choice made. */
  trailing?: ReactNode;
  disabled?: boolean;
  className?: string;
  inputClassName?: string;
  "aria-describedby"?: string;
}) {
  const named = useClanName();
  const ownId = useId();
  const inputId = id ?? `${ownId}-box`;
  const listId = `${ownId}-list`;
  const detailId = `${ownId}-detail`;
  const popup = useRef<HTMLDivElement>(null);
  const listbox = useRef<HTMLUListElement>(null);
  // Whether the highlight moved by key, so the list follows it; a hover leaves the list where it is.
  const byKey = useRef(false);
  const [open, setOpen] = useState(false);
  // What is typed while the list is open; the choice made shows otherwise.
  const [typed, setTyped] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const [place, setPlace] = useState<CSSProperties>({});
  const closing = useRef<ReturnType<typeof setTimeout>>(undefined);
  const q = (typed ?? "").trim().toLowerCase();
  const finds = (text: string) => withClanNames(text).toLowerCase().includes(q) || named(text).toLowerCase().includes(q);
  const shown = choices.filter((c) => !q || finds(c.label) || (!!c.name && finds(c.name)));
  const groupsOf = (list: BoxChoice[]) => [...new Set(list.map((c) => c.group ?? null))];
  const groups = groupsOf(shown);
  // In the order the list shows them, for the arrow keys.
  const inOrder = (list: BoxChoice[]) => groupsOf(list).flatMap((g) => list.filter((c) => (c.group ?? null) === g));
  const ordered = inOrder(shown);
  const lit = ordered[active];
  const isCurrent = (c: BoxChoice) => c.current ?? (!!value && c.label === value);

  const show = () => {
    clearTimeout(closing.current);
    if (open) return;
    setOpen(true);
    onOpen?.(true);
    // The choice made is highlighted, its detail showing: nothing is typed yet, so every choice is listed.
    setActive(inOrder(choices).findIndex(isCurrent));
  };
  const close = () => {
    setOpen(false);
    setTyped(null);
    setActive(-1);
    onOpen?.(false);
    onType?.("");
  };
  const choose = (c: BoxChoice) => {
    if (c.disabled) return;
    close();
    if (!isCurrent(c)) onChoose(c.value);
  };
  const act = (c: BoxChoice) => {
    close();
    c.action?.run();
  };

  // As wide as the screen allows, and kept on it: a box at the right of a card opens leftwards.
  // Placed again if the screen changes while it is open (a phone turned on its side).
  useLayoutEffect(() => {
    if (!open) return;
    const fit = () => {
      const box = document.getElementById(inputId)?.getBoundingClientRect();
      if (!box) return;
      // The page's own width: a phone's innerWidth grows with anything that overflows it.
      const screen = Math.min(window.innerWidth, document.documentElement.clientWidth || window.innerWidth);
      const width = Math.min(Math.max(box.width, 448), screen - 32);
      setPlace({ width, left: Math.max(16 - box.left, Math.min(0, screen - 16 - (box.left + width))) });
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [open, inputId]);
  useEffect(() => {
    if (open) popup.current?.scrollIntoView?.({ block: "nearest" });
  }, [open]);
  // The list alone scrolls to the highlight, never the page, which would move the list under the pointer.
  useEffect(() => {
    const row = open && active >= 0 && byKey.current ? document.getElementById(`${listId}-${active}`) : null;
    const box = listbox.current;
    byKey.current = false;
    if (!row || !box) return;
    // The list is the row's offset parent (it is `relative`).
    const top = row.offsetTop;
    if (top < box.scrollTop) box.scrollTop = top;
    else if (top + row.offsetHeight > box.scrollTop + box.clientHeight) box.scrollTop = top + row.offsetHeight - box.clientHeight;
  }, [open, active, listId]);

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) return show();
      if (!ordered.length) return;
      const step = e.key === "ArrowDown" ? 1 : -1;
      byKey.current = true;
      setActive((active + step + ordered.length) % ordered.length);
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      const pickable = ordered.filter((c) => !c.disabled);
      const c = lit ?? (pickable.length === 1 ? pickable[0] : undefined);
      if (c?.disabled && c.action) act(c);
      else if (c) choose(c);
    } else if (e.key === "Escape" && open) {
      e.preventDefault();
      close();
    }
  };

  return (
    <div className={`relative ${className}`}>
      <Input
        id={inputId}
        role="combobox"
        aria-label={label}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        aria-describedby={describedBy}
        autoComplete="off"
        spellCheck={false}
        enterKeyHint="done"
        placeholder={placeholder}
        value={typed ?? (value ? named(value) : "")}
        disabled={disabled}
        className={`text-sm ${trailing ? "pr-10" : "pr-8"} ${inputClassName}`}
        onChange={(e) => {
          setTyped(e.target.value);
          setActive(-1);
          onType?.(e.target.value);
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
      {trailing ? (
        <span className="absolute top-1/2 right-1 flex -translate-y-1/2 items-center">{trailing}</span>
      ) : (
        <span aria-hidden className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-xs text-mist">
          ▾
        </span>
      )}
      {open && (
        <div
          ref={popup}
          style={place}
          // Keeps the box focused while the list is tapped or scrolled.
          onMouseDown={(e) => e.preventDefault()}
          // The box's width until it is measured, so its one-line summaries never widen the page.
          className="absolute z-20 mt-1 flex w-full flex-col overflow-hidden rounded-md border border-ash bg-dusk shadow-lg"
        >
          {notice && <p className="border-b border-ash px-3 py-2 text-xs text-blood-bright">{notice}</p>}
          <ul ref={listbox} id={listId} role="listbox" aria-label={label ?? placeholder} className="relative max-h-64 overflow-y-auto py-1">
            {groups.map((group) => (
              <li key={group ?? "all"} role="presentation">
                {group && groups.length > 1 && <p className="px-3 pt-2 pb-1 text-xs tracking-wide text-mist uppercase">{group}</p>}
                <ul role="presentation">
                  {shown
                    .filter((c) => (c.group ?? null) === group)
                    .map((c) => {
                      const index = ordered.indexOf(c);
                      const optionId = `${listId}-${index}`;
                      const line = c.summary !== undefined ? c.summary : oneLine(c.trait);
                      const page = pageLabel(c.trait?.page_reference);
                      const current = isCurrent(c);
                      const said = [c.mark && `${optionId}-mark`, c.note ? `${optionId}-note` : `${optionId}-line`].filter(Boolean).join(" ");
                      return (
                        <li key={c.value} role="presentation" data-choice={c.name ?? c.label} className="flex flex-wrap items-start">
                          <div
                            id={optionId}
                            role="option"
                            aria-label={nameOf(c, named)}
                            aria-selected={current}
                            aria-disabled={c.disabled || undefined}
                            aria-describedby={said}
                            onClick={() => choose(c)}
                            onMouseEnter={() => setActive(index)}
                            className={`min-w-0 flex-1 px-3 py-1.5 pointer-coarse:min-h-10 pointer-coarse:py-2 ${c.disabled ? "cursor-not-allowed" : "cursor-pointer"} ${index === active ? "bg-gold/15" : "hover:bg-night"}`}
                          >
                            <span className="flex items-baseline gap-2">
                              <span className={`text-sm ${current ? "text-gold" : c.disabled ? "text-line" : c.note ? "text-mist" : "text-parchment"}`}>
                                {named(c.label)}
                                {c.at !== undefined && <span className={c.disabled ? "" : "text-mist"}> (at {c.at})</span>}
                                {current && <span className="sr-only"> (chosen)</span>}
                              </span>
                              {c.hint && <span className="text-xs text-mist">{c.hint}</span>}
                              {c.mark && <span id={`${optionId}-mark`} className="rounded border border-gold/50 px-1 text-[0.7rem] leading-4 text-gold">{c.mark}</span>}
                              {page && <span className="ml-auto shrink-0 text-[0.7rem] text-mist">{page}</span>}
                            </span>
                            {!c.note && (
                              <span id={`${optionId}-line`} className={`block truncate text-xs ${c.offer ? "text-gold" : "text-mist"}`}>
                                {c.offer ?? named(line)}
                              </span>
                            )}
                          </div>
                          {c.trait && hasAbout(c.trait, splat) && (
                            <AboutButton name={nameOf(c, named)} open={index === active} controls={detailId} onToggle={() => setActive(index === active ? -1 : index)} className="mt-1 mr-1" />
                          )}
                          {/* Beside the option, not in it: its links (to the step a refusal is because of) stay links. */}
                          {c.note && (
                            <p id={`${optionId}-note`} className="-mt-1 basis-full px-3 pb-1.5 text-xs text-blood-bright/90">
                              {typeof c.note === "string" ? named(c.note) : c.note}
                            </p>
                          )}
                          {c.disabled && c.action && (
                            <button
                              type="button"
                              onClick={() => act(c)}
                              className="mb-1.5 ml-3 text-xs text-gold underline hover:text-parchment pointer-coarse:min-h-10"
                            >
                              {c.action.label}
                            </button>
                          )}
                        </li>
                      );
                    })}
                </ul>
              </li>
            ))}
          </ul>
          {shown.length === 0 && empty !== null && <p className="px-3 py-2 text-sm text-mist">{empty}</p>}
          {footer && <div className="border-t border-ash px-1 py-1">{footer}</div>}
          <div id={detailId} role="region" aria-label="About the highlighted choice" aria-live="polite" className="max-h-56 overflow-y-auto border-t border-ash px-3 py-2">
            {lit ? (
              <>
                <p className="text-sm text-gold">
                  {nameOf(lit, named)}
                  {lit.mark && <span className="ml-2 text-xs text-mist">({lit.mark})</span>}
                </p>
                {/* One that can't be chosen says why in its row; one staff can choose all the same says so here. */}
                {lit.note && !lit.disabled && (
                  <p className="text-xs text-blood-bright">
                    {typeof lit.note === "string" ? named(lit.note) : lit.note} Staff can give it all the same.
                  </p>
                )}
                {lit.trait ? (
                  <AboutTrait
                    id={`${detailId}-about`}
                    trait={lit.trait}
                    splat={splat}
                    from={lit.dots?.from ?? 1}
                    to={lit.dots ? (lit.dots.to ?? lit.dots.from) : lit.trait.category === "disciplines" ? 5 : 1}
                    troupeId={troupeId}
                    className="mt-0.5"
                  />
                ) : (
                  lit.summary && <p className="text-xs text-mist">{named(lit.summary)}</p>
                )}
                {lit.trait?.in_clan?.length ? <p className="mt-0.5 text-xs text-mist">In-clan disciplines: {lit.trait.in_clan.join(", ")}.</p> : null}
                <ClanWeakness trait={lit.trait} className="mt-0.5 text-xs text-mist" />
              </>
            ) : (
              <p className="text-xs text-mist">Highlight one to read about it: the arrow keys, a hover, or its chevron.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

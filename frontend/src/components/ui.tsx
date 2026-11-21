// The heading scale (page title, card title, CardHeading, SectionLabel) is written at the top of Headings.tsx (#901).
import { cloneElement, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { ButtonHTMLAttributes, CSSProperties, InputHTMLAttributes, ReactElement, ReactNode, Ref, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { Link, NavLink, useLocation } from "react-router";
import { useMe, usePreferences } from "../hooks";
import { LoaderMark } from "../loaders/art";
import { useMotif } from "../loaders/useMotif";
import { useOnline } from "../offline/connection";
import { NeedsConnection } from "../offline/NeedsConnection";
import { pipGroups } from "../ratings";
import { openTab, tabOpens, textOf, useTitle } from "../title";
import { RowChevron } from "./RowChevron";
import { SectionPicker } from "./SectionPicker";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/*
 * Buttons: which kind, and which words (#920).
 *
 * Kind:
 * - One `primary` (red) button per screen or dialog: the thing the person came to do.
 *   Everything else is `secondary`, `ghost`, or `danger` for what destroys. The Play
 *   View's tracker, with its red − and + for each pool, is the one exception.
 * - A card's own Save is `primary` only if it is the only form on the screen; otherwise
 *   `secondary`. A settings card's Save (`SettingForm`) is always `secondary`: settings
 *   cards share their screen.
 *
 * Words, the same for the same act:
 * - **Save** keeps changes to something that already exists. Never "Save X" unless two
 *   Saves are in sight at once (Save draft beside Save and resubmit, say).
 * - **Add …** puts a new line in a list ("Add a theme", "Add a price").
 * - **Create …** makes a new thing with a page of its own ("Create troupe").
 * - **Edit** opens a form on something shown read-only. That includes a row of a list
 *   whose editor opens beneath it (a price, a territory, a teacher rule): the button reads
 *   "Edit", and its accessible name says which ("Edit the price for Haven").
 * - **Remove** takes a line out of a list; **Delete** destroys something.
 * - "Change" is not used on buttons. A menu may still head a group of items "Change".
 */

export type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-blood text-parchment hover:bg-blood-bright",
  secondary: "border border-ash bg-dusk text-parchment hover:border-mist",
  ghost: "text-mist hover:text-parchment",
  danger: "border border-blood text-blood-bright hover:bg-blood hover:text-parchment",
};

/** A `Button`'s classes, for a link that looks like one (`LinkButton`). */
export function buttonClasses(variant: Variant = "primary", className?: string): string {
  return cx(
    "inline-flex min-h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
    variants[variant],
    className,
  );
}

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; ref?: Ref<HTMLButtonElement> }) {
  return <button className={buttonClasses(variant, className)} {...props} />;
}

export function Card({
  title,
  info,
  actions,
  children,
  className,
  dense,
}: {
  title?: ReactNode;
  /** An `InfoButton` for the title, set beside it. */
  info?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Less padding and a smaller title, for screens with many cards (a sheet). */
  dense?: boolean;
}) {
  return (
    <section className={cx("rounded-lg border border-ash bg-dusk", dense ? "p-3 sm:p-4" : "p-4 sm:p-5", className)}>
      {(title || actions) && (
        <header className={cx("flex flex-wrap items-center justify-between gap-2", dense ? "mb-2" : "mb-3")}>
          {title && (
            <div className="flex items-center gap-2">
              <h2 className={dense ? "text-base text-gold" : "text-lg text-gold"}>{title}</h2>
              {info}
            </div>
          )}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

/**
 * A labelled control. The label is tied to the control by id, so the control's
 * accessible name is the label alone, and a hint is read as its description.
 */
export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactElement<{ id?: string; "aria-describedby"?: string }> }) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id} className="text-mist">
        {label}
      </label>
      {cloneElement(children, { id, "aria-describedby": hint ? hintId : undefined })}
      {hint && (
        <span id={hintId} className="text-xs text-mist">
          {hint}
        </span>
      )}
    </div>
  );
}

const control =
  "min-h-10 w-full rounded-md border border-ash bg-night px-3 py-2 text-parchment placeholder:text-mist/60 focus:border-gold focus:outline-none";

/** The control classes, full width unless the caller gives a width of its own
 * (Tailwind does not let a later width class win over an earlier one). */
function controlClass(className?: string): string {
  const sized = className?.split(/\s+/).some((c) => /^(sm:|md:|lg:)?(w|min-w|max-w|flex)-/.test(c) || c === "flex-1");
  return cx(sized ? control.replace("w-full ", "") : control, className);
}

export function Input(props: InputHTMLAttributes<HTMLInputElement> & { ref?: Ref<HTMLInputElement> }) {
  return <input {...props} className={controlClass(props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={controlClass(props.className)} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement> & { ref?: Ref<HTMLTextAreaElement> }) {
  return <textarea rows={4} {...props} className={controlClass(props.className)} />;
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <p role="alert" className="rounded-md border border-blood/60 bg-blood/15 px-3 py-2 text-sm text-parchment">
      {message}
    </p>
  );
}

/**
 * Who is signed in couldn't be checked: the server failed, rather than saying there
 * is no session (#621). Says so, with a way to ask again, so a signed-in person
 * isn't sent to the sign-in form or offered an account by a passing fault.
 */
export function SessionCheckFailed() {
  const me = useMe();
  return (
    <div className="flex flex-col items-start gap-3">
      <p className="text-parchment">Couldn't check that you're signed in.</p>
      <ErrorText error={me.error} />
      <Button variant="secondary" disabled={me.isFetching} onClick={() => void me.refetch()}>
        Try again
      </Button>
    </div>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-gold/40 bg-gold/10 px-3 py-2 text-sm">{children}</p>;
}

/** How long a wait goes unmarked, so that a quick answer doesn't flash a loader. */
export const LOADING_DELAY_MS = 250;

/** Whether `ms` have passed since the component first showed. */
function useAfter(ms: number): boolean {
  const [passed, setPassed] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setPassed(true), ms);
    return () => clearTimeout(timer);
  }, [ms]);
  return passed;
}

/**
 * Waiting for an answer: after a moment, the loading animation the custodian chose
 * (#568), with `label`. `compact`, a small one to sit beside a line of text, such
 * as a count while a search runs. Offline, with nothing kept to show, the screen
 * says it needs a connection instead (#502).
 */
export function Loading({ compact = false, label = "Loading…" }: { compact?: boolean; label?: string }) {
  const online = useOnline();
  if (!online) return compact ? null : <NeedsConnection />;
  return <Loader compact={compact} label={label} />;
}

/** The loading animation alone, online or not: for what is loading from the
 * device, such as a page's own script, or the Play View's kept answers. */
export function Loader({ compact = false, label = "Loading…" }: { compact?: boolean; label?: string }) {
  const motif = useMotif();
  const shown = useAfter(LOADING_DELAY_MS);
  if (!shown) return null;
  if (compact)
    return (
      <span role="status" aria-label={label} className="loader-appear inline-flex items-center gap-1.5 align-middle text-mist">
        <LoaderMark motif={motif} size="compact" />
        <span>{label}</span>
      </span>
    );
  return (
    <div role="status" aria-label={label} className="loader-appear flex flex-col items-center gap-3 py-8 text-sm text-mist">
      <LoaderMark motif={motif} size="block" />
      <span>{label}</span>
    </div>
  );
}

/**
 * What a query found, once it has: the loader until then, and its error if it
 * failed. So a screen never says there is nothing before it knows (#568):
 * `<Loaded query={list}>{(items) => (items.length ? … : <Empty>None yet.</Empty>)}</Loaded>`.
 * For a query that runs; one waiting on something (not enabled) would load for ever.
 */
export function Loaded<T>({ query, compact, children }: { query: { data: T | undefined; error: unknown }; compact?: boolean; children: (data: T) => ReactNode }) {
  if (query.data !== undefined) return <>{children(query.data)}</>;
  if (query.error) return <ErrorText error={query.error} />;
  return <Loading compact={compact} />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-4 text-sm text-mist">{children}</p>;
}

export function Badge({ children, tone = "mist", className }: { children: ReactNode; tone?: "mist" | "gold" | "blood"; className?: string }) {
  const tones = {
    mist: "border-ash text-mist",
    gold: "border-gold/50 text-gold",
    blood: "border-blood text-blood-bright",
  };
  return <span className={cx("rounded-full border px-2 py-0.5 text-xs whitespace-nowrap", tones[tone], className)}>{children}</span>;
}

/** A page's heading. Its words name the browser tab too (#775); `title` gives them where the heading's own won't do. */
export function PageTitle({ children, subtitle, actions, title }: { children: ReactNode; subtitle?: ReactNode; actions?: ReactNode; title?: string }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useTitle(title ?? textOf(children), heading);
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 ref={heading} className="text-2xl text-parchment sm:text-3xl">
          {children}
        </h1>
        {subtitle && <p className="mt-1 text-sm text-mist">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

/** A small round count, such as how many things are waiting. Shows nothing at zero. */
export function CountBubble({ count, label }: { count: number; label: string }) {
  if (count <= 0) return null;
  return (
    <span
      aria-label={`${count} ${label}`}
      className="inline-grid h-5 min-w-5 place-items-center rounded-full bg-blood px-1.5 font-sans text-[11px] leading-none font-semibold text-parchment"
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}

/** A tab, with a count of what waits on it, such as "2 new" (`countLabel` says what they are).
 * `countInGroup: false` keeps a count that isn't waiting on anyone (characters being
 * built, #774) out of its group's "waiting" total. */
/** A tab: `also` is another address under which it shows as open (see `tabOpens`).
 * `ariaLabel` names it for a screen reader when its label alone doesn't say enough
 * (a tab that leaves the page, #922). */
export type Tab = { to: string; label: string; ariaLabel?: string; end?: boolean; also?: string; count?: number; countLabel?: string; countInGroup?: boolean };

/** How wide the fade is at an edge of a tab bar with more beyond it: as wide as the chevron over it. */
const FADE_PX = 40;

/**
 * For a row of tabs that scrolls sideways on a narrow screen: brings the open
 * tab (the one with `aria-current`) into view whenever the page changes, and
 * fades whichever edge has more tabs beyond it, with a chevron over the fade
 * that scrolls the row that way (#921), so the row is seen to scroll.
 * `scroller` goes on the part that scrolls, and `chevrons` beside it, in a
 * `relative` box around it (`ROW`).
 */
function useTabRow<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const { pathname } = useLocation();
  const [edges, setEdges] = useState({ start: false, end: false });
  const measure = useCallback(() => {
    const row = ref.current;
    if (!row) return;
    const start = row.scrollLeft > 1;
    const end = row.scrollLeft + row.clientWidth < row.scrollWidth - 1;
    setEdges((e) => (e.start === start && e.end === end ? e : { start, end }));
  }, []);
  useLayoutEffect(() => {
    const row = ref.current;
    const open = row?.querySelector<HTMLElement>("[aria-current]");
    if (row && open) {
      // Sideways only: scrollIntoView would move the page up or down too.
      const box = row.getBoundingClientRect();
      const tab = open.getBoundingClientRect();
      if (tab.left < box.left + FADE_PX) row.scrollLeft -= box.left + FADE_PX - tab.left;
      else if (tab.right > box.right - FADE_PX) row.scrollLeft += tab.right - box.right + FADE_PX;
    }
    measure();
  }, [pathname, measure]);
  useEffect(() => {
    const row = ref.current;
    if (!row || typeof ResizeObserver === "undefined") return;
    // The row, and its tabs, which grow when a count comes in.
    const watch = new ResizeObserver(measure);
    watch.observe(row);
    for (const tab of Array.from(row.children)) watch.observe(tab);
    return () => watch.disconnect();
  }, [measure]);
  // By most of the row's width: the tab cut off under one chevron comes out just clear of the other.
  const scroll = useCallback((way: 1 | -1) => {
    const row = ref.current;
    if (!row) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    row.scrollBy({ left: way * Math.max(row.clientWidth - 2 * FADE_PX, row.clientWidth / 2), behavior: still ? "auto" : "smooth" });
  }, []);
  let style: CSSProperties | undefined;
  if (edges.start || edges.end) {
    const from = edges.start ? `transparent, black ${FADE_PX}px` : "black";
    const to = edges.end ? `black calc(100% - ${FADE_PX}px), transparent` : "black";
    const mask = `linear-gradient(to right, ${from}, ${to})`;
    style = { maskImage: mask, WebkitMaskImage: mask };
  }
  const chevrons = (
    <>
      {edges.start && <RowChevron side="start" onPress={() => scroll(-1)} />}
      {edges.end && <RowChevron side="end" onPress={() => scroll(1)} />}
    </>
  );
  return { ref, scroller: { ref, style, onScroll: measure }, chevrons };
}

/**
 * The tab bars' shared look: on a phone the row runs to the screen's edges.
 * `ROW` is the box around it, which holds the chevrons; `SCROLLER` is the part that scrolls.
 */
const ROW = "relative -mx-4 sm:mx-0";
const SCROLLER = "flex overflow-x-auto px-4 sm:px-0";

export function Tabs({ tabs }: { tabs: Tab[] }) {
  const row = useTabRow<HTMLDivElement>();
  const { pathname } = useLocation();
  useTitle(openTab(tabs, pathname)?.label, row.ref);
  return (
    <nav className={cx(ROW, "mb-6")}>
      <div {...row.scroller} className={cx(SCROLLER, "gap-1 border-b border-ash")}>
        {tabs.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              cx(
                "shrink-0 border-b-2 px-3 py-2 text-sm whitespace-nowrap",
                isActive ? "border-gold text-parchment" : "border-transparent text-mist hover:text-parchment",
              )
            }
          >
            <span className="inline-flex items-center gap-1.5">
              {t.label}
              {t.count !== undefined && <CountBubble count={t.count} label={t.countLabel ?? "waiting"} />}
            </span>
          </NavLink>
        ))}
      </div>
      {row.chevrons}
    </nav>
  );
}

/**
 * Tabs in groups, for a page with too many to fit one row: the groups in a row,
 * and under it the open group's own tabs. A group opens its first tab, or the
 * one its `to` names; a group of one is a plain tab. Counts add up on their
 * group, so what waits is seen from anywhere. Someone who sees only one group
 * has its tabs as the only row (#1048). On a phone the rows give way to one
 * `SectionPicker` (#904), with the `recent` tabs at the top of its sheet.
 */
export function GroupedTabs({ label, groups, recent }: { label: string; groups: { label: string; tabs: Tab[]; to?: string }[]; recent?: Tab[] }) {
  const { pathname } = useLocation();
  const shown = groups.filter((g) => g.tabs.length > 0);
  const open = shown.find((g) => g.tabs.some((t) => tabOpens(t, pathname)));
  const only = shown.length === 1 ? shown[0] : undefined;
  const row = useTabRow<HTMLDivElement>();
  useTitle(open && openTab(open.tabs, pathname)?.label, row.ref);
  const look = (active: boolean) =>
    cx("shrink-0 border-b-2 px-3 py-2 text-sm whitespace-nowrap", active ? "border-gold text-parchment" : "border-transparent text-mist hover:text-parchment");
  return (
    // Closer to the heading and the content on a phone, where height is short (#904).
    <div className="mb-6 max-sm:-mt-2 max-sm:mb-4">
      <SectionPicker label={label} groups={shown} recent={recent} className="sm:hidden" />
      <nav aria-label={label} className={cx(ROW, "max-sm:hidden")}>
        <div {...row.scroller} className={cx(SCROLLER, "gap-x-1 border-b border-ash")}>
          {only
            ? only.tabs.map((t) => {
                const active = t === openTab(only.tabs, pathname);
                return (
                  <Link key={t.to} to={t.to} aria-label={t.ariaLabel} aria-current={active ? "page" : undefined} className={look(active)}>
                    <span className="inline-flex items-center gap-1.5">
                      {t.label}
                      {t.count !== undefined && <CountBubble count={t.count} label={t.countLabel ?? "waiting"} />}
                    </span>
                  </Link>
                );
              })
            : shown.map((g) => {
                const active = g === open;
                const counts = g.tabs.filter((t) => t.count !== undefined && t.countInGroup !== false);
                const total = counts.reduce((sum, t) => sum + (t.count ?? 0), 0);
                return (
                  <Link
                    key={g.label}
                    to={g.to && g.tabs.some((t) => t.to === g.to) ? g.to : g.tabs[0]!.to}
                    aria-current={active ? "true" : undefined}
                    className={look(active)}
                  >
                    <span className="inline-flex items-center gap-1.5">
                      {g.label}
                      {counts.length > 0 && <CountBubble count={total} label="waiting" />}
                    </span>
                  </Link>
                );
              })}
        </div>
        {row.chevrons}
      </nav>
      {!only && open && open.tabs.length > 1 && <SubTabs label={open.label} tabs={open.tabs} className="mt-3 mb-0 max-sm:hidden" />}
    </div>
  );
}

/**
 * The second level: a section's pages, as pills, under its group in
 * `GroupedTabs`. For the parts of one page, inside it, use `PageTabs`.
 */
export function SubTabs({ label, tabs, className }: { label: string; tabs: Tab[]; className?: string }) {
  const row = useTabRow<HTMLDivElement>();
  const { pathname } = useLocation();
  useTitle(openTab(tabs, pathname)?.label, row.ref);
  return (
    // A className of its own replaces the margin below.
    <nav aria-label={label} className={cx(ROW, className ?? "mb-5")}>
      <div {...row.scroller} className={cx(SCROLLER, "gap-2")}>
        {tabs.map((t) => (
          // Marked open as NavLink would, and under its `also` address too.
          <Link
            key={t.to}
            to={t.to}
            aria-label={t.ariaLabel}
            aria-current={tabOpens(t, pathname) ? "page" : undefined}
            className={cx(
              "shrink-0 rounded-full border px-3 py-1 text-sm whitespace-nowrap",
              tabOpens(t, pathname) ? "border-gold/60 bg-gold/10 text-parchment" : "border-ash text-mist hover:text-parchment",
            )}
          >
            <span className="inline-flex items-center gap-1.5">
              {t.label}
              {t.count !== undefined && <CountBubble count={t.count} label={t.countLabel ?? "waiting"} />}
            </span>
          </Link>
        ))}
      </div>
      {row.chevrons}
    </nav>
  );
}

/**
 * The third level: the parts of one page, set inside it. A small segmented
 * control, quieter than the pills above it, so the two never read as one row
 * wrapped. When the parts don't fit on one line they wrap onto more, between
 * tabs and never inside a label, so every one is in sight, on a phone too.
 * For a page of five parts or fewer: one with more uses `PartPicker` (#906).
 * `scrolls` keeps the row on one line on a phone, scrolling sideways under the
 * tab bars' chevrons, for a page whose content needs the height more than its
 * tabs need to be all in sight at once, as the boon ledger (#982).
 */
export function PageTabs({ label, tabs, className, scrolls = false }: { label: string; tabs: Tab[]; className?: string; scrolls?: boolean }) {
  const nav = useRef<HTMLElement>(null);
  const row = useTabRow<HTMLDivElement>();
  const { pathname } = useLocation();
  useTitle(openTab(tabs, pathname)?.label, nav);
  const box = (
    <div className={cx("inline-flex gap-0.5 rounded-md border border-ash bg-night p-0.5", scrolls ? "shrink-0 sm:max-w-full sm:flex-wrap" : "max-w-full flex-wrap")}>
      {tabs.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.end}
          className={({ isActive }) =>
            // At least 40 px each way on a touch screen.
            cx(
              "inline-flex shrink-0 items-center justify-center rounded px-2.5 py-1 text-xs whitespace-nowrap pointer-coarse:min-h-10 pointer-coarse:min-w-10",
              isActive ? "bg-ash text-gold" : "text-mist hover:text-parchment",
            )
          }
        >
          <span className="inline-flex items-center gap-1.5">
            {t.label}
            {t.count !== undefined && <CountBubble count={t.count} label={t.countLabel ?? "waiting"} />}
          </span>
        </NavLink>
      ))}
    </div>
  );
  return (
    // A className of its own replaces the margin below (Tailwind does not let a later margin class win).
    <nav ref={nav} aria-label={label} className={cx(scrolls && "relative max-sm:-mx-4", className ?? "mb-5")}>
      {scrolls ? (
        <>
          <div {...row.scroller} className="flex max-sm:overflow-x-auto max-sm:px-4">
            {box}
          </div>
          {row.chevrons}
        </>
      ) : (
        box
      )}
    </nav>
  );
}

/**
 * Filled and empty pips, five to a group, as on the paper sheet. The printed
 * sheet uses them too, so they look the same on screen and on paper. Sized to
 * the text around them, in its colour; pips from `pendingFrom` up are still
 * waiting for approval, in gold.
 */
export function Pips({
  value,
  of = 5,
  pendingFrom,
  planned = null,
  className,
}: {
  value: number;
  of?: number;
  pendingFrom?: number | null;
  planned?: number | null;
  className?: string;
}) {
  return (
    <span role="img" aria-label={ratingLabel(value, planned)} className={cx("inline-flex gap-[0.35em] whitespace-nowrap", className)}>
      {pipGroups(value, of, pendingFrom, planned).map((group, g) => (
        <span key={g} className="inline-flex gap-[0.12em]">
          {group.map((pip, i) => (
            // An SVG rather than "●", so a filled pip prints filled whatever the font or the browser's background setting.
            <svg key={i} viewBox="0 0 10 10" aria-hidden className={cx("h-[0.7em] w-[0.7em]", (pip === "waiting" || pip === "planned") && "text-gold")}>
              <circle
                cx="5"
                cy="5"
                r="4.2"
                stroke="currentColor"
                strokeWidth={pip === "planned" ? 1.4 : 1.2}
                // Outlined and dashed: in the cart, not yet spent.
                strokeDasharray={pip === "planned" ? "2.2 1.1" : undefined}
                fill={pip === "empty" || pip === "planned" ? "none" : "currentColor"}
              />
            </svg>
          ))}
        </span>
      ))}
    </span>
  );
}

function ratingLabel(value: number, planned: number | null) {
  return planned != null && planned !== value ? `${value} dots, ${planned} after the changes in the cart` : `${value} dots`;
}

/**
 * A rating, as the person shows ratings (Settings → Show ratings as): a number,
 * or pips, at least `of` of them. Dots from `pendingFrom` up are still waiting
 * for approval, shown in gold: "2 +1", or gold pips. `planned` is the rating a
 * change in the cart would make it, not yet spent: "2 → 3", or outlined pips.
 */
export function Rating({
  value,
  pendingFrom,
  planned = null,
  of = 5,
  className = "min-w-[1.5rem] text-right font-display text-base text-parchment",
}: {
  value: number;
  pendingFrom?: number | null;
  planned?: number | null;
  of?: number;
  className?: string;
}) {
  const { ratings } = usePreferences();
  if (ratings === "pips") return <Pips value={value} of={of} pendingFrom={pendingFrom} planned={planned} className={className} />;
  const waiting = pendingFrom != null && pendingFrom < value ? value - pendingFrom : 0;
  return (
    <span aria-label={ratingLabel(value, planned)} className={cx("inline-block tabular-nums", className)}>
      {value - waiting}
      {waiting > 0 && <span className="text-gold"> +{waiting}</span>}
      {planned != null && planned !== value && <span className="text-gold"> → {planned}</span>}
    </span>
  );
}

/** Downtime results arrive with **bold** and *italic* marks, as Discord would show them. */
function RichLines({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, j) => (
        <span key={j}>
          {j > 0 && <br />}
          {line.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).map((part, k) =>
            part.startsWith("**") ? (
              <strong key={k} className="text-gold">{part.slice(2, -2)}</strong>
            ) : part.startsWith("*") && part.length > 2 ? (
              <em key={k} className="text-mist">{part.slice(1, -1)}</em>
            ) : (
              <span key={k}>{part}</span>
            ),
          )}
        </span>
      ))}
    </>
  );
}

/** Text with **bold** and *italic*. A paragraph "▸ Summary: the rest" folds away under its summary. */
export function RichText({ text }: { text: string }) {
  return (
    <div className="space-y-3 text-sm leading-relaxed">
      {text.split("\n\n").map((para, i) => {
        const folded = para.match(/^▸ ([^:]+): ([\s\S]*)$/);
        if (folded)
          return (
            <details key={i}>
              <summary className="cursor-pointer text-mist">{folded[1]}</summary>
              <p className="mt-1">
                <RichLines text={folded[2]!} />
              </p>
            </details>
          );
        return (
          <p key={i}>
            <RichLines text={para} />
          </p>
        );
      })}
    </div>
  );
}

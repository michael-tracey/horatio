import { cloneElement, useId } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactElement, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { Link, NavLink, useLocation } from "react-router";
import { usePreferences } from "../hooks";
import { pipGroups } from "../ratings";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-blood text-parchment hover:bg-blood-bright",
  secondary: "border border-ash bg-dusk text-parchment hover:border-mist",
  ghost: "text-mist hover:text-parchment",
  danger: "border border-blood text-blood-bright hover:bg-blood hover:text-parchment",
};

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={cx(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Card({
  title,
  actions,
  children,
  className,
  dense,
}: {
  title?: ReactNode;
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
          {title && <h2 className={dense ? "text-base text-gold" : "text-lg text-gold"}>{title}</h2>}
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

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={controlClass(props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={controlClass(props.className)} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
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

export function Notice({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-gold/40 bg-gold/10 px-3 py-2 text-sm">{children}</p>;
}

export function Loading() {
  return <p className="py-8 text-center text-mist">Loading…</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-4 text-sm text-mist">{children}</p>;
}

export function Badge({ children, tone = "mist" }: { children: ReactNode; tone?: "mist" | "gold" | "blood" }) {
  const tones = {
    mist: "border-ash text-mist",
    gold: "border-gold/50 text-gold",
    blood: "border-blood text-blood-bright",
  };
  return <span className={cx("rounded-full border px-2 py-0.5 text-xs whitespace-nowrap", tones[tone])}>{children}</span>;
}

export function PageTitle({ children, subtitle, actions }: { children: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl text-parchment sm:text-3xl">{children}</h1>
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

export function Tabs({ tabs }: { tabs: { to: string; label: string; end?: boolean; count?: number }[] }) {
  return (
    <nav className="-mx-4 mb-6 flex gap-1 overflow-x-auto border-b border-ash px-4 sm:mx-0 sm:px-0">
      {tabs.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.end}
          className={({ isActive }) =>
            cx(
              "border-b-2 px-3 py-2 text-sm whitespace-nowrap",
              isActive ? "border-gold text-parchment" : "border-transparent text-mist hover:text-parchment",
            )
          }
        >
          <span className="inline-flex items-center gap-1.5">
            {t.label}
            {t.count !== undefined && <CountBubble count={t.count} label="waiting" />}
          </span>
        </NavLink>
      ))}
    </nav>
  );
}

type Tab = { to: string; label: string; end?: boolean; count?: number };

/**
 * Tabs in groups, for a page with too many to fit one row: the groups in a row,
 * and under it the open group's own tabs, wrapping rather than scrolling. A
 * group opens its first tab; a group of one is a plain tab. Counts add up on
 * their group, so what waits is seen from anywhere.
 */
export function GroupedTabs({ label, groups }: { label: string; groups: { label: string; tabs: Tab[] }[] }) {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/$/, "");
  const opens = (t: Tab) => (t.end ? here === t.to : here === t.to || here.startsWith(`${t.to}/`));
  const shown = groups.filter((g) => g.tabs.length > 0);
  const open = shown.find((g) => g.tabs.some(opens));
  return (
    <div className="mb-6">
      <nav aria-label={label} className="flex flex-wrap gap-x-1 border-b border-ash">
        {shown.map((g) => {
          const active = g === open;
          const counts = g.tabs.filter((t) => t.count !== undefined);
          const total = counts.reduce((sum, t) => sum + (t.count ?? 0), 0);
          return (
            <Link
              key={g.label}
              to={g.tabs[0]!.to}
              aria-current={active ? "true" : undefined}
              className={cx(
                "-mb-px border-b-2 px-3 py-2 text-sm whitespace-nowrap",
                active ? "border-gold text-parchment" : "border-transparent text-mist hover:text-parchment",
              )}
            >
              <span className="inline-flex items-center gap-1.5">
                {g.label}
                {counts.length > 0 && <CountBubble count={total} label="waiting" />}
              </span>
            </Link>
          );
        })}
      </nav>
      {open && open.tabs.length > 1 && <SubTabs label={open.label} tabs={open.tabs} className="mt-3 mb-0" />}
    </div>
  );
}

/** Smaller tabs inside a tab, for its parts. */
export function SubTabs({ label, tabs, className }: { label: string; tabs: Tab[]; className?: string }) {
  return (
    <nav aria-label={label} className={cx("mb-5 flex flex-wrap gap-2", className)}>
      {tabs.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.end}
          className={({ isActive }) =>
            cx(
              "rounded-full border px-3 py-1 text-sm whitespace-nowrap",
              isActive ? "border-gold/60 bg-gold/10 text-parchment" : "border-ash text-mist hover:text-parchment",
            )
          }
        >
          <span className="inline-flex items-center gap-1.5">
            {t.label}
            {t.count !== undefined && <CountBubble count={t.count} label="waiting" />}
          </span>
        </NavLink>
      ))}
    </nav>
  );
}

/**
 * Filled and empty pips, five to a group, as on the paper sheet. The printed
 * sheet uses them too, so they look the same on screen and on paper. Sized to
 * the text around them, in its colour; pips from `pendingFrom` up are still
 * waiting for approval, in gold.
 */
export function Pips({ value, of = 5, pendingFrom, className }: { value: number; of?: number; pendingFrom?: number | null; className?: string }) {
  return (
    <span role="img" aria-label={`${value} dots`} className={cx("inline-flex gap-[0.35em] whitespace-nowrap", className)}>
      {pipGroups(value, of, pendingFrom).map((group, g) => (
        <span key={g} className="inline-flex gap-[0.12em]">
          {group.map((pip, i) => (
            // An SVG rather than "●", so a filled pip prints filled whatever the font or the browser's background setting.
            <svg key={i} viewBox="0 0 10 10" aria-hidden className={cx("h-[0.7em] w-[0.7em]", pip === "waiting" && "text-gold")}>
              <circle cx="5" cy="5" r="4.2" stroke="currentColor" strokeWidth="1.2" fill={pip === "empty" ? "none" : "currentColor"} />
            </svg>
          ))}
        </span>
      ))}
    </span>
  );
}

/**
 * A rating, as the person shows ratings (Settings → Show ratings as): a number,
 * or pips, at least `of` of them. Dots from `pendingFrom` up are still waiting
 * for approval, shown in gold: "2 +1", or gold pips.
 */
export function Rating({
  value,
  pendingFrom,
  of = 5,
  className = "min-w-[1.5rem] text-right font-display text-base text-parchment",
}: {
  value: number;
  pendingFrom?: number | null;
  of?: number;
  className?: string;
}) {
  const { ratings } = usePreferences();
  if (ratings === "pips") return <Pips value={value} of={of} pendingFrom={pendingFrom} className={className} />;
  const waiting = pendingFrom != null && pendingFrom < value ? value - pendingFrom : 0;
  return (
    <span aria-label={`${value} dots`} className={cx("inline-block tabular-nums", className)}>
      {value - waiting}
      {waiting > 0 && <span className="text-gold"> +{waiting}</span>}
    </span>
  );
}

/** Downtime results arrive with **bold** and *italic* marks, as Discord would show them. */
export function RichText({ text }: { text: string }) {
  return (
    <div className="space-y-3 text-sm leading-relaxed">
      {text.split("\n\n").map((para, i) => (
        <p key={i}>
          {para.split("\n").map((line, j) => (
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
        </p>
      ))}
    </div>
  );
}

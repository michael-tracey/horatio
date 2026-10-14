import { cloneElement, useId } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactElement, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { NavLink } from "react-router";

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

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-lg border border-ash bg-dusk p-4 sm:p-5", className)}>
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-lg text-gold">{title}</h2>}
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

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(control, props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(control, props.className)} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={4} {...props} className={cx(control, props.className)} />;
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

export function Tabs({ tabs }: { tabs: { to: string; label: string; end?: boolean }[] }) {
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
          {t.label}
        </NavLink>
      ))}
    </nav>
  );
}

/** Dots for a rating, filled to `value`, e.g. ●●●○○. */
export function Dots({ value, approved }: { value: number; approved?: number | null }) {
  const shown = Math.max(value, 5);
  return (
    <span aria-label={`${value} dots`} className="font-mono tracking-tight">
      {Array.from({ length: shown }, (_, i) => (
        <span key={i} className={i < value ? (approved != null && i >= approved ? "text-gold" : "text-blood-bright") : "text-ash"}>
          ●
        </span>
      ))}
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

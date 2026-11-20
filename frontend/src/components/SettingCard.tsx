import { useId, useState, type FormEvent, type ReactNode } from "react";
import type { QueryKey } from "@tanstack/react-query";
import { useAction, useLeaveWarning } from "../hooks";
import { useToast } from "./Toast";
import { Badge, Button, ErrorText } from "./ui";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/** What a read-only card says by default: who can change it. */
export const STORYTELLERS_CHANGE = "The troupe's storytellers change this.";

/**
 * A settings card (#900): every settings card has the same parts in the same places. Its
 * title, an optional state on the right ("On", "Not set up"), one short line saying what
 * the setting does, then the controls. It is a region named by its title.
 *
 * How it saves is decided by what it holds, never by the card:
 *
 * - **Only switches, ticks or choices:** each saves as it changes, with `useSaveOnChange`.
 *   The shared toast says "Saved." each time. The control is disabled while the save runs.
 *   On a failure the control goes back (it shows what the server holds) and the card shows
 *   the error.
 * - **Any typed field (text, a number, Markdown):** the fields are always open, in a
 *   `SettingForm` with `useSettingForm`. One Save button at the bottom left, enabled only
 *   once something has changed, with "Not saved yet" beside it, and leaving the page asks
 *   first while there are changes not saved.
 * - **Read-only for this person:** the same card, the values as plain text and no
 *   controls, with `readOnly` giving one line saying who can change it.
 *
 * There is no Change button that swaps a card into a form: a card is live, or a form.
 * A list of rules with a row editor (teacher rules, territories) keeps a per-row Edit.
 * The Save is `secondary`: settings cards share their screen (the rules in `ui.tsx`).
 */
export function SettingCard({
  setting,
  title = setting?.title ?? "",
  state,
  info,
  actions,
  about = setting?.about,
  readOnly,
  className,
  children,
}: {
  /**
   * A troupe's setting, as Find a setting has it (#1047): its title and line, unless `about`
   * says otherwise, and its id, which an address ending `#<anchor>` lands on.
   */
  setting?: { title: string; about: string; anchor: string };
  title?: string;
  /** A short state, set on the right: a word becomes a `Badge`, "On" in gold. */
  state?: ReactNode;
  /** An `InfoButton` for the title, set beside it. */
  info?: ReactNode;
  /** Links or buttons beside the state, such as Add a rule for a list. */
  actions?: ReactNode;
  /** One short line saying what the setting does; null for none, where the setting has one. */
  about?: ReactNode;
  /** For a person who can't change it: true, or the line saying who can. */
  readOnly?: boolean | string;
  className?: string;
  children?: ReactNode;
}) {
  const id = useId();
  const badge = typeof state === "string" ? <Badge tone={state === "On" ? "gold" : "mist"}>{state}</Badge> : state;
  return (
    <section id={setting?.anchor} aria-labelledby={id} className={cx("scroll-mt-4 rounded-lg border border-ash bg-dusk p-4 sm:p-5", className)}>
      <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 id={id} className="text-lg text-gold">
            {title}
          </h2>
          {info}
        </div>
        {(actions || badge) && (
          <div className="flex flex-wrap items-center gap-2">
            {actions}
            {badge}
          </div>
        )}
      </header>
      {about && <p className="mb-3 text-sm text-mist">{about}</p>}
      {children}
      {readOnly && <p className="mt-3 text-xs text-mist">{readOnly === true ? STORYTELLERS_CHANGE : readOnly}</p>}
    </section>
  );
}

/**
 * Marks a card, or a feature's row, that an address has landed on, as Find a setting does
 * (#1047): it glows gold a moment (`[data-found]` in index.css), so the eye finds it.
 */
export function showFound(el: HTMLElement) {
  clearTimeout(glowing.get(el));
  el.removeAttribute("data-found");
  // Once more from the start, if it was still glowing from the last time.
  void el.offsetWidth;
  el.setAttribute("data-found", "");
  glowing.set(
    el,
    setTimeout(() => el.removeAttribute("data-found"), 3000),
  );
}

const glowing = new WeakMap<HTMLElement, ReturnType<typeof setTimeout>>();

type SaveOptions = {
  /** It changes the rules, so the catalogue is asked again too (`useRulesAction`). */
  rules?: boolean;
  /** The queries that show the change, asked again first. */
  first?: QueryKey[];
};

/**
 * A switch, tick or choice that saves as it changes: the shared toast says "Saved." (or
 * `message`'s words) each time. Disable the control while `isPending`, and show `error`
 * in the card; a control bound to what the server holds goes back by itself on a failure.
 */
export function useSaveOnChange<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  {
    rules = false,
    first = [],
    message,
  }: SaveOptions & {
    /** What the toast says, where "Saved." alone would say less than it should. */
    message?: (args: TArgs) => string;
  } = {},
) {
  const toast = useToast();
  return useAction(
    async (args: TArgs) => {
      const result = await fn(args);
      toast({ message: message?.(args) ?? "Saved." });
      return result;
    },
    first,
    { rules },
  );
}

/** What `useSettingForm` gives its `SettingForm`, and the fields their values. */
export type SettingFormState<T> = {
  /** The fields' values: the saved ones until something changes. */
  value: T;
  /** Change some of the fields. */
  set: (change: Partial<T>) => void;
  /** Put the fields back as they are saved. */
  reset: () => void;
  /** Something has changed since the last save. */
  unsaved: boolean;
  save: () => void;
  saving: boolean;
  error: unknown;
};

/**
 * A settings card's fields, always open, saved together with one button (`SettingForm`).
 * `saved` is the setting as the server has it, in the form's shape; the fields show it until
 * something changes, and again once the change is saved. `submit` may throw an `Error` with a
 * problem to show, such as a band out of order. Leaving the page asks first while there are
 * changes not saved.
 */
export function useSettingForm<T>(saved: T, submit: (value: T) => Promise<unknown>, { rules = false, first = [] }: SaveOptions = {}): SettingFormState<T> {
  const toast = useToast();
  const [draft, setDraft] = useState<T | null>(null);
  const value = draft ?? saved;
  const unsaved = draft !== null && JSON.stringify(draft) !== JSON.stringify(saved);
  useLeaveWarning(unsaved, { inApp: true });
  const mutation = useAction(submit, first, { rules });
  return {
    value,
    set: (change) => setDraft((d) => ({ ...(d ?? saved), ...change })),
    reset: () => setDraft(null),
    unsaved,
    // The fields go back to showing what is saved once the page has it again.
    save: () =>
      mutation.mutate(value, {
        onSuccess: () => {
          setDraft(null);
          toast({ message: "Saved." });
        },
      }),
    saving: mutation.isPending,
    error: mutation.error,
  };
}

/**
 * The fields of a settings card, always open, with its one Save button at the bottom left:
 * enabled only once something has changed, with "Not saved yet" beside it. `problem` is a
 * reason it can't be saved yet, shown above the button, which it disables.
 */
export function SettingForm<T>({ form, problem, className, children }: { form: SettingFormState<T>; problem?: string | null; className?: string; children: ReactNode }) {
  const id = useId();
  return (
    <form
      className={cx("flex flex-col gap-4 text-sm", className)}
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        if (form.unsaved && !problem) form.save();
      }}
    >
      {children}
      <div className="flex flex-col gap-3 border-t border-ash/60 pt-4">
        {problem && (
          <p id={`${id}-problem`} className="text-sm text-blood-bright">
            {problem}
          </p>
        )}
        <ErrorText error={form.error} />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="secondary" disabled={!form.unsaved || !!problem || form.saving} aria-describedby={problem ? `${id}-problem` : undefined}>
            Save
          </Button>
          {form.unsaved && <span className="text-sm text-mist">Not saved yet</span>}
        </div>
      </div>
    </form>
  );
}

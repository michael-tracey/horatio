import { useEffect, useState } from "react";
import type { ReactNode } from "react";

const PREFIX = "horatio.explainer.";

/** Whether an explainer opens: the first time this device sees it, then as it was last left. */
export function explainerOpen(id: string, storage: Storage | undefined = globalThis.localStorage): boolean {
  try {
    const left = storage?.getItem(PREFIX + id);
    return left == null || left === "open";
  } catch {
    return true;
  }
}

/** Remembers an explainer on this device: "seen" once shown, then "open" or "closed" as it is left. */
export function rememberExplainer(id: string, state: "seen" | "open" | "closed", storage: Storage | undefined = globalThis.localStorage): void {
  try {
    if (state === "seen" && storage?.getItem(PREFIX + id) != null) return;
    storage?.setItem(PREFIX + id, state);
  } catch {
    // Private windows keep nothing; it opens again next visit.
  }
}

/**
 * A "How X works" card: open the first time it is seen on this device, and
 * closed after that, so the page's own content comes first. Opened or closed by
 * hand, it stays as it was left. For a few words beside a heading, use an
 * `InfoButton` instead.
 */
export function Explainer({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  const [open, setOpen] = useState(() => explainerOpen(id));
  useEffect(() => rememberExplainer(id, "seen"), [id]);
  return (
    <details open={open} className="group rounded-lg border border-ash bg-dusk p-4 sm:p-5">
      <summary
        className="flex cursor-pointer list-none items-center gap-2 [&::-webkit-details-marker]:hidden"
        onClick={(e) => {
          // Toggled here, not by the browser, so only a press is remembered.
          e.preventDefault();
          setOpen(!open);
          rememberExplainer(id, open ? "closed" : "open");
        }}
      >
        <svg viewBox="0 0 20 20" aria-hidden className="h-4 w-4 shrink-0 text-mist transition-transform group-open:rotate-90" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M7.5 4.5 13 10l-5.5 5.5" />
        </svg>
        <h2 className="text-lg text-gold">{title}</h2>
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

import type { ReactNode } from "react";

/**
 * What a tracker's count brings if the character goes on, and how to play it,
 * with the page it comes from: "near" as the count nears a step, "at" once it
 * is there. A warning only; it never stops a tap.
 */
export function TrackerWarning({ level, title, source, children }: { level: "near" | "at"; title: string; source: string; children: ReactNode }) {
  return (
    <div role="note" aria-label={title} className={`mt-2 rounded-md border px-3 py-2 text-sm ${level === "at" ? "border-blood/60 bg-blood/15" : "border-gold/40 bg-gold/10"}`}>
      <p className={`font-medium ${level === "at" ? "text-blood-bright" : "text-gold"}`}>{title}</p>
      <div className="mt-1 flex flex-col gap-1 text-parchment">{children}</div>
      <p className="mt-1 text-xs text-mist">{source}</p>
    </div>
  );
}

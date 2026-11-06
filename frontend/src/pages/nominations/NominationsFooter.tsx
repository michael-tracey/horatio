import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { StarredOut } from "../../api/types";
import { firstShown, nextShown, ROTATE_MS, rotates } from "./nominations";

/** The troupe's starred Player Nominations, for the foot of its pages: nothing for anyone who doesn't read them, or while there are none. */
export function NominationsFooter({ troupeId }: { troupeId: string }) {
  const starred = useQuery({
    queryKey: ["nominations-starred", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/nominations/starred", { params: { path: { troupe_id: troupeId } } })),
  });
  if (!starred.data?.length) return null;
  return <Rotation items={starred.data} />;
}

const reducedMotion = () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * A quiet line at the foot of the troupe's pages, one starred nomination at a time
 * with its month, never its author (#470). It starts somewhere new on each page
 * load and moves on every so often, but not for someone who asks for less motion,
 * and not while the pointer or focus is on it or it is paused. Next moves on by
 * hand; the skip link passes over it. It is never read out as it changes.
 */
export function Rotation({ items }: { items: readonly StarredOut[] }) {
  const [at, setAt] = useState(() => firstShown(items.length));
  const [paused, setPaused] = useState(false);
  const [held, setHeld] = useState(false);
  const [reduced] = useState(reducedMotion);
  const turning = rotates(items.length, paused || held, reduced);
  useEffect(() => {
    if (!turning) return;
    const timer = setInterval(() => setAt((i) => nextShown(i, items.length)), ROTATE_MS);
    return () => clearInterval(timer);
  }, [turning, items.length]);
  const shown = items[at % items.length]!;
  const button = "rounded px-1.5 py-0.5 text-xs text-mist hover:text-parchment focus-visible:text-parchment";
  return (
    <>
      <aside
        aria-label="Player Nominations"
        className="mt-10 border-t border-ash pt-4 text-sm text-mist"
        onMouseEnter={() => setHeld(true)}
        onMouseLeave={() => setHeld(false)}
        onFocus={() => setHeld(true)}
        onBlur={() => setHeld(false)}
      >
        <a href="#after-nominations" className="sr-only focus:not-sr-only focus:underline">
          Skip the nominations
        </a>
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
          <figure className="min-w-0 flex-1">
            <blockquote className="italic text-parchment/80 wrap-anywhere">“{shown.text}”</blockquote>
            <figcaption className="mt-0.5 text-xs">Player Nominations, {shown.month}</figcaption>
          </figure>
          {items.length > 1 && (
            <div className="flex shrink-0 gap-1">
              {!reduced && (
                <button type="button" className={button} aria-pressed={paused} onClick={() => setPaused(!paused)}>
                  {paused ? "Play" : "Pause"}
                </button>
              )}
              <button type="button" className={button} aria-label="Next nomination" onClick={() => setAt((i) => nextShown(i, items.length))}>
                Next
              </button>
            </div>
          )}
        </div>
      </aside>
      <span id="after-nominations" tabIndex={-1} />
    </>
  );
}

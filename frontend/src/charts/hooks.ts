import { useEffect, useRef, useState, useSyncExternalStore } from "react";

/**
 * The width of the element `ref` is on, kept up to date as it resizes (#706), so
 * a chart fills its card at any width, a phone's included. 0 until measured.
 */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const seen = new ResizeObserver(([entry]) => setWidth(Math.floor(entry?.contentRect.width ?? el.clientWidth)));
    seen.observe(el);
    return () => seen.disconnect();
  }, []);
  return { ref, width };
}

const REDUCE = "(prefers-reduced-motion: reduce)";

function subscribe(changed: () => void) {
  const query = typeof matchMedia === "function" ? matchMedia(REDUCE) : null;
  query?.addEventListener("change", changed);
  return () => query?.removeEventListener("change", changed);
}

/** Whether the person has asked for less motion: charts then change without transitions. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => (typeof matchMedia === "function" ? matchMedia(REDUCE).matches : false),
    () => false,
  );
}

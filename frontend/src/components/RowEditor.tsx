import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

/** The first control a keyboard can use in an editor: a field first, else a button. */
const FIELD = "input:not([type=hidden]):not(:disabled), select:not(:disabled), textarea:not(:disabled)";
const CONTROL = `${FIELD}, button:not(:disabled), a[href]`;

/**
 * Which row of a list has its editor open beneath it, one at a time (#648). Opening
 * remembers the button pressed; closing puts the focus back on it, or, when that row
 * has gone from the list, on what `fallback` is given to (the list's Add button, say).
 */
export function useRowEditor<T>(same: (a: T, b: T) => boolean = Object.is) {
  const [open, setOpen] = useState<T | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const spare = useRef<HTMLElement | null>(null);
  const returning = useRef(false);
  useEffect(() => {
    if (open !== null || !returning.current) return;
    returning.current = false;
    (opener.current?.isConnected ? opener.current : spare.current)?.focus();
  }, [open]);
  const isOpen = (t: T) => open !== null && same(open, t);
  const close = () => {
    returning.current = true;
    setOpen(null);
  };
  return {
    open,
    isOpen,
    close,
    /** Open t's editor from the button pressed, or close it if it is open already. */
    toggle: (t: T, button: HTMLElement) => {
      if (isOpen(t)) return close();
      opener.current = button;
      setOpen(t);
    },
    /** A ref for where the focus goes when the row that opened the editor has gone. */
    fallback: useCallback((el: HTMLElement | null) => {
      spare.current = el;
    }, []),
  };
}

/**
 * An editor shown under the row that opened it (#648), not at the top of a page
 * that may be long. As it opens, the focus moves to its first field, and it scrolls
 * into view when it reaches past the foot of the screen: its top first when it is
 * taller than the screen.
 */
export function RowEditor({ children, className }: { children: ReactNode; className?: string }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    (el.querySelector<HTMLElement>(FIELD) ?? el.querySelector<HTMLElement>(CONTROL) ?? el).focus({ preventScroll: true });
    const { top, bottom, height } = el.getBoundingClientRect();
    if (top < 0 || height > window.innerHeight) el.scrollIntoView?.({ block: "start" });
    else if (bottom > window.innerHeight) el.scrollIntoView?.({ block: "nearest" });
  }, []);
  return (
    <div ref={box} tabIndex={-1} className={`scroll-mt-4 focus:outline-none ${className ?? ""}`}>
      {children}
    </div>
  );
}

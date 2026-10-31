import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

/**
 * A popover opened by a button: pressing the button again, pressing anywhere
 * outside, or Escape closes it. Put `root` on what holds both, `button` on the
 * button and `popover` on the popover, and `shift` as its translateX: it opens
 * beside the button, then slides back inside the screen if it runs off an edge
 * (a phone).
 */
export function usePopover() {
  const [open, setOpen] = useState(false);
  const [shift, setShift] = useState(0);
  const id = useId();
  const root = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const popover = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !popover.current) return;
    const edge = 8;
    const { left, right } = popover.current.getBoundingClientRect();
    const width = document.documentElement.clientWidth;
    setShift(right > width - edge ? width - edge - right : left < edge ? edge - left : 0);
  }, [open]);

  const toggle = () => {
    setShift(0);
    setOpen(!open);
  };
  return { open, toggle, id, root, button, popover, style: shift ? { transform: `translateX(${shift}px)` } : undefined };
}

/**
 * A small ⓘ button that opens a popover with a few words about what it sits
 * beside: a heading, or a choice in the page title. Pressing it again, pressing
 * anywhere outside, or Escape closes it. `label` is what the button is called
 * to a screen reader ("About Skills"); the popover is its `children`, which
 * should be spans (`block` for separate lines) so it can sit inside a paragraph.
 */
export function InfoButton({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  const { open, toggle, id, root, button, popover, style } = usePopover();

  return (
    <span ref={root} className={`relative inline-flex align-middle ${className ?? ""}`}>
      <button
        ref={button}
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={id}
        onClick={toggle}
        className="relative inline-grid h-5 w-5 place-items-center rounded-full text-mist before:absolute before:-inset-2 before:content-[''] hover:text-parchment aria-expanded:text-gold"
      >
        {/* Drawn, not a letter, so it adds no text to the line it sits in. */}
        <svg viewBox="0 0 20 20" aria-hidden className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <circle cx="10" cy="10" r="8.25" />
          <path d="M10 9v5" />
          <circle cx="10" cy="6.2" r="0.6" fill="currentColor" />
        </svg>
      </button>
      {open && (
        <span
          ref={popover}
          id={id}
          style={style}
          className="absolute top-full block left-0 z-20 mt-1 w-64 max-w-[calc(100vw-2rem)] rounded-md border border-ash bg-night p-3 text-left font-sans text-xs leading-relaxed font-normal tracking-normal text-parchment normal-case shadow-lg"
        >
          {children}
        </span>
      )}
    </span>
  );
}

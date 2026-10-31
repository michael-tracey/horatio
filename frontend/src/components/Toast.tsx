import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router";

/**
 * The shared toast: one short line at the foot of the screen saying what just
 * happened, with an optional button such as Undo (issue #358).
 *
 *   const toast = useToast();
 *   toast({ message: "Spent 1 Blood · 9/10", action: { label: "Undo", onClick: undo } });
 *
 * One toast at a time: a new one takes the place of the last. It goes by itself
 * after 4 seconds, or 8 with a button so there is time to press it, and waits
 * while keyboard focus is on its button. It sits above the foot of the screen,
 * clear of the bars fixed there (the Play View's drawer button, the cart), and
 * above any element marked `data-toast-clear` (a sheet open from the foot of
 * the screen) as it appears. Screen readers read it out politely. Changing page clears it, as its
 * button would act on the page that is gone.
 */

export type ToastAction = { label: string; onClick: () => void };
export type ToastIn = {
  message: string;
  action?: ToastAction;
  /** How long it stays, in ms, if not the usual. */
  duration?: number;
};

type Shown = ToastIn & { id: number; lift: number };

/** How far up the screen the tops of elements marked `data-toast-clear` reach, in px. */
function clearance(): number {
  let lift = 0;
  for (const el of document.querySelectorAll("[data-toast-clear]")) {
    const box = el.getBoundingClientRect();
    if (box.height > 0) lift = Math.max(lift, window.innerHeight - box.top);
  }
  return lift;
}

const PLAIN = 4_000;
const WITH_ACTION = 8_000;

/** Outside a ToastProvider (a component's own test) a toast is quietly dropped. */
const ToastContext = createContext<(toast: ToastIn) => void>(() => {});

/** Show a toast in place of any already showing. */
export function useToast(): (toast: ToastIn) => void {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Shown | null>(null);
  const next = useRef(0);
  const show = useCallback((t: ToastIn) => setToast({ ...t, id: ++next.current, lift: clearance() }), []);
  const { pathname } = useLocation();
  useEffect(() => setToast(null), [pathname]);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {/* Always in the page, so a screen reader hears each toast as it arrives. */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="pointer-events-none fixed inset-x-0 z-40 flex justify-center px-4"
        style={{ bottom: `calc(max(5.5rem, ${(toast?.lift ?? 0) + 8}px) + env(safe-area-inset-bottom, 0px))` }}
      >
        {toast && <ToastCard key={toast.id} toast={toast} onDone={() => setToast((now) => (now?.id === toast.id ? null : now))} />}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ toast, onDone }: { toast: Shown; onDone: () => void }) {
  const [held, setHeld] = useState(false);
  const duration = toast.duration ?? (toast.action ? WITH_ACTION : PLAIN);
  // The provider's own renders don't restart the clock.
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    if (held) return;
    const timer = window.setTimeout(() => done.current(), duration);
    return () => window.clearTimeout(timer);
  }, [held, duration]);
  return (
    <div
      className="pointer-events-auto flex w-full max-w-md items-center gap-3 rounded-lg border border-gold/50 bg-dusk px-4 py-2 text-sm text-parchment shadow-2xl"
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
    >
      <p className="min-w-0 flex-1 py-1.5">{toast.message}</p>
      {toast.action && (
        <button
          type="button"
          className="-mr-2 min-h-10 shrink-0 rounded-md px-3 font-medium text-gold hover:bg-gold/10"
          onClick={() => {
            toast.action!.onClick();
            onDone();
          }}
        >
          {toast.action.label}
        </button>
      )}
    </div>
  );
}

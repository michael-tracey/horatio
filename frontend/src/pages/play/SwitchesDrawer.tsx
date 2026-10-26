import { useEffect, useId, useRef, useState } from "react";
import type { PoolModifier, PowerSwitch, TestPool } from "../../api/types";
import { ModifiersPanel } from "./Modifiers";
import { PowersList } from "./Powers";
import type { makeTap } from "./tracker";
import type { useModifiers } from "./useModifiers";

/** What is on, in a few words: the forms and powers, then the player's own modifiers with their amounts. */
export function inUse(powers: PowerSwitch[], modifiers: PoolModifier[]): string {
  const names = [...powers.filter((p) => p.on).map((p) => p.name), ...modifiers.filter((m) => m.on).map((m) => `${m.amount < 0 ? "−" : "+"}${Math.abs(m.amount)} ${m.label}`)];
  return names.length > 0 ? `In use: ${names.join(", ")}` : "Nothing in use";
}

/**
 * Forms, powers and the player's own modifiers, kept out of the page so the
 * pools come first (issue #211): a button fixed at the foot of the Pools tab
 * says what is on, and opens them in a bottom sheet. The sheet leaves the top of
 * the page showing, so the pools can be watched as the switches change.
 */
export function SwitchesDrawer({
  pools,
  powers,
  modifiers,
  tap,
}: {
  pools: TestPool[];
  powers: PowerSwitch[];
  modifiers: ReturnType<typeof useModifiers>;
  tap: (what: Parameters<typeof makeTap>[0]) => void;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const sheet = useRef<HTMLDivElement>(null);
  const close = () => {
    setOpen(false);
    button.current?.focus();
  };

  useEffect(() => {
    if (!open) return;
    sheet.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    // A tap outside closes it (the button toggles it itself).
    const onDown = (e: PointerEvent) => {
      const at = e.target as Node;
      if (!sheet.current?.contains(at) && !button.current?.contains(at)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open]);

  return (
    <>
      <div className="fixed inset-x-0 bottom-0 z-10 border-t border-gold/50 bg-dusk/95 px-4 py-2 backdrop-blur">
        <button
          ref={button}
          type="button"
          className="mx-auto flex min-h-12 w-full max-w-3xl items-center justify-between gap-3 text-left"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => (open ? close() : setOpen(true))}
        >
          <span className="min-w-0 truncate text-sm text-parchment">{inUse(powers, modifiers.modifiers)}</span>
          <span className="shrink-0 text-xs text-gold">{open ? "Close" : "Forms, powers and modifiers"}</span>
        </button>
      </div>
      {open && (
        <div
          id={id}
          ref={sheet}
          tabIndex={-1}
          className="fixed inset-x-0 bottom-0 z-20 max-h-[60vh] overflow-y-auto border-t border-gold/50 bg-dusk p-4 shadow-2xl outline-none"
          role="dialog"
          aria-label="Forms, powers and modifiers"
        >
          <div className="mx-auto flex max-w-3xl flex-col gap-3">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-display text-gold">Forms and powers in use</h2>
              <button type="button" className="min-h-10 px-2 text-sm text-mist underline hover:text-parchment" onClick={close}>
                Close
              </button>
            </div>
            <PowersList powers={powers} tap={tap} />
            <ModifiersPanel pools={pools} modifiers={modifiers} />
          </div>
        </div>
      )}
    </>
  );
}

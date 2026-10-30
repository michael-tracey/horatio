import { useEffect, useId, useRef, type ReactNode } from "react";

/** On a phone, the whole screen. */
const PHONE_FULL = "max-sm:m-0 max-sm:h-dvh max-sm:max-h-none max-sm:w-screen max-sm:max-w-none max-sm:rounded-none max-sm:border-0 max-sm:open:flex max-sm:open:flex-col";

/** A modal dialog over the page: Escape, the × or a click outside closes it.
 * Its content mounts only while open, so forms inside start fresh each time.
 * A wide one has room for a form of several columns; a `phoneFull` one fills a
 * phone's screen, with a Close button across its foot in place of the ×. */
export function Dialog({
  title,
  open,
  onClose,
  wide = false,
  phoneFull = false,
  children,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  wide?: boolean;
  phoneFull?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className={`m-auto ${wide ? "w-[min(48rem,calc(100vw-2rem))]" : "w-[min(28rem,calc(100vw-2rem))]"} rounded-lg border border-ash bg-dusk p-0 text-parchment shadow-xl backdrop:bg-black/60 ${phoneFull ? PHONE_FULL : ""}`}
    >
      <div className="flex items-center justify-between gap-3 border-b border-ash px-4 py-3">
        <h2 id={titleId} className="font-display text-gold">
          {title}
        </h2>
        <button type="button" aria-label="Close" className={`text-xl leading-none text-mist hover:text-parchment ${phoneFull ? "max-sm:hidden" : ""}`} onClick={onClose}>
          ×
        </button>
      </div>
      <div className={`p-4 ${phoneFull ? "max-sm:flex-1 max-sm:overflow-y-auto" : ""}`}>{open && children}</div>
      {phoneFull && (
        <div className="border-t border-ash px-4 py-3 sm:hidden">
          <button type="button" className="min-h-11 w-full rounded-md border border-ash text-parchment hover:border-gold" onClick={onClose}>
            Close
          </button>
        </div>
      )}
    </dialog>
  );
}

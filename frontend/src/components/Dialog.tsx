import { useEffect, useId, useRef, type ReactNode } from "react";

/** A modal dialog over the page: Escape, the × or a click outside closes it.
 * Its content mounts only while open, so forms inside start fresh each time.
 * A wide one has room for a form of several columns. */
export function Dialog({
  title,
  open,
  onClose,
  wide = false,
  children,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  wide?: boolean;
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
      className={`m-auto ${wide ? "w-[min(48rem,calc(100vw-2rem))]" : "w-[min(28rem,calc(100vw-2rem))]"} rounded-lg border border-ash bg-dusk p-0 text-parchment shadow-xl backdrop:bg-black/60`}
    >
      <div className="flex items-center justify-between gap-3 border-b border-ash px-4 py-3">
        <h2 id={titleId} className="font-display text-gold">
          {title}
        </h2>
        <button type="button" aria-label="Close" className="text-xl leading-none text-mist hover:text-parchment" onClick={onClose}>
          ×
        </button>
      </div>
      <div className="p-4">{open && children}</div>
    </dialog>
  );
}

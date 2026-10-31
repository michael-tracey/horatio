import type { ReactNode } from "react";
import { usePopover } from "./InfoButton";

/**
 * A small square button beside a rating or a line: −, + or ×. On a touch
 * screen it grows to 40px; put neighbours in a `StepButtons`, which spaces
 * them further apart there.
 *
 * When it can't be used and there is a `reason`, it stays tappable rather than
 * disabled: a tap shows the reason under it, as a hover title never shows on a
 * phone. The reason is its description to a screen reader too.
 */
export function StepButton({
  label,
  disabled = false,
  reason,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  /** Why it can't be used, when it can't. */
  reason?: string;
  onClick: () => void;
  children: ReactNode;
}) {
  const { open, toggle, id, root, button, popover, style } = usePopover();
  const explained = disabled && !!reason;
  const look = [
    "grid h-6 w-6 place-items-center rounded border text-xs leading-none pointer-coarse:h-10 pointer-coarse:w-10 pointer-coarse:text-base",
    disabled ? "cursor-not-allowed border-ash text-line" : "border-line text-mist hover:border-mist hover:text-parchment",
  ].join(" ");
  if (!explained) {
    return (
      <button type="button" aria-label={label} disabled={disabled} onClick={onClick} className={look}>
        {children}
      </button>
    );
  }
  return (
    <span ref={root} className="relative inline-flex">
      <button
        ref={button}
        type="button"
        aria-label={label}
        aria-disabled="true"
        aria-describedby={id}
        title={reason}
        onClick={toggle}
        className={look}
      >
        {children}
      </button>
      {/* Always there for the description; shown once tapped. */}
      <span
        ref={popover}
        id={id}
        style={style}
        className={`${open ? "block" : "hidden"} absolute top-full right-0 z-20 mt-1 w-56 max-w-[calc(100vw-2rem)] rounded-md border border-ash bg-night p-3 text-left text-xs leading-relaxed text-parchment shadow-lg`}
      >
        {reason}
      </span>
    </span>
  );
}

/** −/+ side by side, with more room between them on a touch screen. */
export function StepButtons({ children }: { children: ReactNode }) {
  return <span className="flex gap-1 pointer-coarse:gap-3">{children}</span>;
}

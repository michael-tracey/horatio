import { createContext, useContext, useEffect, useRef } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { Link } from "react-router";
import { usePopover } from "./InfoButton";
import { Button } from "./ui";

/** What a menu item looks like; for an item made by hand, such as one that explains why it can't be chosen. */
export const MENU_ITEM = "block w-full px-3 py-2 text-left text-sm hover:bg-ash focus-visible:bg-ash disabled:cursor-default disabled:text-mist disabled:hover:bg-transparent";

/** Closes the menu and gives focus back to its button: what choosing an item does first. */
const Chosen = createContext<() => void>(() => {});

/**
 * A button that opens a menu of actions: the ⋯ on a character, a row of People, or
 * the chevron beside Print. Pressing the button again, pressing outside or Escape
 * closes it; ↑ and ↓ (and Home and End) move between the items, and Tab leaves it.
 * It opens under the button, lined up with its right edge, and slides back on screen
 * if it runs off an edge (a phone). Choosing an item, or Escape, gives focus back to
 * the button, so a dialog an item opens hands it back there too.
 *
 * `label` names the button to a screen reader ("Actions for Ines"). The items are
 * `MenuItem`s and `MenuLink`s, in `MenuGroup`s if there are several kinds: a line
 * divides the groups that have something in them. A plain `<Button>` unless
 * `buttonClassName` styles the button itself.
 */
export function ActionMenu({
  label,
  children,
  trigger = "⋯",
  variant = "secondary",
  buttonClassName,
  menuClassName = "w-64",
  className,
}: {
  label: string;
  children: ReactNode;
  trigger?: ReactNode;
  variant?: "secondary" | "ghost";
  buttonClassName?: string;
  menuClassName?: string;
  className?: string;
}) {
  const { open, toggle, close, root, button, popover, style } = usePopover<HTMLDivElement, HTMLDivElement>();
  // Opened with ↑, it starts at the last item; otherwise at the first.
  const startAtEnd = useRef(false);
  const items = () => Array.from(popover.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') ?? []);

  useEffect(() => {
    if (!open) return;
    const all = items();
    (startAtEnd.current ? all.at(-1) : all[0])?.focus();
    startAtEnd.current = false;
    // Only on opening: the items are there by then.
  }, [open]);

  const chosen = () => {
    close();
    button.current?.focus();
  };

  const onButtonKey = (e: KeyboardEvent) => {
    if (open || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return;
    e.preventDefault();
    startAtEnd.current = e.key === "ArrowUp";
    toggle();
  };

  const onMenuKey = (e: KeyboardEvent) => {
    if (e.key === "Tab") return close();
    const all = items();
    if (!all.length) return;
    const at = all.indexOf(document.activeElement as HTMLElement);
    const next = { ArrowDown: at + 1, ArrowUp: at < 0 ? -1 : at - 1, Home: 0, End: -1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    all[(next + all.length) % all.length]?.focus();
  };

  const buttonProps = {
    ref: button,
    type: "button" as const,
    "aria-label": label,
    "aria-haspopup": "menu" as const,
    "aria-expanded": open,
    onClick: toggle,
    onKeyDown: onButtonKey,
  };

  return (
    <div ref={root} className={`relative ${className ?? ""}`}>
      {buttonClassName ? (
        <button {...buttonProps} className={buttonClassName}>
          {trigger}
        </button>
      ) : (
        <Button {...buttonProps} variant={variant}>
          {trigger}
        </Button>
      )}
      {open && (
        <div
          ref={popover}
          role="menu"
          aria-label={label}
          style={style}
          onKeyDown={onMenuKey}
          className={`absolute top-full right-0 z-20 mt-1 max-w-[calc(100vw-1rem)] overflow-hidden rounded-md border border-ash bg-dusk py-1 shadow-xl [&>[role=group]:not(:empty)~[role=group]:not(:empty)]:border-t [&>[role=group]:not(:empty)~[role=group]:not(:empty)]:border-ash ${menuClassName}`}
        >
          <Chosen.Provider value={chosen}>{children}</Chosen.Provider>
        </div>
      )}
    </div>
  );
}

/** Some items of a menu that belong together; a line divides it from the group before. */
export function MenuGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={label}>
      {children}
    </div>
  );
}

/** An item of an `ActionMenu`: choosing it closes the menu, then does `onSelect`. */
export function MenuItem({
  onSelect,
  disabled,
  danger,
  children,
}: {
  onSelect?: () => void;
  disabled?: boolean;
  /** Red, for an item that can't be undone. */
  danger?: boolean;
  children: ReactNode;
}) {
  const chosen = useContext(Chosen);
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      className={`${MENU_ITEM} ${danger ? "text-blood-bright" : ""}`}
      onClick={() => {
        chosen();
        onSelect?.();
      }}
    >
      {children}
    </button>
  );
}

/** An item of an `ActionMenu` that goes to another page. */
export function MenuLink({ to, children }: { to: string; children: ReactNode }) {
  const chosen = useContext(Chosen);
  return (
    <Link role="menuitem" to={to} className={MENU_ITEM} onClick={chosen}>
      {children}
    </Link>
  );
}

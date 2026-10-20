import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

/**
 * A link with a chevron beside it: the link goes to the usual choice, the
 * chevron opens the other choices. Print uses it: numbers by default, pips if
 * you ask.
 */
export function SplitLink({ to, label, choices, menuLabel }: { to: string; label: string; choices: { to: string; label: string }[]; menuLabel: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  const part = "inline-flex min-h-10 items-center justify-center border border-ash bg-dusk text-sm hover:border-mist";
  return (
    <div ref={box} className="relative flex">
      <Link to={to} className={`${part} flex-1 rounded-l-md px-4`}>
        {label}
      </Link>
      <button type="button" aria-label={menuLabel} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)} className={`${part} -ml-px rounded-r-md px-2.5 text-mist`}>
        ▾
      </button>
      {open && (
        <div role="menu" className="absolute top-full right-0 z-20 mt-1 w-44 overflow-hidden rounded-md border border-ash bg-dusk py-1 shadow-xl">
          {choices.map((c) => (
            <Link key={c.to} role="menuitem" to={c.to} className="block px-3 py-2 text-sm hover:bg-ash" onClick={() => setOpen(false)}>
              {c.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

import { useId, useRef, useState, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router";
import type { TroupeOut } from "../../api/types";
import { Input } from "../../components/ui";
import { SHORTEST } from "../../search/search";
import type { abilities } from "./roles";
import { findSettings, settingsIndex } from "./settingsIndex";

/** Settings shown at once; a word more narrows them. */
const SHOWN = 8;

/**
 * Find a setting (#1047), at the top of every Customise tab: type part of a setting's name, or
 * a word of what it does, and choose it to go there, its tab's Settings open or its card
 * scrolled to and glowing. Enter opens the first; Up and Down go through them; Escape clears.
 */
export function FindSetting({ troupe, can }: { troupe: TroupeOut; can: ReturnType<typeof abilities> }) {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const listId = useId();
  const words = text.trim();
  const found = words.length >= SHORTEST ? findSettings(settingsIndex(troupe, can), words) : [];
  const showing = open && words.length >= SHORTEST;

  const pick = () => {
    setText("");
    setOpen(false);
  };

  // Up and Down go from the box through the settings found, in order.
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape" && showing) {
      e.preventDefault();
      pick();
      box.current?.querySelector("input")?.focus();
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const stops = [...(box.current?.querySelectorAll<HTMLElement>("input, a") ?? [])];
    const at = stops.indexOf(document.activeElement as HTMLElement);
    const next = stops[e.key === "ArrowDown" ? Math.min(at + 1, stops.length - 1) : Math.max(at - 1, 0)];
    if (!next) return;
    e.preventDefault();
    next.focus();
  };

  return (
    <div
      ref={box}
      role="search"
      aria-label="Find a setting"
      onKeyDown={onKeyDown}
      // Closed once the focus leaves the box and what it found.
      onBlur={(e) => {
        if (!box.current?.contains(e.relatedTarget as Node | null)) setOpen(false);
      }}
      className="relative mb-4 w-full sm:mb-6 sm:max-w-md print:hidden"
    >
      <Input
        type="search"
        aria-label="Find a setting"
        aria-controls={showing ? listId : undefined}
        placeholder="Find a setting…"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          const first = found[0];
          if (e.key !== "Enter" || !first) return;
          e.preventDefault();
          pick();
          navigate(first.to);
        }}
        className="w-full"
      />
      {showing && (
        <div id={listId} className="absolute inset-x-0 top-full z-20 mt-1 max-h-[60dvh] overflow-y-auto rounded-md border border-ash bg-dusk p-1 shadow-lg">
          {found.length === 0 ? (
            <p role="status" className="px-3 py-2 text-sm text-mist">
              No setting found for “{words}”.
            </p>
          ) : (
            <>
              <p role="status" className="sr-only">
                {found.length === 1 ? "1 setting found." : `${found.length} settings found.`}
              </p>
              <ul aria-label="Settings found" className="flex flex-col">
                {found.slice(0, SHOWN).map((s) => (
                  <li key={s.to}>
                    <Link
                      to={s.to}
                      onClick={pick}
                      className="flex min-h-11 flex-col justify-center rounded-md px-3 py-1.5 hover:bg-ash/40 focus:bg-ash/40 focus:outline-none"
                    >
                      <span className="text-parchment wrap-anywhere">{s.title}</span>
                      <span className="line-clamp-2 text-xs text-mist wrap-anywhere">{[s.where, s.hint].filter(Boolean).join(" · ")}</span>
                    </Link>
                  </li>
                ))}
              </ul>
              {found.length > SHOWN && <p className="px-3 py-1 text-xs text-mist">More than these: add a word to narrow them.</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}

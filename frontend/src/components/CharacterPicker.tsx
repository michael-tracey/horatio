import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { findPatrons, patronLabel } from "../pages/character/status";
import { Input } from "./ui";

/** A character to pick, with the titles it holds in the troupe ("Prince"), if any. */
export type CharacterChoice = { id: string; name: string; kind: string; title: string };

/**
 * A search box over a troupe's characters, each named with its titles, opening a
 * list to pick from: the patron of a status (#252), or who receives an item (#282).
 * `listLabel` names the list; `extra` adds to each option, before PC or NPC.
 */
export function CharacterPicker<T extends CharacterChoice>({
  label,
  listLabel,
  choices,
  picked,
  onPick,
  none = "No one matches.",
  extra,
}: {
  label: string;
  listLabel: string;
  choices: T[];
  picked: string | null;
  onPick: (choice: T | null) => void;
  /** Said when nothing matches what was typed. */
  none?: string;
  extra?: (choice: T) => ReactNode;
}) {
  const chosen = choices.find((c) => c.id === picked);
  const listId = useId();
  const inputId = useId();
  const [typed, setTyped] = useState(chosen ? patronLabel(chosen) : "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const closing = useRef<ReturnType<typeof setTimeout>>(undefined);
  // Once someone is picked, opening the list again shows everyone.
  const options = findPatrons(choices, picked ? "" : typed);
  const pick = (choice: T) => {
    onPick(choice);
    setTyped(patronLabel(choice));
    setOpen(false);
    setActive(-1);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((active + step + options.length) % Math.max(options.length, 1));
    } else if (e.key === "Enter" && open && options[active]) {
      e.preventDefault();
      pick(options[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={inputId} className="text-mist">
        {label}
      </label>
      <div className="relative">
        <Input
          id={inputId}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listId}
          aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
          autoComplete="off"
          placeholder={choices.length ? "Find a character" : "No one to pick"}
          value={typed}
          className="pr-8"
          onChange={(e) => {
            setTyped(e.target.value);
            if (picked) onPick(null);
            setOpen(true);
            setActive(-1);
          }}
          onFocus={() => {
            clearTimeout(closing.current);
            setOpen(true);
          }}
          // Late enough that a click on the list lands first.
          onBlur={() => {
            closing.current = setTimeout(() => setOpen(false), 150);
          }}
          onKeyDown={onKeyDown}
        />
        <span aria-hidden="true" className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs text-mist">
          ▾
        </span>
        {open && (
          <div
            onMouseDown={(e) => e.preventDefault()}
            className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-ash bg-dusk py-1 shadow-lg"
          >
            <ul id={listId} role="listbox" aria-label={listLabel}>
              {options.map((choice, i) => (
                <li
                  key={choice.id}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === active}
                  onClick={() => pick(choice)}
                  className={`flex cursor-pointer items-center gap-2 px-3 py-2 text-sm ${i === active ? "bg-gold/20 text-gold" : "hover:bg-night"}`}
                >
                  <span className="min-w-0 flex-1 truncate">{patronLabel(choice)}</span>
                  {extra?.(choice)}
                  <span className="shrink-0 text-xs text-mist">{choice.kind === "pc" ? "PC" : "NPC"}</span>
                </li>
              ))}
            </ul>
            {options.length === 0 && <p className="px-3 py-2 text-sm text-mist">{none}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

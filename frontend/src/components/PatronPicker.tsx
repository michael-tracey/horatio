import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { api, unwrap } from "../api/client";
import type { PatronChoiceOut } from "../api/types";
import { findPatrons, patronLabel } from "../pages/character/status";
import { Input } from "./ui";

export function usePatrons(characterId: string) {
  return useQuery({
    queryKey: ["status-patrons", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/status/patrons", { params: { path: { character_id: characterId } } })),
    staleTime: 60_000,
  });
}

/**
 * Who gave a status (MET: VTM p. 310): a search box over the home troupe's
 * characters, each with the title it holds there, and beside it a field for anyone
 * the list does not cover. One or both is needed. `troupe` names the home troupe.
 */
export function PatronPicker({
  characterId,
  troupe,
  patronId,
  patronText,
  onChange,
}: {
  characterId: string;
  troupe: string | null;
  patronId: string | null;
  patronText: string;
  onChange: (patronId: string | null, patronText: string) => void;
}) {
  const patrons = usePatrons(characterId);
  const choices = patrons.data ?? [];
  const picked = choices.find((c) => c.id === patronId);
  const listId = useId();
  const inputId = useId();
  const textId = useId();
  const [typed, setTyped] = useState(picked ? patronLabel(picked) : "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const closing = useRef<ReturnType<typeof setTimeout>>(undefined);
  // Once someone is picked, opening the list again shows everyone.
  const options = findPatrons(choices, patronId ? "" : typed);
  const pick = (choice: PatronChoiceOut) => {
    onChange(choice.id, patronText);
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
    <fieldset className="grid gap-2 sm:grid-cols-2">
      <legend className="mb-1 text-sm text-mist">
        Patron: who gave it. Pick {troupe ? `one of ${troupe}'s characters` : "a character"}, say who, or both.
      </legend>
      <div className="flex flex-col gap-1 text-sm">
        <label htmlFor={inputId} className="text-mist">
          A character
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
              if (patronId) onChange(null, patronText);
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
              <ul id={listId} role="listbox" aria-label="Patrons">
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
                    <span className="shrink-0 text-xs text-mist">{choice.kind === "pc" ? "PC" : "NPC"}</span>
                  </li>
                ))}
              </ul>
              {options.length === 0 && <p className="px-3 py-2 text-sm text-mist">No one matches. Say who in the other field.</p>}
            </div>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-1 text-sm">
        <label htmlFor={textId} className="text-mist">
          Or in your own words
        </label>
        <Input
          id={textId}
          value={patronText}
          maxLength={500}
          placeholder="Archon Halloran, at the Charlotte conclave"
          onChange={(e) => onChange(patronId, e.target.value)}
        />
      </div>
    </fieldset>
  );
}

import { useId, useRef, useState, type KeyboardEvent } from "react";
import type { CharacterChoice } from "../../api/types";
import { Input } from "../../components/ui";
import { findCharacters } from "./logInfluence";

type Option = { kind: "character"; character: CharacterChoice } | { kind: "name"; name: string };

/**
 * Who took an influence action: a search box over the troupe's PCs and NPCs that
 * opens as soon as it is focused, with typing narrowing it. Or a name only, for
 * someone not in Horatio: whatever was typed, offered last.
 *
 * `who` is "c:<character id>", "name" (with `name`), or "" until someone is picked.
 */
export function WhoPicker({
  characters,
  who,
  name,
  onChange,
  id,
  "aria-describedby": describedBy,
}: {
  characters: CharacterChoice[];
  who: string;
  name: string;
  onChange: (who: string, name: string) => void;
  id?: string;
  "aria-describedby"?: string;
}) {
  const listId = useId();
  const picked = who.startsWith("c:") ? characters.find((c) => `c:${c.id}` === who) : undefined;
  const shown = picked ? picked.name : who === "name" ? name : "";
  const [text, setText] = useState(shown);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const closing = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Once someone is picked, opening the list again shows everyone, to pick someone else.
  const typed = who ? "" : text;
  const options: Option[] = [
    ...findCharacters(characters, typed).map((character) => ({ kind: "character" as const, character })),
    ...(typed.trim() ? [{ kind: "name" as const, name: typed.trim() }] : []),
  ];
  const pick = (option: Option) => {
    if (option.kind === "character") {
      onChange(`c:${option.character.id}`, "");
      setText(option.character.name);
    } else {
      onChange("name", option.name);
      setText(option.name);
    }
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
    <div className="relative">
      <Input
        id={id}
        aria-describedby={describedBy}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        placeholder="Find a character, or type a name"
        value={text}
        className="pr-8"
        onChange={(e) => {
          setText(e.target.value);
          if (who) onChange("", "");
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
          <ul id={listId} role="listbox" aria-label="Characters">
            {options.map((option, i) => (
              <li
                key={option.kind === "character" ? option.character.id : "name"}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onClick={() => pick(option)}
                className={`flex cursor-pointer items-center gap-2 px-3 py-2 text-sm ${i === active ? "bg-gold/20 text-gold" : "hover:bg-night"}`}
              >
                {option.kind === "character" ? (
                  <>
                    <span className="min-w-0 flex-1 truncate">{option.character.name}</span>
                    <span className="shrink-0 text-xs text-mist">{option.character.kind === "pc" ? "PC" : "NPC"}</span>
                  </>
                ) : (
                  <>
                    <span className="min-w-0 flex-1 truncate">{option.name}</span>
                    <span className="shrink-0 text-xs text-mist">name only, not in Horatio</span>
                  </>
                )}
              </li>
            ))}
          </ul>
          {options.length === 0 && <p className="px-3 py-2 text-sm text-mist">No characters yet. Type a name to log it under.</p>}
        </div>
      )}
    </div>
  );
}

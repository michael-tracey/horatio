import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useId, useState, type KeyboardEvent } from "react";
import { api, unwrap } from "../api/client";
import { Input } from "./ui";

/** Someone's handle as others see it: "@night_owl". */
export function AtHandle({ handle, className = "text-mist" }: { handle: string; className?: string }) {
  return <span className={className}>@{handle}</span>;
}

/**
 * Pick someone by their handle, with a type-ahead: handles starting with what is
 * typed first, then names with it in them. The value is the handle as typed or
 * picked; the server finds whoever has it (or had it lately).
 */
export function PersonPicker({
  value,
  onChange,
  id,
  required,
  "aria-describedby": describedBy,
}: {
  value: string;
  onChange: (handle: string) => void;
  id?: string;
  required?: boolean;
  "aria-describedby"?: string;
}) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const q = useDeferredValue(value.trim().replace(/^@/, ""));
  const found = useQuery({
    queryKey: ["handles", q],
    queryFn: () => unwrap(api.GET("/api/handles", { params: { query: { q } } })),
    enabled: open && q.length > 0,
    placeholderData: (previous) => previous,
    staleTime: 30_000,
  });
  const people = q && found.data ? found.data : [];
  const shown = open && people.length > 0;
  // Nothing to suggest when what is typed is already exactly someone's handle.
  const exact = people.length === 1 && people[0]!.handle.toLowerCase() === q.toLowerCase();

  const pick = (handle: string) => {
    onChange(handle);
    setOpen(false);
    setActive(-1);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!shown) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((a) => (a + step + people.length) % people.length);
    } else if (e.key === "Enter" && active >= 0 && people[active]) {
      e.preventDefault();
      pick(people[active].handle);
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
        aria-expanded={shown && !exact}
        aria-controls={listId}
        aria-activedescendant={shown && active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        autoCapitalize="none"
        spellCheck={false}
        placeholder="@handle"
        required={required}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        // Late enough that a click on a suggestion lands first.
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
      />
      {shown && !exact && (
        <ul id={listId} role="listbox" className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-ash bg-dusk py-1 shadow-lg">
          {people.map((p, i) => (
            <li
              key={p.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(p.handle)}
              className={`flex cursor-pointer items-baseline gap-2 px-3 py-2 text-sm ${i === active ? "bg-gold/20 text-gold" : "hover:bg-night"}`}
            >
              <span>@{p.handle}</span>
              <span className="truncate text-xs text-mist">{p.display_name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

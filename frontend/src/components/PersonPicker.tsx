import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { useDeferredValue, useEffect, useId, useRef, useState, type KeyboardEvent, type UIEvent } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { roleLabel } from "../pages/troupe/roles";
import { Avatar } from "./Avatar";
import { Input } from "./ui";

type Someone = components["schemas"]["Someone"];

/** Someone's handle as others see it: "@night_owl". */
export function AtHandle({ handle, className = "text-mist" }: { handle: string; className?: string }) {
  return <span className={className}>@{handle}</span>;
}

/**
 * Pick someone from a list of people that opens as soon as the box is focused:
 * typing filters it, handles starting with what is typed first, then names with
 * it in them. Picking for a troupe (`troupeId`), its players come first, and
 * those already on its staff are greyed out with their role. More load as the
 * list scrolls. Never shows an email.
 *
 * The value is the handle as typed or picked; the server finds whoever has it
 * (or had it lately).
 */
export function PersonPicker({
  value,
  onChange,
  troupeId,
  id,
  required,
  "aria-describedby": describedBy,
}: {
  value: string;
  onChange: (handle: string) => void;
  troupeId?: string;
  id?: string;
  required?: boolean;
  "aria-describedby"?: string;
}) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [picked, setPicked] = useState<string | null>(null);
  const closing = useRef<ReturnType<typeof setTimeout>>(undefined);
  const show = () => {
    clearTimeout(closing.current);
    setOpen(true);
  };
  // Once someone is picked, opening the list again shows everyone, to pick someone else.
  const q = useDeferredValue(value === picked ? "" : value.trim().replace(/^@/, ""));
  const found = useInfiniteQuery({
    queryKey: ["handles", troupeId ?? null, q],
    queryFn: ({ pageParam }) => unwrap(api.GET("/api/handles", { params: { query: { q, troupe_id: troupeId, offset: pageParam } } })),
    initialPageParam: 0,
    getNextPageParam: (page) => page.next_offset ?? undefined,
    enabled: open,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
  const people = found.data?.pages.flatMap((page) => page.people) ?? [];
  const pickable = (p: Someone | undefined) => p !== undefined && !p.staff_role;

  useEffect(() => {
    if (active >= 0) document.getElementById(`${listId}-${active}`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, listId]);

  const pick = (p: Someone) => {
    if (!pickable(p)) return;
    onChange(p.handle);
    setPicked(p.handle);
    setOpen(false);
    setActive(-1);
  };
  const more = () => {
    if (found.hasNextPage && !found.isFetchingNextPage) void found.fetchNextPage();
  };
  const onScroll = (e: UIEvent<HTMLDivElement>) => {
    const box = e.currentTarget;
    if (box.scrollTop + box.clientHeight >= box.scrollHeight - 48) more();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) return show();
      const step = e.key === "ArrowDown" ? 1 : -1;
      // The next one that can be picked, skipping those already on the staff.
      let next = active;
      for (let i = 0; i < people.length; i++) {
        next = (next + step + people.length) % people.length;
        if (pickable(people[next])) break;
      }
      if (pickable(people[next])) setActive(next);
      if (next >= people.length - 3) more();
    } else if (e.key === "Enter" && open && pickable(people[active])) {
      e.preventDefault();
      pick(people[active]!);
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
        autoCapitalize="none"
        spellCheck={false}
        placeholder="Pick someone, or type to find them"
        required={required}
        value={value}
        className="pr-8"
        onChange={(e) => {
          onChange(e.target.value);
          show();
          setActive(-1);
        }}
        onFocus={show}
        onClick={show}
        // Late enough that a click on someone in the list lands first; coming
        // back to the box before then keeps it open.
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
          onScroll={onScroll}
          // Keeps the box focused while the list is clicked or scrolled.
          onMouseDown={(e) => e.preventDefault()}
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-ash bg-dusk py-1 shadow-lg"
        >
          <ul id={listId} role="listbox" aria-label="People">
            {people.map((p, i) => {
              const can = pickable(p);
              return (
                <li
                  key={p.id}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === active}
                  aria-disabled={!can || undefined}
                  onClick={() => pick(p)}
                  className={`flex items-center gap-2 px-3 py-2 text-sm ${
                    !can ? "cursor-not-allowed opacity-50" : i === active ? "cursor-pointer bg-gold/20 text-gold" : "cursor-pointer hover:bg-night"
                  }`}
                >
                  <Avatar name={p.display_name} size="xs" />
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate">{p.display_name}</span>
                    <AtHandle handle={p.handle} className="truncate text-xs text-mist" />
                  </span>
                  {p.staff_role ? (
                    <span className="shrink-0 text-xs text-mist">{roleLabel(p.staff_role)}</span>
                  ) : (
                    p.plays_here && <span className="shrink-0 rounded-full border border-gold/50 px-2 text-xs text-gold">Plays here</span>
                  )}
                </li>
              );
            })}
          </ul>
          {found.isPending || found.isFetchingNextPage ? (
            <p className="px-3 py-2 text-sm text-mist">Finding people…</p>
          ) : found.isError ? (
            <p className="px-3 py-2 text-sm text-mist">{found.error.message}</p>
          ) : (
            people.length === 0 && <p className="px-3 py-2 text-sm text-mist">Nobody has that name or handle.</p>
          )}
        </div>
      )}
    </div>
  );
}

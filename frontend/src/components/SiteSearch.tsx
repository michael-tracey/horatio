import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { api, unwrap } from "../api/client";
import { characterOf, currentTroupe, isSearchShortcut, searchHere, SHORTEST, type SearchGroup, type SearchHit } from "../search/search";
import { Dialog } from "./Dialog";
import { TroupePill } from "./TroupePill";
import { ErrorText, Input } from "./ui";
import { useCustodianOn } from "../custodianAccess";

/**
 * Search everything from the top bar (#1046): its button, and `/` or Ctrl+K (⌘K) from any
 * page, open a box that finds the characters, players, boons, locations, quests,
 * equipment, news, announcements and help the person may see, each kind a group, the
 * troupe they are on first (on a character's pages, its home troupe: #1147), and that
 * troupe's settings for its storytellers (#1047, #1133). Each hit opens its page. On a
 * phone it fills the screen.
 */
export function SiteSearch() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      // Not over another dialog, which has the keyboard.
      if (!isSearchShortcut(e) || document.querySelector("dialog[open]")) return;
      e.preventDefault();
      setOpen(true);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <button
        type="button"
        aria-label="Search everything"
        aria-keyshortcuts="/ Control+K Meta+K"
        title="Search (/)"
        onClick={() => setOpen(true)}
        // As big as the bell and the menu, so the bar keeps its height; a finger's 44 px to tap, around it.
        className="relative grid h-9 w-9 shrink-0 place-items-center rounded-full text-mist before:absolute before:-inset-1 before:content-[''] hover:bg-ash/60 hover:text-parchment print:hidden"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="6.5" />
          <path d="M16 16l4.5 4.5" />
        </svg>
      </button>
      <Dialog title="Search" open={open} onClose={() => setOpen(false)} wide phoneFull>
        <SearchPanel onPick={() => setOpen(false)} />
      </Dialog>
    </>
  );
}

/** What was typed, once it has stood still a moment: one search a pause, not one a letter. */
function useSettled(value: string, ms = 200): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

export function SearchPanel({ onPick }: { onPick: () => void }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  // On a character's pages, its home troupe counts as the current troupe (#1147). Its page
  // holds the character already (ClanNames' route wrapper asks for it), so this only reads it.
  const characterId = characterOf(pathname);
  const character = useQuery({
    queryKey: ["character", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}", { params: { path: { character_id: characterId! } } })),
    enabled: false,
  });
  const troupeId = currentTroupe(pathname, character.data?.home_troupe_id);
  // The troupe as the person sees it, as its pages have it, for its settings (#1047).
  const custodianOn = useCustodianOn();
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId! } } })),
    enabled: !!troupeId,
  });
  const place = { troupeId, troupe: troupeId ? troupe.data : null, custodian: custodianOn };
  const [text, setText] = useState("");
  const q = useSettled(text.trim());
  const asks = q.length >= SHORTEST;
  const list = useRef<HTMLDivElement>(null);

  const server = useQuery({
    queryKey: ["search", q, troupeId],
    queryFn: () => unwrap(api.GET("/api/search", { params: { query: { q, troupe_id: troupeId ?? undefined } } })),
    enabled: asks,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
  const here = useQuery({
    queryKey: ["search-here", q, place],
    queryFn: () => searchHere(q, place),
    enabled: asks,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });
  const groups: SearchGroup[] = asks ? [...(server.data?.groups ?? []), ...(here.data ?? [])] : [];
  const searching = text.trim().length >= SHORTEST && (text.trim() !== q || server.isFetching || here.isFetching);
  const count = groups.reduce((n, g) => n + g.hits.length, 0);

  // Up and Down go from the box through the hits, in order.
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const stops = [...(list.current?.querySelectorAll<HTMLElement>("input, a[data-hit]") ?? [])];
    const at = stops.indexOf(document.activeElement as HTMLElement);
    const next = stops[e.key === "ArrowDown" ? Math.min(at + 1, stops.length - 1) : Math.max(at - 1, 0)];
    if (!next) return;
    e.preventDefault();
    next.focus();
  };

  return (
    <div ref={list} onKeyDown={onKeyDown} className="flex flex-col gap-4">
      <Input
        type="search"
        aria-label="Search for"
        placeholder="Characters, boons, help…"
        autoFocus
        // The attribute itself, which the dialog's opening looks for: else it focuses its × first.
        ref={(el) => el?.setAttribute("autofocus", "")}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          // Enter opens the first hit, once the server has answered for what is typed.
          const first = groups[0]?.hits[0];
          if (e.key !== "Enter" || !first || text.trim() !== q || server.isFetching) return;
          e.preventDefault();
          onPick();
          navigate(first.to);
        }}
        className="w-full"
      />
      <p role="status" className="text-sm text-mist">
        {!asks && text.trim().length < SHORTEST
          ? "Characters, players, boons, locations, quests, equipment, news, announcements, settings and help: what you may see of each."
          : searching && count === 0
            ? "Searching…"
            : count === 0
              ? `Nothing found for “${q}”.`
              : count === 1
                ? "1 found."
                : `${count} found.`}
      </p>
      {server.error && <ErrorText error={server.error} />}
      {groups.map((g) => (
        <section key={g.kind} aria-labelledby={`search-${g.kind}`} className="flex flex-col gap-1">
          <h3 id={`search-${g.kind}`} className="text-xs font-semibold tracking-wide text-gold uppercase">
            {g.label}
          </h3>
          <ul className="flex flex-col">
            {g.hits.map((hit) => (
              <li key={`${hit.id}-${hit.to}`}>
                <HitLink hit={hit} troupeId={troupeId} onPick={onPick} />
              </li>
            ))}
          </ul>
          {g.more && <p className="px-3 text-xs text-mist">More than these: add a word to narrow them.</p>}
        </section>
      ))}
      {!asks && <p className="text-xs text-mist pointer-coarse:hidden">Press / or Ctrl K on any page to search.</p>}
    </div>
  );
}

function HitLink({ hit, troupeId, onPick }: { hit: SearchHit; troupeId: string | null; onPick: () => void }) {
  // Another troupe's hit carries a pill with what that troupe goes by (#1153). The current
  // troupe's needn't: its hits come first, and a pill on each would only say the same again.
  const other = hit.troupe_id && hit.troupe_id !== troupeId && hit.troupe ? hit.troupe : null;
  return (
    <Link
      to={hit.to}
      data-hit
      onClick={onPick}
      className="flex min-h-11 flex-col justify-center rounded-md px-3 py-1.5 hover:bg-ash/40 focus:bg-ash/40 focus:outline-none"
    >
      <span className="flex items-start justify-between gap-2">
        <span className="min-w-0 text-parchment wrap-anywhere">{hit.title}</span>
        {other && <TroupePill name={other} abbreviation={hit.troupe_abbreviation ?? other} className="mt-0.5" />}
      </span>
      {hit.detail && <span className="line-clamp-2 text-xs text-mist wrap-anywhere">{hit.detail}</span>}
    </Link>
  );
}

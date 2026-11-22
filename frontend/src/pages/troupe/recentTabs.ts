import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useLocation } from "react-router";
import { api, unwrap } from "../../api/client";
import type { Tab } from "../../components/ui";
import { openTab } from "../../title";

/** How many of the tabs opened last head the phone's tab list, not counting the open one (#1048). */
export const RECENT_SHOWN = 3;

/** How long after the open tab changes the list is saved: tabs opened one after another save once. */
const SAVE_AFTER_MS = 3000;

/** The list, newest first, with `opened` (newest first, each once) put first: each once, the open one and the three before it. */
export function withOpened(list: string[], ...opened: string[]): string[] {
  return [...opened, ...list.filter((t) => !opened.includes(t))].slice(0, RECENT_SHOWN + 1);
}

const same = (a: string[], b: string[]) => a.length === b.length && a.every((t, i) => t === b[i]);

/** A tab's address under the troupe's ("/approvals", "" for the Overview); none for one that leaves it. */
export function tabAddress(tab: Tab, base: string): string | undefined {
  if (tab.to === base) return "";
  return tab.to.startsWith(`${base}/`) ? tab.to.slice(base.length) : undefined;
}

/** The tabs the list names that the person may open now, newest first, without the open one: three at most. */
export function recentTabs(list: string[], tabs: Tab[], base: string, open: Tab | undefined): Tab[] {
  const byAddress = new Map(tabs.flatMap((t) => (tabAddress(t, base) === undefined ? [] : [[tabAddress(t, base)!, t] as const])));
  return list
    .map((a) => byAddress.get(a))
    .filter((t): t is Tab => !!t && t !== open)
    .slice(0, RECENT_SHOWN);
}

const key = (troupeId: string) => ["recent-tabs", troupeId];

/**
 * The tabs of the troupe the person opened last (#1048), kept on their account so they
 * follow them between devices: read as the troupe opens and whenever the page comes
 * back into view, put in order here as each tab opens, and sent back a few seconds
 * after the last change, or at once as they leave the troupe or the page is hidden or
 * closed (kept going then). The tabs opened here and not yet kept go on top of each
 * list read, so none is lost to a read that comes late or out of date (#1208). Nothing
 * is sent while the custodian views as someone, which is read-only.
 */
export function useRecentTabs(troupeId: string, tabs: Tab[], enabled: boolean): Tab[] {
  const base = `/troupes/${troupeId}`;
  const { pathname } = useLocation();
  const client = useQueryClient();
  const saved = useQuery({
    queryKey: key(troupeId),
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/recent-tabs", { params: { path: { troupe_id: troupeId } } })),
    enabled,
    // Asked again on coming back to the troupe or the page, as another device may have opened tabs meanwhile.
    staleTime: Infinity,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
  });
  const open = openTab(tabs, pathname);
  const opened = open && tabAddress(open, base);
  // The tabs opened here that the account may not have yet, newest first.
  const mine = useRef<{ troupeId: string; tabs: string[] }>({ troupeId, tabs: [] });
  const pending = useRef<{ troupeId: string; tabs: string[]; mine: string[] } | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const send = useRef(() => {
    window.clearTimeout(timer.current);
    const due = pending.current;
    pending.current = null;
    if (!due || client.getQueryData(["view-as"])) return;
    void api
      .PUT("/api/troupes/{troupe_id}/recent-tabs", { params: { path: { troupe_id: due.troupeId } }, body: { tabs: due.tabs }, keepalive: true })
      .then(({ response }) => {
        // Kept, and nothing opened since: the account is up to date.
        if (response.ok && mine.current.tabs === due.mine) mine.current = { troupeId: due.troupeId, tabs: [] };
      })
      .catch(() => {});
  });

  const list = saved.data?.tabs;
  useEffect(() => {
    if (mine.current.troupeId !== troupeId) mine.current = { troupeId, tabs: [] };
    // Each tab as it opens, even before the list has come.
    if (opened !== undefined && mine.current.tabs[0] !== opened) mine.current = { troupeId, tabs: withOpened(mine.current.tabs, opened) };
    if (!list) return;
    const next = withOpened(list, ...mine.current.tabs);
    if (same(next, list)) return;
    client.setQueryData(key(troupeId), { tabs: next });
    pending.current = { troupeId, tabs: next, mine: mine.current.tabs };
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(send.current, SAVE_AFTER_MS);
  }, [list, opened, troupeId, client]);
  // Leaving the troupe sends what is waiting; so does the page being hidden or closed.
  useEffect(() => {
    const flush = send.current;
    return flush;
  }, [troupeId]);
  useEffect(() => {
    const flush = send.current;
    const hidden = () => {
      if (document.visibilityState === "hidden") flush();
    };
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", hidden);
    return () => {
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, []);

  return recentTabs(list ?? [], tabs, base, open);
}

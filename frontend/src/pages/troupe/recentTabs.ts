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

/** The list, newest first, with `tab` put first: each once, the open one and the three before it. */
export function withOpened(list: string[], tab: string): string[] {
  return [tab, ...list.filter((t) => t !== tab)].slice(0, RECENT_SHOWN + 1);
}

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
 * follow them between devices: read once, put in order here as each tab opens, and sent
 * back a few seconds after the last change, or at once as they leave the troupe or the
 * page is hidden or closed (kept going then). Nothing is sent while the custodian views
 * as someone, which is read-only.
 */
export function useRecentTabs(troupeId: string, tabs: Tab[], enabled: boolean): Tab[] {
  const base = `/troupes/${troupeId}`;
  const { pathname } = useLocation();
  const client = useQueryClient();
  const saved = useQuery({
    queryKey: key(troupeId),
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/recent-tabs", { params: { path: { troupe_id: troupeId } } })),
    enabled,
    staleTime: Infinity,
  });
  const open = openTab(tabs, pathname);
  const opened = open && tabAddress(open, base);
  const pending = useRef<{ troupeId: string; tabs: string[] } | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const send = useRef(() => {
    window.clearTimeout(timer.current);
    const due = pending.current;
    pending.current = null;
    if (!due || client.getQueryData(["view-as"])) return;
    void api
      .PUT("/api/troupes/{troupe_id}/recent-tabs", { params: { path: { troupe_id: due.troupeId } }, body: { tabs: due.tabs }, keepalive: true })
      .catch(() => {});
  });

  const list = saved.data?.tabs;
  useEffect(() => {
    if (!list || opened === undefined || list[0] === opened) return;
    const next = withOpened(list, opened);
    client.setQueryData(key(troupeId), { tabs: next });
    pending.current = { troupeId, tabs: next };
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

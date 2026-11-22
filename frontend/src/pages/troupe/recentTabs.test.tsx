import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useNavigate } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { recentTabs, tabAddress, useRecentTabs, withOpened } from "./recentTabs";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const base = "/troupes/t1";
const tabs = [
  { to: base, label: "Overview", end: true },
  { to: `${base}/approvals`, label: "Approvals" },
  { to: `${base}/roster`, label: "Roster" },
  { to: `${base}/downtimes`, label: "Downtimes" },
  { to: "/play/troupes/t1/scenes", label: "Scenes ↗" },
];

describe("the tabs opened last (#1048)", () => {
  it("puts the tab just opened first, each once, keeping the open one and three more", () => {
    expect(withOpened([], "/roster")).toEqual(["/roster"]);
    expect(withOpened(["/roster", "", "/approvals"], "/approvals")).toEqual(["/approvals", "/roster", ""]);
    expect(withOpened(["/a", "/b", "/c", "/d"], "/e")).toEqual(["/e", "/a", "/b", "/c"]);
    expect(withOpened(["/a", "/b", "/c"], "/d", "/b", "")).toEqual(["/d", "/b", "", "/a"]);
  });

  it("names a tab by its address under the troupe's, and none for one that leaves it", () => {
    expect(tabAddress(tabs[0]!, base)).toBe("");
    expect(tabAddress(tabs[1]!, base)).toBe("/approvals");
    expect(tabAddress(tabs[4]!, base)).toBeUndefined();
  });

  it("shows three at most, not the open one, nor one the person can't open now", () => {
    const open = tabs[3];
    expect(recentTabs(["/downtimes", "/approvals", "/gone", "", "/roster"], tabs, base, open).map((t) => t.label)).toEqual(["Approvals", "Overview", "Roster"]);
    expect(recentTabs([], tabs, base, open)).toEqual([]);
  });
});

/** The hook on a troupe's page, its list read from the account only when `answer` is called. */
function page() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const answers: ((tabs: string[]) => void)[] = [];
  vi.spyOn(api, "GET").mockImplementation((() =>
    new Promise((resolve) => answers.push((tabs) => resolve({ data: { tabs }, response: new Response(null, { status: 200 }) })))) as never);
  const put = vi.spyOn(api, "PUT").mockResolvedValue({ data: { tabs: [] }, response: new Response(null, { status: 200 }) } as never);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[base]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  const hook = renderHook(() => ({ recent: useRecentTabs("t1", tabs, true).map((t) => t.label), go: useNavigate() }), { wrapper });
  const answer = (tabs: string[]) => act(() => answers.shift()!(tabs));
  const go = (to: string) => act(() => void hook.result.current.go(to));
  return { client, hook, answer, go, put };
}

describe("useRecentTabs (#1208)", () => {
  it("keeps the tabs opened while the list is still being read", async () => {
    const { client, hook, answer, go } = page();
    await waitFor(() => expect(api.GET).toHaveBeenCalledOnce());
    go(`${base}/approvals`);
    go(`${base}/roster`);
    go(`${base}/downtimes`);
    answer(["/elsewhere"]);
    await waitFor(() => expect(hook.result.current.recent).toEqual(["Roster", "Approvals", "Overview"]));
    expect(client.getQueryData(["recent-tabs", "t1"])).toEqual({ tabs: ["/downtimes", "/roster", "/approvals", ""] });
  });

  it("keeps the tabs opened here on top of a list read again, as when the page comes back into view", async () => {
    const { client, hook, answer, go } = page();
    answer([]);
    await waitFor(() => expect(client.getQueryData(["recent-tabs", "t1"])).toEqual({ tabs: [""] }));
    go(`${base}/approvals`);
    go(`${base}/roster`);
    // Asked again before what was opened here has been sent: another device had opened Downtimes.
    void act(() => client.refetchQueries({ queryKey: ["recent-tabs", "t1"] }));
    await waitFor(() => expect(api.GET).toHaveBeenCalledTimes(2));
    answer(["/downtimes"]);
    await waitFor(() => expect(client.getQueryData(["recent-tabs", "t1"])).toEqual({ tabs: ["/roster", "/approvals", "", "/downtimes"] }));
    expect(hook.result.current.recent).toEqual(["Approvals", "Overview", "Downtimes"]);
  });
});

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { RULES_QUERY, useAction, useRulesAction } from "./hooks";

afterEach(cleanup);

/** Two queries on screen, each saying when it is asked and answering only when let. */
function page(first?: string[][]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const asked: string[] = [];
  const answer: Record<string, () => void> = {};
  const ask = (name: string) => () => {
    asked.push(name);
    return new Promise<string>((resolve) => (answer[name] = () => resolve(name)));
  };
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const hook = renderHook(
    () => ({
      sheet: useQuery({ queryKey: ["sheet", "agnes"], queryFn: ask("sheet") }),
      log: useQuery({ queryKey: ["character-log", "agnes"], queryFn: ask("log") }),
      action: useAction(async () => "done", first),
    }),
    { wrapper },
  );
  return { hook, asked, answer };
}

async function loaded({ hook, asked, answer }: ReturnType<typeof page>) {
  await waitFor(() => expect(asked).toEqual(["sheet", "log"]));
  act(() => {
    answer.sheet!();
    answer.log!();
  });
  await waitFor(() => expect(hook.result.current.log.isSuccess).toBe(true));
  asked.length = 0;
}

describe("useAction", () => {
  it("asks everything on screen again at once", async () => {
    const shown = page();
    await loaded(shown);
    act(() => shown.hook.result.current.action.mutate(undefined));
    await waitFor(() => expect(shown.asked.sort()).toEqual(["log", "sheet"]));
  });

  it("asks the queries named first on their own, and the rest once they have answered", async () => {
    const shown = page([["sheet"]]);
    await loaded(shown);
    act(() => shown.hook.result.current.action.mutate(undefined));
    await waitFor(() => expect(shown.asked).toEqual(["sheet"]));
    // Still only the sheet while it is being answered.
    await new Promise((r) => setTimeout(r, 20));
    expect(shown.asked).toEqual(["sheet"]);
    act(() => shown.answer.sheet!());
    await waitFor(() => expect(shown.asked).toEqual(["sheet", "log"]));
    act(() => shown.answer.log!());
    await waitFor(() => expect(shown.hook.result.current.action.isSuccess).toBe(true));
  });
});

/** The sheet, its log and the rules catalogue on screen, each answering at once and
 * saying when it is asked, with a change made as `act` makes it. */
function withRules(act: "plain" | "rules" | "answered") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const asked: string[] = [];
  const ask = (name: string) => async () => {
    asked.push(name);
    return name;
  };
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const change = async () => "done";
  const hook = renderHook(
    () => ({
      sheet: useQuery({ queryKey: ["sheet", "agnes"], queryFn: ask("sheet") }),
      log: useQuery({ queryKey: ["character-log", "agnes"], queryFn: ask("log") }),
      catalogue: useQuery({ queryKey: ["catalogue", "vampire", "lords"], queryFn: ask("catalogue"), meta: RULES_QUERY }),
      plain: useAction(change, [], act === "answered" ? { answered: [["sheet", "agnes"]] } : {}),
      rules: useRulesAction(change),
    }),
    { wrapper },
  );
  return { hook, asked, change: () => (act === "rules" ? hook.result.current.rules : hook.result.current.plain).mutateAsync(undefined) };
}

describe("useAction and the rules", () => {
  it("leaves the rules catalogue be after a change that isn't to them", async () => {
    const shown = withRules("plain");
    await waitFor(() => expect(shown.asked.sort()).toEqual(["catalogue", "log", "sheet"]));
    shown.asked.length = 0;
    await act(shown.change);
    expect(shown.asked.sort()).toEqual(["log", "sheet"]);
  });

  it("asks the rules catalogue again after a change to the rules", async () => {
    const shown = withRules("rules");
    await waitFor(() => expect(shown.asked.sort()).toEqual(["catalogue", "log", "sheet"]));
    shown.asked.length = 0;
    await act(shown.change);
    expect(shown.asked.sort()).toEqual(["catalogue", "log", "sheet"]);
  });

  it("doesn't ask again for what the change's own answer put right", async () => {
    const shown = withRules("answered");
    await waitFor(() => expect(shown.asked.sort()).toEqual(["catalogue", "log", "sheet"]));
    shown.asked.length = 0;
    await act(shown.change);
    expect(shown.asked).toEqual(["log"]);
  });
});

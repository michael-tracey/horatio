import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { useAction } from "./hooks";

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

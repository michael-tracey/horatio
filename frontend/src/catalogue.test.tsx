import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { catalogueKey, useCatalogue } from "./catalogue";
import { useAction, useRulesAction } from "./hooks";
import { keepsQuery } from "./offline/keep";

/** Every catalogue asked of the server: its splat, troupe and category. */
const asked: string[] = [];
vi.mock(import("./api/client"), async (original) => ({
  ...(await original()),
  api: {
    GET: async (_path: string, options: { params: { path: { splat: string }; query: { troupe_id?: string; category?: string } } }) => {
      const { troupe_id, category } = options.params.query;
      asked.push([options.params.path.splat, troupe_id ?? "book", ...(category ? [category] : [])].join(" "));
      return { data: { splat: options.params.path.splat, categories: [], traits: [] }, response: new Response(null, { status: 200 }) };
    },
  } as never,
}));

afterEach(cleanup);
beforeEach(() => {
  asked.length = 0;
});

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

/** A screen showing the catalogue, as the sheet, the wizard or a Customise page does. */
function Screen({ name, troupeId, category }: { name: string; troupeId: string | null | undefined; category?: string }) {
  const catalogue = useCatalogue("vampire", troupeId, { category });
  return <p>{catalogue.data ? `${name} shown` : `${name} loading`}</p>;
}

function show(screens: ReactNode) {
  render(<QueryClientProvider client={client()}>{screens}</QueryClientProvider>);
}

describe("the shared catalogue (#644)", () => {
  it("is asked for once by two screens showing it together", async () => {
    show(
      <>
        <Screen name="Sheet" troupeId="lords" />
        <Screen name="Roster" troupeId="lords" />
      </>,
    );
    await screen.findByText("Sheet shown");
    await screen.findByText("Roster shown");
    expect(asked).toEqual(["vampire lords"]);
  });

  it("is the book's for a character with no troupe and a page that wants the book's, asked for once", async () => {
    show(
      <>
        <Screen name="Sheet" troupeId={undefined} />
        <Screen name="Costs" troupeId={null} />
      </>,
    );
    await screen.findByText("Sheet shown");
    await screen.findByText("Costs shown");
    expect(asked).toEqual(["vampire book"]);
    expect(catalogueKey("vampire", undefined)).toEqual(catalogueKey("vampire", null));
    expect(catalogueKey("vampire", "")).toEqual(["catalogue", "vampire", null]);
  });

  it("keeps a troupe's apart from the book's, and one category's apart from the whole", async () => {
    show(
      <>
        <Screen name="Rules" troupeId="lords" />
        <Screen name="Free changes" troupeId={null} />
        <Screen name="Sects" troupeId={null} category="sect" />
      </>,
    );
    await screen.findByText("Sects shown");
    await screen.findByText("Rules shown");
    await screen.findByText("Free changes shown");
    expect(asked.sort()).toEqual(["vampire book", "vampire book sect", "vampire lords"]);
    // Under the whole one's key, so what reloads that reloads it.
    expect(catalogueKey("vampire", null, "sect").slice(0, 3)).toEqual(catalogueKey("vampire", null));
  });

  it("is asked for again by a change to the rules, and not by any other change", async () => {
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client()}>{children}</QueryClientProvider>;
    const change = async () => "done";
    const hook = renderHook(() => ({ catalogue: useCatalogue("vampire", "lords"), sheet: useAction(change), rules: useRulesAction(change) }), { wrapper });
    await waitFor(() => expect(hook.result.current.catalogue.isSuccess).toBe(true));
    expect(asked).toEqual(["vampire lords"]);
    await act(() => hook.result.current.sheet.mutateAsync(undefined));
    expect(asked).toEqual(["vampire lords"]);
    await act(() => hook.result.current.rules.mutateAsync(undefined));
    await waitFor(() => expect(asked).toEqual(["vampire lords", "vampire lords"]));
  });

  it("is kept on the device under the key the screens ask by", () => {
    const mine = { characters: new Set<string>(), troupes: new Set<string>() };
    expect(keepsQuery([...catalogueKey("vampire", "lords")], mine)).toBe(true);
    expect(keepsQuery([...catalogueKey("vampire", undefined)], mine)).toBe(true);
  });
});

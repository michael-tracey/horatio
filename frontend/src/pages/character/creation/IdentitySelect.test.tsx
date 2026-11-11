import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CatalogueOut, CategoryOut, CharacterOut, SheetOut } from "../../../api/types";
import { RULES_QUERY } from "../../../hooks";
import { IdentitySelect } from "./IdentitySelect";

/** The answer to the PUT on its way, let go by the test: kept, or refused. */
let answer: { keep: () => void; refuse: (why: string) => void } | null = null;
const asked: string[] = [];

const sheetWith = (clan: string) => ({ traits: [{ category: "clan", name: clan }] }) as unknown as SheetOut;

vi.mock(import("../../../api/client"), async (original) => ({
  ...(await original()),
  api: {
    PUT: (_path: string, options: { body: { name: string } }) =>
      new Promise((resolve) => {
        answer = {
          keep: () => resolve({ data: { cost: 0, sheet: sheetWith(options.body.name) }, response: new Response(null, { status: 200 }) }),
          refuse: (why) => resolve({ error: { detail: why }, response: new Response(null, { status: 409 }) }),
        };
      }),
  } as never,
}));

afterEach(() => {
  cleanup();
  answer = null;
  asked.length = 0;
});

const character = { id: "agnes", splat: "vampire" } as CharacterOut;
const clan = { key: "clan", name: "Clan" } as CategoryOut;
const catalogue = {
  categories: [clan],
  traits: ["Brujah", "Toreador", "Ventrue"].map((name) => ({ category: "clan", name })),
} as unknown as CatalogueOut;

/** The select as the wizard shows it: with the sheet, and the catalogue, read through queries. */
function Page() {
  const sheet = useQuery({ queryKey: ["sheet", "agnes"], queryFn: async () => (asked.push("sheet"), sheetWith("Brujah")) });
  useQuery({ queryKey: ["catalogue", "vampire", "lords"], meta: RULES_QUERY, queryFn: async () => (asked.push("catalogue"), catalogue) });
  return sheet.data ? <IdentitySelect character={character} choice={clan} sheet={sheet.data} catalogue={catalogue} /> : null;
}

async function shown() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Page />
    </QueryClientProvider>,
  );
  const select = (await screen.findByLabelText("Clan")) as HTMLSelectElement;
  await waitFor(() => expect(asked).toContain("catalogue"));
  asked.length = 0;
  return select;
}

describe("a clan picked in creation", () => {
  it("shows at once, saying it is saving, and stays once saved, without the sheet or the catalogue asked again", async () => {
    const select = await shown();
    expect(select.value).toBe("Brujah");

    fireEvent.change(select, { target: { value: "Toreador" } });

    expect(select.value).toBe("Toreador");
    await screen.findByText("Saving…");
    await waitFor(() => expect(answer).not.toBeNull());
    await act(async () => answer!.keep());
    await waitFor(() => expect(screen.queryByText("Saving…")).toBeNull());
    expect(select.value).toBe("Toreador");
    expect(asked).toEqual([]);
  });

  it("goes back to what is saved, saying why, when the server refuses it", async () => {
    const select = await shown();

    fireEvent.change(select, { target: { value: "Ventrue" } });
    expect(select.value).toBe("Ventrue");
    await waitFor(() => expect(answer).not.toBeNull());
    await act(async () => answer!.refuse("Ventrue is not played in this troupe."));

    await waitFor(() => expect(select.value).toBe("Brujah"));
    expect(screen.getByText("Ventrue is not played in this troupe.")).not.toBeNull();
    expect(screen.queryByText("Saving…")).toBeNull();
  });
});

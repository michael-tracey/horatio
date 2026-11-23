import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { PublicTroupeOut, PublicTroupePageOut } from "../api/types";
import { DirectoryPage } from "./DirectoryPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function troupe(over: Partial<PublicTroupeOut>): PublicTroupeOut {
  return {
    id: "lords",
    name: "Lords of the Night",
    abbreviation: "LotN",
    portrait: null,
    description: "A Camarilla court in **Leeds**.",
    place: "Leeds",
    schedule: "Second Saturday of the month, 7 pm to midnight",
    new_players: "welcoming",
    min_age: 18,
    content_notes: "Violence and body horror.",
    next_game: null,
    time_zone: null,
    ...over,
  };
}

type Query = Record<string, unknown>;

/** Answers the directory's search with `answer`; gives each query it was asked. */
function answering(answer: (query: Query) => PublicTroupePageOut): () => Query[] {
  const asked: Query[] = [];
  vi.spyOn(api, "GET").mockImplementation((async (path: string, init?: { params?: { query?: Query } }) => {
    if (path !== "/api/public/troupes") return { error: { detail: "No" }, response: new Response(null, { status: 404 }) };
    const query = init?.params?.query ?? {};
    asked.push(query);
    return { data: answer(query), response: new Response(null, { status: 200 }) };
  }) as never);
  return () => asked;
}

function Address() {
  const { search } = useLocation();
  return <output aria-label="Address">{search}</output>;
}

function show(at = "/find-a-troupe") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route
            path="/find-a-troupe"
            element={
              <>
                <DirectoryPage />
                <Address />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const page = (troupes: PublicTroupeOut[], over: Partial<PublicTroupePageOut> = {}): PublicTroupePageOut => ({ troupes, page: 1, pages: 1, total: troupes.length, ...over });
const address = () => screen.getByRole("status", { name: "Address" }).textContent;

describe("the troupe directory, /find-a-troupe (#1192)", () => {
  it("lists public troupes in compact rows, each with when it plays, its next game, new players, age and content notes", async () => {
    answering(() => page([troupe({ next_game: "2026-11-28T12:00:00Z" }), troupe({ id: "york", name: "Court of York", abbreviation: "Court of York", schedule: "", new_players: "closed", min_age: null, content_notes: "" })]));
    show();

    expect(await screen.findByRole("heading", { level: 1, name: "Find a troupe" })).toBeTruthy();
    expect(document.title).toBe("Find a troupe · Horatio");
    const list = await screen.findByRole("list", { name: "Troupes found" });
    const [lords, york] = within(list).getAllByRole("link");
    expect(lords!.getAttribute("href")).toBe("/t/lords");
    // Its pill for the eye, its name read once.
    expect(within(lords!).getByText("LotN").closest("[aria-hidden='true']")).toBeTruthy();
    expect(lords!.textContent).toContain("Second Saturday of the month");
    expect(lords!.textContent).toMatch(/Next game: Sat 28 Nov/);
    expect(lords!.textContent).toContain("Welcoming new players");
    expect(lords!.textContent).toContain("18+");
    expect(lords!.textContent).toContain("Content notes: Violence and body horror.");
    expect(lords!.textContent).not.toContain("**");
    // What a troupe doesn't say, its row leaves out.
    expect(york!.textContent).not.toContain("Next game");
    expect(york!.textContent).not.toContain("Welcoming");
    expect(york!.textContent).not.toContain("Content notes");
    expect(york!.textContent).not.toContain("+");
  });

  it("shows a troupe's next game on its own clock, where it has a time zone, as the Day filter takes it (#1211)", async () => {
    // 9:30 pm on Friday 27 November in New York is already Saturday in UTC, and in London.
    answering(() => page([troupe({ next_game: "2026-11-28T02:30:00Z", time_zone: "America/New_York" })]));
    show();
    const list = await screen.findByRole("list", { name: "Troupes found" });
    const [lords] = within(list).getAllByRole("link");
    expect(lords!.textContent).toMatch(/Next game: Fri 27 Nov( 2026)?, 9:30 pm EST/);
  });

  it("searches from the address, and writes each search back to it", async () => {
    const asked = answering(() => page([troupe({})]));
    show("/find-a-troupe?place=Leeds&day=friday");

    const form = await screen.findByRole("search", { name: "Search troupes" });
    expect((within(form).getByLabelText("Place") as HTMLInputElement).value).toBe("Leeds");
    expect((within(form).getByLabelText("Day") as HTMLSelectElement).value).toBe("friday");
    await waitFor(() => expect(asked()[0]).toEqual({ page: 1, place: "Leeds", day: "friday" }));

    // A day, how often or new players searches at once; typed words wait for Search.
    fireEvent.change(within(form).getByLabelText("How often"), { target: { value: "weekly" } });
    await waitFor(() => expect(asked().at(-1)).toEqual({ page: 1, place: "Leeds", day: "friday", frequency: "weekly" }));
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "lords" } });
    fireEvent.change(within(form).getByLabelText("Your age"), { target: { value: "17" } });
    expect(asked().at(-1)).not.toHaveProperty("name");
    fireEvent.click(within(form).getByLabelText("Only troupes welcoming new players"));
    await waitFor(() =>
      expect(asked().at(-1)).toEqual({ page: 1, name: "lords", place: "Leeds", day: "friday", frequency: "weekly", new_players: true, age: 17 }),
    );
    expect(address()).toBe("?place=Leeds&day=friday&often=weekly&name=lords&new=1&age=17");

    // Clear starts again.
    fireEvent.click(within(form).getByRole("button", { name: "Clear the search" }));
    await waitFor(() => expect(asked().at(-1)).toEqual({ page: 1 }));
    expect(address()).toBe("");
    expect((within(form).getByLabelText("Name") as HTMLInputElement).value).toBe("");
  });

  it("types a name or place, then Search", async () => {
    const asked = answering(() => page([troupe({})]));
    show();
    const form = await screen.findByRole("search", { name: "Search troupes" });
    fireEvent.change(within(form).getByLabelText("Place"), { target: { value: "Yorkshire" } });
    fireEvent.click(within(form).getByRole("button", { name: "Search" }));
    await waitFor(() => expect(asked().at(-1)).toEqual({ page: 1, place: "Yorkshire" }));
    expect(address()).toBe("?place=Yorkshire");
  });

  it("goes through the results a page at a time, keeping the search", async () => {
    const many = Array.from({ length: 12 }, (_, n) => troupe({ id: `t${n}`, name: `Court ${n}`, abbreviation: `C${n}` }));
    const asked = answering((query) =>
      query.page === 2 ? page([troupe({ id: "last", name: "Last court", abbreviation: "Last court" })], { page: 2, pages: 2, total: 13 }) : page(many, { pages: 2, total: 13 }),
    );
    show("/find-a-troupe?new=1");

    const pages = await screen.findByRole("navigation", { name: "Pages of troupes" });
    expect(within(pages).getByText("1 to 12 of 13")).toBeTruthy();
    fireEvent.click(within(pages).getByRole("button", { name: "Next" }));
    expect((await screen.findByRole("link", { name: /Last court/ })).getAttribute("href")).toBe("/t/last");
    expect(asked().at(-1)).toEqual({ page: 2, new_players: true });
    expect(address()).toBe("?new=1&page=2");
  });

  it("says so when nothing matches, or no troupe is public yet", async () => {
    answering(() => page([]));
    show("/find-a-troupe?place=Atlantis");
    expect(await screen.findByText("No troupe matches that search. Try fewer filters.")).toBeTruthy();
    cleanup();
    show();
    expect(await screen.findByText("No troupe shows its profile to everyone yet.")).toBeTruthy();
  });
});

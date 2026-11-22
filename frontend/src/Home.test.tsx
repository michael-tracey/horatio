import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api/client";
import type { BlogPublicPageOut, BlogPublicSummaryOut, Me, PublicTroupeOut, PublicTroupePageOut } from "./api/types";
import { Home } from "./Home";
import { articlesShown } from "./pages/LandingPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const agnes = { id: "u1", handle: "agnes", display_name: "Agnes" } as Me;

function article(over: Partial<BlogPublicSummaryOut>): BlogPublicSummaryOut {
  return {
    slug: "running-your-first-elysium",
    title: "Running your first Elysium",
    summary: "What I wish I'd known.",
    picture: null,
    picture_sizes: [],
    author: { name: "Mara Quinn", handle: null },
    troupe: null,
    tags: [],
    featured: false,
    published_at: "2026-11-01T12:00:00Z",
    revised_at: null,
    ...over,
  };
}

const ELYSIUM = article({});
const BOONS = article({
  slug: "boons-101",
  title: "Boons 101",
  featured: true,
  troupe: { name: "Lords of the Night", card: { id: "lords", name: "Lords of the Night", abbreviation: "LotN", portrait: null, description: "" } },
});
// A private troupe's article: its name only, no link (#1160).
const ELYSIUM_PRIVATE = { ...ELYSIUM, troupe: { name: "Hidden Court", card: null } };

function troupe(over: Partial<PublicTroupeOut>): PublicTroupeOut {
  return {
    id: "lords",
    name: "Lords of the Night",
    abbreviation: "LotN",
    portrait: null,
    description: "A Camarilla court in **Leeds**, where the old Prince's grip is slipping.\n\nGames monthly.",
    place: "Leeds",
    schedule: "Second Saturday of the month",
    new_players: "welcoming",
    min_age: 18,
    content_notes: "Violence.",
    next_game: null,
    ...over,
  };
}

const LORDS = troupe({});

type Answer = { status: number; data?: unknown };

type Asked = [string, { params?: { query?: Record<string, unknown> } } | undefined];

/**
 * Answers each GET by its path: `me` for /api/auth/me, the rest from `answers`; anything
 * else is a 404. Gives what the page asked for, each path with its query.
 */
function answering(me: Answer, answers: Record<string, (query: Record<string, unknown>) => unknown> = {}): () => Asked[] {
  const asked: Asked[] = [];
  vi.spyOn(api, "GET").mockImplementation((async (path: string, init?: { params?: { query?: Record<string, unknown> } }) => {
    asked.push([path, init]);
    if (path === "/api/auth/me")
      return me.status === 200 ? { data: me.data, response: new Response(null, { status: 200 }) } : { error: { detail: "No" }, response: new Response(null, { status: me.status }) };
    const answer = answers[path];
    if (!answer) return { error: { detail: "No such thing." }, response: new Response(null, { status: 404 }) };
    return { data: answer(init?.params?.query ?? {}), response: new Response(null, { status: 200 }) };
  }) as never);
  return () => asked;
}

function blog(over: Partial<BlogPublicPageOut> = {}): BlogPublicPageOut {
  return { articles: [ELYSIUM_PRIVATE, BOONS], page: 1, pages: 1, total: 2, featured: [BOONS], ...over };
}

function troupes(over: Partial<PublicTroupePageOut> = {}): PublicTroupePageOut {
  return { troupes: [LORDS], page: 1, pages: 1, total: 1, ...over };
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/characters" element={<p>Your characters</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the front door, / (#1164)", () => {
  it("takes someone signed in on to their characters, as before", async () => {
    const asked = answering({ status: 200, data: agnes });
    show();
    expect(await screen.findByText("Your characters")).toBeTruthy();
    // Nothing of the landing page is asked for.
    expect(asked().filter(([path]) => /blog|troupes/.test(path))).toEqual([]);
  });

  it("shows someone signed out what Horatio is, a few articles, public troupes and the ways in", async () => {
    answering({ status: 401 }, { "/api/blog/public/articles": () => blog(), "/api/public/troupes": () => troupes() });
    show();

    expect(await screen.findByRole("heading", { level: 1, name: "Welcome to Horatio" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "What Horatio is" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Create an account" }).getAttribute("href")).toBe("/sign-up");
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/sign-in");
    expect(screen.getByRole("link", { name: "About Horatio" }).getAttribute("href")).toBe("/about");

    // The featured article first, then the newest.
    const articles = await screen.findByRole("list", { name: "Articles" });
    expect(within(articles).getAllByRole("listitem").map((li) => li.getAttribute("aria-label"))).toEqual(["Boons 101", "Running your first Elysium"]);
    expect(within(articles).getByRole("link", { name: "Boons 101" }).getAttribute("href")).toBe("/blog/boons-101");
    expect(screen.getByRole("link", { name: "Read the blog" }).getAttribute("href")).toBe("/blog");
    // Each names its troupe: linked to its profile while public and running, else its name only.
    const boons = within(articles).getByRole("listitem", { name: "Boons 101" });
    expect(within(boons).getByRole("link", { name: "Lords of the Night" }).getAttribute("href")).toBe("/t/lords");
    const elysium = within(articles).getByRole("listitem", { name: "Running your first Elysium" });
    expect(elysium.textContent).toContain("of Hidden Court");
    expect(within(elysium).queryByRole("link", { name: "Hidden Court" })).toBeNull();

    // A public troupe, to its public profile: its name read once, its pill for the eye.
    const list = await screen.findByRole("list", { name: "Troupes" });
    const row = within(list).getByRole("link");
    expect(row.getAttribute("href")).toBe("/t/lords");
    expect(row.textContent).toContain("LotN");
    expect(within(row).getByText("LotN").closest("[aria-hidden='true']")).toBeTruthy();
    expect(row.textContent).toContain("A Camarilla court in Leeds");
    expect(row.textContent).not.toContain("**");
    // Compact: the directory's details are for the directory.
    expect(row.textContent).not.toContain("Second Saturday");
    expect(screen.getByRole("link", { name: "Search the troupe directory" }).getAttribute("href")).toBe("/find-a-troupe");
    expect(document.title).toBe("Welcome · Horatio");
  });

  it("goes through the troupes a page at a time", async () => {
    const many = Array.from({ length: 12 }, (_, n) => troupe({ id: `t${n}`, name: `Court ${n}`, abbreviation: `C${n}` }));
    const asked = answering(
      { status: 401 },
      {
        "/api/blog/public/articles": () => blog(),
        "/api/public/troupes": (query) => (query.page === 2 ? troupes({ troupes: [troupe({ id: "last", name: "Last court", abbreviation: "Last court" })], page: 2, pages: 2, total: 13 }) : troupes({ troupes: many, pages: 2, total: 13 })),
      },
    );
    show();

    const pages = await screen.findByRole("navigation", { name: "Pages of troupes" });
    expect(within(pages).getByText("1 to 12 of 13")).toBeTruthy();
    fireEvent.click(within(pages).getByRole("button", { name: "Next" }));
    const last = await screen.findByRole("link", { name: /Last court/ });
    expect(last.getAttribute("href")).toBe("/t/last");
    // A troupe that goes by its own name has no pill.
    expect(within(last).getAllByText("Last court")).toHaveLength(1);
    await waitFor(() => expect(asked().some(([path, init]) => path === "/api/public/troupes" && init?.params?.query?.page === 2)).toBe(true));
  });

  it("says so when there are no articles or public troupes yet", async () => {
    answering({ status: 401 }, { "/api/blog/public/articles": () => blog({ articles: [], featured: [], total: 0 }), "/api/public/troupes": () => troupes({ troupes: [], total: 0 }) });
    show();
    expect(await screen.findByText("No articles yet.")).toBeTruthy();
    expect(await screen.findByText("No troupe shows its profile to everyone yet.")).toBeTruthy();
  });

  it("says when the session check fails, rather than the landing page", async () => {
    answering({ status: 500 });
    show();
    expect(await screen.findByRole("button", { name: "Try again" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Welcome to Horatio" })).toBeNull();
  });
});

describe("the landing page's articles", () => {
  it("are at most two featured, then the newest, each once, four in all", () => {
    const a = (slug: string, featured = false) => article({ slug, title: slug, featured });
    const featured = [a("f1", true), a("f2", true), a("f3", true)];
    const newest = [a("f1", true), a("n1"), a("f3", true), a("n2"), a("n3")];
    expect(articlesShown(featured, newest).map((x) => x.slug)).toEqual(["f1", "f2", "n1", "f3"]);
    expect(articlesShown([], [a("n1")]).map((x) => x.slug)).toEqual(["n1"]);
  });
});

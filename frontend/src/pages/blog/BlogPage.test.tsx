import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { BlogPublicArticleOut, BlogPublicPageOut, BlogPublicSummaryOut, BlogPublicTagCountOut } from "../../api/types";
import { ArticlePage } from "./ArticlePage";
import { AuthorPage } from "./AuthorPage";
import { BlogPage, feedPath, pageFrom } from "./BlogPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const TAGS: BlogPublicTagCountOut[] = [
  { id: "t1", name: "How to play", slug: "how-to-play", articles: 0 },
  { id: "t2", name: "Storytelling", slug: "storytelling", articles: 2 },
  { id: "t3", name: "Safety and consent", slug: "safety-and-consent", articles: 1 },
];

function summary(over: Partial<BlogPublicSummaryOut>): BlogPublicSummaryOut {
  return {
    slug: "running-your-first-elysium",
    title: "Running your first Elysium",
    summary: "What I wish I'd known.",
    picture: null,
    author: { name: "Mara Quinn", handle: null },
    troupe: { name: "Lords of the Night", card: null },
    tags: [{ id: "t2", name: "Storytelling", slug: "storytelling" }],
    featured: false,
    published_at: "2026-11-01T12:00:00Z",
    revised_at: null,
    ...over,
  };
}

const ELYSIUM = summary({});
const BOONS = summary({ slug: "boons-101", title: "Boons 101", featured: true, tags: [] });

function page(over: Partial<BlogPublicPageOut> = {}): BlogPublicPageOut {
  return { articles: [ELYSIUM, BOONS], page: 1, pages: 1, total: 2, featured: [BOONS], ...over };
}

const ARTICLE: BlogPublicArticleOut = {
  ...ELYSIUM,
  body: "Start **small**.\n\n<script>alert(1)</script>",
  tags: [
    { id: "t2", name: "Storytelling", slug: "storytelling" },
    { id: "t3", name: "Safety and consent", slug: "safety-and-consent" },
  ],
  picture: "/api/blog/articles/a1/pictures/p1",
  author_card: null,
  edit: null,
};

/** Answers the blog's GETs from `answers`, by path; a missing one is a 404. */
function answering(answers: Record<string, unknown>) {
  return vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
    if (!(path in answers)) return { error: { detail: "No such thing." }, response: new Response(null, { status: 404 }) };
    return { data: answers[path], response: new Response(null, { status: 200 }) };
  }) as never);
}

function show(at: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/blog" element={<BlogPage />} />
          <Route path="/blog/tags/:tag" element={<BlogPage />} />
          <Route path="/blog/:slug" element={<ArticlePage />} />
          <Route path="/blog/authors/:handle" element={<AuthorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the blog (#1158)", () => {
  it("lists articles newest first, with the featured ones on top and the tags that have articles", async () => {
    answering({ "/api/blog/public/articles": page(), "/api/blog/public/tags": TAGS });
    show("/blog");

    const list = await screen.findByRole("list", { name: "Articles" });
    expect(within(list).getAllByRole("listitem").map((li) => li.getAttribute("aria-label"))).toEqual(["Running your first Elysium", "Boons 101"]);
    expect(within(within(list).getByRole("listitem", { name: "Running your first Elysium" })).getByRole("link", { name: "Running your first Elysium" }).getAttribute("href")).toBe("/blog/running-your-first-elysium");
    const featured = screen.getByRole("heading", { name: "Featured" }).closest("section")!;
    expect(within(featured).getByRole("link", { name: "Boons 101" })).toBeTruthy();
    const tags = await screen.findByRole("navigation", { name: "Tags" });
    await waitFor(() => expect(within(tags).getAllByRole("link").map((a) => a.textContent)).toEqual(["All", "Storytelling", "Safety and consent"]));
    expect(within(tags).getByRole("link", { name: "All" }).getAttribute("aria-current")).toBe("page");
    expect(within(tags).getByRole("link", { name: "Storytelling" }).getAttribute("href")).toBe("/blog/tags/storytelling");
    expect(document.title).toBe("Blog · Horatio");
  });

  it("shows a tag's articles, marked in the tags, without the featured row", async () => {
    const get = answering({
      "/api/blog/public/tags/{slug}": { ...page({ articles: [ELYSIUM], total: 1 }), tag: { id: "t2", name: "Storytelling", slug: "storytelling" } },
      "/api/blog/public/tags": TAGS,
    });
    show("/blog/tags/storytelling");

    expect(await screen.findByRole("heading", { level: 1, name: "Storytelling" })).toBeTruthy();
    expect(get).toHaveBeenCalledWith("/api/blog/public/tags/{slug}", { params: { path: { slug: "storytelling" }, query: { page: 1 } } });
    expect(screen.getByRole("list", { name: "Articles" }).children).toHaveLength(1);
    expect(screen.queryByRole("heading", { name: "Featured" })).toBeNull();
    const tags = await screen.findByRole("navigation", { name: "Tags" });
    await waitFor(() => expect(within(tags).getByRole("link", { name: "Storytelling" }).getAttribute("aria-current")).toBe("page"));
    await waitFor(() => expect(document.title).toBe("Storytelling · Blog · Horatio"));
  });

  it("moves on from a merged tag's old address to the tag it was merged into (#1184)", async () => {
    // The API answers the old address with the other tag's page.
    const get = answering({
      "/api/blog/public/tags/{slug}": { ...page({ articles: [ELYSIUM], total: 1 }), tag: { id: "t2", name: "Storytelling", slug: "storytelling" } },
      "/api/blog/public/tags": TAGS,
    });
    show("/blog/tags/stories?page=2");

    expect(await screen.findByRole("heading", { level: 1, name: "Storytelling" })).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("link", { name: "Follow this tag by feed" }).getAttribute("href")).toBe("/blog/tags/storytelling/feed.xml"));
    expect(get).toHaveBeenCalledWith("/api/blog/public/tags/{slug}", { params: { path: { slug: "stories" }, query: { page: 2 } } });
    expect(get).toHaveBeenCalledWith("/api/blog/public/tags/{slug}", { params: { path: { slug: "storytelling" }, query: { page: 2 } } });
    const tags = await screen.findByRole("navigation", { name: "Tags" });
    await waitFor(() => expect(within(tags).getByRole("link", { name: "Storytelling" }).getAttribute("aria-current")).toBe("page"));
  });

  it("says when a tag is unknown", async () => {
    answering({ "/api/blog/public/tags": TAGS });
    show("/blog/tags/nope");
    expect(await screen.findByRole("heading", { level: 1, name: "No such tag" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "See every article" }).getAttribute("href")).toBe("/blog");
  });

  it("pages through, asking for the next page", async () => {
    const get = answering({ "/api/blog/public/articles": page({ pages: 2, total: 14 }), "/api/blog/public/tags": TAGS });
    show("/blog");

    fireEvent.click(await screen.findByRole("button", { name: "Next" }));

    await waitFor(() => expect(get).toHaveBeenCalledWith("/api/blog/public/articles", { params: { query: { page: 2 } } }));
  });

  it("says when there are no articles yet", async () => {
    answering({ "/api/blog/public/articles": page({ articles: [], featured: [], total: 0 }), "/api/blog/public/tags": TAGS.map((t) => ({ ...t, articles: 0 })) });
    show("/blog");
    expect(await screen.findByText("No articles yet.")).toBeTruthy();
  });

  it("links to the blog's feed, and on a tag's page to the tag's (#1162)", async () => {
    answering({
      "/api/blog/public/articles": page(),
      "/api/blog/public/tags/{slug}": { ...page({ articles: [ELYSIUM], total: 1 }), tag: { id: "t2", name: "Storytelling", slug: "storytelling" } },
      "/api/blog/public/tags": TAGS,
    });
    show("/blog");
    const feed = await screen.findByRole("link", { name: "Follow by feed" });
    expect(feed.getAttribute("href")).toBe("/blog/feed.xml");
    expect(feed.getAttribute("type")).toBe("application/atom+xml");
    cleanup();

    show("/blog/tags/storytelling");
    expect((await screen.findByRole("link", { name: "Follow this tag by feed" })).getAttribute("href")).toBe("/blog/tags/storytelling/feed.xml");
    expect(feedPath("a b")).toBe("/blog/tags/a%20b/feed.xml");
  });

  it("reads the page asked for from the address", () => {
    expect(pageFrom(new URLSearchParams("page=3"))).toBe(3);
    expect(pageFrom(new URLSearchParams(""))).toBe(1);
    expect(pageFrom(new URLSearchParams("page=-2"))).toBe(1);
    expect(pageFrom(new URLSearchParams("page=two"))).toBe(1);
  });
});

describe("an article's page (#1158)", () => {
  it("shows its title, summary, picture, author, date, linked tags and words, rendering no HTML", async () => {
    answering({ "/api/blog/public/articles/{slug}": ARTICLE });
    show("/blog/running-your-first-elysium");

    expect(await screen.findByRole("heading", { level: 1, name: "Running your first Elysium" })).toBeTruthy();
    expect(screen.getByText("What I wish I'd known.")).toBeTruthy();
    expect(screen.getByText("Mara Quinn").closest("p")?.textContent).toMatch(/^By Mara Quinn of Lords of the Night · /);
    expect(document.querySelector("article img")?.getAttribute("src")).toBe("/api/blog/articles/a1/pictures/p1/1200.webp");
    const tags = screen.getByRole("list", { name: "Tags" });
    expect(within(tags).getByRole("link", { name: "Safety and consent" }).getAttribute("href")).toBe("/blog/tags/safety-and-consent");
    expect(screen.getByText("small").tagName).toBe("STRONG");
    expect(document.querySelector("article script")).toBeNull();
    // A private troupe is its name only, with no card.
    expect(screen.getByText("Lords of the Night")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Lords of the Night" })).toBeNull();
    expect(screen.queryByRole("region", { name: "About Lords of the Night" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Change it" })).toBeNull();
    expect(screen.getByRole("link", { name: "← Blog" }).getAttribute("href")).toBe("/blog");
    await waitFor(() => expect(document.title).toBe("Running your first Elysium · Blog · Horatio"));
  });

  it("links a public troupe, puts the author's and troupe's cards under it, and offers its author a way to change it", async () => {
    const card = { handle: "mara", display_name: "Mara Quinn", bio: "I run *Lords*.", links: [], picture: null };
    answering({
      "/api/blog/public/articles/{slug}": { ...ARTICLE, troupe: { name: "Lords of the Night", card: { id: "lords", name: "Lords of the Night", abbreviation: "LotN", portrait: "/api/troupes/lords/portraits/p9", description: "A Camarilla game in Leeds." } }, author: { name: "Mara Quinn", handle: "mara" }, author_card: card, edit: "/blog/write/a1" },
    });
    show("/blog/running-your-first-elysium");

    const byline = (await screen.findByText(/^By /)).closest("p")!;
    expect(within(byline).getByRole("link", { name: "Lords of the Night" }).getAttribute("href")).toBe("/t/lords");
    // The troupe's card (#1160): its portrait, name linked to its profile, pill and description.
    const troupe = screen.getByRole("region", { name: "About Lords of the Night" });
    expect(within(troupe).getByRole("link", { name: "Lords of the Night" }).getAttribute("href")).toBe("/t/lords");
    expect(within(troupe).getByText("LotN").closest("[title]")?.getAttribute("title")).toBe("Lords of the Night");
    expect(within(troupe).getByText("A Camarilla game in Leeds.")).toBeTruthy();
    expect(troupe.querySelector("img")?.getAttribute("src")).toBe("/api/troupes/lords/portraits/p9/128.webp");
    const about = screen.getByRole("region", { name: "About Mara Quinn" });
    expect(within(about).getByRole("link", { name: "Mara Quinn" }).getAttribute("href")).toBe("/blog/authors/mara");
    expect(within(about).getByText("Lords").tagName).toBe("EM");
    expect(screen.getByRole("link", { name: "Change it" }).getAttribute("href")).toBe("/blog/write/a1");
  });

  it("says there is no such article for anything not published", async () => {
    answering({});
    show("/blog/a-draft");
    expect(await screen.findByRole("heading", { level: 1, name: "No such article" })).toBeTruthy();
    expect(screen.getByText(/may have been taken down/)).toBeTruthy();
  });
});

describe("an author's page (#1158)", () => {
  const AUTHOR = { handle: "mara", display_name: "Mara Quinn", bio: "", links: [], picture: null, yours: false, can_clear: false };

  it("lists the articles they have published under their card", async () => {
    const get = answering({
      "/api/blog/authors/{handle}": AUTHOR,
      "/api/blog/public/authors/{handle}/articles": { ...page({ articles: [ELYSIUM], total: 1 }), author: { name: "Mara Quinn", handle: "mara" } },
    });
    show("/blog/authors/mara");

    expect(await screen.findByRole("heading", { level: 1, name: "Mara Quinn" })).toBeTruthy();
    const list = await screen.findByRole("list", { name: "Articles" });
    expect(within(list).getByRole("link", { name: "Running your first Elysium" }).getAttribute("href")).toBe("/blog/running-your-first-elysium");
    expect(get).toHaveBeenCalledWith("/api/blog/public/authors/{handle}/articles", { params: { path: { handle: "mara" }, query: { page: 1 } } });
    await waitFor(() => expect(document.title).toBe("Mara Quinn · Blog · Horatio"));
  });

  it("says when they have none published yet", async () => {
    answering({
      "/api/blog/authors/{handle}": { ...AUTHOR, yours: true },
      "/api/blog/public/authors/{handle}/articles": { ...page({ articles: [], featured: [], total: 0 }), author: { name: "Mara Quinn", handle: "mara" } },
    });
    show("/blog/authors/mara");
    expect(await screen.findByText("Mara Quinn has no articles published yet.")).toBeTruthy();
  });
});

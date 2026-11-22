import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { BlogArticleOut, BlogQueueOut, BlogTagOut } from "../../api/types";
import { statusText } from "../blog/blog";
import { BlogTab } from "./BlogTab";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const TAGS: BlogTagOut[] = [
  { id: "t1", name: "How to play", slug: "how-to-play" },
  { id: "t2", name: "Storytelling", slug: "storytelling" },
];
const TROUPE = { id: "lords", name: "Lords of the Night", archived: false, public: false };

function article(over: Partial<BlogArticleOut>): BlogArticleOut {
  return {
    id: "a1",
    status: "submitted",
    slug: "running-your-first-elysium",
    slug_fixed: false,
    title: "Running your first Elysium",
    summary: "What I wish I'd known.",
    body: "Start **small**.",
    picture: null,
    author_id: "u1",
    author_name: "Mara Quinn",
    troupe: TROUPE,
    featured: false,
    note: "",
    tags: [],
    created_at: "2026-11-20T12:00:00Z",
    updated_at: "2026-11-20T12:00:00Z",
    submitted_at: "2026-11-20T12:00:00Z",
    published_at: null,
    revised_at: null,
    unpublished_at: null,
    revision: null,
    waiting: "article",
    mine: false,
    ...over,
  };
}

const PUBLISHED = article({
  id: "a2",
  status: "published",
  slug: "boons-101",
  slug_fixed: true,
  title: "Boons 101",
  published_at: "2026-11-01T12:00:00Z",
  waiting: null,
  tags: [TAGS[1]!],
});
const CHANGED = article({
  id: "a3",
  status: "published",
  slug: "safety-at-the-table",
  slug_fixed: true,
  title: "Safety at the table",
  published_at: "2026-10-01T12:00:00Z",
  waiting: "changes",
  revision: { title: "Safety at every table", summary: "Revised.", body: "New words.", troupe: TROUPE, picture: null, submitted_at: "2026-11-21T09:00:00Z" },
});
const DOWN = article({ id: "a4", status: "unpublished", title: "Old news", published_at: "2026-09-01T12:00:00Z", unpublished_at: "2026-11-02T12:00:00Z", waiting: null, note: "Out of date." });

function show(queue: Partial<BlogQueueOut> = {}, at = "/custodian/blog") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  client.setQueryData(["blog-queue"], { waiting: [article({}), CHANGED], published: [PUBLISHED, CHANGED], unpublished: [DOWN], ...queue });
  client.setQueryData(["blog-tags"], TAGS);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <BlogTab />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function answering(method: "POST" | "PUT") {
  return vi.spyOn(api, method).mockImplementation((async () => ({ data: {}, response: new Response(null, { status: 200 }) })) as never);
}

const section = (name: string) => screen.getByRole("heading", { name, level: 2 }).closest("section")!;
const item = (within_: HTMLElement, name: string) => within(within_).getByRole("listitem", { name });

describe("Custodian › Blog (#1156)", () => {
  it("lists what waits, what is published and what was unpublished", () => {
    show();
    const waiting = section("Waiting");
    const first = item(waiting, "Running your first Elysium");
    expect(within(first).getByText("Mara Quinn")).toBeTruthy();
    expect(within(first).getByText(/of Lords of the Night/)).toBeTruthy();
    expect(within(first).getByText("Address: /blog/running-your-first-elysium")).toBeTruthy();
    expect(within(first).getByRole("button", { name: "Publish" })).toBeTruthy();
    // A published article's changes wait as the changes, while it is listed as published.
    const changes = item(waiting, "Safety at every table");
    expect(within(changes).getByText("Changes")).toBeTruthy();
    expect(within(changes).getByRole("button", { name: "Publish the changes" })).toBeTruthy();
    const published = section("Published");
    expect(within(item(published, "Safety at the table")).getByText("Changes waiting")).toBeTruthy();
    expect(within(item(published, "Boons 101")).getByRole("button", { name: "Feature it" })).toBeTruthy();
    // Once published its address is fixed.
    expect(within(item(published, "Boons 101")).queryByRole("button", { name: "Change" })).toBeNull();
    const down = item(section("Unpublished"), "Old news");
    expect(within(down).getByText(/Why it was unpublished:/)).toBeTruthy();
    expect(within(down).queryByRole("button", { name: /Publish|Unpublish/ })).toBeNull();
  });

  it("says when nothing waits or is published, and leaves Unpublished out when empty", () => {
    show({ waiting: [], published: [], unpublished: [] });
    expect(screen.getByText("Nothing is waiting to be published.")).toBeTruthy();
    expect(screen.getByText("No article is published yet.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Unpublished" })).toBeNull();
  });

  it("opens the article the custodian's bell task links to, under Waiting (#1170)", () => {
    show({}, "/custodian/blog#article-a3");
    const opened = (li: HTMLElement) => (li.querySelector("details") as HTMLDetailsElement).open;
    const changes = item(section("Waiting"), "Safety at every table");
    expect(changes.id).toBe("article-a3");
    expect(opened(changes)).toBe(true);
    // Not its entry under Published, nor any other article.
    expect(opened(item(section("Published"), "Safety at the table"))).toBe(false);
    expect(opened(item(section("Waiting"), "Running your first Elysium"))).toBe(false);
    expect(document.querySelectorAll("#article-a3")).toHaveLength(1);
  });

  it("publishes what waits", async () => {
    const post = answering("POST");
    show();
    fireEvent.click(within(item(section("Waiting"), "Running your first Elysium")).getByRole("button", { name: "Publish" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/blog/articles/{article_id}/publish", { params: { path: { article_id: "a1" } } }));
  });

  it("returns an article only with a note for its author", async () => {
    const post = answering("POST");
    show();
    const first = item(section("Waiting"), "Running your first Elysium");
    fireEvent.click(within(first).getByRole("button", { name: "Return with a note…" }));
    const send = within(first).getByRole("button", { name: "Return it" });
    expect((send as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(first).getByLabelText("Note to the author"), { target: { value: "Say who it's for." } });
    fireEvent.click(send);
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/blog/articles/{article_id}/return", { params: { path: { article_id: "a1" } }, body: { note: "Say who it's for." } }),
    );
  });

  it("unpublishes only with a reason, and features", async () => {
    const post = answering("POST");
    const put = answering("PUT");
    show();
    const boons = item(section("Published"), "Boons 101");
    fireEvent.click(within(boons).getByRole("button", { name: "Feature it" }));
    await waitFor(() => expect(put).toHaveBeenCalledWith("/api/blog/articles/{article_id}/featured", { params: { path: { article_id: "a2" } }, body: { featured: true } }));
    fireEvent.click(within(boons).getByRole("button", { name: "Unpublish…" }));
    const down = within(boons).getByRole("button", { name: "Unpublish" });
    expect((down as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(boons).getByLabelText("Why unpublish it?"), { target: { value: "It names a real player." } });
    fireEvent.click(down);
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/blog/articles/{article_id}/unpublish", { params: { path: { article_id: "a2" } }, body: { reason: "It names a real player." } }),
    );
  });

  it("tags with the chips, each choice saved at once", async () => {
    const put = answering("PUT");
    show();
    const tags = within(item(section("Published"), "Boons 101")).getByRole("list", { name: "Tags" });
    expect(within(tags).getByRole("button", { name: "Storytelling" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(tags).getByRole("button", { name: "How to play" }).getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(within(tags).getByRole("button", { name: "How to play" }));
    await waitFor(() => expect(put).toHaveBeenCalledWith("/api/blog/articles/{article_id}/tags", { params: { path: { article_id: "a2" } }, body: { tag_ids: ["t2", "t1"] } }));
  });

  it("shows a retired tag an article has, to take off but not put back (#1161)", async () => {
    const put = answering("PUT");
    // The list offered leaves the retired tag out; the article still has it.
    show({ published: [{ ...PUBLISHED, tags: [TAGS[1]!, { id: "t9", name: "Old ways", slug: "old-ways" }] }], waiting: [article({})] });
    const tags = within(item(section("Published"), "Boons 101")).getByRole("list", { name: "Tags" });
    expect(within(tags).getAllByRole("button").map((b) => b.textContent)).toEqual(["How to play", "Storytelling", "Old ways(retired)"]);
    expect(within(item(section("Waiting"), "Running your first Elysium")).queryByText("Old ways")).toBeNull();
    fireEvent.click(within(tags).getByRole("button", { name: /Old ways/ }));
    await waitFor(() => expect(put).toHaveBeenCalledWith("/api/blog/articles/{article_id}/tags", { params: { path: { article_id: "a2" } }, body: { tag_ids: ["t2"] } }));
  });

  it("changes an address before it is published", async () => {
    const put = answering("PUT");
    show();
    const first = item(section("Waiting"), "Running your first Elysium");
    fireEvent.click(within(first).getByRole("button", { name: "Change" }));
    fireEvent.change(within(first).getByLabelText("Address"), { target: { value: "first-elysium" } });
    fireEvent.click(within(first).getByRole("button", { name: "Save address" }));
    await waitFor(() => expect(put).toHaveBeenCalledWith("/api/blog/articles/{article_id}/slug", { params: { path: { article_id: "a1" } }, body: { slug: "first-elysium" } }));
  });
});

describe("where an article stands, for its author", () => {
  it("names each step", () => {
    expect(statusText(article({ status: "draft", waiting: null }))).toBe("Draft");
    expect(statusText(article({ status: "draft", waiting: null, note: "Shorter." }))).toBe("Returned to you");
    expect(statusText(article({}))).toBe("Waiting for the custodian");
    expect(statusText(PUBLISHED)).toBe("Published");
    expect(statusText(CHANGED)).toBe("Published, with changes waiting for the custodian");
    expect(statusText({ ...CHANGED, waiting: null })).toBe("Published, with changes not yet proposed");
    expect(statusText({ ...CHANGED, waiting: null, note: "Too long." })).toBe("Published, with changes returned to you");
    expect(statusText(DOWN)).toBe("Unpublished");
  });
});

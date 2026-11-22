import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { BlogTagKeptOut } from "../../api/types";
import { tagArticles, withRetired } from "../blog/blog";
import { BlogTagsTab } from "./BlogTagsTab";

beforeAll(() => {
  // jsdom has no modal dialogs of its own.
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.open = false;
  };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function tag(over: Partial<BlogTagKeptOut>): BlogTagKeptOut {
  return { id: "t1", name: "How to play", slug: "how-to-play", slug_fixed: false, retired: false, articles: 0, published: 0, ...over };
}

const TAGS = [
  tag({ articles: 3, published: 2, slug_fixed: true }),
  tag({ id: "t2", name: "Storytelling", slug: "storytelling", articles: 1, published: 0 }),
  tag({ id: "t3", name: "Old ways", slug: "old-ways", retired: true, articles: 1, published: 1, slug_fixed: true }),
];

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  client.setQueryData(["blog-tags", "kept"], TAGS);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BlogTagsTab />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function answering(method: "POST" | "PUT") {
  return vi.spyOn(api, method).mockImplementation((async () => ({ data: TAGS, response: new Response(null, { status: 200 }) })) as never);
}

const row = (name: string) => screen.getByRole("row", { name });
function choose(name: string, item: string) {
  fireEvent.click(within(row(name)).getByRole("button", { name: `Actions for ${name}` }));
  fireEvent.click(screen.getByRole("menuitem", { name: item }));
}

describe("Custodian › Blog › Tags (#1161)", () => {
  it("lists every tag in order, with its articles, and marks the retired", () => {
    show();
    const rows = within(screen.getByRole("table", { name: "Tags" })).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.getAttribute("aria-label"))).toEqual(["How to play", "Storytelling", "Old ways"]);
    expect(within(row("How to play")).getAllByText("3 articles, 2 published").length).toBeGreaterThan(0);
    expect(within(row("Old ways")).getByText("Retired")).toBeTruthy();
    expect(within(row("Storytelling")).queryByText("Retired")).toBeNull();
  });

  it("adds a tag", async () => {
    const post = answering("POST");
    show();
    fireEvent.click(screen.getByRole("button", { name: "Add a tag" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Elysium" } });
    fireEvent.click(screen.getByRole("button", { name: "Add the tag" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/blog/tags", { body: { name: "Elysium" } }));
  });

  it("renames, saying whether its address stays", async () => {
    const put = answering("PUT");
    show();
    choose("How to play", "Rename…");
    expect(screen.getByText(/Its address on the blog stays how-to-play: a published article has it/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Playing" } });
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    await waitFor(() => expect(put).toHaveBeenCalledWith("/api/blog/tags/{tag_id}", { params: { path: { tag_id: "t1" } }, body: { name: "Playing" } }));
  });

  it("retires a tag and offers a retired one again", async () => {
    const put = answering("PUT");
    show();
    choose("Storytelling", "Retire");
    await waitFor(() => expect(put).toHaveBeenCalledWith("/api/blog/tags/{tag_id}/retired", { params: { path: { tag_id: "t2" } }, body: { retired: true } }));
    choose("Old ways", "Offer it again");
    await waitFor(() => expect(put).toHaveBeenCalledWith("/api/blog/tags/{tag_id}/retired", { params: { path: { tag_id: "t3" } }, body: { retired: false } }));
  });

  it("moves a tag, sending the whole order", async () => {
    const put = answering("PUT");
    show();
    choose("Storytelling", "Move up");
    await waitFor(() => expect(put).toHaveBeenCalledWith("/api/blog/tag-order", { body: { tag_ids: ["t2", "t1", "t3"] } }));
  });

  it("merges into a tag that isn't retired", async () => {
    const post = answering("POST");
    show();
    choose("How to play", "Merge into…");
    expect(screen.getByText(/The 3 articles tagged How to play are tagged with the tag you choose instead/)).toBeTruthy();
    const into = screen.getByLabelText("Merge it into");
    expect(within(into).getAllByRole("option").map((o) => o.textContent)).toEqual(["Storytelling"]);
    fireEvent.click(screen.getByRole("button", { name: "Merge into Storytelling" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/blog/tags/{tag_id}/merge", { params: { path: { tag_id: "t1" } }, body: { into_id: "t2" } }));
  });
});

describe("a tag's articles, in words", () => {
  it("counts them and those published", () => {
    expect(tagArticles({ articles: 0, published: 0 })).toBe("No articles");
    expect(tagArticles({ articles: 1, published: 0 })).toBe("1 article, none published");
    expect(tagArticles({ articles: 1, published: 1 })).toBe("1 article, published");
    expect(tagArticles({ articles: 4, published: 4 })).toBe("4 articles, all published");
    expect(tagArticles({ articles: 4, published: 1 })).toBe("4 articles, 1 published");
  });
});

describe("the chips both pages show (#1161)", () => {
  it("offers the tags, then any retired one the article has", () => {
    const offered = [{ id: "t1", name: "How to play", slug: "how-to-play" }];
    const old = { id: "t9", name: "Old ways", slug: "old-ways" };
    expect(withRetired(offered, [offered[0]!, old])).toEqual([
      { tag: offered[0], retired: false },
      { tag: old, retired: true },
    ]);
    expect(withRetired(offered)).toEqual([{ tag: offered[0], retired: false }]);
  });
});

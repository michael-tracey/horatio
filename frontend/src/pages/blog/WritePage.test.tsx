import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { BlogArticleOut, BlogTagOut, BlogWriterOut, MyAuthor } from "../../api/types";
import { BlogArticleView } from "./BlogArticleView";
import { WritePage } from "./WritePage";

// The editor itself (Tiptap) is tested where it lives; here a plain box stands in.
vi.mock("../character/RichEditor", () => ({
  default: ({ initial, onChange, label }: { initial: string; onChange: (s: string) => void; label: string }) => (
    <textarea aria-label={label} defaultValue={initial} onChange={(e) => onChange(e.target.value)} />
  ),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeAll(() => {
  // jsdom has no modal dialogs of its own.
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.open = false;
  };
});

const LORDS = { id: "lords", name: "Lords of the Night", archived: false, public: true, card: { id: "lords", name: "Lords of the Night", abbreviation: "LotN", portrait: "/api/troupes/lords/portraits/p9", description: "A Camarilla game in Leeds." } };
const ASH = { id: "ash", name: "Court of Ash", archived: false, public: false, card: null };
const TAGS: BlogTagOut[] = [
  { id: "t1", name: "How to play", slug: "how-to-play" },
  { id: "t2", name: "Storytelling", slug: "storytelling" },
];
const WRITER: BlogWriterOut = { can_write: true, troupes: [ASH, LORDS] };

function article(over: Partial<BlogArticleOut> = {}): BlogArticleOut {
  return {
    id: "a1",
    status: "draft",
    slug: "running-your-first-elysium",
    slug_fixed: false,
    title: "Running your first Elysium",
    summary: "What I wish I'd known.",
    body: "Start small.",
    picture: null,
    author_id: "u1",
    author_name: "Mara Quinn",
    troupe: LORDS,
    featured: false,
    note: "",
    tags: [],
    created_at: "2026-11-18T12:00:00Z",
    updated_at: "2026-11-19T12:00:00Z",
    submitted_at: null,
    published_at: null,
    revised_at: null,
    unpublished_at: null,
    revision: null,
    waiting: null,
    mine: true,
    ...over,
  };
}

const NO_AUTHOR: MyAuthor = { saved: false, display_name: "Mara Quinn", handle: "mara", bio: "", links: [], picture: null, picture_crop: null, public: false, pictures_available: true };

function show(at: string, mine: BlogArticleOut[] = [], writer: BlogWriterOut = WRITER, author: MyAuthor = NO_AUTHOR) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  client.setQueryData(["blog-writer"], writer);
  client.setQueryData(["blog-mine"], mine);
  client.setQueryData(["blog-tags"], TAGS);
  client.setQueryData(["blog-author"], author);
  client.setQueryData(["me"], { id: "u1", display_name: "Mara Quinn" });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/blog/write" element={<WritePage />} />
          <Route path="/blog/write/:articleId" element={<WritePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const answer = (data: unknown) => ({ data, response: new Response(null, { status: 200 }) });
const button = (name: string) => screen.queryByRole("button", { name });
const where = () => screen.getByRole("region", { name: "Where it stands" });

describe("Write for the blog: your articles (#1157)", () => {
  it("lists each article with where it stands, its dates and the custodian's note", () => {
    show("/blog/write", [
      article({ note: "Say which book it's from." }),
      article({ id: "a2", title: "Boons 101", status: "published", published_at: "2026-11-01T12:00:00Z", troupe: null }),
      article({ id: "a3", title: "Old news", status: "unpublished", published_at: "2026-10-01T12:00:00Z", unpublished_at: "2026-11-10T12:00:00Z", note: "Out of date." }),
    ]);
    expect(screen.getByRole("link", { name: "Write an article" }).getAttribute("href")).toBe("/blog/write/new");
    expect(screen.getByRole("link", { name: "the writing guide" }).getAttribute("href")).toBe("/help/blog");
    const returned = screen.getByRole("listitem", { name: "Running your first Elysium" });
    expect(within(returned).getByText("Returned to you")).toBeTruthy();
    expect(within(returned).getByText(/^Started 18 Nov 2026/)).toBeTruthy();
    expect(within(returned).getByText("The custodian's note:")).toBeTruthy();
    expect(within(returned).getByText("Say which book it's from.")).toBeTruthy();
    expect(within(screen.getByRole("listitem", { name: "Boons 101" })).getByText("Started 18 Nov 2026 · published 1 Nov 2026")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Set up your author profile" }).getAttribute("href")).toBe("/account/blog");
    const down = screen.getByRole("listitem", { name: "Old news" });
    expect(within(down).getByText(/unpublished 10 Nov 2026/)).toBeTruthy();
    expect(within(down).getByText("Why the custodian unpublished it:")).toBeTruthy();
  });

  it("says when there are none, and offers no new article to someone who can't write", () => {
    show("/blog/write", [], { can_write: false, troupes: [] });
    expect(screen.getByText("Only the staff of a troupe that is running can write for the blog.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Write an article" })).toBeNull();
  });
});

describe("Write for the blog: one article (#1157)", () => {
  it("starts a new one naming the troupe it was opened from, and says a private troupe shows its name only", () => {
    show("/blog/write/new?troupe=ash");
    expect(where().textContent).toContain("A new article, not yet saved.");
    expect((screen.getByLabelText("Troupe") as HTMLSelectElement).value).toBe("ash");
    expect(screen.getByText(/Court of Ash isn't public, so the blog will show its name only\./)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Troupe"), { target: { value: "lords" } });
    expect(screen.queryByText(/so the blog will show its name only/)).toBeNull();
    expect(screen.getByText(/a private or archived troupe shows its name only/)).toBeTruthy();
    expect(screen.getByText("Save it as a draft first, then add a picture to go across the top of it.")).toBeTruthy();
    expect(button("Delete the draft")).toBeNull();
  });

  it("saves a new one with its tags, then submits it", async () => {
    const made = article();
    const post = vi.spyOn(api, "POST").mockImplementation((async (url: string) => answer(url === "/api/blog/articles" ? made : { ...made, status: "submitted" })) as never);
    const put = vi.spyOn(api, "PUT").mockImplementation((async () => answer({ ...made, tags: [TAGS[1]] })) as never);
    show("/blog/write/new");
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Running your first Elysium" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Article" }), { target: { value: "Start small." } });
    fireEvent.click(within(screen.getByRole("list", { name: "Tags" })).getByRole("button", { name: "Storytelling" }));
    fireEvent.click(button("Submit to the custodian")!);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[0]![1]).toEqual({ body: { title: "Running your first Elysium", summary: "", body: "Start small.", troupe_id: "ash" } });
    expect(put.mock.calls[0]![1]).toEqual({ params: { path: { article_id: "a1" } }, body: { tag_ids: ["t2"] } });
    expect(post.mock.calls[1]![0]).toBe("/api/blog/articles/{article_id}/submit");
  });

  it("shows a returned draft's note, and lets its author delete it", () => {
    show("/blog/write/a1", [article({ note: "Say which book it's from." })]);
    expect(where().textContent).toContain("The custodian returned it to you, with a note.");
    expect(within(where()).getByText("Say which book it's from.")).toBeTruthy();
    expect(button("Submit to the custodian")).toBeTruthy();
    expect(button("Delete the draft")).toBeTruthy();
    // Nothing changed yet: nothing to save.
    expect((button("Save draft") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Your first Elysium" } });
    expect((button("Save draft") as HTMLButtonElement).disabled).toBe(false);
  });

  it("holds one waiting for the custodian still, with Withdraw", () => {
    show("/blog/write/a1", [article({ status: "submitted", submitted_at: "2026-11-20T09:00:00Z", waiting: "article" })]);
    expect(where().textContent).toContain("Waiting for the custodian since 20 Nov 2026.");
    expect(button("Withdraw")).toBeTruthy();
    expect(button("Submit to the custodian")).toBeNull();
    expect(button("Delete the draft")).toBeNull();
    expect(screen.getByLabelText("Title").matches(":disabled")).toBe(true);
    expect(screen.getByText("The custodian tags it once it is submitted.")).toBeTruthy();
  });

  it("proposes a published article's changes, and throws them away", async () => {
    const live = article({ status: "published", published_at: "2026-11-01T12:00:00Z", slug_fixed: true });
    show("/blog/write/a1", [live]);
    expect(where().textContent).toContain("Published on 1 Nov 2026.");
    // Nothing to propose until something changes.
    expect((button("Propose the changes") as HTMLButtonElement).disabled).toBe(true);
    expect(button("Throw away the changes")).toBeNull();
    expect(button("Delete the draft")).toBeNull();
    cleanup();

    const changed = { ...live, revision: { title: "Your first Elysium", summary: "", body: "Start smaller.", troupe: LORDS, picture: null, submitted_at: null } };
    const remove = vi.spyOn(api, "DELETE").mockImplementation((async () => answer(live)) as never);
    show("/blog/write/a1", [changed]);
    expect(where().textContent).toContain("You have changes not yet proposed.");
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Your first Elysium");
    expect((button("Propose the changes") as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button("Throw away the changes")!);
    fireEvent.click(within(await screen.findByRole("dialog", { name: "Throw away your changes?" })).getByRole("button", { name: "Throw them away" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("/api/blog/articles/{article_id}/revision", { params: { path: { article_id: "a1" } } }));
    await waitFor(() => expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Running your first Elysium"));
  });

  it("withdraws a published article's changes waiting", () => {
    show("/blog/write/a1", [
      article({ status: "published", published_at: "2026-11-01T12:00:00Z", waiting: "changes", revision: { title: "Again", summary: "", body: "x", troupe: null, picture: null, submitted_at: "2026-11-06T12:00:00Z" } }),
    ]);
    expect(where().textContent).toContain("Your changes have waited for the custodian since 6 Nov 2026.");
    expect(button("Withdraw the changes")).toBeTruthy();
    expect(button("Propose the changes")).toBeNull();
  });

  it("previews what is written as the blog will show it, under a banner", () => {
    show("/blog/write/a1", [article({ tags: [TAGS[0]!] })]);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Your first Elysium" } });
    fireEvent.click(screen.getByRole("radio", { name: "Preview" }));
    expect(screen.getByRole("note").textContent).toMatch(/^Preview: the article as the blog will show it\./);
    const shown = screen.getByRole("article", { name: "Your first Elysium" });
    expect(within(shown).getByRole("heading", { name: "Your first Elysium", level: 2 })).toBeTruthy();
    expect(within(shown).getByText("How to play")).toBeTruthy();
    expect(within(shown).getByText(/Not published yet/)).toBeTruthy();
    expect(within(shown).getAllByRole("link", { name: "Lords of the Night" })[0]!.getAttribute("href")).toBe("/t/lords");
    // A public troupe's card is beside the author's, as on the blog (#1160).
    const troupe = within(shown).getByRole("region", { name: "About Lords of the Night" });
    expect(within(troupe).getByText("A Camarilla game in Leeds.")).toBeTruthy();
  });

  it("shows no troupe card for a private troupe in the preview", () => {
    show("/blog/write/a1", [article({ troupe: ASH })]);
    fireEvent.click(screen.getByRole("radio", { name: "Preview" }));
    const shown = screen.getByRole("article", { name: "Running your first Elysium" });
    expect(within(shown).getByText("Court of Ash")).toBeTruthy();
    expect(within(shown).queryByRole("region", { name: "About Court of Ash" })).toBeNull();
  });

  it("puts their author card under the preview, once they have one", () => {
    show("/blog/write/a1", [article()], WRITER, { ...NO_AUTHOR, saved: true, display_name: "Mara Q.", bio: "Storyteller since 1998." });
    fireEvent.click(screen.getByRole("radio", { name: "Preview" }));
    const shown = screen.getByRole("article", { name: "Running your first Elysium" });
    expect(within(shown).getByRole("region", { name: "About Mara Q." })).toBeTruthy();
    expect(within(shown).getByText("Storyteller since 1998.")).toBeTruthy();
    expect(within(shown).queryByRole("link", { name: "Set up your author profile" })).toBeNull();
  });

  it("says when the article isn't theirs or doesn't exist", () => {
    show("/blog/write/nope");
    expect(screen.getByText("No such article.")).toBeTruthy();
  });
});

describe("BlogArticleView", () => {
  it("names a private or archived troupe without a link, and shows the picture 2:1", () => {
    const shown = {
      title: "Boons 101",
      summary: "",
      body: "Owe nobody.",
      picture: "/api/blog/articles/a1/pictures/p1",
      author_name: "Mara Quinn",
      troupe: ASH,
      tags: [],
      published_at: "2026-11-01T12:00:00Z",
      revised_at: "2026-11-05T12:00:00Z",
    };
    const { container } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { enabled: false } } })}>
        <MemoryRouter>
          <BlogArticleView article={shown} author={<p>About Mara</p>} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("heading", { name: "Boons 101", level: 1 })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Court of Ash" })).toBeNull();
    expect(screen.getByText("Court of Ash")).toBeTruthy();
    expect(screen.getByText(/1 Nov 2026, changed 5 Nov 2026/)).toBeTruthy();
    expect(screen.getByText("About Mara")).toBeTruthy();
    expect(container.querySelector("img")?.getAttribute("src")).toBe("/api/blog/articles/a1/pictures/p1/1200.webp");
  });
});

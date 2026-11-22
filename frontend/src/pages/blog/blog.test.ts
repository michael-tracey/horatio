import { describe, expect, it } from "vitest";
import type { BlogArticleOut } from "../../api/types";
import { deletable, standing, statusText, taggable, troupeLinked } from "./blog";

const day = (at: string) => at.slice(0, 10);

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
    picture_sizes: [],
    author_id: "u1",
    author_name: "Mara Quinn",
    troupe: { id: "lords", name: "Lords of the Night", archived: false, public: true, card: null },
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
    body_pictures: [],
    waiting: null,
    mine: true,
    ...over,
  };
}

const REVISION = { title: "Running your first Elysium, again", summary: "", body: "Start smaller.", troupe: null, picture: null, picture_sizes: [], submitted_at: null };

describe("where an article stands, for its author (#1157)", () => {
  it("says what a new article and a draft are, and what comes next", () => {
    expect(standing(undefined, day).where).toBe("A new article, not yet saved.");
    expect(standing(article(), day)).toEqual({
      where: "A draft: only you and the custodian can see it.",
      next: "Submit it when it's ready. The custodian reads it before it goes on the blog.",
    });
  });

  it("gives a returned draft the custodian's note", () => {
    const found = standing(article({ note: "Say which book." }), day);
    expect(found.where).toBe("The custodian returned it to you, with a note.");
    expect(found.next).toBe("Change what the note asks, then submit it again.");
    expect(found.note).toEqual({ label: "The custodian's note", text: "Say which book." });
  });

  it("dates one waiting, and says how to change it", () => {
    const found = standing(article({ status: "submitted", submitted_at: "2026-11-20T09:00:00Z", waiting: "article" }), day);
    expect(found.where).toBe("Waiting for the custodian since 2026-11-20.");
    expect(found.next).toMatch(/withdraw it\.$/);
    expect(found.note).toBeUndefined();
  });

  it("follows a published article through its changes", () => {
    const up = { status: "published" as const, published_at: "2026-11-01T12:00:00Z" };
    expect(standing(article(up), day).where).toBe("Published on 2026-11-01.");
    expect(standing(article({ ...up, revised_at: "2026-11-05T12:00:00Z" }), day).where).toBe("Published on 2026-11-01, changed 2026-11-05.");
    expect(standing(article({ ...up, revision: REVISION }), day).where).toBe("Published on 2026-11-01. You have changes not yet proposed.");
    const waiting = standing(article({ ...up, revision: { ...REVISION, submitted_at: "2026-11-06T12:00:00Z" }, waiting: "changes" }), day);
    expect(waiting.where).toBe("Published on 2026-11-01. Your changes have waited for the custodian since 2026-11-06.");
    const returned = standing(article({ ...up, revision: REVISION, note: "Too long." }), day);
    expect(returned.where).toBe("Published on 2026-11-01. The custodian returned your changes, with a note.");
    expect(returned.note?.text).toBe("Too long.");
    // A note left from changes since thrown away no longer applies.
    expect(standing(article({ ...up, note: "Too long." }), day).note).toBeUndefined();
  });

  it("gives an unpublished article the custodian's reason", () => {
    const found = standing(article({ status: "unpublished", published_at: "2026-11-01T12:00:00Z", unpublished_at: "2026-11-10T12:00:00Z", note: "Out of date." }), day);
    expect(found.where).toBe("The custodian unpublished it on 2026-11-10: it isn't on the blog.");
    expect(found.note).toEqual({ label: "Why the custodian unpublished it", text: "Out of date." });
  });
});

describe("what its author may do", () => {
  it("deletes only an article never published and not waiting", () => {
    expect(deletable(article())).toBe(true);
    expect(deletable(article({ status: "submitted" }))).toBe(false);
    expect(deletable(article({ status: "published", published_at: "2026-11-01T12:00:00Z" }))).toBe(false);
    expect(deletable(article({ status: "unpublished", published_at: "2026-11-01T12:00:00Z" }))).toBe(false);
  });

  it("tags it while it is being written, and not once the custodian has it", () => {
    expect(taggable(undefined)).toBe(true);
    expect(taggable(article())).toBe(true);
    expect(taggable(article({ status: "unpublished" }))).toBe(true);
    expect(taggable(article({ status: "submitted" }))).toBe(false);
    expect(taggable(article({ status: "published" }))).toBe(false);
  });

  it("says in a word or two where each stands, for the list", () => {
    expect(statusText(article({ note: "Say which book." }))).toBe("Returned to you");
    expect(statusText(article({ status: "submitted" }))).toBe("Waiting for the custodian");
  });
});

describe("the troupe an article names", () => {
  it("is linked only when public and running", () => {
    expect(troupeLinked({ id: "t", name: "T", archived: false, public: true, card: null })).toBe(true);
    expect(troupeLinked({ id: "t", name: "T", archived: false, public: false, card: null })).toBe(false);
    expect(troupeLinked({ id: "t", name: "T", archived: true, public: true, card: null })).toBe(false);
  });
});

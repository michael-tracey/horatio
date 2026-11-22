import type { BlogArticleOut, BlogTagOut, BlogTroupeOut, PictureSizeOut } from "../../api/types";

/** What an article says, as the custodian reads it to decide and its author works on it: a published one's changes, if it has any, else the article itself. */
export type Words = { title: string; summary: string; body: string; troupe: BlogTroupeOut | null; picture: string | null; picture_sizes: PictureSizeOut[] };

export function working(article: BlogArticleOut): Words {
  return article.revision ?? article;
}

/** Where an article stands, in a few words, for its author. */
export function statusText(article: BlogArticleOut): string {
  if (article.waiting === "changes") return "Published, with changes waiting for the custodian";
  if (article.status === "published" && article.revision) return article.note ? "Published, with changes returned to you" : "Published, with changes not yet proposed";
  if (article.status === "draft" && article.note) return "Returned to you";
  return { draft: "Draft", submitted: "Waiting for the custodian", published: "Published", unpublished: "Unpublished" }[article.status];
}

/** The ids with `id` added, or taken out if it was there. */
export function toggled(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id];
}

/**
 * The tags to show as chips: those offered, then any retired one the article has
 * (#1161). A retired tag isn't offered any more, so `GET /blog/tags` leaves it out,
 * but it stays on the articles that have it.
 */
export function withRetired(offered: BlogTagOut[], had: BlogTagOut[] = []): { tag: BlogTagOut; retired: boolean }[] {
  const ids = new Set(offered.map((t) => t.id));
  return [...offered.map((tag) => ({ tag, retired: false })), ...had.filter((t) => !ids.has(t.id)).map((tag) => ({ tag, retired: true }))];
}

/** How many articles carry a tag, and how many of those are published, for Custodian › Blog › Tags. */
export function tagArticles({ articles, published }: { articles: number; published: number }): string {
  if (articles === 0) return "No articles";
  const many = articles === 1 ? "1 article" : `${articles} articles`;
  if (published === articles) return articles === 1 ? "1 article, published" : `${many}, all published`;
  return `${many}, ${published === 0 ? "none" : published} published`;
}

/** Where an article stands and what happens next, in a line each, for its author on the writing page (#1157); and the custodian's note, if it is about where it stands now. */
export type Standing = { where: string; next: string; note?: { label: string; text: string } };

export function standing(article: BlogArticleOut | undefined, date: (at: string) => string): Standing {
  if (!article) return { where: "A new article, not yet saved.", next: "Save it as a draft, and submit it when it's ready: the custodian reads it before it goes on the blog." };
  const a = article;
  const returned = a.note ? { label: "The custodian's note", text: a.note } : undefined;
  if (a.status === "submitted")
    return {
      where: `Waiting for the custodian since ${date(a.submitted_at ?? a.updated_at)}.`,
      next: "They'll publish it or return it to you with a note, and you'll hear on your bell. To change it first, withdraw it.",
    };
  if (a.status === "draft" && a.note)
    return { where: "The custodian returned it to you, with a note.", next: "Change what the note asks, then submit it again.", note: returned };
  if (a.status === "draft") return { where: "A draft: only you and the custodian can see it.", next: "Submit it when it's ready. The custodian reads it before it goes on the blog." };
  if (a.status === "unpublished")
    return {
      where: `The custodian unpublished it${a.unpublished_at ? ` on ${date(a.unpublished_at)}` : ""}: it isn't on the blog.`,
      next: "Change it if you like and submit it again. Once they publish it, it's back at the same address.",
      note: a.note ? { label: "Why the custodian unpublished it", text: a.note } : undefined,
    };
  const up = `Published${a.published_at ? ` on ${date(a.published_at)}` : ""}${a.revised_at ? `, changed ${date(a.revised_at)}` : ""}.`;
  if (a.waiting === "changes")
    return {
      where: `${up} Your changes have waited for the custodian since ${date(a.revision?.submitted_at ?? a.updated_at)}.`,
      next: "Readers see the published version until the custodian publishes your changes. To change them again, withdraw them.",
    };
  if (a.revision && a.note)
    return {
      where: `${up} The custodian returned your changes, with a note.`,
      next: "Readers still see the published version. Change what the note asks and propose the changes again, or throw them away.",
      note: returned,
    };
  if (a.revision)
    return { where: `${up} You have changes not yet proposed.`, next: "Readers still see the published version. Propose the changes to the custodian, or throw them away." };
  return { where: up, next: "To change it, edit it here and propose the changes: it stays on the blog as it is until the custodian publishes them." };
}

/** Its author may delete it: never published, and not waiting for the custodian. */
export function deletable(article: BlogArticleOut): boolean {
  return article.published_at == null && article.status !== "submitted";
}

/** Its author may tag it: the custodian tags it once it is submitted or published. */
export function taggable(article: BlogArticleOut | undefined): boolean {
  return !article || article.status === "draft" || article.status === "unpublished";
}

/** The blog links a troupe that is public and running; any other it names only (#1155). */
export function troupeLinked(troupe: BlogTroupeOut): boolean {
  return troupe.public && !troupe.archived;
}

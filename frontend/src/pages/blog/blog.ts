import type { BlogArticleOut, BlogTroupeOut } from "../../api/types";

/** What an article says, as the custodian reads it to decide and its author works on it: a published one's changes, if it has any, else the article itself. */
export type Words = { title: string; summary: string; body: string; troupe: BlogTroupeOut | null; picture: string | null };

export function working(article: BlogArticleOut): Words {
  return article.revision ?? article;
}

/** Where an article stands, in a few words, for its author. */
export function statusText(article: BlogArticleOut): string {
  if (article.waiting === "changes") return "Published, with changes waiting for the custodian";
  if (article.status === "published" && article.revision) return "Published, with changes not yet sent";
  if (article.status === "draft" && article.note) return "Returned to you";
  return { draft: "Draft", submitted: "Waiting for the custodian", published: "Published", unpublished: "Unpublished" }[article.status];
}

/** The ids with `id` added, or taken out if it was there. */
export function toggled(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id];
}

/** How many articles carry a tag, and how many of those are published, for Custodian › Blog › Tags. */
export function tagArticles({ articles, published }: { articles: number; published: number }): string {
  if (articles === 0) return "No articles";
  const many = articles === 1 ? "1 article" : `${articles} articles`;
  if (published === articles) return articles === 1 ? "1 article, published" : `${many}, all published`;
  return `${many}, ${published === 0 ? "none" : published} published`;
}

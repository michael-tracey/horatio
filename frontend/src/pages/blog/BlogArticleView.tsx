import type { ReactNode } from "react";
import { Link } from "react-router";
import type { BlogTagOut, BlogTroupeOut } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { useDates } from "../../dates";
import { troupeLinked } from "./blog";

/** What an article shows a reader: its published words, or its author's working ones in a preview. */
export type ArticleShown = {
  title: string;
  summary: string;
  body: string;
  /** Its hero picture (add "/1200.webp" or "/600.webp"), or null. */
  picture: string | null;
  author_name: string;
  troupe: BlogTroupeOut | null;
  tags: BlogTagOut[];
  published_at: string | null;
  revised_at: string | null;
};

/**
 * An article as the blog shows it (#1157): its hero picture, tags, title, summary,
 * byline and words. The writing page's preview draws it, and the blog's own article
 * page (#1158) is meant to as well, so the two can't drift apart. The troupe it names
 * is a link to the troupe's public page only when that is public and running (#1155);
 * otherwise its name alone. `author` is the room under the words for the author's
 * card (#1159); `tagLink` makes each tag a link to its page.
 */
export function BlogArticleView({
  article: a,
  heading = "h1",
  author,
  tagLink,
}: {
  article: ArticleShown;
  /** The title's level: h1 on the blog's own page, h2 inside another page. */
  heading?: "h1" | "h2";
  author?: ReactNode;
  tagLink?: (tag: BlogTagOut) => string;
}) {
  const dates = useDates();
  const Title = heading;
  const chip = "inline-flex min-h-7 items-center rounded-full border border-ash px-3 text-xs text-mist";
  return (
    <article aria-label={a.title} className="mx-auto flex w-full max-w-3xl min-w-0 flex-col gap-4">
      {a.picture && (
        <img
          src={`${a.picture}/1200.webp`}
          srcSet={`${a.picture}/600.webp 600w, ${a.picture}/1200.webp 1200w`}
          sizes="(min-width: 48rem) 48rem, 100vw"
          alt=""
          className="aspect-[2/1] w-full rounded-md object-cover"
        />
      )}
      {a.tags.length > 0 && (
        <ul aria-label="Tags" className="flex flex-wrap gap-2">
          {a.tags.map((t) => (
            <li key={t.id}>
              {tagLink ? (
                <Link to={tagLink(t)} className={`${chip} hover:border-mist hover:text-parchment`}>
                  {t.name}
                </Link>
              ) : (
                <span className={chip}>{t.name}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      <header className="flex flex-col gap-2">
        <Title className="font-display text-2xl break-words text-parchment sm:text-3xl">{a.title || "Untitled"}</Title>
        {a.summary && <p className="text-base break-words text-mist">{a.summary}</p>}
        <p className="text-sm text-mist">
          By <span className="text-parchment">{a.author_name}</span>
          {a.troupe && (
            <>
              {" of "}
              {troupeLinked(a.troupe) ? (
                <Link to={`/t/${a.troupe.id}`} className="text-gold hover:underline">
                  {a.troupe.name}
                </Link>
              ) : (
                <span className="text-parchment">{a.troupe.name}</span>
              )}
            </>
          )}
          {" · "}
          {a.published_at ? dates.date(a.published_at) : "Not published yet"}
          {a.revised_at && <>, changed {dates.date(a.revised_at)}</>}
        </p>
      </header>
      <Markdown text={a.body} />
      {author}
    </article>
  );
}

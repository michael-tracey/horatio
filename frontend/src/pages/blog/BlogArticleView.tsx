import { useMemo, type ReactNode } from "react";
import { Link } from "react-router";
import type { BlogBodyPictureOut, BlogPublicTroupeOut, BlogTagOut, PictureSizeOut } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { useDates } from "../../dates";
import { sizedPicture, sizesById } from "../../pictureSizes";
import { TroupeCard } from "./TroupeCard";

/** What an article shows a reader: its published words, or its author's working ones in a preview. */
export type ArticleShown = {
  title: string;
  summary: string;
  body: string;
  /** Its hero picture (add "/1200.webp" or "/600.webp"), or null. */
  picture: string | null;
  /** Its copies' sizes, so it keeps its room while it loads (#1183). */
  picture_sizes?: PictureSizeOut[];
  /** The pictures its words name, with their sizes. */
  body_pictures?: BlogBodyPictureOut[];
  author_name: string;
  /** Its name, and its card while it is public and running (#1160). */
  troupe: BlogPublicTroupeOut | null;
  tags: BlogTagOut[];
  published_at: string | null;
  revised_at: string | null;
};

/**
 * An article as the blog shows it (#1157): its hero picture, tags, title, summary,
 * byline and words. The writing page's preview draws it, and the blog's own article
 * page (#1158) is meant to as well, so the two can't drift apart. The troupe it names
 * is a link to the troupe's public page, with its card beside the author's, only when
 * it has a card: when it is public and running (#1160); otherwise its name alone.
 * `author` is the room under the words for the author's card (#1159); `tagLink` makes
 * each tag a link to its page. The words show their pictures (#1163).
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
  const hero = a.picture ? sizedPicture(a.picture, a.picture_sizes) : null;
  const sizes = useMemo(() => sizesById(a.body_pictures), [a.body_pictures]);
  const chip = "inline-flex min-h-7 items-center rounded-full border border-ash px-3 text-xs text-mist";
  return (
    <article aria-label={a.title} className="mx-auto flex w-full max-w-3xl min-w-0 flex-col gap-4">
      {hero && (
        <img
          src={hero.src}
          srcSet={hero.srcSet}
          width={hero.width}
          height={hero.height}
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
              {a.troupe.card ? (
                <Link to={`/t/${a.troupe.card.id}`} className="text-gold hover:underline">
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
      <Markdown text={a.body} pictures sizes={sizes} />
      {author}
      {a.troupe?.card && <TroupeCard troupe={a.troupe.card} />}
    </article>
  );
}

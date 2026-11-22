import type { ReactNode } from "react";
import { Link } from "react-router";
import type { BlogPublicAuthorOut, BlogPublicTagOut, BlogPublicTroupeOut } from "../../api/types";
import { authorPath } from "../../components/AuthorCard";
import { Markdown } from "../../components/Markdown";
import { PageTitle } from "../../components/ui";
import { useDates } from "../../dates";

/** A tag as a chip, leading to the tag's own page. */
export function TagChip({ tag }: { tag: BlogPublicTagOut }) {
  return (
    <Link to={`/blog/tags/${tag.slug}`} className="inline-flex min-h-8 items-center rounded-full border border-ash px-3 text-sm text-parchment hover:border-gold hover:text-gold">
      {tag.name}
    </Link>
  );
}

/** Who wrote it: their name, leading to their author page once they have one (#1159). */
export function AuthorName({ author }: { author: BlogPublicAuthorOut }) {
  if (!author.handle) return <>{author.name}</>;
  return (
    <Link to={authorPath(author.handle)} className="text-gold hover:underline">
      {author.name}
    </Link>
  );
}

/**
 * The troupe an article names: its public profile, or its name only when the troupe
 * is private or archived. The troupe card (#1160) takes its place.
 */
export function TroupeLine({ troupe }: { troupe: BlogPublicTroupeOut }) {
  return (
    <p className="text-sm text-mist">
      From{" "}
      {troupe.id ? (
        <Link to={`/t/${troupe.id}`} className="text-gold hover:underline">
          {troupe.name}
        </Link>
      ) : (
        troupe.name
      )}
    </p>
  );
}

/** "Published 3 Nov 2026", and when it was last changed if it was. */
export function Dateline({ publishedAt, revisedAt }: { publishedAt: string | null; revisedAt?: string | null }) {
  const dates = useDates();
  if (!publishedAt) return null;
  return (
    <>
      <time dateTime={publishedAt}>{dates.date(publishedAt)}</time>
      {revisedAt && <>, changed {dates.date(revisedAt)}</>}
    </>
  );
}

/** Its summary, then who wrote it and when, as lines of the title's subtitle. */
function Byline({ article }: { article: ArticleWords }) {
  return (
    <>
      {article.summary && <span className="mb-1 block text-base text-parchment">{article.summary}</span>}
      <span className="block">
        By <AuthorName author={article.author} />
        {article.published_at && (
          <>
            , <Dateline publishedAt={article.published_at} revisedAt={article.revised_at} />
          </>
        )}
      </span>
    </>
  );
}

export type ArticleWords = {
  title: string;
  summary: string;
  /** Markdown. */
  body: string;
  /** Its hero picture: add "/1200.webp" or "/600.webp". */
  picture: string | null;
  tags: BlogPublicTagOut[];
  author: BlogPublicAuthorOut;
  troupe: BlogPublicTroupeOut | null;
  /** None while it isn't published, as in a preview. */
  published_at: string | null;
  revised_at?: string | null;
};

/**
 * An article as the blog shows it (#1158): its title, summary, hero picture, who wrote
 * it and when, its tags, and its words, through the Markdown that renders no HTML. On
 * its own page it is the page's title; elsewhere, a preview say, give `heading={2}`.
 * `authorCard` goes under it (#1159's AuthorCard, for an author with a profile); its
 * author's name is on the dateline either way.
 */
export function BlogArticleView({ article, heading = 1, actions, authorCard }: { article: ArticleWords; heading?: 1 | 2; actions?: ReactNode; authorCard?: ReactNode }) {
  const title = article.title || "Untitled";
  return (
    <article className="flex min-w-0 flex-col gap-4">
      {article.picture && (
        <img
          src={`${article.picture}/1200.webp`}
          srcSet={`${article.picture}/600.webp 600w, ${article.picture}/1200.webp 1200w`}
          sizes="(min-width: 64rem) 64rem, 100vw"
          alt=""
          className="aspect-[16/9] w-full rounded-lg border border-ash object-cover"
        />
      )}
      {heading === 1 ? (
        <PageTitle actions={actions} subtitle={<Byline article={article} />}>
          {title}
        </PageTitle>
      ) : (
        <div>
          <h2 className="text-2xl text-parchment">{title}</h2>
          <p className="mt-1 text-sm text-mist">
            <Byline article={article} />
          </p>
        </div>
      )}
      {article.troupe && <TroupeLine troupe={article.troupe} />}
      {article.tags.length > 0 && (
        <ul aria-label="Tags" className="flex flex-wrap gap-2">
          {article.tags.map((t) => (
            <li key={t.slug}>
              <TagChip tag={t} />
            </li>
          ))}
        </ul>
      )}
      <div className="max-w-prose">
        <Markdown text={article.body} />
      </div>
      {authorCard && <div className="mt-4">{authorCard}</div>}
    </article>
  );
}

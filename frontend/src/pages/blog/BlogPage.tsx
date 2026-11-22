import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, Navigate, useParams, useSearchParams } from "react-router";
import { api, ApiError, unwrap } from "../../api/client";
import type { BlogPublicAuthorOut, BlogPublicPageOut, BlogPublicSummaryOut, BlogTagOut } from "../../api/types";
import { authorPath } from "../../components/AuthorCard";
import { Pager } from "../../components/Pager";
import { Badge, Empty, ErrorText, Loading, PageTitle } from "../../components/ui";
import { useDates } from "../../dates";
import { sizedPicture } from "../../pictureSizes";
import { useTitle } from "../../title";

// As many as the API puts on a page (blog_public.PAGE_SIZE).
export const PAGE_SIZE = 12;

/** The page asked for in the address (?page=2), counting from 1. */
export function pageFrom(params: URLSearchParams): number {
  const n = Number(params.get("page"));
  return Number.isInteger(n) && n >= 1 ? n : 1;
}

/** Who wrote it: their name, leading to their author page once they have one (#1159). */
function AuthorName({ author }: { author: BlogPublicAuthorOut }) {
  if (!author.handle) return <>{author.name}</>;
  return (
    <Link to={authorPath(author.handle)} className="text-gold hover:underline">
      {author.name}
    </Link>
  );
}

/** The troupe an article names (#1160): a link to its public profile while it has a card, else its name only. */
function TroupeName({ troupe }: { troupe: NonNullable<BlogPublicSummaryOut["troupe"]> }) {
  if (!troupe.card) return <>{troupe.name}</>;
  return (
    <Link to={`/t/${troupe.card.id}`} className="text-gold hover:underline">
      {troupe.name}
    </Link>
  );
}

/**
 * An article in a list: its picture, title, summary, author, date and tags. With
 * `withTroupe`, the byline names its troupe too, as the landing page's does (#1164).
 */
export function ArticleCard({ article: a, wide = false, withTroupe = false }: { article: BlogPublicSummaryOut; wide?: boolean; withTroupe?: boolean }) {
  const dates = useDates();
  // The 600 px copy, with its size, so the card keeps its room while it loads (#1183).
  const picture = a.picture ? sizedPicture(a.picture, a.picture_sizes, "600.webp") : null;
  return (
    <li aria-label={a.title} className="flex min-w-0 flex-col overflow-hidden rounded-lg border border-ash bg-night">
      {picture && <img src={picture.src} width={picture.width} height={picture.height} alt="" loading="lazy" className="aspect-[2/1] w-full object-cover" />}
      <div className="flex flex-col gap-2 p-4">
        <h3 className={wide ? "text-xl" : "text-lg"}>
          <Link to={`/blog/${a.slug}`} className="text-parchment hover:text-gold">
            {a.title}
          </Link>
          {a.featured && !wide && (
            <Badge tone="gold" className="ml-2 align-middle">
              Featured
            </Badge>
          )}
        </h3>
        {a.summary && <p className="text-sm">{a.summary}</p>}
        <p className="text-xs text-mist">
          By <AuthorName author={a.author} />
          {withTroupe && a.troupe && (
            <>
              {" "}
              of <TroupeName troupe={a.troupe} />
            </>
          )}
          , <time dateTime={a.published_at}>{dates.date(a.published_at)}</time>
        </p>
        {a.tags.length > 0 && (
          <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {a.tags.map((t) => (
              <Link key={t.slug} to={`/blog/tags/${t.slug}`} className="text-gold hover:underline">
                {t.name}
              </Link>
            ))}
          </p>
        )}
      </div>
    </li>
  );
}

/** The blog's tags that have articles, as links to each one's page; the tag open now is marked. */
function TagFilter({ open }: { open?: string }) {
  const tags = useQuery({ queryKey: ["blog-public", "tags"], queryFn: () => unwrap(api.GET("/api/blog/public/tags")) });
  const shown = (tags.data ?? []).filter((t) => t.articles > 0 || t.slug === open);
  if (shown.length === 0) return null;
  const chip = (here: boolean) => `inline-flex min-h-8 items-center rounded-full border px-3 text-sm ${here ? "border-gold bg-gold/10 text-gold" : "border-ash text-parchment hover:border-mist"}`;
  return (
    <nav aria-label="Tags" className="mb-6">
      <ul className="flex flex-wrap gap-2">
        <li>
          <Link to="/blog" className={chip(!open)} aria-current={!open ? "page" : undefined}>
            All
          </Link>
        </li>
        {shown.map((t) => (
          <li key={t.slug}>
            <Link to={`/blog/tags/${t.slug}`} className={chip(t.slug === open)} aria-current={t.slug === open ? "page" : undefined}>
              {t.name}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** A page of articles, newest first, with Previous and Next. `none` says there are none at all. */
export function ArticleList({ found, onPage, none = "No articles yet." }: { found: BlogPublicPageOut; onPage: (page: number) => void; none?: string }) {
  if (found.total === 0) return <Empty>{none}</Empty>;
  if (found.articles.length === 0) return <Empty>There are no more articles. Go back a page.</Empty>;
  return (
    <div className="flex flex-col gap-4">
      <ul aria-label="Articles" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {found.articles.map((a) => (
          <ArticleCard key={a.slug} article={a} />
        ))}
      </ul>
      <Pager label="Pages of articles" page={found.page} size={PAGE_SIZE} shown={found.articles.length} total={found.total} onPage={onPage} />
    </div>
  );
}

/** Where a feed reader follows the blog, or one tag of it (#1162). */
export function feedPath(tag?: string): string {
  return tag ? `/blog/tags/${encodeURIComponent(tag)}/feed.xml` : "/blog/feed.xml";
}

/**
 * The blog's feed, or the tag's, for a feed reader. A plain link, as the API answers
 * it rather than the app: the router would take it for an article.
 */
function FeedLink({ tag }: { tag?: string }) {
  return (
    <a href={feedPath(tag)} type="application/atom+xml" className="text-sm text-gold underline hover:text-parchment">
      {tag ? "Follow this tag by feed" : "Follow by feed"}
    </a>
  );
}

/**
 * The game developer blog (#1158), for anyone, signed in or not: articles newest first
 * a page at a time, the featured ones across the top of the first page, and its tags to
 * filter by. At /blog/tags/<tag>, that tag's articles; at a merged tag's old address, the
 * API answers with the tag it was merged into, and the page moves to that tag's (#1184).
 */
export function BlogPage() {
  const { tag } = useParams();
  const [params, setParams] = useSearchParams();
  const page = pageFrom(params);
  useTitle("Blog");
  const found = useQuery({
    queryKey: ["blog-public", "articles", tag ?? null, page],
    queryFn: (): Promise<BlogPublicPageOut & { tag?: BlogTagOut }> =>
      tag
        ? unwrap(api.GET("/api/blog/public/tags/{slug}", { params: { path: { slug: tag }, query: { page } } }))
        : unwrap(api.GET("/api/blog/public/articles", { params: { query: { page } } })),
    placeholderData: keepPreviousData,
    retry: false,
  });
  const onPage = (n: number) => {
    setParams(n === 1 ? {} : { page: String(n) });
    window.scrollTo({ top: 0 });
  };
  const tagName = found.data?.tag?.name;
  // Not while the last tag's page stands in for this one's.
  const movedTo = tag && !found.isPlaceholderData && found.data?.tag && found.data.tag.slug !== tag ? found.data.tag.slug : null;

  if (movedTo) return <Navigate replace to={{ pathname: `/blog/tags/${encodeURIComponent(movedTo)}`, search: params.toString() }} />;
  if (found.error) {
    const missing = found.error instanceof ApiError && found.error.status === 404;
    return (
      <>
        <PageTitle>{tag ? "No such tag" : "Blog"}</PageTitle>
        {missing ? (
          <p className="text-mist">
            The blog has no tag at this address. <Link to="/blog" className="text-gold underline">See every article</Link>
          </p>
        ) : (
          <ErrorText error={found.error} />
        )}
      </>
    );
  }
  const featured = !tag && page === 1 ? (found.data?.featured ?? []) : [];

  return (
    <>
      <PageTitle
        subtitle={tag ? "Articles with this tag, newest first." : "Essays by the staff of troupes on Horatio: on playing, running a game, and the tricks of both."}
        actions={<FeedLink tag={tag} />}
      >
        {tag ? (tagName ?? "Tag") : "Blog"}
      </PageTitle>
      <TagFilter open={tag} />
      {found.isPending ? (
        <Loading />
      ) : (
        <>
          {featured.length > 0 && (
            <section aria-labelledby="featured" className="mb-8">
              <h2 id="featured" className="mb-3 text-lg text-gold">
                Featured
              </h2>
              <ul className="grid gap-4 md:grid-cols-3">
                {featured.map((a) => (
                  <ArticleCard key={a.slug} article={a} wide />
                ))}
              </ul>
            </section>
          )}
          <section aria-labelledby="latest">
            <h2 id="latest" className={featured.length > 0 ? "mb-3 text-lg text-gold" : "sr-only"}>
              {tag ? `Tagged ${tagName ?? ""}` : "Latest"}
            </h2>
            <ArticleList found={found.data} onPage={onPage} />
          </section>
        </>
      )}
    </>
  );
}

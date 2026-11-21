import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router";
import { api, ApiError, unwrap } from "../../api/client";
import type { BlogPublicPageOut, BlogPublicSummaryOut, BlogPublicTagOut } from "../../api/types";
import { Pager } from "../../components/Pager";
import { Badge, Empty, ErrorText, Loading, PageTitle } from "../../components/ui";
import { useTitle } from "../../title";
import { AuthorName, Dateline } from "./BlogArticleView";

// As many as the API puts on a page (blog_public.PAGE_SIZE).
export const PAGE_SIZE = 12;

/** The page asked for in the address (?page=2), counting from 1. */
export function pageFrom(params: URLSearchParams): number {
  const n = Number(params.get("page"));
  return Number.isInteger(n) && n >= 1 ? n : 1;
}

/** An article in a list: its picture, title, summary, author, date and tags. */
export function ArticleCard({ article: a, wide = false }: { article: BlogPublicSummaryOut; wide?: boolean }) {
  return (
    <li aria-label={a.title} className="flex min-w-0 flex-col overflow-hidden rounded-lg border border-ash bg-night">
      {a.picture && <img src={`${a.picture}/600.webp`} alt="" loading="lazy" className="aspect-[16/9] w-full object-cover" />}
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
          By <AuthorName author={a.author} />, <Dateline publishedAt={a.published_at} />
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

/** A page of articles, newest first, with Previous and Next. */
function Articles({ found, onPage }: { found: BlogPublicPageOut; onPage: (page: number) => void }) {
  if (found.total === 0) return <Empty>No articles yet.</Empty>;
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

/**
 * The game developer blog (#1158), for anyone, signed in or not: articles newest first
 * a page at a time, the featured ones across the top of the first page, and its tags to
 * filter by. At /blog/tags/<tag>, that tag's articles.
 */
export function BlogPage() {
  const { tag } = useParams();
  const [params, setParams] = useSearchParams();
  const page = pageFrom(params);
  useTitle("Blog");
  const found = useQuery({
    queryKey: ["blog-public", "articles", tag ?? null, page],
    queryFn: (): Promise<BlogPublicPageOut & { tag?: BlogPublicTagOut }> =>
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
      <PageTitle subtitle={tag ? "Articles with this tag, newest first." : "Essays by the staff of troupes on Horatio: on playing, running a game, and the tricks of both."}>{tag ? (tagName ?? "Tag") : "Blog"}</PageTitle>
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
            <Articles found={found.data} onPage={onPage} />
          </section>
        </>
      )}
    </>
  );
}

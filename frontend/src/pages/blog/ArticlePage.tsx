import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, ApiError, unwrap } from "../../api/client";
import { AuthorCard } from "../../components/AuthorCard";
import { BackLink } from "../../components/BackLink";
import { ErrorText, Loading, PageTitle } from "../../components/ui";
import { useTitle } from "../../title";
import { BlogArticleView } from "./BlogArticleView";

/**
 * One of the blog's articles at its own address, /blog/<slug> (#1158), for anyone,
 * signed in or not. Only a published one: anything else is "no such article". It is
 * drawn as the writing page's preview draws it (BlogArticleView), with its author's
 * card under it. No comments, ever (#1155).
 */
export function ArticlePage() {
  const { slug = "" } = useParams();
  const article = useQuery({
    queryKey: ["blog-public", "article", slug],
    queryFn: () => unwrap(api.GET("/api/blog/public/articles/{slug}", { params: { path: { slug } } })),
    retry: false,
  });
  // "<Its title> · Blog · Horatio": the article draws its own heading, not a PageTitle.
  useTitle(article.data ? `${article.data.title} · Blog` : "Blog");

  const back = <BackLink to="/blog" label="Blog" className="self-start" />;
  if (article.isPending) return <Loading />;
  if (article.error) {
    const missing = article.error instanceof ApiError && article.error.status === 404;
    return (
      <div className="flex flex-col gap-2">
        {back}
        <PageTitle>No such article</PageTitle>
        {missing ? <p className="text-mist">The blog has no article at this address: the link may be wrong, or the article may have been taken down.</p> : <ErrorText error={article.error} />}
      </div>
    );
  }
  const a = article.data;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-x-4">
        {back}
        {a.edit && (
          <Link to={a.edit} className="text-sm text-gold underline">
            Change it
          </Link>
        )}
      </div>
      <BlogArticleView
        article={{ ...a, author_name: a.author.name }}
        tagLink={(t) => `/blog/tags/${t.slug}`}
        author={a.author_card && <AuthorCard author={a.author_card} linked />}
      />
    </div>
  );
}

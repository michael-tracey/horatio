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
 * signed in or not. Only a published one: anything else is "no such article". No
 * comments, ever (#1155).
 */
export function ArticlePage() {
  const { slug = "" } = useParams();
  useTitle("Blog");
  const article = useQuery({
    queryKey: ["blog-public", "article", slug],
    queryFn: () => unwrap(api.GET("/api/blog/public/articles/{slug}", { params: { path: { slug } } })),
    retry: false,
  });

  const back = <BackLink to="/blog" label="Blog" className="mb-2 self-start" />;
  if (article.isPending) return <Loading />;
  if (article.error) {
    const missing = article.error instanceof ApiError && article.error.status === 404;
    return (
      <div className="flex flex-col">
        {back}
        <PageTitle>No such article</PageTitle>
        {missing ? <p className="text-mist">The blog has no article at this address: the link may be wrong, or the article may have been taken down.</p> : <ErrorText error={article.error} />}
      </div>
    );
  }
  const a = article.data;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col">
      {back}
      <BlogArticleView
        article={a}
        actions={
          a.edit && (
            <Link to={a.edit} className="text-sm text-gold underline">
              Change it
            </Link>
          )
        }
        authorCard={a.author_card && <AuthorCard author={a.author_card} linked />}
      />
    </div>
  );
}

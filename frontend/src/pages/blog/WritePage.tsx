import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { BlogArticleOut, BlogWriterOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, PageTitle, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { ACCEPT } from "../news/PostForm";
import { statusText, working } from "./blog";

const RichEditor = lazy(() => import("../character/RichEditor"));

const MINE = ["blog-mine"];

/**
 * Writing for the blog (#1156), plainly: a member of staff's own articles, and one to
 * write, send to the custodian, withdraw, or change once published. Deleting a draft
 * is in the API, and comes to this page with #1157. The fuller writing
 * page, with a guide, is #1157.
 */
export function WritePage() {
  const { articleId } = useParams();
  const writer = useQuery({ queryKey: ["blog-writer"], queryFn: () => unwrap(api.GET("/api/blog/writer")) });
  const mine = useQuery({ queryKey: MINE, queryFn: () => unwrap(api.GET("/api/blog/articles/mine")) });
  if (writer.isPending || mine.isPending) return <Loading />;
  if (!writer.data || !mine.data) return <ErrorText error={writer.error ?? mine.error} />;
  const article = articleId ? mine.data.find((a) => a.id === articleId) : undefined;

  return (
    <>
      <PageTitle subtitle="Articles on playing and running a game, for everyone who uses Horatio. The custodian reads each one before it goes up.">Write for the blog</PageTitle>
      <div className="flex flex-col gap-6">
        <Card title="Your articles" actions={writer.data.can_write && articleId ? <Link to="/blog/write" className="text-sm text-gold hover:underline">New article</Link> : undefined}>
          {mine.data.length ? (
            <ul className="divide-y divide-ash text-sm">
              {mine.data.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <Link to={`/blog/write/${a.id}`} className="text-gold hover:underline">
                    {working(a).title}
                  </Link>
                  <Badge tone={a.status === "published" ? "gold" : "mist"}>{statusText(a)}</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>You haven't written an article yet.</Empty>
          )}
        </Card>
        {articleId && !article ? (
          <Empty>No such article.</Empty>
        ) : writer.data.can_write || article ? (
          <ArticleForm key={article?.id ?? "new"} article={article} writer={writer.data} />
        ) : (
          <Empty>Only the staff of a troupe that is running can write for the blog.</Empty>
        )}
      </div>
    </>
  );
}

function ArticleForm({ article, writer }: { article?: BlogArticleOut; writer: BlogWriterOut }) {
  const navigate = useNavigate();
  const words = article ? working(article) : undefined;
  const [title, setTitle] = useState(words?.title ?? "");
  const [summary, setSummary] = useState(words?.summary ?? "");
  const [body, setBody] = useState(words?.body ?? "");
  const [troupeId, setTroupeId] = useState(words?.troupe?.id ?? writer.troupes[0]?.id ?? "");
  const file = useRef<HTMLInputElement>(null);
  const fields = { title, summary, body, troupe_id: troupeId || null };
  const path = { params: { path: { article_id: article?.id ?? "" } } };
  const save = useAction(async () => {
    if (!article) {
      const made = await unwrap(api.POST("/api/blog/articles", { body: fields }));
      void navigate(`/blog/write/${made.id}`);
      return made;
    }
    return unwrap(api.PUT("/api/blog/articles/{article_id}", { ...path, body: fields }));
  }, [MINE]);
  const submit = useAction(async () => {
    await unwrap(api.PUT("/api/blog/articles/{article_id}", { ...path, body: fields }));
    return unwrap(api.POST("/api/blog/articles/{article_id}/submit", path));
  }, [MINE]);
  const withdraw = useAction(() => unwrap(api.POST("/api/blog/articles/{article_id}/withdraw", path)), [MINE]);
  const discard = useAction(() => unwrap(api.DELETE("/api/blog/articles/{article_id}/revision", path)), [MINE]);
  const picture = useAction(async (chosen: File) => {
    const form = new FormData();
    form.append("file", chosen);
    return unwrap(api.POST("/api/blog/articles/{article_id}/picture", { ...path, body: form as never, bodySerializer: (b: unknown) => b as FormData }));
  }, [MINE]);
  const busy = [save, submit, withdraw, discard, picture].some((a) => a.isPending);
  const waits = article?.waiting != null;
  const troupes = [...writer.troupes];
  if (words?.troupe && !troupes.some((t) => t.id === words.troupe?.id)) troupes.push(words.troupe);

  return (
    <Card title={article ? working(article).title : "New article"}>
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        {article && <p className="text-sm text-mist">{statusText(article)}. Its address: /blog/{article.slug}</p>}
        {article?.note && (
          <p className="border-l-2 border-gold pl-3 text-sm whitespace-pre-line">
            <span className="text-mist">{article.status === "unpublished" ? "Why the custodian unpublished it: " : "The custodian's note: "}</span>
            {article.note}
          </p>
        )}
        {article?.status === "published" && <p className="text-sm text-mist">It stays on the blog as it is while you change it. Send your changes, and the custodian puts them up.</p>}
        <fieldset disabled={waits || busy} className="flex flex-col gap-3">
          <Field label="Title">
            <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label="Summary" hint="A line or two for lists and links.">
            <Textarea rows={2} value={summary} maxLength={500} onChange={(e) => setSummary(e.target.value)} />
          </Field>
          <Field label="Troupe" hint="The troupe you run that the article names, if any.">
            <Select value={troupeId} onChange={(e) => setTroupeId(e.target.value)}>
              <option value="">None</option>
              {troupes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
          <Suspense fallback={<Loading />}>
            <RichEditor initial={body} onChange={setBody} label="Article" placeholder="Write your article here…" />
          </Suspense>
        </fieldset>
        {article && !waits && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {words?.picture && <img src={`${words.picture}/600.webp`} alt="The article's picture" className="max-h-32 rounded-md" />}
            <input ref={file} type="file" accept={ACCEPT} className="sr-only" aria-label="Choose a picture" onChange={(e) => e.target.files?.[0] && picture.mutate(e.target.files[0])} />
            <Button type="button" variant="secondary" disabled={busy} onClick={() => file.current?.click()}>
              {words?.picture ? "Change the picture" : "Add a picture"}
            </Button>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          {!waits && (
            <>
              <Button type="submit" variant="secondary" disabled={busy || !title.trim()}>
                {article ? "Save" : "Save draft"}
              </Button>
              {article && (
                <Button type="button" disabled={busy || !title.trim()} onClick={() => submit.mutate(undefined)}>
                  {article.status === "published" ? "Send the changes to the custodian" : "Send to the custodian"}
                </Button>
              )}
            </>
          )}
          {waits && (
            <Button type="button" variant="secondary" disabled={busy} onClick={() => withdraw.mutate(undefined)}>
              Withdraw
            </Button>
          )}
          {article?.status === "published" && article.revision && !waits && (
            <Button type="button" variant="ghost" disabled={busy} onClick={() => discard.mutate(undefined)}>
              Throw away the changes
            </Button>
          )}
        </div>
        <ErrorText error={save.error ?? submit.error ?? withdraw.error ?? discard.error ?? picture.error} />
      </form>
    </Card>
  );
}

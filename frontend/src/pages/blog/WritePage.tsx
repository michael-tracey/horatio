import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { BlogArticleOut, BlogTagOut, BlogTroupeOut, BlogWriterOut, MyAuthor } from "../../api/types";
import { AuthorCard } from "../../components/AuthorCard";
import { BackLink } from "../../components/BackLink";
import { useConfirm } from "../../components/ConfirmDialog";
import type { Crop } from "../../components/crop";
import { LinkButton } from "../../components/LinkButton";
import { Segmented } from "../../components/Segmented";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, PageTitle, Select, Textarea } from "../../components/ui";
import { useDates, type Dates } from "../../dates";
import { useAction, useLeaveWarning, useMe } from "../../hooks";
import { manualLink } from "../../manualLink";
import { BlogArticleView } from "./BlogArticleView";
import { BodyPictureForm, pictureTool, type Placing } from "./BodyPicture";
import { deletable, standing, statusText, taggable, toggled, troupeLinked, withRetired, working } from "./blog";
import { HeroPicture } from "./HeroPicture";
import { TagChips } from "./TagChips";
import { useWriter } from "./writer";

const RichEditor = lazy(() => import("../character/RichEditor"));

const MINE = ["blog-mine"];

const GUIDE = (
  <Link to={manualLink("blog")} className="text-gold underline hover:text-parchment">
    the writing guide
  </Link>
);

/**
 * Write for the blog (#1157): at /blog/write, the member of staff's own articles,
 * each with where it stands; at /blog/write/new and /blog/write/:id, one article to
 * write, preview as the blog will show it, and submit to the custodian, withdraw,
 * change once published, or delete while it has never been published. A troupe's
 * Overview links to /blog/write/new?troupe=<id>, to name that troupe.
 */
export function WritePage() {
  const { articleId } = useParams();
  const writer = useWriter();
  const mine = useQuery({ queryKey: MINE, queryFn: () => unwrap(api.GET("/api/blog/articles/mine")) });
  const tags = useQuery({ queryKey: ["blog-tags"], queryFn: () => unwrap(api.GET("/api/blog/tags")) });
  // Their author profile (#1159), under the article in the preview; or a way to set it up.
  const author = useQuery({ queryKey: ["blog-author"], queryFn: () => unwrap(api.GET("/api/blog/author")) });
  if (writer.isPending || mine.isPending) return <Loading />;
  if (!writer.data || !mine.data) return <ErrorText error={writer.error ?? mine.error} />;
  if (!articleId) return <MyArticles articles={mine.data} canWrite={writer.data.can_write} author={author.data} />;

  const article = articleId === "new" ? undefined : mine.data.find((a) => a.id === articleId);
  const back = <BackLink to="/blog/write" label="Your articles" className="self-start" />;
  const missing = articleId !== "new" && !article ? "No such article." : !article && !writer.data.can_write ? "Only the staff of a troupe that is running can write for the blog." : null;
  return (
    <div className="flex flex-col gap-2">
      {back}
      {missing ? <Empty>{missing}</Empty> : <ArticleEditor key={article?.id ?? "new"} article={article} writer={writer.data} tags={tags.data ?? []} author={author.data} />}
    </div>
  );
}

/** The writer's own articles, the latest changed first: each one's title, where it stands, its dates and the custodian's note. */
function MyArticles({ articles, canWrite, author }: { articles: BlogArticleOut[]; canWrite: boolean; author: MyAuthor | undefined }) {
  const dates = useDates();
  return (
    <>
      <PageTitle
        subtitle={<>Articles on playing and running a game, for everyone who uses Horatio. The custodian reads each one before it goes up. Before you start, read {GUIDE}.</>}
        actions={canWrite && <LinkButton to="/blog/write/new">Write an article</LinkButton>}
      >
        Write for the blog
      </PageTitle>
      {canWrite && <NoAuthor author={author} className="mb-4" />}
      <Card title="Your articles">
        {articles.length ? (
          <ul className="divide-y divide-ash">
            {articles.map((a) => (
              <ArticleLine key={a.id} article={a} dates={dates} />
            ))}
          </ul>
        ) : (
          <Empty>{canWrite ? "You haven't written an article yet." : "Only the staff of a troupe that is running can write for the blog."}</Empty>
        )}
      </Card>
    </>
  );
}

function ArticleLine({ article: a, dates }: { article: BlogArticleOut; dates: Dates }) {
  const words = working(a);
  const when = [
    `started ${dates.date(a.created_at)}`,
    a.status === "submitted" && a.submitted_at && `submitted ${dates.date(a.submitted_at)}`,
    a.published_at && `published ${dates.date(a.published_at)}`,
    a.revised_at && `changed ${dates.date(a.revised_at)}`,
    a.revision?.submitted_at && `changes proposed ${dates.date(a.revision.submitted_at)}`,
    a.status === "unpublished" && a.unpublished_at && `unpublished ${dates.date(a.unpublished_at)}`,
  ]
    .filter(Boolean)
    .join(" · ");
  const { note } = standing(a, dates.date);
  return (
    <li aria-label={words.title} className="flex min-w-0 flex-col gap-1 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Link to={`/blog/write/${a.id}`} className="min-w-0 break-words text-gold hover:underline">
          {words.title}
        </Link>
        <Badge tone={note ? "blood" : a.status === "published" ? "gold" : "mist"}>{statusText(a)}</Badge>
      </div>
      <p className="text-xs text-mist">
        {when.charAt(0).toUpperCase() + when.slice(1)}
        {words.troupe && <> · {words.troupe.name}</>}
      </p>
      {note && (
        <p className="border-l-2 border-gold pl-3 text-sm break-words whitespace-pre-line">
          <span className="text-mist">{note.label}: </span>
          {note.text}
        </p>
      )}
    </li>
  );
}

/** Set up your author profile: said once it is known they have none. */
function NoAuthor({ author, className = "" }: { author: MyAuthor | undefined; className?: string }) {
  if (!author || author.saved) return null;
  return (
    <p className={`text-sm text-mist ${className}`}>
      Your articles show a card about you under them.{" "}
      <Link to="/account/blog" className="text-gold underline hover:text-parchment">
        Set up your author profile
      </Link>{" "}
      to give it your picture and a few words about you.
    </p>
  );
}

type Fields = { title: string; summary: string; body: string; troupeId: string; tagIds: string[] };

function fieldsOf(article: BlogArticleOut | undefined, troupeId: string): Fields {
  const words = article && working(article);
  return {
    title: words?.title ?? "",
    summary: words?.summary ?? "",
    body: words?.body ?? "",
    troupeId: article ? (words?.troupe?.id ?? "") : troupeId,
    tagIds: article?.tags.map((t) => t.id) ?? [],
  };
}

const sameTags = (a: string[], b: string[]) => a.length === b.length && a.every((id) => b.includes(id));
const same = (a: Fields, b: Fields) => a.title === b.title && a.summary === b.summary && a.body === b.body && a.troupeId === b.troupeId && sameTags(a.tagIds, b.tagIds);

/** One article to write: its fields, or a preview of it as the blog will show it, where it stands, and what its author can do with it now. */
function ArticleEditor({ article, writer, tags, author }: { article?: BlogArticleOut; writer: BlogWriterOut; tags: BlogTagOut[]; author: MyAuthor | undefined }) {
  const navigate = useNavigate();
  const me = useMe();
  const dates = useDates();
  const [search] = useSearchParams();
  const asked = search.get("troupe");
  const startTroupe = writer.troupes.find((t) => t.id === asked)?.id ?? writer.troupes[0]?.id ?? "";
  const [saved, setSaved] = useState(() => fieldsOf(article, startTroupe));
  const [form, setForm] = useState(saved);
  const set = (change: Partial<Fields>) => setForm((f) => ({ ...f, ...change }));
  // The editor starts again from the words when they are put back (changes thrown away).
  const [editorKey, setEditorKey] = useState(0);
  const [mode, setMode] = useState<"write" | "preview">("write");
  // Adding a picture to the words, or changing what one says (#1163).
  const [placing, setPlacing] = useState<Placing | null>(null);
  const [goTo, setGoTo] = useState<string | null>(null);
  const [confirmed, confirming] = useConfirm();
  const client = useQueryClient();
  const dirty = !same(form, saved);
  useLeaveWarning(dirty, { inApp: true });
  // Leaving once saved (a new article to its own page, a deleted one to the list)
  // waits until the form is no longer marked unsaved.
  useEffect(() => {
    if (!goTo) return;
    void navigate(goTo, { replace: true });
    void client.invalidateQueries({ queryKey: MINE });
  }, [goTo, navigate, client]);

  const words = article && working(article);
  const waiting = article?.status === "submitted" || article?.waiting === "changes";
  const published = article?.status === "published";
  const ownTags = taggable(article);
  const body = { title: form.title, summary: form.summary, body: form.body, troupe_id: form.troupeId || null };

  /** Save the fields, and its tags while they are its author's, as a new article or onto this one. */
  const write = async (): Promise<BlogArticleOut> => {
    let done = article
      ? await unwrap(api.PUT("/api/blog/articles/{article_id}", { params: { path: { article_id: article.id } }, body }))
      : await unwrap(api.POST("/api/blog/articles", { body }));
    if (ownTags && !sameTags(form.tagIds, done.tags.map((t) => t.id)))
      done = await unwrap(api.PUT("/api/blog/articles/{article_id}/tags", { params: { path: { article_id: done.id } }, body: { tag_ids: form.tagIds } }));
    return done;
  };
  /** The form as the server kept it (the title and summary trimmed), and a new article's own page. */
  const keep = (done: BlogArticleOut) => {
    const kept = { ...fieldsOf(done, ""), body: form.body };
    setSaved(kept);
    setForm(kept);
    if (!article) setGoTo(`/blog/write/${done.id}`);
  };
  const path = { params: { path: { article_id: article?.id ?? "" } } };
  const save = useAction(write, [MINE]);
  const submit = useAction(async () => {
    const done = await write();
    return unwrap(api.POST("/api/blog/articles/{article_id}/submit", { params: { path: { article_id: done.id } } }));
  }, [MINE]);
  const withdraw = useAction(() => unwrap(api.POST("/api/blog/articles/{article_id}/withdraw", path)), [MINE]);
  const discard = useAction(() => unwrap(api.DELETE("/api/blog/articles/{article_id}/revision", path)), [MINE]);
  // Not a useAction: the list is asked again only once this page has gone, which it would otherwise leave with "No such article".
  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/blog/articles/{article_id}", path)),
    onSuccess: () => {
      setSaved(form);
      setGoTo("/blog/write");
    },
  });
  const picture = useAction(async ({ file, crop }: { file: File; crop: Crop | null }) => {
    const sent = new FormData();
    sent.append("file", file);
    if (crop) {
      sent.append("crop_x", String(crop.x));
      sent.append("crop_y", String(crop.y));
      sent.append("crop_size", String(crop.size));
    }
    // The form goes as it is: multipart, with the browser's own boundary.
    return unwrap(api.POST("/api/blog/articles/{article_id}/picture", { ...path, body: sent as never, bodySerializer: (b: unknown) => b as FormData }));
  }, [MINE]);
  const unpicture = useAction(() => unwrap(api.DELETE("/api/blog/articles/{article_id}/picture", path)), [MINE]);
  const busy = [save, submit, withdraw, discard, remove, picture, unpicture].some((a) => a.isPending);

  const troupes: BlogTroupeOut[] = [...writer.troupes];
  if (words?.troupe && !troupes.some((t) => t.id === words.troupe?.id)) troupes.push(words.troupe);
  const troupe = troupes.find((t) => t.id === form.troupeId) ?? null;
  const where = standing(article, dates.date);
  // A published article with nothing changed has nothing to propose.
  const unchanged = published && !article?.revision && !dirty;
  const written = !!form.title.trim() && !!form.body.trim();

  return (
    <>
      <PageTitle subtitle={<>The custodian reads each article before it goes on the blog, where anyone can read it. Before you start, read {GUIDE}.</>}>Write for the blog</PageTitle>
      {confirming}
      <div className="flex flex-col gap-4">
        <section aria-label="Where it stands" className="flex flex-col gap-1 rounded-lg border border-ash bg-dusk p-4 text-sm">
          <p className="text-parchment">{where.where}</p>
          <p className="text-mist">{where.next}</p>
          {where.note && (
            <p className="mt-1 border-l-2 border-gold pl-3 break-words whitespace-pre-line">
              <span className="text-mist">{where.note.label}: </span>
              {where.note.text}
            </p>
          )}
          {article && <p className="text-xs break-all text-mist">Its address: /blog/{article.slug}</p>}
        </section>

        <Segmented
          label="Show"
          value={mode}
          onChange={setMode}
          options={[
            { value: "write", label: "Write" },
            { value: "preview", label: "Preview" },
          ]}
          className="self-start"
        />

        {mode === "preview" && (
          <div className="flex min-w-0 flex-col gap-4">
            <p role="note" className="rounded-md border border-dashed border-gold/60 bg-gold/5 px-3 py-2 text-sm text-gold">
              Preview: the article as the blog will show it. Nobody else sees it until the custodian publishes it.
            </p>
            <BlogArticleView
              heading="h2"
              article={{
                title: form.title,
                summary: form.summary,
                body: form.body,
                picture: words?.picture ?? null,
                author_name: author?.saved ? author.display_name : (article?.author_name ?? me.data?.display_name ?? ""),
                troupe,
                tags: withRetired(tags, article?.tags)
                  .map(({ tag }) => tag)
                  .filter((t) => form.tagIds.includes(t.id)),
                published_at: article?.published_at ?? null,
                revised_at: article?.revised_at ?? null,
              }}
              author={author?.saved ? <AuthorCard author={author} /> : <NoAuthor author={author} />}
            />
          </div>
        )}

        <div className={mode === "write" ? "flex min-w-0 flex-col gap-4" : "hidden"}>
          <Card>
            <fieldset disabled={waiting || busy} className="flex min-w-0 flex-col gap-4">
              <legend className="sr-only">The article</legend>
              {published && <p className="text-sm text-mist">It stays on the blog as it is while you change it here. The custodian puts your changes up once you propose them.</p>}
              <Field label="Title">
                <Input value={form.title} maxLength={200} onChange={(e) => set({ title: e.target.value })} />
              </Field>
              <Field label="Summary" hint="A line or two, under the title and wherever the article is listed.">
                <Textarea rows={2} value={form.summary} maxLength={500} onChange={(e) => set({ summary: e.target.value })} />
              </Field>
              <Field
                label="Troupe"
                hint={
                  <>
                    The troupe you're on the staff of that the article names, if any. Readers can follow its name to the troupe's public profile; a private or archived troupe shows its name only.
                    {troupe && !troupeLinked(troupe) && <> {troupe.name} {troupe.archived ? "is archived" : "isn't public"}, so the blog will show its name only.</>}
                  </>
                }
              >
                <Select value={form.troupeId} onChange={(e) => set({ troupeId: e.target.value })}>
                  <option value="">None</option>
                  {troupes.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </fieldset>
          </Card>

          <Card title="Picture">
            {article ? (
              <HeroPicture
                picture={words?.picture ?? null}
                disabled={waiting}
                saving={picture.isPending || unpicture.isPending}
                error={picture.error ?? unpicture.error}
                onUpload={(file, crop, done) => picture.mutate({ file, crop }, { onSuccess: done })}
                onRemove={() => unpicture.mutate(undefined)}
              />
            ) : (
              <p className="text-sm text-mist">Save it as a draft first, then add a picture to go across the top of it.</p>
            )}
            <p className="mt-2 text-xs text-mist">A JPEG, PNG, WebP or HEIC picture up to 10 MB, cut twice as wide as it is high. Only a picture you made or may share: never one from the books.</p>
          </Card>

          <Card title="Tags">
            {ownTags ? (
              <div className="flex flex-col gap-2">
                <p className="text-sm text-mist">What it is about, from the custodian's list. They may change them before it goes up.</p>
                <TagChips tags={tags} had={article?.tags} chosen={form.tagIds} disabled={waiting || busy} onToggle={(id) => set({ tagIds: toggled(form.tagIds, id) })} />
              </div>
            ) : (
              <div className="flex flex-col gap-2 text-sm">
                <p className="text-mist">The custodian tags it once it is submitted.</p>
                {article && article.tags.length > 0 && (
                  <ul aria-label="Tags" className="flex flex-wrap gap-2">
                    {article.tags.map((t) => (
                      <li key={t.id}>
                        <Badge>{t.name}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </Card>

          <fieldset disabled={waiting || busy} className="min-w-0">
            <legend className="sr-only">Its words</legend>
            <Suspense fallback={<Loading />}>
              <RichEditor
                key={editorKey}
                initial={form.body}
                onChange={(b) => set({ body: b })}
                label="Article"
                placeholder="Write your article here…"
                pictures
                moreTools={(editor) => [pictureTool(editor, placing !== null, setPlacing)]}
                panel={placing && <BodyPictureForm key={placing.chosen ? "change" : "add"} articleId={article?.id} placing={placing} onDone={() => setPlacing(null)} />}
              />
            </Suspense>
          </fieldset>
        </div>

        <div className="flex flex-wrap gap-2">
          {!waiting && (
            <>
              <Button type="button" disabled={busy || !written || unchanged} onClick={() => submit.mutate(undefined, { onSuccess: keep })}>
                {published ? "Propose the changes" : "Submit to the custodian"}
              </Button>
              <Button type="button" variant="secondary" disabled={busy || !form.title.trim() || (!!article && !dirty)} onClick={() => save.mutate(undefined, { onSuccess: keep })}>
                {published ? "Save the changes" : "Save draft"}
              </Button>
            </>
          )}
          {waiting && (
            <Button type="button" variant="secondary" disabled={busy} onClick={() => withdraw.mutate(undefined)}>
              {article?.waiting === "changes" ? "Withdraw the changes" : "Withdraw"}
            </Button>
          )}
          {published && article?.revision && !waiting && (
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={async () => {
                if (!(await confirmed({ title: "Throw away your changes?", body: "The article stays on the blog as it is now, and your changes are lost.", action: "Throw them away" }))) return;
                discard.mutate(undefined, {
                  onSuccess: (done) => {
                    const back = fieldsOf(done, "");
                    setSaved(back);
                    setForm(back);
                    setEditorKey((k) => k + 1);
                    setPlacing(null);
                  },
                });
              }}
            >
              Throw away the changes
            </Button>
          )}
          {article && deletable(article) && (
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={async () => {
                if (!(await confirmed({ title: "Delete this article?", body: "It has never been published. Once deleted, it can't be brought back.", action: "Delete" }))) return;
                remove.mutate();
              }}
            >
              Delete the draft
            </Button>
          )}
        </div>
        {unchanged && !waiting && <p className="text-xs text-mist">Change something above, and you can propose it to the custodian.</p>}
        <ErrorText error={save.error ?? submit.error ?? withdraw.error ?? discard.error ?? remove.error} />
      </div>
    </>
  );
}

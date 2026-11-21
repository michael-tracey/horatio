import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { api, unwrap } from "../../api/client";
import type { BlogArticleOut, BlogTagOut } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { toggled, working } from "../blog/blog";

export function useBlogQueue(enabled = true) {
  return useQuery({ queryKey: ["blog-queue"], queryFn: () => unwrap(api.GET("/api/blog/queue")), enabled });
}

export function useBlogTags() {
  return useQuery({ queryKey: ["blog-tags"], queryFn: () => unwrap(api.GET("/api/blog/tags")) });
}

/**
 * The game developer blog's queue (#1156): articles staff have sent, and changes to
 * published ones, for the custodian to publish or return with a note; then those
 * published, to feature, tag or unpublish, and those unpublished.
 */
export function BlogTab() {
  const queue = useBlogQueue();
  const tags = useBlogTags();
  if (queue.isPending) return <Loading />;
  if (!queue.data) return <ErrorText error={queue.error} />;
  const all = tags.data ?? [];
  const { waiting, published, unpublished } = queue.data;

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-mist">Staff of any troupe write articles for the blog. Nothing is on the blog until you publish it, and the blog's own pages aren't open to readers yet.</p>
      <Card title="Waiting">
        {waiting.length ? (
          <ul className="divide-y divide-ash">
            {waiting.map((a) => (
              <Article key={a.id} article={a} tags={all} waiting>
                <WaitingActions article={a} />
              </Article>
            ))}
          </ul>
        ) : (
          <Empty>Nothing is waiting to be published.</Empty>
        )}
      </Card>
      <Card title="Published">
        {published.length ? (
          <ul className="divide-y divide-ash">
            {published.map((a) => (
              <Article key={a.id} article={a} tags={all}>
                <PublishedActions article={a} />
              </Article>
            ))}
          </ul>
        ) : (
          <Empty>No article is published yet.</Empty>
        )}
      </Card>
      {unpublished.length > 0 && (
        <Card title="Unpublished">
          <ul className="divide-y divide-ash">
            {unpublished.map((a) => (
              <Article key={a.id} article={a} tags={all} />
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

/**
 * One article: what it says (under Waiting, a published one's changes), who wrote it, and its tags.
 * An address ending #article-<id>, as the custodian's bell task links (#1170), opens it to read,
 * under Waiting while it waits there.
 */
function Article({ article: a, tags, waiting = false, children }: { article: BlogArticleOut; tags: BlogTagOut[]; waiting?: boolean; children?: ReactNode }) {
  const dates = useDates();
  const words = waiting ? working(a) : a;
  const { hash } = useLocation();
  const anchor = waiting || !a.waiting ? `article-${a.id}` : undefined;
  const opened = !!anchor && hash === `#${anchor}`;
  const here = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (opened) here.current?.scrollIntoView?.({ block: "start" });
  }, [opened]);
  const when =
    waiting && a.waiting === "changes" && a.revision?.submitted_at
      ? `changes sent ${dates.date(a.revision.submitted_at)}`
      : a.status === "submitted" && a.submitted_at
        ? `sent ${dates.date(a.submitted_at)}`
        : a.status === "unpublished" && a.unpublished_at
          ? `unpublished ${dates.date(a.unpublished_at)}`
          : a.published_at
            ? `published ${dates.date(a.published_at)}`
            : "";
  return (
    <li ref={here} id={anchor} className="flex flex-col gap-2 py-3" aria-label={words.title}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-parchment">
          {words.title}
          {a.featured && (
            <Badge tone="gold" className="ml-2">
              Featured
            </Badge>
          )}
          {a.waiting === "changes" && (
            <Badge tone="mist" className="ml-2">
              {waiting ? "Changes" : "Changes waiting"}
            </Badge>
          )}
        </h3>
        <span className="text-xs text-mist">
          by{" "}
          <Link to={`/players/${a.author_id}`} className="text-gold hover:underline">
            {a.author_name}
          </Link>
          {words.troupe && <> of {words.troupe.name}</>}
          {when && <>, {when}</>}
        </span>
      </div>
      {waiting && a.waiting === "changes" && <p className="text-xs text-mist">Changes to a published article. Publishing them puts them up in place of what readers see now; returning them leaves it as it is.</p>}
      {words.summary && <p className="text-sm">{words.summary}</p>}
      {a.note && (
        <p className="border-l-2 border-ash pl-3 text-sm whitespace-pre-line text-mist">
          {a.status === "unpublished" ? "Why it was unpublished: " : "Your note when you returned it: "}
          {a.note}
        </p>
      )}
      <details className="text-sm" open={opened || undefined}>
        <summary className="cursor-pointer text-mist hover:text-parchment">Read it</summary>
        <div className="mt-2 flex flex-col gap-3">
          {words.picture && <img src={`${words.picture}/600.webp`} alt="" className="max-h-64 w-fit rounded-md" />}
          <Markdown text={words.body} />
        </div>
      </details>
      <Address article={a} />
      <Tags article={a} tags={tags} />
      {children}
    </li>
  );
}

/** Its address on the blog, which the custodian may change until it is first published. */
function Address({ article: a }: { article: BlogArticleOut }) {
  const [slug, setSlug] = useState<string | null>(null);
  const save = useAction(() => unwrap(api.PUT("/api/blog/articles/{article_id}/slug", { params: { path: { article_id: a.id } }, body: { slug: slug ?? "" } })), [["blog-queue"]]);
  if (slug === null) {
    return (
      <p className="text-xs text-mist">
        Address: /blog/{a.slug}
        {!a.slug_fixed && (
          <button type="button" className="ml-2 underline hover:text-parchment" onClick={() => setSlug(a.slug)}>
            Change
          </button>
        )}
      </p>
    );
  }
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: () => setSlug(null) });
      }}
    >
      <Field label="Address" hint="Fixed once it is published, so links to it keep working.">
        <Input value={slug} onChange={(e) => setSlug(e.target.value)} />
      </Field>
      <Button type="submit" variant="secondary" disabled={save.isPending || !slug.trim()}>
        Save address
      </Button>
      <Button type="button" variant="ghost" onClick={() => setSlug(null)}>
        Cancel
      </Button>
      <ErrorText error={save.error} />
    </form>
  );
}

/** Its tags, as chips: choosing one tags it at once, and again untags it. */
function Tags({ article: a, tags }: { article: BlogArticleOut; tags: BlogTagOut[] }) {
  const on = a.tags.map((t) => t.id);
  const save = useAction((ids: string[]) => unwrap(api.PUT("/api/blog/articles/{article_id}/tags", { params: { path: { article_id: a.id } }, body: { tag_ids: ids } })), [["blog-queue"]]);
  if (tags.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <ul aria-label="Tags" className="flex flex-wrap gap-2">
        {tags.map((t) => {
          const chosen = on.includes(t.id);
          return (
            <li key={t.id}>
              <button
                type="button"
                aria-pressed={chosen}
                disabled={save.isPending}
                onClick={() => save.mutate(toggled(on, t.id))}
                className={`min-h-8 rounded-full border px-3 text-sm ${chosen ? "border-gold bg-gold/10 text-gold" : "border-ash text-parchment hover:border-mist"}`}
              >
                {t.name}
              </button>
            </li>
          );
        })}
      </ul>
      <ErrorText error={save.error} />
    </div>
  );
}

/** Publish it, or return it to its author with a note. */
function WaitingActions({ article: a }: { article: BlogArticleOut }) {
  const [returning, setReturning] = useState(false);
  const [note, setNote] = useState("");
  const path = { params: { path: { article_id: a.id } } };
  const publish = useAction(() => unwrap(api.POST("/api/blog/articles/{article_id}/publish", path)), [["blog-queue"]]);
  const send = useAction(() => unwrap(api.POST("/api/blog/articles/{article_id}/return", { ...path, body: { note } })), [["blog-queue"]]);
  const busy = publish.isPending || send.isPending;
  const changes = a.waiting === "changes";

  return (
    <>
      {returning ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send.mutate(undefined);
          }}
        >
          <Field label="Note to the author" hint={`${a.author_name} sees this on their bell, with ${changes ? "the changes" : "the article"} back to work on.`}>
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" variant="secondary" disabled={busy || !note.trim()}>
              Return it
            </Button>
            <Button type="button" variant="ghost" onClick={() => setReturning(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" disabled={busy} onClick={() => publish.mutate(undefined)}>
            {changes ? "Publish the changes" : "Publish"}
          </Button>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => setReturning(true)}>
            Return with a note…
          </Button>
        </div>
      )}
      <ErrorText error={publish.error ?? send.error} />
    </>
  );
}

/** Feature it or stop, or unpublish it with a reason. */
function PublishedActions({ article: a }: { article: BlogArticleOut }) {
  const [unpublishing, setUnpublishing] = useState(false);
  const [reason, setReason] = useState("");
  const path = { params: { path: { article_id: a.id } } };
  const feature = useAction(() => unwrap(api.PUT("/api/blog/articles/{article_id}/featured", { ...path, body: { featured: !a.featured } })), [["blog-queue"]]);
  const unpublish = useAction(() => unwrap(api.POST("/api/blog/articles/{article_id}/unpublish", { ...path, body: { reason } })), [["blog-queue"]]);
  const busy = feature.isPending || unpublish.isPending;

  return (
    <>
      {unpublishing ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            unpublish.mutate(undefined);
          }}
        >
          <Field label="Why unpublish it?" hint={`${a.author_name} sees this on their bell.`}>
            <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" variant="danger" disabled={busy || !reason.trim()}>
              Unpublish
            </Button>
            <Button type="button" variant="ghost" onClick={() => setUnpublishing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="secondary" disabled={busy} onClick={() => feature.mutate(undefined)}>
            {a.featured ? "Stop featuring" : "Feature it"}
          </Button>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => setUnpublishing(true)}>
            Unpublish…
          </Button>
        </div>
      )}
      <ErrorText error={feature.error ?? unpublish.error} />
    </>
  );
}

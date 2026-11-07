import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { PostOut } from "../../api/types";
import { useAction } from "../../hooks";
import { manualLink } from "../../manualLink";
import { Button, Card, Empty, ErrorText, Field, Loading, Select } from "../../components/ui";
import { Desk } from "./Desk";
import { KINDS, type Kind } from "./posts";
import { PostForm, type Action, type Fields } from "./PostForm";
import { olderPosts, postPath, useAgencies, useMarkRead, usePost, usePublished } from "./queries";
import { StoryCard, StoryView } from "./Story";

/**
 * A troupe's posts of one kind (#510), at /troupes/<id>/news: the list everyone in
 * the troupe reads, each post's own page, and for its staff the desk and the editor.
 * `writes`: a storyteller or assistant storyteller; `proposes`: a narrator, who only
 * proposes news.
 */
export function PostsSection({ troupeId, kind, writes, proposes }: { troupeId: string; kind: Kind; writes: boolean; proposes: boolean }) {
  const staff = writes || proposes;
  return (
    <Routes>
      <Route index element={<PostList troupeId={troupeId} kind={kind} writes={writes} proposes={proposes} />} />
      {staff && <Route path="desk" element={<Desk troupeId={troupeId} kind={kind} writes={writes} />} />}
      {staff && <Route path="write" element={<WritePost troupeId={troupeId} kind={kind} writes={writes} />} />}
      {staff && <Route path=":postId/edit" element={<WritePost troupeId={troupeId} kind={kind} writes={writes} />} />}
      <Route path=":postId" element={<PostPage troupeId={troupeId} kind={kind} writes={writes} />} />
    </Routes>
  );
}

/** Everything published, newest first, under each agency's masthead, with a filter by agency. */
function PostList({ troupeId, kind, writes, proposes }: { troupeId: string; kind: Kind; writes: boolean; proposes: boolean }) {
  const words = KINDS[kind];
  const [params, setParams] = useSearchParams();
  const agencyId = params.get("agency") || undefined;
  const agencies = useAgencies(troupeId);
  const list = usePublished(troupeId, kind, agencyId);
  const client = useQueryClient();
  const [older, setOlder] = useState<{ for: string; posts: PostOut[]; more: boolean } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const filter = agencyId ?? "";
  const shownOlder = older?.for === filter ? older : null;
  const posts = [...(list.data?.posts ?? []), ...(shownOlder?.posts ?? [])];
  const more = shownOlder ? shownOlder.more : !!list.data?.older;
  const unread = posts.some((p) => p.unread);

  const showOlder = async () => {
    const last = posts[posts.length - 1];
    if (!last?.published_at) return;
    setLoading(true);
    setError(null);
    try {
      const page = await olderPosts(troupeId, kind, last.published_at, agencyId);
      setOlder({ for: filter, posts: [...(shownOlder?.posts ?? []), ...page.posts], more: page.older });
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  };
  const markAll = useAction(async () => {
    await unwrap(api.POST("/api/troupes/{troupe_id}/posts/read", { params: { path: { troupe_id: troupeId }, query: { kind } } }));
    setOlder((o) => (o ? { ...o, posts: o.posts.map((p) => ({ ...p, unread: false })) } : o));
    await client.invalidateQueries({ queryKey: ["posts", troupeId, kind] });
  });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        {kind === "news" && (agencies.data?.length ?? 0) > 1 ? (
          <div className="min-w-48">
            <Field label="From">
              <Select
                value={filter}
                onChange={(e) => {
                  const next = new URLSearchParams(params);
                  if (e.target.value) next.set("agency", e.target.value);
                  else next.delete("agency");
                  setParams(next, { replace: true });
                }}
              >
                <option value="">Every agency</option>
                {agencies.data?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        ) : (
          <span />
        )}
        <span className="flex flex-wrap gap-2">
          {unread && (
            <Button variant="ghost" disabled={markAll.isPending} onClick={() => markAll.mutate(undefined)}>
              Mark all as read
            </Button>
          )}
          {(writes || proposes) && (
            <Link to="desk" className="inline-flex min-h-10 items-center rounded-md border border-ash bg-dusk px-4 text-sm text-parchment hover:border-mist">
              {writes ? `${words.title} desk` : "Your proposals"}
            </Link>
          )}
        </span>
      </div>
      {list.isPending ? (
        <Loading />
      ) : list.error ? (
        <ErrorText error={list.error} />
      ) : posts.length === 0 ? (
        <Card>
          <Empty>
            {agencyId ? `Nothing from this agency yet.` : `No ${words.nouns} yet.`} {writes && (
              <Link to="write" className="text-gold underline">
                Write the first.
              </Link>
            )}
          </Empty>
        </Card>
      ) : (
        <ul className="flex flex-col gap-3" aria-label={words.title}>
          {posts.map((p) => (
            <StoryCard key={p.id} post={p} agency={agencies.data?.find((a) => a.id === p.agency_id)} to={p.id} />
          ))}
        </ul>
      )}
      {more && (
        <Button variant="secondary" className="self-center" disabled={loading} onClick={() => void showOlder()}>
          {loading ? "Loading…" : `Show older ${words.nouns}`}
        </Button>
      )}
      <ErrorText error={error ?? markAll.error} />
      <p className="text-center text-xs text-mist">
        <Link to={manualLink("players", "reading-the-troupes-news")} className="underline hover:text-parchment">
          About the troupe's news
        </Link>
      </p>
    </div>
  );
}

/** One post, read in full; opening it marks it read. Staff may go on to edit it. */
function PostPage({ troupeId, kind, writes }: { troupeId: string; kind: Kind; writes: boolean }) {
  const { postId = "" } = useParams();
  const words = KINDS[kind];
  const post = usePost(troupeId, kind, postId);
  const agencies = useAgencies(troupeId);
  const markRead = useMarkRead(troupeId, kind);
  const marked = useRef<string | null>(null);
  const p = post.data;
  useEffect(() => {
    if (p?.status === "published" && p.unread && marked.current !== p.id) {
      marked.current = p.id;
      void markRead(p.id).catch(() => undefined);
    }
  }, [p, markRead]);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-3">
      <span className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <Link to=".." relative="path" className="text-mist underline hover:text-parchment">
          All {words.nouns === "stories" ? "news" : words.nouns}
        </Link>
        {writes && p && (
          <Link to="edit" className="text-gold underline hover:text-parchment">
            Edit
          </Link>
        )}
      </span>
      {post.isPending ? (
        <Loading />
      ) : !p ? (
        <Card>
          <Empty>This {words.noun} isn't published any more.</Empty>
        </Card>
      ) : (
        <>
          {p.status !== "published" && <p className="rounded-md border border-gold/40 bg-gold/10 px-3 py-2 text-sm">Not published: only staff see this.</p>}
          <StoryView post={p} agency={agencies.data?.find((a) => a.id === p.agency_id)} />
        </>
      )}
    </div>
  );
}

/** Writing a new post, or changing one, then back to the desk (or to the post, once published). */
function WritePost({ troupeId, kind, writes }: { troupeId: string; kind: Kind; writes: boolean }) {
  const { postId } = useParams();
  const navigate = useNavigate();
  const agencies = useAgencies(troupeId);
  const existing = usePost(troupeId, kind, postId ?? "", !!postId);
  const back = postId ? "../../desk" : "../desk";

  const save = async (fields: Fields, post?: PostOut): Promise<PostOut> => {
    const body = { agency_id: fields.agency_id, title: fields.title, dateline: fields.dateline, body: fields.body };
    if (post) return unwrap(api.PUT("/api/posts/{post_id}", { ...postPath(post.id), body }));
    return unwrap(api.POST("/api/troupes/{troupe_id}/posts", { params: { path: { troupe_id: troupeId } }, body: { ...body, kind } }));
  };
  const act = useAction(async ({ fields, action }: { fields: Fields; action: Action }) => {
    const post = existing.data;
    const saved = await save(fields, post);
    const path = postPath(saved.id);
    if (action.do === "draft" && saved.status === "proposed") await unwrap(api.POST("/api/posts/{post_id}/accept", path));
    if (action.do === "draft" && saved.status === "scheduled") await unwrap(api.POST("/api/posts/{post_id}/unschedule", path));
    if (action.do === "publish") await unwrap(api.POST("/api/posts/{post_id}/publish", { ...path, body: { note: action.note } }));
    if (action.do === "schedule") await unwrap(api.POST("/api/posts/{post_id}/schedule", { ...path, body: { publish_at: action.at } }));
    if (action.do === "decline") await unwrap(api.POST("/api/posts/{post_id}/decline", { ...path, body: { note: action.note } }));
    return { saved, action };
  });
  const picture = useAction(async ({ fields, file }: { fields: Fields; file: File }) => {
    const saved = existing.data ? existing.data : await save(fields);
    const form = new FormData();
    form.append("file", file);
    await unwrap(api.POST("/api/posts/{post_id}/picture", { ...postPath(saved.id), body: form as never, bodySerializer: (b: unknown) => b as FormData }));
    if (!existing.data) navigate(`../${saved.id}/edit`, { replace: true, relative: "path" });
  });
  const removePicture = useAction(() => unwrap(api.DELETE("/api/posts/{post_id}/picture", postPath(postId ?? ""))));

  if (agencies.isPending || (postId && existing.isPending)) return <Loading />;
  if (postId && !existing.data) return <ErrorText error={existing.error ?? "No such post."} />;
  const post = postId ? existing.data : undefined;
  const words = KINDS[kind];
  const heading = !post ? (writes ? `Write a ${words.noun}` : `Propose a ${words.noun}`) : post.status === "published" ? `Edit the published ${words.noun}` : `Edit the ${words.noun}`;
  return (
    <Card title={heading} className="mx-auto max-w-3xl">
      <PostForm
        key={post?.id ?? "new"}
        kind={kind}
        post={post}
        writes={writes}
        agencies={agencies.data ?? []}
        busy={act.isPending || picture.isPending || removePicture.isPending}
        error={act.error ?? picture.error ?? removePicture.error}
        onAction={(fields, action) =>
          act.mutate(
            { fields, action },
            {
              onSuccess: ({ saved, action: done }) => navigate(done.do === "publish" || (done.do === "save" && saved.status === "published") ? `${postId ? "../.." : ".."}/${saved.id}` : back, { relative: "path" }),
            },
          )
        }
        onPicture={(fields, file) => picture.mutate({ fields, file })}
        onRemovePicture={() => removePicture.mutate(undefined)}
        onCancel={() => navigate(back, { relative: "path" })}
      />
    </Card>
  );
}

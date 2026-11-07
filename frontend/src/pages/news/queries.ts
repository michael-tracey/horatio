import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { PostOut, PostPage } from "../../api/types";
import { listKey, type Kind } from "./posts";

const troupePath = (troupeId: string) => ({ params: { path: { troupe_id: troupeId } } });
export const postPath = (postId: string) => ({ params: { path: { post_id: postId } } });

/** The troupe's news agencies, for mastheads and the filter: every member reads them. */
export function useAgencies(troupeId: string) {
  return useQuery({
    queryKey: ["agencies", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/agencies", troupePath(troupeId))),
  });
}

/** The first page of a kind's published posts (the last 30 days), the one a device keeps. */
export function usePublished(troupeId: string, kind: Kind, agencyId?: string) {
  return useQuery({
    queryKey: listKey(troupeId, kind, agencyId),
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/posts", { params: { path: { troupe_id: troupeId }, query: { kind, agency_id: agencyId } } })),
  });
}

export function olderPosts(troupeId: string, kind: Kind, before: string, agencyId?: string): Promise<PostPage> {
  return unwrap(api.GET("/api/troupes/{troupe_id}/posts", { params: { path: { troupe_id: troupeId }, query: { kind, before, agency_id: agencyId } } }));
}

/** What staff are writing: everything not yet published, or a narrator's own proposals. */
export function useDesk(troupeId: string, kind: Kind, enabled = true) {
  return useQuery({
    queryKey: ["post-desk", troupeId, kind],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/posts/desk", { params: { path: { troupe_id: troupeId }, query: { kind } } })),
    enabled,
  });
}

/** Unread counts and the latest headline, for the tabs and the front page. */
export function useGlance(troupeId: string, enabled = true) {
  return useQuery({
    queryKey: ["posts-glance", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/posts/glance", troupePath(troupeId))),
    enabled,
    refetchInterval: 120_000,
  });
}

/** One post: from a list already on hand (so a kept story opens offline), or asked for. */
export function usePost(troupeId: string, kind: Kind, postId: string, enabled = true) {
  const client = useQueryClient();
  const held = () => {
    for (const [, data] of client.getQueriesData<PostPage>({ queryKey: ["posts", troupeId, kind] })) {
      const found = data?.posts?.find((p) => p.id === postId);
      if (found) return found;
    }
    for (const [, data] of client.getQueriesData<{ posts: PostOut[] }>({ queryKey: ["post-desk", troupeId, kind] })) {
      const found = data?.posts?.find((p) => p.id === postId);
      if (found) return found;
    }
    return undefined;
  };
  return useQuery({
    queryKey: ["post", postId],
    queryFn: () => unwrap(api.GET("/api/posts/{post_id}", postPath(postId))),
    placeholderData: held,
    enabled,
  });
}

/** Mark a post read, there and then: its dot goes from the lists, and the counts follow. */
export function useMarkRead(troupeId: string, kind: Kind) {
  const client = useQueryClient();
  return async (postId: string) => {
    await unwrap(api.POST("/api/posts/{post_id}/read", postPath(postId)));
    client.setQueriesData<PostPage>({ queryKey: ["posts", troupeId, kind] }, (page) =>
      page ? { ...page, posts: page.posts.map((p) => (p.id === postId ? { ...p, unread: false } : p)) } : page,
    );
    client.setQueryData<PostOut>(["post", postId], (post) => (post ? { ...post, unread: false } : post));
    await client.invalidateQueries({ queryKey: ["posts-glance", troupeId] });
  };
}

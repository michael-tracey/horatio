import type { PostOut } from "../../api/types";

/**
 * A troupe's posts (horatio.posts): what the News and Announcements pages share.
 * Each kind of post has its own list, desk and words, and they never mix.
 */
export type Kind = PostOut["kind"];

export const KINDS: Record<Kind, { path: string; title: string; noun: string; one: string; nouns: string; channel: string }> = {
  news: { path: "news", title: "News", noun: "story", one: "a story", nouns: "stories", channel: "news" },
  announcement: { path: "announcements", title: "Announcements", noun: "announcement", one: "an announcement", nouns: "announcements", channel: "announcements" },
};

/** The queries a kind's published list is kept under: the first page alone is kept on a device (#502). */
export function listKey(troupeId: string, kind: Kind, agencyId?: string): string[] {
  return agencyId ? ["posts", troupeId, kind, agencyId] : ["posts", troupeId, kind];
}

/** The desk's sections, in order: what waits on someone first. Scheduled ones go soonest first. */
export function deskSections(posts: PostOut[]): { title: string; status: PostOut["status"]; posts: PostOut[] }[] {
  const of = (status: PostOut["status"]) => posts.filter((p) => p.status === status);
  const scheduled = of("scheduled").sort((a, b) => (a.publish_at ?? "").localeCompare(b.publish_at ?? ""));
  return [
    { title: "Proposed by narrators", status: "proposed" as const, posts: of("proposed") },
    { title: "Drafts", status: "draft" as const, posts: of("draft") },
    { title: "Scheduled", status: "scheduled" as const, posts: scheduled },
    { title: "Declined", status: "declined" as const, posts: of("declined") },
  ].filter((s) => s.posts.length > 0);
}

/** Why a time to schedule for can't be used, or null when it can. `at` is the input read on the writer's clock. */
export function scheduleProblem(value: string, at: Date | null, now: Date = new Date()): string | null {
  if (!value || !at || Number.isNaN(at.getTime())) return "Choose a date and time.";
  if (at.getTime() <= now.getTime()) return "Choose a time to come, or publish it now.";
  return null;
}

/** A suggestion for when to schedule: the next whole hour at least half an hour away, as a datetime-local value on the writer's clock. */
export function suggestedTime(now: Date, toInput: (at: Date) => string): string {
  const at = new Date(now.getTime() + 30 * 60_000);
  at.setMinutes(0, 0, 0);
  at.setTime(at.getTime() + 60 * 60_000);
  return toInput(at);
}

/** A story's opening, for the list: its first paragraph as plain words, cut at a word near `max`. */
export function excerpt(body: string, max = 180): string {
  const first =
    body
      .split(/\n\s*\n/)
      .map((p) => p.trim())
      .find((p) => p && !/^(#|>|---|```)/.test(p)) ?? "";
  const plain = first
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_`~]+/g, "")
    .replace(/^\s*([-+]|\d+\.)\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
  if (plain.length <= max) return plain;
  const cut = plain.slice(0, max);
  const space = cut.lastIndexOf(" ");
  return `${(space > max * 0.6 ? cut.slice(0, space) : cut).replace(/[,;:.\s]+$/, "")}…`;
}

/** Ink that reads on a masthead's colour: dark on a light colour, light on a dark one. */
export function inkOn(colour: string): string {
  const hex = /^#([0-9a-f]{6})$/i.exec(colour)?.[1];
  if (!hex) return "#f4ecd8";
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  const light = 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
  return light > 0.4 ? "#111111" : "#f4ecd8";
}

/** An announcement's colour, on Discord and beside it, as it has no masthead (horatio.posts.ANNOUNCEMENT_COLOUR). */
export const ANNOUNCEMENT_COLOUR = "#c9a24a";

/** Discord's limit on an embed's text, less room for the headline (horatio.connectors.discord.EMBED_LIMIT). */
export const EMBED_LIMIT = 4000;

/**
 * The text of each embed a post goes to Discord as, as the server splits it: the
 * dateline in italics, then the body, broken between paragraphs to fit, with the
 * Read in Horatio link at the end of the last. For the preview, so it is rough
 * where the server would cut a long paragraph.
 */
export function discordParts(dateline: string, body: string, limit = EMBED_LIMIT): string[] {
  const read = "Read in Horatio";
  const text = [dateline ? `*${dateline}*` : "", body.trim()].filter(Boolean).join("\n\n");
  const room = limit - read.length - 2;
  const parts: string[] = [];
  let current = "";
  for (const paragraph of text ? text.split("\n\n") : []) {
    for (let piece = paragraph; piece; piece = piece.slice(room)) {
      const chunk = piece.slice(0, room);
      const joined = current ? `${current}\n\n${chunk}` : chunk;
      if (joined.length <= room) current = joined;
      else {
        parts.push(current);
        current = chunk;
      }
    }
  }
  if (current) parts.push(current);
  if (!parts.length) parts.push("");
  parts[parts.length - 1] = parts[parts.length - 1] ? `${parts[parts.length - 1]}\n\n${read}` : read;
  return parts;
}

/** What staff see about where a post is on Discord, in a few words. */
export function discordText(post: PostOut): string | null {
  const d = post.discord;
  if (!d) return null;
  if (d.state === "app_only") return `In the app only: ${d.reason ?? "there is nowhere on Discord for it."}`;
  if (post.status !== "published") return "Goes to Discord when published.";
  if (d.state === "sent") return "On Discord.";
  if (d.state === "failed") return `Not on Discord: ${d.reason ?? "it failed."}`;
  return d.reason ? `Waiting to go to Discord, after: ${d.reason}` : "Waiting to go to Discord.";
}

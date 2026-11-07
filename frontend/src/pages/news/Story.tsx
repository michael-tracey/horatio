import { Link } from "react-router";
import type { AgencyOut, PostOut } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { useDates } from "../../dates";
import { discordParts, excerpt, inkOn } from "./posts";

/** An agency's masthead: its picture, or its name on its colour. */
export function Masthead({ agency, small = false }: { agency: AgencyOut | undefined; small?: boolean }) {
  if (!agency) return null;
  if (agency.picture)
    return <img src={`${agency.picture}/600.webp`} alt={agency.name} className={`${small ? "max-h-8" : "max-h-16"} w-auto max-w-full self-start object-contain object-left`} />;
  return (
    <span
      className={`inline-block self-start rounded-sm font-display tracking-wider uppercase ${small ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-base"}`}
      style={{ backgroundColor: agency.colour, color: inkOn(agency.colour) }}
    >
      {agency.name}
    </span>
  );
}

/** A story in the list: masthead, headline, dateline and opening, with a dot until the person reads it. */
export function StoryCard({ post, agency, to }: { post: PostOut; agency: AgencyOut | undefined; to: string }) {
  const dates = useDates();
  return (
    <li>
      <Link
        to={to}
        className="flex flex-col gap-2 rounded-lg border bg-dusk p-4 hover:border-mist"
        style={{ borderColor: agency?.colour ?? undefined, borderLeftWidth: 4 }}
        aria-label={`${post.unread ? "Unread: " : ""}${post.title}${agency ? `, from ${agency.name}` : ""}`}
      >
        <span className="flex flex-wrap items-center justify-between gap-2">
          <Masthead agency={agency} small />
          {post.published_at && <span className="text-xs text-mist">{dates.due(post.published_at)}</span>}
        </span>
        <span className="flex items-start gap-2">
          {post.unread && <span aria-hidden className="mt-2 h-2.5 w-2.5 shrink-0 rounded-full bg-blood-bright" />}
          <span className="min-w-0 font-display text-lg leading-snug text-parchment">{post.title}</span>
        </span>
        {post.dateline && <span className="text-xs text-mist italic">{post.dateline}</span>}
        {post.body && <span className="text-sm text-parchment/90">{excerpt(post.body)}</span>}
      </Link>
    </li>
  );
}

/** A story as everyone reads it: under its masthead, the dateline, headline, picture and body. */
export function StoryView({ post, agency }: { post: Pick<PostOut, "title" | "dateline" | "body" | "picture" | "published_at">; agency: AgencyOut | undefined }) {
  const dates = useDates();
  return (
    <article className="flex flex-col gap-3 rounded-lg border-t-4 bg-dusk p-4 sm:p-6" style={{ borderTopColor: agency?.colour }}>
      <Masthead agency={agency} />
      {post.dateline && <p className="text-sm text-mist italic">{post.dateline}</p>}
      <h2 className="font-display text-2xl leading-tight text-parchment">{post.title}</h2>
      {post.published_at && <p className="text-xs text-mist">Published {dates.dateTime(post.published_at)}</p>}
      {post.picture && <img src={`${post.picture}/1200.webp`} srcSet={`${post.picture}/600.webp 600w, ${post.picture}/1200.webp 1200w`} sizes="(min-width: 48rem) 48rem, 100vw" alt="" className="w-full rounded-md" />}
      {post.body && <Markdown text={post.body} />}
    </article>
  );
}

/** Roughly how the story will look on Discord: an embed in the masthead's colour, split where Horatio splits it. */
export function DiscordPreview({ post, agency }: { post: Pick<PostOut, "title" | "dateline" | "body" | "picture">; agency: AgencyOut | undefined }) {
  const parts = discordParts(post.dateline, post.body);
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-[#313338] p-3 text-[#dbdee1]" aria-label="On Discord">
      {parts.map((part, i) => (
        <div key={i} className="flex max-w-xl overflow-hidden rounded bg-[#2b2d31]">
          <span aria-hidden className="w-1 shrink-0" style={{ backgroundColor: agency?.colour ?? "#8b1e1e" }} />
          <div className="flex min-w-0 flex-1 gap-3 p-3">
            <div className="flex min-w-0 flex-1 flex-col gap-2 text-sm">
              {i === 0 && agency && <span className="text-xs font-semibold text-white">{agency.name}</span>}
              {i === 0 && <span className="font-semibold text-[#00a8fc]">{post.title || "Headline"}</span>}
              <Markdown text={part} />
              {i === parts.length - 1 && post.picture && <img src={`${post.picture}/600.webp`} alt="" className="max-h-64 w-fit rounded" />}
            </div>
            {i === 0 && agency?.picture && <img src={`${agency.picture}/600.webp`} alt="" className="h-16 w-16 shrink-0 rounded object-contain" />}
          </div>
        </div>
      ))}
    </div>
  );
}

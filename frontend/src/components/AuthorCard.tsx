import { useState } from "react";
import { Link } from "react-router";
import type { AuthorCard as Author } from "../api/types";
import { webLink } from "../markdown";
import { clanColour, initials } from "./avatar";
import { Markdown } from "./Markdown";

/** An author's page on the blog. */
export function authorPath(handle: string): string {
  return `/blog/authors/${encodeURIComponent(handle)}`;
}

/** Each size it shows at, and which of the picture's files fit it (and twice it, for sharp screens). */
const SIZES = {
  md: { px: 80, file: "96", sharp: "256" },
  lg: { px: 160, file: "256", sharp: "512" },
} as const;

/** An author's picture, round, or without one their initials. `picture` is AuthorCard.picture. */
export function AuthorPicture({ name, picture, size = "md" }: { name: string; picture: string | null; size?: keyof typeof SIZES }) {
  const { px, file, sharp } = SIZES[size];
  const [failed, setFailed] = useState<string | null>(null);
  const box = "inline-grid shrink-0 place-items-center overflow-hidden rounded-full border border-ash";
  if (picture && failed !== picture) {
    return (
      <img
        src={`${picture}/${file}.webp`}
        srcSet={`${picture}/${file}.webp 1x, ${picture}/${sharp}.webp 2x`}
        alt=""
        width={px}
        height={px}
        loading="lazy"
        onError={() => setFailed(picture)}
        className={`${box} bg-ash object-cover`}
        style={{ width: px, height: px }}
      />
    );
  }
  return (
    <span aria-hidden="true" className={`${box} font-display text-parchment/90 select-none`} style={{ width: px, height: px, background: clanColour(null), fontSize: px * 0.38 }}>
      {initials(name)}
    </span>
  );
}

/**
 * Who wrote an article (#1159): the author's picture, name, bio and links, as they set them
 * in Account › Blog author, and nothing else about them. Shown under each article (#1158),
 * on the author's page, and as the live preview while they edit it. `linked` makes their
 * name a link to their page.
 */
export function AuthorCard({ author, linked = false, size = "md" }: { author: Author; linked?: boolean; size?: keyof typeof SIZES }) {
  const name = author.display_name.trim() || "Your name";
  return (
    <section aria-label={`About ${name}`} className="flex flex-col gap-4 rounded-lg border border-ash bg-dusk p-4 sm:flex-row sm:items-start">
      <AuthorPicture name={name} picture={author.picture} size={size} />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div>
          <p className="font-display text-lg text-parchment">
            {linked ? (
              <Link to={authorPath(author.handle)} className="hover:text-gold hover:underline">
                {name}
              </Link>
            ) : (
              name
            )}
          </p>
          <p className="text-xs text-mist">@{author.handle}</p>
        </div>
        {author.bio.trim() && <Markdown text={author.bio} />}
        {author.links.length > 0 && (
          <ul aria-label={`${name}'s links`} className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {author.links.map((link, i) => {
              const href = webLink(link.url);
              return (
                <li key={i}>
                  {/* Anyone's links, on a public page: never followed for search ranking. */}
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer nofollow ugc" className="text-gold underline hover:text-parchment">
                      {link.label || link.url}
                    </a>
                  ) : (
                    <span className="break-all">{link.label || link.url}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

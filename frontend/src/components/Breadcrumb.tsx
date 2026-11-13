import { Link } from "react-router";

export type Crumb = { label: string; to: string };

/**
 * Where a page sits, as one quiet line of links back up (#777): "‹Troupe› › At
 * game ›" above a scene or a game night, the page's own heading following it.
 * Only the way back: the page names itself, so this adds nothing to the tab's
 * title.
 */
export function Breadcrumb({ crumbs, className = "" }: { crumbs: Crumb[]; className?: string }) {
  return (
    <nav aria-label="Breadcrumb" className={`min-w-0 ${className}`}>
      <ol className="flex flex-wrap items-center gap-x-1.5 text-sm text-mist">
        {crumbs.map((c) => (
          <li key={c.to} className="flex min-w-0 items-center gap-x-1.5">
            <Link to={c.to} className="inline-flex min-h-10 min-w-0 items-center hover:text-parchment">
              <span className="truncate">{c.label}</span>
            </Link>
            <span aria-hidden="true">›</span>
          </li>
        ))}
      </ol>
    </nav>
  );
}

/** The way back from a troupe's scenes and game nights: the troupe, then its At game tab. */
export function atGameCrumbs(troupeId: string, troupeName: string | undefined): Crumb[] {
  return [
    { label: troupeName ?? "Troupe", to: `/troupes/${troupeId}` },
    { label: "At game", to: `/troupes/${troupeId}/play` },
  ];
}

import { Link } from "react-router";
import type { BlogTroupeCardOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { TroupePill } from "../../components/TroupePill";

/**
 * The troupe an article names, as a card beside its author's (#1160): its portrait, name,
 * abbreviation pill and description, as its public profile shows them, with its name a
 * link to that profile (/t/<id>). Only a troupe that is public and running has a card:
 * the API sends none for any other, and the article names that one only.
 */
export function TroupeCard({ troupe: t }: { troupe: BlogTroupeCardOut }) {
  return (
    <section aria-label={`About ${t.name}`} className="flex flex-col gap-4 rounded-lg border border-ash bg-dusk p-4 sm:flex-row sm:items-start">
      <Avatar name={t.name} picture={t.portrait} size="md" />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div>
          <div className="flex min-w-0 items-center gap-2">
            <p className="min-w-0 font-display text-lg break-words text-parchment">
              <Link to={`/t/${t.id}`} className="hover:text-gold hover:underline">
                {t.name}
              </Link>
            </p>
            {/* What it goes by elsewhere (#1153), when that isn't its name. */}
            {t.abbreviation !== t.name && <TroupePill name={t.name} abbreviation={t.abbreviation} />}
          </div>
          <p className="text-xs text-mist">Troupe</p>
        </div>
        {t.description.trim() && <p className="line-clamp-4 text-sm break-words whitespace-pre-line">{t.description}</p>}
      </div>
    </section>
  );
}

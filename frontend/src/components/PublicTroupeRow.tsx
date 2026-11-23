import { Link } from "react-router";
import type { PublicTroupeOut } from "../api/types";
import { useDatesIn } from "../dates";
import { excerpt } from "../pages/troupeList";
import { Avatar } from "./Avatar";
import { TroupePill } from "./TroupePill";
import { Badge } from "./ui";

/**
 * A troupe anyone may find, as a compact row linking to its public profile: its portrait,
 * name, abbreviation, where it plays and the start of its description (#1164). With
 * `details`, as the troupe directory shows it (#1192), also when it plays and its next
 * game (#1206), as its profile shows them, whether it welcomes new players, its minimum
 * age and its content notes. The next game is on the troupe's clock, if it has a time zone,
 * which the directory's Day takes its day from (#1211), so the row agrees with the day it
 * was found under; else on the viewer's.
 */
export function PublicTroupeRow({ troupe: t, details = false }: { troupe: PublicTroupeOut; details?: boolean }) {
  const dates = useDatesIn(t.time_zone);
  const about = excerpt(t.description);
  const welcoming = details && t.new_players === "welcoming";
  const aged = details && t.min_age !== null;
  return (
    <Link to={`/t/${t.id}`} className="group flex items-start gap-3 py-3">
      <Avatar name={t.name} picture={t.portrait} size="sm" />
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="min-w-0 font-medium break-words text-parchment group-hover:text-gold">{t.name}</span>
          {/* The name is just before it: only the eye needs it again. */}
          {t.abbreviation !== t.name && (
            <span aria-hidden="true" className="contents">
              <TroupePill name={t.name} abbreviation={t.abbreviation} />
            </span>
          )}
          {t.place && <span className="text-xs text-mist">{t.place}</span>}
        </span>
        {details && t.schedule && <span className="text-sm break-words text-parchment">{t.schedule}</span>}
        {details && t.next_game && (
          <span className="text-sm">
            <span className="text-mist">Next game:</span> <span className="text-parchment">{dates.gameStart(t.next_game)}</span>
          </span>
        )}
        {(welcoming || aged) && (
          <span className="flex flex-wrap gap-2">
            {welcoming && <Badge tone="gold">Welcoming new players</Badge>}
            {aged && <Badge>{t.min_age}+</Badge>}
          </span>
        )}
        {about && <span className="line-clamp-2 text-sm text-mist">{about}</span>}
        {details && t.content_notes && (
          <span className="line-clamp-2 text-xs break-words text-mist">
            <span className="text-parchment">Content notes:</span> {t.content_notes}
          </span>
        )}
      </span>
    </Link>
  );
}

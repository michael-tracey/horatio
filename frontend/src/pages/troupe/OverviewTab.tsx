import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { LogList } from "../../components/LogList";
import { AtHandle } from "../../components/PersonPicker";
import { Card, ErrorText, Loading } from "../../components/ui";
import { useDates } from "../../dates";
import { GamesCard } from "./GamesCard";
import type { abilities } from "./roles";
import { sectsText, useSplatsText } from "./SettingsTab";
import { useWaiting, WaitingList } from "./WaitingList";
import { XpRangeCard } from "./XpRange";

/**
 * The troupe at a glance, to read: for its staff, what is waiting on them first;
 * for its members, the games to come, to say whether they are coming, and its
 * calendar to subscribe to; then what the troupe is, when it next plays and who leads it; who may join; its
 * XP floor and ceiling; and, for its running staff, the latest of its log. Nothing
 * here is a setting: those are under Customise, and the full profile is on the
 * Profile tab.
 */
export function OverviewTab({ troupe, can }: { troupe: TroupeOut; can: ReturnType<typeof abilities> }) {
  const base = `/troupes/${troupe.id}`;
  const change = can.storyteller && !troupe.archived;
  const settings = (
    <Link to={`${base}/settings`} className="text-sm text-mist underline hover:text-parchment">
      Change in Customise
    </Link>
  );
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {can.staff && !troupe.archived && <WaitingCard troupeId={troupe.id} />}
      {/* For its members: the same people as see its Who's Who. */}
      {troupe.whos_who && !troupe.archived && <GamesCard troupe={troupe} canAddGames={can.storyteller} />}
      <Summary troupe={troupe} />
      <JoinCard troupe={troupe} link={change && settings} />
      <div className="md:col-span-2">
        <XpRangeCard
          troupeId={troupe.id}
          canEdit={false}
          link={
            <>
              {can.running && (
                <Link to={`${base}/xp`} className="text-sm text-mist underline hover:text-parchment">
                  Award XP
                </Link>
              )}
              {change && settings}
            </>
          }
        />
      </div>
      {can.running && <RecentLog troupeId={troupe.id} />}
    </div>
  );
}

/** What waits on this staff member, one line per kind of work, each a link straight to it. */
function WaitingCard({ troupeId }: { troupeId: string }) {
  const waiting = useWaiting(troupeId);
  return (
    <Card title="Waiting on you" className="md:col-span-2">
      {waiting.isPending ? (
        <Loading />
      ) : waiting.error ? (
        <ErrorText error={waiting.error} />
      ) : waiting.data.length === 0 ? (
        <p className="text-sm text-mist">Nothing waiting.</p>
      ) : (
        <WaitingList lines={waiting.data} label="Waiting on you" />
      )}
    </Card>
  );
}

/** The troupe's description, next game, schedule and lead, from its profile. */
function Summary({ troupe }: { troupe: TroupeOut }) {
  const dates = useDates();
  const profile = useQuery({
    queryKey: ["troupe-profile", troupe.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/profile", { params: { path: { troupe_id: troupe.id } } })),
  });
  const p = profile.data;
  const next = p?.games[0];
  return (
    <Card>
      <div className="flex flex-col gap-3 text-sm">
        {/* Not a heading: the page's own title already is. */}
        <p className="font-display text-lg text-gold">{troupe.name}</p>
        <p className="whitespace-pre-line">{troupe.description || <span className="text-mist">No description yet.</span>}</p>
        {profile.isPending ? (
          <Loading />
        ) : profile.error ? (
          <ErrorText error={profile.error} />
        ) : (
          p && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
              <dt className="text-mist">Next game</dt>
              <dd>{next ? dates.gameStart(next.starts_at) : <span className="text-mist">None planned</span>}</dd>
              {p.schedule && (
                <>
                  <dt className="text-mist">Schedule</dt>
                  <dd>{p.schedule}</dd>
                </>
              )}
              <dt className="text-mist">Lead storyteller</dt>
              <dd>
                <Link to={`/players/${p.lead.id}`} className="hover:text-gold">
                  {p.lead.display_name}
                </Link>{" "}
                <AtHandle handle={p.lead.handle} />
              </dd>
            </dl>
          )
        )}
        <Link to={`/troupes/${troupe.id}/profile`} className="self-start text-mist underline hover:text-parchment">
          See the full profile
        </Link>
      </div>
    </Card>
  );
}

/** Who may join, in two lines: the splats and the sects the troupe takes. */
function JoinCard({ troupe, link }: { troupe: TroupeOut; link: ReactNode }) {
  const { text } = useSplatsText(troupe);
  return (
    <Card title="Who may join" actions={link}>
      <div className="flex flex-col gap-1 text-sm">
        <p>{text} player characters may join.</p>
        <p>{sectsText(troupe.allowed_sects)}</p>
        <p className="text-mist">
          Their house rules are on{" "}
          <Link to={`/troupes/${troupe.id}/house-rules`} className="underline hover:text-parchment">
            House rules
          </Link>
          .
        </p>
      </div>
    </Card>
  );
}

/** The last few lines of the troupe's log, with the way to the rest. */
function RecentLog({ troupeId }: { troupeId: string }) {
  const log = useQuery({
    queryKey: ["log", troupeId, "recent"],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/log", { params: { path: { troupe_id: troupeId }, query: { limit: 5 } } })),
    refetchInterval: 60_000,
  });
  return (
    <Card
      title="Latest in the log"
      className="md:col-span-2"
      actions={
        <Link to={`/troupes/${troupeId}/log`} className="text-sm text-mist underline hover:text-parchment">
          See the whole log
        </Link>
      }
    >
      {log.isPending ? (
        <Loading />
      ) : log.error ? (
        <ErrorText error={log.error} />
      ) : log.data.length === 0 ? (
        <p className="text-sm text-mist">Nothing has happened yet.</p>
      ) : (
        <LogList entries={log.data} linkTo={(e) => (e.character_id ? `/characters/${e.character_id}?troupe=${troupeId}` : null)} />
      )}
    </Card>
  );
}

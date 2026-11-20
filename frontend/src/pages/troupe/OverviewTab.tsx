import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { api, unwrap } from "../../api/client";
import type { PostOut, TroupeOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { useAction } from "../../hooks";
import { LogList } from "../../components/LogList";
import { Card, ErrorText, Loading } from "../../components/ui";
import { useAgencies, useGlance } from "../news/queries";
import { Banners, Masthead } from "../news/Story";
import { ArchiveTroupe } from "./ArchiveTroupe";
import { GamesCard } from "./GamesCard";
import { GettingReadyCard, PROFILE_ANCHOR } from "./GettingReady";
import { NameAndDescription } from "./ProfileControls";
import type { abilities } from "./roles";
import { troupeSettings, type TroupeSettingsPart } from "./features";
import { sectsText, useSplatsText } from "./SettingsTab";
import { TroupeProfileView } from "./TroupeProfile";
import { useWaiting, WaitingList } from "./WaitingList";
import { XpRangeCard } from "./XpRange";

/**
 * The troupe's front page, its Overview (#781, About and Profile in one): for its
 * lead storyteller and storytellers, getting the troupe ready until they hide it
 * (#1049); for its staff, what is waiting on them; for its members, its pinned announcements,
 * the latest of its news and the games to come; then its profile, as its players
 * see it, which its storytellers edit here and switch public; who may join; its
 * XP floor and ceiling; for its running staff, the latest of its log; and its
 * lead's archiving. The troupe's settings are under Customise.
 */
export function OverviewTab({ troupe, can }: { troupe: TroupeOut; can: ReturnType<typeof abilities> }) {
  const base = `/troupes/${troupe.id}`;
  const change = can.storyteller && !troupe.archived;
  const leading = can.lead && !troupe.archived;
  // Who may join and the XP range each have a part of Troupe settings (#908).
  const settings = (part: TroupeSettingsPart) => (
    <Link to={`${base}/${troupeSettings(part)}`} className="text-sm text-mist underline hover:text-parchment">
      Edit in Customise
    </Link>
  );
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 md:grid-cols-2 empty:hidden">
        {change && <GettingReadyCard troupeId={troupe.id} />}
        {can.staff && !troupe.archived && <WaitingCard troupeId={troupe.id} />}
        {/* For its members: the same people as see its Who's Who. */}
        {troupe.whos_who && !troupe.archived && <PinnedBanners troupeId={troupe.id} />}
        {troupe.whos_who && !troupe.archived && <LatestNews troupeId={troupe.id} />}
        {troupe.whos_who && !troupe.archived && <GamesCard troupe={troupe} canAddGames={can.storyteller} running={can.running} />}
      </div>
      <Profile troupe={troupe} leading={leading} />
      <JoinCard troupe={troupe} link={change && settings("joining")} />
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
            {change && settings("xp")}
          </>
        }
      />
      {can.running && <RecentLog troupeId={troupe.id} />}
      {/* The lead's own, at the foot: archiving is rare. Renaming is under Edit profile. */}
      {leading && <ArchiveTroupe troupe={troupe} />}
    </div>
  );
}

/**
 * The troupe's profile, for anyone who can see the troupe, as a player sees it.
 * Its storytellers open its editing parts, and its Signed-in only switch, with
 * Edit profile (#912); its lead finds the troupe's name and description there too.
 */
function Profile({ troupe, leading }: { troupe: TroupeOut; leading: boolean }) {
  const [editing, setEditing] = useState(false);
  const profile = useQuery({
    queryKey: ["troupe-profile", troupe.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/profile", { params: { path: { troupe_id: troupe.id } } })),
  });
  // Getting your troupe ready links here, from above or from Setup (#1049).
  const { hash, key } = useLocation();
  const here = useRef<HTMLDivElement>(null);
  const loaded = !!profile.data;
  useEffect(() => {
    if (loaded && hash === `#${PROFILE_ANCHOR}`) here.current?.scrollIntoView({ block: "start" });
  }, [loaded, hash, key]);
  if (profile.isPending) return <Loading />;
  if (profile.error) return <ErrorText error={profile.error} />;
  return (
    <div id={PROFILE_ANCHOR} ref={here} className="scroll-mt-4">
      <TroupeProfileView
        profile={profile.data}
        signedIn
        editing={editing}
        onEditing={setEditing}
        leadParts={leading && <NameAndDescription troupe={troupe} />}
      />
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

/** The troupe's latest news headline (#510), with how many stories the person hasn't read. Nothing until there is news. */
function LatestNews({ troupeId }: { troupeId: string }) {
  const glance = useGlance(troupeId);
  const agencies = useAgencies(troupeId);
  const latest = glance.data?.latest_news;
  if (!latest) return null;
  const unread = glance.data?.news_unread ?? 0;
  return (
    <Card
      title="Latest news"
      className="md:col-span-2"
      actions={
        <Link to={`/troupes/${troupeId}/news`} className="text-sm text-mist underline hover:text-parchment">
          {unread > 0 ? `${unread} unread` : "All the news"}
        </Link>
      }
    >
      <Link to={`/troupes/${troupeId}/news/${latest.id}`} className="flex flex-col gap-1 hover:text-gold">
        <Masthead agency={agencies.data?.find((a) => a.id === latest.agency_id)} small />
        <span className="font-display text-lg">{latest.title}</span>
        {latest.dateline && <span className="text-xs text-mist italic">{latest.dateline}</span>}
      </Link>
    </Card>
  );
}

/** Pinned announcements (#511) the person hasn't dismissed, as banners at the top. */
function PinnedBanners({ troupeId }: { troupeId: string }) {
  const glance = useGlance(troupeId);
  const toast = useToast();
  const dismiss = useAction((post: PostOut) => unwrap(api.POST("/api/posts/{post_id}/dismiss", { params: { path: { post_id: post.id } } })));
  return (
    <Banners
      troupeId={troupeId}
      banners={glance.data?.banners ?? []}
      busy={dismiss.isPending}
      onDismiss={(post) => dismiss.mutate(post, { onSuccess: () => toast({ message: "Dismissed. It's still under Announcements." }) })}
    />
  );
}

import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Avatar } from "../../components/Avatar";
import { NotOpenHere } from "../../components/NotOpenHere";
import { Badge, ErrorText, GroupedTabs, Loading, PageTitle } from "../../components/ui";
import { useMe } from "../../hooks";
import { ApprovalsPages } from "./ApprovalsTab";
import { BondsPages } from "./BondsPages";
import { BoonsPages } from "./BoonsPages";
import { ConnectorsTab } from "./ConnectorsTab";
import { CyclesTab } from "./CyclesTab";
import { EquipmentTab } from "./EquipmentTab";
import { PartSettings, TabSettings } from "./FeatureSettings";
import { FindSetting } from "./FindSetting";
import { GameNightPage } from "./GameNight";
import { HouseRulesTab } from "./HouseRulesTab";
import { InfluenceLogTab } from "./InfluenceLogTab";
import { LinesVeilsTab } from "./LinesVeilsTab";
import { LocationsTab } from "./LocationsTab";
import { LogTab } from "./LogTab";
import { StockNpcBuilder } from "./StockNpcBuilder";
import { OldWorkLink, WorkTab } from "./WorkTab";
import { PostsSection } from "../news/PostsSection";
import { useGlance } from "../news/queries";
import { NominationsFooter } from "../nominations/NominationsFooter";
import { NominationsTab } from "../nominations/NominationsTab";
import { OverviewTab } from "./OverviewTab";
import { PlayersTab } from "./PlayersTab";
import { QuestsTab } from "./QuestsTab";
import { PlayHere } from "./PlayHere";
import { PlayTab } from "./PlayTab";
import { abilities, roleLabel } from "./roles";
import { RosterTab } from "./RosterTab";
import { TroupeImportPage } from "./TroupeImport";
import { OldRulesLink, RulesTab } from "./RulesTab";
import { SettingsTab } from "./SettingsTab";
import { SettingPages } from "./SettingTab";
import { SharedBackgroundsTab } from "./SharedBackgroundsTab";
import { ShareSettingsTab } from "./ShareSettingsTab";
import { SpecializationsTab } from "./SpecializationsTab";
import { StaffTab } from "./StaffTab";
import { statusLink } from "../rules/rulesBrowser";
import { TablesTab } from "./TablesTab";
import { TitlesTab } from "./TitlesTab";
import { useRecentTabs } from "./recentTabs";
import { troupeTabGroups } from "./troupeTabs";
import { useWaiting } from "./WaitingList";
import { tabCounts } from "./waiting";
import { WhosWhoTab } from "./WhosWhoTab";
import { XpAwardsTab } from "./XpAwardsTab";

// The court over time (#712) draws with the chart kit, so d3 loads only when it is opened.
const CourtTab = lazy(() => import("./CourtTab").then((m) => ({ default: m.CourtTab })));
// The chronicle (#711) too.
const ChronicleTab = lazy(() => import("./ChronicleTab").then((m) => ({ default: m.ChronicleTab })));
// A downtime cycle's pages (#776), as they loaded apart when they were a page of their own.
const CyclePage = lazy(() => import("./CyclePage").then((m) => ({ default: m.CyclePage })));
// The web of obligation (#709) draws with the chart kit too.
const ObligationWeb = lazy(() => import("./ObligationWeb").then((m) => ({ default: m.ObligationWeb })));

export function TroupePage() {
  const { troupeId = "" } = useParams();
  const { pathname } = useLocation();
  const me = useMe();
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  // What waits on the staff member, for the tab counts: the same lines as About's
  // Waiting on you, so the two agree.
  const staff = troupe.data ? abilities(troupe.data.my_role, me.data?.is_custodian ?? false).staff : false;
  const waiting = useWaiting(troupeId, staff && !troupe.data?.archived);
  const counts = tabCounts(waiting.data);
  // What its members haven't read of its news (#510) and its announcements (#511), each counted apart.
  const glance = useGlance(troupeId, !!troupe.data?.whos_who && !troupe.data.archived);
  // Characters built to its rules whose players haven't asked to join yet (#774).
  const running = troupe.data ? abilities(troupe.data.my_role, me.data?.is_custodian ?? false).running : false;
  const building = useQuery({
    queryKey: ["builds-count", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/builds/count", { params: { path: { troupe_id: troupeId } } })),
    enabled: running && !troupe.data?.archived,
  });

  const groups = troupe.data
    ? troupeTabGroups(troupe.data, abilities(troupe.data.my_role, me.data?.is_custodian ?? false), {
        ...counts,
        newsUnread: glance.data?.news_unread,
        announcementsUnread: glance.data?.announcements_unread,
      })
    : [];
  // The tabs opened last here, for the top of the phone's list (#1048).
  const recent = useRecentTabs(
    troupeId,
    groups.flatMap((g) => g.tabs),
    !!troupe.data && (!troupe.data.archived || !!me.data?.is_custodian),
  );

  if (troupe.isPending) return <Loading />;
  if (troupe.error) return <ErrorText error={troupe.error} />;
  const t = troupe.data;
  const can = abilities(t.my_role, me.data?.is_custodian ?? false);
  const base = `/troupes/${t.id}`;
  // A feature's settings are behind its tab's Settings button (#784, #909): running staff read
  // them, and its storytellers change them while the troupe is in play.
  const settings = can.running;
  const changes = can.storyteller && !t.archived;
  // On any Setting up tab, Find a setting is at the top (#1047).
  const settingUp = groups.some((g) => g.label === "Setting up" && g.tabs.some((tab) => pathname === tab.to || pathname.startsWith(`${tab.to}/`)));

  return (
    <>
      {t.banner && (
        <img
          src={`${t.banner}/1500.webp`}
          srcSet={`${t.banner}/750.webp 750w, ${t.banner}/1500.webp 1500w`}
          sizes="(min-width: 64rem) 64rem, 100vw"
          alt=""
          className="mb-4 aspect-[3/1] w-full rounded-lg border border-ash object-cover"
        />
      )}
      <PageTitle actions={t.my_role && <Badge tone="gold">{roleLabel(t.my_role)}</Badge>} subtitle={t.archived ? "Archived" : undefined}>
        <span className="inline-flex items-center gap-3">
          {t.portrait && <Avatar name={t.name} picture={t.portrait} size="sm" />}
          {t.name}
        </span>
      </PageTitle>
      <GroupedTabs label="Troupe sections" groups={groups} recent={recent} />
      {settingUp && <FindSetting troupe={t} can={can} />}
      {!can.staff && !t.archived && <PlayHere troupe={t} />}
      <Routes>
        <Route index element={<OverviewTab troupe={t} can={can} />} />
        {/* The profile is on the Overview now (#781). */}
        <Route path="profile" element={<Navigate to={base} replace />} />
        {/* One House rules tab (#782): players read it; running staff also find each kind of rule in its own part. */}
        <Route path="house-rules/*" element={can.running ? <RulesTab troupe={t} canEdit={can.storyteller} /> : <HouseRulesTab troupe={t} staff={false} />} />
        <Route path="setting/*" element={<SettingPages troupeId={t.id} staff={can.running} bible={can.running && !t.archived} />} />
        {/* The status reference moved into the Rulebook, with this troupe chosen (#787). */}
        <Route path="status" element={<Navigate to={statusLink(t.id)} replace />} />
        {t.whos_who && !t.archived && <Route path="news/*" element={<PostsSection troupeId={t.id} kind="news" writes={can.running} proposes={can.staff && !can.running} />} />}
        {/* Announcements are written by storytellers and assistant storytellers only: narrators read them, as players do. */}
        {t.whos_who && !t.archived && <Route path="announcements/*" element={<PostsSection troupeId={t.id} kind="announcement" writes={can.running} proposes={false} />} />}
        {can.staff && <Route path="staff" element={<StaffTab troupe={t} canManage={can.storyteller} />} />}
        {t.whos_who && (
          <Route
            path="whos-who"
            element={
              <>
                {settings && <TabSettings troupe={t} feature="whos_who" canEdit={changes} />}
                <WhosWhoTab troupeId={t.id} />
              </>
            }
          />
        )}
        {t.nominations && (
          <Route path="nominations" element={<NominationsTab troupeId={t.id} canStar={can.running} nominations={!!t.player_nominations} remembrances={!!t.remembrances} />} />
        )}
        {(can.running || (t.whos_who && t.chronicle_players)) && (
          <Route
            path="chronicle"
            element={
              <Suspense fallback={<Loading />}>
                <ChronicleTab troupeId={t.id} />
              </Suspense>
            }
          />
        )}
        {can.running && <Route path="log" element={<LogTab troupeId={t.id} />} />}
        {can.running && (
          <Route
            path="approvals/*"
            element={
              <>
                <PartSettings troupeId={t.id} place="approvals" canEdit={can.storyteller} />
                <ApprovalsPages troupeId={t.id} live={!t.archived} building={building.data?.count} />
              </>
            }
          />
        )}
        {can.running && (
          <Route
            path="roster"
            element={
              <>
                <PartSettings troupeId={t.id} place="characters" canEdit={can.storyteller} />
                <RosterTab troupeId={t.id} canEmail={can.storyteller} />
              </>
            }
          />
        )}
        {can.running && !t.archived && <Route path="roster/import" element={<TroupeImportPage troupeId={t.id} />} />}
        {can.running && <Route path="players" element={<PlayersTab troupeId={t.id} />} />}
        {can.staff && <Route path="lines-and-veils" element={<LinesVeilsTab troupeId={t.id} />} />}
        {can.running && <Route path="equipment" element={<EquipmentTab troupeId={t.id} troupeName={t.name} />} />}
        {can.running && <Route path="shared-backgrounds/*" element={<SharedBackgroundsTab troupeId={t.id} />} />}
        {can.running && <Route path="npcs/:characterId" element={<StockNpcBuilder troupeId={t.id} />} />}
        {can.running && (
          <Route
            path="at-game"
            element={
              <>
                {settings && <TabSettings troupe={t} feature="play_view" canEdit={changes} />}
                <PlayTab troupeId={t.id} />
              </>
            }
          />
        )}
        {can.running && <Route path="award-xp" element={<XpAwardsTab troupeId={t.id} />} />}
        {can.running && <Route path="games/:gameId" element={<GameNightPage troupeId={t.id} />} />}
        {can.running && <Route path="titles" element={<TitlesTab troupeId={t.id} />} />}
        {(can.running || (t.whos_who && t.court_history_players)) && (
          <Route
            path="court-over-time"
            element={
              <Suspense fallback={<Loading />}>
                <CourtTab troupeId={t.id} />
              </Suspense>
            }
          />
        )}
        {can.running && t.boons && (
          <Route
            path="boons/*"
            element={
              <>
                {settings && <TabSettings troupe={t} feature="boons" canEdit={changes} />}
                <BoonsPages troupeId={t.id} holdsReview={t.boon_review} />
              </>
            }
          />
        )}
        {can.running && (t.blood_bonds ?? "off") !== "off" && (
          <Route
            path="bonds/*"
            element={
              <>
                {settings && <TabSettings troupe={t} feature="blood_bonds" canEdit={changes} />}
                <BondsPages troupeId={t.id} />
              </>
            }
          />
        )}
        {/* The standings and statistics were tabs of their own until they joined Boons (#780). */}
        <Route path="boon-standings" element={<Navigate to={`${base}/boons/standings`} replace />} />
        <Route path="boon-statistics" element={<Navigate to={`${base}/boons/statistics`} replace />} />
        {can.running && (
          <Route
            path="web-of-obligation"
            element={
              <Suspense fallback={<Loading />}>
                <ObligationWeb troupeId={t.id} boonsOn={!!t.boons} bondsOn={(t.blood_bonds ?? "off") !== "off"} />
              </Suspense>
            }
          />
        )}
        {can.running && <Route path="downtimes" element={<CyclesTab troupeId={t.id} />} />}
        {can.staff && (
          <Route
            path="downtimes/:cycleId/*"
            element={
              <Suspense fallback={<Loading />}>
                <CyclePage troupeId={t.id} clanName={t.assamite_name} running={can.running} />
              </Suspense>
            }
          />
        )}
        {can.staff && <Route path="my-work" element={<WorkTab troupeId={t.id} />} />}
        {can.staff && <Route path="fill-tables" element={<TablesTab troupeId={t.id} canEdit={can.running} />} />}
        {can.running && <Route path="influence-log/*" element={<InfluenceLogTab troupeId={t.id} />} />}
        {can.running && (
          <Route
            path="locations/*"
            element={
              <>
                <PartSettings troupeId={t.id} place="locations" canEdit={can.storyteller} />
                <LocationsTab troupeId={t.id} questsOn={t.quests_enabled} />
              </>
            }
          />
        )}
        {can.staff && t.quests_enabled && (
          <Route
            path="quests/*"
            element={
              <>
                {can.running && <PartSettings troupeId={t.id} place="quests" canEdit={can.storyteller} />}
                <QuestsTab troupeId={t.id} running={can.running} />
              </>
            }
          />
        )}
        {can.running && <Route path="settings/*" element={<SettingsTab troupe={t} canEdit={can.storyteller && !t.archived} />} />}
        {can.running && <Route path="specialisations/*" element={<SpecializationsTab troupeId={t.id} canEdit={can.storyteller} />} />}
        {can.running && <Route path="connectors" element={<ConnectorsTab troupeId={t.id} canEdit={can.storyteller} />} />}
        {can.running && <Route path="export-and-import" element={<ShareSettingsTab troupe={t} canImport={can.storyteller && !t.archived} />} />}
        {/* The status reference was a part of Rules, then the Troupe group's Status tab, before the Rulebook. */}
        <Route path="rules/status" element={<Navigate to={statusLink(t.id)} replace />} />
        {/* Customise › Rules became the House rules tab (#782): an old address goes to the same part of it. */}
        <Route path="rules/*" element={<OldRulesLink troupeId={t.id} />} />
        {/* NPCs were a tab of their own until they joined the Characters list (#556). */}
        <Route path="npcs" element={<Navigate to={`${base}/roster?show=npcs`} replace />} />
        {/* An old work/:cycleId link goes to the cycle's own My work (#789). */}
        {can.staff && <Route path="work/:cycleId" element={<OldWorkLink troupeId={t.id} />} />}
        {/* Every tab's address became its name, and four tabs became parts of others (#1048): the old addresses, kept for good. */}
        {Object.entries(MOVED).map(([from, to]) => (
          <Route key={from} path={`${from}/*`} element={<Moved to={`${base}/${to}`} />} />
        ))}
        {/* A tab not open to them, or no such tab (#907). */}
        <Route path="*" element={<NotOpenHere name={t.name} to={base} />} />
      </Routes>
      {/* Every starred nomination, for the troupe's players and staff (#470). */}
      {t.nominations && t.player_nominations && <NominationsFooter troupeId={t.id} />}
    </>
  );
}

/**
 * The old address of each tab whose address became its name, or that became a part of
 * another tab (#1048), and where it is now, under the troupe. Kept for good: links in old
 * emails, bell messages, Discord posts and bookmarks still land.
 */
export const MOVED: Record<string, string> = {
  "story-bible": "setting/story-bible",
  "being-built": "approvals/being-built",
  "news-agencies": "news/agencies",
  customise: "settings/getting-ready",
  characters: "roster",
  "lines-veils": "lines-and-veils",
  shared: "shared-backgrounds",
  play: "at-game",
  xp: "award-xp",
  court: "court-over-time",
  obligations: "web-of-obligation",
  work: "my-work",
  tables: "fill-tables",
  influence: "influence-log",
  specializations: "specialisations",
  share: "export-and-import",
};

/** An old address: the same place at its new one, with whatever followed it, its query and its anchor. */
function Moved({ to }: { to: string }) {
  const rest = useParams()["*"] ?? "";
  const { search, hash } = useLocation();
  return <Navigate to={`${to}${rest ? `/${rest}` : ""}${search}${hash}`} replace />;
}

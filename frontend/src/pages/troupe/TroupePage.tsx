import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Avatar } from "../../components/Avatar";
import { Badge, ErrorText, GroupedTabs, Loading, PageTitle } from "../../components/ui";
import { useMe } from "../../hooks";
import { ApprovalsTab } from "./ApprovalsTab";
import { BeingBuiltTab } from "./BeingBuiltTab";
import { BondsPages } from "./BondsPages";
import { BoonsPages } from "./BoonsPages";
import { ConnectorsTab } from "./ConnectorsTab";
import { CyclesTab } from "./CyclesTab";
import { EquipmentTab } from "./EquipmentTab";
import { TabSettings } from "./FeatureSettings";
import { GameNightPage } from "./GameNight";
import { HouseRulesTab } from "./HouseRulesTab";
import { InfluenceLogTab } from "./InfluenceLogTab";
import { LinesVeilsTab } from "./LinesVeilsTab";
import { LocationsTab } from "./LocationsTab";
import { LogTab } from "./LogTab";
import { StockNpcBuilder } from "./StockNpcBuilder";
import { OldWorkLink, WorkTab } from "./WorkTab";
import { AgenciesTab } from "../news/AgenciesTab";
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
import { RulesTab } from "./RulesTab";
import { SettingsTab } from "./SettingsTab";
import { SettingTab } from "./SettingTab";
import { SetupTab } from "./SetupTab";
import { SharedBackgroundsTab } from "./SharedBackgroundsTab";
import { ShareSettingsTab } from "./ShareSettingsTab";
import { SpecializationsTab } from "./SpecializationsTab";
import { StaffTab } from "./StaffTab";
import { StatusRulesTab } from "./StatusRulesSection";
import { TablesTab } from "./TablesTab";
import { TitlesTab } from "./TitlesTab";
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

  if (troupe.isPending) return <Loading />;
  if (troupe.error) return <ErrorText error={troupe.error} />;
  const t = troupe.data;
  const can = abilities(t.my_role, me.data?.is_custodian ?? false);
  const base = `/troupes/${t.id}`;
  // Those who may change a feature's settings find them folded at the top of its tab (#784).
  const settings = can.storyteller && !t.archived;

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
      <GroupedTabs
        label="Troupe sections"
        groups={troupeTabGroups(t, can, {
          ...counts,
          building: building.data?.count,
          newsUnread: glance.data?.news_unread,
          announcementsUnread: glance.data?.announcements_unread,
        })}
      />
      {!can.staff && !t.archived && <PlayHere troupe={t} />}
      <Routes>
        <Route index element={<OverviewTab troupe={t} can={can} />} />
        {/* The profile is on the Overview now (#781). */}
        <Route path="profile" element={<Navigate to={base} replace />} />
        <Route path="house-rules" element={<HouseRulesTab troupe={t} staff={can.running} />} />
        <Route path="setting" element={<SettingTab troupeId={t.id} staff={can.running} />} />
        <Route path="status" element={<StatusRulesTab troupe={t} />} />
        {t.whos_who && !t.archived && <Route path="news/*" element={<PostsSection troupeId={t.id} kind="news" writes={can.running} proposes={can.staff && !can.running} />} />}
        {/* Announcements are written by storytellers and assistant storytellers only: narrators read them, as players do. */}
        {t.whos_who && !t.archived && <Route path="announcements/*" element={<PostsSection troupeId={t.id} kind="announcement" writes={can.running} proposes={false} />} />}
        {can.running && <Route path="news-agencies" element={<AgenciesTab troupeId={t.id} archived={t.archived} />} />}
        {can.staff && <Route path="staff" element={<StaffTab troupe={t} canManage={can.storyteller} />} />}
        {t.whos_who && (
          <Route
            path="whos-who"
            element={
              <>
                {settings && <TabSettings troupe={t} feature="whos_who" />}
                <WhosWhoTab troupeId={t.id} />
              </>
            }
          />
        )}
        {t.nominations && (
          <Route path="nominations" element={<NominationsTab troupeId={t.id} canStar={can.running} nominations={!!t.player_nominations} remembrances={!!t.remembrances} />} />
        )}
        {can.running && <Route path="characters" element={<RosterTab troupeId={t.id} canEmail={can.storyteller} />} />}
        {can.running && !t.archived && <Route path="characters/import" element={<TroupeImportPage troupeId={t.id} />} />}
        {can.running && <Route path="players" element={<PlayersTab troupeId={t.id} />} />}
        {can.staff && <Route path="lines-veils" element={<LinesVeilsTab troupeId={t.id} />} />}
        {can.running && (
          <Route
            path="play"
            element={
              <>
                {settings && <TabSettings troupe={t} feature="play_view" />}
                <PlayTab troupeId={t.id} />
              </>
            }
          />
        )}
        {can.running && <Route path="xp" element={<XpAwardsTab troupeId={t.id} />} />}
        {can.running && <Route path="games/:gameId" element={<GameNightPage troupeId={t.id} />} />}
        {/* NPCs were a tab of their own until they joined the Characters list (#556). */}
        <Route path="npcs" element={<Navigate to={`${base}/characters?show=npcs`} replace />} />
        {can.running && <Route path="npcs/:characterId" element={<StockNpcBuilder troupeId={t.id} />} />}
        {can.running && <Route path="titles" element={<TitlesTab troupeId={t.id} />} />}
        {(can.running || (t.whos_who && t.court_history_players)) && (
          <Route
            path="court"
            element={
              <Suspense fallback={<Loading />}>
                <CourtTab troupeId={t.id} />
              </Suspense>
            }
          />
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
        {can.running && (t.blood_bonds ?? "off") !== "off" && (
          <Route
            path="bonds/*"
            element={
              <>
                {settings && <TabSettings troupe={t} feature="blood_bonds" />}
                <BondsPages troupeId={t.id} />
              </>
            }
          />
        )}
        {can.running && t.boons && (
          <Route
            path="boons/*"
            element={
              <>
                {settings && <TabSettings troupe={t} feature="boons" />}
                <BoonsPages troupeId={t.id} />
              </>
            }
          />
        )}
        {/* The standings and statistics were tabs of their own until they joined Boons (#780). */}
        <Route path="boon-standings" element={<Navigate to={`${base}/boons/standings`} replace />} />
        <Route path="boon-statistics" element={<Navigate to={`${base}/boons/statistics`} replace />} />
        {can.running && (
          <Route
            path="obligations"
            element={
              <Suspense fallback={<Loading />}>
                <ObligationWeb troupeId={t.id} boonsOn={!!t.boons} bondsOn={(t.blood_bonds ?? "off") !== "off"} />
              </Suspense>
            }
          />
        )}
        {can.running && <Route path="shared/*" element={<SharedBackgroundsTab troupeId={t.id} />} />}
        {can.running && <Route path="locations/*" element={<LocationsTab troupeId={t.id} questsOn={t.quests_enabled} />} />}
        {can.running && <Route path="equipment" element={<EquipmentTab troupeId={t.id} troupeName={t.name} />} />}
        {can.running && <Route path="approvals" element={<ApprovalsTab troupeId={t.id} />} />}
        {can.running && !t.archived && <Route path="being-built" element={<BeingBuiltTab troupeId={t.id} />} />}
        {can.running && <Route path="customise" element={<SetupTab troupe={t} canEdit={can.storyteller && !t.archived} />} />}
        {can.running && <Route path="settings" element={<SettingsTab troupe={t} canEdit={can.storyteller && !t.archived} />} />}
        {/* The status reference was a part of Rules until it moved to the Troupe group. */}
        <Route path="rules/status" element={<Navigate to={`${base}/status`} replace />} />
        {can.running && <Route path="rules/*" element={<RulesTab troupeId={t.id} canEdit={can.storyteller} />} />}
        {can.running && <Route path="specializations/*" element={<SpecializationsTab troupeId={t.id} canEdit={can.storyteller} />} />}
        {can.running && <Route path="log" element={<LogTab troupeId={t.id} />} />}
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
        {can.running && <Route path="connectors" element={<ConnectorsTab troupeId={t.id} canEdit={can.storyteller} />} />}
        {can.running && <Route path="share" element={<ShareSettingsTab troupe={t} canImport={can.storyteller && !t.archived} />} />}
        {can.staff && <Route path="work" element={<WorkTab troupeId={t.id} />} />}
        {can.staff && <Route path="work/:cycleId" element={<OldWorkLink troupeId={t.id} />} />}
        {can.running && <Route path="influence/*" element={<InfluenceLogTab troupeId={t.id} />} />}
        {can.staff && <Route path="tables" element={<TablesTab troupeId={t.id} canEdit={can.running} />} />}
        {can.staff && t.quests_enabled && <Route path="quests/*" element={<QuestsTab troupeId={t.id} running={can.running} />} />}
      </Routes>
      {/* Every starred nomination, for the troupe's players and staff (#470). */}
      {t.nominations && t.player_nominations && <NominationsFooter troupeId={t.id} />}
    </>
  );
}

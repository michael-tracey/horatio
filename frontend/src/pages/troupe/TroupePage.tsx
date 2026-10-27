import { useQuery } from "@tanstack/react-query";
import { Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Avatar } from "../../components/Avatar";
import { Badge, ErrorText, GroupedTabs, Loading, PageTitle } from "../../components/ui";
import { useMe } from "../../hooks";
import { ApprovalsTab } from "./ApprovalsTab";
import { ConnectorsTab } from "./ConnectorsTab";
import { CyclesTab } from "./CyclesTab";
import { InfluenceLogTab } from "./InfluenceLogTab";
import { LogTab } from "./LogTab";
import { StockNpcBuilder } from "./StockNpcBuilder";
import { NpcsTab } from "./NpcsTab";
import { MyWork, WorkTab } from "./WorkTab";
import { OverviewTab } from "./OverviewTab";
import { PlayersTab } from "./PlayersTab";
import { PlayTab } from "./PlayTab";
import { ProfileTab } from "./ProfileTab";
import { abilities, roleLabel } from "./roles";
import { RosterTab } from "./RosterTab";
import { RulesTab } from "./RulesTab";
import { SharedBackgroundsTab } from "./SharedBackgroundsTab";
import { SpecializationsTab } from "./SpecializationsTab";
import { StaffTab } from "./StaffTab";
import { TablesTab } from "./TablesTab";
import { TitlesTab } from "./TitlesTab";
import { WhosWhoTab } from "./WhosWhoTab";
import { XpAwardsTab } from "./XpAwardsTab";

export function TroupePage() {
  const { troupeId = "" } = useParams();
  const me = useMe();
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  // What waits on the Approvals tab; shares the tab's own query, so they agree.
  const running = troupe.data ? abilities(troupe.data.my_role, me.data?.is_custodian ?? false).running : false;
  const waiting = useQuery({
    queryKey: ["approvals", troupeId, "pending"],
    queryFn: () =>
      unwrap(api.GET("/api/troupes/{troupe_id}/approvals", { params: { path: { troupe_id: troupeId }, query: { state: "pending" } } })),
    enabled: running,
    refetchInterval: 60_000,
  });

  if (troupe.isPending) return <Loading />;
  if (troupe.error) return <ErrorText error={troupe.error} />;
  const t = troupe.data;
  const can = abilities(t.my_role, me.data?.is_custodian ?? false);
  const base = `/troupes/${t.id}`;

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
        groups={[
          {
            label: "Troupe",
            tabs: [
              { to: base, label: "About", end: true },
              { to: `${base}/profile`, label: "Profile" },
              ...(t.whos_who ? [{ to: `${base}/whos-who`, label: "Who's Who" }] : []),
              ...(can.staff ? [{ to: `${base}/staff`, label: "Staff" }] : []),
              ...(can.running ? [{ to: `${base}/log`, label: "Log" }] : []),
            ],
          },
          {
            label: "Characters",
            tabs: [
              ...(can.running ? [{ to: `${base}/characters`, label: "Characters" }] : []),
              ...(can.running ? [{ to: `${base}/npcs`, label: "NPCs" }] : []),
              ...(can.running ? [{ to: `${base}/play`, label: "At game" }] : []),
              ...(can.running ? [{ to: `${base}/xp`, label: "Award XP" }] : []),
              ...(can.running ? [{ to: `${base}/titles`, label: "Titles" }] : []),
              ...(can.running ? [{ to: `${base}/shared`, label: "Shared backgrounds" }] : []),
              ...(can.running ? [{ to: `${base}/approvals`, label: "Approvals", count: waiting.data?.length ?? 0 }] : []),
            ],
          },
          {
            label: "Players",
            tabs: [...(can.running ? [{ to: `${base}/players`, label: "Players" }] : [])],
          },
          {
            label: "Downtimes",
            tabs: [
              ...(can.running ? [{ to: `${base}/downtimes`, label: "Cycles" }] : []),
              ...(can.staff ? [{ to: `${base}/work`, label: "My work" }] : []),
              ...(can.staff ? [{ to: `${base}/tables`, label: "Fill tables" }] : []),
              ...(can.running ? [{ to: `${base}/influence`, label: "Influence log" }] : []),
            ],
          },
          {
            label: "Customize",
            tabs: [
              ...(can.running ? [{ to: `${base}/rules`, label: "Rules" }] : []),
              ...(can.running ? [{ to: `${base}/specializations`, label: "Specialisations" }] : []),
              ...(can.running ? [{ to: `${base}/connectors`, label: "Connectors" }] : []),
            ],
          },
        ]}
      />
      <Routes>
        <Route index element={<OverviewTab troupe={t} can={can} />} />
        <Route path="profile" element={<ProfileTab troupe={t} can={can} />} />
        {can.staff && <Route path="staff" element={<StaffTab troupe={t} canManage={can.storyteller} />} />}
        {t.whos_who && <Route path="whos-who" element={<WhosWhoTab troupeId={t.id} />} />}
        {can.running && <Route path="characters" element={<RosterTab troupeId={t.id} />} />}
        {can.running && <Route path="players" element={<PlayersTab troupeId={t.id} />} />}
        {can.running && <Route path="play" element={<PlayTab troupeId={t.id} />} />}
        {can.running && <Route path="xp" element={<XpAwardsTab troupeId={t.id} />} />}
        {can.running && <Route path="npcs" element={<NpcsTab troupeId={t.id} />} />}
        {can.running && <Route path="npcs/:characterId" element={<StockNpcBuilder troupeId={t.id} />} />}
        {can.running && <Route path="titles" element={<TitlesTab troupeId={t.id} />} />}
        {can.running && <Route path="shared/*" element={<SharedBackgroundsTab troupeId={t.id} />} />}
        {can.running && <Route path="approvals" element={<ApprovalsTab troupeId={t.id} />} />}
        {can.running && <Route path="rules/*" element={<RulesTab troupeId={t.id} canEdit={can.storyteller} />} />}
        {can.running && <Route path="specializations/*" element={<SpecializationsTab troupeId={t.id} canEdit={can.storyteller} />} />}
        {can.running && <Route path="log" element={<LogTab troupeId={t.id} />} />}
        {can.running && <Route path="downtimes" element={<CyclesTab troupeId={t.id} />} />}
        {can.running && <Route path="connectors" element={<ConnectorsTab troupeId={t.id} canEdit={can.storyteller} />} />}
        {can.staff && <Route path="work" element={<WorkTab troupeId={t.id} />} />}
        {can.staff && <Route path="work/:cycleId" element={<MyWork troupeId={t.id} canLog={can.running} />} />}
        {can.running && <Route path="influence/*" element={<InfluenceLogTab troupeId={t.id} />} />}
        {can.staff && <Route path="tables" element={<TablesTab troupeId={t.id} canEdit={can.running} />} />}
      </Routes>
    </>
  );
}

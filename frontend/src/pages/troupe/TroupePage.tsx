import { useQuery } from "@tanstack/react-query";
import { Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Badge, ErrorText, Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { ApprovalsTab } from "./ApprovalsTab";
import { CyclesTab } from "./CyclesTab";
import { LogTab } from "./LogTab";
import { NpcsTab } from "./NpcsTab";
import { MyWork, WorkTab } from "./WorkTab";
import { OverviewTab } from "./OverviewTab";
import { abilities, roleLabel } from "./roles";
import { RosterTab } from "./RosterTab";
import { StaffTab } from "./StaffTab";
import { TablesTab } from "./TablesTab";
import { TitlesTab } from "./TitlesTab";

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
      <PageTitle actions={t.my_role && <Badge tone="gold">{roleLabel(t.my_role)}</Badge>} subtitle={t.archived ? "Archived" : undefined}>
        {t.name}
      </PageTitle>
      <Tabs
        tabs={[
          { to: base, label: "About", end: true },
          ...(can.staff ? [{ to: `${base}/staff`, label: "Staff" }] : []),
          ...(can.running ? [{ to: `${base}/characters`, label: "Characters" }] : []),
          ...(can.running ? [{ to: `${base}/npcs`, label: "NPCs" }] : []),
          ...(can.running ? [{ to: `${base}/titles`, label: "Titles" }] : []),
          ...(can.running ? [{ to: `${base}/approvals`, label: "Approvals", count: waiting.data?.length ?? 0 }] : []),
          ...(can.running ? [{ to: `${base}/downtimes`, label: "Downtimes" }] : []),
          ...(can.staff ? [{ to: `${base}/work`, label: "My work" }] : []),
          ...(can.staff ? [{ to: `${base}/tables`, label: "Fill tables" }] : []),
          ...(can.running ? [{ to: `${base}/log`, label: "Log" }] : []),
        ]}
      />
      <Routes>
        <Route index element={<OverviewTab troupe={t} can={can} />} />
        {can.staff && <Route path="staff" element={<StaffTab troupe={t} canManage={can.storyteller} />} />}
        {can.running && <Route path="characters" element={<RosterTab troupeId={t.id} />} />}
        {can.running && <Route path="npcs" element={<NpcsTab troupeId={t.id} />} />}
        {can.running && <Route path="titles" element={<TitlesTab troupeId={t.id} />} />}
        {can.running && <Route path="approvals" element={<ApprovalsTab troupeId={t.id} />} />}
        {can.running && <Route path="log" element={<LogTab troupeId={t.id} />} />}
        {can.running && <Route path="downtimes" element={<CyclesTab troupeId={t.id} />} />}
        {can.staff && <Route path="work" element={<WorkTab troupeId={t.id} />} />}
        {can.staff && <Route path="work/:cycleId" element={<MyWork troupeId={t.id} />} />}
        {can.staff && <Route path="tables" element={<TablesTab troupeId={t.id} canEdit={can.running} />} />}
      </Routes>
    </>
  );
}

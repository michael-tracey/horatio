import { Link, Navigate, Route, Routes, useLocation } from "react-router";
import { Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { ArchivedTroupesTab } from "./ArchivedTroupesTab";
import { AuditTab } from "./AuditTab";
import { BackupsTab } from "./BackupsTab";
import { ClanLogosTab } from "./ClanLogosTab";
import { PeopleTab } from "./PeopleTab";
import { SettingsTab } from "./SettingsTab";
import { SystemTab } from "./SystemTab";
import { ToolsTab } from "./ToolsTab";
import { TroupeRequestsTab, useTroupeRequests } from "./TroupeRequestsTab";
import { YorickImportTab } from "./YorickImportTab";

/** What only the custodian can do, in one place. Anyone else is sent away. */
export function CustodianPage() {
  const me = useMe();
  const requests = useTroupeRequests(!!me.data?.is_custodian);
  if (me.isPending) return <Loading />;
  if (!me.data?.is_custodian) return <Navigate to="/characters" replace />;

  return (
    <>
      <PageTitle subtitle="Looking after Horatio as a whole: its people, its troupes and its data.">Custodian</PageTitle>
      <Tabs
        tabs={[
          { to: "/custodian/people", label: "People" },
          { to: "/custodian/troupe-requests", label: "Troupe requests", count: requests.data?.filter((r) => r.status === "pending").length ?? 0 },
          { to: "/custodian/archived-troupes", label: "Archived troupes" },
          { to: "/custodian/clan-logos", label: "Clan logos" },
          { to: "/custodian/backups", label: "Backups" },
          { to: "/custodian/audit", label: "Audit" },
          { to: "/custodian/settings", label: "Settings" },
          { to: "/custodian/system", label: "System" },
          { to: "/custodian/tools", label: "Tools" },
        ]}
      />
      <Routes>
        <Route index element={<Navigate to="people" replace />} />
        <Route path="people" element={<PeopleTab />} />
        <Route path="troupe-requests" element={<TroupeRequestsTab />} />
        <Route path="archived-troupes" element={<ArchivedTroupesTab />} />
        <Route path="clan-logos" element={<ClanLogosTab />} />
        {/* Moved under Tools (#758); old links, with their ?troupe=, still land there. */}
        <Route path="yorick-import" element={<ToYorickImport />} />
        <Route path="backups" element={<BackupsTab />} />
        <Route path="audit" element={<AuditTab />} />
        <Route path="settings" element={<SettingsTab />} />
        <Route path="system" element={<SystemTab />} />
        <Route path="tools" element={<ToolsTab />} />
        <Route
          path="tools/yorick-import"
          element={
            <>
              <Link to="/custodian/tools" className="mb-3 inline-block text-sm text-mist hover:text-parchment">
                ← Tools
              </Link>
              <YorickImportTab />
            </>
          }
        />
      </Routes>
    </>
  );
}

/** The import's old address, sent on to its place under Tools with its query kept. */
function ToYorickImport() {
  const { search } = useLocation();
  return <Navigate to={`/custodian/tools/yorick-import${search}`} replace />;
}

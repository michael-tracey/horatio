import { Link, Navigate, Route, Routes, useLocation } from "react-router";
import { Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { AuditTab } from "./AuditTab";
import { BackupsTab } from "./BackupsTab";
import { ClanLogosTab } from "./ClanLogosTab";
import { PeopleTab } from "./PeopleTab";
import { SiteTab } from "./SiteTab";
import { ToolsTab } from "./ToolsTab";
import { TroupeManagementTab } from "./TroupeManagementTab";
import { useTroupeRequests } from "./TroupeRequestsTab";
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
          { to: "/custodian/troupe-management", label: "Troupe management", count: requests.data?.filter((r) => r.status === "pending").length ?? 0 },
          { to: "/custodian/clan-logos", label: "Clan logos" },
          { to: "/custodian/backups", label: "Backups" },
          { to: "/custodian/audit", label: "Audit" },
          { to: "/custodian/site", label: "Site" },
          { to: "/custodian/tools", label: "Tools" },
        ]}
      />
      <Routes>
        <Route index element={<Navigate to="people" replace />} />
        <Route path="people" element={<PeopleTab />} />
        <Route path="troupe-management" element={<TroupeManagementTab />} />
        {/* Their own tabs until #759; old links land on their sections. */}
        <Route path="troupe-requests" element={<Navigate to="/custodian/troupe-management#requests" replace />} />
        <Route path="archived-troupes" element={<Navigate to="/custodian/troupe-management#archived" replace />} />
        <Route path="clan-logos" element={<ClanLogosTab />} />
        {/* Moved under Tools (#758); old links, with their ?troupe=, still land there. */}
        <Route path="yorick-import" element={<ToYorickImport />} />
        <Route path="backups" element={<BackupsTab />} />
        <Route path="audit" element={<AuditTab />} />
        <Route path="site" element={<SiteTab />} />
        {/* Their own tabs until #790; old links land on Site. */}
        <Route path="settings" element={<Navigate to="/custodian/site" replace />} />
        <Route path="system" element={<Navigate to="/custodian/site" replace />} />
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

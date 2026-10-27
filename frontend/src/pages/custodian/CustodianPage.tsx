import { Navigate, Route, Routes } from "react-router";
import { Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { ArchivedTroupesTab } from "./ArchivedTroupesTab";
import { BackupsTab } from "./BackupsTab";
import { ClanLogosTab } from "./ClanLogosTab";
import { PeopleTab } from "./PeopleTab";
import { SystemTab } from "./SystemTab";
import { TroupeRequestsTab, useTroupeRequests } from "./TroupeRequestsTab";

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
          { to: "/custodian/system", label: "System" },
        ]}
      />
      <Routes>
        <Route index element={<Navigate to="people" replace />} />
        <Route path="people" element={<PeopleTab />} />
        <Route path="troupe-requests" element={<TroupeRequestsTab />} />
        <Route path="archived-troupes" element={<ArchivedTroupesTab />} />
        <Route path="clan-logos" element={<ClanLogosTab />} />
        <Route path="backups" element={<BackupsTab />} />
        <Route path="system" element={<SystemTab />} />
      </Routes>
    </>
  );
}

import { Navigate, Route, Routes } from "react-router";
import { Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { BackupsTab } from "./BackupsTab";
import { PeopleTab } from "./PeopleTab";
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
          { to: "/custodian/backups", label: "Backups" },
        ]}
      />
      <Routes>
        <Route index element={<Navigate to="people" replace />} />
        <Route path="people" element={<PeopleTab />} />
        <Route path="troupe-requests" element={<TroupeRequestsTab />} />
        <Route path="backups" element={<BackupsTab />} />
      </Routes>
    </>
  );
}

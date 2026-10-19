import { Navigate, Route, Routes } from "react-router";
import { Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { BackupsTab } from "./BackupsTab";
import { PeopleTab } from "./PeopleTab";

/** What only the custodian can do, in one place. Anyone else is sent away. */
export function CustodianPage() {
  const me = useMe();
  if (me.isPending) return <Loading />;
  if (!me.data?.is_custodian) return <Navigate to="/characters" replace />;

  return (
    <>
      <PageTitle subtitle="Looking after Horatio as a whole: its people and its data.">Custodian</PageTitle>
      <Tabs
        tabs={[
          { to: "/custodian/people", label: "People" },
          { to: "/custodian/backups", label: "Backups" },
        ]}
      />
      <Routes>
        <Route index element={<Navigate to="people" replace />} />
        <Route path="people" element={<PeopleTab />} />
        <Route path="backups" element={<BackupsTab />} />
      </Routes>
    </>
  );
}

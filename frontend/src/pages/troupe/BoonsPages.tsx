import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { Loading, PageTabs } from "../../components/ui";
import { BoonStandingsTab } from "./BoonStandingsTab";
import { BoonsTab } from "./BoonsTab";

// The statistics bring d3 with them (#702), so they load only when opened (#706).
const BoonStatisticsPage = lazy(() => import("./BoonStatisticsPage").then((m) => ({ default: m.BoonStatisticsPage })));

/** The troupe's boons, for its running staff, as one tab (#780): the ledger, the standings and the statistics. */
export function BoonsPages({ troupeId }: { troupeId: string }) {
  const base = `/troupes/${troupeId}/boons`;
  return (
    <>
      <PageTabs
        label="Boons"
        tabs={[
          { to: base, label: "Ledger", end: true },
          { to: `${base}/standings`, label: "Standings" },
          { to: `${base}/statistics`, label: "Statistics" },
        ]}
      />
      <Routes>
        <Route index element={<BoonsTab troupeId={troupeId} />} />
        <Route path="standings" element={<BoonStandingsTab troupeId={troupeId} />} />
        <Route
          path="statistics"
          element={
            <Suspense fallback={<Loading />}>
              <BoonStatisticsPage troupeId={troupeId} />
            </Suspense>
          }
        />
      </Routes>
    </>
  );
}

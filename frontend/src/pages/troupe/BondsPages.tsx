import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { Loading, PageTabs } from "../../components/ui";
import { BondsTab } from "./BondsTab";

// The web draws with d3, which only it loads (#706, #708).
const BondWeb = lazy(() => import("./BondWeb").then((m) => ({ default: m.BondWeb })));

/** The troupe's blood bonds, for its running staff: the list, and the same bonds as a web (#708). */
export function BondsPages({ troupeId }: { troupeId: string }) {
  const base = `/troupes/${troupeId}/bonds`;
  return (
    <>
      <PageTabs
        label="Blood bonds"
        tabs={[
          { to: base, label: "Bonds", end: true },
          { to: `${base}/web`, label: "Web" },
        ]}
      />
      <Routes>
        <Route index element={<BondsTab troupeId={troupeId} />} />
        <Route
          path="web"
          element={
            <Suspense fallback={<Loading />}>
              <BondWeb troupeId={troupeId} />
            </Suspense>
          }
        />
      </Routes>
    </>
  );
}

import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useState, type ReactNode } from "react";
import { Navigate, Route, Routes, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Empty, ErrorText, Loading, Select } from "../../components/ui";
import { BackLink } from "../../components/BackLink";
import { usePageWidth, WidePages } from "../../components/widePage";
import { useOnline } from "../../offline/connection";
import { AuditsCard } from "../troupe/BoonAudits";
import { BoonbreakersTab } from "../troupe/Boonbreakers";
import { HarpyMode } from "../troupe/boonKeeper";
import { BoonReviewTab } from "../troupe/BoonReviewTab";
import { BoonStandingsTab } from "../troupe/BoonStandingsTab";
import { BoonsTab, type LedgerKeeper } from "../troupe/BoonsTab";
import { BoonTabs, partPath, partTo, type BoonPart } from "../troupe/BoonTabs";
import { TalonsCard } from "../troupe/BoonTalons";
import { useTitle } from "../../title";

// It brings d3, so it loads on its own, only when opened (as on the staff screen).
const BoonStatisticsPage = lazy(() => import("../troupe/BoonStatisticsPage").then((m) => ({ default: m.BoonStatisticsPage })));

/**
 * The boon ledger its Harpy keeps (#688), or one of its Lesser Harpies (#689), linked
 * from the Play View's Boons tab: the review queue, or the whole ledger, as the troupe
 * lets its Harpy reach and the Harpy lets a Lesser Harpy act. Everything done here is
 * logged as done by the character. The Harpy also gives others access here. With no
 * Harpy title or access given, or no access, there is nothing to keep. Where the
 * troupe lets its Harpy read them (#749), the boon standings and statistics too, with
 * who has left as the court knows it. Each part is a tab, as on staff's boons screen
 * (#982): Ledger, To review, Standings, Statistics, Boonbreakers (the Harpy's, not a
 * Lesser Harpy's) and Audits, as far as each reaches; with only the review queue and
 * no standings, the queue alone. The page is as narrow as the Play View, and as wide
 * as staff's from lg up while the ledger's table asks (#985), so a boon opens beside
 * it there. Offline, what shows is as it was, and nothing can be done with it.
 */
export function HarpyLedgerPage() {
  const { characterId = "" } = useParams();
  const ledgers = useQuery({
    queryKey: ["harpy-ledgers", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/harpy-ledgers", { params: { path: { character_id: characterId } } })),
  });
  // A link can name the troupe whose ledger to open (`?troupe=`), as the top bar's search does (#1046).
  const [params] = useSearchParams();
  const [picked, setPicked] = useState<string | null>(() => params.get("troupe"));
  const found = ledgers.isSuccess ? ledgers.data : [];
  const shown = found.find((l) => l.troupe_id === picked) ?? found[0];
  const keeper: LedgerKeeper | null = shown
    ? {
        access: shown.access,
        role: shown.role ?? "harpy",
        add: shown.can_add ?? true,
        edit: shown.can_edit ?? true,
        settle: shown.can_settle ?? true,
        review: shown.can_review ?? true,
        audit: shown.can_audit ?? true,
        export: shown.can_export ?? false,
        word: shown.talon_word ?? "Lesser Harpy",
      }
    : null;

  const full = shown?.access === "full";
  const parts: BoonPart[] = [
    ...(full ? (["ledger"] as const) : []),
    ...(keeper?.review ? (["review"] as const) : []),
    ...(shown?.sees_standings ? (["standings", "statistics"] as const) : []),
    ...(full && keeper?.role === "harpy" ? (["boonbreakers"] as const) : []),
    ...(full && keeper?.audit ? (["audits"] as const) : []),
  ];
  const base = `/play/characters/${characterId}/ledger`;

  const heading = shown?.access === "submissions" ? "Boons to review" : "The boon ledger";
  useTitle(heading);
  // The Play View's width, and staff's from lg up for the ledger's table (#975, #985).
  const page = usePageWidth("max-w-3xl", "max-w-3xl lg:max-w-7xl");
  const online = useOnline();

  return (
    // The sticky header's height, which a boon's side panel stays below (#985).
    <div className="min-h-screen bg-night pb-16 text-parchment [--sticky-top:3.625rem]">
      <header className="play-header">
        <div className={`mx-auto flex ${page.width} items-center justify-between gap-3 px-4 py-2`}>
          <BackLink label="Play View" to={`/play/characters/${characterId}?tab=boons`} />
          <h1 className="text-lg">{heading}</h1>
        </div>
      </header>
      <main className={`mx-auto flex ${page.width} flex-col gap-4 px-4 pt-3`}>
        {ledgers.isPending ? (
          <Loading />
        ) : ledgers.error ? (
          <ErrorText error={ledgers.error} />
        ) : !shown ? (
          <Empty>
            This character keeps no boon ledger: it holds no Harpy title where the troupe gives its Harpy the ledger, and no Harpy has given it access.
          </Empty>
        ) : (
          <>
            {found.length > 1 && (
              <Select aria-label="Troupe" value={shown.troupe_id} onChange={(e) => setPicked(e.target.value)}>
                {found.map((l) => (
                  <option key={l.troupe_id} value={l.troupe_id}>
                    {l.troupe_name}
                  </option>
                ))}
              </Select>
            )}
            <p className="text-sm text-mist">
              As {keeper?.role === "talon" ? `a ${keeper.word}` : "Harpy"} of {shown.troupe_name}.
            </p>
            {!online && (
              <p role="status" className="text-sm text-blood-bright">
                The ledger needs a signal. What shows is as it was; you can act on it again once you have signal.
              </p>
            )}
            <WidePages ask={page.ask}>
              <HarpyMode.Provider value={keeper}>
                <BoonTabs key={shown.troupe_id} troupeId={shown.troupe_id} base={base} parts={parts} holdsReview={!full} />
                <Routes>
                  {parts.map((part) => {
                    const element = partOf(part, shown.troupe_id, keeper!, shown.gives_access ?? false, partTo(base, parts, "review"), online);
                    const path = partPath(parts, part);
                    return path ? <Route key={part} path={path} element={element} /> : <Route key={part} index element={element} />;
                  })}
                  {/* A part this troupe's ledger doesn't give, as after picking another troupe. */}
                  <Route path="*" element={<Navigate to={base} replace />} />
                </Routes>
              </HarpyMode.Provider>
            </WidePages>
          </>
        )}
      </main>
    </div>
  );
}

/**
 * What the keeper does in a part, which offline can't be done (#985): its buttons and
 * fields disabled, its links still links. The ledger disables its own actions.
 */
function Acts({ online, className = "", children }: { online: boolean; className?: string; children: ReactNode }) {
  return (
    <fieldset disabled={!online} className={`flex min-w-0 flex-col gap-4 ${className}`}>
      {children}
    </fieldset>
  );
}

/** A part of the ledger the Harpy keeps, for its tab: each keyed by troupe, so picking another starts it afresh. */
function partOf(part: BoonPart, troupeId: string, keeper: LedgerKeeper, givesAccess: boolean, reviewTo: string, online: boolean) {
  switch (part) {
    case "ledger":
      return (
        <>
          <BoonsTab key={troupeId} troupeId={troupeId} harpy={keeper} review={keeper.review ? reviewTo : undefined} />
          {/* A form: at the Play View's width while the page is wide for the table. */}
          {givesAccess && (
            <Acts online={online} className="max-w-3xl">
              <TalonsCard key={`talons-${troupeId}`} troupeId={troupeId} />
            </Acts>
          )}
        </>
      );
    case "review":
      return (
        <Acts online={online}>
          <BoonReviewTab key={troupeId} troupeId={troupeId} />
        </Acts>
      );
    case "standings":
      return <BoonStandingsTab key={troupeId} troupeId={troupeId} harpy />;
    case "statistics":
      return (
        <Suspense fallback={<Loading />}>
          <BoonStatisticsPage key={troupeId} troupeId={troupeId} harpy />
        </Suspense>
      );
    case "boonbreakers":
      return (
        <Acts online={online}>
          <BoonbreakersTab key={troupeId} troupeId={troupeId} />
        </Acts>
      );
    case "audits":
      return (
        <Acts online={online}>
          <AuditsCard key={troupeId} troupeId={troupeId} inPlay />
        </Acts>
      );
  }
}

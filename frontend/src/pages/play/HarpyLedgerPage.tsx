import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";
import { Link, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Empty, ErrorText, Loading, Select } from "../../components/ui";
import { BoonStandingsTab } from "../troupe/BoonStandingsTab";
import { BoonsTab, type LedgerKeeper } from "../troupe/BoonsTab";
import { TalonsCard } from "../troupe/BoonTalons";
import { useTitle } from "../../title";

// It brings d3, so it loads on its own, only when opened (as on the staff screen).
const BoonStatisticsPage = lazy(() => import("../troupe/BoonStatisticsPage").then((m) => ({ default: m.BoonStatisticsPage })));

type View = "ledger" | "standings" | "statistics";
const VIEWS: { value: View; label: string }[] = [
  { value: "ledger", label: "Ledger" },
  { value: "standings", label: "Standings" },
  { value: "statistics", label: "Statistics" },
];

/**
 * The boon ledger its Harpy keeps (#688), or one of its Lesser Harpies (#689), linked
 * from the Play View's Boons tab: the review queue, or the whole ledger, as the troupe
 * lets its Harpy reach and the Harpy lets a Lesser Harpy act. Everything done here is
 * logged as done by the character. The Harpy also gives others access here. With no
 * Harpy title or access given, or no access, there is nothing to keep. Where the
 * troupe lets its Harpy read them (#749), the boon standings and statistics too, with
 * who has left as the court knows it.
 */
export function HarpyLedgerPage() {
  const { characterId = "" } = useParams();
  const ledgers = useQuery({
    queryKey: ["harpy-ledgers", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/harpy-ledgers", { params: { path: { character_id: characterId } } })),
  });
  const [picked, setPicked] = useState<string | null>(null);
  const [view, setView] = useState<View>("ledger");
  const found = ledgers.isSuccess ? ledgers.data : [];
  const shown = found.find((l) => l.troupe_id === picked) ?? found[0];
  const seen: View = shown?.sees_standings ? view : "ledger";
  const keeper: LedgerKeeper | null = shown
    ? {
        access: shown.access,
        role: shown.role ?? "harpy",
        add: shown.can_add ?? true,
        edit: shown.can_edit ?? true,
        review: shown.can_review ?? true,
        audit: shown.can_audit ?? true,
        word: shown.talon_word ?? "Lesser Harpy",
      }
    : null;

  const heading = shown?.access === "submissions" ? "Boons to review" : "The boon ledger";
  useTitle(heading);

  return (
    <div className="min-h-screen bg-night pb-16 text-parchment">
      <header className="sticky top-0 z-10 border-b border-ash bg-night/95 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
          <Link to={`/play/characters/${characterId}?tab=boons`} className="inline-flex min-h-10 items-center text-sm text-mist hover:text-parchment">
            ← Play View
          </Link>
          <h1 className="text-lg">{heading}</h1>
        </div>
      </header>
      <main className="mx-auto flex max-w-3xl flex-col gap-4 px-4 pt-3">
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
            {shown.sees_standings && (
              <div role="group" aria-label="Show" className="flex flex-wrap gap-2">
                {VIEWS.map((v) => (
                  <button
                    key={v.value}
                    type="button"
                    aria-pressed={seen === v.value}
                    onClick={() => setView(v.value)}
                    className={`min-h-10 rounded border px-3 text-sm ${seen === v.value ? "border-gold text-parchment" : "border-ash text-mist hover:text-parchment"}`}
                  >
                    {v.label}
                  </button>
                ))}
              </div>
            )}
            {seen === "ledger" && (
              <>
                <BoonsTab key={shown.troupe_id} troupeId={shown.troupe_id} harpy={keeper} />
                {shown.gives_access && <TalonsCard key={`talons-${shown.troupe_id}`} troupeId={shown.troupe_id} />}
              </>
            )}
            {seen === "standings" && <BoonStandingsTab key={shown.troupe_id} troupeId={shown.troupe_id} harpy />}
            {seen === "statistics" && (
              <Suspense fallback={<Loading />}>
                <BoonStatisticsPage key={shown.troupe_id} troupeId={shown.troupe_id} harpy />
              </Suspense>
            )}
          </>
        )}
      </main>
    </div>
  );
}

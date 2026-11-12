import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Empty, ErrorText, Loading, Select } from "../../components/ui";
import { BoonsTab } from "../troupe/BoonsTab";

/**
 * The boon ledger its Harpy keeps (#688), linked from the Play View's Boons tab: the
 * review queue, or the whole ledger, as the troupe lets its Harpy reach. Everything
 * done here is logged as done by the character. With no Harpy title, or no access,
 * there is nothing to keep.
 */
export function HarpyLedgerPage() {
  const { characterId = "" } = useParams();
  const ledgers = useQuery({
    queryKey: ["harpy-ledgers", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/harpy-ledgers", { params: { path: { character_id: characterId } } })),
  });
  const [picked, setPicked] = useState<string | null>(null);
  const found = ledgers.isSuccess ? ledgers.data : [];
  const shown = found.find((l) => l.troupe_id === picked) ?? found[0];

  return (
    <div className="min-h-screen bg-night pb-16 text-parchment">
      <header className="sticky top-0 z-10 border-b border-ash bg-night/95 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
          <Link to={`/play/characters/${characterId}?tab=boons`} className="inline-flex min-h-10 items-center text-sm text-mist hover:text-parchment">
            ← Play View
          </Link>
          <h1 className="text-lg">{shown?.access === "submissions" ? "Boons to review" : "The boon ledger"}</h1>
        </div>
      </header>
      <main className="mx-auto flex max-w-3xl flex-col gap-4 px-4 pt-3">
        {ledgers.isPending ? (
          <Loading />
        ) : ledgers.error ? (
          <ErrorText error={ledgers.error} />
        ) : !shown ? (
          <Empty>This character keeps no boon ledger: it holds no Harpy title where the troupe gives its Harpy the ledger.</Empty>
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
            <p className="text-sm text-mist">As Harpy of {shown.troupe_name}.</p>
            <BoonsTab key={shown.troupe_id} troupeId={shown.troupe_id} harpy={shown.access} />
          </>
        )}
      </main>
    </div>
  );
}
